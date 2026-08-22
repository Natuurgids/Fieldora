# Proposed media-library UI implementation

This package updates the Photos/Sounds/Videos/Documents presentation toward the supplied dark three-pane design while retaining the existing data-query, search, playback, PDF/text preview, overlay, selection, and enrichment connections.

## Main changes

- Sounds, Videos, and Documents now use a compact command bar consistent with Photos.
- Added a collapsible Structured Filters row without changing query semantics.
- Reorganized media workspaces into a preview/result area plus persistent right-side Inspector.
- Moved the canonical enrichment panel into the Inspector so existing enrichment actions and overlay synchronization remain wired.
- Added a contextual bottom action/status bar.
- Applied the existing Photos dark visual language across all media workspaces.
- Selection now updates type-specific Inspector metadata while still loading the selected source into the existing player/viewer.

## Validation

- `python -m py_compile src/natureai_next/ui/qt/media_library.py`
- `pytest -q tests/test_media_workspace_navigation.py tests/test_build27_repair1_library_map.py`
- Result: 5 passed.

This is a source package, not a newly signed Windows installer. Rebuild the Windows installer using the repository's normal build process after field validation.
