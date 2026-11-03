# Timblee Pad
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Launch host files, folders, editors and web resources safely."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from timblee_pad.file_io import absolute_user_path
from timblee_pad.runtime_paths import RuntimePaths


EDITOR_OVERRIDE_VARIABLE = "TIMBLEEPAD_EDITOR"

_SANITIZED_VARIABLES = frozenset(
    {
        "APPDIR",
        "APPIMAGE",
        "ARGV0",
        "OWD",
        "LD_LIBRARY_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONEXECUTABLE",
        "TIMBLEEPAD_APPIMAGE_THEME",
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
        "QML2_IMPORT_PATH",
        "QML_IMPORT_PATH",
    }
)


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    program: str
    arguments: tuple[str, ...] = ()
    working_directory: Path | None = None


class RuntimeLauncher(QObject):
    """Open host-side applications without leaking bundled runtime paths."""

    status_message = pyqtSignal(str)
    launch_error = pyqtSignal(str)

    def __init__(self, runtime_paths: RuntimePaths, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.runtime_paths = runtime_paths

    def process_environment(self) -> QProcessEnvironment:
        environment = QProcessEnvironment.systemEnvironment()
        if not self.runtime_paths.running_as_appimage and not self.runtime_paths.running_frozen:
            return environment
        for name in _SANITIZED_VARIABLES:
            environment.remove(name)
        host_path = self._host_path()
        if host_path:
            environment.insert("PATH", host_path)
        for name in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH"):
            original_name = f"APPIMAGE_ORIGINAL_{name}"
            original_value = os.environ.get(original_name)
            if original_value is not None:
                environment.insert(name, original_value)
            environment.remove(original_name)
        return environment

    def start_detached(self, command: LaunchCommand) -> bool:
        process = QProcess(self)
        process.setProgram(command.program)
        process.setArguments(list(command.arguments))
        if command.working_directory is not None:
            process.setWorkingDirectory(str(command.working_directory))
        process.setProcessEnvironment(self.process_environment())
        try:
            try:
                result = process.startDetached()
            except TypeError:
                result = QProcess.startDetached(
                    command.program,
                    list(command.arguments),
                    str(command.working_directory or ""),
                )
        finally:
            process.deleteLater()
        if isinstance(result, tuple):
            return bool(result[0])
        return bool(result)

    def open_path(self, path: str | Path) -> bool:
        """Open a regular file or folder with the host desktop default app."""
        target = absolute_user_path(path)
        if not target.exists():
            return self._fail(f"The path does not exist: {target}")
        command = self._desktop_open_command(str(target))
        if command is None:
            return self._fail("No host desktop opener was found (xdg-open or gio).")
        if not self.start_detached(command):
            return self._fail(f"Could not open '{target}'.")
        return True

    def open_url(self, url: str) -> bool:
        """Open an HTTP(S) URL with the host default browser."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return self._fail(f"Unsupported URL: {url}")
        command = self._desktop_open_command(url)
        if command is None:
            return self._fail("No host desktop opener was found (xdg-open or gio).")
        if not self.start_detached(command):
            return self._fail(f"Could not open '{url}'.")
        return True

    def open_in_external_editor(self, path: str | Path) -> bool:
        """Open source in a graphical host editor, respecting TIMBLEEPAD_EDITOR."""
        target = absolute_user_path(path)
        if not target.is_file():
            return self._fail(f"The file does not exist: {target}")

        explicit = os.environ.get(EDITOR_OVERRIDE_VARIABLE, "").strip()
        if explicit:
            try:
                parts = shlex.split(explicit)
            except ValueError as error:
                return self._fail(f"Invalid {EDITOR_OVERRIDE_VARIABLE} value: {error}")
            if parts:
                resolved = self._resolve_executable(parts[0])
                if resolved:
                    command = LaunchCommand(
                        resolved,
                        tuple(parts[1:] + [str(target)]),
                        target.parent,
                    )
                    if self.start_detached(command):
                        return True

        # A desktop association is the most reliable route for native and
        # sandboxed graphical editors.
        desktop = self._desktop_open_command(str(target))
        if desktop is not None and self.start_detached(desktop):
            return True

        for executable in (
            "gnome-text-editor",
            "kate",
            "code",
            "codium",
            "gedit",
            "geany",
            "mousepad",
            "xed",
            "pluma",
        ):
            resolved = self._resolve_executable(executable)
            if resolved:
                command = LaunchCommand(resolved, (str(target),), target.parent)
                if self.start_detached(command):
                    return True

        return self._fail("No graphical editor or desktop file association could be started.")

    def _desktop_open_command(self, target: str) -> LaunchCommand | None:
        xdg_open = self._resolve_executable("xdg-open")
        if xdg_open:
            return LaunchCommand(xdg_open, (target,))
        gio = self._resolve_executable("gio")
        if gio:
            return LaunchCommand(gio, ("open", target))
        return None

    def _resolve_executable(self, executable: str) -> str | None:
        path = Path(executable).expanduser()
        if path.is_absolute():
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which(executable, path=self._host_path())

    def _host_path(self) -> str | None:
        original = os.environ.get("APPIMAGE_ORIGINAL_PATH")
        if original:
            return original
        current = os.environ.get("PATH")
        if not current or (
            not self.runtime_paths.running_as_appimage
            and not self.runtime_paths.running_frozen
        ):
            return current
        blocked_roots = {
            str(self.runtime_paths.launcher_root),
            str(self.runtime_paths.package_root),
        }
        appdir = os.environ.get("APPDIR")
        if appdir:
            blocked_roots.add(str(Path(appdir).resolve(strict=False)))
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            blocked_roots.add(str(Path(frozen_root).resolve(strict=False)))
        clean_entries: list[str] = []
        for entry in current.split(os.pathsep):
            if not entry:
                continue
            resolved = str(Path(entry).expanduser().resolve(strict=False))
            if any(resolved == root or resolved.startswith(root + os.sep) for root in blocked_roots):
                continue
            clean_entries.append(entry)
        return os.pathsep.join(clean_entries)

    def _fail(self, message: str) -> bool:
        self.launch_error.emit(message)
        self.status_message.emit(message)
        return False
