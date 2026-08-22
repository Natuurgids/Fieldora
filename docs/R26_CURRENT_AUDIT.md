# R26 current audit

## Resolved in this build

- Windows startup crash after local login caused by a function-local `import os` shadowing the module import.
- Provider-specific MCP tool display is cleared whenever the AI provider changes, preventing stale capability presentation.

## Verification

The complete packaged test suite was executed in four deterministic rounds:

- 149 passed, 1 skipped
- 171 passed
- 176 passed, 1 skipped
- 147 passed

Total: **643 passed, 2 skipped, 0 failed**.

The two skipped tests require PySide6, which is not installed in the Linux packaging environment. All non-graphical tests passed.
