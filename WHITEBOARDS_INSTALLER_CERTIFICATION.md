# Whiteboards installer certification

The complete Windows installer is pinned to Fieldora `7c49b936cb06273e98526c2f7060a064b502804f`.

Acceptance requires:

1. The exact immutable pin is present in `Install-Fieldora-Complete-Windows.ps1`.
2. The canonical shell renders exactly one visible/actionable `#whiteboards-link`.
3. The composed runtime serves `/whiteboards/?project_id=acceptance-project` successfully.
4. The click handler preserves selected-project context.
5. Existing repository certification checks remain green.

A helper-level DOM repair alone is not certification.
