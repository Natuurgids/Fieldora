"""Open-source Planetiler based OSM PBF -> vector MBTiles conversion.

The converter uses a cached Eclipse Temurin Java 21 runtime and Planetiler jar.
Both dependencies are architecture-aware and downloaded from their official
open-source projects on first use when they are not bundled with Aperture.
Once cached, conversion is fully offline.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request
import zipfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from natureai_next.application.geofabrik_maps import ConversionResult
from natureai_next.infrastructure.subsystems.maps import VectorMbtilesMapProvider


class PlanetilerVectorConverter:
    PLANETILER_VERSION = "0.10.2"
    PLANETILER_URL = (
        "https://github.com/onthegomap/planetiler/releases/download/v0.10.2/planetiler.jar"
    )
    ADOPTIUM_API = (
        "https://api.adoptium.net/v3/binary/latest/21/ga/windows/"
        "{arch}/jre/hotspot/normal/eclipse?project=jdk"
    )

    def __init__(self, resource_root: Path) -> None:
        self.resource_root = resource_root

    def convert(
        self,
        source: Path,
        destination: Path,
        entry: object,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> ConversionResult:
        report = progress or (lambda _c, _t, _m: None)
        is_cancelled = cancelled or (lambda: False)
        if not source.is_file() or source.stat().st_size < 1024:
            raise ValueError(f"Downloaded OpenStreetMap source is missing or empty: {source}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        tool_root = destination.parent / ".map-tools" / "planetiler"
        work_root = destination.parent / ".map-build" / destination.stem
        work_root.mkdir(parents=True, exist_ok=True)
        staged = destination.with_name(destination.stem + ".converting.partial.mbtiles")
        log_path = destination.with_name(destination.stem + ".converting.log")
        staged.unlink(missing_ok=True)

        report(0, 100, "Preparing open-source Planetiler map builder…")
        memory_mb = self._memory_limit_mb(source)
        (tool_root / "sources").mkdir(parents=True, exist_ok=True)
        command: list[str] | None = None
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = os.environ.copy()
        env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true"
        succeeded = False
        try:
            # One cross-process lock covers both toolchain installation and all
            # Planetiler shared downloads.  Multiple regional activities may be
            # queued independently, but they can no longer race on the JAR or on
            # Planetiler's fixed *_inprogress source filenames on Windows.
            with self._shared_source_lock(tool_root, report, is_cancelled):
                java, jar = self._ensure_toolchain(tool_root, report)
                if is_cancelled():
                    raise InterruptedError("Map build cancelled")
                command = [
                    str(java),
                    f"-Xmx{memory_mb}m",
                    "-Dfile.encoding=UTF-8",
                    "-jar",
                    str(jar),
                    f"--osm-path={source}",
                    f"--output={staged}",
                    f"--tmpdir={work_root / 'tmp'}",
                    "--download",
                    f"--natural-earth-path={tool_root / 'sources' / 'natural-earth.gpkg.zip'}",
                    f"--water-polygons-path={tool_root / 'sources' / 'water-polygons-split-3857.zip'}",
                    f"--tile-weights={tool_root / 'sources' / 'tile-weights.tsv.gz'}",
                    "--force",
                    "--render-maxzoom=14",
                    "--maxzoom=15",
                    "--building-merge-z13=false",
                    "--loginterval=2s",
                ]
                self._remove_stale_planetiler_downloads(tool_root / "sources")
                with log_path.open("w", encoding="utf-8", errors="replace") as output:
                    process = subprocess.Popen(
                        command,
                        cwd=work_root,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        text=True,
                        shell=False,
                        creationflags=flags,
                        env=env,
                    )
                    started = time.monotonic()
                    last_message = "Building independent offline map database…"
                    while process.poll() is None:
                        if is_cancelled():
                            self._stop(process)
                            raise InterruptedError("Map build cancelled")
                        tail = self._tail(log_path, 700)
                        if tail:
                            last_message = tail.splitlines()[-1][-240:]
                        elapsed = int(time.monotonic() - started)
                        # Planetiler does not expose one stable machine-readable total;
                        # keep progress truthful and bounded until archive validation.
                        current = min(94, 10 + elapsed // 6)
                        report(current, 100, f"Map database builder: {last_message}")
                        time.sleep(1.0)
            if process.returncode != 0:
                raise RuntimeError(
                    f"Planetiler map build failed with exit code {process.returncode}: "
                    f"{self._tail(log_path)}\n"
                    f"Downloaded OSM source retained at: {source}\n"
                    f"Full builder log retained at: {log_path}"
                )
            valid, message, details = VectorMbtilesMapProvider().validate_package(staged)
            if not valid:
                raise ValueError(f"Planetiler MBTiles validation failed: {message}")
            max_zoom = int(details.get("max_zoom", -1))
            if max_zoom < 14:
                raise ValueError("Planetiler output does not reach vector base zoom 14")
            os.replace(staged, destination)
            digest = self._sha256(destination)
            report(100, 100, "Offline MBTiles map built and validated")
            succeeded = True
            return ConversionResult(
                destination,
                digest,
                destination.stat().st_size,
                int(details.get("min_zoom", 0)),
                max_zoom,
            )
        finally:
            if succeeded:
                log_path.unlink(missing_ok=True)
                shutil.rmtree(work_root, ignore_errors=True)

    @staticmethod
    def _remove_stale_planetiler_downloads(source_root: Path) -> None:
        """Remove abandoned Planetiler temporary downloads while holding the global lock."""
        source_root.mkdir(parents=True, exist_ok=True)
        for candidate in source_root.glob("*_inprogress"):
            candidate.unlink(missing_ok=True)

    @staticmethod
    @contextmanager
    def _shared_source_lock(
        tool_root: Path,
        report: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
    ):
        """Serialize builds because Planetiler shares fixed ``*_inprogress`` filenames."""
        lock_path = tool_root / "sources.lock"
        deadline = time.monotonic() + 60 * 60
        handle: int | None = None
        while handle is None:
            if cancelled():
                raise InterruptedError("Map build cancelled while waiting for shared map sources")
            try:
                handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(handle, f"pid={os.getpid()} started={time.time()}".encode("ascii"))
            except FileExistsError:
                try:
                    age = time.time() - lock_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > 2 * 60 * 60:
                    lock_path.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Timed out waiting for another offline map build to release shared sources"
                    )
                report(
                    7,
                    100,
                    "Waiting for another offline map build to finish shared source preparation…",
                )
                time.sleep(1.0)
        try:
            yield
        finally:
            if handle is not None:
                os.close(handle)
            lock_path.unlink(missing_ok=True)

    def _ensure_toolchain(
        self, root: Path, report: Callable[[int, int, str], None]
    ) -> tuple[Path, Path]:
        root.mkdir(parents=True, exist_ok=True)
        bundled = self.resource_root / "map_builder"
        jar = root / f"planetiler-{self.PLANETILER_VERSION}.jar"
        bundled_jar = bundled / "planetiler.jar"
        if not jar.exists() and bundled_jar.is_file():
            shutil.copy2(bundled_jar, jar)
        if not jar.is_file() or jar.stat().st_size < 1_000_000:
            report(2, 100, "Downloading open-source Planetiler…")
            self._download(self.PLANETILER_URL, jar)
        java = self._find_bundled_java(bundled) or self._find_java(root)
        if java is None:
            report(4, 100, "Downloading open-source Eclipse Temurin Java runtime…")
            java = self._download_jre(root)
        self._verify_java(java)
        self._write_manifest(root, java, jar)
        return java, jar

    @staticmethod
    def _find_bundled_java(root: Path) -> Path | None:
        candidate = root / "jre" / "bin" / "java.exe"
        return candidate if candidate.is_file() else None

    @staticmethod
    def _find_java(root: Path) -> Path | None:
        candidate = root / "jre" / "bin" / "java.exe"
        if candidate.is_file():
            return candidate
        system = shutil.which("java")
        return Path(system) if system else None

    def _download_jre(self, root: Path) -> Path:
        machine = platform.machine().lower()
        arch = "aarch64" if machine in {"arm64", "aarch64"} else "x64"
        archive = root / "temurin-jre.zip.partial"
        self._download(self.ADOPTIUM_API.format(arch=arch), archive)
        target = root / "jre"
        unpack = root / "jre.unpacking"
        shutil.rmtree(unpack, ignore_errors=True)
        unpack.mkdir(parents=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(unpack)
        dirs = [p for p in unpack.iterdir() if p.is_dir()]
        source = dirs[0] if len(dirs) == 1 else unpack
        shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(source), str(target))
        shutil.rmtree(unpack, ignore_errors=True)
        archive.unlink(missing_ok=True)
        java = target / "bin" / "java.exe"
        if not java.is_file():
            raise RuntimeError("Eclipse Temurin archive did not contain bin\\java.exe")
        return java

    @staticmethod
    def _download(url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".download")
        request = urllib.request.Request(
            url, headers={"User-Agent": "Aperture/3.320 offline-map-builder"}
        )
        with (
            urllib.request.urlopen(request, timeout=180) as response,
            temporary.open("wb") as output,
        ):
            shutil.copyfileobj(response, output, length=1024 * 1024)
        os.replace(temporary, destination)

    @staticmethod
    def _verify_java(java: Path) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [str(java), "-version"],
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
            creationflags=flags,
        )
        version_text = (result.stdout + result.stderr).strip()
        if result.returncode != 0 or not any(
            f'"{major}.' in version_text for major in range(21, 40)
        ):
            raise RuntimeError(
                f"Planetiler requires Java 21 or newer; detected: {version_text or 'unknown'}"
            )

    def _write_manifest(self, root: Path, java: Path, jar: Path) -> None:
        payload = {
            "builder": "Planetiler",
            "builder_version": self.PLANETILER_VERSION,
            "builder_license": "Apache-2.0",
            "builder_url": self.PLANETILER_URL,
            "java_distribution": "Eclipse Temurin",
            "java_license": "GPL-2.0-with-classpath-exception",
            "java_path": str(java),
            "planetiler_sha256": self._sha256(jar),
            "offline_after_cache": True,
        }
        (root / "toolchain.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _memory_limit_mb(source: Path) -> int:
        requested = os.environ.get("APERTURE_PLANETILER_MEMORY_MB", "").strip()
        if requested.isdigit():
            return max(1024, min(32768, int(requested)))
        # Conservative automatic value: at least 2GB, up to 8GB, scaled to input.
        return max(2048, min(8192, int(source.stat().st_size / (2 * 1024 * 1024))))

    @staticmethod
    def _stop(process: subprocess.Popen[str]) -> None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    @staticmethod
    def _tail(path: Path, limit: int = 2400) -> str:
        if not path.exists():
            return "No Planetiler output was produced."
        data = path.read_bytes()[-limit * 4 :]
        return data.decode("utf-8", errors="replace").strip()[-limit:]

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
