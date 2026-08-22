# Build 30 Change Summary

Build 30 formalizes Aperture's federated execution architecture. Independent import, export, derivative, AI, map and maintenance workers remain isolated, while common non-Qt activity contracts provide normalized lifecycle, progress, cancellation, retry, resource and diagnostic semantics.

Implemented:
- shared `ActivitySnapshot`, `ActivitySource` and `ActivityRegistry`;
- adapters for durable jobs and storage journals;
- shared capacity broker without centralizing execution;
- storage journal listing, explicit retry and cancellation; failed work no longer retries implicitly;
- derivative idempotency includes renderer and output format;
- derivative jobs resolve current catalog file paths before using stored fallback paths;
- durable derivative states include generating, blocked-source-offline, failed and valid;
- ADR-030 and ADR-031 documenting the accepted architecture;
- clean-install Windows and Linux field-test packages.
