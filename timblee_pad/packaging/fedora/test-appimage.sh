#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
HOST_ARCH_RAW="$(uname -m)"
case "$HOST_ARCH_RAW" in
    x86_64) HOST_ARCH="x86_64" ;;
    aarch64|arm64) HOST_ARCH="aarch64" ;;
    *) echo "Unsupported architecture: $HOST_ARCH_RAW" >&2; exit 2 ;;
esac
ARCH="${ARCH:-$HOST_ARCH}"
IMAGE="${1:-$ROOT/dist/Timblee-Pad-0.2.3-${ARCH}.AppImage}"
[[ -x "$IMAGE" ]] || { echo "AppImage not found or not executable: $IMAGE" >&2; exit 2; }
SMOKE_HOME="$(mktemp -d "${TMPDIR:-/tmp}/timbleepad-appimage-test.XXXXXX")"
trap 'rm -rf "$SMOKE_HOME"' EXIT
mkdir -p "$SMOKE_HOME/.config" "$SMOKE_HOME/.cache" "$SMOKE_HOME/.local/share"
run_gui_probe() {
    timeout 30s env \
        HOME="$SMOKE_HOME" XDG_CONFIG_HOME="$SMOKE_HOME/.config" \
        XDG_CACHE_HOME="$SMOKE_HOME/.cache" XDG_DATA_HOME="$SMOKE_HOME/.local/share" \
        QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
        "$IMAGE" --appimage-extract-and-run "$@" --timbleepad-smoke-test
}
run_gui_probe
run_gui_probe --appimage-theme=dark
run_gui_probe --appimage-theme=light
run_gui_probe --appimage-theme=system
"$IMAGE" --appimage-extract-and-run --version
"$IMAGE" --appimage-extract-and-run --appimage-theme=dark --version
"$IMAGE" --appimage-extract-and-run --appimage-theme=light --version
"$IMAGE" --appimage-extract-and-run --appimage-theme=system --version
if [[ -f "$IMAGE.sha256" ]]; then
    (cd "$(dirname -- "$IMAGE")" && sha256sum -c "$(basename -- "$IMAGE.sha256")")
fi
printf 'AppImage default/dark/light/system GUI + version smoke matrix passed.\n'
