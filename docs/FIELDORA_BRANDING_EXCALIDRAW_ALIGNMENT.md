# Fieldora branding and Excalidraw document alignment

## Decision

Fieldora is the user-facing product name. NatureAI Next remains the technical
engine and integration layer. Splash text, executable links, shortcut names,
icons, About descriptions, and project links use the Fieldora identity.

The Science whiteboard route now embeds the full offline Excalidraw application
and manages standard `.excalidraw` documents. These files live under
`Documents/Whiteboards` and
their immutable snapshots live under `Documents/Whiteboards/.versions`.
Whiteboard version control therefore belongs to Documents rather than the
Science database.

## Compatibility boundary

- The former custom Qt whiteboard is no longer exposed as the active editor.
- Existing Science whiteboard tables are left untouched and are not migrated.
- Existing whiteboards are not automatically converted or deleted.
- Dossiers can refer to new whiteboards through their normal Document links.
- Existing Aperture command aliases remain available for installed-script
  compatibility, but newly created user-facing links use Fieldora names.
- The bundled editor profile blocks HTTP and HTTPS requests; all application
  scripts, fonts, locales, and diagram modules ship inside Fieldora.
- Existing Science whiteboards require no migration. Libraries that predate the
  Phase E core schema receive a verified backup followed by the checksum-validated
  additive core migrations; `science.sqlite3` is not opened by that upgrade.

## Documentation alignment

| Source of truth | Required alignment |
| --- | --- |
| `PROJECT_SPEC.md` | Product identity, Excalidraw document ownership, no migration |
| `ARCHITECTURE.md` | Documents boundary and inactive legacy Science tables |
| `GUI.md` | Embedded editor, whiteboard navigation, autosave, snapshots |
| `DATABASE.md` | No new schema and no conversion of existing rows |
| `CONFIGURATION.md` | Local document path and bundled offline editor |
| `ROADMAP.md` | Replacement recorded as completed |
| `RELEASE_NOTES.md` / `CHANGELOG.md` | Current release behavior |
| `src/natureai_next/resources/help` | Synchronized copies of user-facing root docs |
