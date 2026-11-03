# Timblee Pad
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Runtime and resource paths for source, frozen, and AppImage builds."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APPIMAGE_ENVIRONMENT_VARIABLE = "APPIMAGE"
APPDIR_ENVIRONMENT_VARIABLE = "APPDIR"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Resolved locations used by the current Timblee Pad process."""

    launcher_root: Path
    package_root: Path
    resource_root: Path
    config_root: Path
    running_as_appimage: bool
    running_frozen: bool

    @classmethod
    def detect(cls, launcher_file: str | Path) -> "RuntimePaths":
        """Resolve paths without relying on the shell's working directory."""
        launcher_root = Path(launcher_file).resolve().parent
        running_as_appimage = bool(
            os.environ.get(APPIMAGE_ENVIRONMENT_VARIABLE)
            or os.environ.get(APPDIR_ENVIRONMENT_VARIABLE)
        )
        running_frozen = bool(getattr(sys, "frozen", False))

        frozen_root_value = getattr(sys, "_MEIPASS", None)
        frozen_root = (
            Path(frozen_root_value).resolve()
            if frozen_root_value
            else launcher_root
        )

        source_package_root = launcher_root / "timblee_pad"
        bundled_package_root = frozen_root / "timblee_pad"
        package_root = (
            bundled_package_root
            if bundled_package_root.exists()
            else source_package_root
        )

        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA") or str(
                Path.home() / "AppData" / "Roaming"
            )
            config_root = Path(appdata) / "brunonlinespace" / "TimbleePad"
        else:
            config_root = Path.home() / ".config" / "brunonlinespace" / "timbleepad"

        return cls(
            launcher_root=launcher_root,
            package_root=package_root,
            resource_root=package_root / "assets",
            config_root=config_root,
            running_as_appimage=running_as_appimage,
            running_frozen=running_frozen,
        )

    @property
    def icon_path(self) -> Path:
        return self.resource_root / "icons" / "timbleepad.png"


    @property
    def appimage_theme_paths(self) -> dict[str, Path]:
        """Return bundled AppImage QSS files, or an empty mapping elsewhere."""
        if not self.running_as_appimage:
            return {}
        appdir_value = os.environ.get(APPDIR_ENVIRONMENT_VARIABLE)
        if not appdir_value:
            return {}
        style_root = (
            Path(appdir_value).resolve()
            / "usr"
            / "share"
            / "timbleepad"
            / "styles"
        )
        resources = {
            "dark": style_root / "breeze-dark.qss",
            "light": style_root / "breeze-light.qss",
        }
        return resources if all(path.is_file() for path in resources.values()) else {}

    @property
    def config_path(self) -> Path:
        return self.config_root / "timbleepad.json"

    @property
    def legacy_config_paths(self) -> tuple[Path, ...]:
        """Import Sheepy Pad UI preferences once when Timblee Pad is first run."""
        if sys.platform == "win32":
            appdata = Path(
                os.environ.get("APPDATA")
                or str(Path.home() / "AppData" / "Roaming")
            )
            return (
                appdata / "brunonlinespace" / "SheepyPad" / "sheepypad.json",
            )
        base = Path.home() / ".config" / "brunonlinespace"
        return (base / "sheepypad" / "sheepypad.json",)

    @property
    def runtime_label(self) -> str:
        if self.running_as_appimage:
            return "AppImage"
        if self.running_frozen:
            return "Frozen bundle"
        return "Portable source"
