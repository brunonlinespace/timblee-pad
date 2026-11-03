#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

# Timblee Pad AppImage builder aligned with the Pad-family portable tree and
# the latest Ricopad/Portapad packaging hardening. It never invokes sudo, dnf,
# pkexec, su, or another host package installer/elevation command.

APP_NAME="Timblee Pad"
APP_ID="timbleepad"
SUITE_COMPONENT_ID="timblee-pad"
APP_VERSION="0.2.3"
DESKTOP_ID="io.github.brunonlinespace.timbleepad"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd -P)"
PROGRAM_ROOT="${PROJECT_ROOT}/timblee_pad"
COMPONENT_MANIFEST="${PROJECT_ROOT}/suite-pythoine-component.json"
ROOT_README="${PROJECT_ROOT}/README.md"
IDENTITY_FILE="${PROGRAM_ROOT}/__init__.py"
SOURCE_FILE="${PROGRAM_ROOT}/app.py"
ASSET_DIR="${PROGRAM_ROOT}/assets/icons"
APPIMAGE_PAYLOAD="${PROGRAM_ROOT}/packaging/appimage"
PYINSTALLER_SPEC="${PROGRAM_ROOT}/packaging/pyinstaller/timbleepad.spec"
BUILD_REQUIREMENTS="${PROGRAM_ROOT}/packaging/pyinstaller/build-requirements.txt"
QA_RUNNER="${PROGRAM_ROOT}/qa/run-qa.sh"
SOURCE_MANIFEST="${PROGRAM_ROOT}/SOURCE_MANIFEST.sha256"

HOST_ARCH_RAW="$(uname -m)"
case "$HOST_ARCH_RAW" in
    x86_64) HOST_ARCH="x86_64" ;;
    aarch64|arm64) HOST_ARCH="aarch64" ;;
    *) printf 'Error: unsupported build architecture: %s\n' "$HOST_ARCH_RAW" >&2; exit 2 ;;
esac
ARCH="${ARCH:-$HOST_ARCH}"

FEDORA_RELEASE="unknown"
HOST_NAME="unknown Linux"
OS_ID="unknown"
if [[ -r /etc/os-release ]]; then
    mapfile -d '' -t OS_RELEASE_VALUES < <(
        set +u
        # shellcheck disable=SC1091
        source /etc/os-release
        printf '%s\0%s\0%s\0' "${ID:-unknown}" "${VERSION_ID:-unknown}" "${PRETTY_NAME:-unknown Linux}"
    )
    OS_ID="${OS_RELEASE_VALUES[0]:-unknown}"
    FEDORA_RELEASE="${OS_RELEASE_VALUES[1]:-unknown}"
    HOST_NAME="${OS_RELEASE_VALUES[2]:-unknown Linux}"
fi

BUILD_ROOT="${BUILD_ROOT:-${PROGRAM_ROOT}/build/appimage-fedora${FEDORA_RELEASE}-${ARCH}}"
VENV="${BUILD_ROOT}/venv"
PYI_WORK="${BUILD_ROOT}/pyinstaller-work"
PYI_DIST="${BUILD_ROOT}/pyinstaller-dist"
APPDIR="${BUILD_ROOT}/TimbleePad.AppDir"
SMOKE_HOME="${BUILD_ROOT}/smoke-home"
DIST_DIR="${OUTPUT_DIR:-${PROGRAM_ROOT}/dist}"
CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/timbleepad-appimage-tools"
APPIMAGE="${DIST_DIR}/Timblee-Pad-${APP_VERSION}-${ARCH}.AppImage"
SHA_FILE="${APPIMAGE}.sha256"
BUILD_INFO="${DIST_DIR}/Timblee-Pad-${APP_VERSION}-${ARCH}.build-info.txt"
PYTHON_LOCK="${DIST_DIR}/Timblee-Pad-${APP_VERSION}-${ARCH}.build-python-lock.txt"
APPIMAGETOOL_RESOLVED=""
MAX_TOOL_BYTES=$((200 * 1024 * 1024))

export PYTHONDONTWRITEBYTECODE=1

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
require_file() { [[ -f "$1" ]] || die "Missing file: $1"; }

validate_build_root() {
    local allowed_root resolved_root
    allowed_root="$(readlink -m -- "${PROGRAM_ROOT}/build")"
    resolved_root="$(readlink -m -- "$BUILD_ROOT")"
    [[ "$resolved_root" != "$allowed_root" ]] \
        || die "BUILD_ROOT must be a child directory beneath ${allowed_root}; refusing to remove the build root itself."
    case "$resolved_root" in
        "$allowed_root"/*) ;;
        *) die "Unsafe BUILD_ROOT outside ${allowed_root}: ${resolved_root}" ;;
    esac
}

clean_source_python_caches() {
    while IFS= read -r -d '' cache_dir; do
        rm -rf -- "$cache_dir"
    done < <(
        find "$PROJECT_ROOT" \
            \( -path "$PROJECT_ROOT/.git" \
               -o -path "$PROJECT_ROOT/.venv" \
               -o -path "$PROJECT_ROOT/venv" \
               -o -path "$PROGRAM_ROOT/build" \
               -o -path "$PROGRAM_ROOT/dist" \) -prune \
            -o -type d -name "__pycache__" -print0
    )
    while IFS= read -r -d '' bytecode_file; do
        rm -f -- "$bytecode_file"
    done < <(
        find "$PROJECT_ROOT" \
            \( -path "$PROJECT_ROOT/.git" \
               -o -path "$PROJECT_ROOT/.venv" \
               -o -path "$PROJECT_ROOT/venv" \
               -o -path "$PROGRAM_ROOT/build" \
               -o -path "$PROGRAM_ROOT/dist" \) -prune \
            -o -type f \( -name "*.pyc" -o -name "*.pyo" \) -print0
    )
}

source_tree_sha256() {
    find "$PROJECT_ROOT" \
        \( -path "$PROJECT_ROOT/.git" \
           -o -path "$PROJECT_ROOT/.venv" \
           -o -path "$PROJECT_ROOT/venv" \
           -o -path "$PROGRAM_ROOT/build" \
           -o -path "$PROGRAM_ROOT/dist" \) -prune \
        -o -type f -not -name '*.pyc' -not -name '*.pyo' -print0 \
        | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
}

cleanup() {
    rm -rf "$SMOKE_HOME"
    clean_source_python_caches
}
trap cleanup EXIT

check_non_privileged_policy() {
    if grep -Eq '^[[:space:]]*(sudo|dnf|pkexec|su)([[:space:]]|$)' "$0"; then
        die "Privilege-elevation or host-package-install command detected in builder."
    fi
}

check_host_prerequisites() {
    log "Checking non-privileged host prerequisites"
    local missing=() command_name
    for command_name in python3 bash timeout sha256sum od stat find grep cp ln chmod install mktemp \
        rm mkdir mv tr awk cut date uname readlink sort env wc xargs; do
        command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
    done
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        missing+=("curl-or-wget")
    fi
    if ((${#missing[@]})); then
        die "Missing required host command(s): ${missing[*]}. The builder will not install system packages; provide them and rerun."
    fi
    python3 - <<'PYVENV' >/dev/null 2>&1 || \
        die "This Python cannot create virtual environments. Provide Python with venv/ensurepip support and rerun."
import ensurepip, venv
PYVENV
}

check_inputs() {
    validate_build_root
    if (( EUID == 0 )) && [[ "${TIMBLEEPAD_ALLOW_ROOT_BUILD:-${ALLOW_ROOT_BUILD:-0}}" != "1" ]]; then
        die "Do not run the Timblee Pad AppImage builder with sudo/root."
    fi
    case "$ARCH" in x86_64|aarch64) ;; *) die "Unsupported AppImage architecture: ${ARCH}" ;; esac
    [[ "$ARCH" == "$HOST_ARCH" ]] || die "Requested ${ARCH}, but host is ${HOST_ARCH_RAW}; cross-building is unsupported."
    if [[ "$OS_ID" != "fedora" || ! "$FEDORA_RELEASE" =~ ^(43|44)$ ]]; then
        if [[ "${TIMBLEEPAD_ALLOW_UNSUPPORTED_HOST:-0}" != "1" ]]; then
            die "Validated for Fedora 43/44. Detected ${HOST_NAME}. Set TIMBLEEPAD_ALLOW_UNSUPPORTED_HOST=1 only for intentional testing."
        fi
        printf 'Warning: continuing on unsupported host: %s\n' "$HOST_NAME" >&2
    fi
    for path in \
        "${PROJECT_ROOT}/main.py" "$ROOT_README" "$COMPONENT_MANIFEST" "$IDENTITY_FILE" "$SOURCE_FILE" "$BUILD_REQUIREMENTS" "$QA_RUNNER" "$SOURCE_MANIFEST" "$PYINSTALLER_SPEC" \
        "${PROGRAM_ROOT}/requirements.txt" "${PROGRAM_ROOT}/docs/README.md" "${PROGRAM_ROOT}/docs/RELEASE_NOTES.md" "${PROGRAM_ROOT}/LICENSE" \
        "${ASSET_DIR}/timbleepad.png" "${ASSET_DIR}/timbleepad.svg" \
        "${APPIMAGE_PAYLOAD}/AppRun" "${APPIMAGE_PAYLOAD}/timbleepad.desktop" \
        "${APPIMAGE_PAYLOAD}/timbleepad.svg" "${APPIMAGE_PAYLOAD}/io.github.brunonlinespace.timbleepad.metainfo.xml" \
        "${APPIMAGE_PAYLOAD}/styles/breeze-dark.qss" "${APPIMAGE_PAYLOAD}/styles/breeze-light.qss"; do
        require_file "$path"
    done
    for size in 16 24 32 48 64 128 256 512; do
        require_file "${ASSET_DIR}/timbleepad-${size}.png"
    done
    grep -Fq "APP_NAME = \"${APP_NAME}\"" "$IDENTITY_FILE" || die "Canonical application name mismatch."
    grep -Fq "APP_VERSION = \"${APP_VERSION}\"" "$IDENTITY_FILE" || die "Canonical application version mismatch."

    python3 - "$COMPONENT_MANIFEST" "$SUITE_COMPONENT_ID" "$APP_NAME" "$APP_VERSION" "$DESKTOP_ID" <<'PYCOMPONENT'
import json
from pathlib import Path
import sys
path = Path(sys.argv[1])
expected_id, expected_name, expected_version, expected_desktop = sys.argv[2:]
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Invalid Suite Pythoine component manifest: {exc}")
expected = {
    "id": expected_id,
    "name": expected_name,
    "version": expected_version,
    "component_kind": "editor",
    "desktop_id": expected_desktop,
    "publisher_id": "brunonlinespace",
}
for key, value in expected.items():
    if data.get(key) != value:
        raise SystemExit(f"Suite component manifest mismatch for {key}: {data.get(key)!r} != {value!r}")
if data.get("portable_command") != ["main.py"]:
    raise SystemExit('Suite component manifest must declare portable_command ["main.py"]')
if data.get("extensions") != [".html", ".htm", ".css"]:
    raise SystemExit("Suite component manifest must preserve canonical Suite HTML/HTM/CSS routing")
if data.get("tagline") != "Friendly. Fast. Focused.":
    raise SystemExit("Suite component manifest has the wrong Pad-family tagline")
if data.get("capabilities") != {"routing": True, "open": True, "create": True}:
    raise SystemExit("Suite component manifest has unexpected capabilities")
PYCOMPONENT
}

run_release_qa() {
    log "Running release/static/security QA"
    clean_source_python_caches
    # Invoke nested shell QA through Bash so ZIP/file-manager extraction does not
    # have to preserve the helper's executable bit.
    bash "$QA_RUNNER"
    clean_source_python_caches
}

validate_desktop_entry_basic() {
    local desktop="$1"
    grep -Fqx '[Desktop Entry]' "$desktop" || die "Desktop entry missing [Desktop Entry]: $desktop"
    grep -Eq '^Type=Application$' "$desktop" || die "Desktop entry Type must be Application: $desktop"
    grep -Eq '^Name=Timblee Pad$' "$desktop" || die "Desktop entry Name mismatch: $desktop"
    grep -Eq '^Exec=timbleepad([[:space:]]|$)' "$desktop" || die "Desktop entry Exec mismatch: $desktop"
    grep -Eq '^Icon=timbleepad$' "$desktop" || die "Desktop entry Icon mismatch: $desktop"
    grep -Eq '^MimeType=.*text/html;' "$desktop" || die "Desktop entry HTML MIME missing: $desktop"
    grep -Eq '^MimeType=.*text/css;' "$desktop" || die "Desktop entry CSS MIME missing: $desktop"
    grep -Eq '^MimeType=.*application/xml;' "$desktop" || die "Desktop entry XML MIME missing: $desktop"
}

validate_appstream_basic() {
    local metainfo="$1"
    python3 - "$metainfo" "$APP_VERSION" <<'PYXML'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
path = Path(sys.argv[1])
version = sys.argv[2]
root = ET.parse(path).getroot()
def txt(tag):
    node = root.find(tag)
    return (node.text or "").strip() if node is not None else ""
assert txt("id") == "io.github.brunonlinespace.timbleepad"
assert txt("project_license") == "GPL-3.0-or-later"
media = {(node.text or "").strip() for node in root.findall("./provides/mediatype")}
assert "text/html" in media
assert "text/css" in media
assert "application/xml" in media
assert any(node.attrib.get("version") == version for node in root.findall("./releases/release"))
PYXML
}

prepare_environment() {
    log "Preparing isolated build environment"
    rm -rf "$BUILD_ROOT"
    mkdir -p "$BUILD_ROOT" "$DIST_DIR" "$CACHE_DIR"
    chmod 0700 "$CACHE_DIR"
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip wheel setuptools
    "$VENV/bin/python" -m pip install -r "${PROGRAM_ROOT}/requirements.txt" -r "$BUILD_REQUIREMENTS"
    PYTHONPYCACHEPREFIX="${BUILD_ROOT}/pycache" \
        "$VENV/bin/python" -m compileall -q "${PROJECT_ROOT}/main.py" "$PROGRAM_ROOT"
    "$VENV/bin/python" -m pip check
    "$VENV/bin/python" -m pip freeze --all > "$PYTHON_LOCK"
}

freeze_application() {
    log "Freezing Timblee Pad with PyInstaller"
    "$VENV/bin/python" -m PyInstaller \
        --clean --noconfirm \
        --distpath "$PYI_DIST" \
        --workpath "$PYI_WORK" \
        "$PYINSTALLER_SPEC"
    [[ -x "${PYI_DIST}/timbleepad/timbleepad" ]] || die "PyInstaller executable was not created."
}

assemble_appdir() {
    log "Dynamically assembling AppDir"
    rm -rf "$APPDIR"
    mkdir -p \
        "$APPDIR/usr/bin" \
        "$APPDIR/usr/lib/timbleepad" \
        "$APPDIR/usr/share/applications" \
        "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
        "$APPDIR/usr/share/metainfo" \
        "$APPDIR/usr/share/timbleepad/styles" \
        "$APPDIR/usr/share/doc/timbleepad"

    cp -a "${PYI_DIST}/timbleepad/." "$APPDIR/usr/lib/timbleepad/"
    ln -s ../lib/timbleepad/timbleepad "$APPDIR/usr/bin/timbleepad"
    install -m 0755 "${APPIMAGE_PAYLOAD}/AppRun" "$APPDIR/AppRun"
    install -m 0644 "${APPIMAGE_PAYLOAD}/timbleepad.desktop" "$APPDIR/timbleepad.desktop"
    install -m 0644 "${APPIMAGE_PAYLOAD}/timbleepad.desktop" "$APPDIR/usr/share/applications/timbleepad.desktop"
    install -m 0644 "${APPIMAGE_PAYLOAD}/timbleepad.svg" "$APPDIR/timbleepad.svg"
    install -m 0644 "${APPIMAGE_PAYLOAD}/timbleepad.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/timbleepad.svg"
    for size in 16 24 32 48 64 128 256 512; do
        mkdir -p "$APPDIR/usr/share/icons/hicolor/${size}x${size}/apps"
        install -m 0644 "${ASSET_DIR}/timbleepad-${size}.png" \
            "$APPDIR/usr/share/icons/hicolor/${size}x${size}/apps/timbleepad.png"
    done
    # Create .DirIcon only in generated output so ZIP/file-manager extraction
    # cannot turn a source-tree symlink into manifest/checksum drift.
    ln -s timbleepad.svg "$APPDIR/.DirIcon"

    install -m 0644 "${APPIMAGE_PAYLOAD}/io.github.brunonlinespace.timbleepad.metainfo.xml" \
        "$APPDIR/usr/share/metainfo/io.github.brunonlinespace.timbleepad.metainfo.xml"
    install -m 0644 "${APPIMAGE_PAYLOAD}/styles/breeze-dark.qss" "$APPDIR/usr/share/timbleepad/styles/breeze-dark.qss"
    install -m 0644 "${APPIMAGE_PAYLOAD}/styles/breeze-light.qss" "$APPDIR/usr/share/timbleepad/styles/breeze-light.qss"
    install -m 0644 "${PROGRAM_ROOT}/LICENSE" "$APPDIR/usr/share/doc/timbleepad/LICENSE"
    install -m 0644 "${PROGRAM_ROOT}/docs/README.md" "$APPDIR/usr/share/doc/timbleepad/README.md"
    install -m 0644 "${PROGRAM_ROOT}/docs/RELEASE_NOTES.md" "$APPDIR/usr/share/doc/timbleepad/RELEASE_NOTES.md"

    validate_desktop_entry_basic "$APPDIR/timbleepad.desktop"
    validate_desktop_entry_basic "$APPDIR/usr/share/applications/timbleepad.desktop"
    validate_appstream_basic "$APPDIR/usr/share/metainfo/io.github.brunonlinespace.timbleepad.metainfo.xml"
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$APPDIR/timbleepad.desktop"
        desktop-file-validate "$APPDIR/usr/share/applications/timbleepad.desktop"
    else
        printf 'Info: desktop-file-validate unavailable; built-in checks passed.\n' >&2
    fi
    if command -v appstreamcli >/dev/null 2>&1; then
        appstreamcli validate --no-net "$APPDIR/usr/share/metainfo/io.github.brunonlinespace.timbleepad.metainfo.xml"
    else
        printf 'Info: appstreamcli unavailable; built-in AppStream checks passed.\n' >&2
    fi
}

run_gui_smoke_test() {
    local label="$1"; shift
    local log_file status
    rm -rf "$SMOKE_HOME"
    mkdir -p "$SMOKE_HOME/.config" "$SMOKE_HOME/.cache" "$SMOKE_HOME/.local/share" "$SMOKE_HOME/Documents"
    log_file="$(mktemp "${TMPDIR:-/tmp}/timbleepad-gui-smoke.XXXXXX.log")"
    log "Running ${label} offscreen GUI smoke test"
    set +e
    timeout 30s env \
        HOME="$SMOKE_HOME" XDG_CONFIG_HOME="$SMOKE_HOME/.config" \
        XDG_CACHE_HOME="$SMOKE_HOME/.cache" XDG_DATA_HOME="$SMOKE_HOME/.local/share" \
        QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
        "$@" --timbleepad-smoke-test >"$log_file" 2>&1
    status=$?
    set -e
    if [[ "$status" -ne 0 ]] || ! grep -Fxq 'GUI smoke test passed.' "$log_file"; then
        cat "$log_file" >&2
        rm -f "$log_file"
        die "${label} GUI smoke test failed with exit code ${status}."
    fi
    rm -f "$log_file"
}

run_version_smoke_test() {
    local label="$1"; shift
    local log_file expected status
    expected="${APP_NAME} ${APP_VERSION}"
    rm -rf "$SMOKE_HOME"
    mkdir -p "$SMOKE_HOME/.config" "$SMOKE_HOME/.cache" "$SMOKE_HOME/.local/share"
    log_file="$(mktemp "${TMPDIR:-/tmp}/timbleepad-smoke.XXXXXX.log")"
    log "Running ${label} smoke test"
    set +e
    timeout 30s env \
        HOME="$SMOKE_HOME" XDG_CONFIG_HOME="$SMOKE_HOME/.config" \
        XDG_CACHE_HOME="$SMOKE_HOME/.cache" XDG_DATA_HOME="$SMOKE_HOME/.local/share" \
        QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
        "$@" --version >"$log_file" 2>&1
    status=$?
    set -e
    if [[ "$status" -ne 0 ]] || ! grep -Fxq "$expected" "$log_file"; then
        cat "$log_file" >&2
        rm -f "$log_file"
        die "${label} smoke test failed with exit code ${status}."
    fi
    rm -f "$log_file"
}

validate_bundle() {
    log "Validating Qt bundle"
    find "$APPDIR/usr/lib/timbleepad" -name 'libqxcb.so' -print -quit | grep -q . \
        || die "Qt XCB platform plugin was not bundled."
    find "$APPDIR/usr/lib/timbleepad" \( -name 'libqwayland*.so' -o -name '*wayland*.so' \) -print -quit | grep -q . \
        || printf 'Warning: Qt Wayland plugin was not detected; test native Wayland carefully.\n' >&2
    if find "$APPDIR/usr/lib/timbleepad" -iname '*WebEngine*' -print -quit | grep -q .; then
        die "Qt WebEngine was bundled unexpectedly; Timblee Pad previews in the default browser."
    fi
    run_gui_smoke_test "AppDir GUI" "$APPDIR/AppRun"
    run_gui_smoke_test "AppDir GUI dark-theme" "$APPDIR/AppRun" --appimage-theme=dark
    run_gui_smoke_test "AppDir GUI light-theme" "$APPDIR/AppRun" --appimage-theme=light
    run_gui_smoke_test "AppDir GUI system-theme" "$APPDIR/AppRun" --appimage-theme=system
    run_version_smoke_test "AppDir" "$APPDIR/AppRun"
    run_version_smoke_test "AppDir dark-theme" "$APPDIR/AppRun" --appimage-theme=dark
    run_version_smoke_test "AppDir light-theme" "$APPDIR/AppRun" --appimage-theme=light
    run_version_smoke_test "AppDir system-theme" "$APPDIR/AppRun" --appimage-theme=system
}

elf_sanity_check() {
    local tool="$1" magic size
    require_file "$tool"
    size="$(stat -c %s "$tool")"
    [[ "$size" -gt 0 && "$size" -le "$MAX_TOOL_BYTES" ]] || die "appimagetool invalid size: ${size} bytes."
    magic="$(od -An -tx1 -N4 "$tool" | tr -d ' \n')"
    [[ "$magic" == "7f454c46" ]] || die "appimagetool is not an ELF executable: $tool"
}

download_tool() {
    local url="$1"
    local destination="$2"
    local part="${destination}.part"
    [[ "$url" == https://* ]] || die "appimagetool URL must use HTTPS."
    rm -f "$part"
    if command -v curl >/dev/null 2>&1; then
        curl --proto '=https' --tlsv1.2 --fail --location --retry 3 --retry-all-errors \
            --connect-timeout 30 --max-time 300 --max-filesize "$MAX_TOOL_BYTES" \
            --output "$part" "$url"
    else
        wget --https-only --tries=3 --timeout=30 --output-document="$part" "$url"
    fi
    [[ -f "$part" ]] || die "appimagetool download produced no file."
    elf_sanity_check "$part"
    chmod 0755 "$part"
    mv -f "$part" "$destination"
}

prepare_appimagetool() {
    local tool url
    if [[ -n "${APPIMAGETOOL_PATH:-}" ]]; then
        tool="$(readlink -f -- "$APPIMAGETOOL_PATH")"
        [[ -x "$tool" ]] || die "APPIMAGETOOL_PATH is not executable: $tool"
        log "Using appimagetool supplied through APPIMAGETOOL_PATH"
    else
        mkdir -p "$CACHE_DIR"
        chmod 0700 "$CACHE_DIR"
        tool="${CACHE_DIR}/appimagetool-${ARCH}.AppImage"
        url="${APPIMAGETOOL_URL:-https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage}"
        if [[ ! -x "$tool" ]]; then
            log "Downloading official appimagetool"
            download_tool "$url" "$tool"
        else
            log "Using cached appimagetool"
        fi
    fi
    elf_sanity_check "$tool"
    if [[ -n "${APPIMAGETOOL_SHA256:-}" ]]; then
        [[ "$APPIMAGETOOL_SHA256" =~ ^[[:xdigit:]]{64}$ ]] || die "APPIMAGETOOL_SHA256 must be 64 hexadecimal characters."
        printf '%s  %s\n' "$APPIMAGETOOL_SHA256" "$tool" | sha256sum --check --status \
            || die "appimagetool SHA-256 verification failed."
    elif [[ "${TIMBLEEPAD_RELEASE_BUILD:-0}" == "1" ]]; then
        die "TIMBLEEPAD_RELEASE_BUILD=1 requires APPIMAGETOOL_SHA256."
    else
        printf 'Warning: APPIMAGETOOL_SHA256 not supplied; resolved hash will be recorded.\n' >&2
    fi
    APPIMAGETOOL_RESOLVED="$tool"
}

build_appimage() {
    prepare_appimagetool
    log "Creating ${APPIMAGE##*/}"
    rm -f "$APPIMAGE" "$SHA_FILE"
    ARCH="$ARCH" VERSION="$APP_VERSION" \
        "$APPIMAGETOOL_RESOLVED" --appimage-extract-and-run "$APPDIR" "$APPIMAGE"
    [[ -s "$APPIMAGE" ]] || die "appimagetool did not create expected output."
    chmod 0755 "$APPIMAGE"
    run_gui_smoke_test "final AppImage GUI" "$APPIMAGE" --appimage-extract-and-run
    run_gui_smoke_test "final AppImage GUI dark-theme" "$APPIMAGE" --appimage-extract-and-run --appimage-theme=dark
    run_gui_smoke_test "final AppImage GUI light-theme" "$APPIMAGE" --appimage-extract-and-run --appimage-theme=light
    run_gui_smoke_test "final AppImage GUI system-theme" "$APPIMAGE" --appimage-extract-and-run --appimage-theme=system
    run_version_smoke_test "final AppImage" "$APPIMAGE" --appimage-extract-and-run
    run_version_smoke_test "final AppImage dark-theme" "$APPIMAGE" --appimage-extract-and-run --appimage-theme=dark
    run_version_smoke_test "final AppImage light-theme" "$APPIMAGE" --appimage-extract-and-run --appimage-theme=light
    run_version_smoke_test "final AppImage system-theme" "$APPIMAGE" --appimage-extract-and-run --appimage-theme=system
    (cd "$DIST_DIR" && sha256sum "${APPIMAGE##*/}" > "${SHA_FILE##*/}")
}

write_build_info() {
    {
        echo "Timblee Pad AppImage build"
        echo "Version: ${APP_VERSION}"
        echo "Architecture: ${ARCH}"
        echo "Release mode: ${TIMBLEEPAD_RELEASE_BUILD:-0}"
        echo "Built: $(date --iso-8601=seconds)"
        echo "Host: ${HOST_NAME}"
        echo "Fedora release: ${FEDORA_RELEASE}"
        echo "Privilege policy: non-privileged; no sudo/dnf/su/pkexec"
        echo "System Python: $(python3 --version 2>&1)"
        echo "Build Python: $("$VENV/bin/python" --version 2>&1)"
        echo "PyInstaller: $("$VENV/bin/python" -m PyInstaller --version)"
        "$VENV/bin/python" - <<'PYVERS'
from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
print(f"PyQt6: {PYQT_VERSION_STR}")
print(f"Qt: {QT_VERSION_STR}")
PYVERS
        echo "Root README SHA-256: $(sha256sum "$ROOT_README" | awk '{print $1}')"
        echo "Suite component manifest SHA-256: $(sha256sum "$COMPONENT_MANIFEST" | awk '{print $1}')"
        echo "Identity file SHA-256: $(sha256sum "$IDENTITY_FILE" | awk '{print $1}')"
        echo "Runtime requirements SHA-256: $(sha256sum "${PROGRAM_ROOT}/requirements.txt" | awk '{print $1}')"
        echo "Build requirements SHA-256: $(sha256sum "$BUILD_REQUIREMENTS" | awk '{print $1}')"
        echo "SOURCE_MANIFEST.sha256 SHA-256: $(sha256sum "$SOURCE_MANIFEST" | awk '{print $1}')"
        echo "Builder SHA-256: $(sha256sum "$0" | awk '{print $1}')"
        echo "Source tree SHA-256: $(source_tree_sha256)"
        echo "appimagetool: ${APPIMAGETOOL_RESOLVED}"
        echo "appimagetool SHA-256: $(sha256sum "$APPIMAGETOOL_RESOLVED" | awk '{print $1}')"
        echo "Output: ${APPIMAGE##*/}"
        echo "Output SHA-256: $(sha256sum "$APPIMAGE" | awk '{print $1}')"
        echo "Smoke tests: AppDir GUI PASS + version PASS (default/dark/light/system); final AppImage GUI PASS + version PASS (default/dark/light/system)"
        echo "Source cleanliness: __pycache__/pyc/pyo removed before QA/build and at exit"
    } > "$BUILD_INFO"
}

main() {
    check_non_privileged_policy
    check_host_prerequisites
    check_inputs
    clean_source_python_caches
    run_release_qa
    clean_source_python_caches
    prepare_environment
    freeze_application
    assemble_appdir
    validate_bundle
    build_appimage
    write_build_info
    clean_source_python_caches
    log "Build complete"
    printf 'AppImage: %s\nChecksum: %s\nBuild information: %s\nPython lock: %s\n' \
        "$APPIMAGE" "$SHA_FILE" "$BUILD_INFO" "$PYTHON_LOCK"
}

main "$@"
