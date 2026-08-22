# Build 26 Repair 12 — Windows Conda channel policy

Native Windows installation of Repair 11 exposed a Conda 26 behavior: `conda env remove` evaluated
the configured Anaconda default channels and stopped for unaccepted Terms of Service before
removing the Aperture environment.

Aperture obtains its Conda packages from conda-forge. Repair 12 therefore removes an existing
environment with:

```text
conda remove --all --yes --name natureai-next --override-channels --channel conda-forge
```

Environment creation and package installation already use the same explicit channel override.
The installer neither silently accepts third-party terms nor asks users to accept terms for
repositories it does not consume.

The correction is source-tested on Linux and the complete Linux acceptance cycle was repeated
before packaging. Native Windows execution of the replacement remains to be confirmed by the
Windows field installation.
