# Next implementation slice

1. Wire the HTTP-neutral `FacilityApiAdapter` into the main authenticated server composition without bypassing existing authorization or canonical Operations services.
2. Reconcile the older future-layout / relocation helper implementations still present on `OperationsAssetService` so `FacilityPlanningService` is the single supported planning facade.
3. Remove the focused-CI Ruff exceptions (`UP035` for `operations_assets.py`, `I001/F401` for `facility_planning.py`) as part of that controlled cleanup, keeping facility certification strict.
4. Run the broader Fieldora Ruff/unit/migration/Qt certification suite against the feature branch.
5. Perform an interactive desktop smoke test using real multi-level facility data plus Library-governed SVG/PDF/CAD-derived drawing assets.
6. Keep PR #1 in draft until the broader certification and smoke evidence are green; do not merge solely on the focused facility workflow.

Release invariant: planning and intermediate relocation states must never mutate the authoritative current physical location. Only an explicit final placement action may update live placement and append movement history.
