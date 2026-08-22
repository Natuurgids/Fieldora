#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${APERTURE_DATA_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/FieldoraV5}"
INSTALL_ROOT="${APERTURE_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/FieldoraV5/runtime}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
MODE=""
ASSUME_YES=0

usage() {
  cat <<USAGE
Usage: fieldora-uninstall [options]
  --package-only       Remove the Fieldora package and launchers; retain the runtime
  --remove-runtime     Remove Fieldora and its complete managed Python runtime
  --full-reset         Also remove Fieldora configuration, caches, logs and install reports
  --data-root PATH     Fieldora V5 mutable application data
  --install-root PATH  Fieldora V5 managed runtime
  --yes                Do not ask for confirmation

Research libraries, photographs, project exports and backups are never removed.
USAGE
}

while (($#)); do
  case "$1" in
    --package-only) MODE="package"; shift;;
    --remove-runtime) MODE="runtime"; shift;;
    --full-reset) MODE="reset"; shift;;
    --data-root) DATA_ROOT="$2"; shift 2;;
    --install-root) INSTALL_ROOT="$2"; shift 2;;
    --yes|-y) ASSUME_YES=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "Fieldora V5 uninstaller"
  echo "1. Remove Fieldora package and launchers only"
  echo "2. Remove Fieldora and the complete managed runtime"
  echo "3. Full reset: runtime, application configuration, caches, logs and reports"
  echo "4. Cancel"
  read -r -p "Choose 1, 2, 3, or 4: " answer
  case "$answer" in
    1) MODE="package";; 2) MODE="runtime";; 3) MODE="reset";;
    4) echo "Uninstall cancelled."; exit 0;;
    *) echo "Invalid choice." >&2; exit 2;;
  esac
fi

safe_path() {
  local value xdg_root
  value="$(realpath -m -- "$1")"
  xdg_root="$(realpath -m -- "${XDG_DATA_HOME:-$HOME/.local/share}")"
  [[ -n "$value" && "$value" != / && "$value" != "$HOME" && "$value" != "$xdg_root" ]] || {
    echo "Refusing unsafe cleanup path: $1" >&2
    exit 2
  }
  printf '%s' "$value"
}

DATA_ROOT="$(safe_path "$DATA_ROOT")"
INSTALL_ROOT="$(safe_path "$INSTALL_ROOT")"
VENV="$INSTALL_ROOT/venv"

if [[ "$ASSUME_YES" -eq 0 ]]; then
  read -r -p "Continue with '$MODE' uninstall? Libraries and research data are preserved. [y/N]: " answer
  case "${answer:-}" in y|Y|yes|YES) ;; *) echo "Uninstall cancelled."; exit 0;; esac
fi

if [[ "$MODE" == package && -x "$VENV/bin/python" ]]; then
  "$VENV/bin/python" -m pip uninstall --yes natureai-next || true
fi

rm -f -- \
  "$BIN_DIR/fieldora" "$BIN_DIR/fieldora-uninstall" \
  "$BIN_DIR/fieldora-maintenance-center" "$BIN_DIR/fieldora-manuals" \
  "$BIN_DIR/aperture" "$BIN_DIR/aperture-maintenance-center" \
  "$APPLICATIONS_DIR/fieldora.desktop" "$APPLICATIONS_DIR/aperture.desktop"

if [[ "$MODE" == runtime || "$MODE" == reset ]]; then
  rm -rf -- "$INSTALL_ROOT"
else
  rm -f -- "$INSTALL_ROOT/uninstall_linux.sh" "$INSTALL_ROOT/share/fieldora.ico"
  rmdir "$INSTALL_ROOT/share" "$INSTALL_ROOT" 2>/dev/null || true
fi

# Clean runtime paths used by pre-V5 Linux packages without touching their data roots.
LEGACY_APP_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/Aperture"
rm -rf -- "$LEGACY_APP_HOME/runtime" "$LEGACY_APP_HOME/application" "$LEGACY_APP_HOME/environment"

rm -f -- "$DATA_ROOT/config/installation.json"
if [[ "$MODE" == reset ]]; then
  rm -rf -- "$DATA_ROOT"
fi

command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true

echo "Fieldora V5 application components removed."
echo "Research libraries, photographs, projects, backups and exports were preserved."
