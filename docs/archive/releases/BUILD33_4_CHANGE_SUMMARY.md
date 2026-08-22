# Build 33.4 Change Summary

Build 33.4 turns Models into an explanatory model catalog. Every model declares its category, purpose, best uses, limitations, compatible companion models, normal workflow, runtime dependencies, and offline readiness.

Workflow dependencies are explicit. MegaDetector is described as camera-trap localization and requires BioCLIP 2 or BioCLIP 2.5 for species identification. YOLO detection and segmentation locate or isolate subjects; BioCLIP performs taxonomy classification. Segment Anything refines regions and likewise does not identify species by itself.

No working inference provider was replaced. Build 33.4 changes model discovery and presentation metadata while retaining Build 33.3 execution paths.
