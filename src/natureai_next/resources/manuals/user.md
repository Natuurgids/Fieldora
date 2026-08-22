| **Release**  | 0.11.21 — AI review and offline map labels                     |
|--------------|---------------------------------------------------------------------------------|
| **Audience** | Researchers, collection managers, field teams, reviewers, and data contributors |
| **Platform** | Windows 11 desktop; optional multi-server deployment                            |
| **Status**   | Operational reference — July 2026                                               |

**This manual reflects the packaged Fieldora 5.4.0 source release.
Commands that change data should first be exercised against a test
library or non-production environment.**

## Trash and organizational deletion

Use **Platform Management > Library Administration > Trash & Deletion
Approvals**. Local Trash can restore items or submit permanent organizational
deletion. Choose a named person or organization function and provide a reason.
If nobody eligible is available, Fieldora routes the request to the tool
administrator. Approved removal runs in the background; rejected requests
remain audited.

## Background thumbnails

Photos displays placeholders immediately. Original decoding and thumbnail cache
writes run in the durable background job engine, never in the GUI worker. The
bottom bar shows checking, queued or awaiting-generation counts. You may leave
Photos and continue elsewhere; generation continues and completed thumbnails
appear when you return. Fieldora's active-screen response target remains three
seconds even when thumbnail generation takes several minutes.

## Home and connected calendars

Fieldora opens on **Home**, showing Library volume, incomplete work, planned
activities, Marine Science records and the next 30 days. Both Research Calendar
and the project calendar highlight scheduled dates and show an activity-count
badge.

Research Calendar can export `.ics` and open a selected activity in the Google
Calendar or Outlook event composer. These actions are user initiated. Fieldora
does not send calendar data continuously or retain provider credentials for this
integration.

## Marine science and maritime operations

Use **Research > Scientific Records > Marine & Freshwater Science** for sampling
stations, surveys, samples, measurements, species/eDNA evidence, habitats and
acoustic or sonar records. Use **Research > Maritime Operations**
for vessels, voyages, ports, routes, crew, equipment, dives and operation logs.

The maritime workspace also contains a dedicated **Submarine Logs** screen.
Depth is entered in metres and is retained in records and JSON exports.
The **Dives** screen records the buddy or dive partner as a dedicated field.

Each record can link selected Library media without duplicating it. Use **Export
domain JSON** for a portable record package. Attached media remains governed by
its existing access contract. Administrators can enable or disable both modules
independently without deleting retained records.

# How to use this manual

Follow procedures in order. Text marked Important identifies a safety or
security boundary. Command blocks are intended to be copied only after
paths, environment names, and organization identifiers are replaced.

# Contents

- 1\. Getting started

- 2\. Application layout and navigation

- 3\. Libraries

- 4\. Importing photographs and files

- 5\. Browsing photographs

- 6\. Search and filtering

- 7\. Metadata and organization

- 8\. Observations

- 9\. AI Review and taxonomy

- 10\. Science projects and dossiers

- 11\. Embedded Excalidraw whiteboards

- 12\. Maps and field context

- 13\. Export, reporting, and Fieldora integration

- 14\. Synchronization and contracts

- 15\. Jobs and Activity Center

- 16\. Settings, diagnostics, and updates

- 17\. Backup and recovery

- 18\. Troubleshooting and safe use

- 19\. Glossary

# 1. Getting started

1.  Start Fieldora from the installed shortcut or with natureai-next
    --library PATH.

2.  Select an existing verified Fieldora library or ask an administrator
    to create one.

3.  Confirm the title bar names the current library.

4.  Open Library and browse a small set of photographs.

5.  Open About Fieldora and confirm release 0.11.21.

6.  Open Excalidraw Whiteboards and verify Drawing 1 appears inside
    Fieldora.

**Important:** A library contains databases, metadata, thumbnails,
backups, and possibly managed originals. Do not rename, move, or edit
its internal files while Fieldora is open.

# 2. Application layout and navigation

- Menus and command bar: import, export, backup, restore, Activity
  Center, settings, help, and About.

- Navigation tree: Library Management, Observations, Knowledge, Core
  resources, AI Models, Knowledge Sources, Science, Extensions, and
  Settings.

- Workspace: the active photo, observation, science, map, export, or
  configuration screen.

- Inspector and lower panels: details and context for the current
  selection where available.

- Activity Center: progress, completion, warnings, and failures for
  longer operations.

## Useful navigation habits

- Wait for long work to appear in Activity Center instead of repeatedly
  clicking the command.

- Use the navigation tree to move between workspaces without closing the
  library.

- Read inline banners and error codes; failures are not silently
  ignored.

- Keep Fieldora open during an active non-resumable operation unless the
  screen explicitly says it can resume.

# 3. Libraries

A Fieldora library is the working boundary for media, observations,
derived information, documents, and settings. A library should be opened
by one standalone workstation at a time unless it is explicitly deployed
through server services.

- Use a local SSD for responsive standalone operation.

- Keep separate libraries for production, testing, and legacy
  applications.

- Use library-check after an unexpected shutdown or before/after a major
  upgrade.

- Back up through supported commands; do not rely on copying open SQLite
  files.

- Keep sufficient space for thumbnails, AI models, imports, exports, and
  backups.

# 4. Importing photographs and files

7.  Open Import from the toolbar or Library Management.

8.  Choose source folders or files.

9.  Review storage policy: copy, move, or reference, where offered.

10. Review discovered formats, duplicates, sidecars, and conflicts.

11. Confirm the plan and start the import.

12. Follow progress in Activity Center.

13. Inspect successes, skips, and failures before removing source media.

**Important:** Use copy for the safest first import. Do not erase memory
cards or source disks until imported files, metadata, and backups have
been verified.

# 5. Browsing photographs

The photo screen is optimized for large result sets. While you drag the
scroll bar or use the mouse wheel, Fieldora postpones thumbnail
requests. After scrolling has been idle for more than 300 ms, it loads
the visible region and a bounded predicted window of approximately 50
plus 400 thumbnails.

- Fast scrolling should show lightweight placeholders instead of
  stalling on decoding.

- Stop scrolling briefly to allow the visible region to populate.

- Selection and context should remain stable during background refresh.

- Open a photograph for fit, 100%, zoom, pan, metadata overlay, and
  next/previous navigation.

- Use multi-selection carefully; batch edits show the number of affected
  assets.

# 6. Search and filtering

The search bar searches indexed metadata and includes filename and
directory-path terms. Use meaningful filename fragments, folder names,
tags, taxa, places, or saved queries. Search results remain subject to
access rules in server deployments.

- Filename search: type a distinctive part of the file name, with or
  without the extension.

- Directory search: type a parent folder name or meaningful path
  component.

- Metadata search: use title, caption, notes, tag, taxon, or place
  terms.

- Clear filters when expected items are missing.

- Rebuild or refresh the search projection only through administrative
  tools when indexing is stale.

- Search results never grant access to records you are not permitted to
  view.

# 7. Metadata and organization

- Ratings, pick state, and color labels support triage.

- Titles, captions, notes, and tags describe assets.

- Capture information, file details, location, taxonomy, and AI
  provenance appear in inspector sections.

- Multi-selection shows common and mixed values; confirm batch changes.

- Edits create application-level history where supported.

- Imports, purges, model installation, and exports are not assumed
  undoable.

# 8. Observations

Observations connect evidence, taxonomy, location, time, and research
context. Use the observation workspaces to record field evidence and
review related media.

- Confirm date, location, observer, and project context.

- Link the correct photographs, sounds, videos, or documents.

- Prefer accepted taxonomy names while retaining provenance for
  suggestions.

- Record uncertainty and notes instead of forcing a confident
  identification.

- Use regional knowledge, habitats, and seasonality as context, not as
  automatic proof.

# 9. AI Review and taxonomy

14. Open AI Resources and confirm the selected model and classifier are
    ready.

15. Select one or more photographs.

16. Open AI Review.

17. Inspect ranked candidates, score type, model identity, and
    crop/image context.

18. Accept, reject, defer, or choose another taxon. Choose **Defer to user…**
    to place the item in a named identity's queue; use **Return to shared
    queue** to remove the assignment.

19. Use Current photograph only when changing one image.

20. Use Accept & Reject Rest only after checking that the selected
    answer is correct.

21. Review accepted results and provenance.

**Important:** AI suggestions are proposals. They do not replace expert
review, field evidence, or source attribution.

## Parallel analysis in every media library

Photos, Sounds, Videos, and Documents each provide their own batch-analysis
screen.

1. Open the applicable library and select one or more files.
2. Choose **Run Enrichment…**, select the primary capability, and optionally
   check additional compatible enrichments. Additional capabilities use their
   catalogued defaults and receive independent progress screens.
3. Confirm the parameters. Fieldora opens that library's independent analysis
   screen and runs up to two heavyweight model workers in parallel.
4. Follow the state of every file: Queued, Running, Succeeded, Failed, or
   Cancelled.
5. Use **Cancel remaining** to stop work that has not completed. Completed
   canonical results remain available for review.

Failures are isolated per file. A failed item does not discard successful
results from the same batch. Turning a media library off under **Settings →
Turn Workspaces On or Off** hides its analysis screen and cancels remaining
work. Re-enabling the library restores its analysis actions; persisted results
are never deleted by the switch.

## Documents, PDFs, and OCR

- PDFs open in continuous multi-page mode. Scroll normally or select a page
  from the page rail.
- Install **Fieldora Offline Document OCR** under **Tools & Resources →
  Models**, accept its licence terms, then activate it.
- Select one or more documents and choose **OCR** or **Run Enrichment…**.
  Searchable PDF text is preserved directly; scanned pages are rendered and
  recognized locally with RapidOCR.
- OCR creates page-specific transcript and region evidence for review. It does
  not modify the original PDF.

# 10. Science projects and dossiers

- Projects organize research aims, status, leads, dates, and linked
  evidence.

- Dossiers collect structured records and project context.

- Animals, Plants & Flowers, and Other Artifacts organize scientific
  objects.

- Activity Calendar coordinates field and analysis work.

- Science data remains in Fieldora's separate Science repository.

- In **Research Area & Media**, click points around a study area and save the
  polygon, or import an existing Polygon GeoJSON boundary. Saved areas remain
  attached to the project and are shown on its project map.

- Select media in Photos, Sounds, Videos, or Documents, then use **Attach
  selected Library media** in the project. Add project notes from the same tab.

- **Research Package** exports a selective ZIP containing structured project
  records, GeoJSON and an offline map document, a media index, notes, and
  optional original media and task attachments. Playable audio and video can
  be enabled in the offline HTML index.

- Document versioning is used for Excalidraw snapshots.

# 11. Embedded Excalidraw whiteboards

Fieldora bundles the complete offline Excalidraw 0.18.1 application. No
separate Excalidraw installation is required. Whiteboards are standard
.excalidraw documents stored beneath Documents/Whiteboards.

22. Open Science \> Excalidraw Whiteboards.

23. If the workspace is empty, Fieldora creates Drawing 1 and opens it
    automatically.

24. Use the embedded toolbar for selection, shapes, arrows, drawing,
    text, images, erasing, zoom, and canvas movement.

25. Fieldora autosaves the current document atomically.

26. Use Create document version before a major change to preserve a
    snapshot.

27. Use Import .excalidraw to bring in a standard file.

28. Use Open Whiteboards folder only for supported file management while
    documents are closed.

- The editor blocks network schemes and uses bundled assets.

- Old custom Science whiteboards are not migrated and remain untouched.

- Version snapshots are managed through Documents.

- If startup reports QListWidgetItem NameError, the installed package is
  older than the 0.10.11 hotfix or was not upgraded correctly.

# 12. Maps and field context

- Offline Maps use downloaded packages and local rendering.

- Area All merges enabled OpenStreetMap extracts so package boundaries
  are not shown in normal use.

- Named areas remain available for navigation and filtering.

- Map context supports location review but does not overwrite original
  capture metadata without an explicit edit.

- Sounds and Videos provide **Location…** for entering latitude and longitude.
  Country, region, and locality can be entered manually or reconstructed from
  the coordinates through OpenStreetMap Nominatim.

- Keep map packages and licensing information with the installation.

# 13. Export, reporting, and Fieldora integration

Export Assets and Export Data are separate from Reporting. Reporting
contains reports, templates, report history, and statistics. Generate
Report is also available contextually from media and collection screens.

Use **Reconstruct country / region…** in Analytics when existing coordinate-only
records appear as Unknown in geographic reports. The operation runs in the
Activity Center, fills only missing administrative geography, and requires an
internet connection. Refresh analytics after it completes.

| **Action**          | **Use**                                                                |
|---------------------|------------------------------------------------------------------------|
| Export Assets       | Create selected media derivatives or copies under explicit options     |
| Export Data         | Export structured records and metadata                                 |
| Generate Report     | Create a report from the active context and selected content           |
| Fieldora/API upload | Send governed elements under the same contract and permission boundary |

- Review the preflight summary, estimated size, unavailable originals,
  and destination.

- Choose report content separately from whether original media is
  included.

- Confirm filename collision and derivative-quality settings.

- Include provenance when required.

- For Fieldora integration, select only allowed elements; export/API
  upload rights and contract restrictions remain authoritative.

- Do not assume that possession of an export grants permission to
  redistribute it.

# 14. Synchronization and contracts

- Desktop synchronization uses versioned HTTPS endpoints and device
  registration.

- Project enrollment rights are default-deny when revoked, expired, or
  not acknowledged.

- Push and pull journals make interrupted work replay-safe.

- Contribution review shows updates, deletions, conflicts, licenses, and
  contract terms.

- Resolve conflicts explicitly: keep local, accept remote, or manual
  resolution.

- Governed packs are signed, encrypted, expiring, and revocable.

- A revoked right blocks new contribution and disclosure even when data
  was previously synchronized.

# 15. Jobs and Activity Center

- Queued: waiting for a worker or prerequisite.

- Active: currently running; progress and throughput may be shown.

- Completed: finished successfully; inspect output location or result.

- Failed: open technical details and follow the suggested action.

- Paused/cancelled: available only where the operation supports safe
  interruption.

- Do not launch duplicate jobs to work around a slow operation; check
  Activity Center first.

# 16. Settings, diagnostics, and updates

- Preferences: theme, language, behavior, and supported defaults.

- Branding & Project: Fieldora identity and project information.

- Access & Contracts: rights, enrollments, and governance context.

- Manage Integrations: external connections and Fieldora integration.

- Health Check: component readiness.

- Diagnostics: versions, paths, logs, and non-secret environment
  information.

- Updates: release and update controls.

- About Fieldora: release, Excalidraw version, licenses,
  acknowledgements, and system information.

# 17. Backup and recovery

- Ask an administrator for the approved backup destination and
  frequency.

- Keep at least one backup separate from the workstation.

- Verify backups; a copied file is not proof of recoverability.

- Practice restore into a new location.

- After recovery, check the library, photographs, documents,
  observations, AI resources, and search.

- Never overwrite the only surviving library during a restore test.

# 18. Troubleshooting and safe use

| **Problem**                | **What to do**                                                                                         |
|----------------------------|--------------------------------------------------------------------------------------------------------|
| Application does not start | Capture the full traceback and About/package version; install 0.10.11 for the Excalidraw import fix    |
| Thumbnails seem delayed    | Stop scrolling for at least 300 ms; current builds intentionally defer loading during rapid movement   |
| Search misses a file       | Try a filename fragment or parent folder; clear filters; ask an administrator to check the index       |
| Excalidraw is blank        | Select or create a document; verify embedded assets and current release; no external install is needed |
| AI actions disabled        | Open AI Resources and complete the selected model/classifier path                                      |
| Schema migration error     | Stop. Do not force the library. Record the exact release and use the compatible recovery procedure     |
| Export denied              | Review selection, purpose, contract, expiry, revocation, and field permissions                         |
| Window too large after moving screens | Move it to the target screen and wait for automatic refitting; Reset Workspace Layout if a dock remains inconvenient |

**Important:** When reporting a problem, include steps, time, release,
workspace, and error text. Remove passwords, tokens, DSNs, and sensitive
research data.

# 19. Glossary

| **Term**            | **Meaning**                                                                                                        |
|---------------------|--------------------------------------------------------------------------------------------------------------------|
| Library             | Fieldora's working data boundary for metadata, media references, caches, documents, and settings                   |
| PBAC                | Policy-based access control evaluated for action, resource, tenant, project, purpose, fields, conditions, and time |
| Contract            | Governance terms that may require approval and constrain disclosure or contribution                                |
| Governed export     | Export whose contents and lifecycle are filtered, recorded, expiring, and revocable                                |
| Fencing token       | Monotonic claim value preventing a stale worker from completing reassigned work                                    |
| Legal hold          | Administrative block that prevents retention deletion for covered resources                                        |
| Projection          | Rebuildable derived index, such as OpenSearch, that is not authoritative                                           |
| Excalidraw document | Standard offline .excalidraw file edited inside Fieldora and versioned through Documents                           |
