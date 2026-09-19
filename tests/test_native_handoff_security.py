from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from natureai_next.application.native_handoff import HelperLaunch, augment_request, launch_helper


def test_augment_request_carries_explicit_config_root(tmp_path: Path) -> None:
    request = tmp_path / "pending-update.json"
    request.write_text('{"format":"natureai-next.pending-update","format_version":2}\n', encoding="utf-8")
    config_root = tmp_path / "admin-root"

    augment_request(request, parent_pid=42, library_path=tmp_path / "library", config_root=config_root)

    payload = json.loads(request.read_text(encoding="utf-8"))
    assert payload["parent_pid"] == 42
    assert payload["config_root"] == str(config_root.resolve())


def test_launch_helper_passes_explicit_updater_roots(tmp_path: Path) -> None:
    launch = HelperLaunch(
        module="natureai_next.bootstrap.native_updater",
        request_path=tmp_path / "pending-update.json",
        parent_pid=42,
        library_path=tmp_path / "library",
        config_root=tmp_path / "admin-root",
        trust_anchor_path=tmp_path / "admin-root" / "update-trust-anchors.json",
    )

    with patch("natureai_next.application.native_handoff.subprocess.Popen") as popen:
        launch_helper(launch)

    command = popen.call_args.args[0]
    assert command[command.index("--config-root") + 1] == str(launch.config_root.resolve())
    assert command[command.index("--trust-anchor") + 1] == str(launch.trust_anchor_path.resolve())
