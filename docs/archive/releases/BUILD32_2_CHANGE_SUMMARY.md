# Build 32.2 Change Summary

Build 32.2 restores the specialized photo/BioCLIP review workflow as the Photos page inside the multimodal Knowledge Base and hardens BioCLIP visual provenance capture.

The persisted model-input snapshot is now best-effort and cannot fail a valid inference run. Images are explicitly converted to RGB, written to a JPEG temporary file, and atomically finalized. Snapshot failures are recorded diagnostically while classification continues. The existing BioCLIP generation, review, accept, reject, defer, provenance, and history controls remain the authoritative Photos workflow; sound, video, document, comparison, and accepted-knowledge screens remain separate multimodal pages.
