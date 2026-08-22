# Fieldora 0.05.1 Science Persistence Audit

## Result

**Internal validation passed; Windows field validation required.**

The active Science persistence path now follows the intended dependency direction:

`Qt screens → ScienceSession → repository contract → SqliteScienceRepository`

## Closed findings

- Science uses the registered optional-subsystem database path.
- Backup, restore staging, integrity checks, and Maintenance inventory include Science.
- Seven separate Science screens share one application-owned snapshot and revision.
- Stored entities have stable record identities and independent revisions.
- Saves calculate a diff and issue only required inserts, updates, and deletes.
- A no-op save neither rewrites records nor advances the database revision.
- Stale writers are refused before mutations.
- Restart loading and record deletion were validated against a fresh database.

## Quarantined source

The pre-0.05 full-table SQL adapter remains below an unconditional return in
`ui/qt/science.py` for one clean-start field comparison cycle. It is unreachable in
0.05.1. Remove it after Windows field validation confirms that no required field or
workflow was omitted from `science_records`.

## Remaining risks

- PySide6 is unavailable in the build environment, so complete interactive Qt testing
  must occur on the Windows target.
- The current application session intentionally serializes local Science edits. Future
  server synchronization needs record-level merge policies, not only stale-snapshot
  rejection.
- The generic record payload format needs a versioned export contract before portable
  project packages are frozen.

## Freeze gate

Phase A may be frozen after:

1. clean-start Windows creation and reopen;
2. project, dossier, artifact, calendar, and whiteboard mutation testing;
3. backup and full restore including Science;
4. forced stale-writer and interrupted-exit testing;
5. removal of the quarantined Qt adapter and its legacy SQLite import.
