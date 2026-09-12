# Fieldora web parity — Library file-instance contract

Status: implementation contract for `WEB-034` in `WEB_DESKTOP_PARITY_PLAN.md`.

## Purpose

WEB-034 must let the managed browser distinguish one canonical evidence identity from the physical/logical file instances that carry its bytes. The browser must not manufacture storage semantics from upload history, filenames, project membership, or UI state.

The authoritative order remains domain invariants → application/repository contracts → governed API → UI.

## Existing authoritative desktop model

The desktop/catalog storage model already has the required concepts:

- `AssetStoragePolicy`: `managed`, `referenced`, `hybrid`;
- `StorageLocation` roles: source and managed/Aperture master;
- durable file-instance linkage through `asset_storage_locations.file_instance_id`;
- availability/health independent from evidence identity;
- an `asset_storage_overview` projection that derives policy and source/master/available counts without requiring UI code to inspect paths.

`ImportService.plan()` also establishes the identity rule: identical bytes under a different path or storage policy attach to the existing asset instead of creating another evidence identity.

## Managed-server model gap

The managed server currently has two separate storage-oriented registries:

1. `governed_media` stores the organization-canonical media identity plus one internal object-store `relative_path` for managed bytes.
2. linked-storage catalogues store organization-controlled referenced files by opaque storage source plus relative path, but currently mint their own `media_id` per linked storage/path.

Neither SQLite nor PostgreSQL governed-media persistence has a durable file-instance table keyed to the canonical governed `media_id`.

Therefore WEB-034 cannot be implemented correctly by adding browser labels alone. Doing so would either:

- pretend every governed media item is permanently `managed`;
- expose storage paths or provider internals;
- treat linked-storage catalogue identity as canonical evidence identity; or
- infer file instances from filenames/project relationships.

All four would violate the parity contract.

## Required managed-server contract

Introduce a durable governed media-instance record whose identity is subordinate to canonical `media_id`.

Minimum durable fields:

- opaque `instance_id`;
- canonical `media_id`;
- organization scope;
- storage policy/role sufficient to distinguish managed versus referenced presence;
- availability state;
- verified size and SHA-256 when established;
- opaque storage/provider reference where needed internally.

Internal-only fields may include object keys, relative paths, storage IDs, device/provider routing and other retrieval material. They must never be copied wholesale into browser JSON.

The server projection should derive evidence-level policy as:

- managed instance(s), no referenced instance → `managed`;
- referenced instance(s), no managed instance → `referenced`;
- both → `hybrid`.

A new instance must never allocate a new canonical evidence identity when the organization-scoped verified SHA-256 + size already resolves to existing evidence.

## API disclosure contract

The existing governed `/api/v1/media/{id}/detail` endpoint remains PBAC-gated by `view asset` in the requested Project context. File-instance disclosure is part of that authorized asset detail and must not weaken the existing relationship-specific PBAC filtering.

Safe browser projection may contain only values such as:

- evidence-level `storage_policy` (`managed`, `referenced`, `hybrid`);
- counts of managed/referenced/available instances;
- per-instance opaque ID, role/kind and availability when individual rows are useful.

The browser JSON must not contain:

- governed-media `relative_path`;
- linked-storage relative paths;
- object-store keys;
- filesystem paths or URIs;
- storage-node IDs/routing;
- organization IDs;
- device identities, mount paths or credentials.

## UI contract

The Library evidence detail should render canonical identity separately from file-instance state. A user must be able to understand that one evidence item can have multiple byte locations/instances without interpreting those instances as multiple evidence records.

The UI must not present project associations as storage ownership and must not imply that sharing/linking evidence creates a new file instance.

## Certification contract

Focused certification must cover at least:

1. one managed instance → one canonical evidence ID, policy `managed`;
2. one referenced instance → one canonical evidence ID, policy `referenced`;
3. managed + referenced instances with identical verified content → one canonical evidence ID, policy `hybrid`;
4. adding a materially distinct instance does not create a second evidence identity;
5. unauthorized asset detail remains 404/absent as today;
6. unauthorized relationships remain absent independently of storage-instance disclosure;
7. API and rendered UI contain no filesystem/object-store/linked-relative paths, organization IDs or provider-routing internals;
8. existing `/api/v1/media/{id}` byte/download behavior is unchanged.

SQLite/reference and PostgreSQL persistence must implement the same instance contract before WEB-034 is marked technically complete.

## Implementation sequence

1. Add a small governed media-instance value/repository contract shared by SQLite/reference and PostgreSQL metadata adapters.
2. Record a managed instance transactionally when a new governed upload/register creates canonical media; repeated exact uploads remain no-ops.
3. Add the referenced-instance attachment path by converging linked-storage verified content onto canonical media identity rather than minting a second evidence identity.
4. Expose only the safe derived storage projection from the existing governed media-detail endpoint.
5. Render the projection in the existing `media_detail_web.py` section.
6. Extend `media-identity-certification.yml` with real Chromium coverage for managed/referenced/hybrid identity and nondisclosure.

Do not mark WEB-034 DONE until both managed and referenced/hybrid cases are durably represented and certified.
