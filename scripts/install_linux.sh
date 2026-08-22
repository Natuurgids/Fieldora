#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${APERTURE_DATA_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/FieldoraV5}"
LIBRARY_ROOT="${APERTURE_LIBRARY_ROOT:-$HOME/Fieldora-Library-V5}"
INSTALL_ROOT="${APERTURE_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/FieldoraV5/runtime}"
VENV="$INSTALL_ROOT/venv"
BIN_ROOT="${XDG_BIN_HOME:-$HOME/.local/bin}"
APPLICATIONS_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
SKIP_GUI_SMOKE=0

usage() {
  cat <<USAGE
Usage: ./Install\ Aperture\ Linux.sh [options]
  --data-root PATH       Mutable application data (default: $DATA_ROOT)
  --library PATH         First Aperture library (default: $LIBRARY_ROOT)
  --install-root PATH    Managed Python runtime (default: $INSTALL_ROOT)
  --python PATH          Python 3.11 executable (default: $PYTHON_BIN)
  --skip-gui-smoke       Skip the real off-screen Qt startup acceptance test
USAGE
}
while (($#)); do
  case "$1" in
    --data-root) DATA_ROOT="$2"; shift 2;;
    --library) LIBRARY_ROOT="$2"; shift 2;;
    --install-root) INSTALL_ROOT="$2"; VENV="$2/venv"; shift 2;;
    --python) PYTHON_BIN="$2"; shift 2;;
    --skip-gui-smoke) SKIP_GUI_SMOKE=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2;;
  esac
done

command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "Python 3.11 is required. Install python3.11 and python3.11-venv." >&2; exit 2; }
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info[:2] != (3, 11):
    raise SystemExit(f"Python 3.11 required, found {sys.version.split()[0]}")
PY

python_preflight=("$PYTHON_BIN" -B "$REPOSITORY_ROOT/scripts/deployment_preflight.py" --release-root "$REPOSITORY_ROOT")
"${python_preflight[@]}"

mkdir -p "$DATA_ROOT" "$INSTALL_ROOT" "$BIN_ROOT" "$APPLICATIONS_ROOT"
case "$(realpath -m -- "$INSTALL_ROOT")" in
  /|"$HOME") echo "Unsafe install root: $INSTALL_ROOT" >&2; exit 2;;
esac
rm -rf "$VENV.new"
"$PYTHON_BIN" -m venv "$VENV.new"
"$VENV.new/bin/python" -m pip install --upgrade \
  -c "$REPOSITORY_ROOT/requirements/constraints-py311.txt" setuptools wheel
"$VENV.new/bin/python" -m pip install -r "$REPOSITORY_ROOT/requirements/gui.txt"
"$VENV.new/bin/python" -m pip install "$REPOSITORY_ROOT"
"$VENV.new/bin/python" "$REPOSITORY_ROOT/scripts/verify_install.py" --require-gui

mkdir -p "$DATA_ROOT/config" "$DATA_ROOT/cache" "$DATA_ROOT/logs"
cat > "$DATA_ROOT/config/installation.json.new" <<JSON
{
  "schema_version": 1,
  "version": "$(cat "$REPOSITORY_ROOT/VERSION")",
  "installation_root": "$REPOSITORY_ROOT",
  "data_root": "$DATA_ROOT",
  "library_root": "$LIBRARY_ROOT",
  "runtime": "$VENV"
}
JSON

cat > "$BIN_ROOT/fieldora.new" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
export APERTURE_DATA_ROOT=$(printf '%q' "$DATA_ROOT")
export NATUREAI_DATA_ROOT=$(printf '%q' "$DATA_ROOT")
export XDG_CACHE_HOME=$(printf '%q' "$DATA_ROOT/cache")
exec $(printf '%q' "$VENV/bin/fieldora") --library $(printf '%q' "$LIBRARY_ROOT") "\$@"
LAUNCHER
chmod +x "$BIN_ROOT/fieldora.new"

mkdir -p "$INSTALL_ROOT/share"
cp "$REPOSITORY_ROOT/resources/fieldora.ico" "$INSTALL_ROOT/share/fieldora.ico.new"
cat > "$APPLICATIONS_ROOT/fieldora.desktop.new" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Fieldora
Comment=Offline biodiversity research and scientific project workspace
Exec=$BIN_ROOT/fieldora
Icon=$INSTALL_ROOT/share/fieldora.ico
Terminal=false
Categories=Graphics;Photography;Science;
StartupNotify=true
DESKTOP
chmod 0644 "$APPLICATIONS_ROOT/fieldora.desktop.new"

# Create and validate the exact first-run library through the installed package.
export APERTURE_DATA_ROOT="$DATA_ROOT" NATUREAI_DATA_ROOT="$DATA_ROOT" XDG_CACHE_HOME="$DATA_ROOT/cache"
"$VENV.new/bin/python" - <<PY
from pathlib import Path
from natureai_next.application.library_service import LibraryService
from natureai_next.infrastructure.diagnostics.system_services import SystemClock, SystemUuidGenerator
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend
root=Path(r'''$LIBRARY_ROOT''')
service=LibraryService(SystemClock(),SystemUuidGenerator(),backend_factory=lambda c,i,s:SqliteLibraryLifecycleBackend(c,i,s))
with service.open_or_create_clean(root) as opened:
    con=opened.connection_factory.connect(read_only=True)
    try: con.execute('SELECT 1 FROM observations LIMIT 0')
    finally: con.close()
PY

if [[ "$SKIP_GUI_SMOKE" -eq 0 ]]; then
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
  export APERTURE_SMOKE_TEST_SECONDS=2
  timeout 45 "$VENV.new/bin/aperture" --library "$LIBRARY_ROOT" --no-update-check
fi

# Publish only after package, schema, reopen, and GUI checks pass.  Console
# scripts embed the absolute staging interpreter path, so repair those shebangs
# as part of the swap before exposing the final launcher.
rm -rf "$VENV.old"
if [[ -d "$VENV" ]]; then mv "$VENV" "$VENV.old"; fi
mv "$VENV.new" "$VENV"
"$VENV/bin/python" - "$VENV.new" "$VENV" <<'PY'
from pathlib import Path
import sys

old = sys.argv[1].encode()
new = sys.argv[2].encode()
for path in (Path(sys.argv[2]) / "bin").iterdir():
    if not path.is_file():
        continue
    data = path.read_bytes()
    if data.startswith(b"#!") and old in data.splitlines()[0]:
        path.write_bytes(data.replace(old, new, 1))
PY
mv "$DATA_ROOT/config/installation.json.new" "$DATA_ROOT/config/installation.json"
mv "$BIN_ROOT/fieldora.new" "$BIN_ROOT/fieldora"
mv "$APPLICATIONS_ROOT/fieldora.desktop.new" "$APPLICATIONS_ROOT/fieldora.desktop"
mv "$INSTALL_ROOT/share/fieldora.ico.new" "$INSTALL_ROOT/share/fieldora.ico"
cp "$REPOSITORY_ROOT/scripts/uninstall_linux.sh" "$INSTALL_ROOT/uninstall_linux.sh"
chmod +x "$INSTALL_ROOT/uninstall_linux.sh"
cat > "$BIN_ROOT/fieldora-uninstall.new" <<UNINSTALLER
#!/usr/bin/env bash
exec $(printf '%q' "$INSTALL_ROOT/uninstall_linux.sh") --data-root $(printf '%q' "$DATA_ROOT") --install-root $(printf '%q' "$INSTALL_ROOT") "\$@"
UNINSTALLER
chmod +x "$BIN_ROOT/fieldora-uninstall.new"
mv "$BIN_ROOT/fieldora-uninstall.new" "$BIN_ROOT/fieldora-uninstall"
rm -rf "$VENV.old"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPLICATIONS_ROOT" >/dev/null 2>&1 || true
echo "Fieldora V5 installed successfully."
echo "Launcher: $BIN_ROOT/fieldora"
echo "Uninstaller: $BIN_ROOT/fieldora-uninstall"
echo "Library:  $LIBRARY_ROOT"
