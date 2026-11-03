# Timblee Pad
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone lightweight editor for HTML, CSS and XML source files."""

from __future__ import annotations

import argparse
import bisect
import codecs
import functools
import html
import http.server
import json
import locale
import os
import re
import stat
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import QSize, QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QIntValidator,
    QKeySequence,
    QPainter,
    QPalette,
    QPixmap,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTabWidget,
    QStyleFactory,
    QToolButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from timblee_pad import APP_NAME, APP_VERSION
from timblee_pad.document_profiles import (
    DOCUMENT_PROFILES,
    DOCUMENT_TYPE_ORDER,
    SOURCE_FILE_FILTER,
    SUPPORTED_SOURCE_SUFFIXES,
    document_type_for_path,
    extension_matches_type,
    profile_for_key,
)
from timblee_pad.library_catalog import LibrarySpec, NON_HTML_LIBRARY
from timblee_pad.templates import (
    BUILTIN_TEMPLATES,
    BUILTIN_TEMPLATE_BY_ID,
    CURSOR_MARKER,
    MAX_CUSTOM_TEMPLATES,
    MAX_TEMPLATE_CHARACTERS,
    MAX_TEMPLATE_NAME,
    TemplateSpec,
    default_template_id,
    normalise_custom_templates,
    serialise_custom_templates,
)
from timblee_pad.code_editor import CodeEditor
from timblee_pad.html_tags import (
    COMMON_HTML_TAGS,
    ESSENTIAL_TAGS,
    HTML5_TEMPLATE,
    TAG_BY_KEY,
    TAG_CATEGORIES,
    TagSpec,
    custom_tag,
)
from timblee_pad.tag_io import (
    TagCollectionError,
    build_tag_collection,
    parse_tag_collection,
)
from timblee_pad.file_io import (
    FileSnapshot,
    FileStateChangedError,
    FileTooLargeError,
    UnsupportedFileError,
    absolute_user_path,
    current_file_state,
    ensure_private_directory,
    fsync_directory,
    install_new_file_from_temp,
    path_identity_matches,
    path_lexists,
    read_regular_file,
    rename_path_no_replace,
    snapshot_from_payload,
    validated_symlink_target,
)
from timblee_pad.runtime_launcher import RuntimeLauncher
from timblee_pad.runtime_paths import RuntimePaths

MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_SEARCH_MATCHES = 10_000
MAX_SEARCH_QUERY_CHARACTERS = 4096
MAX_DOCUMENT_CHARACTERS = 25_000_000
MAX_CONFIG_SIZE = 1024 * 1024
MAX_TAG_COLLECTION_SIZE = 1 * 1024 * 1024
TAG_COLLECTION_FILTER = "Timblee Pad Tag Collections (*.timbleetags);;JSON Files (*.json);;All Files (*)"
SUPPORTED_WEB_SUFFIXES = SUPPORTED_SOURCE_SUFFIXES
GITHUB_URL = "https://github.com/brunonlinespace/timblee-pad"
ISSUES_URL = f"{GITHUB_URL}/issues"
WEB_FILE_FILTER = SOURCE_FILE_FILTER
OPEN_WINDOWS: set["TimbleePadWindow"] = set()


def app_dialog_title(subject: str) -> str:
    """Return a Nuxpad-style title for application-owned dialogs."""
    return f"{subject} — {APP_NAME}"


def register_window(window: "TimbleePadWindow") -> None:
    OPEN_WINDOWS.add(window)
    window.destroyed.connect(
        lambda _object=None, registered=window: OPEN_WINDOWS.discard(registered)
    )



class ReplaceDialog(QDialog):
    """Modeless Nuxpad-style replace controls."""

    def __init__(self, window: "TimbleePadWindow") -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle(app_dialog_title("Replace"))
        self.setModal(False)
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.find_input = QLineEdit(self)
        self.find_input.setMaxLength(MAX_SEARCH_QUERY_CHARACTERS)
        self.replace_input = QLineEdit(self)
        form.addRow("Find:", self.find_input)
        form.addRow("Replace with:", self.replace_input)
        layout.addLayout(form)

        self.match_case = QCheckBox("Match case", self)
        layout.addWidget(self.match_case)

        buttons = QHBoxLayout()
        find_next = QPushButton("Find Next", self)
        self.replace_button = QPushButton("Replace", self)
        self.replace_all_button = QPushButton("Replace All", self)
        close = QPushButton("Close", self)
        buttons.addWidget(find_next)
        buttons.addWidget(self.replace_button)
        buttons.addWidget(self.replace_all_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.find_input.returnPressed.connect(self._find_next)
        find_next.clicked.connect(self._find_next)
        self.replace_button.clicked.connect(self._replace)
        self.replace_all_button.clicked.connect(self._replace_all)
        close.clicked.connect(self.close)
        self.find_input.textChanged.connect(self._sync_find_text)
        self.match_case.toggled.connect(self._sync_case)

    def prepare(self, query: str, match_case: bool) -> None:
        self.find_input.blockSignals(True)
        self.match_case.blockSignals(True)
        self.find_input.setText(query)
        self.match_case.setChecked(match_case)
        self.find_input.blockSignals(False)
        self.match_case.blockSignals(False)
        self.find_input.selectAll()
        self.find_input.setFocus()

    def set_view_only(self, enabled: bool) -> None:
        """Disable document-changing controls while preserving Find Next."""
        self.replace_button.setEnabled(not enabled)
        self.replace_all_button.setEnabled(not enabled)

    def _sync_find_text(self, text: str) -> None:
        self.window.set_search_query(text)

    def _sync_case(self, checked: bool) -> None:
        self.window.set_search_case_sensitive(checked)

    def _find_next(self) -> None:
        self.window.set_search_query(self.find_input.text())
        self.window.set_search_case_sensitive(self.match_case.isChecked())
        self.window.find_next()

    def _replace(self) -> None:
        self.window.set_search_query(self.find_input.text())
        self.window.set_search_case_sensitive(self.match_case.isChecked())
        self.window.replace_current(self.replace_input.text())

    def _replace_all(self) -> None:
        self.window.set_search_query(self.find_input.text())
        self.window.set_search_case_sensitive(self.match_case.isChecked())
        self.window.replace_all(self.replace_input.text())


class NewDocumentDialog(QDialog):
    """Compact chooser used by File → New when no direct default applies."""

    def __init__(self, window: "TimbleePadWindow", *, show_default_checkbox: bool = True) -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle(app_dialog_title("New Document"))
        self.setWindowIcon(window.windowIcon())
        self.setModal(True)
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.type_combo = QComboBox(self)
        for key in DOCUMENT_TYPE_ORDER:
            self.type_combo.addItem(profile_for_key(key).label, key)
        self.template_combo = QComboBox(self)
        form.addRow("Document type:", self.type_combo)
        form.addRow("Template:", self.template_combo)
        layout.addLayout(form)

        self.default_checkbox = QCheckBox(
            "Use this type and template as my default for New", self
        )
        self.default_checkbox.setVisible(show_default_checkbox)
        layout.addWidget(self.default_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.type_combo.currentIndexChanged.connect(self._refresh_templates)
        self._refresh_templates()

    def _refresh_templates(self) -> None:
        language = self.selected_language()
        previous = self.template_combo.currentData()
        self.template_combo.clear()
        for spec in self.window.templates_for_language(language):
            label = spec.name + ("  (Built-in)" if spec.builtin else "")
            self.template_combo.addItem(label, spec.template_id)
        wanted = previous or default_template_id(language)
        index = self.template_combo.findData(wanted)
        self.template_combo.setCurrentIndex(index if index >= 0 else 0)

    def selected_language(self) -> str:
        value = self.type_combo.currentData()
        return str(value) if value in DOCUMENT_PROFILES else "html"

    def selected_template_id(self) -> str:
        value = self.template_combo.currentData()
        return str(value) if isinstance(value, str) else default_template_id(self.selected_language())


class DefaultNewDocumentDialog(QDialog):
    """Configure the direct Ctrl+N/startup document default."""

    def __init__(self, window: "TimbleePadWindow") -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle(app_dialog_title("Default New Document"))
        self.setWindowIcon(window.windowIcon())
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Choose what Timblee Pad should create when it starts without a file "
            "and when you press Ctrl+N. Choose Always Ask to use the Start a Document screen/chooser.",
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.type_combo = QComboBox(self)
        self.type_combo.addItem("Always Ask", "ask")
        for key in DOCUMENT_TYPE_ORDER:
            self.type_combo.addItem(profile_for_key(key).label, key)
        self.template_combo = QComboBox(self)
        form.addRow("Default:", self.type_combo)
        form.addRow("Template:", self.template_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.type_combo.currentIndexChanged.connect(self._refresh_templates)
        index = self.type_combo.findData(window.default_new_type)
        self.type_combo.setCurrentIndex(index if index >= 0 else 0)
        self._refresh_templates()

    def _refresh_templates(self) -> None:
        language = str(self.type_combo.currentData())
        ask = language == "ask"
        self.template_combo.setEnabled(not ask)
        self.template_combo.clear()
        if ask:
            return
        for spec in self.window.templates_for_language(language):
            label = spec.name + ("  (Built-in)" if spec.builtin else "")
            self.template_combo.addItem(label, spec.template_id)
        wanted = self.window.default_new_template or default_template_id(language)
        index = self.template_combo.findData(wanted)
        self.template_combo.setCurrentIndex(index if index >= 0 else 0)


class TemplateManagerDialog(QDialog):
    """Edit user template copies while keeping factory templates immutable."""

    def __init__(self, window: "TimbleePadWindow") -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle(app_dialog_title("Templates"))
        self.setWindowIcon(window.windowIcon())
        self.setModal(True)
        self.setMinimumSize(760, 560)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Language:", self))
        self.language_combo = QComboBox(self)
        for key in DOCUMENT_TYPE_ORDER:
            self.language_combo.addItem(profile_for_key(key).short_label, key)
        header.addWidget(self.language_combo)
        header.addStretch(1)
        layout.addLayout(header)

        self.template_list = QListWidget(self)
        layout.addWidget(self.template_list, 1)

        form = QFormLayout()
        self.name_edit = QLineEdit(self)
        self.name_edit.setMaxLength(MAX_TEMPLATE_NAME)
        self.content_edit = QPlainTextEdit(self)
        self.content_edit.setPlaceholderText(
            "Template text. Use [[cursor]] once to choose the initial caret position."
        )
        form.addRow("Name:", self.name_edit)
        form.addRow("Template:", self.content_edit)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add Custom", self)
        self.duplicate_button = QPushButton("Duplicate & Edit", self)
        self.save_button = QPushButton("Save Custom", self)
        self.delete_button = QPushButton("Delete Custom", self)
        actions.addWidget(self.add_button)
        actions.addWidget(self.duplicate_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        close_box.rejected.connect(self.close)
        layout.addWidget(close_box)

        self.language_combo.currentIndexChanged.connect(self.refresh)
        self.template_list.itemSelectionChanged.connect(self._selection_changed)
        self.add_button.clicked.connect(self._add_custom)
        self.duplicate_button.clicked.connect(self._duplicate_selected)
        self.save_button.clicked.connect(self._save_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.refresh()

    def language(self) -> str:
        value = self.language_combo.currentData()
        return str(value) if value in DOCUMENT_PROFILES else "html"

    def selected_template_id(self) -> str | None:
        item = self.template_list.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return str(value) if isinstance(value, str) else None

    def refresh(self) -> None:
        selected_id = self.selected_template_id()
        self.template_list.blockSignals(True)
        self.template_list.clear()
        for spec in self.window.templates_for_language(self.language()):
            item = QListWidgetItem(spec.name + ("  • Built-in" if spec.builtin else "  • Custom"))
            item.setData(Qt.ItemDataRole.UserRole, spec.template_id)
            self.template_list.addItem(item)
            if spec.template_id == selected_id:
                self.template_list.setCurrentItem(item)
        self.template_list.blockSignals(False)
        if self.template_list.currentItem() is None and self.template_list.count():
            self.template_list.setCurrentRow(0)
        self._selection_changed()

    def _selection_changed(self) -> None:
        spec = self.window.template_for_id(self.selected_template_id())
        if spec is None:
            self.name_edit.clear()
            self.content_edit.clear()
            self.name_edit.setEnabled(False)
            self.content_edit.setEnabled(False)
            self.save_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.duplicate_button.setEnabled(False)
            return
        self.name_edit.setText(spec.name)
        self.content_edit.setPlainText(spec.content)
        editable = not spec.builtin
        self.name_edit.setEnabled(editable)
        self.content_edit.setEnabled(editable)
        self.save_button.setEnabled(editable)
        self.delete_button.setEnabled(editable)
        self.duplicate_button.setEnabled(True)

    def _add_custom(self) -> None:
        try:
            spec = self.window.add_custom_template(self.language())
        except ValueError as error:
            QMessageBox.warning(self, app_dialog_title("Template Limit"), str(error))
            return
        self.refresh()
        for row in range(self.template_list.count()):
            item = self.template_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == spec.template_id:
                self.template_list.setCurrentRow(row)
                self.name_edit.setFocus()
                self.name_edit.selectAll()
                break

    def _duplicate_selected(self) -> None:
        source = self.window.template_for_id(self.selected_template_id())
        if source is None:
            return
        try:
            spec = self.window.add_custom_template(
                source.language,
                name=f"{source.name} Copy",
                content=source.content,
            )
        except ValueError as error:
            QMessageBox.warning(self, app_dialog_title("Template Limit"), str(error))
            return
        self.refresh()
        for row in range(self.template_list.count()):
            item = self.template_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == spec.template_id:
                self.template_list.setCurrentRow(row)
                break

    def _save_selected(self) -> None:
        template_id = self.selected_template_id()
        if not template_id:
            return
        try:
            self.window.update_custom_template(
                template_id,
                self.name_edit.text(),
                self.content_edit.toPlainText(),
            )
        except ValueError as error:
            QMessageBox.warning(self, app_dialog_title("Invalid Template"), str(error))
            return
        self.refresh()

    def _delete_selected(self) -> None:
        template_id = self.selected_template_id()
        if not template_id or template_id in BUILTIN_TEMPLATE_BY_ID:
            return
        answer = QMessageBox.question(
            self,
            app_dialog_title("Delete Template"),
            "Delete this custom template?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.window.delete_custom_template(template_id)
            self.refresh()


class _QuietPreviewHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args) -> None:
        return


class PreviewServer:
    """Tiny loopback-only static server used to avoid .html file associations."""

    def __init__(self) -> None:
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.root: Path | None = None

    def ensure_root(self, root: Path) -> int:
        root = root.resolve(strict=False)
        if self._server is not None and self.root == root:
            return int(self._server.server_address[1])
        self.close()
        handler = functools.partial(_QuietPreviewHandler, directory=str(root))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        self.root = root
        return int(server.server_address[1])

    def close(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        self.root = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)


class TagLibraryPanel(QWidget):
    """Reusable language-aware insertion Library surface."""

    def __init__(
        self,
        window: "TimbleePadWindow",
        parent: QWidget | None = None,
        *,
        sidebar_mode: bool = False,
    ) -> None:
        super().__init__(parent or window)
        self.window = window
        self.sidebar_mode = bool(sidebar_mode)
        self._lists: dict[str, QListWidget] = {}
        self._tab_signature: tuple[str, ...] = ()
        self._catalog_signature: tuple[str, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        if self.sidebar_mode:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(6)
            self.catalog_combo = QComboBox(self)
            self.catalog_combo.setToolTip("Choose Library catalogue")
            header.addWidget(self.catalog_combo, 1)
            self.close_sidebar_button = QToolButton(self)
            self.close_sidebar_button.setText("×")
            self.close_sidebar_button.setToolTip("Close Library sidebar")
            self.close_sidebar_button.setAccessibleName("Close Library sidebar")
            self.close_sidebar_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.close_sidebar_button.setFixedWidth(26)
            self.close_sidebar_button.clicked.connect(
                self.window.hide_tag_library_sidebar
            )
            header.addWidget(self.close_sidebar_button)
            layout.addLayout(header)
        else:
            self.catalog_combo = None
            self.close_sidebar_button = None

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search the current language Library")
        self.search_input.textChanged.connect(self.refresh)
        layout.addWidget(self.search_input)

        if self.sidebar_mode:
            self.sidebar_list = QListWidget(self)
            self.sidebar_list.setAlternatingRowColors(True)
            self.sidebar_list.itemSelectionChanged.connect(self._update_details)
            self.sidebar_list.itemDoubleClicked.connect(
                lambda _item: self._insert_from_list(self.sidebar_list)
            )
            layout.addWidget(self.sidebar_list, 1)
            self.tabs = None
            self._rebuild_catalog_selector()
            self.catalog_combo.currentTextChanged.connect(lambda _text: self.refresh())
        else:
            self.sidebar_list = None
            self.tabs = QTabWidget(self)
            self.tabs.setDocumentMode(True)
            self.tabs.setUsesScrollButtons(True)
            layout.addWidget(self.tabs, 1)
            self._rebuild_tabs()

        self.details = QLabel("", self)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)

        primary_buttons = QHBoxLayout()
        self.insert_button = QPushButton("Insert", self)
        self.favourite_button = QPushButton("Add to My Favourites", self)
        self.insert_button.clicked.connect(self.insert_selected)
        self.favourite_button.clicked.connect(self.toggle_selected_favourite)
        primary_buttons.addWidget(self.insert_button)
        primary_buttons.addWidget(self.favourite_button)
        layout.addLayout(primary_buttons)

        self.add_custom_button: QPushButton | None = None
        self.remove_custom_button: QPushButton | None = None
        self.import_button: QPushButton | None = None
        self.export_button: QPushButton | None = None
        if not self.sidebar_mode:
            custom_buttons = QHBoxLayout()
            self.add_custom_button = QPushButton("Add Custom Tag…", self)
            self.remove_custom_button = QPushButton("Remove Custom", self)
            self.add_custom_button.clicked.connect(self.add_custom)
            self.remove_custom_button.clicked.connect(self.remove_selected_custom)
            custom_buttons.addWidget(self.add_custom_button)
            custom_buttons.addWidget(self.remove_custom_button)
            layout.addLayout(custom_buttons)

            transfer_buttons = QHBoxLayout()
            self.import_button = QPushButton("Import Tags…", self)
            self.export_button = QPushButton("Export Tags…", self)
            self.import_button.clicked.connect(self.window.import_tags)
            self.export_button.clicked.connect(self.window.export_tags)
            transfer_buttons.addWidget(self.import_button)
            transfer_buttons.addWidget(self.export_button)
            layout.addLayout(transfer_buttons)

        # QTabWidget can emit currentChanged while tabs are being added. Connect
        # only after every control used by _update_details() has been created.
        if self.tabs is not None:
            self.tabs.currentChanged.connect(lambda _index: self._update_details())
        self.refresh()

    def _categories(self) -> tuple[str, ...]:
        base = ("All", *self.window.library_categories())
        has_favourites = any(
            spec.key in self.window.favourite_tags
            for spec in self.window.library_specs()
        )
        return ("Favourites", *base) if has_favourites else base

    def _rebuild_catalog_selector(self) -> None:
        if self.catalog_combo is None:
            return
        categories = self._categories()
        if categories == self._catalog_signature:
            return
        selected = self.catalog_combo.currentText() or categories[0]
        self.catalog_combo.blockSignals(True)
        self.catalog_combo.clear()
        self.catalog_combo.addItems(categories)
        index = self.catalog_combo.findText(selected)
        if index < 0:
            index = self.catalog_combo.findText("All")
        self.catalog_combo.setCurrentIndex(max(0, index))
        self.catalog_combo.blockSignals(False)
        self._catalog_signature = categories

    def _rebuild_tabs(self) -> None:
        if self.tabs is None:
            return
        categories = self._categories()
        if categories == self._tab_signature:
            return
        previous_index = self.tabs.currentIndex()
        selected = (
            self.tabs.tabText(previous_index)
            if previous_index >= 0 and self.tabs.count()
            else categories[0]
        )
        self.tabs.blockSignals(True)
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()
        self._lists.clear()
        for category in categories:
            list_widget = QListWidget(self.tabs)
            list_widget.setAlternatingRowColors(True)
            list_widget.itemSelectionChanged.connect(
                lambda selected=list_widget: self._selection_changed(selected)
            )
            list_widget.itemDoubleClicked.connect(
                lambda _item, selected=list_widget: self._insert_from_list(selected)
            )
            self.tabs.addTab(list_widget, category)
            self._lists[category] = list_widget
        target = self.tabs.indexOf(self._lists.get(selected)) if selected in self._lists else -1
        if target < 0:
            target = self.tabs.indexOf(self._lists.get("All"))
        self.tabs.setCurrentIndex(max(0, target))
        self.tabs.blockSignals(False)
        self._tab_signature = categories

    def _current_category(self) -> str:
        if self.catalog_combo is not None:
            return self.catalog_combo.currentText() or "All"
        if self.tabs is None:
            return "All"
        index = self.tabs.currentIndex()
        return self.tabs.tabText(index) if index >= 0 else "All"

    def _current_list(self) -> QListWidget | None:
        if self.sidebar_list is not None:
            return self.sidebar_list
        return self._lists.get(self._current_category())

    def _selection_changed(self, source: QListWidget) -> None:
        if source is not self._current_list():
            return
        self._update_details()

    @staticmethod
    def _key_from_list(list_widget: QListWidget | None) -> str | None:
        if list_widget is None:
            return None
        item = list_widget.currentItem()
        if item is None:
            return None
        key = item.data(Qt.ItemDataRole.UserRole)
        return str(key) if isinstance(key, str) else None

    def current_key(self) -> str | None:
        return self._key_from_list(self._current_list())

    def _populate_list(
        self,
        list_widget: QListWidget,
        category: str,
        query: str,
        selected_key: str | None,
    ) -> None:
        list_widget.blockSignals(True)
        list_widget.clear()
        for spec in self.window.library_specs():
            haystack = f"{spec.key} {spec.label} {spec.category} {spec.description}".casefold()
            if query and query not in haystack:
                continue
            favourite = spec.key in self.window.favourite_tags
            if category == "Favourites" and not favourite:
                continue
            if category not in {"Favourites", "All"} and spec.category != category:
                continue
            starred = "★" if favourite else "☆"
            item = QListWidgetItem(f"{starred}  {spec.label} — {spec.description}")
            item.setData(Qt.ItemDataRole.UserRole, spec.key)
            item.setToolTip(f"{spec.category}: {spec.description}")
            list_widget.addItem(item)
            if spec.key == selected_key:
                list_widget.setCurrentItem(item)
        list_widget.blockSignals(False)
        if list_widget.currentItem() is None and list_widget.count():
            list_widget.setCurrentRow(0)

    def refresh(self) -> None:
        self._rebuild_catalog_selector()
        self._rebuild_tabs()
        language = self.window.document_type
        self.search_input.setPlaceholderText(
            f"Search {profile_for_key(language).short_label} Library"
        )
        html_mode = language == "html"
        for control in (
            self.add_custom_button,
            self.remove_custom_button,
            self.import_button,
            self.export_button,
        ):
            if control is not None:
                control.setVisible(html_mode)
        query = self.search_input.text().strip().casefold()
        selected_key = self.current_key()
        selected_category = self._current_category()

        if self.sidebar_list is not None:
            self._populate_list(
                self.sidebar_list,
                selected_category,
                query,
                selected_key,
            )
        else:
            for category, list_widget in self._lists.items():
                self._populate_list(list_widget, category, query, selected_key)
        self._update_details()

    def update_action_state(self) -> None:
        self._update_details()

    def _update_details(self) -> None:
        key = self.current_key()
        spec = self.window.tag_spec_for_key(key) if key else None
        enabled = spec is not None
        self.insert_button.setEnabled(enabled and self.window.library_actions_available())
        self.favourite_button.setEnabled(enabled)
        if self.remove_custom_button is not None:
            self.remove_custom_button.setEnabled(
                self.window.document_type == "html"
                and enabled
                and key in self.window.custom_tag_names
            )
        if spec is None:
            self.details.setText("No tag selected.")
            self.favourite_button.setText("Add to My Favourites")
            return
        self.details.setText(
            f"{spec.label}  •  {spec.category}\n{spec.description}\n"
            f"Insertion: {spec.opening}{'…' + spec.closing if spec.closing else ''}"
        )
        self.favourite_button.setText(
            "Remove from My Favourites"
            if spec.key in self.window.favourite_tags
            else "Add to My Favourites"
        )

    def _insert_from_list(self, list_widget: QListWidget) -> None:
        key = self._key_from_list(list_widget)
        if key:
            self.window.insert_library_item_by_key(key)

    def insert_selected(self) -> None:
        key = self.current_key()
        if key:
            self.window.insert_library_item_by_key(key)

    def toggle_selected_favourite(self) -> None:
        key = self.current_key()
        if key:
            self.window.toggle_library_favourite(key)

    def add_custom(self) -> None:
        self.window.add_custom_tag()

    def remove_selected_custom(self) -> None:
        key = self.current_key()
        if key:
            self.window.remove_custom_tag(key)


class TagLibraryDialog(QDialog):
    """Modeless floating wrapper around the shared tag library panel."""

    def __init__(self, window: "TimbleePadWindow") -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle(app_dialog_title("Library"))
        self.setWindowIcon(window.windowIcon())
        self.setModal(False)
        self.setMinimumSize(760, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.panel = TagLibraryPanel(window, self)
        layout.addWidget(self.panel, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def refresh(self) -> None:
        self.panel.refresh()


class TimbleePadWindow(QMainWindow):
    """One independent Timblee Pad document window."""

    def __init__(self, initial_file: str | Path | None = None) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        register_window(self)

        self.file_path: Path | None = None
        self.file_encoding = "utf-8"
        self.file_bom = b""
        self.file_newline = "\n"
        self.file_disk_snapshot: FileSnapshot | None = None
        self.document_type = "html"
        self.document_active = False
        self._loading = False
        self.view_only = False
        self._view_only_edit_notice_shown = False

        self.search_query = ""
        self.search_case_sensitive = False
        self.search_matches: list[tuple[int, int]] = []
        self.search_match_starts: list[int] = []
        self.search_match_ends: list[int] = []
        self.current_search_index = -1
        self.search_results_truncated = False
        self._pending_search_preserve_position = False
        self._search_refresh_timer = QTimer(self)
        self._search_refresh_timer.setSingleShot(True)
        self._search_refresh_timer.setInterval(120)
        self._search_refresh_timer.timeout.connect(
            self._run_pending_search_refresh
        )
        self.preview_server = PreviewServer()
        self.search_icon_bindings: list[tuple[object, str, QStyle.StandardPixmap]] = []

        self.replace_dialog: ReplaceDialog | None = None
        self.shortcuts_dialog: QDialog | None = None
        self.about_dialog: QDialog | None = None
        self.tag_library_dialog: TagLibraryDialog | None = None

        self.runtime_paths = RuntimePaths.detect(
            Path(__file__).resolve().parents[1] / "main.py"
        )
        if self.runtime_paths.icon_path.is_file():
            self.setWindowIcon(QIcon(str(self.runtime_paths.icon_path)))
        self.runtime_launcher = RuntimeLauncher(self.runtime_paths, self)
        self.runtime_launcher.launch_error.connect(self._show_launch_error)
        self.runtime_launcher.status_message.connect(self.show_status)

        self.appimage_theme_files = self.runtime_paths.appimage_theme_paths
        self.appimage_theme_available = bool(self.appimage_theme_files)
        requested_theme = os.environ.get(
            "TIMBLEEPAD_APPIMAGE_THEME",
            "",
        ).strip().lower()
        self.appimage_theme_override = (
            requested_theme
            if requested_theme in ("dark", "light", "system")
            else None
        )

        self.config_file = self.runtime_paths.config_path
        self._load_preferences()
        if self.appimage_theme_available:
            self.apply_appimage_theme(
                self.effective_appimage_theme(),
                update_actions=False,
            )

        self.resize(940, 650)
        self.setMinimumSize(680, 440)
        self.setAcceptDrops(True)
        self._build_ui()
        self._apply_preferences()
        self._update_title()
        self._update_status()
        self._update_file_action_state()
        self._update_edit_action_state()

        if initial_file is not None:
            self.load_file(initial_file, check_changes=False)
        else:
            self._handle_startup_without_file()

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def _load_preferences(self) -> None:
        self.word_wrap = False
        self.show_line_numbers = True
        self.show_status_bar = True
        self.use_app_menu = True
        self.layout_mode = 1
        self.tag_library_sidebar_position = "disabled"
        self.tag_library_sidebar_hidden = False
        self.drop_open_mode = "active_window"
        self.dark_editor = True
        fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.font_family = fixed.family()
        self.font_size = 10
        self.font_weight = int(QFont.Weight.Normal)
        self.font_italic = False
        self.tab_width_spaces = 4
        self.appimage_theme = "dark"
        self.auto_close_html_tags = True
        self.favourite_tags: set[str] = set()
        self.custom_tag_names: list[str] = []
        self.default_new_type = "ask"
        self.default_new_template = ""
        self.custom_templates: list[TemplateSpec] = []

        config_source = self.config_file
        imported_legacy_preferences = False
        if not path_lexists(config_source):
            for legacy_config in self.runtime_paths.legacy_config_paths:
                if path_lexists(legacy_config):
                    config_source = legacy_config
                    imported_legacy_preferences = True
                    break

        try:
            raw_config, _snapshot = read_regular_file(
                config_source,
                MAX_CONFIG_SIZE,
                follow_symlinks=False,
            )
            loaded = json.loads(raw_config.decode("utf-8"))
        except (
            FileNotFoundError,
            FileTooLargeError,
            UnsupportedFileError,
            UnicodeDecodeError,
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ):
            return
        if not isinstance(loaded, dict):
            return

        def bounded_int(
            key: str,
            default: int,
            minimum: int,
            maximum: int,
        ) -> int:
            try:
                value = int(loaded.get(key, default))
            except (TypeError, ValueError, OverflowError):
                return default
            return max(minimum, min(maximum, value))

        def boolean_value(key: str, default: bool) -> bool:
            value = loaded.get(key, default)
            return value if isinstance(value, bool) else default

        self.word_wrap = boolean_value("word_wrap", False)
        self.show_line_numbers = boolean_value("show_line_numbers", True)
        self.show_status_bar = boolean_value("show_status_bar", True)
        self.use_app_menu = boolean_value("use_app_menu", True)
        self.layout_mode = bounded_int("layout_mode", 1, 1, 4)
        sidebar_position = loaded.get("tag_library_sidebar_position")
        if sidebar_position in ("disabled", "left", "right"):
            self.tag_library_sidebar_position = str(sidebar_position)
        if loaded.get("drop_open_mode") in ("active_window", "new_window"):
            self.drop_open_mode = str(loaded["drop_open_mode"])
        self.dark_editor = boolean_value("dark_editor", True)

        family = loaded.get("font_family")
        if isinstance(family, str) and family.strip():
            self.font_family = family.strip()
        self.font_size = bounded_int("font_size", 10, 6, 72)
        self.font_weight = bounded_int(
            "font_weight",
            int(QFont.Weight.Normal),
            int(QFont.Weight.Thin),
            int(QFont.Weight.Black),
        )
        self.font_italic = boolean_value("font_italic", False)
        self.tab_width_spaces = bounded_int("tab_width_spaces", 4, 1, 16)
        saved_appimage_theme = str(loaded.get("appimage_theme", "")).lower()
        if saved_appimage_theme in ("dark", "light"):
            self.appimage_theme = saved_appimage_theme
        else:
            # Import the short-lived boolean preference used by r1-r16.
            self.appimage_theme = (
                "dark"
                if boolean_value("appimage_dark_mode", True)
                else "light"
            )

        self.auto_close_html_tags = boolean_value("auto_close_html_tags", True)
        favourite_values = loaded.get("favourite_tags", [])
        if isinstance(favourite_values, list):
            self.favourite_tags = {
                value for value in favourite_values
                if isinstance(value, str) and len(value) <= 128
            }
        custom_values = loaded.get("custom_tag_names", [])
        if isinstance(custom_values, list):
            cleaned_custom: list[str] = []
            for value in custom_values[:200]:
                if not isinstance(value, str) or len(value) > 128:
                    continue
                try:
                    spec = custom_tag(value)
                except ValueError:
                    continue
                if spec.key not in TAG_BY_KEY and spec.key not in cleaned_custom:
                    cleaned_custom.append(spec.key)
            self.custom_tag_names = cleaned_custom

        default_type = loaded.get("default_new_type", "ask")
        if default_type in {"ask", *DOCUMENT_TYPE_ORDER}:
            self.default_new_type = str(default_type)
        default_template = loaded.get("default_new_template", "")
        if isinstance(default_template, str) and len(default_template) <= 160:
            self.default_new_template = default_template
        self.custom_templates = normalise_custom_templates(
            loaded.get("custom_templates", [])
        )

        # Preserve the former file as a backup while importing its settings
        # once into the new Timblee Pad configuration location.
        if imported_legacy_preferences:
            self._save_preferences()

    def _save_preferences(self) -> None:
        data = {
            "word_wrap": self.word_wrap,
            "show_line_numbers": self.show_line_numbers,
            "show_status_bar": self.show_status_bar,
            "use_app_menu": self.use_app_menu,
            "layout_mode": self.layout_mode,
            "tag_library_sidebar_position": self.tag_library_sidebar_position,
            "drop_open_mode": self.drop_open_mode,
            "dark_editor": self.dark_editor,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "font_italic": self.font_italic,
            "tab_width_spaces": self.tab_width_spaces,
            # Preserve the AppImage choice even when source/portable mode saves
            # other preferences; those modes still do not apply or expose it.
            "appimage_theme": self.appimage_theme,
            "auto_close_html_tags": self.auto_close_html_tags,
            "favourite_tags": sorted(self.favourite_tags),
            "custom_tag_names": list(self.custom_tag_names),
            "default_new_type": self.default_new_type,
            "default_new_template": self.default_new_template,
            "custom_templates": serialise_custom_templates(self.custom_templates),
        }
        temporary: Path | None = None
        descriptor: int | None = None
        try:
            ensure_private_directory(self.config_file.parent)
            descriptor, raw_path = tempfile.mkstemp(
                prefix=".timbleepad-",
                suffix=".json.tmp",
                dir=self.config_file.parent,
                text=True,
            )
            temporary = Path(raw_path)
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = None
                json.dump(data, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.config_file)
            temporary = None
            fsync_directory(self.config_file.parent)
        except OSError:
            pass
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(6, 6, 6, 6)
        self.main_layout.setSpacing(6)

        self.toolbar = QWidget(self)
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_layout.setSpacing(6)
        self.main_layout.addWidget(self.toolbar)

        # The Edit menu binds several actions directly to CodeEditor methods,
        # so the editor must exist before the menus are constructed.
        self.editor = CodeEditor(self)
        self.editor.setObjectName("editor")
        self.editor.document().modificationChanged.connect(
            lambda _modified: self._update_title()
        )
        self.editor.textChanged.connect(self._on_document_text_changed)
        self.editor.cursorPositionChanged.connect(self._update_status)
        self.editor.overwrite_mode_changed.connect(
            lambda _enabled: self._update_status()
        )
        self.editor.go_to_line_requested.connect(self.go_to_line)
        self.editor.paste_rejected.connect(self.show_status)
        self.editor.view_only_edit_attempt.connect(
            self.show_view_only_edit_prompt
        )
        self.editor.files_dropped.connect(self.open_dropped_files)

        self.app_menu_bar = self.menuBar()
        self.app_menu_bar.clear()
        self._make_file_menu()
        self._make_edit_menu()
        self._make_view_menu()
        self._make_tags_menu()
        self._make_help_menu()

        self.menu_buttons_container = QWidget(self.toolbar)
        menu_buttons_layout = QHBoxLayout(self.menu_buttons_container)
        menu_buttons_layout.setContentsMargins(0, 0, 0, 0)
        menu_buttons_layout.setSpacing(6)
        self.menu_buttons_container.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        for label, menu in (
            ("File", self.file_menu),
            ("Edit", self.edit_menu),
            ("View", self.view_menu),
            ("Library", self.tags_menu),
            ("Help", self.help_menu),
        ):
            button = QToolButton(self.menu_buttons_container)
            button.setText(label)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            button.setMenu(menu)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            menu_buttons_layout.addWidget(button)

        self.primary_controls = QWidget(self.toolbar)
        self.primary_controls.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Preferred,
        )
        primary_layout = QHBoxLayout(self.primary_controls)
        primary_layout.setContentsMargins(0, 0, 0, 0)
        primary_layout.setSpacing(6)
        primary_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        primary_layout.addWidget(self.menu_buttons_container)

        # Document type remains available from File -> Document Type.  The
        # persistent toolbar shortcut was intentionally removed to keep the
        # primary chrome focused on menus, Preview and Find.
        self.preview_button = self._action_button(
            "Preview", self.preview_in_default_browser
        )
        primary_layout.addWidget(self.preview_button)
        self.toolbar_layout.addWidget(
            self.primary_controls,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )

        self.search_container = self._create_search_bar(bottom=False)
        self.toolbar_layout.addWidget(self.search_container, 1)

        # Start a Document and the active editor share one authoritative
        # workspace slot.  A separate editor column lets split-mode Find sit
        # above/below the editor only, while a Library sidebar spans the full
        # workspace height exactly as drawn in the split-layout contract.
        self.workspace_host = QStackedWidget(self)
        self.start_panel = self._create_start_panel()
        self.workspace_host.addWidget(self.start_panel)
        self.workspace_host.addWidget(self.editor)
        self.workspace_host.setCurrentWidget(self.editor)

        self.bottom_search = self._create_search_bar(bottom=True)
        self.document_column = QWidget(self)
        self.document_column_layout = QVBoxLayout(self.document_column)
        self.document_column_layout.setContentsMargins(0, 0, 0, 0)
        self.document_column_layout.setSpacing(6)
        self.document_column_layout.addWidget(self.workspace_host, 1)
        self.document_column_layout.addWidget(self.bottom_search)

        self.tag_library_sidebar = TagLibraryPanel(self, sidebar_mode=True)
        self.tag_library_sidebar.setMinimumWidth(230)
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(self.document_column)
        self.workspace_splitter.addWidget(self.tag_library_sidebar)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.main_layout.addWidget(self.workspace_splitter, 1)

        self.app_status_bar = self.statusBar()
        self.path_label = QLabel("Untitled", self.app_status_bar)
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.operation_mode_label = QLabel("Insert", self.app_status_bar)
        self.operation_mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.operation_mode_label.setMinimumWidth(
            self.operation_mode_label.fontMetrics().horizontalAdvance("Overwrite") + 8
        )
        self.counter_label = QLabel(
            "Ln: 1/1, Col: 1, Char: 0", self.app_status_bar
        )
        self.encoding_label = QLabel("UTF-8", self.app_status_bar)
        self.app_status_bar.addWidget(self.path_label, 1)
        self.app_status_bar.addPermanentWidget(self.operation_mode_label)
        self.app_status_bar.addPermanentWidget(self.counter_label)
        self.app_status_bar.addPermanentWidget(self.encoding_label)

        self.setStyleSheet(
            "QToolButton::menu-indicator { image: none; width: 0px; }"
        )

    def _create_start_panel(self) -> QWidget:
        panel = QWidget(self)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(48, 36, 48, 36)
        outer.addStretch(1)

        card = QWidget(panel)
        card.setMaximumWidth(560)
        card_layout = QVBoxLayout(card)
        heading = QLabel("<h2>Start a Document</h2>", card)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(heading)
        guidance = QLabel(
            "Choose the kind of source you want to create, or open an existing file.",
            card,
        )
        guidance.setWordWrap(True)
        guidance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(guidance)

        form = QFormLayout()
        self.start_type_combo = QComboBox(card)
        for key in DOCUMENT_TYPE_ORDER:
            self.start_type_combo.addItem(profile_for_key(key).label, key)
        self.start_template_combo = QComboBox(card)
        form.addRow("Document type:", self.start_type_combo)
        form.addRow("Template:", self.start_template_combo)
        card_layout.addLayout(form)
        self.start_default_checkbox = QCheckBox(
            "Use this type and template as my default", card
        )
        card_layout.addWidget(self.start_default_checkbox)

        buttons = QHBoxLayout()
        create = QPushButton("Create Document", card)
        open_existing = QPushButton("Open Existing File…", card)
        create.clicked.connect(self._create_from_start_panel)
        open_existing.clicked.connect(self.open_file)
        buttons.addStretch(1)
        buttons.addWidget(create)
        buttons.addWidget(open_existing)
        buttons.addStretch(1)
        card_layout.addLayout(buttons)
        self.start_type_combo.currentIndexChanged.connect(
            self._refresh_start_templates
        )
        self._refresh_start_templates()

        centre = QHBoxLayout()
        centre.addStretch(1)
        centre.addWidget(card)
        centre.addStretch(1)
        outer.addLayout(centre)
        outer.addStretch(2)
        return panel

    def _refresh_start_templates(self) -> None:
        if not hasattr(self, "start_template_combo"):
            return
        language = str(self.start_type_combo.currentData() or "html")
        self.start_template_combo.clear()
        for spec in self.templates_for_language(language):
            self.start_template_combo.addItem(
                spec.name + ("  (Built-in)" if spec.builtin else ""),
                spec.template_id,
            )
        wanted = default_template_id(language)
        index = self.start_template_combo.findData(wanted)
        self.start_template_combo.setCurrentIndex(index if index >= 0 else 0)

    def _action_button(self, text: str, callback) -> QPushButton:
        button = QPushButton(text, self.primary_controls)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(callback)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return button

    def _create_search_bar(self, *, bottom: bool) -> QWidget:
        host = QWidget(self)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        entry = QLineEdit(host)
        entry.setMaxLength(MAX_SEARCH_QUERY_CHARACTERS)
        entry.setPlaceholderText("Find text")
        entry.returnPressed.connect(self.find_next)
        entry.textChanged.connect(self.set_search_query)

        # Restore Nuxpad's persistent search icons. Find remains icon-only
        # in Inline layouts and gains a text label in both Split layouts;
        # Previous and Next remain icon-only in every layout.
        find_button = QPushButton(host)
        previous_button = QToolButton(host)
        next_button = QToolButton(host)
        self._bind_search_icon(
            find_button,
            "edit-find",
            QStyle.StandardPixmap.SP_FileDialogContentsView,
            "Highlight all matches",
            "Find" if bottom else "",
        )
        self._bind_search_icon(
            previous_button,
            "go-previous",
            QStyle.StandardPixmap.SP_ArrowBack,
            "Previous match",
        )
        self._bind_search_icon(
            next_button,
            "go-next",
            QStyle.StandardPixmap.SP_ArrowForward,
            "Next match",
        )

        counter = QLabel("0/0", host)
        counter.setMinimumWidth(48)
        counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        find_button.clicked.connect(self.find_and_refocus)
        previous_button.clicked.connect(self.find_previous)
        next_button.clicked.connect(self.find_next)
        layout.addWidget(entry, 1)
        layout.addWidget(find_button)
        layout.addWidget(counter)
        layout.addWidget(previous_button)
        layout.addWidget(next_button)
        if bottom:
            self.bottom_search_entry = entry
            self.bottom_search_counter = counter
        else:
            self.search_entry = entry
            self.search_counter = counter
        return host

    def _bind_search_icon(
        self,
        target,
        theme_name: str,
        fallback: QStyle.StandardPixmap,
        tooltip: str,
        text: str = "",
    ) -> None:
        target.setText(text)
        target.setToolTip(tooltip)
        target.setAccessibleName(tooltip)
        target.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        target.setIconSize(QSize(16, 16))
        target.setMinimumWidth(68 if text else 30)
        self.search_icon_bindings.append((target, theme_name, fallback))
        self._refresh_search_icon(target, theme_name, fallback)

    def _refresh_search_icon(
        self,
        target,
        theme_name: str,
        fallback: QStyle.StandardPixmap,
    ) -> None:
        target.setIcon(self._search_icon(theme_name, fallback))

    @staticmethod
    def _tint_icon(icon: QIcon, colour: QColor) -> QIcon:
        """Return a monochrome copy suitable for the selected AppImage chrome."""
        if icon.isNull():
            return icon

        tinted_icon = QIcon()
        for logical_size in (16, 20, 24, 32):
            pixmap = icon.pixmap(logical_size, logical_size)
            if pixmap.isNull():
                continue
            tinted = QPixmap(pixmap.size())
            tinted.fill(Qt.GlobalColor.transparent)
            painter = QPainter(tinted)
            painter.drawPixmap(0, 0, pixmap)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn
            )
            painter.fillRect(tinted.rect(), colour)
            painter.end()
            tinted.setDevicePixelRatio(pixmap.devicePixelRatio())
            tinted_icon.addPixmap(tinted)
        return tinted_icon if not tinted_icon.isNull() else icon

    def _search_icon(
        self,
        theme_name: str,
        fallback: QStyle.StandardPixmap,
    ) -> QIcon:
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            icon = self.style().standardIcon(fallback)
        if self.appimage_theme_available:
            theme = self.effective_appimage_theme()
            if theme == "dark":
                return self._tint_icon(icon, QColor("#eff0f1"))
            if theme == "light":
                return self._tint_icon(icon, QColor("#232629"))
        return icon

    def _refresh_search_icons(self) -> None:
        for target, theme_name, fallback in tuple(self.search_icon_bindings):
            try:
                self._refresh_search_icon(target, theme_name, fallback)
            except RuntimeError:
                continue

    def _add_action(
        self,
        menu: QMenu,
        label: str,
        callback,
        shortcut: QKeySequence | str | None = None,
        *,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(label, self)
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _make_file_menu(self) -> None:
        self.file_menu = self.app_menu_bar.addMenu("&File")
        self.new_action = self._add_action(
            self.file_menu, "New", self.new_file, QKeySequence.StandardKey.New
        )
        self._add_action(self.file_menu, "New Type…", self.new_type_file)
        self._add_action(
            self.file_menu, "Default New Document…", self.configure_default_new_document
        )
        self._add_action(
            self.file_menu, "Open...", self.open_file, QKeySequence.StandardKey.Open
        )
        self.file_menu.addSeparator()
        self.document_type_file_menu = self.file_menu.addMenu("Document Type")
        self.document_type_file_actions: dict[str, QAction] = {}
        type_group = QActionGroup(self)
        type_group.setExclusive(True)
        for key in DOCUMENT_TYPE_ORDER:
            action = QAction(profile_for_key(key).label, self, checkable=True)
            action.triggered.connect(
                lambda _checked=False, selected=key: self.set_current_document_type(selected)
            )
            type_group.addAction(action)
            self.document_type_file_menu.addAction(action)
            self.document_type_file_actions[key] = action
        self.file_menu.addSeparator()
        self.save_action = self._add_action(
            self.file_menu, "Save", self.save_file, QKeySequence.StandardKey.Save
        )
        self.save_as_action = self._add_action(
            self.file_menu,
            "Save As...",
            self.save_as_file,
            QKeySequence.StandardKey.SaveAs,
        )
        self.preview_action = self._add_action(
            self.file_menu,
            "Preview in default browser",
            self.preview_in_default_browser,
            QKeySequence("F5"),
        )
        self.file_menu.addSeparator()
        self.properties_action = self._add_action(
            self.file_menu,
            "Properties",
            self.show_properties_dialog,
        )
        self.more_actions_menu = self.file_menu.addMenu("More Actions")
        self.external_action = self._add_action(
            self.more_actions_menu,
            "Open in External Editor",
            self.open_external_editor,
            QKeySequence("Ctrl+Shift+E"),
        )
        self.more_actions_menu.addSeparator()
        self.rename_action = self._add_action(
            self.more_actions_menu,
            "Rename...",
            self.rename_current_file,
            QKeySequence("F2"),
        )
        self.delete_action = self._add_action(
            self.more_actions_menu,
            "Delete File",
            self.delete_file,
        )
        self.more_actions_menu.addSeparator()
        self.duplicate_file_action = self._add_action(
            self.more_actions_menu,
            "Duplicate File",
            self.duplicate_file,
            QKeySequence("Ctrl+Shift+D"),
        )
        self.folder_action = self._add_action(
            self.more_actions_menu,
            "Open Containing Folder",
            self.open_folder,
            QKeySequence("Ctrl+Shift+O"),
        )
        self.file_menu.addSeparator()
        self._add_action(
            self.file_menu,
            "New Window",
            self.new_window,
            QKeySequence("Ctrl+Shift+N"),
        )
        self._add_action(
            self.file_menu, "Exit", self.close, QKeySequence.StandardKey.Quit
        )

    def _make_edit_menu(self) -> None:
        self.edit_menu = self.app_menu_bar.addMenu("&Edit")
        self.undo_action = self._add_action(
            self.edit_menu,
            "Undo",
            self.editor_undo,
            QKeySequence.StandardKey.Undo,
        )
        self.redo_action = self._add_action(
            self.edit_menu, "Redo", self.editor_redo, QKeySequence("Ctrl+Y")
        )
        self.edit_menu.addSeparator()
        self.cut_action = self._add_action(
            self.edit_menu,
            "Cut",
            lambda: self.editor.cut(),
            QKeySequence.StandardKey.Cut,
        )
        self.copy_action = self._add_action(
            self.edit_menu,
            "Copy",
            lambda: self.editor.copy(),
            QKeySequence.StandardKey.Copy,
        )
        self.paste_action = self._add_action(
            self.edit_menu,
            "Paste",
            self.editor.paste_safely,
            QKeySequence.StandardKey.Paste,
        )
        self.delete_text_action = self._add_action(
            self.edit_menu,
            "Delete",
            self.editor.delete_selection_or_character,
            QKeySequence.StandardKey.Delete,
        )
        self.edit_menu.addSeparator()
        self.comment_action = self._add_action(
            self.edit_menu,
            "Toggle Comment",
            self.editor.toggle_comment,
            QKeySequence("Ctrl+/"),
        )
        self.edit_menu.addSeparator()
        self.duplicate_action = self._add_action(
            self.edit_menu,
            "Duplicate Line / Selection",
            self.editor.duplicate_current_line_or_selection,
            QKeySequence("Ctrl+D"),
        )
        self.delete_line_action = self._add_action(
            self.edit_menu,
            "Delete Line",
            self.editor.delete_current_line,
            QKeySequence("Ctrl+Shift+K"),
        )
        self.edit_menu.addSeparator()
        self.select_all_action = self._add_action(
            self.edit_menu,
            "Select All",
            self.editor.select_all_text,
            QKeySequence.StandardKey.SelectAll,
        )
        self.edit_menu.addSeparator()
        self.go_to_line_action = self._add_action(
            self.edit_menu,
            "Go To Line...",
            self.go_to_line,
            QKeySequence("Ctrl+G"),
        )
        self.replace_action = self._add_action(
            self.edit_menu,
            "Replace...",
            self.show_replace_dialog,
            QKeySequence("Ctrl+H"),
        )

        self.focus_find_action = QAction(self)
        self.focus_find_action.setShortcut(QKeySequence.StandardKey.Find)
        self.focus_find_action.triggered.connect(self.focus_search)
        self.addAction(self.focus_find_action)
        self.find_next_action = QAction(self)
        self.find_next_action.setShortcut(QKeySequence("F3"))
        self.find_next_action.triggered.connect(self.find_next)
        self.addAction(self.find_next_action)
        self.find_previous_action = QAction(self)
        self.find_previous_action.setShortcut(QKeySequence("Shift+F3"))
        self.find_previous_action.triggered.connect(self.find_previous)
        self.addAction(self.find_previous_action)
        self.clear_search_action = QAction(self)
        self.clear_search_action.setShortcut(QKeySequence("Esc"))
        self.clear_search_action.triggered.connect(self.clear_search)
        self.addAction(self.clear_search_action)

    def _make_view_menu(self) -> None:
        self.view_menu = self.app_menu_bar.addMenu("&View")
        self.view_only_action = self._add_action(
            self.view_menu,
            "View Only",
            self.toggle_view_only,
            checkable=True,
        )
        self.view_menu.addSeparator()
        self.wrap_action = self._add_action(
            self.view_menu,
            "Word Wrap",
            self.toggle_word_wrap,
            checkable=True,
        )
        self.line_numbers_action = self._add_action(
            self.view_menu,
            "Line Numbers",
            self.toggle_line_numbers,
            checkable=True,
        )
        self.view_menu.addSeparator()
        self.app_menu_action = self._add_action(
            self.view_menu,
            "Menu Only",
            self.toggle_menu_style,
            checkable=True,
        )
        self.status_bar_action = self._add_action(
            self.view_menu,
            "Status Bar",
            self.toggle_status_bar,
            checkable=True,
        )
        self.view_menu.addSeparator()

        library_sidebar_menu = self.view_menu.addMenu("Library")
        library_sidebar_group = QActionGroup(self)
        library_sidebar_group.setExclusive(True)
        self.tag_library_sidebar_actions: dict[str, QAction] = {}
        sidebar_positions = {
            "left": "Left Sidebar",
            "right": "Right Sidebar",
            "disabled": "Floating Only",
        }
        for position, label in sidebar_positions.items():
            action = QAction(label, self, checkable=True)
            action.triggered.connect(
                lambda _checked=False, selected=position: self.set_tag_library_sidebar_position(selected)
            )
            library_sidebar_group.addAction(action)
            library_sidebar_menu.addAction(action)
            self.tag_library_sidebar_actions[position] = action

        self.view_menu.addSeparator()
        layout_menu = self.view_menu.addMenu("Layout")
        layout_group = QActionGroup(self)
        layout_group.setExclusive(True)
        self.layout_actions: dict[int, QAction] = {}
        labels = {
            1: "Inline — Top",
            2: "Inline — Bottom",
            3: "Split — Toolbar Up / Search Down",
            4: "Split — Toolbar Down / Search Top",
        }
        for mode, label in labels.items():
            action = QAction(label, self, checkable=True)
            action.triggered.connect(
                lambda _checked=False, selected=mode: self.set_layout_mode(selected)
            )
            layout_group.addAction(action)
            layout_menu.addAction(action)
            self.layout_actions[mode] = action

        behaviour_menu = self.view_menu.addMenu("File Drag and Drop")
        behaviour_group = QActionGroup(self)
        behaviour_group.setExclusive(True)
        self.drop_behaviour_actions: dict[str, QAction] = {}
        behaviours = {
            "active_window": "Opens on Active Window",
            "new_window": "Opens on New Window",
        }
        for mode, label in behaviours.items():
            action = QAction(label, self, checkable=True)
            action.triggered.connect(
                lambda _checked=False, selected=mode: self.set_drop_open_mode(selected)
            )
            behaviour_group.addAction(action)
            behaviour_menu.addAction(action)
            self.drop_behaviour_actions[mode] = action

        self.view_menu.addSeparator()
        self.dark_editor_action = self._add_action(
            self.view_menu,
            "Dark Editor",
            self.toggle_dark_editor,
            checkable=True,
        )
        self.dark_editor_action.setToolTip(
            "Use the dark editor canvas and matching syntax colours; "
            "turn off for the light editor palette."
        )

        self.appimage_dark_action: QAction | None = None
        if self.appimage_theme_available:
            self.appimage_dark_action = self._add_action(
                self.view_menu,
                "Dark Mode",
                self.toggle_appimage_dark_mode,
                checkable=True,
            )
            self.appimage_dark_action.setToolTip(
                "Use the AppImage-only Breeze-inspired dark theme; "
                "turn off for light mode."
            )
        self._add_action(self.view_menu, "Display Font...", self.choose_font)

    def _make_tags_menu(self) -> None:
        # Internal attribute names stay compatible with the established Timblee
        # implementation, but the user-facing concept is now a language-aware Library.
        self.tags_menu = self.app_menu_bar.addMenu("&Library")
        self.templates_menu = self.tags_menu.addMenu("Templates")
        self._refresh_templates_menu()
        self.tags_menu.addSeparator()

        self.essential_tag_actions: list[QAction] = []
        for key, shortcut in ESSENTIAL_TAGS:
            spec = TAG_BY_KEY[key]
            action = self._add_action(
                self.tags_menu,
                spec.label,
                lambda _checked=False, selected=key: self.insert_library_item_by_key(selected),
                QKeySequence(shortcut),
            )
            action.setToolTip(spec.description)
            self.essential_tag_actions.append(action)
        self.tags_menu.addSeparator()
        self.favourites_menu = self.tags_menu.addMenu("My Favourites")
        self._refresh_favourites_menu()
        self.library_action = self._add_action(
            self.tags_menu,
            "Library...",
            self.toggle_library_visibility,
            QKeySequence("Ctrl+L"),
        )
        self.add_custom_tag_action = self._add_action(
            self.tags_menu,
            "Add Custom HTML Tag...",
            self.add_custom_tag,
        )
        self.remove_custom_tag_action = self._add_action(
            self.tags_menu,
            "Remove Custom HTML Tag...",
            self.remove_custom_tag_via_menu,
        )
        self.import_tags_action = self._add_action(
            self.tags_menu,
            "Import HTML Tags...",
            self.import_tags,
        )
        self.export_tags_action = self._add_action(
            self.tags_menu,
            "Export HTML Tags...",
            self.export_tags,
        )
        self.tags_menu.addSeparator()
        self.auto_close_tags_action = self._add_action(
            self.tags_menu,
            "Auto-complete Closing Tags",
            self.toggle_auto_close_html_tags,
            checkable=True,
        )

    def _make_help_menu(self) -> None:
        self.help_menu = self.app_menu_bar.addMenu("&Help")
        self._add_action(
            self.help_menu,
            "Documentation",
            self.open_documentation,
            QKeySequence("F1"),
        )
        self._add_action(
            self.help_menu, "Keyboard Shortcuts", self.show_shortcuts_dialog
        )
        self.help_menu.addSeparator()
        self._add_action(
            self.help_menu, "GitHub Repository", self.open_github_repository
        )
        self._add_action(
            self.help_menu, "Report an Issue", self.report_an_issue
        )
        self.help_menu.addSeparator()
        about_action = self._add_action(
            self.help_menu, "About Timblee Pad", self.show_about_dialog
        )
        about_action.setMenuRole(QAction.MenuRole.AboutRole)

    def _apply_preferences(self) -> None:
        self.wrap_action.setChecked(self.word_wrap)
        self.line_numbers_action.setChecked(self.show_line_numbers)
        self.app_menu_action.setChecked(self.use_app_menu)
        self.status_bar_action.setChecked(self.show_status_bar)
        self.view_only_action.setChecked(self.view_only)
        self.auto_close_tags_action.setChecked(self.auto_close_html_tags)
        self.dark_editor_action.setChecked(self.dark_editor)
        if self.appimage_dark_action is not None:
            self.appimage_dark_action.setChecked(
                self.effective_appimage_theme() == "dark"
            )
        for mode, action in self.layout_actions.items():
            action.setChecked(mode == self.layout_mode)
        for position, action in self.tag_library_sidebar_actions.items():
            action.setChecked(position == self.tag_library_sidebar_position)
        for mode, action in self.drop_behaviour_actions.items():
            action.setChecked(mode == self.drop_open_mode)
        self.editor.set_word_wrap_enabled(self.word_wrap)
        self.editor.set_line_numbers_visible(self.show_line_numbers)
        self.editor.set_tab_width_spaces(self.tab_width_spaces)
        self.editor.set_view_only(self.view_only)
        self.editor.set_auto_close_html_tags(self.auto_close_html_tags)
        font = QFont(self.font_family, self.font_size)
        try:
            font_weight = QFont.Weight(self.font_weight)
        except (TypeError, ValueError):
            font_weight = QFont.Weight.Normal
            self.font_weight = int(font_weight)
        font.setWeight(font_weight)
        font.setItalic(self.font_italic)
        self.editor.set_editor_font(font)
        self.editor.set_color_scheme("dark" if self.dark_editor else "light")
        self.app_status_bar.setVisible(self.show_status_bar)
        self._apply_menu_style()
        self._apply_tag_library_sidebar_position()
        self._apply_layout_mode()

    def toggle_view_only(self, checked: bool) -> None:
        """Toggle the non-persistent document-editing protection mode."""
        requested = bool(checked)
        if self.view_only and not requested:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle(app_dialog_title("Disable View Only?"))
            dialog.setText(
                "View Only protects this file from accidental changes."
            )
            dialog.setInformativeText(
                "Disabling it will allow editing and could change the file. "
                "Do you want to continue?"
            )
            keep_button = dialog.addButton(
                "Keep View Only", QMessageBox.ButtonRole.RejectRole
            )
            continue_button = dialog.addButton(
                "Continue", QMessageBox.ButtonRole.AcceptRole
            )
            dialog.setDefaultButton(keep_button)
            dialog.setEscapeButton(keep_button)
            dialog.exec()
            if dialog.clickedButton() is not continue_button:
                self.view_only_action.blockSignals(True)
                self.view_only_action.setChecked(True)
                self.view_only_action.blockSignals(False)
                self.show_status("View Only mode remains enabled.")
                self.editor.setFocus()
                return

        self.view_only = requested
        if self.view_only:
            self._view_only_edit_notice_shown = False
        self.editor.set_view_only(self.view_only)
        self.editor.set_auto_close_html_tags(self.auto_close_html_tags)
        self._update_edit_action_state()
        if self.replace_dialog is not None:
            self.replace_dialog.set_view_only(self.view_only)
        self.show_status(
            "View Only mode enabled." if self.view_only else "View Only mode disabled."
        )
        self.editor.setFocus()

    def show_view_only_edit_prompt(self) -> None:
        """Explain the first blocked edit attempt in each View Only session."""
        if not self.view_only:
            return
        self.show_status("Editing is disabled while View Only mode is enabled.")
        if self._view_only_edit_notice_shown:
            return

        # Set this before opening the modal dialog so key auto-repeat or queued
        # input cannot create a cascade of identical prompts.
        self._view_only_edit_notice_shown = True
        QMessageBox.information(
            self,
            app_dialog_title("View Only Mode"),
            "Editing is disabled because View Only mode is enabled.\n\n"
            "To enable editing, open View → View Only, clear the check mark, "
            "and select Continue in the confirmation prompt.",
        )
        self.editor.setFocus()

    def _update_edit_action_state(self) -> None:
        """Keep the Edit menu visible while reflecting document/View Only state."""
        all_edit_actions = (
            self.undo_action,
            self.redo_action,
            self.cut_action,
            self.copy_action,
            self.paste_action,
            self.delete_text_action,
            self.comment_action,
            self.duplicate_action,
            self.delete_line_action,
            self.select_all_action,
            self.go_to_line_action,
            self.replace_action,
        )
        if not self.document_active:
            for action in all_edit_actions:
                action.setEnabled(False)
            return

        # An active document restores the complete Edit menu first. View Only
        # then disables only commands that can modify text; navigation and
        # selection/copy remain available exactly as before.
        for action in all_edit_actions:
            action.setEnabled(True)
        editing_enabled = not self.view_only
        for action in (
            self.undo_action,
            self.redo_action,
            self.cut_action,
            self.paste_action,
            self.delete_text_action,
            self.comment_action,
            self.duplicate_action,
            self.delete_line_action,
            self.replace_action,
        ):
            action.setEnabled(editing_enabled)

    def _update_find_bar_state(self) -> None:
        """Show the saved Find layout at all times, disabled until a document exists."""
        enabled = self.document_active
        self.search_container.setEnabled(enabled)
        self.bottom_search.setEnabled(enabled)
        for action in (
            self.focus_find_action,
            self.find_next_action,
            self.find_previous_action,
            self.clear_search_action,
        ):
            action.setEnabled(enabled)

    # ------------------------------------------------------------------
    # View behavior
    # ------------------------------------------------------------------

    def toggle_word_wrap(self, checked: bool) -> None:
        self.word_wrap = bool(checked)
        self.editor.set_word_wrap_enabled(self.word_wrap)
        self._save_preferences()

    def toggle_line_numbers(self, checked: bool) -> None:
        self.show_line_numbers = bool(checked)
        self.editor.set_line_numbers_visible(self.show_line_numbers)
        self._save_preferences()

    def toggle_menu_style(self, checked: bool) -> None:
        self.use_app_menu = bool(checked)
        self._apply_menu_style()
        self._save_preferences()

    def _apply_menu_style(self) -> None:
        self.app_menu_bar.setVisible(self.use_app_menu)
        self.menu_buttons_container.setVisible(not self.use_app_menu)

    def toggle_status_bar(self, checked: bool) -> None:
        self.show_status_bar = bool(checked)
        self.app_status_bar.setVisible(self.show_status_bar)
        self._save_preferences()

    def set_layout_mode(self, mode: int) -> None:
        if mode not in (1, 2, 3, 4):
            return
        self.layout_mode = mode
        for value, action in self.layout_actions.items():
            action.blockSignals(True)
            action.setChecked(value == mode)
            action.blockSignals(False)
        self._apply_layout_mode()
        self._save_preferences()

    def _apply_layout_mode(self) -> None:
        query = self.search_entry.text() or self.bottom_search_entry.text()
        self.search_entry.blockSignals(True)
        self.bottom_search_entry.blockSignals(True)
        self.search_entry.setText(query)
        self.bottom_search_entry.setText(query)
        self.search_entry.blockSignals(False)
        self.bottom_search_entry.blockSignals(False)

        for widget in (self.toolbar, self.workspace_splitter):
            self.main_layout.removeWidget(widget)
        for widget in (self.workspace_host, self.bottom_search):
            self.document_column_layout.removeWidget(widget)

        split = self.layout_mode in (3, 4)
        self.search_container.setVisible(not split)
        self.bottom_search.setVisible(split)

        # Split modes intentionally keep the Find bar inside the editor column.
        # A left/right Library sidebar therefore spans the full workspace height
        # instead of having the split Find bar run underneath/above the sidebar.
        if self.layout_mode == 4:
            self.document_column_layout.addWidget(self.bottom_search)
            self.document_column_layout.addWidget(self.workspace_host, 1)
        else:
            self.document_column_layout.addWidget(self.workspace_host, 1)
            if self.layout_mode == 3:
                self.document_column_layout.addWidget(self.bottom_search)

        if self.layout_mode in (1, 3):
            self.main_layout.addWidget(self.toolbar)
            self.main_layout.addWidget(self.workspace_splitter, 1)
        else:
            self.main_layout.addWidget(self.workspace_splitter, 1)
            self.main_layout.addWidget(self.toolbar)

    def set_tag_library_sidebar_position(self, position: str) -> None:
        if position not in ("disabled", "left", "right"):
            return
        self.tag_library_sidebar_position = position
        # Choosing a sidebar position is an explicit request to show it. The
        # close button/Ctrl+L may hide it transiently without rewriting this
        # saved preference, so the same side can be restored immediately.
        self.tag_library_sidebar_hidden = False
        for value, action in self.tag_library_sidebar_actions.items():
            action.blockSignals(True)
            action.setChecked(value == position)
            action.blockSignals(False)
        self._apply_tag_library_sidebar_position()
        self._save_preferences()

    def hide_tag_library_sidebar(self) -> None:
        """Hide a configured sidebar without changing its saved side preference."""
        if self.tag_library_sidebar_position not in ("left", "right"):
            return
        self.tag_library_sidebar_hidden = True
        self._apply_tag_library_sidebar_position()

    def toggle_library_visibility(self) -> None:
        """Toggle Library UI according to the saved View → Library preference."""
        if not self.document_active:
            return
        if self.tag_library_sidebar_position in ("left", "right"):
            self.tag_library_sidebar_hidden = not self.tag_library_sidebar_hidden
            self._apply_tag_library_sidebar_position()
            return

        if self.tag_library_dialog is not None and self.tag_library_dialog.isVisible():
            self.tag_library_dialog.close()
            return
        self.show_tag_library()

    def _apply_tag_library_sidebar_position(self) -> None:
        position = self.tag_library_sidebar_position
        sidebar = self.tag_library_sidebar
        content = self.document_column

        # The Library is an insertion surface and remains out of the
        # no-document Start screen, while its configured side is preserved.
        if (
            position == "disabled"
            or self.tag_library_sidebar_hidden
            or not self.document_active
        ):
            sidebar.hide()
            self.workspace_splitter.insertWidget(0, content)
            self.workspace_splitter.setStretchFactor(0, 1)
            return

        sidebar.show()
        if position == "left":
            self.workspace_splitter.insertWidget(0, sidebar)
            self.workspace_splitter.insertWidget(1, content)
            self.workspace_splitter.setStretchFactor(0, 0)
            self.workspace_splitter.setStretchFactor(1, 1)
            self.workspace_splitter.setSizes([300, max(500, self.width() - 300)])
        else:
            self.workspace_splitter.insertWidget(0, content)
            self.workspace_splitter.insertWidget(1, sidebar)
            self.workspace_splitter.setStretchFactor(0, 1)
            self.workspace_splitter.setStretchFactor(1, 0)
            self.workspace_splitter.setSizes([max(500, self.width() - 300), 300])
        sidebar.refresh()

    def set_drop_open_mode(self, mode: str) -> None:
        if mode not in ("active_window", "new_window"):
            return
        self.drop_open_mode = mode
        for value, action in self.drop_behaviour_actions.items():
            action.blockSignals(True)
            action.setChecked(value == mode)
            action.blockSignals(False)
        self._save_preferences()

    def toggle_dark_editor(self, checked: bool) -> None:
        """Switch the editor canvas and syntax palette independently of app chrome."""
        self.dark_editor = bool(checked)
        self.editor.set_color_scheme("dark" if self.dark_editor else "light")
        self._apply_search_highlights()
        self._save_preferences()

    def choose_font(self) -> None:
        current = self.editor.font()
        selected, accepted = QFontDialog.getFont(current, self, app_dialog_title("Display Font"))
        if not accepted:
            return
        self.font_family = selected.family()
        self.font_size = selected.pointSize() if selected.pointSize() > 0 else 10
        self.font_weight = int(selected.weight())
        self.font_italic = selected.italic()
        self.editor.set_editor_font(selected)
        self._save_preferences()

    def effective_appimage_theme(self) -> str:
        """Return the one-launch override or the saved AppImage choice."""
        return self.appimage_theme_override or self.appimage_theme

    def apply_appimage_theme(
        self,
        theme: str,
        *,
        update_actions: bool = True,
    ) -> None:
        """Apply bundled AppImage QSS without changing portable/source builds."""
        if not self.appimage_theme_available:
            return
        if theme not in ("dark", "light", "system"):
            return

        application = QApplication.instance()
        if application is None:
            return

        original_palette = application.property("timbleepad_original_palette")
        if isinstance(original_palette, QPalette):
            application.setPalette(original_palette)

        if theme == "system":
            application.setStyleSheet("")
            original_style = application.property("timbleepad_original_style")
            restored_style = (
                QStyleFactory.create(str(original_style))
                if original_style
                else None
            )
            if restored_style is not None:
                application.setStyle(restored_style)
        else:
            stylesheet_path = self.appimage_theme_files.get(theme)
            if stylesheet_path is None:
                return
            try:
                stylesheet = stylesheet_path.read_text(encoding="utf-8")
            except OSError:
                return
            fusion_style = QStyleFactory.create("Fusion")
            if fusion_style is not None:
                application.setStyle(fusion_style)
            application.setStyleSheet(stylesheet)

        for window in tuple(OPEN_WINDOWS):
            if hasattr(window, "editor"):
                # AppImage chrome and editor canvas are intentionally separate:
                # View → Dark Editor owns the editor/syntax palette.
                window.editor.set_color_scheme(
                    "dark" if getattr(window, "dark_editor", True) else "light"
                )
                window._apply_search_highlights()
            if update_actions:
                action = window.appimage_dark_action
                if action is not None:
                    action.blockSignals(True)
                    action.setChecked(theme == "dark")
                    action.blockSignals(False)
                window._refresh_search_icons()

    def toggle_appimage_dark_mode(self, checked: bool) -> None:
        """Switch every AppImage window between bundled dark and light QSS."""
        if not self.appimage_theme_available:
            return
        selected_theme = "dark" if checked else "light"

        # A menu choice takes precedence over a launch-only override.
        os.environ.pop("TIMBLEEPAD_APPIMAGE_THEME", None)
        for window in tuple(OPEN_WINDOWS):
            window.appimage_theme = selected_theme
            window.appimage_theme_override = None
        self.apply_appimage_theme(selected_theme)
        self._save_preferences()

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------

    def _update_title(self) -> None:
        if not self.document_active:
            self.setWindowTitle(APP_NAME)
            return
        prefix = "*" if self.editor.document().isModified() else ""
        if self.file_path is not None:
            name = self.file_path.name
        else:
            name = f"Untitled {profile_for_key(self.document_type).short_label}"
        self.setWindowTitle(f"{prefix}{name} — {APP_NAME}")

    def _update_status(self) -> None:
        if not self.document_active:
            self.path_label.setText("No document open")
            self.path_label.setToolTip("Choose a document type or open an existing file.")
            self.operation_mode_label.setText("—")
            self.counter_label.setText("Ln: —, Col: —, Char: —")
            self.encoding_label.setText("—")
            for action in getattr(self, "document_type_file_actions", {}).values():
                action.setChecked(False)
            return

        path = str(self.file_path) if self.file_path else f"Untitled {profile_for_key(self.document_type).short_label}"
        self.path_label.setText(path)
        self.path_label.setToolTip(path)
        for key, action in getattr(self, "document_type_file_actions", {}).items():
            action.blockSignals(True)
            action.setChecked(key == self.document_type)
            action.blockSignals(False)

        cursor = self.editor.textCursor()
        document = self.editor.document()
        current_line = cursor.blockNumber() + 1
        total_lines = max(1, document.blockCount())
        current_column = cursor.positionInBlock() + 1
        total_characters = max(0, document.characterCount() - 1)
        self.operation_mode_label.setText(
            "Overwrite" if self.editor.overwriteMode() else "Insert"
        )
        self.counter_label.setText(
            f"Ln: {current_line}/{total_lines}, "
            f"Col: {current_column}, Char: {total_characters}"
        )
        encoding = self.file_encoding.upper().replace("-", "-")
        if self.file_bom:
            encoding += " BOM"
        self.encoding_label.setText(encoding)

    def _on_document_text_changed(self) -> None:
        if self._loading:
            return
        self._update_status()
        self._schedule_search_refresh(preserve_position=True)

    # ------------------------------------------------------------------
    # Document type, startup and templates
    # ------------------------------------------------------------------

    def templates_for_language(self, language: str) -> list[TemplateSpec]:
        return [
            spec
            for spec in (*BUILTIN_TEMPLATES, *self.custom_templates)
            if spec.language == language
        ]

    def template_for_id(self, template_id: str | None) -> TemplateSpec | None:
        if not template_id:
            return None
        builtin = BUILTIN_TEMPLATE_BY_ID.get(template_id)
        if builtin is not None:
            return builtin
        return next(
            (spec for spec in self.custom_templates if spec.template_id == template_id),
            None,
        )

    def add_custom_template(
        self,
        language: str,
        *,
        name: str = "Custom Template",
        content: str = "",
    ) -> TemplateSpec:
        if language not in DOCUMENT_PROFILES:
            language = "html"
        if len(self.custom_templates) >= MAX_CUSTOM_TEMPLATES:
            raise ValueError(f"At most {MAX_CUSTOM_TEMPLATES} custom templates are supported.")
        spec = TemplateSpec(
            f"user:{uuid.uuid4().hex}",
            language,
            name[:MAX_TEMPLATE_NAME].strip() or "Custom Template",
            content[:MAX_TEMPLATE_CHARACTERS],
            builtin=False,
        )
        self.custom_templates.append(spec)
        self._save_preferences()
        self._refresh_templates_menu()
        self._refresh_start_templates()
        return spec

    def update_custom_template(self, template_id: str, name: str, content: str) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Template name cannot be empty.")
        if len(clean_name) > MAX_TEMPLATE_NAME:
            raise ValueError(f"Template names are limited to {MAX_TEMPLATE_NAME} characters.")
        if len(content) > MAX_TEMPLATE_CHARACTERS:
            raise ValueError(
                f"Template content is limited to {MAX_TEMPLATE_CHARACTERS:,} characters."
            )
        if content.count(CURSOR_MARKER) > 1:
            raise ValueError("Use [[cursor]] at most once in a template.")
        for index, spec in enumerate(self.custom_templates):
            if spec.template_id == template_id:
                self.custom_templates[index] = TemplateSpec(
                    spec.template_id,
                    spec.language,
                    clean_name,
                    content,
                    builtin=False,
                )
                self._save_preferences()
                self._refresh_templates_menu()
                self._refresh_start_templates()
                return
        raise ValueError("The custom template no longer exists.")

    def delete_custom_template(self, template_id: str) -> None:
        self.custom_templates = [
            spec for spec in self.custom_templates if spec.template_id != template_id
        ]
        if self.default_new_template == template_id:
            self.default_new_template = (
                default_template_id(self.default_new_type)
                if self.default_new_type in DOCUMENT_PROFILES
                else ""
            )
        self._save_preferences()
        self._refresh_templates_menu()
        self._refresh_start_templates()

    def show_template_manager(self) -> None:
        TemplateManagerDialog(self).exec()

    def _refresh_templates_menu(self) -> None:
        menu = getattr(self, "templates_menu", None)
        if menu is None:
            return
        menu.clear()
        language = self.document_type if self.document_active else "html"
        for spec in self.templates_for_language(language):
            action = QAction(spec.name, self)
            action.setToolTip(
                f"Create a new {profile_for_key(language).short_label} document from this template"
            )
            action.triggered.connect(
                lambda _checked=False, template_id=spec.template_id, lang=language:
                    self.new_document_from_template(lang, template_id)
            )
            menu.addAction(action)
        menu.addSeparator()
        self._add_action(menu, "Manage Templates…", self.show_template_manager)

    def _valid_template_for_language(self, language: str, template_id: str | None) -> TemplateSpec:
        spec = self.template_for_id(template_id)
        if spec is None or spec.language != language:
            spec = self.template_for_id(default_template_id(language))
        assert spec is not None
        return spec

    def _set_default_new_document(self, language: str, template_id: str) -> None:
        spec = self._valid_template_for_language(language, template_id)
        self.default_new_type = language
        self.default_new_template = spec.template_id
        self._save_preferences()

    def _show_start_panel(self) -> None:
        self.document_active = False
        self.workspace_host.setCurrentWidget(self.start_panel)
        self._apply_tag_library_sidebar_position()
        self._apply_layout_mode()
        self._update_find_bar_state()
        self.preview_button.setEnabled(False)
        self.preview_action.setEnabled(False)
        self._update_title()
        self._update_status()
        self._update_file_action_state()
        self._update_edit_action_state()
        self.start_type_combo.setFocus()

    def _show_document_workspace(self) -> None:
        self.workspace_host.setCurrentWidget(self.editor)
        self._apply_tag_library_sidebar_position()
        self._apply_layout_mode()
        self._update_find_bar_state()
        self.preview_button.setVisible(True)
        self._update_file_action_state()
        self._update_edit_action_state()

    def _handle_startup_without_file(self) -> None:
        if self.default_new_type in DOCUMENT_PROFILES:
            spec = self._valid_template_for_language(
                self.default_new_type, self.default_new_template
            )
            self._create_document(self.default_new_type, spec.template_id)
        else:
            self._show_start_panel()

    def _create_from_start_panel(self) -> None:
        language = str(self.start_type_combo.currentData() or "html")
        template_id = str(
            self.start_template_combo.currentData() or default_template_id(language)
        )
        if self.start_default_checkbox.isChecked():
            self._set_default_new_document(language, template_id)
        self._create_document(language, template_id)

    def _create_document(self, language: str, template_id: str) -> None:
        spec = self._valid_template_for_language(language, template_id)
        content = spec.content
        cursor_position = content.find(CURSOR_MARKER)
        if cursor_position >= 0:
            content = content.replace(CURSOR_MARKER, "", 1)
        self._loading = True
        try:
            self.editor.set_source_language(profile_for_key(language).editor_language)
            self.editor.load_text(content)
        finally:
            self._loading = False
        self.document_active = True
        self.document_type = language
        self.file_path = None
        self.file_encoding = "utf-8"
        self.file_bom = b""
        self.file_newline = "\n"
        self.file_disk_snapshot = None
        self.clear_search()
        if cursor_position >= 0:
            cursor = self.editor.textCursor()
            cursor.setPosition(min(cursor_position, max(0, self.editor.document().characterCount() - 1)))
            self.editor.setTextCursor(cursor)
        self._show_document_workspace()
        self._refresh_templates_menu()
        self._refresh_favourites_menu()
        self._refresh_tag_library_views()
        self._update_title()
        self._update_status()
        self._update_file_action_state()
        self._update_edit_action_state()
        self.editor.setFocus()

    def new_document_from_template(self, language: str, template_id: str) -> None:
        if self.document_active and not self.check_save_changes():
            return
        self._create_document(language, template_id)

    def new_file(self) -> None:
        if self.document_active and not self.check_save_changes():
            return
        if self.default_new_type in DOCUMENT_PROFILES:
            spec = self._valid_template_for_language(
                self.default_new_type, self.default_new_template
            )
            self._create_document(self.default_new_type, spec.template_id)
            return
        self.new_type_file(skip_save_check=True)

    def new_type_file(self, _checked: bool = False, *, skip_save_check: bool = False) -> None:
        if not skip_save_check and self.document_active and not self.check_save_changes():
            return
        dialog = NewDocumentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            if not self.document_active:
                self._show_start_panel()
            return
        language = dialog.selected_language()
        template_id = dialog.selected_template_id()
        if dialog.default_checkbox.isChecked():
            self._set_default_new_document(language, template_id)
        self._create_document(language, template_id)

    def configure_default_new_document(self) -> None:
        dialog = DefaultNewDocumentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        language = str(dialog.type_combo.currentData())
        if language == "ask":
            self.default_new_type = "ask"
            self.default_new_template = ""
        else:
            template_id = str(
                dialog.template_combo.currentData() or default_template_id(language)
            )
            spec = self._valid_template_for_language(language, template_id)
            self.default_new_type = language
            self.default_new_template = spec.template_id
        self._save_preferences()
        self.show_status(
            "New documents will ask for a type."
            if self.default_new_type == "ask"
            else f"Default New document: {profile_for_key(self.default_new_type).label}."
        )

    def set_current_document_type(self, language: str) -> None:
        if not self.document_active or language not in DOCUMENT_PROFILES:
            return
        if language == self.document_type:
            return
        old = self.document_type
        self.document_type = language
        self.editor.set_source_language(profile_for_key(language).editor_language)
        self._refresh_templates_menu()
        self._refresh_favourites_menu()
        self._refresh_tag_library_views()
        self._update_file_action_state()
        self._update_title()
        self._update_status()
        message = (
            f"Document interpretation changed from {profile_for_key(old).short_label} "
            f"to {profile_for_key(language).short_label}; text was not modified."
        )
        if self.file_path is not None and not extension_matches_type(self.file_path, language):
            message += f" Filename remains {self.file_path.name}; Save As will suggest the matching extension."
        self.show_status(message)

    def check_save_changes(self) -> bool:
        if not self.document_active:
            return True
        if not self.editor.document().isModified():
            return True
        answer = QMessageBox.question(
            self,
            app_dialog_title("Unsaved Changes"),
            "Do you want to save changes?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_file()
        if answer == QMessageBox.StandardButton.Discard:
            return True
        return False

    def new_window(self) -> "TimbleePadWindow":
        window = TimbleePadWindow()
        window.show()
        return window

    def open_file(self) -> bool:
        start = str(self.file_path.parent if self.file_path else Path.home())
        selected, _filter = QFileDialog.getOpenFileName(
            self, app_dialog_title("Open Source File"), start, WEB_FILE_FILTER
        )
        if not selected:
            return False
        return self.load_file(selected)

    def show_unsupported_file_dialog(self, rejected_count: int = 1) -> None:
        """Explain Timblee Pad's deliberately small source-format scope."""
        count = max(1, int(rejected_count))
        title = "Unsupported File Type" if count == 1 else "Unsupported File Types"
        detail = (
            "The selected item was not opened."
            if count == 1
            else f"{count} unsupported items were not opened."
        )
        QMessageBox.information(
            self,
            app_dialog_title(title),
            f"Timblee Pad {APP_VERSION} opens HTML, CSS and XML/XSD/XSL/XSLT source files."
            f"\n\n{detail}",
            QMessageBox.StandardButton.Ok,
        )

    def load_file(
        self,
        file_path: str | Path,
        *,
        check_changes: bool = True,
        show_error: bool = True,
    ) -> bool:
        path = absolute_user_path(file_path)
        if path.suffix.casefold() not in SUPPORTED_WEB_SUFFIXES:
            if show_error:
                self.show_unsupported_file_dialog()
            return False

        try:
            data, snapshot = read_regular_file(path, MAX_FILE_SIZE)
            text, encoding, bom = self._decode_source(data, path)
        except FileTooLargeError:
            if show_error:
                QMessageBox.warning(
                    self,
                    app_dialog_title("File Too Large"),
                    "Timblee Pad does not open files larger than 25 MiB.",
                )
            return False
        except UnsupportedFileError as error:
            if show_error:
                QMessageBox.warning(self, app_dialog_title("Unsupported File"), str(error))
            return False
        except FileStateChangedError as error:
            if show_error:
                QMessageBox.warning(self, app_dialog_title("File Changed"), str(error))
            return False
        except UnicodeDecodeError as error:
            if show_error:
                QMessageBox.warning(self, app_dialog_title("Encoding Error"), str(error))
            return False
        except (OSError, MemoryError) as error:
            if show_error:
                QMessageBox.critical(self, app_dialog_title("Open Failed"), str(error))
            return False

        if self._looks_binary_text(text):
            if show_error:
                QMessageBox.warning(
                    self,
                    app_dialog_title("Unsupported File"),
                    "The file appears to contain binary control data.",
                )
            return False
        if check_changes and not self.check_save_changes():
            return False

        newline = self._detect_newline_style(text)
        normalised = text.replace("\r\n", "\n").replace("\r", "\n")
        document_type = document_type_for_path(path)
        if document_type is None:
            if show_error:
                self.show_unsupported_file_dialog()
            return False
        self._loading = True
        try:
            self.document_type = document_type
            self.editor.set_source_language(
                profile_for_key(document_type).editor_language
            )
            self.editor.load_text(normalised)
        except MemoryError:
            if show_error:
                QMessageBox.critical(
                    self,
                    app_dialog_title("File Too Large"),
                    "The decoded file is too large to load safely.",
                )
            return False
        finally:
            self._loading = False

        self.file_path = path
        self.document_active = True
        self.file_encoding = encoding
        self.file_bom = bom
        self.file_newline = newline
        self.file_disk_snapshot = snapshot
        self.clear_search()
        self._show_document_workspace()
        self._refresh_templates_menu()
        self._refresh_favourites_menu()
        self._refresh_tag_library_views()
        self._update_title()
        self._update_status()
        self._update_file_action_state()
        self.editor.setFocus()
        return True

    def _decode_source(
        self,
        data: bytes,
        path: Path,
    ) -> tuple[str, str, bytes]:
        """Decode supported text source while preserving declared encodings where practical."""
        bom_map = (
            (codecs.BOM_UTF32_LE, "utf-32-le"),
            (codecs.BOM_UTF32_BE, "utf-32-be"),
            (codecs.BOM_UTF8, "utf-8"),
            (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be"),
        )
        for bom, encoding in bom_map:
            if data.startswith(bom):
                return data[len(bom):].decode(encoding, errors="strict"), encoding, bom

        declared: str | None = None
        header = data[:8192].decode("latin-1", errors="ignore")
        suffix_type = document_type_for_path(path)
        if suffix_type == "css":
            match = re.search(r'^\s*@charset\s+["\']([^"\']+)["\']\s*;', header, re.IGNORECASE)
            if match:
                declared = match.group(1).strip()
        elif suffix_type == "xml":
            match = re.search(r'<\?xml\s+[^?]*encoding\s*=\s*["\']([^"\']+)["\']', header, re.IGNORECASE)
            if match:
                declared = match.group(1).strip()
        else:
            match = re.search(r'<meta\s+[^>]*charset\s*=\s*["\']?([^\s"\'>/;]+)', header, re.IGNORECASE)
            if match:
                declared = match.group(1).strip()
            else:
                match = re.search(r'<meta\s+[^>]*content\s*=\s*["\'][^"\']*charset\s*=\s*([^\s"\';>]+)', header, re.IGNORECASE)
                if match:
                    declared = match.group(1).strip()

        candidates: list[str] = []
        if declared:
            candidates.append(declared)
        candidates.append("utf-8")
        for encoding in candidates:
            try:
                codecs.lookup(encoding)
                return data.decode(encoding, errors="strict"), encoding, b""
            except (LookupError, UnicodeDecodeError):
                continue

        system_encoding = locale.getpreferredencoding(False) or "utf-8"
        choices = [
            "Windows-1252",
            "ISO-8859-1",
            "UTF-16 LE",
            "UTF-16 BE",
            f"System encoding ({system_encoding})",
        ]
        selected, accepted = QInputDialog.getItem(
            self,
            app_dialog_title("Choose Source Encoding"),
            f"{path.name} could not be decoded with its declared encoding or UTF-8.\\n\\nOpen using:",
            choices,
            0,
            False,
        )
        if not accepted:
            raise UnicodeDecodeError("utf-8", data, 0, 1, "opening cancelled")
        encoding = {
            "Windows-1252": "cp1252",
            "ISO-8859-1": "iso-8859-1",
            "UTF-16 LE": "utf-16-le",
            "UTF-16 BE": "utf-16-be",
            f"System encoding ({system_encoding})": system_encoding,
        }[selected]
        return data.decode(encoding, errors="strict"), encoding, b""

    @staticmethod
    def _looks_binary_text(text: str) -> bool:
        if "\x00" in text:
            return True
        if not text:
            return False
        controls = sum(
            1
            for char in text
            if ord(char) < 32 and char not in "\t\n\r\f\b"
        )
        return controls / len(text) > 0.02

    @staticmethod
    def _detect_newline_style(content: str) -> str:
        crlf = content.count("\r\n")
        lf = content.count("\n") - crlf
        cr = content.count("\r") - crlf
        count, newline = max(((crlf, "\r\n"), (lf, "\n"), (cr, "\r")))
        return newline if count else "\n"

    @staticmethod
    def _default_created_file_mode() -> int:
        if sys.platform == "win32":
            return 0o666
        current_umask = os.umask(0)
        os.umask(current_umask)
        return 0o666 & ~current_umask

    def _external_change_action(self) -> tuple[str, FileSnapshot | None]:
        if self.file_path is None:
            return "overwrite", None
        try:
            _data, current = read_regular_file(self.file_path, MAX_FILE_SIZE)
        except FileNotFoundError:
            current = None
        except OSError as error:
            QMessageBox.warning(
                self,
                app_dialog_title("File Check Failed"),
                f"Timblee Pad could not verify the file before saving:\n\n{error}",
            )
            return "cancel", None

        if current == self.file_disk_snapshot:
            return "overwrite", current

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(app_dialog_title("File Changed on Disk"))
        dialog.setText("This file changed on disk after Timblee Pad opened or saved it.")
        dialog.setInformativeText(
            "Reload discards the current Timblee Pad edits. Save As keeps both versions. "
            "Overwrite replaces the disk copy."
        )
        reload_button = dialog.addButton(
            "Reload",
            QMessageBox.ButtonRole.AcceptRole,
        )
        save_as_button = dialog.addButton(
            "Save As",
            QMessageBox.ButtonRole.ActionRole,
        )
        overwrite_button = dialog.addButton(
            "Overwrite",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is reload_button:
            return "reload", current
        if clicked is save_as_button:
            return "save_as", current
        if clicked is overwrite_button:
            return "overwrite", current
        return "cancel", current

    def save_file(self, *, check_external_change: bool = True) -> bool:
        if not self.document_active:
            self.show_status("Create a document before saving.")
            return False
        if self.file_path is None:
            return self.save_as_file()
        if not extension_matches_type(self.file_path, self.document_type):
            profile = profile_for_key(self.document_type)
            dialog = QMessageBox(self)
            dialog.setWindowTitle(app_dialog_title("Document Type and Filename Differ"))
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setText(
                f"Timblee Pad is treating this document as {profile.label}, "
                f"but its filename is '{self.file_path.name}'."
            )
            dialog.setInformativeText(
                "Saving anyway keeps the existing filename. Save As lets Timblee Pad "
                f"suggest {profile.default_extension}."
            )
            save_anyway = dialog.addButton("Save Anyway", QMessageBox.ButtonRole.AcceptRole)
            save_as = dialog.addButton("Save As…", QMessageBox.ButtonRole.ActionRole)
            cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
            dialog.setDefaultButton(cancel)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is save_as:
                return self.save_as_file()
            if clicked is not save_anyway:
                return False

        expected = self.file_disk_snapshot
        if check_external_change:
            action, expected = self._external_change_action()
            if action == "reload":
                self.load_file(self.file_path, check_changes=False)
                return False
            if action == "save_as":
                return self.save_as_file()
            if action != "overwrite":
                return False

        content = self.editor.toPlainText()
        if self.file_newline != "\n":
            content = content.replace("\n", self.file_newline)
        try:
            payload = self.file_bom + content.encode(
                self.file_encoding,
                errors="strict",
            )
        except UnicodeEncodeError as error:
            QMessageBox.critical(
                self,
                app_dialog_title("Encoding Error"),
                f"The edited text cannot be represented as {self.file_encoding}:\n\n{error}",
            )
            return False
        if len(payload) > MAX_FILE_SIZE:
            QMessageBox.warning(
                self,
                app_dialog_title("File Too Large"),
                "The edited file exceeds Timblee Pad's 25 MiB safety limit and was not saved.",
            )
            return False

        temporary: Path | None = None
        descriptor: int | None = None
        try:
            if expected is None:
                if path_lexists(self.file_path):
                    raise FileStateChangedError(
                        "A file appeared at the save location. Saving was cancelled."
                    )
                write_path = self.file_path
                existing_mode = self._default_created_file_mode()
            else:
                if current_file_state(self.file_path) != expected.state:
                    raise FileStateChangedError(
                        "The file changed again before Timblee Pad could save it."
                    )
                write_path = (
                    validated_symlink_target(self.file_path, expected.state)
                    if expected.state.is_symlink
                    else self.file_path
                )
                existing_mode = expected.state.target_mode & 0o7777

            parent = write_path.parent
            descriptor, raw_path = tempfile.mkstemp(
                prefix=f".{write_path.name}.timbleepad-",
                suffix=".tmp",
                dir=parent,
            )
            temporary = Path(raw_path)
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, existing_mode)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            if expected is None:
                install_new_file_from_temp(temporary, write_path)
                temporary = None
            else:
                if current_file_state(self.file_path) != expected.state:
                    raise FileStateChangedError(
                        "The file changed again before Timblee Pad could replace it."
                    )
                if expected.state.is_symlink and validated_symlink_target(
                    self.file_path,
                    expected.state,
                ) != write_path:
                    raise FileStateChangedError(
                        "The symbolic-link target changed before replacement."
                    )
                os.replace(temporary, write_path)
                temporary = None
            fsync_directory(parent)
        except FileStateChangedError as error:
            QMessageBox.warning(self, app_dialog_title("Save Cancelled"), str(error))
            return False
        except OSError as error:
            QMessageBox.critical(self, app_dialog_title("Save Failed"), str(error))
            return False
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

        try:
            self.file_disk_snapshot = snapshot_from_payload(
                self.file_path,
                payload,
            )
        except OSError:
            self.file_disk_snapshot = None
        self.editor.mark_clean()
        self._update_title()
        self._update_status()
        self._update_file_action_state()
        self.show_status(f"Saved {self.file_path.name}")
        return True

    def save_as_file(self) -> bool:
        if not self.document_active:
            self.show_status("Create a document before saving.")
            return False
        profile = profile_for_key(self.document_type)
        default_name = self.file_path if self.file_path else Path.home() / f"untitled{profile.default_extension}"
        selected, _selected_filter = QFileDialog.getSaveFileName(
            self,
            app_dialog_title("Save Source File"),
            str(default_name),
            WEB_FILE_FILTER,
        )
        if not selected:
            return False
        path = absolute_user_path(selected)
        if not path.suffix:
            path = path.with_suffix(profile.default_extension)
        target_type = document_type_for_path(path)
        if target_type is None:
            QMessageBox.warning(
                self,
                app_dialog_title("Unsupported Source Type"),
                "Use an HTML, CSS or XML/XSD/XSL/XSLT filename extension.",
            )
            return False

        destination_snapshot: FileSnapshot | None = None
        if path_lexists(path):
            try:
                _data, destination_snapshot = read_regular_file(
                    path,
                    MAX_FILE_SIZE,
                )
            except FileTooLargeError:
                QMessageBox.warning(
                    self,
                    app_dialog_title("File Too Large"),
                    "The destination exceeds Timblee Pad's 25 MiB safety limit.",
                )
                return False
            except OSError as error:
                QMessageBox.critical(self, app_dialog_title("Save As Failed"), str(error))
                return False
            answer = QMessageBox.question(
                self,
                app_dialog_title("Replace File"),
                f"Replace '{path.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        old_path = self.file_path
        old_snapshot = self.file_disk_snapshot
        old_type = self.document_type
        self.file_path = path
        self.document_type = target_type
        self.editor.set_source_language(profile_for_key(target_type).editor_language)
        self.file_disk_snapshot = destination_snapshot
        if not self.save_file(check_external_change=False):
            self.file_path = old_path
            self.document_type = old_type
            self.editor.set_source_language(profile_for_key(old_type).editor_language)
            self.file_disk_snapshot = old_snapshot
            self._update_title()
            self._update_status()
            self._update_file_action_state()
            return False
        self._refresh_templates_menu()
        self._refresh_favourites_menu()
        self._refresh_tag_library_views()
        return True

    @staticmethod
    def _default_duplicate_path(source: Path) -> Path:
        """Return the first unused sibling name for a duplicate file."""
        candidate = source.with_name(f"{source.stem} copy{source.suffix}")
        number = 2
        while path_lexists(candidate):
            candidate = source.with_name(
                f"{source.stem} copy {number}{source.suffix}"
            )
            number += 1
        return candidate

    def duplicate_file(self) -> bool:
        """Write a safe copy of the current editor contents to a new path."""
        if self.file_path is None:
            QMessageBox.information(
                self,
                app_dialog_title("Duplicate File"),
                "Save the file before duplicating it.",
            )
            return False

        source = self.file_path
        try:
            _disk_payload, source_snapshot = read_regular_file(
                source,
                MAX_FILE_SIZE,
            )
        except OSError as error:
            QMessageBox.warning(
                self,
                app_dialog_title("Duplicate Cancelled"),
                str(error),
            )
            return False

        if (
            self.file_disk_snapshot is not None
            and source_snapshot != self.file_disk_snapshot
        ):
            answer = QMessageBox.question(
                self,
                app_dialog_title("File Changed on Disk"),
                "The source file changed on disk after Timblee Pad opened or saved it.\n\n"
                "Duplicate the current editor contents anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        selected, _selected_filter = QFileDialog.getSaveFileName(
            self,
            app_dialog_title("Duplicate Source File"),
            str(self._default_duplicate_path(source)),
            WEB_FILE_FILTER,
        )
        if not selected:
            return False

        destination = absolute_user_path(selected)
        if not destination.suffix:
            destination = destination.with_suffix(source.suffix)
        if destination.suffix.casefold() != source.suffix.casefold():
            QMessageBox.warning(
                self,
                app_dialog_title("Duplicate Cancelled"),
                f"The duplicate must keep the {source.suffix} file type.",
            )
            return False
        if destination == source:
            QMessageBox.warning(
                self,
                app_dialog_title("Duplicate Cancelled"),
                "Choose a different filename from the current file.",
            )
            return False

        content = self.editor.toPlainText()
        if self.file_newline != "\n":
            content = content.replace("\n", self.file_newline)
        try:
            payload = self.file_bom + content.encode(
                self.file_encoding,
                errors="strict",
            )
        except UnicodeEncodeError as error:
            QMessageBox.critical(
                self,
                app_dialog_title("Encoding Error"),
                f"The current text cannot be represented as {self.file_encoding}:\n\n{error}",
            )
            return False
        if len(payload) > MAX_FILE_SIZE:
            QMessageBox.warning(
                self,
                app_dialog_title("File Too Large"),
                "The duplicate would exceed Timblee Pad's 25 MiB safety limit.",
            )
            return False

        destination_snapshot: FileSnapshot | None = None
        if path_lexists(destination):
            try:
                _existing_payload, destination_snapshot = read_regular_file(
                    destination,
                    MAX_FILE_SIZE,
                )
            except OSError as error:
                QMessageBox.warning(
                    self,
                    app_dialog_title("Duplicate Cancelled"),
                    str(error),
                )
                return False
            if (
                destination_snapshot.state.target_device
                == source_snapshot.state.target_device
                and destination_snapshot.state.target_inode
                == source_snapshot.state.target_inode
            ):
                QMessageBox.warning(
                    self,
                    app_dialog_title("Duplicate Cancelled"),
                    "The selected destination refers to the current file.",
                )
                return False
            answer = QMessageBox.question(
                self,
                app_dialog_title("Replace File"),
                f"Replace '{destination.name}' with the duplicate?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        temporary: Path | None = None
        descriptor: int | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix=f".{destination.name}.timbleepad-duplicate-",
                suffix=".tmp",
                dir=destination.parent,
            )
            temporary = Path(raw_path)
            if hasattr(os, "fchmod"):
                os.fchmod(
                    descriptor,
                    source_snapshot.state.target_mode & 0o7777,
                )
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

            if destination_snapshot is None:
                install_new_file_from_temp(temporary, destination)
                temporary = None
            else:
                if current_file_state(destination) != destination_snapshot.state:
                    raise FileStateChangedError(
                        "The destination changed after the replacement confirmation."
                    )
                os.replace(temporary, destination)
                temporary = None
            fsync_directory(destination.parent)
        except FileStateChangedError as error:
            QMessageBox.warning(
                self,
                app_dialog_title("Duplicate Cancelled"),
                str(error),
            )
            return False
        except OSError as error:
            QMessageBox.critical(
                self,
                app_dialog_title("Duplicate Failed"),
                str(error),
            )
            return False
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

        self.show_status(f"Created duplicate {destination.name}")
        return True

    def rename_current_file(self) -> bool:
        if self.file_path is None:
            QMessageBox.information(
                self,
                app_dialog_title("Rename"),
                "Save the file before renaming it.",
            )
            return False
        if self.editor.document().isModified() and not self.save_file():
            return False

        current = self.file_path
        try:
            source_snapshot = (
                self.file_disk_snapshot
                if self.file_disk_snapshot is not None
                else read_regular_file(current, MAX_FILE_SIZE)[1]
            )
        except OSError as error:
            QMessageBox.warning(self, app_dialog_title("Rename Cancelled"), str(error))
            return False

        new_name, accepted = QInputDialog.getText(
            self,
            app_dialog_title("Rename Source File"),
            "New filename:",
            text=current.name,
        )
        if not accepted:
            return False
        new_name = new_name.strip()
        if not new_name:
            return False
        candidate = Path(new_name)
        if (
            candidate.name != new_name
            or candidate.suffix.casefold() not in SUPPORTED_WEB_SUFFIXES
        ):
            QMessageBox.warning(
                self,
                app_dialog_title("Invalid Filename"),
                "Use an HTML, CSS or XML/XSD/XSL/XSLT filename without folder separators.",
            )
            return False

        destination = current.with_name(new_name)
        if destination == current:
            return True

        destination_snapshot: FileSnapshot | None = None
        if path_lexists(destination):
            try:
                destination_snapshot = read_regular_file(
                    destination,
                    MAX_FILE_SIZE,
                )[1]
            except OSError as error:
                QMessageBox.warning(self, app_dialog_title("Rename Cancelled"), str(error))
                return False
            answer = QMessageBox.question(
                self,
                app_dialog_title("Replace File"),
                f"Replace '{destination.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        try:
            if current_file_state(current) != source_snapshot.state:
                raise FileStateChangedError(
                    "The source file changed before it could be renamed."
                )
            if destination_snapshot is None:
                rename_path_no_replace(current, destination)
            else:
                if current_file_state(destination) != destination_snapshot.state:
                    raise FileStateChangedError(
                        "The destination changed after the confirmation dialog."
                    )
                os.replace(current, destination)
            fsync_directory(destination.parent)
        except FileStateChangedError as error:
            QMessageBox.warning(self, app_dialog_title("Rename Cancelled"), str(error))
            return False
        except OSError as error:
            QMessageBox.critical(self, app_dialog_title("Rename Failed"), str(error))
            return False

        self.file_path = destination
        renamed_type = document_type_for_path(destination)
        if renamed_type is not None:
            self.document_type = renamed_type
            self.editor.set_source_language(
                profile_for_key(renamed_type).editor_language
            )
            self._refresh_templates_menu()
            self._refresh_favourites_menu()
            self._refresh_tag_library_views()
        try:
            self.file_disk_snapshot = FileSnapshot(
                state=current_file_state(self.file_path),
                digest=source_snapshot.digest,
            )
        except OSError:
            self.file_disk_snapshot = None
        self._update_title()
        self._update_status()
        self._update_file_action_state()
        self.show_status(f"Renamed file to {destination.name}")
        return True

    def delete_file(self) -> bool:
        if self.file_path is None:
            return False
        original_path = self.file_path
        if self.editor.document().isModified() and not self.check_save_changes():
            return False
        if self.file_path != original_path:
            QMessageBox.information(
                self,
                app_dialog_title("Delete Cancelled"),
                "The active file changed during Save As, so nothing was deleted.",
            )
            return False
        try:
            expected_state = (
                self.file_disk_snapshot.state
                if self.file_disk_snapshot is not None
                else current_file_state(original_path)
            )
        except OSError as error:
            QMessageBox.warning(self, app_dialog_title("Delete Cancelled"), str(error))
            return False
        answer = QMessageBox.question(
            self,
            app_dialog_title("Delete Source File"),
            f"Permanently delete '{original_path.name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        if not path_identity_matches(original_path, expected_state):
            QMessageBox.warning(
                self,
                app_dialog_title("Delete Cancelled"),
                "The file was replaced after the confirmation dialog. Nothing was deleted.",
            )
            return False
        try:
            original_path.unlink()
            fsync_directory(original_path.parent)
        except FileNotFoundError:
            pass
        except OSError as error:
            QMessageBox.critical(self, app_dialog_title("Delete Failed"), str(error))
            return False
        self.new_file_after_removal()
        return True

    def new_file_after_removal(self) -> None:
        self._loading = True
        try:
            self.editor.load_text("")
        finally:
            self._loading = False
        self.file_path = None
        self.file_disk_snapshot = None
        self.document_active = False
        self.clear_search()
        self._handle_startup_without_file()
        self.show_status("File deleted from disk.")

    def set_search_query(self, query: str) -> None:
        query = query[:MAX_SEARCH_QUERY_CHARACTERS]
        self.search_query = query
        for entry in (self.search_entry, self.bottom_search_entry):
            if entry.text() != query:
                entry.blockSignals(True)
                entry.setText(query)
                entry.blockSignals(False)
        self._schedule_search_refresh(preserve_position=False)

    def set_search_case_sensitive(self, enabled: bool) -> None:
        self.search_case_sensitive = bool(enabled)
        self._schedule_search_refresh(preserve_position=False)

    def _schedule_search_refresh(self, *, preserve_position: bool) -> None:
        if not self.search_query:
            self._search_refresh_timer.stop()
            self.search_matches = []
            self.search_match_starts = []
            self.search_match_ends = []
            self.current_search_index = -1
            self.search_results_truncated = False
            self.editor.clear_search_selections()
            self._update_search_counter()
            return
        if self._search_refresh_timer.isActive():
            self._pending_search_preserve_position = (
                self._pending_search_preserve_position and preserve_position
            )
        else:
            self._pending_search_preserve_position = preserve_position
        self._search_refresh_timer.start()

    def _run_pending_search_refresh(self) -> None:
        preserve = self._pending_search_preserve_position
        self._pending_search_preserve_position = False
        self._refresh_search_matches(preserve_position=preserve)

    def _refresh_search_matches(self, *, preserve_position: bool) -> None:
        self._search_refresh_timer.stop()
        query = self.search_query
        if not query:
            self.search_matches = []
            self.search_match_starts = []
            self.search_match_ends = []
            self.current_search_index = -1
            self.search_results_truncated = False
            self.editor.clear_search_selections()
            self._update_search_counter()
            return

        old_position = None
        if preserve_position and 0 <= self.current_search_index < len(
            self.search_matches
        ):
            old_position = self.search_matches[self.current_search_index][0]

        text = self.editor.toPlainText()
        flags = 0 if self.search_case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(query), flags)
        matches: list[tuple[int, int]] = []
        self.search_results_truncated = False
        for match in pattern.finditer(text):
            if len(matches) >= MAX_SEARCH_MATCHES:
                self.search_results_truncated = True
                break
            matches.append(match.span())
        self.search_matches = matches
        self.search_match_starts = [start for start, _end in matches]
        self.search_match_ends = [end for _start, end in matches]

        if not matches:
            self.current_search_index = -1
        elif old_position is not None:
            insertion = bisect.bisect_left(self.search_match_starts, old_position)
            candidates = [
                index
                for index in (insertion - 1, insertion)
                if 0 <= index < len(matches)
            ]
            self.current_search_index = min(
                candidates,
                key=lambda index: abs(
                    self.search_match_starts[index] - old_position
                ),
            )
        elif not preserve_position or self.current_search_index >= len(matches):
            self.current_search_index = -1

        self._apply_search_highlights()
        self._update_search_counter()

    def _apply_search_highlights(self) -> None:
        selections = []
        (
            current_background,
            current_foreground,
            match_background,
            match_foreground,
        ) = self.editor.search_highlight_colors()
        for index, (start, end) in enumerate(self.search_matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(self.editor.document())
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            if index == self.current_search_index:
                selection.format.setBackground(QColor(current_background))
                selection.format.setForeground(QColor(current_foreground))
            else:
                selection.format.setBackground(QColor(match_background))
                selection.format.setForeground(QColor(match_foreground))
            selections.append(selection)
        self.editor.set_search_selections(selections)

    def _update_search_counter(self) -> None:
        total = len(self.search_matches)
        current = self.current_search_index + 1 if self.current_search_index >= 0 else 0
        suffix = "+" if self.search_results_truncated else ""
        label = f"{current}/{total}{suffix}"
        self.search_counter.setText(label)
        self.bottom_search_counter.setText(label)

    def find_and_refocus(self) -> None:
        self._refresh_search_matches(preserve_position=False)
        self.find_next()

    def find_next(self) -> bool:
        if not self.search_query:
            self.focus_search()
            return False
        if self._search_refresh_timer.isActive() or not self.search_matches:
            self._refresh_search_matches(preserve_position=False)
        if not self.search_matches:
            self.show_status("No matches found.")
            return False
        if self.current_search_index >= 0:
            next_index = (self.current_search_index + 1) % len(self.search_matches)
        else:
            cursor_position = self.editor.textCursor().selectionEnd()
            next_index = bisect.bisect_left(
                self.search_match_starts,
                cursor_position,
            )
            if next_index >= len(self.search_matches):
                next_index = 0
        self._select_search_match(next_index)
        return True

    def find_previous(self) -> bool:
        if not self.search_query:
            self.focus_search()
            return False
        if self._search_refresh_timer.isActive() or not self.search_matches:
            self._refresh_search_matches(preserve_position=False)
        if not self.search_matches:
            self.show_status("No matches found.")
            return False
        if self.current_search_index >= 0:
            index = (self.current_search_index - 1) % len(self.search_matches)
        else:
            cursor_position = self.editor.textCursor().selectionStart()
            index = bisect.bisect_right(
                self.search_match_ends,
                cursor_position,
            ) - 1
            if index < 0:
                index = len(self.search_matches) - 1
        self._select_search_match(index)
        return True

    def _select_search_match(self, index: int) -> None:
        if not (0 <= index < len(self.search_matches)):
            return
        self.current_search_index = index
        start, end = self.search_matches[index]
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.editor.setFocus()
        self._apply_search_highlights()
        self._update_search_counter()

    def clear_search(self) -> None:
        self._search_refresh_timer.stop()
        self.search_query = ""
        self.search_matches = []
        self.search_match_starts = []
        self.search_match_ends = []
        self.current_search_index = -1
        self.search_results_truncated = False
        for entry in (self.search_entry, self.bottom_search_entry):
            entry.blockSignals(True)
            entry.clear()
            entry.blockSignals(False)
        self.editor.clear_search_selections()
        self._update_search_counter()

    def focus_search(self) -> None:
        entry = self.bottom_search_entry if self.layout_mode in (3, 4) else self.search_entry
        entry.setFocus()
        entry.selectAll()

    def show_replace_dialog(self) -> None:
        if self.replace_dialog is None:
            self.replace_dialog = ReplaceDialog(self)
            self.replace_dialog.finished.connect(
                lambda _result: setattr(self, "replace_dialog", None)
            )
        self.replace_dialog.prepare(self.search_query, self.search_case_sensitive)
        self.replace_dialog.set_view_only(self.view_only)
        self.replace_dialog.show()
        self.replace_dialog.raise_()
        self.replace_dialog.activateWindow()

    def replace_current(self, replacement: str) -> bool:
        if self.view_only:
            self.show_view_only_edit_prompt()
            return False
        query = self.search_query
        if not query:
            return False
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n")
        matches = (
            selected == query
            if self.search_case_sensitive
            else selected.casefold() == query.casefold()
        )
        if not matches:
            if not self.find_next():
                return False
            cursor = self.editor.textCursor()
            selected = cursor.selectedText().replace("\u2029", "\n")
        resulting_size = (
            max(0, self.editor.document().characterCount() - 1)
            - len(selected)
            + len(replacement)
        )
        if resulting_size > MAX_DOCUMENT_CHARACTERS:
            QMessageBox.warning(
                self,
                app_dialog_title("Replacement Too Large"),
                "The replacement would exceed Timblee Pad's document safety limit.",
            )
            return False
        cursor.insertText(replacement)
        self.editor.setTextCursor(cursor)
        self._refresh_search_matches(preserve_position=False)
        self.find_next()
        return True

    def replace_all(self, replacement: str) -> int:
        if self.view_only:
            self.show_view_only_edit_prompt()
            return 0
        query = self.search_query
        if not query:
            return 0
        flags = 0 if self.search_case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(query), flags)
        current = self.editor.toPlainText()
        count = sum(1 for _match in pattern.finditer(current))
        estimated_size = len(current) + count * (len(replacement) - len(query))
        if estimated_size > MAX_DOCUMENT_CHARACTERS:
            QMessageBox.warning(
                self,
                app_dialog_title("Replacement Too Large"),
                "Replace All would exceed Timblee Pad's document safety limit.",
            )
            return 0
        updated, count = pattern.subn(lambda _match: replacement, current)
        if count:
            if not self.editor.replace_document_text(updated):
                return 0
            self._refresh_search_matches(preserve_position=False)
            suffix = "es" if count != 1 else ""
            self.show_status(f"Replaced {count:,} match{suffix}.")
        else:
            self.show_status("No matches found.")
        return count

    def go_to_line(self) -> None:
        """Move to a validated line using a plain text field without arrows."""
        maximum = max(1, self.editor.blockCount())
        current = self.editor.textCursor().blockNumber() + 1

        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title("Go To Line"))
        dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(True)
        dialog.setMinimumWidth(310)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        prompt = QLabel(f"Line number (1–{maximum}):", dialog)
        line_input = QLineEdit(dialog)
        line_input.setValidator(QIntValidator(1, maximum, line_input))
        line_input.setText(str(current))
        line_input.selectAll()
        layout.addWidget(prompt)
        layout.addWidget(line_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setEnabled(line_input.hasAcceptableInput())
        line_input.textChanged.connect(
            lambda _text: ok_button.setEnabled(line_input.hasAcceptableInput())
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        line_input.returnPressed.connect(
            lambda: dialog.accept() if line_input.hasAcceptableInput() else None
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.editor.go_to_line(int(line_input.text()))

    # ------------------------------------------------------------------
    # Preview and language-aware Library
    # ------------------------------------------------------------------

    def library_actions_available(self) -> bool:
        return self.document_active

    def html_tag_actions_available(self) -> bool:
        """Compatibility helper retained for the legacy HTML tag collection UI."""
        return self.document_active and self.document_type == "html"

    def _prepare_preview(self) -> bool:
        if not self.document_active:
            self.show_status("Create or open a document before previewing.")
            return False
        profile = profile_for_key(self.document_type)
        if not profile.previewable:
            QMessageBox.information(
                self,
                app_dialog_title("Preview"),
                "A standalone CSS stylesheet has no page to display. "
                "Open the HTML document that links the stylesheet and preview that instead.",
            )
            return False
        if self.file_path is None:
            if not self.save_as_file():
                return False
        if self.file_path is None:
            return False
        if self.editor.document().isModified() and not self.save_file():
            return False
        try:
            _payload, current_snapshot = read_regular_file(self.file_path, MAX_FILE_SIZE)
        except OSError:
            QMessageBox.warning(
                self,
                app_dialog_title("File Unavailable"),
                "The source file no longer exists or is not a regular file.",
            )
            self._update_file_action_state()
            return False
        if self.file_disk_snapshot is not None and current_snapshot != self.file_disk_snapshot:
            answer = QMessageBox.question(
                self,
                app_dialog_title("File Changed on Disk"),
                "The source file changed on disk after Timblee Pad loaded it. "
                "Reload the disk version before previewing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            if not self.load_file(self.file_path, check_changes=False):
                return False
        self.file_disk_snapshot = current_snapshot
        return True

    def preview_in_default_browser(self) -> bool:
        """Preview through localhost so .html editor associations cannot loop back."""
        if not self._prepare_preview() or self.file_path is None:
            return False
        try:
            port = self.preview_server.ensure_root(self.file_path.parent)
        except OSError as error:
            QMessageBox.warning(
                self,
                app_dialog_title("Preview Failed"),
                f"Could not start the local preview server: {error}",
            )
            return False
        url = f"http://127.0.0.1:{port}/{quote(self.file_path.name)}"
        if self.runtime_launcher.open_url(url):
            self.show_status(
                f"Previewed {self.file_path.name} in the default browser via localhost."
            )
            return True
        return False

    def library_specs(self) -> list[TagSpec | LibrarySpec]:
        if self.document_type == "html":
            specs: list[TagSpec | LibrarySpec] = list(COMMON_HTML_TAGS)
            for name in self.custom_tag_names:
                try:
                    specs.append(custom_tag(name))
                except ValueError:
                    continue
            return specs
        return list(NON_HTML_LIBRARY.get(self.document_type, ()))

    def library_categories(self) -> tuple[str, ...]:
        categories: list[str] = []
        for spec in self.library_specs():
            if spec.category not in categories:
                categories.append(spec.category)
        return tuple(categories)

    def library_spec_for_key(self, key: str | None) -> TagSpec | LibrarySpec | None:
        if not key:
            return None
        if self.document_type == "html":
            standard = TAG_BY_KEY.get(key)
            if standard is not None:
                return standard
            if key in self.custom_tag_names:
                try:
                    return custom_tag(key)
                except ValueError:
                    return None
            return None
        return next(
            (spec for spec in NON_HTML_LIBRARY.get(self.document_type, ()) if spec.key == key),
            None,
        )

    def tag_specs(self) -> list[TagSpec | LibrarySpec]:
        return self.library_specs()

    def tag_spec_for_key(self, key: str | None) -> TagSpec | LibrarySpec | None:
        return self.library_spec_for_key(key)

    def _require_library_editing(self) -> bool:
        if not self.document_active:
            self.show_status("Create or open a document before inserting Library content.")
            return False
        if self.view_only or self.editor.isReadOnly():
            self.show_view_only_edit_prompt()
            return False
        return True

    def _require_html_editing(self) -> bool:
        if self.document_type != "html":
            QMessageBox.information(
                self,
                app_dialog_title("HTML Library"),
                "HTML tag insertion is available while the current document type is HTML.",
            )
            return False
        return self._require_library_editing()

    def insert_library_item_by_key(self, key: str) -> bool:
        spec = self.library_spec_for_key(key)
        if spec is None or not self._require_library_editing():
            return False
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n") if cursor.hasSelection() else ""
        cursor.beginEditBlock()
        if spec.closing:
            cursor.insertText(spec.opening + selected + spec.closing)
            if not selected:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Left,
                    QTextCursor.MoveMode.MoveAnchor,
                    len(spec.closing),
                )
        else:
            cursor.insertText(spec.opening)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()
        self.show_status(f"Inserted {spec.label}")
        return True

    def insert_tag_by_key(self, key: str) -> bool:
        return self.insert_library_item_by_key(key)

    def insert_html5_template(self) -> bool:
        self.new_document_from_template("html", "html:html5")
        return True

    def toggle_auto_close_html_tags(self, checked: bool) -> None:
        self.auto_close_html_tags = bool(checked)
        self.editor.set_auto_close_html_tags(self.auto_close_html_tags)
        self._save_preferences()

    def _refresh_tag_library_views(self) -> None:
        if hasattr(self, "tag_library_sidebar"):
            self.tag_library_sidebar.refresh()
        if self.tag_library_dialog is not None:
            self.tag_library_dialog.refresh()

    def _update_tag_library_action_state(self) -> None:
        if hasattr(self, "tag_library_sidebar"):
            self.tag_library_sidebar.update_action_state()
        if self.tag_library_dialog is not None:
            self.tag_library_dialog.panel.update_action_state()

    def _refresh_favourites_menu(self) -> None:
        if not hasattr(self, "favourites_menu"):
            return
        self.favourites_menu.clear()
        specs = [
            spec for spec in self.library_specs()
            if spec.key in self.favourite_tags
        ]
        self.favourites_menu.menuAction().setVisible(bool(specs))
        if not specs:
            return
        for spec in specs:
            action = QAction(spec.label, self)
            action.setToolTip(spec.description)
            action.triggered.connect(
                lambda _checked=False, selected=spec.key: self.insert_library_item_by_key(selected)
            )
            self.favourites_menu.addAction(action)

    def toggle_library_favourite(self, key: str) -> None:
        if self.library_spec_for_key(key) is None:
            return
        if key in self.favourite_tags:
            self.favourite_tags.remove(key)
        else:
            self.favourite_tags.add(key)
        self._refresh_favourites_menu()
        self._refresh_tag_library_views()
        self._save_preferences()

    def toggle_tag_favourite(self, key: str) -> None:
        self.toggle_library_favourite(key)

    def add_custom_tag(self) -> bool:
        name, accepted = QInputDialog.getText(
            self,
            app_dialog_title("Add Custom Tag"),
            "Custom HTML tag name:",
        )
        if not accepted:
            return False
        try:
            spec = custom_tag(name)
        except ValueError as error:
            QMessageBox.warning(self, app_dialog_title("Invalid Tag"), str(error))
            return False
        if spec.key in TAG_BY_KEY:
            QMessageBox.information(
                self,
                app_dialog_title("Tag Already Available"),
                f"{spec.label} is already included in the standard Library.",
            )
            return False
        if spec.key not in self.custom_tag_names:
            self.custom_tag_names.append(spec.key)
            self.custom_tag_names.sort(key=str.casefold)
            self._save_preferences()
            self._refresh_tag_library_views()
        self.show_status(f"Added custom tag {spec.label}")
        return True

    def remove_custom_tag_via_menu(self) -> bool:
        """Choose and remove a custom HTML tag without opening the Library dialog."""
        if self.document_type != "html":
            return False
        if not self.custom_tag_names:
            QMessageBox.information(
                self,
                app_dialog_title("Remove Custom Tag"),
                "There are no custom HTML tags to remove.",
            )
            return False
        labels = [f"<{name}>" for name in self.custom_tag_names]
        selected, accepted = QInputDialog.getItem(
            self,
            app_dialog_title("Remove Custom Tag"),
            "Custom HTML tag:",
            labels,
            0,
            False,
        )
        if not accepted:
            return False
        key = str(selected).strip()[1:-1]
        return self.remove_custom_tag(key)

    def remove_custom_tag(self, key: str) -> bool:
        if key not in self.custom_tag_names:
            return False
        answer = QMessageBox.question(
            self,
            app_dialog_title("Remove Custom Tag"),
            f"Remove <{key}> from the custom tag Library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.custom_tag_names.remove(key)
        self.favourite_tags.discard(key)
        self._refresh_favourites_menu()
        self._save_preferences()
        self._refresh_tag_library_views()
        return True

    def import_tags(self) -> bool:
        """Import custom tags and favourites from a portable collection."""
        selected, _selected_filter = QFileDialog.getOpenFileName(
            self,
            app_dialog_title("Import Tags"),
            "",
            TAG_COLLECTION_FILTER,
        )
        if not selected:
            return False
        source = absolute_user_path(selected)
        try:
            payload, _snapshot = read_regular_file(
                source,
                MAX_TAG_COLLECTION_SIZE,
            )
            imported_custom, imported_favourites = parse_tag_collection(payload)
        except (OSError, TagCollectionError) as error:
            QMessageBox.warning(
                self,
                app_dialog_title("Import Tags Failed"),
                str(error),
            )
            return False

        mode = "merge"
        non_html_favourites = {key for key in self.favourite_tags if ":" in key}
        html_favourites = self.favourite_tags - non_html_favourites
        if self.custom_tag_names or html_favourites:
            dialog = QMessageBox(self)
            dialog.setWindowTitle(app_dialog_title("Import Tags"))
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setText(
                "How should the imported custom tags and favourites be applied?"
            )
            dialog.setInformativeText(
                "Merge keeps your current collection and adds imported entries. "
                "Replace makes the imported collection your complete user tag set."
            )
            merge_button = dialog.addButton("Merge", QMessageBox.ButtonRole.AcceptRole)
            replace_button = dialog.addButton("Replace", QMessageBox.ButtonRole.DestructiveRole)
            cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
            dialog.setDefaultButton(merge_button)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is cancel_button:
                return False
            if clicked is replace_button:
                mode = "replace"

        if mode == "replace":
            new_custom = list(imported_custom)
            available = set(TAG_BY_KEY) | set(new_custom)
            new_favourites = non_html_favourites | {
                key for key in imported_favourites if key in available
            }
        else:
            new_custom = sorted(
                set(self.custom_tag_names) | set(imported_custom),
                key=str.casefold,
            )
            available = set(TAG_BY_KEY) | set(new_custom)
            new_favourites = non_html_favourites | {
                key for key in (html_favourites | imported_favourites)
                if key in available
            }

        self.custom_tag_names = new_custom
        self.favourite_tags = new_favourites
        self._save_preferences()
        self._refresh_favourites_menu()
        self._refresh_tag_library_views()
        self.show_status(
            f"Imported {len(imported_custom)} custom tag(s) and "
            f"{len(imported_favourites)} favourite(s) from {source.name}."
        )
        return True

    def export_tags(self) -> bool:
        """Export custom tags and favourites as a portable JSON collection."""
        selected, _selected_filter = QFileDialog.getSaveFileName(
            self,
            app_dialog_title("Export Tags"),
            "timblee-pad-tags.timbleetags",
            TAG_COLLECTION_FILTER,
        )
        if not selected:
            return False
        destination = absolute_user_path(selected)
        if not destination.suffix:
            destination = destination.with_suffix(".timbleetags")

        destination_state = None
        if path_lexists(destination):
            try:
                destination_state = current_file_state(destination)
            except OSError as error:
                QMessageBox.warning(
                    self,
                    app_dialog_title("Export Tags Failed"),
                    str(error),
                )
                return False
            answer = QMessageBox.question(
                self,
                app_dialog_title("Replace Tag Collection"),
                f"Replace '{destination.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        collection = build_tag_collection(
            self.custom_tag_names,
            self.favourite_tags,
        )
        payload = (json.dumps(collection, indent=2) + "\n").encode("utf-8")
        temporary: Path | None = None
        descriptor: int | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix=f".{destination.name}.timbleepad-tags-",
                suffix=".tmp",
                dir=destination.parent,
            )
            temporary = Path(raw_path)
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = None
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if destination_state is None:
                install_new_file_from_temp(temporary, destination)
                temporary = None
            else:
                if current_file_state(destination) != destination_state:
                    raise FileStateChangedError(
                        "The destination changed after the replacement confirmation."
                    )
                os.replace(temporary, destination)
                temporary = None
            fsync_directory(destination.parent)
        except (OSError, FileStateChangedError) as error:
            QMessageBox.critical(
                self,
                app_dialog_title("Export Tags Failed"),
                str(error),
            )
            return False
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

        self.show_status(
            f"Exported {len(collection['custom_tags'])} custom tag(s) and "
            f"{len(collection['favourites'])} favourite(s) to {destination.name}."
        )
        return True

    def show_tag_library(self) -> None:
        if self.tag_library_dialog is None:
            dialog = TagLibraryDialog(self)
            dialog.finished.connect(
                lambda _result: setattr(self, "tag_library_dialog", None)
            )
            self.tag_library_dialog = dialog
        self.tag_library_dialog.refresh()
        self.tag_library_dialog.show()
        self.tag_library_dialog.raise_()
        self.tag_library_dialog.activateWindow()

    def open_external_editor(self) -> bool:
        if self.file_path is None:
            QMessageBox.information(self, app_dialog_title("External Editor"), "Save the file first.")
            return False
        if self.editor.document().isModified() and not self.save_file():
            return False
        if self.runtime_launcher.open_in_external_editor(self.file_path):
            self.show_status(f"Opened {self.file_path.name} in an external editor.")
            return True
        return False

    def open_folder(self) -> bool:
        if self.file_path is None:
            QMessageBox.information(
                self, app_dialog_title("Open Containing Folder"), "Save the file first."
            )
            return False
        if self.runtime_launcher.open_path(self.file_path.parent):
            self.show_status(f"Opened {self.file_path.parent}.")
            return True
        return False

    def _update_file_action_state(self) -> None:
        has_document = self.document_active
        has_file = has_document and self.file_path is not None
        for action in (
            self.properties_action,
            self.external_action,
            self.rename_action,
            self.delete_action,
            self.duplicate_file_action,
            self.folder_action,
        ):
            action.setEnabled(has_file)
        self.save_action.setEnabled(has_document)
        self.save_as_action.setEnabled(has_document)
        self.document_type_file_menu.setEnabled(has_document)

        previewable = has_document and profile_for_key(self.document_type).previewable
        self.preview_button.setEnabled(previewable)
        self.preview_action.setEnabled(previewable)
        if has_document and self.document_type == "css":
            preview_tip = "Preview the HTML document that links this stylesheet."
        elif has_document:
            preview_tip = "Preview in the default web browser through a localhost URL."
        else:
            preview_tip = "Create or open a document before previewing."
        self.preview_button.setToolTip(preview_tip)
        self.preview_action.setToolTip(preview_tip)

        # Templates stay available even on the Start a Document screen, while
        # insertion/favourite controls require an active document.
        self.tags_menu.setEnabled(True)
        self.library_action.setEnabled(has_document)
        self.favourites_menu.setEnabled(has_document)
        html_mode = has_document and self.document_type == "html"
        for action in self.essential_tag_actions:
            action.setVisible(html_mode)
            action.setEnabled(html_mode)
        for action in (
            self.add_custom_tag_action,
            self.remove_custom_tag_action,
            self.import_tags_action,
            self.export_tags_action,
        ):
            action.setVisible(html_mode)
            action.setEnabled(html_mode)
        self.auto_close_tags_action.setEnabled(
            has_document and self.document_type in {"html", "xml"}
        )
        self._update_tag_library_action_state()


    @staticmethod
    def _format_file_size(size: int) -> str:
        """Return a compact binary size while preserving the exact byte count."""
        if size < 1024:
            return f"{size} byte" if size == 1 else f"{size} bytes"
        units = ("KiB", "MiB", "GiB", "TiB")
        value = float(size)
        for unit in units:
            value /= 1024.0
            if value < 1024.0 or unit == units[-1]:
                return f"{value:.1f} {unit} ({size:,} bytes)"
        return f"{size:,} bytes"

    @staticmethod
    def _format_file_time(timestamp_ns: int) -> str:
        """Format a filesystem timestamp using the user's locale."""
        try:
            return time.strftime("%x %X", time.localtime(timestamp_ns / 1_000_000_000))
        except (OverflowError, OSError, ValueError):
            return "Unavailable"

    @staticmethod
    def _properties_value_label(
        text: str,
        parent: QWidget,
        *,
        wrap: bool = False,
    ) -> QLabel:
        label = QLabel(text, parent)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        label.setWordWrap(wrap)
        return label

    def show_properties_dialog(self) -> None:
        """Show filesystem and in-editor details for the current document."""
        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title("Properties"))
        dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(True)
        dialog.setMinimumWidth(520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(10)

        file_heading = QLabel("<b>File</b>", dialog)
        file_heading.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(file_heading)

        file_form = QFormLayout()
        file_form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        file_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        path = self.file_path
        profile = profile_for_key(self.document_type)
        if path is None:
            document_type = f"{profile.label} (unsaved)"
        elif extension_matches_type(path, self.document_type):
            document_type = f"{profile.label} ({path.suffix.lower()})"
        else:
            document_type = f"{profile.label} interpretation ({path.suffix.lower()} filename)"

        if path is None:
            file_rows = (
                ("Name:", "Untitled", False),
                ("Type:", document_type, False),
                ("Location:", "Not saved", False),
                ("Size on disk:", "Not saved", False),
                ("Modified:", "Not saved", False),
                ("Permissions:", "Not available", False),
                ("Symbolic link:", "No", False),
            )
        else:
            try:
                state = current_file_state(path)
                permissions = (
                    f"{stat.filemode(state.target_mode)} "
                    f"({stat.S_IMODE(state.target_mode):04o})"
                )
                symbolic_link = "Yes" if state.is_symlink else "No"
                if state.is_symlink:
                    try:
                        symbolic_link += f" → {os.readlink(path)}"
                    except OSError:
                        symbolic_link += " → target unavailable"
                file_rows = (
                    ("Name:", path.name, False),
                    ("Type:", document_type, False),
                    ("Location:", str(path.parent), True),
                    ("Full path:", str(path), True),
                    ("Size on disk:", self._format_file_size(state.size), False),
                    ("Modified:", self._format_file_time(state.mtime_ns), False),
                    ("Metadata changed:", self._format_file_time(state.ctime_ns), False),
                    ("Permissions:", permissions, False),
                    ("Symbolic link:", symbolic_link, True),
                )
            except OSError as error:
                file_rows = (
                    ("Name:", path.name, False),
                    ("Type:", document_type, False),
                    ("Location:", str(path.parent), True),
                    ("Full path:", str(path), True),
                    ("Filesystem details:", f"Unavailable: {error}", True),
                )

        for title, value, wrap in file_rows:
            file_form.addRow(
                title,
                self._properties_value_label(value, dialog, wrap=wrap),
            )
        layout.addLayout(file_form)

        document_heading = QLabel("<b>Document</b>", dialog)
        document_heading.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(document_heading)

        document_form = QFormLayout()
        document_form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        document_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        document = self.editor.document()
        encoding = self.file_encoding.upper()
        if self.file_bom:
            encoding += " with BOM"
        newline_name = {"\n": "LF", "\r\n": "CRLF", "\r": "CR"}.get(
            self.file_newline,
            "Unknown",
        )
        document_rows = (
            ("Document type:", profile_for_key(self.document_type).label),
            ("Encoding:", encoding),
            ("Line endings:", newline_name),
            ("Lines:", f"{max(1, document.blockCount()):,}"),
            ("Characters:", f"{max(0, document.characterCount() - 1):,}"),
            ("Unsaved changes:", "Yes" if document.isModified() else "No"),
            ("View Only:", "On" if self.view_only else "Off"),
        )
        for title, value in document_rows:
            document_form.addRow(
                title,
                self._properties_value_label(value, dialog),
            )
        layout.addLayout(document_form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _documentation_path(self) -> Path | None:
        """Locate the bundled README in source, frozen and AppImage modes."""
        candidates = [
            self.runtime_paths.package_root / "docs" / "README.md",
            Path(__file__).resolve().parent / "docs" / "README.md",
        ]
        appdir = os.environ.get("APPDIR", "").strip()
        if appdir:
            candidates.append(
                Path(appdir) / "usr" / "share" / "doc" / "timbleepad" / "README.md"
            )
        seen: set[Path] = set()
        for candidate in candidates:
            path = absolute_user_path(candidate)
            if path in seen:
                continue
            seen.add(path)
            if path.is_file():
                return path
        return None

    def open_documentation(self) -> bool:
        """Open the bundled README with the host desktop application."""
        readme = self._documentation_path()
        if readme is None:
            QMessageBox.information(
                self,
                app_dialog_title("Documentation"),
                "The bundled README.md documentation could not be found.",
            )
            return False
        if self.runtime_launcher.open_path(readme):
            self.show_status("Opened Timblee Pad documentation.")
            return True
        return False

    def open_github_repository(self) -> bool:
        """Open the official Timblee Pad repository in the host browser."""
        if self.runtime_launcher.open_url(GITHUB_URL):
            self.show_status("Opened the Timblee Pad GitHub repository.")
            return True
        return False

    def report_an_issue(self) -> bool:
        """Open the official issue tracker in the host browser."""
        if self.runtime_launcher.open_url(ISSUES_URL):
            self.show_status("Opened the Timblee Pad issue tracker.")
            return True
        return False

    # ------------------------------------------------------------------
    # Informational dialogs
    # ------------------------------------------------------------------

    def show_shortcuts_dialog(self) -> None:
        if self.shortcuts_dialog is not None:
            self.shortcuts_dialog.show()
            self.shortcuts_dialog.raise_()
            self.shortcuts_dialog.activateWindow()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title("Keyboard Shortcuts"))
        dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(False)
        dialog.setMinimumWidth(980)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        columns = QHBoxLayout()
        columns.setSpacing(22)
        layout.addLayout(columns)

        left_column = QVBoxLayout()
        middle_column = QVBoxLayout()
        right_column = QVBoxLayout()
        for column in (left_column, middle_column, right_column):
            column.setSpacing(12)
            columns.addLayout(column, 1)

        def add_section(
            column: QVBoxLayout,
            title: str,
            entries: tuple[tuple[str, str], ...],
        ) -> None:
            heading = QLabel(f"<b>{title}</b>", dialog)
            heading.setTextFormat(Qt.TextFormat.RichText)
            column.addWidget(heading)

            table = QFormLayout()
            table.setHorizontalSpacing(18)
            table.setVerticalSpacing(5)
            table.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            for action_name, shortcut in entries:
                action_label = QLabel(dialog)
                action_label.setTextFormat(Qt.TextFormat.PlainText)
                action_label.setText(action_name)
                shortcut_label = QLabel(dialog)
                shortcut_label.setTextFormat(Qt.TextFormat.PlainText)
                shortcut_label.setText(shortcut)
                shortcut_label.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                table.addRow(action_label, shortcut_label)
            column.addLayout(table)

        add_section(
            left_column,
            "Application and Files",
            (
                ("New", "Ctrl+N"),
                ("New Window", "Ctrl+Shift+N"),
                ("Open", "Ctrl+O"),
                ("Save", "Ctrl+S"),
                ("Save As", "Ctrl+Shift+S"),
                ("Documentation", "F1"),
                ("Exit", "Ctrl+Q"),
            ),
        )
        add_section(
            left_column,
            "More Actions",
            (
                ("Open in External Editor", "Ctrl+Shift+E"),
                ("Rename", "F2"),
                ("Duplicate File", "Ctrl+Shift+D"),
                ("Open Containing Folder", "Ctrl+Shift+O"),
            ),
        )
        left_column.addStretch(1)

        add_section(
            middle_column,
            "Editing",
            (
                ("Undo", "Ctrl+Z"),
                ("Redo", "Ctrl+Y"),
                ("Cut", "Ctrl+X"),
                ("Copy", "Ctrl+C"),
                ("Paste", "Ctrl+V"),
                ("Delete", "Delete"),
                ("Toggle Comment", "Ctrl+/"),
                ("Duplicate Line / Selection", "Ctrl+D"),
                ("Delete Line", "Ctrl+Shift+K"),
                ("Select All", "Ctrl+A"),
            ),
        )
        middle_column.addStretch(1)

        add_section(
            right_column,
            "Search and Navigation",
            (
                ("Find", "Ctrl+F"),
                ("Next Match", "F3"),
                ("Previous Match", "Shift+F3"),
                ("Replace", "Ctrl+H"),
                ("Go To Line", "Ctrl+G"),
            ),
        )
        add_section(
            right_column,
            "Preview and Library",
            (
                ("Preview in default browser", "F5"),
                ("Library", "Ctrl+L"),
                *((TAG_BY_KEY[key].label, shortcut) for key, shortcut in ESSENTIAL_TAGS),
            ),
        )
        right_column.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.finished.connect(
            lambda _result: setattr(self, "shortcuts_dialog", None)
        )
        self.shortcuts_dialog = dialog
        dialog.show()

    def show_about_dialog(self) -> None:
        if self.about_dialog is not None:
            self.about_dialog.show()
            self.about_dialog.raise_()
            self.about_dialog.activateWindow()
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(app_dialog_title("About"))
        dialog.setWindowIcon(self.windowIcon())
        dialog.setModal(False)
        dialog.setMinimumWidth(390)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(10)

        if self.runtime_paths.icon_path.is_file():
            logo = QLabel(dialog)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(str(self.runtime_paths.icon_path))
            if not pixmap.isNull():
                logo.setPixmap(
                    pixmap.scaled(
                        112,
                        112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                layout.addWidget(logo)

        application_name = QLabel(f"<h2>{APP_NAME}</h2>", dialog)
        application_name.setTextFormat(Qt.TextFormat.RichText)
        application_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(application_name)

        version = QLabel(f"Version {APP_VERSION}", dialog)
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        tagline = QLabel("<b>Friendly. Fast. Focused.</b>", dialog)
        tagline.setTextFormat(Qt.TextFormat.RichText)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tagline)

        description = QLabel(
            "A lightweight standalone editor for HTML, CSS and XML source files, "
            "with language-aware editing, templates, Library insertions and focused preview tools. "
            "Celebrating Tim Berners-Lee's contribution to the work.",
            dialog,
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(description)

        preferences_path = html.escape(str(self.config_file))
        details = QLabel(
            f"<a href='{GITHUB_URL}'>"
            f"{GITHUB_URL}</a><br>"
            "Built on Python and PyQt6; derived from the Sheepy Pad source-editor framework.<br>"
            f"<b>Preferences:</b> {preferences_path}<br><br>"
            "Copyright © 2026 Bruno Machado<br>"
            "[<a href='https://github.com/brunonlinespace/'>"
            "https://github.com/brunonlinespace/</a>]<br>"
            "Licensed under the GNU General Public License v3 or later.",
            dialog,
        )
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setOpenExternalLinks(True)
        details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(details)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, dialog)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("OK")
        buttons.accepted.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.finished.connect(lambda _result: setattr(self, "about_dialog", None))
        self.about_dialog = dialog
        dialog.show()

    # ------------------------------------------------------------------
    # Drag/drop and lifecycle
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        self.open_dropped_files(paths)
        event.acceptProposedAction()

    def open_dropped_files(self, paths: list[str]) -> None:
        source_files: list[Path] = []
        unsupported_types = 0
        invalid_items = 0
        for raw_path in paths:
            path = absolute_user_path(raw_path)
            if path.suffix.casefold() not in SUPPORTED_WEB_SUFFIXES:
                unsupported_types += 1
                continue
            try:
                current_file_state(path)
            except OSError:
                invalid_items += 1
                continue
            source_files.append(path)

        if unsupported_types:
            self.show_unsupported_file_dialog(unsupported_types)
        rejected = unsupported_types + invalid_items
        if rejected:
            suffix = "s" if rejected != 1 else ""
            self.show_status(
                f"Ignored {rejected} item{suffix}; Timblee Pad opens supported HTML, CSS and XML source files only."
            )
        if not source_files:
            return

        remaining = iter(source_files)
        if self.drop_open_mode == "active_window":
            if not self.check_save_changes():
                return
            for first in remaining:
                if self.load_file(first, check_changes=False):
                    break
            else:
                return

        for path in remaining:
            window = TimbleePadWindow()
            if window.load_file(path, check_changes=False):
                window.show()
            else:
                window.close()

    def editor_undo(self) -> None:
        if not self.view_only:
            self.editor.undo()

    def editor_redo(self) -> None:
        if not self.view_only:
            self.editor.redo()

    def _show_launch_error(self, message: str) -> None:
        """Present failures from browser, desktop-opener and external-editor actions."""
        QMessageBox.warning(
            self,
            app_dialog_title("Could Not Open"),
            message,
        )

    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.check_save_changes():
            event.ignore()
            return
        self._save_preferences()
        self.preview_server.close()
        event.accept()



def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Timblee Pad lightweight HTML, CSS and XML source editor"
    )
    parser.add_argument("files", nargs="*", help="HTML, CSS or XML source files to open")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument(
        "--appimage-theme",
        choices=("dark", "light", "system"),
        help="Override AppImage chrome theme for this launch.",
    )
    parser.add_argument(
        "--timbleepad-smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.appimage_theme:
        os.environ["TIMBLEEPAD_APPIMAGE_THEME"] = arguments.appimage_theme
    application = QApplication(sys.argv[:1])
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    application.setOrganizationName("brunonlinespace")
    application.setDesktopFileName("timbleepad")
    application.setQuitOnLastWindowClosed(True)
    runtime_paths = RuntimePaths.detect(
        Path(__file__).resolve().parents[1] / "main.py"
    )
    if runtime_paths.icon_path.is_file():
        application.setWindowIcon(QIcon(str(runtime_paths.icon_path)))
    application.setProperty("timbleepad_original_palette", QPalette(application.palette()))
    application.setProperty("timbleepad_original_style", application.style().objectName())

    valid_files = [
        absolute_user_path(value)
        for value in arguments.files
        if Path(value).suffix.casefold() in SUPPORTED_WEB_SUFFIXES
    ]
    unsupported_files = [
        value
        for value in arguments.files
        if Path(value).suffix.casefold() not in SUPPORTED_WEB_SUFFIXES
    ]
    window = TimbleePadWindow(valid_files[0] if valid_files else None)
    if arguments.timbleepad_smoke_test:
        requested_smoke_theme = os.environ.get("TIMBLEEPAD_APPIMAGE_THEME", "").strip().lower()
        if requested_smoke_theme in {"dark", "light", "system"}:
            if not window.appimage_theme_available:
                print("GUI smoke theme check failed: packaged AppImage theme assets are unavailable.", file=sys.stderr, flush=True)
                window.close()
                return 1
            if window.effective_appimage_theme() != requested_smoke_theme:
                print(
                    f"GUI smoke theme check failed: expected {requested_smoke_theme}, "
                    f"got {window.effective_appimage_theme()}.",
                    file=sys.stderr,
                    flush=True,
                )
                window.close()
                return 1
            stylesheet_active = bool(application.styleSheet().strip())
            if requested_smoke_theme in {"dark", "light"} and not stylesheet_active:
                print(
                    f"GUI smoke theme check failed: {requested_smoke_theme} stylesheet was not applied.",
                    file=sys.stderr,
                    flush=True,
                )
                window.close()
                return 1
            if requested_smoke_theme == "system" and stylesheet_active:
                print(
                    "GUI smoke theme check failed: system mode retained a bundled stylesheet.",
                    file=sys.stderr,
                    flush=True,
                )
                window.close()
                return 1
            print(f"GUI smoke theme check passed: {requested_smoke_theme}.", flush=True)
        window.show()
        smoke_completed = False

        def finish_smoke_test() -> None:
            nonlocal smoke_completed
            application.processEvents()
            smoke_completed = True
            print("GUI smoke test passed.", flush=True)
            window.close()
            application.quit()

        QTimer.singleShot(0, finish_smoke_test)
        status = application.exec()
        return status if smoke_completed else 1

    extra_windows: list[TimbleePadWindow] = []
    for path in valid_files[1:]:
        extra = TimbleePadWindow(path)
        if extra.file_path is not None:
            extra_windows.append(extra)
        else:
            extra.close()

    window.show()
    for extra in extra_windows:
        extra.show()
    if unsupported_files:
        QTimer.singleShot(
            0,
            lambda count=len(unsupported_files): window.show_unsupported_file_dialog(
                count
            ),
        )
    return application.exec()
