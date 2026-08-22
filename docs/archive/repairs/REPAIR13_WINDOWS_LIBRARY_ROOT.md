# Build 26 Repair 13 — Windows library drive root

When a user selects a library such as `D:\Aperture-Library-V4`, PowerShell resolves its parent to
the existing drive root `D:\`. Some Windows PowerShell/.NET combinations reject an unconditional
`New-Item -Force` invocation for that root with “The path is not of a legal form.”

Repair 13 resolves the parent once and creates it only when it does not already exist as a
container. The library creation command remains responsible for creating and validating the
selected library directory.
