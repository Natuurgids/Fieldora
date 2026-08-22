# Aperture Version 1 Project Handover

## Current state

- **Product:** Aperture
- **Internal engine:** NatureAI_Next
- **Primary identification model:** BioCLIP
- **Release line:** 1.0.0 Foundation Release
- **Runtime state:** Feature frozen except for verified release blockers
- **Current workstream:** Documentation synchronization and final release validation

## Validated Windows workflows

The following workflows were validated through automated tests and hands-on Windows testing:

- clean installation with automatic runtime bootstrap;
- repair, upgrade, CMD uninstall, and Windows Apps uninstall;
- library creation, selection, compatibility normalization, and lock handling;
- normal startup, second-instance handling, clean shutdown, and recovery after interruption;
- AI job pause, resume, cancel, and interrupted-job continuation;
- import, catalog refresh, latest-import view, and bounded thumbnail generation;
- backup creation and verification;
- restore with and without emergency backup;
- visible Maintenance Center handoff, SQLite validation, rollback, and relaunch;
- keyboard, high-DPI, and screen-reader operation.

## Version 1 intentional limitations

The following are deferred rather than omitted accidentally:

- content SHA-256 storage and exact duplicate detection;
- expanded import provenance and source-volume identity;
- complete Taxonomy & Knowledge Center;
- perceptual duplicate detection;
- multi-library synchronization;
- offline maps and field calendar;
- semantic and natural-language search;
- broader dynamic AI-engine orchestration.

See **Help → Roadmap & Future Releases** for the approved direction.

## Engineering lessons retained

- Test installation, launch, database replacement, and file locking on real Windows systems.
- Keep ordinary launchers free of PowerShell and visible console dependencies.
- Use explicit readiness acknowledgement before closing the main application for maintenance operations.
- Close SQLite cursors and connections explicitly before atomic file replacement on Windows.
- Preserve rollback copies and validate database integrity before activation.
- Use append-only JSONL diagnostics for startup, import synchronization, maintenance launch, and restore history.
- Prefer minimal, evidence-driven fixes late in a release cycle.
- Do not introduce database migrations during release-candidate stabilization unless data safety requires them.

## Next-chat starting scope

The next development conversation should begin with this boundary:

> Aperture Version 1 runtime is frozen except for critical release blockers. Complete documentation synchronization, final release validation, and Version 1 packaging first. Then begin the approved Version 2 roadmap with taxonomy, provenance, content hashing, exact duplicate detection, migration tooling, and modular AI orchestration.
