# Repair 7 startup failure review

The Repair 6 trace exposed two independent failure-unwinding defects.

1. Runtime identity drift was treated as fatal even for a clean, empty library. The runtime guard now rebuilds an empty database from the authoritative `library.json` identity, while still refusing destructive repair when user data exists.
2. `SqliteOpenLibrary.close()` used the guarded repository factory after marking the library closed. The guard therefore raised `library is closed`, masking the original exception and risking failure to release the library lock. Shutdown now uses the unguarded maintenance factory, treats WAL checkpointing as best-effort, and always releases the lock.

The same empty-identity recovery is also applied during initial open. Regression tests cover stale database identity, schema recovery, guard bypass during shutdown, and successful immediate reopen after a failed/normal close.
