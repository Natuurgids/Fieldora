# Taxonomy Library

The Taxonomy workspace provides the current scientific classification used by Aperture. Version 1 focuses on stable browsing and assignment of taxa to observations. Major knowledge-center features such as comparison, maps, taxon timelines, and the Natuurgids.org Design System remain reserved for Version 2.

## Expected information

A taxon record should provide its scientific name, rank, accepted parent hierarchy, available common names, authority or source identifiers when supplied, and synonym relationships supported by the installed taxonomy package. Observation counts and AI suggestions are library data and do not replace the authoritative taxonomy record.

## Data quality

Missing names or hierarchy should be corrected in the source taxonomy package rather than edited directly in `library.sqlite3`. Use the Health Center and diagnostic logs to identify package or indexing problems. Back up the library before importing or replacing taxonomy resources.

## Importing GBIF Darwin Core Archives

Open **Resources → Taxonomy Resources → Import GBIF Darwin Core Archive** to load a raw GBIF source ZIP as taxonomy. Aperture reads `meta.xml` and the declared core table, preserves the original archive unchanged, deduplicates taxon identifiers, installs a signed local taxonomy package, and adds scientific and available vernacular names. This workflow is separate from image import and separate from AI model installation.

A taxonomy can be installed before BioCLIP. When a compatible model and prompt set later become active, choose **Build taxonomy embeddings** or re-import the taxonomy to reconcile model labels with the installed taxonomy. A taxonomy package extends the model vocabulary; it does not replace or reuse the model package identity.

## Version 2 scope

Version 2 will expand this area into Taxonomy & Knowledge with ecology, identification traits, conservation, media, similar species, analytics, completeness scoring, and validated taxonomy maintenance workflows.

## Importing an extracted Darwin Core folder

Build 3.322 accepts both the original GBIF `.zip` and an already-extracted Darwin Core Archive directory. In **Resources → Taxonomy Resources**, choose **Import GBIF Darwin Core Archive…** for a ZIP or **Import Extracted Darwin Core Folder…** for a directory. The directory must contain exactly one `meta.xml`; Aperture resolves the declared core table relative to that file and reads the source in place. It does not normalize, recompress, or modify the source files. Metadata declarations without explicit column `index` attributes are interpreted in declaration order.


## Detached source builds and working sets

Large GBIF source builds run outside the Aperture process. Closing or restarting Aperture does not terminate the builder. Activity Center can reattach to the persistent job, and the builder resumes from its last committed 5,000-row checkpoint when necessary. The active taxonomy database remains read-only and available throughout.

Use **Taxonomy Resources → Manage Working Taxonomy Sets** to save focused views by kingdom, class, order/subgroup, family, or rank. For example, choose `Animalia`, then `Aves`, then `Accipitriformes` to create a birds-of-prey working set. These filters do not copy taxonomy rows into the Aperture Library.
