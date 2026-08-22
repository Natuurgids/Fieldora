# Build 34 — Exchange & Internationalization

Build 34 establishes Aperture's offline-first exchange layer and internationalization foundation.

## Delivered

- Core locale service with English fallback and runtime locale switching contract.
- Built-in English, Dutch, German, French, Spanish, Portuguese, and Italian catalogs.
- Plugin catalog merge support.
- Localized Export workspace headings and export-language selection.
- Darwin Core Archive writer with Occurrence and Multimedia tables, `meta.xml`, and `eml.xml`.
- Connector registry and offline preflight mapping for Waarneming.nl, Observation.org, iNaturalist, and GBIF.
- Connector validation UI that identifies records requiring taxon, time, or location corrections before upload.
- Existing JSON, CSV, original-media package, provenance, activity, and cancellation behavior retained.

## Boundary

Build 34 deliberately does not silently perform network uploads. Credentials and network operations remain isolated from the user-owned library. Service-specific authenticated upload adapters can be added behind the connector contract after API approval and interoperability testing.
