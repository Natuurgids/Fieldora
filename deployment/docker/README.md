# Docker deployment target

Fieldora treats Windows Docker and Linux Docker as first-class deployment targets, separate from Windows Desktop, Linux Desktop, Kubernetes, and OpenShift.

The clean Docker installer implementation is organized here by responsibility:

- `common/Install-Fieldora-Clean.ps1` contains the shared clean Docker installation implementation.
- `windows/Install-Fieldora-Clean-Windows.ps1` is the Windows Docker entry point.
- `linux/Install-Fieldora-Clean-Linux.ps1` is the Linux Docker entry point.

The matching installer files at the repository root remain supported compatibility entry points because external raw-download consumers and installer selectors still use those paths. During this staging step the root and deployment-target copies are intentionally byte-for-byte identical. A later atomic cutover may replace the root copies with thin compatibility wrappers only after all consumers and certification workflows are updated together.

Do not treat the Linux Docker installer as a Linux Desktop installer.
