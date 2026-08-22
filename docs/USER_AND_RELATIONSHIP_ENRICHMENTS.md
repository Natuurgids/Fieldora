# User and relationship enrichments

RC1F6 distinguishes immutable asset facts from knowledge added after import.

* Capture location is asset provenance: where the camera was when the file was created.
* Subject location is a user enrichment: where the photographed subject was located.
* Titles, captions, notes, ratings, tags and other user assertions are enrichments and retain provenance/history.
* Duplicate and version findings are relationship enrichments. A relationship group may have a user title and one designated current asset without deleting any related asset.
* A related asset may retain its own source/current storage location. Changing the current representative is an append-only decision, not destructive file replacement.

The Library Inspector is selection-aware: one selected photograph shows Photo and Geolocation controls; two or more selected photographs replace those controls with Batch Update.
