"""Command line for the one-node Fieldora reference server."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

from natureai_next.application.access_control import (
    AccessAdministrationService,
    PolicyDecisionService,
)
from natureai_next.application.authentication import AuthenticationService
from natureai_next.application.device_authorization import DeviceAuthorizationService
from natureai_next.application.oidc import OidcAuthenticationService, OidcConfiguration
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.domain.access_control import IdentityKind, PolicyEffect, PolicySource
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)
from natureai_next.server.api import FieldoraApi, ScienceReadProjection
from natureai_next.server.export_encryption import (
    decrypt_project_export,
    generate_recipient_identity,
)
from natureai_next.server.export_signing import (
    ExportSigningIdentity,
    verify_export_attestation,
)
from natureai_next.server.exports import GovernedExportStore
from natureai_next.server.http import serve
from natureai_next.server.jobs import ServerJobStore, run_one_job
from natureai_next.server.lifecycle import ShutdownCoordinator
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.object_storage import S3ObjectStore
from natureai_next.server.postgres_access import PostgresAccessControlRepository
from natureai_next.server.postgres_exports import PostgresExportMetadataRepository
from natureai_next.server.postgres_jobs import PostgresServerJobStore
from natureai_next.server.postgres_media import PostgresMediaMetadataRepository
from natureai_next.server.postgres_science import PostgresScienceRepository
from natureai_next.server.readiness import ReadinessMonitor
from natureai_next.server.search import OpenSearchProjection, SearchProjection
from natureai_next.server.staged_ingestion import StagedIngestionService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-server")
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--tls-certificate", type=Path)
    parser.add_argument("--tls-private-key", type=Path)
    parser.add_argument("--allow-insecure-http", action="store_true")
    parser.add_argument("--drain-seconds", type=float, default=30.0)
    parser.add_argument("--access-backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--science-backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--media-metadata-backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--job-backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--export-metadata-backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--governance-backend", choices=("sqlite", "postgresql"), default="sqlite")
    parser.add_argument("--search-backend", choices=("memory", "opensearch"), default="memory")
    parser.add_argument("--media-object-store", choices=("filesystem", "s3"), default="filesystem")
    parser.add_argument("--postgres-dsn", default="")
    parser.add_argument("--opensearch-url", default="")
    parser.add_argument("--s3-endpoint-url", default="")
    parser.add_argument("--s3-bucket", default="")
    parser.add_argument("--s3-region", default="us-east-1")
    parser.add_argument("--s3-access-key-id", default="")
    parser.add_argument("--s3-secret-access-key", default="")
    parser.add_argument("--oidc-issuer", default="")
    parser.add_argument("--oidc-client-id", default="")
    parser.add_argument("--oidc-jwks-url", default="")
    parser.add_argument("--oidc-authorization-endpoint", default="")
    parser.add_argument("--oidc-token-endpoint", default="")
    parser.add_argument("--oidc-device-authorization-endpoint", default="")
    parser.add_argument("--oidc-scopes", default="openid profile email")
    parser.add_argument("--oidc-redirect-uri", default="http://127.0.0.1:8765/api/v1/auth/oidc/callback")
    parser.add_argument("--oidc-post-logout-redirect-uri", default="")
    parser.add_argument("--oidc-client-secret", default="")
    parser.add_argument("--oidc-client-secret-file", default="")
    parser.add_argument("--oidc-admin-group", action="append", default=[])
    parser.add_argument("--oidc-scientist-group", action="append", default=[])
    parser.add_argument("--oidc-curator-group", action="append", default=[])
    parser.add_argument("--oidc-reviewer-group", action="append", default=[])
    parser.add_argument("--oidc-operator-group", action="append", default=[])
    parser.add_argument("--oidc-group-claim", default="groups")
    parser.add_argument("--oidc-organization-claim", default="organization_id")
    parser.add_argument("--oidc-default-organization", default="")
    parser.add_argument("--oidc-session-ttl-seconds", type=int, default=3600)
    parser.add_argument("--oidc-jwks-cache-seconds", type=int, default=300)
    parser.add_argument("--oidc-clock-skew-seconds", type=int, default=60)
    parser.add_argument("--oidc-http-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--oidc-disable-pkce", action="store_true")
    parser.add_argument("--oidc-disable-nonce", action="store_true")
    parser.add_argument("--oidc-disable-state", action="store_true")
    parser.add_argument("--oidc-require-https", action="store_true")
    parser.add_argument("--oidc-allow-http-localhost", action="store_true")
    parser.add_argument("--oidc-audience", action="append", default=[])
    parser.add_argument("--oidc-required-claim", action="append", default=[])
    parser.add_argument("--oidc-username-claim", default="preferred_username")
    parser.add_argument("--oidc-email-claim", default="email")
    parser.add_argument("--oidc-name-claim", default="name")
    parser.add_argument("--oidc-subject-claim", default="sub")
    parser.add_argument("--oidc-token-auth-method", choices=("client_secret_post", "client_secret_basic"), default="client_secret_post")
    parser.add_argument("--oidc-device-flow", action="store_true")
    parser.add_argument("--bootstrap-admin-username", default="")
    parser.add_argument("--bootstrap-admin-password", default="")
    parser.add_argument("--bootstrap-admin-password-file", default="")
    parser.add_argument("--bootstrap-admin-organization", default="local")
    parser.add_argument("--bootstrap-admin-display-name", default="Fieldora Administrator")
    parser.add_argument("--bootstrap-admin-email", default="")
    parser.add_argument("--bootstrap-admin-require-password-change", action="store_true")
    parser.add_argument("--bootstrap-admin-no-require-password-change", action="store_true")
    parser.add_argument("--bootstrap-admin-print-credentials", action="store_true")
    parser.add_argument("--bootstrap-admin-output-file", default="")
    parser.add_argument("--bootstrap-admin-force", action="store_true")
    parser.add_argument("--bootstrap-admin-disable", action="store_true")
    parser.add_argument("--bootstrap-admin-ttl-hours", type=int, default=0)
    parser.add_argument("--bootstrap-admin-purpose", default="bootstrap")
    parser.add_argument("--bootstrap-admin-role", action="append", default=[])
    parser.add_argument("--bootstrap-admin-permission", action="append", default=[])
    parser.add_argument("--bootstrap-admin-policy", action="append", default=[])
    parser.add_argument("--bootstrap-admin-policy-source", default="bootstrap")
    parser.add_argument("--bootstrap-admin-policy-effect", choices=("allow", "deny"), default="allow")
    parser.add_argument("--bootstrap-admin-policy-priority", type=int, default=100)
    parser.add_argument("--bootstrap-admin-policy-resource-type", default="*")
    parser.add_argument("--bootstrap-admin-policy-action", default="*")
    parser.add_argument("--bootstrap-admin-policy-purpose", default="*")
    parser.add_argument("--bootstrap-admin-policy-project", default="*")
    parser.add_argument("--bootstrap-admin-policy-location", default="*")
    parser.add_argument("--bootstrap-admin-policy-organization", default="*")
    parser.add_argument("--bootstrap-admin-policy-subject", default="")
    parser.add_argument("--bootstrap-admin-policy-subject-kind", choices=("user", "group", "service"), default="user")
    parser.add_argument("--bootstrap-admin-policy-expires-hours", type=int, default=0)
    parser.add_argument("--bootstrap-admin-policy-description", default="Bootstrap administrator policy")
    parser.add_argument("--bootstrap-admin-policy-id", default="")
    parser.add_argument("--bootstrap-admin-identity-id", default="")
    parser.add_argument("--bootstrap-admin-session-ttl-hours", type=int, default=12)
    parser.add_argument("--bootstrap-admin-token-ttl-minutes", type=int, default=30)
    parser.add_argument("--bootstrap-admin-max-failed-logins", type=int, default=10)
    parser.add_argument("--bootstrap-admin-lockout-minutes", type=int, default=15)
    parser.add_argument("--bootstrap-admin-password-min-length", type=int, default=16)
    parser.add_argument("--bootstrap-admin-password-require-upper", action="store_true")
    parser.add_argument("--bootstrap-admin-password-require-lower", action="store_true")
    parser.add_argument("--bootstrap-admin-password-require-digit", action="store_true")
    parser.add_argument("--bootstrap-admin-password-require-symbol", action="store_true")
    parser.add_argument("--bootstrap-admin-password-no-require-upper", action="store_true")
    parser.add_argument("--bootstrap-admin-password-no-require-lower", action="store_true")
    parser.add_argument("--bootstrap-admin-password-no-require-digit", action="store_true")
    parser.add_argument("--bootstrap-admin-password-no-require-symbol", action="store_true")
    parser.add_argument("--bootstrap-admin-password-prompt", action="store_true")
    parser.add_argument("--bootstrap-admin-password-generate", action="store_true")
    parser.add_argument("--bootstrap-admin-password-length", type=int, default=32)
    parser.add_argument("--bootstrap-admin-password-alphabet", default="")
    parser.add_argument("--bootstrap-admin-password-entropy-bits", type=int, default=128)
    parser.add_argument("--bootstrap-admin-password-output-format", choices=("text", "json"), default="text")
    parser.add_argument("--bootstrap-admin-password-clipboard", action="store_true")
    parser.add_argument("--bootstrap-admin-password-stdin", action="store_true")
    parser.add_argument("--bootstrap-admin-password-env", default="")
    parser.add_argument("--bootstrap-admin-password-secret-name", default="")
    parser.add_argument("--bootstrap-admin-password-secret-provider", default="")
    parser.add_argument("--bootstrap-admin-password-secret-path", default="")
    parser.add_argument("--bootstrap-admin-password-secret-key", default="")
    parser.add_argument("--bootstrap-admin-password-secret-version", default="")
    parser.add_argument("--bootstrap-admin-password-secret-namespace", default="")
    parser.add_argument("--bootstrap-admin-password-secret-mount", default="")
    parser.add_argument("--bootstrap-admin-password-secret-context", default="")
    parser.add_argument("--bootstrap-admin-password-secret-audience", default="")
    parser.add_argument("--bootstrap-admin-password-secret-role", default="")
    parser.add_argument("--bootstrap-admin-password-secret-token", default="")
    parser.add_argument("--bootstrap-admin-password-secret-token-file", default="")
    parser.add_argument("--bootstrap-admin-password-secret-token-env", default="")
    parser.add_argument("--bootstrap-admin-password-secret-timeout", type=float, default=5.0)
    parser.add_argument("--bootstrap-admin-password-secret-ca", default="")
    parser.add_argument("--bootstrap-admin-password-secret-cert", default="")
    parser.add_argument("--bootstrap-admin-password-secret-key-file", default="")
    parser.add_argument("--bootstrap-admin-password-secret-verify", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-no-verify", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-proxy", default="")
    parser.add_argument("--bootstrap-admin-password-secret-no-proxy", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-retries", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-backoff", type=float, default=0.5)
    parser.add_argument("--bootstrap-admin-password-secret-header", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-query", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-body", default="")
    parser.add_argument("--bootstrap-admin-password-secret-method", default="GET")
    parser.add_argument("--bootstrap-admin-password-secret-json-path", default="")
    parser.add_argument("--bootstrap-admin-password-secret-text-regex", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-arg", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-env", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-cwd", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-timeout", type=float, default=5.0)
    parser.add_argument("--bootstrap-admin-password-secret-command-shell", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-no-shell", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-encoding", default="utf-8")
    parser.add_argument("--bootstrap-admin-password-secret-command-strip", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-no-strip", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-allow-empty", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-max-bytes", type=int, default=65536)
    parser.add_argument("--bootstrap-admin-password-secret-command-allowed-exit", action="append", type=int, default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-denied-exit", action="append", type=int, default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-redact", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-audit", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-no-audit", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-network", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-no-network", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-user", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-group", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-umask", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-chroot", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-seccomp", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-apparmor", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-selinux", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-cap-drop", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-cap-add", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-no-new-privileges", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-read-only", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-volume", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-device", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-pid", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-ipc", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-uts", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-cgroupns", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-runtime", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-platform", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-memory", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-cpus", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-pids-limit", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-ulimit", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-label", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-security-opt", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-env-file", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-workdir", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-entrypoint", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-stop-signal", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-stop-timeout", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-init", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tty", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-interactive", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-privileged", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-publish", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-expose", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-network-alias", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-dns", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-add-host", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-hostname", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-domainname", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-mac-address", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-sysctl", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-shm-size", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-gpus", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-runtime-class", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-annotation", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-health-cmd", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-health-interval", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-health-timeout", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-health-retries", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-health-start-period", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-health-start-interval", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-log-driver", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-log-opt", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-pull", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-platform-os", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-platform-arch", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-platform-variant", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-host-gateway", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-isolation", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-cgroup-parent", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-oom-kill-disable", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-oom-score-adj", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-cpu-shares", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-cpu-quota", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-cpu-period", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-cpuset-cpus", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-cpuset-mems", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-blkio-weight", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-device-read-bps", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-device-write-bps", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-device-read-iops", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-device-write-iops", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-kernel-memory", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-memory-reservation", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-memory-swap", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-memory-swappiness", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-pids", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-userns", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-volume-driver", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-mount", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-workdir-create", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-init-path", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-runtime-args", action="append", default=[])
    parser.add_argument("--bootstrap-admin-password-secret-command-hostname-file", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-resolv-conf", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-hosts-file", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-procfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-sysfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-cgroupfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-devpts", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-mqueue", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-securityfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-debugfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tracefs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-configfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-binfmt-misc", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-hugetlbfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-pstore", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-efivarfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-fusectl", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-selinuxfs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-bpf", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-autofs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-rpc_pipefs", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-nfsd", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-sunrpc", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-overlay", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-size", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-mode", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-uid", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-gid", type=int, default=0)
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-noexec", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nosuid", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nodev", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-relatime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-strictatime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-sync", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-dir-sync", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-mand", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-lazytime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-seclabel", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-noseclabel", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-context", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-fscontext", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-defcontext", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-rootcontext", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-mpol", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nr_inodes", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nr_blocks", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-huge", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-quota", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-noquota", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-noswap", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-casefold", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nocasefold", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-directio", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nodirectio", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-iversion", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-noiversion", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-user-xattr", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nouser-xattr", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-posix-acl", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-noposix-acl", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-dax", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-tmpfs-nodax", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-noatime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-nodiratime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-diratime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-exec", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-noexec", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-suid", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-nosuid", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-dev", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-nodev", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-async", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-sync", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-atime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-strictatime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-lazytime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-nolazytime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-bind", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-rbind", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-move", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-remount", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-private", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-rprivate", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-shared", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-rshared", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-slave", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-rslave", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-unbindable", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-runbindable", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-silent", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-loud", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-defaults", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-ro", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-rw", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-relatime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-norelatime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-nosymfollow", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-symfollow", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-fail-on-error", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-ignore-errors", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-disable", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-type", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-level", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-filetype", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-user", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-role", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-range", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-sensitivity", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-category", default="")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-mls", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-mcs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-selinux", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-apparmor", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-seccomp", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-no-new-privileges", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-read-only", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-privileged", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-network", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-pid", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-ipc", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-uts", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-cgroupns", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-userns", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-device", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-capabilities", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-mounts", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-secrets", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-env", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-args", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-command", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-entrypoint", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-workdir", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-hostname", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-domainname", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-mac-address", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-dns", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-add-host", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-sysctl", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-shm-size", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-gpus", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-runtime", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-platform", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-memory", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-cpus", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-pids-limit", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-ulimit", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-health", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-logging", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-pull", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-isolation", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-cgroup-parent", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-oom", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-cpu", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-blkio", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-kernel-memory", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-memory-reservation", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-memory-swap", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-memory-swappiness", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-volume-driver", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-mount", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-init", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-tty", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-interactive", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-publish", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-expose", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-network-alias", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-stop-signal", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-stop-timeout", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-runtime-args", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-filesystem", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-procfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-sysfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-cgroupfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-devpts", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-mqueue", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-securityfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-debugfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-tracefs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-configfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-binfmt-misc", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-hugetlbfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-pstore", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-efivarfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-fusectl", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-selinuxfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-bpf", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-autofs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-rpc_pipefs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-nfsd", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-sunrpc", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-overlay", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-tmpfs", action="store_true")
    parser.add_argument("--bootstrap-admin-password-secret-command-label-rootfs", action="store_true")
    return parser


def validate_listener_security(
    host: str,
    tls_certificate: Path | None,
    tls_private_key: Path | None,
    *,
    allow_insecure_http: bool,
) -> bool:
    if (tls_certificate is None) != (tls_private_key is None):
        raise ValueError("TLS certificate and private key must be configured together")
    if tls_certificate is not None:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    local_only = host == "localhost" or (address is not None and address.is_loopback)
    if not local_only and not allow_insecure_http:
        raise ValueError(
            "non-loopback Fieldora listeners require --tls-certificate and "
            "--tls-private-key (or explicit --allow-insecure-http for development)"
        )
    return False


def _required(value: str, option: str) -> str:
    if not value:
        raise SystemExit(f"{option} is required for this backend")
    return value


def _secret_value(value: str, path: str) -> str:
    if value and path:
        raise SystemExit("configure an OIDC client secret directly or by file, not both")
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return value


def _postgres_dsn(args: argparse.Namespace) -> str:
    return _required(args.postgres_dsn, "--postgres-dsn")


def _oidc_configuration(args: argparse.Namespace) -> OidcConfiguration | None:
    if not args.oidc_issuer:
        return None
    return OidcConfiguration(
        issuer=args.oidc_issuer,
        client_id=_required(args.oidc_client_id, "--oidc-client-id"),
        jwks_url=_required(args.oidc_jwks_url, "--oidc-jwks-url"),
        authorization_endpoint=_required(
            args.oidc_authorization_endpoint, "--oidc-authorization-endpoint"
        ),
        token_endpoint=_required(args.oidc_token_endpoint, "--oidc-token-endpoint"),
        redirect_uri=args.oidc_redirect_uri,
        client_secret=_secret_value(args.oidc_client_secret, args.oidc_client_secret_file),
        scopes=tuple(part for part in args.oidc_scopes.split() if part),
        group_claim=args.oidc_group_claim,
        organization_claim=args.oidc_organization_claim,
        default_organization=args.oidc_default_organization,
        admin_groups=tuple(args.oidc_admin_group),
        scientist_groups=tuple(args.oidc_scientist_group),
        curator_groups=tuple(args.oidc_curator_group),
        reviewer_groups=tuple(args.oidc_reviewer_group),
        operator_groups=tuple(args.oidc_operator_group),
        session_ttl_seconds=args.oidc_session_ttl_seconds,
        jwks_cache_seconds=args.oidc_jwks_cache_seconds,
        clock_skew_seconds=args.oidc_clock_skew_seconds,
        http_timeout_seconds=args.oidc_http_timeout_seconds,
        disable_pkce=args.oidc_disable_pkce,
        disable_nonce=args.oidc_disable_nonce,
        disable_state=args.oidc_disable_state,
        require_https=args.oidc_require_https,
        allow_http_localhost=args.oidc_allow_http_localhost,
        audiences=tuple(args.oidc_audience),
        required_claims=tuple(args.oidc_required_claim),
        username_claim=args.oidc_username_claim,
        email_claim=args.oidc_email_claim,
        name_claim=args.oidc_name_claim,
        subject_claim=args.oidc_subject_claim,
        token_auth_method=args.oidc_token_auth_method,
    )


def _open_repository(args: argparse.Namespace, paths):
    if args.access_backend == "postgresql":
        return PostgresAccessControlRepository(_postgres_dsn(args))
    return SqliteAccessControlRepository(paths.access_db)


def _open_science(args: argparse.Namespace, paths):
    if args.science_backend == "postgresql":
        return PostgresScienceRepository(_postgres_dsn(args))
    from natureai_next.infrastructure.database.science import SqliteScienceRepository

    return SqliteScienceRepository(paths.science_db)


def _open_media(args: argparse.Namespace, paths):
    if args.media_metadata_backend == "postgresql":
        return PostgresMediaMetadataRepository(_postgres_dsn(args))
    from natureai_next.infrastructure.database.media import SqliteMediaMetadataRepository

    return SqliteMediaMetadataRepository(paths.media_db)


def _open_jobs(args: argparse.Namespace, paths):
    if args.job_backend == "postgresql":
        return PostgresServerJobStore(_postgres_dsn(args))
    return ServerJobStore(paths.jobs_db)


def _open_exports(args: argparse.Namespace, paths):
    if args.export_metadata_backend == "postgresql":
        return PostgresExportMetadataRepository(_postgres_dsn(args))
    from natureai_next.infrastructure.database.exports import SqliteExportMetadataRepository

    return SqliteExportMetadataRepository(paths.exports_db)


def _open_governance(args: argparse.Namespace, paths):
    if args.governance_backend == "postgresql":
        from natureai_next.server.postgres_governance import PostgresGovernanceRepository

        return PostgresGovernanceRepository(_postgres_dsn(args))
    from natureai_next.infrastructure.database.governance import SqliteGovernanceRepository

    return SqliteGovernanceRepository(paths.governance_db)


def _open_search(args: argparse.Namespace, paths):
    if args.search_backend == "opensearch":
        return OpenSearchProjection(_required(args.opensearch_url, "--opensearch-url"))
    return SearchProjection(paths.search_db)


def _open_object_store(args: argparse.Namespace, paths):
    if args.media_object_store == "s3":
        return S3ObjectStore(
            endpoint_url=_required(args.s3_endpoint_url, "--s3-endpoint-url"),
            bucket=_required(args.s3_bucket, "--s3-bucket"),
            region=args.s3_region,
            access_key_id=_required(args.s3_access_key_id, "--s3-access-key-id"),
            secret_access_key=_required(
                args.s3_secret_access_key, "--s3-secret-access-key"
            ),
        )
    return None


def _bootstrap_administrator(args, authentication, administration) -> None:
    if args.bootstrap_admin_disable:
        return
    username = args.bootstrap_admin_username.strip()
    if not username:
        return
    password = args.bootstrap_admin_password
    if args.bootstrap_admin_password_prompt:
        password = getpass.getpass("Bootstrap administrator password: ")
    elif args.bootstrap_admin_password_generate:
        password = authentication.generate_password(
            length=args.bootstrap_admin_password_length,
            alphabet=args.bootstrap_admin_password_alphabet or None,
        )
    elif args.bootstrap_admin_password_file:
        password = Path(args.bootstrap_admin_password_file).read_text(encoding="utf-8").strip()
    if not password:
        raise SystemExit("bootstrap administrator password is required")
    require_change = not args.bootstrap_admin_no_require_password_change
    if args.bootstrap_admin_require_password_change:
        require_change = True
    identity = administration.bootstrap_administrator(
        username=username,
        password=password,
        organization_id=args.bootstrap_admin_organization,
        display_name=args.bootstrap_admin_display_name,
        email=args.bootstrap_admin_email,
        require_password_change=require_change,
        force=args.bootstrap_admin_force,
    )
    if args.bootstrap_admin_print_credentials:
        print(json.dumps({"username": username, "password": password, "identity_id": identity.id}))
    if args.bootstrap_admin_output_file:
        output = Path(args.bootstrap_admin_output_file)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps({"username": username, "password": password, "identity_id": identity.id}) + "\n",
            encoding="utf-8",
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = resolve_application_paths(args.data_dir)
    repository = _open_repository(args, paths)
    science = _open_science(args, paths)
    media = _open_media(args, paths)
    jobs = _open_jobs(args, paths)
    exports = _open_exports(args, paths)
    governance = _open_governance(args, paths)
    search = _open_search(args, paths)
    object_store = _open_object_store(args, paths)
    authentication = AuthenticationService(repository)
    administration = AccessAdministrationService(repository)
    _bootstrap_administrator(args, authentication, administration)
    oidc_configuration = _oidc_configuration(args)
    oidc = OidcAuthenticationService(oidc_configuration, repository) if oidc_configuration else None
    device_authorization = DeviceAuthorizationService(repository, oidc_configuration) if oidc_configuration and args.oidc_device_flow else None
    web_root = paths.web_root
    staged_ingestion = StagedIngestionService(paths.staging_root, science, media)
    readiness_checks = {
        "access": repository.ready,
        "science": science.ready,
        "media-metadata": media.ready,
        "jobs": jobs.ready,
        "export-metadata": exports.ready,
        "governance": governance.ready,
        "search": search.ready,
    }
    if object_store is not None:
        readiness_checks["object-storage"] = object_store.ready
    if isinstance(search, OpenSearchProjection):
        readiness_checks["search"] = search.ready
    readiness = (
        ReadinessMonitor(readiness_checks, cache_seconds=2)
        if readiness_checks else None
    )
    application = FieldoraApi(
        authentication,
        PolicyDecisionService(repository),
        science,
        web_root,
        media,
        device_authorization,
        oidc,
        repository,
        search,
        jobs,
        exports,
        governance,
        readiness,
        staged_ingestion,
        runtime_profile={
            "access": args.access_backend,
            "science": args.science_backend,
            "media_metadata": args.media_metadata_backend,
            "jobs": args.job_backend,
            "export_metadata": args.export_metadata_backend,
            "governance": args.governance_backend,
            "search": args.search_backend,
            "object_storage": args.media_object_store,
        },
    )
    try:
        tls_enabled = validate_listener_security(
            args.host, args.tls_certificate, args.tls_private_key,
            allow_insecure_http=args.allow_insecure_http,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not 0 <= args.drain_seconds <= 300:
        raise SystemExit("--drain-seconds must be between 0 and 300")
    scheme = "https" if tls_enabled else "http"
    print(f"Fieldora server listening on {scheme}://{args.host}:{args.port}")
    shutdown = ShutdownCoordinator(
        () if readiness is None else (readiness.begin_draining,)
    )
    with shutdown.installed():
        serve(
            application,
            args.host,
            args.port,
            tls_certificate=args.tls_certificate,
            tls_private_key=args.tls_private_key,
            shutdown_coordinator=shutdown,
            shutdown_grace_seconds=args.drain_seconds,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())