#!/usr/bin/env python3
"""Regression tests for Timblee Pad filesystem safety helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from timblee_pad.file_io import (
    FileStateChangedError,
    FileTooLargeError,
    UnsupportedFileError,
    absolute_user_path,
    current_file_state,
    ensure_private_directory,
    install_new_file_from_temp,
    path_identity_matches,
    path_lexists,
    read_regular_file,
    rename_path_no_replace,
    snapshot_from_payload,
    validated_symlink_target,
)


class FileIoTests(unittest.TestCase):
    def test_regular_file_snapshot_and_payload_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "index.html"
            path.write_bytes(b"<p>ok</p>\n")
            data, snapshot = read_regular_file(path, 1024)
            self.assertEqual(data, b"<p>ok</p>\n")
            self.assertEqual(snapshot, snapshot_from_payload(path, data))

    def test_size_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "large.css"
            path.write_bytes(b"x" * 17)
            with self.assertRaises(FileTooLargeError):
                read_regular_file(path, 16)

    def test_absolute_path_does_not_resolve_final_symlink(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            target = root / "target.html"
            link = root / "link.html"
            target.write_text("old\n", encoding="utf-8")
            link.symlink_to(target.name)
            self.assertEqual(absolute_user_path(link), link)
            self.assertTrue(link.is_symlink())

    def test_symlink_target_update_is_guarded(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            first = root / "first.html"
            second = root / "second.html"
            link = root / "link.html"
            first.write_text("first\n", encoding="utf-8")
            second.write_text("second\n", encoding="utf-8")
            link.symlink_to(first.name)
            state = current_file_state(link)
            link.unlink()
            link.symlink_to(second.name)
            with self.assertRaises(FileStateChangedError):
                validated_symlink_target(link, state)
            self.assertEqual(second.read_text(encoding="utf-8"), "second\n")

    def test_dangling_symlink_is_visible_to_lexists(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as raw_root:
            link = Path(raw_root) / "dangling.html"
            link.symlink_to("missing.html")
            self.assertTrue(path_lexists(link))
            self.assertFalse(link.exists())

    def test_private_read_rejects_symbolic_link(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            target = root / "target.json"
            link = root / "config.json"
            target.write_bytes(b"{}")
            link.symlink_to(target.name)
            with self.assertRaises(UnsupportedFileError):
                read_regular_file(link, 1024, follow_symlinks=False)

    def test_fifo_is_rejected_without_blocking(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFOs are unavailable")
        with tempfile.TemporaryDirectory() as raw_root:
            fifo = Path(raw_root) / "pipe.css"
            os.mkfifo(fifo)
            with self.assertRaises(UnsupportedFileError):
                read_regular_file(fifo, 1024)

    def test_new_file_install_does_not_overwrite_raced_destination(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            temporary = root / ".new.tmp"
            destination = root / "index.html"
            temporary.write_bytes(b"new\n")
            destination.write_bytes(b"existing\n")
            with self.assertRaises(FileStateChangedError):
                install_new_file_from_temp(temporary, destination)
            self.assertEqual(destination.read_bytes(), b"existing\n")
            self.assertTrue(temporary.exists())

    def test_new_file_install_creates_destination(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            temporary = root / ".new.tmp"
            destination = root / "styles.css"
            temporary.write_bytes(b"body {}\n")
            install_new_file_from_temp(temporary, destination)
            self.assertEqual(destination.read_bytes(), b"body {}\n")
            self.assertFalse(temporary.exists())

    def test_rename_no_replace_preserves_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            source = root / "source.html"
            destination = root / "destination.htm"
            source.write_bytes(b"source\n")
            destination.write_bytes(b"destination\n")
            with self.assertRaises(FileStateChangedError):
                rename_path_no_replace(source, destination)
            self.assertEqual(source.read_bytes(), b"source\n")
            self.assertEqual(destination.read_bytes(), b"destination\n")

    def test_path_identity_detects_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "styles.css"
            path.write_bytes(b"one\n")
            state = current_file_state(path)
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(b"two\n")
            os.replace(replacement, path)
            self.assertFalse(path_identity_matches(path, state))

    def test_private_directory_rejects_symlink(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(OSError):
                ensure_private_directory(link)


if __name__ == "__main__":
    unittest.main()
