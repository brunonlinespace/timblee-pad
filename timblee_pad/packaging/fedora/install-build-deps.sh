#!/usr/bin/env bash
set -euo pipefail
command -v dnf >/dev/null 2>&1 || { echo "This helper targets Fedora." >&2; exit 2; }
sudo dnf install -y \
    python3 python3-pip python3-devel \
    gcc binutils patchelf file desktop-file-utils appstream \
    fuse-libs curl zsync
