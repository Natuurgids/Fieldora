"""Run the deterministic local validation sequence used by CI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


def _run(command: Sequence[str], *, required: bool = True) -> int:
    executable = command[0]
    if executable != sys.executable and shutil.which(executable) is None:
        message = f"validation tool is not installed: {executable}"
        if required:
            print(message, file=sys.stderr)
            return 127
        print(f"SKIP: {message}")
        return 0
    env = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(command, check=False, env=env)
    return completed.returncode


def main() -> int:
    commands = (
        ((sys.executable, "-m", "compileall", "-q", "src", "tests"), True),
        (("ruff", "check", "."), True),
        (("ruff", "format", "--check", "."), True),
        (("mypy",), True),
        (("lint-imports",), True),
        (("pytest",), True),
    )
    for command, required in commands:
        return_code = _run(command, required=required)
        if return_code != 0:
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
