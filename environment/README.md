# NatureAI Next environments

NatureAI Next must use an isolated Python 3.11 Conda environment. Do not install
it into the NatureAI Legacy environment.

Available definitions:

- `environment-core.yml`: command-line and non-GUI services.
- `environment-gui.yml`: normal desktop installation.
- `environment-full.yml`: desktop plus the local AI stack.
- `environment-dev.yml`: separate development environment with validation tools.
- `environment.yml`: GUI plus development tools; retained as the default developer file.

The PowerShell installer is preferred on Windows because it validates the Python
version, reuses an existing compatible environment, installs the pinned LibRaw/rawpy
camera-RAW adapter, records `pip freeze`, checks
entry points, and supports Core, GUI, and FullAI profiles.

Manual example:

```powershell
conda env create -f environment\environment-gui.yml
conda run -n natureai-next python scripts\verify_install.py --require-gui
```

The files under `requirements/` share `constraints-py311.txt`. The constraint
file pins direct dependencies selected for this source snapshot. It is not a
hash-locked wheel bundle; installation still downloads packages from configured
Conda/PyPI sources.
