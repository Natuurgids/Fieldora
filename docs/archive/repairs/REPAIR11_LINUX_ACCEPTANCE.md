# Build 26 Repair 11 — Linux acceptance closure

Repair 11 is the first package created after the Build 26 Linux acceptance cycle completed.

The accepted Linux path covers a fresh Python 3.11 environment, installed-package verification,
clean-library creation, manifest/database identity equality, the complete schema (including
`observations`), a real PySide6 launch on Qt's Linux off-screen display platform, all registered
workspaces, ordinary close, worker-thread cleanup, lock release, same-library relaunch, in-place
repair, transactional rollback, and preservation of user library data.

The Linux installer stages its replacement runtime and generated launch files under `.new` names.
It publishes them only after package, schema, reopen, and Qt startup gates succeed. A failure before
publication leaves the installed runtime and selected user library intact.

The Windows archive is produced from the same frozen source inventory. Its source-level and
cross-platform contract checks run on Linux; native Windows execution is not claimed by this
acceptance record.
