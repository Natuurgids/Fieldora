from __future__ import annotations

import re
from pathlib import Path


WORKFLOWS = Path(".github/workflows")
CONTAINER_KEY = re.compile(r"^\s+container:\s*(?:\S.*)?$", re.MULTILINE)
EXACT_HEAD_CHECK = 'git rev-parse HEAD'
SAFE_DIRECTORY = 'git config --global --add safe.directory "$GITHUB_WORKSPACE"'


def test_container_exact_head_verification_marks_workspace_safe_first() -> None:
    """Keep strict PR-head verification usable inside job containers.

    actions/checkout configures safe.directory using its temporary HOME. A later
    shell step running inside a job-level container can therefore fail Git's
    dubious-ownership protection before rev-parse executes. Container workflows
    that independently verify the checked-out HEAD must mark only the Actions
    workspace as safe before asking Git for HEAD; the exact-SHA comparison stays
    mandatory and unchanged.
    """

    audited: list[str] = []
    violations: list[str] = []

    for workflow in sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml"))):
        text = workflow.read_text(encoding="utf-8")
        if not CONTAINER_KEY.search(text) or EXACT_HEAD_CHECK not in text:
            continue

        audited.append(workflow.name)
        safe_index = text.find(SAFE_DIRECTORY)
        verify_index = text.find(EXACT_HEAD_CHECK)
        if safe_index < 0 or safe_index > verify_index:
            violations.append(workflow.as_posix())

    assert audited, "Expected at least one container exact-head certification workflow to audit."
    assert not violations, (
        "Job-container workflows must configure only $GITHUB_WORKSPACE as a Git "
        "safe.directory before strict git rev-parse HEAD verification: "
        + ", ".join(violations)
    )
