# Build 33.2 Change Summary

Build 33.2 centralizes optional model installation and offline execution.

- MegaDetector now uses the maintained official MDv5a release instead of the removed v6 URL.
- Model health checks acquire required weights and resources into Aperture-owned model storage.
- Enrichment workers run with offline flags and cannot silently download resources.
- All catalog models declare a shared offline installation contract.
- BioCLIP 2 and BioCLIP 2.5 retain their Build 33.1 execution paths.
