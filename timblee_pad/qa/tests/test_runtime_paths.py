#!/usr/bin/env python3
"""Regression tests for Timblee Pad runtime and preference paths."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from timblee_pad.runtime_paths import RuntimePaths


class RuntimePathsTests(unittest.TestCase):
    def test_linux_paths_and_sheepy_preference_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "timblee_pad").mkdir()
            home = root / "home"
            with (
                patch.object(sys, "platform", "linux"),
                patch.object(Path, "home", return_value=home),
                patch.dict(os.environ, {}, clear=True),
            ):
                paths = RuntimePaths.detect(root / "main.py")
                legacy = paths.legacy_config_paths
            self.assertEqual(paths.package_root, root / "timblee_pad")
            self.assertEqual(paths.icon_path, root / "timblee_pad/assets/icons/timbleepad.png")
            self.assertEqual(
                paths.config_path,
                home / ".config/brunonlinespace/timbleepad/timbleepad.json",
            )
            self.assertEqual(
                legacy,
                (home / ".config/brunonlinespace/sheepypad/sheepypad.json",),
            )

    def test_windows_paths_and_sheepy_preference_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "timblee_pad").mkdir()
            appdata = root / "AppData/Roaming"
            with (
                patch.object(sys, "platform", "win32"),
                patch.dict(os.environ, {"APPDATA": str(appdata)}, clear=True),
            ):
                paths = RuntimePaths.detect(root / "main.py")
                legacy = paths.legacy_config_paths
            self.assertEqual(
                paths.config_path,
                appdata / "brunonlinespace/TimbleePad/timbleepad.json",
            )
            self.assertEqual(
                legacy,
                (appdata / "brunonlinespace/SheepyPad/sheepypad.json",),
            )

    def test_appimage_theme_paths_require_both_bundled_styles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "timblee_pad").mkdir()
            appdir = root / "TimbleePad.AppDir"
            styles = appdir / "usr/share/timbleepad/styles"
            styles.mkdir(parents=True)
            dark = styles / "breeze-dark.qss"
            light = styles / "breeze-light.qss"
            dark.write_text("QWidget { color: white; }", encoding="utf-8")
            with patch.dict(os.environ, {"APPDIR": str(appdir)}, clear=True):
                self.assertEqual(RuntimePaths.detect(root / "main.py").appimage_theme_paths, {})
                light.write_text("QWidget { color: black; }", encoding="utf-8")
                self.assertEqual(
                    RuntimePaths.detect(root / "main.py").appimage_theme_paths,
                    {"dark": dark, "light": light},
                )

    def test_source_runtime_does_not_expose_appimage_themes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "timblee_pad").mkdir()
            with patch.dict(os.environ, {}, clear=True):
                paths = RuntimePaths.detect(root / "main.py")
            self.assertFalse(paths.running_as_appimage)
            self.assertEqual(paths.appimage_theme_paths, {})


if __name__ == "__main__":
    unittest.main()
