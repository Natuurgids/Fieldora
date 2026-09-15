# Native update trust hardening

Status: implementation branch
Base: `54abf55aa0c5124e1c1e7c46db14814c64a4e37c`

## Objective

Close the native-update security findings without conflating integrity, authenticity, authorization, and deployment binding.

The target architecture is fail-closed at every trust boundary:

1. A release producer signs a canonical native update manifest with an offline/release-controlled Ed25519 key.
2. Fieldora verifies the detached signature against an administrator-controlled trust anchor before it accepts any update metadata.
3. The signed payload binds product, channel, version, minimum supported version, package filename, package SHA-256, package size, release identity, and the Security Install evidence digest.
4. Security Install derives `signature_verified` and `provenance_verified` from verification results. Serialized booleans from the update source are not treated as proof.
5. The detached updater remains independently PBAC-authorized as `fieldora-native-updater` with least privilege.
6. Clean installation provisions that service identity and only the `install` / `security_install_release` / `security_install` authorization required by the updater.
7. Desktop PBAC administration is fail-closed unless an authenticated acting identity is authorized to administer access control.
8. The desktop config root is propagated into the detached updater so the staged request, update history, and PBAC database resolve from the same application root.
9. Release/runtime evidence records immutable OCI image identity where container deployment is used.

## Required implementation changes

### F-01 Native release authenticity

Introduce a native-release verifier with an explicit trust-anchor interface. `OfflineUpdateService.check()` must verify `update-index.json` before reading security-sensitive fields from it. The signature file and package may live on removable/user-selected media; the trusted public key may not come from that same update source.

Canonical signed fields:

- format and format version
- product
- channel
- version
- minimum supported version
- package basename
- package SHA-256
- package byte size
- release identifier/digest
- Security Install evidence digest

Reject unsigned indexes, unknown key IDs, malformed signatures, path traversal, mismatched package digest/size, and evidence whose digest is not bound by the signed manifest.

### F-02 Native updater PBAC provisioning

Clean-install/bootstrap must create an enabled service identity with exact ID `fieldora-native-updater` and grant only:

- action: `install`
- resource type: `security_install_release`
- purpose: `security_install`

No wildcard action/resource policy is acceptable for the updater. Provisioning must be idempotent and covered by a clean-install test.

### F-03 PBAC administration authorization

The application-service boundary, not only Qt visibility, must authorize access-control mutations. Mutation methods must receive authenticated actor context and require a dedicated administration permission before writing organizations, identities, groups, roles, contracts, or policies.

The local Qt workspace must be read-only when no authenticated/authorized actor context is available.

### F-04 Config-root binding

The native handoff request must carry the resolved application/config root. The detached updater must resolve `access-control.sqlite3`, update history, and related state from that explicit root. Do not independently rediscover the root from inherited environment variables after handoff.

### F-05 Authenticated anti-rollback

Version and `minimum_supported_version` remain monotonic checks, but both must be inside the authenticated native-release manifest. Add tests proving that modifying either field invalidates the signature.

### F-06 Deployment identity

Container release/runtime evidence should bind:

`Git commit -> build input -> OCI digest -> deployed digest -> running container digest -> certification proof`.

Functional health checks remain necessary but are not a substitute for immutable artifact identity.

## Certification gates

The implementation is complete only when CI demonstrates all of the following:

- valid signed native update is accepted;
- unsigned index is rejected;
- signature made by an untrusted key is rejected;
- tampered version, minimum version, package hash, package size, release digest, or Security Install evidence is rejected;
- valid package with invalid/missing PBAC authorization is rejected;
- clean install provisions the exact updater identity and least-privilege allow policy;
- unrelated subjects cannot install a Security Install release;
- local PBAC mutation without authorized actor context is rejected;
- explicit non-default config root is preserved across detached updater handoff;
- updater cannot select a different PBAC database through inherited root environment variables;
- container certification records and verifies the immutable running image digest.

## Branch integration

This branch owns the security implementation. It should not be folded into stale deployment-layout staging work.

`feat/platform-bootstrap-contract` has useful overlap at the platform/supply-chain contract layer and should be rebased onto current `main`; its platform manifest work can remain separate. Native update authenticity, updater PBAC provisioning, and local PBAC authorization must be implemented here (or cherry-picked from here) so the trust-boundary changes remain independently reviewable.

## Non-claims

Until the implementation and tests above are merged, the audit does not claim demonstrated arbitrary package execution or RCE. Package SHA-256 is integrity, not publisher authenticity; PBAC is authorization, not provenance; and Git SHA is source identity, not OCI runtime identity.
