# Export, Reporting, Backup, and Restore Architecture

**Status:** Approved Release 3 design; export implementation currently has a field-validated blocking defect

## Current implementation status — 2026-07-24

The architecture below remains the intended design. In Build 26 Repair 16, the tested export operation is not operational: it failed at progress 2 of 4 with `'str' object has no attribute 'value'`. Existing installed data remained available. Export must remain marked unavailable until the string/enum handling defect is corrected and a complete export run passes field validation. Import and canonical enrichment are functioning and are not affected by this export-status statement.

## Separation of responsibilities

Aperture provides three user-facing output workflows and one recovery workflow:

- **Export Assets** transfers selected Aperture records and optionally original photos, sounds, videos, and documents.
- **Export Data** exports only selected fields and rows that are permitted by the active export profile.
- **Generate Report** communicates selected or aggregated information, from a single observation count through full record tables, and may optionally create a report package containing selected originals.
- **Backup and Restore** protects Aperture-owned databases and configuration required to reconstruct a library. It is not a sharing/export mechanism.

## Placement

Reporting is a top-level workspace with Reports, Templates, History, and Export Profiles. Contextual **Generate Report** actions are also available from Observations, Photos, Sounds, Videos, Documents, and every collection view. All contextual actions open the same reporting workflow with the current selection or filter prefilled.

## Original media

When original media is requested, the export package builder resolves and verifies the original file for each selected asset. It records file availability, expected size, checksum, storage volume identity, last known path, and exported package path. Missing or offline originals do not erase the asset record.

Users choose one policy:

- require every requested original;
- include available originals and report unavailable files (default);
- previews and metadata only;
- metadata only.

Reports distinguish presentation from file inclusion. A photo thumbnail, sound waveform, video poster frame, or document extract may appear without automatically copying the original. Original photos, sounds, videos, and documents are included only when explicitly selected.

## Report aggregation and permissions

Report definitions store source selection, filters, sections, aggregation levels, allowed fields, privacy profile, layout, and output format. Observation output may be total count only, grouped totals, a summary table, or individual registrations. Aggregation occurs during report generation and never replaces source observations.

Export profiles classify fields as Public, Internal, Sensitive, Restricted, or Never export. Exact GPS, private notes, identities, storage paths, unpublished observations, rejected AI suggestions, and internal processing state can therefore be withheld or generalized.

## Package builder

Asset export and report packages share these Aperture-owned services:

- ExportSelectionResolver
- ExportPermissionService
- OriginalAvailabilityService
- ExportPackageBuilder
- ExportManifestWriter
- ExportVerificationService

Reporting additionally uses ReportQueryEngine and ReportRenderer. Package manifests use stable Aperture IDs and package-relative paths, record omitted/unavailable originals, and distinguish originals from developed or derived files.

## Backup inventory and scope

Backup uses a central database inventory service and includes every Aperture-owned database needed for the chosen scope, not only `library.sqlite3`. This includes active core, media, enrichment, reporting, taxonomy, maps, and other Aperture subsystem databases when required by the backup scope.

Backup scope options are:

- **Complete library** (default and recommended);
- **Active library types only**;
- **Custom**.

Active-type backup is explicit and warns that disabled retained data is excluded. Shared records such as collections, observations, notes, locations, and relationships are included when linked by selected media. Cross-scope relationships may be omitted unless both endpoints are included or preserved as external placeholders.

## Integrations

Integration runtimes are excluded from normal backup and export: model files, downloaded weights, inference caches, temporary queues, plugin databases, and installation state are not copied. Accepted, validated, normalized enrichment is Aperture-owned data and is included with its producer identity, confidence, timestamps, and schema version. BioCLIP itself is not backed up; accepted BioCLIP results are.

## Consistent snapshots and restore

The backup coordinator briefly quiesces Aperture writer queues, uses SQLite online backup for each included database, records transaction/schema markers, resumes writers, hashes every snapshot, and builds a verified archive. It must not rely on raw filesystem copies of open SQLite databases.

Restore first validates the manifest and displays included capabilities and databases. Initial Release 3 restore modes are **Restore as a new library** and **Replace current library**. Merge restore remains deferred until identifier collision, duplicate detection, collection merge, and relationship conflict rules are proven.

## Implemented export-package foundation

The portable package builder accepts report/data attachments and optional original media records for photo, sound, video, and document assets. It copies into a staging directory, verifies size/checksum where recorded, writes `manifest.json`, and atomically publishes the package. Missing originals can be reported without failing the rest; strict mode fails atomically.
