Aperture 4.0 Development Test Release

Version: 4.0.0.dev1 Build 26 Repair 16

Run Install Aperture.cmd. The installer creates a separate ApertureData-V4 runtime root and a new clean V4 default library. Existing V3 libraries are not opened or migrated by this release.

Field-validation status (2026-07-24):
- Import functions are functioning for the supported media and document types.
- Canonical enrichment is taking place and is functioning.
- Export is currently blocked by a runtime error: 'str' object has no attribute 'value'.
- The video model is not yet functioning correctly. Other tested model functions are functioning.

See FIELD_VALIDATION_STATUS.md for the recorded validation details and current limitations.
