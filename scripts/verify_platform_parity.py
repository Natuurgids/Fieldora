#!/usr/bin/env python3
"""Validate the authoritative platform feature registry for release gating."""
from __future__ import annotations
import json
from natureai_next.application.platform_features import parity_payload, registry_payload, validate_registry

def main() -> int:
    validate_registry()
    result = {"registry": registry_payload(), "parity": parity_payload()}
    print(json.dumps(result, indent=2, sort_keys=True))
    # All supported platforms must be functionally complete before certification.
    for platform in ("windows_desktop", "linux_desktop", "server"):
        summary = result["parity"]["platforms"][platform]
        if summary["missing"] or summary["partial"]:
            raise SystemExit(f"desktop parity failed for {platform}: {summary}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
