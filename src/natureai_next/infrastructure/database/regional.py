"""SQLite persistence and evidence resolution for regional profiles."""

from __future__ import annotations

import json

from natureai_next.domain.regional import RegionalCountry, RegionalEvidence, RegionalProfile


class SqliteRegionalProfileStore:
    def __init__(self, factory: object) -> None:
        self._factory = factory

    def load(self) -> RegionalProfile:
        c = self._factory.connect(read_only=True)
        try:
            row = c.execute(
                "SELECT primary_continent_code,include_global_fallback,preferred_languages_json FROM regional_profiles WHERE id=1"
            ).fetchone()
            countries = tuple(
                RegionalCountry(
                    str(r[0]), str(r[1]), str(r[2]), int(r[3]), None if r[4] is None else str(r[4])
                )
                for r in c.execute(
                    "SELECT country_code,continent_code,country_name,priority,verified_by FROM regional_profile_countries ORDER BY priority,country_name"
                )
            )
            if row is None:
                return RegionalProfile(None, countries)
            try:
                languages = tuple(str(v) for v in json.loads(str(row[2])))
            except Exception:
                languages = ("en", "scientific")
            return RegionalProfile(
                None if row[0] is None else str(row[0]), countries, bool(row[1]), languages
            )
        finally:
            c.close()

    def save(self, profile: RegionalProfile, *, now_us: int) -> RegionalProfile:
        c = self._factory.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT INTO regional_profiles(id,primary_continent_code,include_global_fallback,preferred_languages_json,modified_at_us) VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET primary_continent_code=excluded.primary_continent_code,include_global_fallback=excluded.include_global_fallback,preferred_languages_json=excluded.preferred_languages_json,modified_at_us=excluded.modified_at_us",
                (
                    profile.primary_continent_code,
                    1 if profile.include_global_fallback else 0,
                    json.dumps(profile.preferred_languages),
                    now_us,
                ),
            )
            c.execute("DELETE FROM regional_profile_countries")
            c.executemany(
                "INSERT INTO regional_profile_countries(country_code,continent_code,country_name,priority,verified_by,modified_at_us) VALUES(?,?,?,?,?,?)",
                [
                    (
                        x.country_code,
                        x.continent_code,
                        x.country_name,
                        x.priority,
                        x.verified_by,
                        now_us,
                    )
                    for x in profile.countries
                ],
            )
            c.execute("COMMIT")
            return profile
        except Exception:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        finally:
            c.close()

    def evidence_for_taxon(self, taxon_public_id: str | None) -> RegionalEvidence:
        profile = self.load()
        if not taxon_public_id:
            return RegionalEvidence("unknown", "No taxonomy candidate", None, None, None)
        c = self._factory.connect(read_only=True)
        try:
            rows = c.execute(
                "SELECT tr.region_code,tr.occurrence_status,tr.source FROM taxon_regions tr JOIN taxa t ON t.id=tr.taxon_id WHERE t.public_id=? ORDER BY tr.source",
                (taxon_public_id,),
            ).fetchall()
        finally:
            c.close()
        by_code = {
            str(r[0]).upper(): (None if r[1] is None else str(r[1]), str(r[2])) for r in rows
        }
        for country in profile.countries:
            hit = by_code.get(country.country_code.upper())
            if hit:
                return RegionalEvidence(
                    "selected_country",
                    f"Verified in {country.country_name}",
                    country.country_code,
                    hit[0],
                    hit[1],
                )
        continent = (profile.primary_continent_code or "").upper()
        if continent:
            hit = by_code.get(continent)
            if hit:
                return RegionalEvidence(
                    "selected_continent", f"Verified in {continent}", continent, hit[0], hit[1]
                )
        if rows and profile.include_global_fallback:
            return RegionalEvidence(
                "global_fallback",
                "Rest of world",
                str(rows[0][0]),
                None if rows[0][1] is None else str(rows[0][1]),
                str(rows[0][2]),
            )
        return RegionalEvidence("not_verified", "Not verified in selected region", None, None, None)
