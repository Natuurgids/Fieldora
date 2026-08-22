# Build 31 Change Summary

## Added

- Federated operational health contract and source health snapshots.
- Recovery, verification and previewable cleanup protocol.
- Expanded Activity Registry with safe unregister, health federation and missing-source handling.
- Observable bounded Resource Broker supporting CPU, GPU, I/O, high-I/O, database writer, network and memory-heavy classes.
- Resource acquisition timeout and idle-drain support.
- Operational diagnostics service for Activity Centre and Maintenance Centre field diagnostics.
- Linux uninstaller preserving all user libraries and media.
- Build 31 regression tests.

## Preserved

- Independent subsystem executors, databases and tables.
- Cache-only gallery thumbnail consumption.
- Durable derivative jobs.
- Verified per-item transfer primitives.
- Existing import, export, AI, maps, taxonomy, media, viewer and maintenance behavior.

## Architectural intent

Build 31 implements one shared operational control plane without creating one queue, one executor, one database or one hardware dependency. This preserves Qt responsiveness, subsystem isolation and future distributed execution.
