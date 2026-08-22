# Build 31.2 Change Summary

Build 31.2 repairs two Windows field failures discovered in Build 31.1.

## Portable export

Qt may return `QComboBox.currentData()` as a plain string even when a `StrEnum` was stored. The export workspace now normalizes the value immediately. The export plan and manifest writer also normalize persisted string values, so newly queued, retried, and resumed package exports share the same behavior.

## Storage verification

Storage verification no longer runs synchronously from the Storage Manager. Verify selected and Verify all create `storage.verify` activities, return control to Qt immediately, publish location-level progress, support cancellation, commit updates in bounded batches, and refresh the table after completion.

## Validation

The complete available automated suite passes. The PySide6-only scheduling test remains environment-skipped in the packaging container.
