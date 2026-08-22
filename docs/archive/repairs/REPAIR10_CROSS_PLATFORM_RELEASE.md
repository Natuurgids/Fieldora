# Build 26 Repair 10 — Cross-platform release closure

Repair 10 adds a transactional Linux installation path and closes the Repair 9 release blockers.

## Windows

The source and generated Windows repair commands explicitly disable environment recreation. Repair therefore cannot remove the installed Conda environment while package and dependency installation are skipped.

## Linux

`Install Aperture Linux.sh` creates a managed Python 3.11 virtual environment in a staging directory, installs GUI dependencies and Aperture, runs the installed-package verification including clean-library creation and `observations` compilation, atomically publishes the runtime, installs a freedesktop launcher, creates the first library, and executes a real Qt off-screen startup/normal-shutdown smoke test.

The Linux installer refuses Python versions other than 3.11. `--skip-gui-smoke` exists only for diagnosed systems where an off-screen Qt platform plugin is unavailable; production acceptance must run without that switch.

## Release checker

The release checker disables bytecode generation before importing local helpers, so the documented command is non-mutating.
