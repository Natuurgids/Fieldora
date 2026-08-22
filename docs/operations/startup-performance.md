# Startup performance diagnostics

Aperture records low-overhead startup milestones in `%LOCALAPPDATA%\Aperture\Logs\startup-timing.jsonl`. Each line contains one launch with elapsed times for process start, foundation setup, library opening, desktop service composition, and first visible main-window paint.

Use this file when comparing cold and warm starts. A single slow launch is not necessarily a regression because antivirus scanning, Windows disk caching, GPU initialization, and first-time Python bytecode creation can affect results. Compare at least five cold launches after a restart and five warm launches.

The timing log contains the library display name and elapsed timings. It does not contain photographs, observation content, or database records.

Full database integrity checks, update scans, and maintenance history refreshes are intentionally kept outside the first-paint path. Run integrity checks from the Health Center when needed.


## V3.RC1F2 startup experience

Aperture now presents the packaged system logo and real milestone progress while the
blocking desktop path is assembled. The splash reuses the shared QApplication, remains
responsive through explicit event processing, and closes as soon as the main window is
shown. NatureAI, GBIF, update checks, integrity checks, and maintenance remain candidates
for post-first-paint background initialization; they must not be added to the blocking
progress budget. Startup timing records include `startup-splash-visible`.
