# Build 28 — Flexible Storage Architecture

Build 28 separates an asset's identity and enrichments from the physical location of its original media.

## Storage policies

- **Managed**: Aperture creates and verifies a full-size original in Aperture-managed storage. The import source is retained as provenance.
- **Linked**: Aperture works with the full-size source in place. Catalog data, thumbnails, previews and enrichments remain inside Aperture.
- **Hybrid**: Aperture keeps both a verified managed original and an active source reference.

The default policy is configurable in **Settings → Preferences** and can be changed for each import.

## Canonical model

`asset_storage_policies` records the policy for each asset. `storage_providers` describes Aperture, local, removable, network, cloud and camera storage. `asset_storage_locations` records source and Aperture-master locations independently from catalog enrichments. `storage_verification_events` preserves health-check history.

## Storage Manager

**Tools & Resources → Storage Manager** provides storage statistics, verifies selected or all locations, relinks missing sources with checksum validation, creates managed Aperture originals from linked sources, and removes redundant Aperture originals where a source reference remains.

## Backup semantics

The backup dialog supports catalog-only backups, catalog plus managed originals, catalog plus a linked-original manifest, and a complete storage-aware backup. Linked originals are never silently copied or deleted.

## Pre-RC clean-start policy

Build 28 defines the canonical development schema. Compatibility and migration from earlier development databases are intentionally not part of this build.
