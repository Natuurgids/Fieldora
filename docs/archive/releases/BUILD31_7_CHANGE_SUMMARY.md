# Build 31.7 Change Summary

Build 31.7 repairs Version 2 platform certification. `LibraryHealthService` now consumes `SubsystemDatabaseRegistry.keys()` instead of treating the registry as an iterable. This preserves the registry abstraction and allows read-only certification to inspect optional subsystem databases without raising `TypeError`.

A regression test executes the health subsystem check with the real registry type.
