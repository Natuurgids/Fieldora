# Build 35 UI repair

- Made the photo enrichment workflow graph responsive. It stays horizontal in wide workspaces and switches to a vertical sequence in narrow viewer/inspector panes, so later stages are no longer clipped off-screen.
- Removed the workflow-node minimum width that forced overflow at smaller window sizes.
- Corrected the collapsed enrichment panel height calculation. The visible pipeline is now included in the fixed height, preventing the pipeline summary from being hidden behind the Photos selection/action bar.
- Verified with the Build 33.5 workflow-pipeline tests and Build 35 platform-completion tests (5 passed).

The region-aware model flow remains represented by canonical spatial enrichment: detector output can identify a raster/zoom region, and downstream identification should consume that selected region rather than the full photo. This repair focuses on the reported presentation and accessibility defects.
