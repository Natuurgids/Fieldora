# Build 31.3 Change Summary

Build 31.3 is a field-repair release for the operational integration issues reported in Build 31.2.

## Thumbnail path resolution

Catalog derivative paths are now resolved relative to the active Aperture Library before they are returned to the gallery, collections, inspector, or viewer. Managed and linked assets therefore consume the same Aperture-owned thumbnail files regardless of the process working directory.

## Import activity

Folder imports retain their independent import application service and database transactions, but execution is now registered with the Activity Centre. Scanning, hashing, import execution, completion, cancellation, and failure are visible without blocking the Qt event loop.

## Backup activity

Library backup creation and verification now run as a serialized Activity Centre operation. The main window returns immediately, progress remains visible, and the verified backup result is retained in the activity details instead of blocking the interface while a modal completion dialog is prepared.

## Restore handoff

Restore Library launches the external Maintenance Center with an explicit restore intent. The window scrolls directly to a clearly labelled Backup and restore section, exposes Restore Selected, selects the first verified backup when available, and explains the safe restore behavior.

## Operational limits

Import, backup, and storage-verification activities are serialized per activity kind. They remain independent of AI, export, map, and derivative workers while avoiding overlapping writes within the same library operation family.
