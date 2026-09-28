# ADR: canonical media type ownership

Status: accepted for implementation.

The installed Fieldora server owns canonical media-type identification. Client/browser `File.type` is advisory because desktop WebViews and operating-system pickers may provide an empty value. Generic binary declarations therefore cannot be persisted as authoritative metadata when the filename provides a known type.

Direct uploads normalize at the server API boundary. Linked-storage convergence normalizes before attaching referenced media. Staged ingestion keeps its stronger signature detection plus filename fallback. Specific non-generic declarations remain unchanged.
