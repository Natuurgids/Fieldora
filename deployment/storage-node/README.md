# Fieldora linked storage node

Fieldora linked archives are an **offline-first storage path**. They do not require
FieldoraBastion, a public cloud, or an Internet connection once the Fieldora
platform and storage node have been provisioned.

The storage service owns the real filesystem mount and presents only an opaque
`storage_id`, relative catalogue paths, governed derivatives, and bounded original
ranges to Fieldora. The browser and Fieldora API do not receive the host mount path
or storage credentials.

## Supported deployment shapes

### 1. Direct attached storage on the Fieldora host

Use any host directory that Docker can read, including a local disk, RAID volume,
USB/DAS volume, or another directly attached filesystem. Set
`FIELDORA_STORAGE_ROOT` to that host directory. The Compose contract bind-mounts it
into the storage container at `/mnt/fieldora-storage` **read-only**.

For the clean single-host deployment, also use `compose.same-host.yaml`. It joins
the storage service to Fieldora's private Docker network so the mTLS endpoint can
be `https://fieldora-server:8765`; no Fieldora API port needs to be exposed beyond
the existing localhost browser listener.

Example PowerShell environment setup:

```powershell
$env:FIELDORA_STORAGE_ENDPOINT = "https://fieldora-server:8765"
$env:FIELDORA_STORAGE_SERVICE_ID = "<enrolled linked-storage service id>"
$env:FIELDORA_STORAGE_ORGANIZATION = "local"
$env:FIELDORA_STORAGE_ID = "archive-main"
$env:FIELDORA_STORAGE_DISPLAY_NAME = "Main archive"
$env:FIELDORA_STORAGE_ROOT_ALIAS = "main-archive"
$env:FIELDORA_STORAGE_ROOT = "D:\Archive"
$env:FIELDORA_STORAGE_TRUST_DIR = "D:\FieldoraStorageTrust"

docker compose `
  -f deployment/storage-node/compose.yaml `
  -f deployment/storage-node/compose.same-host.yaml `
  up -d --build
```

`FIELDORA_STORAGE_ROOT_ALIAS` is an opaque label, not a path. Do not use a drive
letter, UNC path, hostname, username, or other location-bearing value as the root
alias or storage identity.

## 2. LAN/NAS/network storage

Mount the SMB/NFS/NAS/SAN filesystem on the **storage-node host first** using the
host operating system or institutional storage tooling. Then set
`FIELDORA_STORAGE_ROOT` to that already-mounted host directory.

This is deliberate: NAS credentials remain in the host operating system,
credential manager, service account, mount unit, or other infrastructure boundary.
Do **not** place SMB/NFS usernames, passwords, access keys, or connection strings in
Fieldora browser fields, Fieldora service metadata, `FIELDORA_STORAGE_*` values, or
this Compose file.

On Windows, use a path that Docker Desktop can actually bind into Linux containers.
Mapped drive letters can be session-specific; a Docker-readable host mount is
preferred. On Linux, a systemd-managed NFS/SMB mount under a stable path such as
`/mnt/fieldora/archive` is suitable.

The storage container still receives the mounted archive read-only. Fieldora only
sees the storage service identity plus opaque archive/object identities.

## 3. Storage node on another host

Use `compose.yaml` by itself. Configure `FIELDORA_STORAGE_ENDPOINT` to an HTTPS DNS
origin reachable from that host and covered by the Fieldora server certificate.
The storage service makes outbound mTLS requests to Fieldora; it does not expose an
inbound NAS/file protocol to browsers or API nodes.

## Bastion is optional

FieldoraBastion is an acquisition/quarantine boundary for controlled external
downloads and transfer workflows. It is **not** on the normal read path for direct
attached or LAN linked storage and is not required for offline Library access.

A site can therefore run:

`browser -> Fieldora -> private storage-service -> local/NAS mount`

with the WAN disconnected. Bastion can remain stopped unless an explicit external
acquisition workflow needs it.

## Cloud is optional

Cloud/object storage can be added as a deployment choice, but it is not required by
the linked-storage contract. Fieldora authorization, provenance, stable IDs, and
checksums remain authoritative regardless of whether bytes live on direct storage,
a LAN archive, or an intentionally configured remote tier.

For sensitive evidence, prefer local or institution-controlled storage where that
matches the organisation's threat model. If a cloud tier is enabled, keep the same
principles: least-privilege service identity, encryption in transit and at rest,
explicit PBAC, no browser-visible storage credentials, auditable lifecycle, and no
silent widening of access.

## Security invariants

The reference storage container is intentionally constrained:

- archive bind mount is read-only;
- container root filesystem is read-only;
- `no-new-privileges` is enabled;
- all Linux capabilities are dropped;
- service trust material is mounted read-only;
- storage credentials and host paths are not browser/API metadata;
- archive disablement in Fieldora remains authoritative;
- machine-to-machine traffic uses enrolled service identity and mTLS.

The storage service must be enrolled and active in Operator before it can register
an archive. Its certificate identity and organisation must match the enrolled
service. A service re-registration must never bypass an Operator-disabled archive.
