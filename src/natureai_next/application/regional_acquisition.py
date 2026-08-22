"""Automatic acquisition and installation of regional GBIF taxonomy evidence."""

from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path

from natureai_next import __version__
from natureai_next.application.ai_resources import LocalAIResourceService
from natureai_next.application.ai_setup import BioCLIPQuickSetupService
from natureai_next.domain.regional import RegionalCountry, RegionalProfile
from natureai_next.domain.taxonomy import LicenseMetadata
from natureai_next.ports.taxonomy_packages import (
    TaxonomyPackageBuilder,
    TaxonomyPackageBuildRequest,
)

_GBIF_API = "https://api.gbif.org/v1"
_CONTINENT_NAMES = {
    "AF": "AFRICA",
    "AS": "ASIA",
    "EU": "EUROPE",
    "NA": "NORTH_AMERICA",
    "SA": "SOUTH_AMERICA",
    "OC": "OCEANIA",
    "AN": "ANTARCTICA",
}


@dataclass(frozen=True, slots=True)
class RegionalAcquisitionResult:
    package_path: Path
    taxonomy_source_public_id: str
    prompt_manifest: Path
    prompt_public_id: str
    embedding_counts: tuple[int, int] | None
    taxa_count: int
    region_record_count: int


class GbifRegionalClient:
    """Small anonymous GBIF client using occurrence facets and species records."""

    def __init__(
        self, *, base_url: str = _GBIF_API, timeout: int = 60, facet_page: int = 1000
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._facet_page = facet_page
        self._local = threading.local()

    def species_keys(
        self, *, country: str | None = None, continent: str | None = None, maximum: int = 20000
    ) -> tuple[int, ...]:
        result: list[int] = []
        offset = 0
        while len(result) < maximum:
            params: dict[str, object] = {
                "limit": 0,
                "facet": "speciesKey",
                "facetLimit": min(self._facet_page, maximum - len(result)),
                "facetOffset": offset,
                "hasCoordinate": "true",
            }
            if country:
                params["country"] = country
            if continent:
                params["continent"] = continent
            payload = self._json("/occurrence/search", params)
            facets = payload.get("facets", []) if isinstance(payload, dict) else []
            counts = facets[0].get("counts", []) if facets and isinstance(facets[0], dict) else []
            page: list[int] = []
            for item in counts:
                try:
                    page.append(int(item["name"]))
                except (KeyError, TypeError, ValueError):
                    continue
            result.extend(page)
            if len(page) < int(params["facetLimit"]):
                break
            offset += len(page)
        return tuple(dict.fromkeys(result[:maximum]))

    def species(self, key: int, *, attempts: int = 5) -> dict[str, object]:
        """Retrieve one taxon with bounded retry for throttling and transient failures."""
        transient = (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
            OSError,
        )
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                value = self._json(f"/species/{key}", {})
                if not isinstance(value, dict):
                    raise ValueError(f"GBIF species {key} returned invalid data")
                return value
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == attempts:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else min(20.0, 0.75 * (2 ** (attempt - 1)))
                )
            except transient as exc:
                last_error = exc
                if attempt == attempts:
                    raise
                delay = min(20.0, 0.75 * (2 ** (attempt - 1)))
            time.sleep(delay + random.uniform(0.0, 0.35))
        raise RuntimeError(f"GBIF species {key} could not be downloaded: {last_error}")

    def _json(self, path: str, params: dict[str, object]) -> object:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{self._base_url}{path}" + (f"?{query}" if query else ""),
            headers={"Accept": "application/json", "User-Agent": f"NatureAI-Next/{__version__}"},
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            return json.load(response)


class RegionalKnowledgeAcquisitionService:
    """Downloads, signs, installs and activates a regional GBIF knowledge package."""

    def __init__(
        self,
        resources: LocalAIResourceService,
        *,
        workspace: Path,
        package_builder: TaxonomyPackageBuilder,
        client: GbifRegionalClient | None = None,
        reference_installer: Callable[[Path, Path], str] | None = None,
    ) -> None:
        self._resources = resources
        self._workspace = workspace
        self._package_builder = package_builder
        self._client = client or GbifRegionalClient()
        self._reference_installer = reference_installer

    def _job_root(self, profile: RegionalProfile) -> Path:
        code = "-".join(
            [
                profile.primary_continent_code or "global",
                *(c.country_code for c in profile.countries),
            ]
        )
        return self._workspace.expanduser().resolve() / "activity" / f"regional-{code.casefold()}"

    @staticmethod
    def profile_payload(profile: RegionalProfile) -> dict[str, object]:
        return {
            "primary_continent_code": profile.primary_continent_code,
            "countries": [asdict(item) for item in profile.countries],
            "include_global_fallback": profile.include_global_fallback,
            "preferred_languages": list(profile.preferred_languages),
        }

    @staticmethod
    def profile_from_payload(payload: dict[str, object]) -> RegionalProfile:
        countries = tuple(
            RegionalCountry(**item)
            for item in payload.get("countries", [])
            if isinstance(item, dict)
        )
        return RegionalProfile(
            payload.get("primary_continent_code")
            if isinstance(payload.get("primary_continent_code"), str)
            else None,
            countries,
            bool(payload.get("include_global_fallback", True)),
            tuple(str(x) for x in payload.get("preferred_languages", ("en", "scientific"))),
        )

    def recovery_operation(
        self, payload: dict[str, object]
    ) -> Callable[..., RegionalAcquisitionResult]:
        profile = self.profile_from_payload(payload)
        return lambda progress, cancelled: self.acquire(
            profile, progress=progress, cancelled=cancelled
        )

    def acquire(
        self,
        profile: RegionalProfile,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> RegionalAcquisitionResult:
        report = progress or (lambda _current, _total, _message: None)
        is_cancelled = cancelled or (lambda: False)

        def check_cancelled() -> None:
            if is_cancelled():
                raise InterruptedError("Cancelled by user")

        job_root = self._job_root(profile)
        job_root.mkdir(parents=True, exist_ok=True)
        state_path = job_root / "state.json"

        def checkpoint(stage: str, **extra: object) -> None:
            value = {"stage": stage, "profile": self.profile_payload(profile), **extra}
            temp = state_path.with_suffix(".tmp")
            temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
            temp.replace(state_path)

        checkpoint("started")
        if not profile.primary_continent_code and not profile.countries:
            raise ValueError(
                "Save a continent or country profile before downloading regional knowledge."
            )
        root = self._workspace.expanduser().resolve()
        signing = root / "signing"
        packages = root / "packages"
        prompts = root / "prompts"
        for folder in (signing, packages, prompts):
            folder.mkdir(parents=True, exist_ok=True)
        key_id = "natureai-local"
        private_path = signing / f"{key_id}-private.pem"
        trusted_path = signing / f"{key_id}-trusted.json"
        private_key = BioCLIPQuickSetupService._ensure_signing_identity(
            key_id, private_path, trusted_path
        )

        scopes: list[tuple[str, str]] = []
        for country in profile.countries:
            scopes.append((country.country_code, country.country_code))
        if profile.primary_continent_code:
            scopes.append(
                (profile.primary_continent_code, _CONTINENT_NAMES[profile.primary_continent_code])
            )
        report(1, 5, "Checking installed regional data and available updates…")
        cache_root = root / "resource-cache" / "gbif"
        region_cache = cache_root / "regions"
        detail_dir = cache_root / "species"
        region_cache.mkdir(parents=True, exist_ok=True)
        detail_dir.mkdir(parents=True, exist_ok=True)
        keys_by_region: dict[str, tuple[int, ...]] = {}
        # A small region-key query is the update check.  Species details are
        # shared across every profile, so adding a country downloads only keys
        # and taxon records not already held locally.
        for region_code, api_value in scopes:
            check_cancelled()
            keys_path = region_cache / f"{region_code.casefold()}.json"
            previous: tuple[int, ...] = ()
            if keys_path.is_file():
                try:
                    previous = tuple(
                        int(x) for x in json.loads(keys_path.read_text(encoding="utf-8"))
                    )
                except (OSError, ValueError, TypeError):
                    previous = ()
            current = self._client.species_keys(
                country=api_value
                if len(region_code) == 2 and region_code not in _CONTINENT_NAMES
                else None,
                continent=api_value if region_code in _CONTINENT_NAMES else None,
            )
            keys_by_region[region_code] = current
            if current != previous:
                temp = keys_path.with_suffix(".tmp")
                temp.write_text(json.dumps(list(current), indent=2), encoding="utf-8")
                temp.replace(keys_path)
        all_keys: dict[int, None] = {}
        for keys in keys_by_region.values():
            all_keys.update((key, None) for key in keys)
        if not all_keys:
            raise RuntimeError("GBIF returned no species for the selected regional profile.")
        checkpoint("region-keys-complete", taxa_total=len(all_keys))

        report(2, 5, f"Downloading taxonomy details for {len(all_keys):,} taxa…")
        taxa: list[dict[str, object]] = []
        names: list[dict[str, object]] = []
        valid_keys: set[int] = set()

        # Each completed response is published as its own atomic cache file.
        # This is the resume boundary: cancellation, process exit, or network
        # failure retains every species already downloaded.  Parallelism is
        # intentionally bounded to avoid overwhelming GBIF or local storage.
        requested_workers = int(os.environ.get("APERTURE_GBIF_WORKERS", "16"))
        worker_count = max(2, min(requested_workers, 32))
        pending_limit = worker_count * 4
        ordered_keys = tuple(all_keys)
        items_by_key: dict[int, dict[str, object]] = {}
        missing_keys: list[int] = []
        corrupt_keys: list[int] = []

        for key in ordered_keys:
            detail_path = detail_dir / f"{key}.json"
            if not detail_path.is_file():
                missing_keys.append(key)
                continue
            try:
                cached = json.loads(detail_path.read_text(encoding="utf-8"))
                if not isinstance(cached, dict):
                    raise ValueError("cached taxon is not an object")
                items_by_key[key] = cached
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                corrupt_keys.append(key)
                detail_path.unlink(missing_ok=True)

        missing_keys.extend(corrupt_keys)
        completed = len(items_by_key)
        total = len(ordered_keys)
        report(
            completed,
            total,
            f"Resuming taxonomy download: {completed:,} cached, {len(missing_keys):,} remaining",
        )
        checkpoint("taxonomy-details", completed=completed, total=total, workers=worker_count)

        def download_one(key: int) -> tuple[int, dict[str, object]]:
            item = self._client.species(key)
            detail_path = detail_dir / f"{key}.json"
            temp = detail_path.with_suffix(f".json.{threading.get_ident()}.tmp")
            try:
                temp.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
                temp.replace(detail_path)
            finally:
                temp.unlink(missing_ok=True)
            return key, item

        if missing_keys:
            iterator = iter(missing_keys)
            inflight: dict[Future[tuple[int, dict[str, object]]], int] = {}
            last_report = time.monotonic()
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="gbif") as pool:
                while len(inflight) < pending_limit:
                    try:
                        key = next(iterator)
                    except StopIteration:
                        break
                    inflight[pool.submit(download_one, key)] = key
                while inflight:
                    check_cancelled()
                    done, _ = wait(inflight, timeout=0.5, return_when=FIRST_COMPLETED)
                    if not done:
                        continue
                    for future in done:
                        key = inflight.pop(future)
                        downloaded_key, item = future.result()
                        items_by_key[downloaded_key] = item
                        completed += 1
                        try:
                            next_key = next(iterator)
                        except StopIteration:
                            pass
                        else:
                            inflight[pool.submit(download_one, next_key)] = next_key
                    now = time.monotonic()
                    if completed == total or completed % 100 == 0 or now - last_report >= 1.0:
                        report(
                            completed,
                            total,
                            f"Downloading taxonomy details: {completed:,} of {total:,} ({worker_count} parallel)",
                        )
                        checkpoint(
                            "taxonomy-details",
                            completed=completed,
                            total=total,
                            workers=worker_count,
                        )
                        last_report = now

        # Build package input deterministically after all cached/downloaded
        # records are available.  Stable ordering keeps package hashes repeatable.
        for key in ordered_keys:
            item = items_by_key[key]
            scientific = str(item.get("scientificName") or item.get("canonicalName") or "").strip()
            rank = str(item.get("rank") or "SPECIES").casefold()
            if not scientific or rank not in {"species", "subspecies", "variety", "form"}:
                continue
            source_id = str(key)
            valid_keys.add(key)
            status_text = str(item.get("taxonomicStatus") or "ACCEPTED").upper()
            status = "accepted" if status_text in {"ACCEPTED", "DOUBTFUL"} else "unresolved"
            taxa.append(
                {
                    "source_taxon_id": source_id,
                    "scientific_name": scientific,
                    "rank": rank,
                    "status": status,
                    "authorship": item.get("authorship"),
                    "kingdom": item.get("kingdom"),
                    "major_group": item.get("phylum") or item.get("class"),
                    "extinct": bool(item.get("extinct", False)),
                }
            )
            names.append(
                {
                    "source_taxon_id": source_id,
                    "name": scientific,
                    "name_type": "scientific",
                    "source": "GBIF Backbone Taxonomy",
                    "language_tag": "scientific",
                    "preferred": True,
                }
            )
            vernacular = str(item.get("vernacularName") or "").strip()
            if vernacular:
                names.append(
                    {
                        "source_taxon_id": source_id,
                        "name": vernacular,
                        "name_type": "vernacular",
                        "source": "GBIF Backbone Taxonomy",
                        "language_tag": "en",
                        "preferred": True,
                    }
                )
        regions: list[dict[str, object]] = []
        for region_code, keys in keys_by_region.items():
            for key in keys:
                if key in valid_keys:
                    regions.append(
                        {
                            "source_taxon_id": str(key),
                            "region_code": region_code,
                            "occurrence_status": "recorded",
                            "source": "GBIF occurrence search",
                        }
                    )

        check_cancelled()
        checkpoint("taxonomy-details-complete", taxa_count=len(taxa), region_count=len(regions))
        report(3, 5, "Building and signing the regional taxonomy package…")
        profile_code = "-".join(
            [
                profile.primary_continent_code or "global",
                *(c.country_code for c in profile.countries),
            ]
        )
        snapshot_hash = hashlib.sha256(
            json.dumps(
                {"taxa": taxa, "regions": regions}, sort_keys=True, ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()[:12]
        package_identity = f"natureai-gbif-{profile_code.casefold()}-{snapshot_hash}"
        package_path = packages / f"{package_identity}.zip"
        self._package_builder.build(
            TaxonomyPackageBuildRequest(
                package_path=package_path,
                private_key=private_key,
                key_id=key_id,
                package_id=package_identity,
                source_name="GBIF regional occurrence and backbone taxonomy",
                source_version=f"api-snapshot-{snapshot_hash}",
                minimum_app_version=__version__,
                license_metadata=LicenseMetadata(
                    "CC BY 4.0",
                    "https://creativecommons.org/licenses/by/4.0/",
                    "GBIF.org occurrence data and GBIF Backbone Taxonomy; accessed by NatureAI Next.",
                    True,
                ),
                taxa=taxa,
                names=names,
                regions=regions,
                attribution_text="GBIF.org occurrence data and GBIF Backbone Taxonomy. Individual occurrence datasets may require additional attribution; see GBIF.org.",
            )
        )
        checkpoint("package-built", package_path=str(package_path))
        check_cancelled()
        report(4, 5, "Installing taxonomy and generating prompts…")
        source_id = self._resources.install_taxonomy(package_path, trusted_path)
        # The same verified regional package also feeds the shared reference
        # taxonomy used by the Knowledge Center.  This keeps BioCLIP behavior
        # unchanged while avoiding a second, empty taxonomy acquisition path.
        if self._reference_installer is not None:
            self._reference_installer(package_path, trusted_path)
        prompt_path = prompts / f"natureai-gbif-{profile_code.casefold()}-prompts.json"
        prompt_rows = [
            {
                "label": f"{t['scientific_name']} [{t['source_taxon_id']}]",
                "text": f"a wildlife photograph of {t['scientific_name']}",
                "taxon_public_id": None,
                "broad_group": t.get("major_group") or "organism",
            }
            for t in taxa
        ]
        prompt_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "identity": f"natureai-gbif-{profile_code.casefold()}-prompts",
                    "semantic_version": "1.0.0",
                    "model_family": "bioclip",
                    "minimum_application_version": __version__,
                    "prompts": prompt_rows,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        prompt_id = self._resources.install_prompt_set(prompt_path, model_family="bioclip")
        checkpoint(
            "resources-installed", taxonomy_source_public_id=source_id, prompt_public_id=prompt_id
        )
        check_cancelled()
        report(5, 5, "Building regional taxonomy embeddings…")
        try:
            embedding_counts = self._resources.build_taxonomy_embeddings()
        except RuntimeError:
            embedding_counts = None
        result = RegionalAcquisitionResult(
            package_path,
            source_id,
            prompt_path,
            prompt_id,
            embedding_counts,
            len(taxa),
            len(regions),
        )
        checkpoint("completed", result=str(result))
        return result
