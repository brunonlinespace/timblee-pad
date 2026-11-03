# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder bundle for Timblee Pad."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH).resolve().parents[2]
program_root = project_root / "timblee_pad"
excluded_qt_bindings = [
    "PySide2",
    "PySide6",
    "PyQt5",
    # Timblee Pad does not use PDF or printing. Exclude these at freeze time
    # rather than treating their accidental presence as a fatal AppDir error.
    "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets",
    "PyQt6.QtPrintSupport",
]
hiddenimports = collect_submodules("timblee_pad")
datas = [
    (str(program_root / "LICENSE"), "timblee_pad"),
    (str(program_root / "docs"), "timblee_pad/docs"),
    (str(program_root / "assets"), "timblee_pad/assets"),
]

a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_qt_bindings,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="timbleepad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="timbleepad",
)
