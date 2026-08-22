"""Generate a deterministic dependency declaration SBOM from pyproject metadata."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _component(requirement: str, scope: str) -> dict[str, str]:
    name = re.split(r"[<>=!~;\\[]", requirement, maxsplit=1)[0].strip()
    return {
        "type": "library",
        "name": name,
        "requirement": requirement,
        "scope": scope,
    }


def generate() -> dict[str, object]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    components = [
        _component(requirement, "required")
        for requirement in project.get("dependencies", [])
    ]
    for group, requirements in sorted(
        project.get("optional-dependencies", {}).items()
    ):
        components.extend(_component(requirement, f"optional:{group}") for requirement in requirements)
    components.sort(key=lambda item: (item["name"].casefold(), item["scope"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "Fieldora",
                "version": project["version"],
            }
        },
        "components": components,
    }


def main() -> int:
    (ROOT / "FIELDORA_SBOM.json").write_text(
        json.dumps(generate(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
