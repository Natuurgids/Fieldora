# Windows Docker installation

This path installs the **Fieldora web/server stack on Windows using Docker Desktop**. It is not the native Windows desktop application installer.

## Requirements

- Windows 11 host.
- PowerShell 7 (`pwsh`).
- Docker Desktop running Linux containers.
- Docker Compose available through `docker compose`.
- Network access to the repository/source unless using an explicitly prepared offline path.

## Clean installation

Run the Windows wrapper from a directory **outside** the target installation root:

```powershell
irm https://raw.githubusercontent.com/Natuurgids/Fieldora/main/Install-Fieldora-Clean-Windows.ps1 -OutFile .\Install-Fieldora-Clean-Windows.ps1
.\Install-Fieldora-Clean-Windows.ps1 -FieldoraRef main
```

The default install root is currently `D:\FDTEST`.

The installer asks for explicit confirmation before the destructive clean step. A clean install removes the previous Fieldora Docker deployment and PostgreSQL data **inside the selected installation root**, removes the known Fieldora containers/volumes/network/image, recreates the installation, builds the image, initializes PostgreSQL databases, and starts the server stack.

Do not run a clean installation against an install root containing data you intend to preserve.

## What is created

The certified clean-install architecture includes:

- Fieldora API/server;
- Fieldora worker;
- PostgreSQL and the Fieldora application databases;
- HTTPS service trust;
- mutual-TLS PostgreSQL/service identity material;
- certificate-renewal infrastructure;
- temporary bootstrap administrator credential handoff;
- internal storage-service mTLS listener;
- optional verified offline model provisioning.

The Windows wrapper imports the generated Fieldora public root CA into the current user's Windows root store and verifies HTTPS using the OS trust store.

## Credentials

Treat the bootstrap credential handoff as temporary sensitive material. Read the installer output for its location and retention behavior, log in, establish the intended administrator state, and rotate/remove temporary credentials according to operational policy.

## Data and upgrades

The clean installer is intentionally a clean-room/rebuild operation for its target root. Production data upgrades, migration, backup, and restore must be planned separately from a destructive test-root reinstall.

## Desktop application

This Docker deployment does not replace the native Windows desktop installation. Both may exist for different workflows.
