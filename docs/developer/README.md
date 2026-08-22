# Aperture Developer Guide

The implementation namespace remains `natureai_next`. User-visible strings use Aperture; internal package names, commands, database identifiers, plugin API, and resource formats must not be rebranded.

Use Python 3.11 and the `src/` layout. Production code is typed. Dependency direction remains `shared <- domain <- ports/application <- infrastructure/ui/plugins/bootstrap`. UI code must not perform blocking filesystem, database, metadata, thumbnail, or inference work on the Qt thread.

Run `python scripts/validate.py` in the development environment. The sequence compiles sources, checks Ruff formatting/lint, runs mypy and import-linter, then executes pytest. Add regression coverage for every defect. Documentation changes that affect a workflow ship in the same release as the code.


## Native Windows installer

See [Build a Windows installer](build-windows-installer.md) for the supported developer workflow using PyInstaller and Inno Setup. The helper script is shipped as `scripts/build_aperture_windows_installer.ps1`. Native Windows installer outputs must be built and validated on Windows.

## Offline map packages

See [Offline Map Catalogs and Bundles](offline-map-packages.md) for the catalog schema, `.apkg` bundle format, verification, and installation rules.
