# Platform parity

Windows and Linux desktop use the same Qt workspace registry and shared `natureai_next` domain/application services. The server exposes the authoritative feature registry through `/api/v1/platform/features` and `/api/v1/platform/parity`, and displays it in **Platform parity**.

The registry deliberately reports server gaps as `partial` or `not_implemented`; those capabilities are not certified until equivalent server UI/API workflows and evidence exist. Run `python scripts/verify_platform_parity.py` as a desktop parity release gate.
