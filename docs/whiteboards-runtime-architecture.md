# Whiteboards runtime ownership

Whiteboards is a first-class Fieldora destination.

## Invariants

- The canonical server shell owns the single rendered `#whiteboards-link` navigation control.
- `ExcalidrawWebMixin` owns the governed `/whiteboards/` application and its project-context integration; it must not be treated as the primary owner of sidebar rendering.
- Audit/repair layers may verify compatibility, but certification must not rely on them to manufacture the primary navigation control.
- Clicking Whiteboards resolves the selected project and navigates to `/whiteboards/?project_id=<selected-project>`.
- Release acceptance is performed against the composed `OfflineFirstFieldoraApi`, not an isolated HTML rewrite helper.
- The Windows complete installer pins an immutable Fieldora commit only after the composed-runtime acceptance suite is green.

This contract exists to prevent a recurrence of the false-positive certification where helper/audit tests passed while the clean installed UI lacked Whiteboards.
