# Science Subsystem Architecture

## Purpose

The Science subsystem organizes research projects, dossiers, specimen or observation
artifacts, calendar activities, and a drawing whiteboard. It extends Fieldora without
changing ownership of the personal media library.

## Database boundary

Science owns `science.sqlite3`. The database uses WAL journaling, foreign keys,
bounded busy waiting, and transactions local to the Science subsystem. It does not
join to or write through `library.sqlite3`.

From 0.05, Science is registered through the common optional-subsystem lifecycle at
`subsystems/science.sqlite3`. The registry owns activation, schema-family metadata,
health status, and SQLite integrity checks. Verified Library backups include an online
SQLite snapshot of Science with a checksum entry in the backup manifest.

Media links contain stable Fieldora asset public IDs. They are cross-subsystem
references, not database foreign keys. Original photos, sounds, videos, and documents
remain owned by the Fieldora library.

## Current entities

- projects;
- ordered project stages and stage-linked activities;
- required project resources, quantities, units, and estimated unit costs;
- planned and spent project budgets with an explicit currency;
- dossiers, including dossiers that act as projects;
- dossier-to-media references;
- animal, plant/flower, and other scientific artifacts;
- measurements and descriptive attributes;
- calendar activities;
- named whiteboards with persistent pen strokes, lines, rectangles, ellipses,
  sticky notes, built-in symbols, and sanitized embedded SVG-pack icons;
- stable Library asset references on a board for images, videos, sounds, and documents;
- dossier-to-whiteboard relations and SVG/PDF rendering;
- independent Science workspace visibility settings.

## Integrity rules

- A dossier may be independent, belong to one project, or share its identity with a
  project that it creates.
- Deleting or changing library media must not delete a dossier; an unavailable media
  reference remains provenance that can be diagnosed.
- Science writes never participate in a transaction with another Fieldora database.
- Original media are never copied or rewritten by dossier creation.
- Whiteboards store stable Library asset references, not duplicate original media.
- Imported SVG icons are self-contained, size-bounded, and reject scripts or external
  links; users remain responsible for the icon pack's license.
- Every committed Science mutation advances a database-wide revision. A process based
  on an older revision is refused instead of overwriting newer work.

## Incremental repository

Fieldora 0.05.1 moves the active persistence path to
`infrastructure/database/science.py`. One application-owned `ScienceSession` shares a
snapshot and revision across every Science screen. The repository compares that
snapshot with independently identified stored records and issues only the necessary
insert, update, and delete statements. Each changed record advances its own revision;
the database revision advances only when stored state changes.

The pre-0.05 full-table adapter remains unreachable in the Qt source for one field
validation cycle so its schema can be compared during clean-start testing. It is not
called by the application. Removing that quarantined source after field validation is
cleanup, not a persistence migration.
