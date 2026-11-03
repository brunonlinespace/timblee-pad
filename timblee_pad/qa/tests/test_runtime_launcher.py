#!/usr/bin/env python3
"""Headless regressions for Timblee Pad host-side launching."""

from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

try:
    import PyQt6.QtCore  # type: ignore[import-not-found]  # noqa: F401
except ModuleNotFoundError:
    qtcore = types.ModuleType("PyQt6.QtCore")

    class _Signal:
        def emit(self, *_args, **_kwargs) -> None:
            return None

    class _QObject:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    class _QProcess:
        pass

    class _QProcessEnvironment:
        @staticmethod
        def systemEnvironment():
            return _QProcessEnvironment()

        def remove(self, *_args) -> None:
            pass

        def insert(self, *_args) -> None:
            pass

    qtcore.QObject = _QObject
    qtcore.QProcess = _QProcess
    qtcore.QProcessEnvironment = _QProcessEnvironment
    qtcore.pyqtSignal = lambda *_args, **_kwargs: _Signal()
    package = types.ModuleType("PyQt6")
    package.QtCore = qtcore
    sys.modules.setdefault("PyQt6", package)
    sys.modules.setdefault("PyQt6.QtCore", qtcore)

from timblee_pad.runtime_launcher import LaunchCommand, RuntimeLauncher
from timblee_pad.runtime_paths import RuntimePaths


class RuntimeLauncherTests(unittest.TestCase):
    def _paths(self, root: Path, *, appimage: bool = False) -> RuntimePaths:
        return RuntimePaths(
            launcher_root=root,
            package_root=root / "timblee_pad",
            resource_root=root / "timblee_pad/assets",
            config_root=root / "config",
            running_as_appimage=appimage,
            running_frozen=False,
        )

    def test_open_path_uses_desktop_opener_without_shell_command(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            page = root / "index.html"
            page.write_text("<p>ok</p>", encoding="utf-8")
            launcher = RuntimeLauncher(self._paths(root))
            command_value = LaunchCommand("/usr/bin/xdg-open", (str(page),))
            with (
                mock.patch.object(launcher, "_desktop_open_command", return_value=command_value) as command,
                mock.patch.object(launcher, "start_detached", return_value=True) as detached,
            ):
                self.assertTrue(launcher.open_path(page))
            command.assert_called_once_with(str(page))
            self.assertEqual(detached.call_args.args[0], command_value)

    def test_open_url_rejects_non_http_schemes(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            launcher = RuntimeLauncher(self._paths(Path(raw_root)))
            with mock.patch.object(launcher, "start_detached") as detached:
                self.assertFalse(launcher.open_url("file:///tmp/index.html"))
                self.assertFalse(launcher.open_url("javascript:alert(1)"))
            detached.assert_not_called()

    def test_external_editor_override_is_argument_safe(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            page = root / "index.html"
            page.write_text("<p>ok</p>", encoding="utf-8")
            launcher = RuntimeLauncher(self._paths(root))
            with (
                mock.patch.dict(os.environ, {"TIMBLEEPAD_EDITOR": "editor --new-window"}, clear=False),
                mock.patch.object(launcher, "_resolve_executable", return_value="/usr/bin/editor"),
                mock.patch.object(launcher, "start_detached", return_value=True) as detached,
            ):
                self.assertTrue(launcher.open_in_external_editor(page))
            command = detached.call_args.args[0]
            self.assertEqual(command.program, "/usr/bin/editor")
            self.assertEqual(command.arguments, ("--new-window", str(page)))
            self.assertEqual(command.working_directory, page.parent)

    def test_appimage_sanitizer_names_are_present(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "runtime_launcher.py").read_text(encoding="utf-8")
        for name in ("APPDIR", "APPIMAGE", "PYTHONPATH", "QT_PLUGIN_PATH", "TIMBLEEPAD_APPIMAGE_THEME"):
            self.assertIn(f'"{name}"', source)
        self.assertIn('APPIMAGE_ORIGINAL_PATH', source)

    def test_runtime_launcher_has_no_script_execution_api(self) -> None:
        forbidden = {
            "python_command",
            "shell_command",
            "script_command",
            "script_terminal_command",
            "sudo_executable",
            "launch_script",
        }
        self.assertTrue(forbidden.isdisjoint(set(dir(RuntimeLauncher))))


if __name__ == "__main__":
    unittest.main()
