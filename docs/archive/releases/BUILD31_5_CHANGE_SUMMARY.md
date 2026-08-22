# Build 31.5 Change Summary

Build 31.5 is a focused field repair.

- Persisted JPEG thumbnails are accepted when their stored dimensions are larger than the current gallery cell; Qt scales them for display.
- Startup thumbnail reconciliation resumes failed, interrupted, and paused idempotent derivative jobs instead of merely rediscovering the same terminal job.
- The in-application Maintenance Center handoff directly invokes the installed console entry point with the active library.
- Windows Maintenance Center shortcuts now use an ApertureData launcher wrapper that resolves the configured library before starting maintenance.
