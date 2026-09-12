# Linux Docker installation

This path installs the Fieldora governed web/server stack on a Linux Docker host.

## Requirements

- Linux host with PowerShell 7 (`pwsh`).
- Docker Engine accessible to the installing user.
- Docker Compose through `docker compose`.
- `curl` for TLS verification.

## Clean installation

Download and run the Linux wrapper from outside the target installation root:

```powershell
Invoke-WebRequest `
  -Uri https://raw.githubusercontent.com/Natuurgids/Fieldora/main/Install-Fieldora-Clean-Linux.ps1 `
  -OutFile ./Install-Fieldora-Clean-Linux.ps1

./Install-Fieldora-Clean-Linux.ps1 -FieldoraRef main
```

The default Linux install root is `$HOME/fieldora-server`.

The Linux wrapper preserves the same repository-controlled clean deployment architecture used by Windows while adapting host-specific Docker checks, certificate-trust guidance, and curl smoke testing.

## Destructive scope

The clean installer removes and recreates the selected Fieldora installation. Back up any data that must survive before using the clean path. Do not run the installer from inside the target install root.

## Security

The Linux path retains HTTPS, service identity, PostgreSQL TLS/mTLS, constrained certificate renewal, credential handoff, internal storage-service mTLS, and optional verified offline-model contracts. Host CA installation is distribution/operator specific; the installer verifies Fieldora TLS explicitly and provides trust guidance rather than weakening certificate validation.

## Production use

Treat the clean installer as a reproducible deployment baseline. Persistent production upgrades and migration should use an explicit backup/migration procedure rather than assuming a destructive clean reinstall preserves state.
