"""CLI for the offline-first Fieldora linked-storage service agent."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Sequence

from natureai_next.server.lifecycle import ShutdownCoordinator
from natureai_next.server.storage_service_agent import LinkedStorageAgent, StorageAgentConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldora-storage-service")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--service-id", required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--storage-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--root-alias", required=True)
    parser.add_argument("--root-path", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--certificate", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--ca-certificate", required=True, type=Path)
    parser.add_argument("--project", default="")
    parser.add_argument("--maximum-preview-edge", type=int, default=512)
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalogue = subparsers.add_parser("catalogue")
    catalogue.add_argument("--batch-size", type=int, default=250)

    preview = subparsers.add_parser("previews-once")
    preview.add_argument("--worker-id", required=True)
    preview.add_argument("--limit", type=int, default=20)
    preview.add_argument("--lease-seconds", type=int, default=120)

    run = subparsers.add_parser("run")
    run.add_argument("--worker-id", required=True)
    run.add_argument("--batch-size", type=int, default=250)
    run.add_argument("--preview-limit", type=int, default=20)
    run.add_argument("--lease-seconds", type=int, default=120)
    run.add_argument("--poll-seconds", type=float, default=2.0)
    run.add_argument("--rescan-seconds", type=float, default=3600.0)
    return parser


def _agent(args: argparse.Namespace) -> LinkedStorageAgent:
    config = StorageAgentConfig(
        endpoint=args.endpoint,
        service_id=args.service_id,
        organization_id=args.organization,
        storage_id=args.storage_id,
        display_name=args.display_name,
        root_alias=args.root_alias,
        root_path=args.root_path,
        state_root=args.state_root,
        certificate=args.certificate,
        private_key=args.private_key,
        ca_certificate=args.ca_certificate,
        project_id=args.project,
        maximum_preview_edge=args.maximum_preview_edge,
    )
    return LinkedStorageAgent(config)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    agent = _agent(args)
    if args.command == "catalogue":
        state = agent.catalogue(batch_size=args.batch_size)
        print(
            f"{state.storage_id}: scan {state.scan_id} {state.state}; "
            f"sequence {state.sequence}"
        )
        return 0
    if args.command == "previews-once":
        count = agent.process_preview_leases(
            worker_id=args.worker_id,
            limit=args.limit,
            lease_seconds=args.lease_seconds,
        )
        print(f"Processed {count} preview lease(s)")
        return 0

    poll = max(0.1, min(float(args.poll_seconds), 60.0))
    rescan = max(60.0, min(float(args.rescan_seconds), 7 * 24 * 3600.0))
    agent.catalogue(batch_size=args.batch_size)
    next_scan = time.monotonic() + rescan
    shutdown = ShutdownCoordinator()
    processed = 0
    with shutdown.installed():
        while not shutdown.requested:
            processed += agent.process_preview_leases(
                worker_id=args.worker_id,
                limit=args.preview_limit,
                lease_seconds=args.lease_seconds,
            )
            now = time.monotonic()
            if now >= next_scan:
                agent.catalogue(batch_size=args.batch_size)
                next_scan = now + rescan
            shutdown.wait(poll)
    print(f"Storage service stopped; processed {processed} preview lease(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
