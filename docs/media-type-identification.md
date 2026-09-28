# Media type identification

Fieldora treats browser/client MIME declarations as hints, not canonical metadata.

The server canonicalizes empty and generic declarations (`application/octet-stream` and `binary/octet-stream`) from the filename at ingestion boundaries. Specific declared media types are preserved. Unknown extensions remain `application/octet-stream`.

This contract applies to direct managed uploads and linked-storage convergence. Staged ingestion additionally performs byte-signature detection before its filename fallback.

The purpose is to keep Library/Evidence Gallery preview/type behavior consistent across browser uploads, OS/WebView file pickers, staged directory intake, and linked storage.