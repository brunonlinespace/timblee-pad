#!/usr/bin/env python3
"""Static release checks for Timblee Pad 0.2.3 AppImage/portable packaging release."""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

PROGRAM_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PROGRAM_ROOT.parent
MANIFEST = PROGRAM_ROOT / "SOURCE_MANIFEST.sha256"


def fail(message: str) -> None:
    raise SystemExit(f"release check failed: {message}")


def require(text: str, fragment: str, label: str) -> None:
    if fragment not in text:
        fail(f"{label} missing: {fragment}")


def forbid(text: str, fragment: str, label: str) -> None:
    if fragment in text:
        fail(f"{label} still contains: {fragment}")


def source_files() -> list[Path]:
    files = [PROJECT_ROOT / "main.py"]
    files.extend(
        path
        for path in PROGRAM_ROOT.rglob("*.py")
        if "build" not in path.parts
        and "dist" not in path.parts
        and "__pycache__" not in path.parts
    )
    return sorted(files)


def manifest_files() -> list[Path]:
    return sorted(
        path
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file()
        and path != MANIFEST
        and ".git" not in path.parts
        and "build" not in path.parts
        and "dist" not in path.parts
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def main() -> int:
    root_entries = {path.name for path in PROJECT_ROOT.iterdir()}
    if root_entries != {"README.md", "main.py", "suite-pythoine-component.json", "timblee_pad"}:
        fail(
            "portable root must contain only README.md, main.py, suite-pythoine-component.json and timblee_pad/; "
            f"found {sorted(root_entries)}"
        )

    generated = [
        path
        for path in PROJECT_ROOT.rglob("*")
        if "build" not in path.parts
        and "dist" not in path.parts
        and ".git" not in path.parts
        and (path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"})
    ]
    if generated:
        fail(f"generated Python cache remains: {generated[0].relative_to(PROJECT_ROOT)}")

    for path in source_files():
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            fail(f"Python syntax error in {path.relative_to(PROJECT_ROOT)}: {error}")

    init_source = (PROGRAM_ROOT / "__init__.py").read_text(encoding="utf-8")
    app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
    editor_source = (PROGRAM_ROOT / "code_editor.py").read_text(encoding="utf-8")
    tags_source = (PROGRAM_ROOT / "html_tags.py").read_text(encoding="utf-8")
    tag_io_source = (PROGRAM_ROOT / "tag_io.py").read_text(encoding="utf-8")
    profiles_source = (PROGRAM_ROOT / "document_profiles.py").read_text(encoding="utf-8")
    templates_source = (PROGRAM_ROOT / "templates.py").read_text(encoding="utf-8")
    library_source = (PROGRAM_ROOT / "library_catalog.py").read_text(encoding="utf-8")
    launcher_source = (PROGRAM_ROOT / "runtime_launcher.py").read_text(encoding="utf-8")
    paths_source = (PROGRAM_ROOT / "runtime_paths.py").read_text(encoding="utf-8")
    main_source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")

    require(main_source, "from timblee_pad import APP_NAME, APP_VERSION", "portable launcher")
    require(main_source, "from timblee_pad.app import main as gui_main", "portable launcher")
    require(init_source, 'APP_NAME = "Timblee Pad"', "package identity")
    require(init_source, 'APP_VERSION = "0.2.3"', "package version")
    component_path = PROJECT_ROOT / "suite-pythoine-component.json"
    if not component_path.is_file():
        fail("suite-pythoine-component.json is missing")
    import json
    component = json.loads(component_path.read_text(encoding="utf-8"))
    if component.get("id") != "timblee-pad" or component.get("version") != "0.2.3":
        fail("Suite component identity/version mismatch")
    if component.get("extensions") != [".html", ".htm", ".css"]:
        fail("Suite component routing must remain HTML/HTM/CSS only")
    if component.get("tagline") != "Friendly. Fast. Focused.":
        fail("Suite component tagline mismatch")
    require(app_source, '<b>Friendly. Fast. Focused.</b>', "Pad-family slogan")
    require(app_source, "Celebrating Tim Berners-Lee\'s contribution to the work.", "About tribute sentence")
    require(app_source, 'SUPPORTED_WEB_SUFFIXES = SUPPORTED_SOURCE_SUFFIXES', "document-profile file scope")
    require(app_source, 'addMenu("&Library")', "Library menu")
    require(app_source, '"Preview in default browser"', "browser preview")
    require(app_source, '"Preview", self.preview_in_default_browser', "compact Preview toolbar button")
    require(app_source, '"Duplicate Line / Selection"', "reviewed duplicate-line label")
    require(app_source, '"Delete Line"', "delete-line action")
    require(app_source, 'QKeySequence("Ctrl+Shift+K")', "delete-line shortcut")
    require(editor_source, "def delete_current_line", "delete-line implementation")
    for fragment in (
        "self.setCenterOnScroll(False)",
        "def _resize_gutter_above_horizontal_scrollbar(self) -> None:",
        "horizontal = self.horizontalScrollBar()",
        "gutter_height = max(0, gutter_height - horizontal.height())",
        "self.centerCursor()",
    ):
        if fragment not in editor_source:
            fail(f"0.2.3 editor scrolling/gutter corrective missing: {fragment}")
    if "self.setCenterOnScroll(True)" in editor_source:
        fail("legacy global center-on-scroll remains enabled")
    forbid(app_source, "document_type_button", "removed permanent Document Type toolbar shortcut")
    menu_index = app_source.find("primary_layout.addWidget(self.menu_buttons_container)")
    preview_index = app_source.find("primary_layout.addWidget(self.preview_button)")
    if not (0 <= menu_index < preview_index):
        fail("Toolbar order must keep menus/Help before Preview")
    forbid(app_source, "document_check_label", "removed document-check status-bar surface")
    forbid(app_source, "document_check_summary", "removed document-check state")
    forbid(app_source, "Type OK", "removed type-validation claim")
    require(app_source, '"Library..."', "tag library")
    require(app_source, '"My Favourites"', "tag favourites")
    require(app_source, '"Remove Custom HTML Tag..."', "HTML custom-tag removal action")
    require(app_source, '"Import HTML Tags..."', "HTML tag import action")
    require(app_source, '"Export HTML Tags..."', "HTML tag export action")
    require(app_source, "def import_tags", "tag import implementation")
    require(app_source, "def export_tags", "tag export implementation")
    require(app_source, 'class TagLibraryPanel(QWidget)', "shared tag library panel")
    require(app_source, 'sidebar_mode: bool = False', "sidebar-specific Library mode")
    require(app_source, 'self.catalog_combo = QComboBox(self)', "sidebar Library catalogue dropdown")
    require(app_source, 'self.close_sidebar_button.setText("×")', "sidebar close control")
    require(app_source, 'base = ("All", *self.window.library_categories())', "All-first fallback Library catalogue")
    require(app_source, 'return ("Favourites", *base) if has_favourites else base', "conditional Favourites Library catalogue")
    require(app_source, 'self.catalog_combo.currentText() or categories[0]', "empty-favourites sidebar default to All")
    require(app_source, 'self.favourites_menu.menuAction().setVisible(bool(specs))', "hide empty Favourites menu")
    forbid(app_source, 'No favourites for this document type', "empty Favourites placeholder")
    require(app_source, 'self.tabs = QTabWidget(self)', "floating Library tabs retained")
    require(app_source, '"left": "Left Sidebar"', "left Library label")
    require(app_source, '"right": "Right Sidebar"', "right Library label")
    require(app_source, '"disabled": "Floating Only"', "floating-only Library label")
    require(app_source, 'self.view_menu.addMenu("Library")', "Library view menu")
    require(app_source, 'self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal, self)', "resizable library/editor splitter")
    require(app_source, 'self.workspace_host = QStackedWidget(self)', "shared Start/editor workspace slot")
    require(app_source, 'self.workspace_host.setCurrentWidget(self.start_panel)', "Start panel workspace switch")
    require(app_source, 'self.workspace_host.setCurrentWidget(self.editor)', "document workspace switch")
    require(app_source, 'self.document_column_layout.addWidget(self.bottom_search)', "split Find inside editor column")
    require(app_source, 'self.workspace_splitter.insertWidget(0, sidebar)', "left sidebar split placement")
    require(app_source, 'self.workspace_splitter.insertWidget(1, content)', "left sidebar editor-column placement")
    forbid(app_source, 'self.main_layout.addWidget(self.bottom_search)', "full-width split Find placement")
    require(app_source, '"Dark Editor"', "independent dark-editor toggle")
    require(app_source, 'self.dark_editor = True', "dark-editor default")
    require(app_source, 'boolean_value("dark_editor", True)', "dark-editor preference load")
    require(app_source, '"dark_editor": self.dark_editor', "dark-editor preference save")
    require(app_source, 'self.view_menu.addMenu("File Drag and Drop")', "File Drag and Drop submenu")
    require(app_source, '"active_window": "Opens on Active Window"', "active-window drag/drop label")
    require(app_source, '"new_window": "Opens on New Window"', "new-window drag/drop label")
    require(app_source, '"tag_library_sidebar_position": self.tag_library_sidebar_position', "sidebar preference")
    require(app_source, "if not self.sidebar_mode:", "sidebar-only compact control guard")
    require(app_source, "def hide_tag_library_sidebar(self) -> None:", "transient sidebar close")
    require(app_source, "def toggle_library_visibility(self) -> None:", "preference-aware Library toggle")
    require(app_source, "self.tag_library_sidebar_hidden = False", "transient sidebar visibility state")
    require(app_source, 'QKeySequence("Ctrl+L")', "Library Ctrl+L shortcut")
    require(app_source, 'QKeySequence("Ctrl+Shift+E")', "external-editor shortcut")
    require(app_source, 'QKeySequence("F2")', "rename shortcut")
    require(app_source, 'QKeySequence("Ctrl+Shift+D")', "duplicate-file shortcut")
    require(app_source, 'QKeySequence("Ctrl+Shift+O")', "containing-folder shortcut")
    forbid(app_source, "Ctrl+Alt", "retired Ctrl+Alt shortcuts")
    forbid(app_source, "Ctrl+Delete", "retired Delete File shortcut")
    require(app_source, "action_label.setTextFormat(Qt.TextFormat.PlainText)", "plain shortcut action labels")
    require(app_source, "*((TAG_BY_KEY[key].label, shortcut) for key, shortcut in ESSENTIAL_TAGS)", "synchronised Library shortcut labels")
    start_panel_source = app_source[
        app_source.find("    def _show_start_panel(self) -> None:"):
        app_source.find("    def _show_document_workspace", app_source.find("    def _show_start_panel(self) -> None:"))
    ]
    if "self.search_container.hide()" in start_panel_source or "self.bottom_search.hide()" in start_panel_source:
        fail("Start a Document must not hide the saved search-bar layout")
    require(start_panel_source, "self._update_find_bar_state()", "disabled Find bar on Start screen")
    require(start_panel_source, "self._update_edit_action_state()", "disabled Edit commands on Start screen")
    require(app_source, "def _update_find_bar_state(self) -> None:", "Find-bar document-state helper")
    require(app_source, "self.search_container.setEnabled(enabled)", "inline Find enabled-state binding")
    require(app_source, "self.bottom_search.setEnabled(enabled)", "split Find enabled-state binding")
    require(app_source, "if not self.document_active:", "no-document Edit-state branch")
    require(app_source, "self.go_to_line_action = self._add_action(", "tracked Go To Line Edit action")
    require(app_source, "self.delete_line_action,", "Delete Line View Only state coverage")
    require(app_source, "def insert_html5_template", "HTML5 template action")
    require(app_source, "def add_custom_tag", "custom tag action")
    require(app_source, "def _show_launch_error", "runtime launch-error handler")
    require(app_source, '"--timbleepad-smoke-test"', "hidden GUI smoke-test switch")
    require(app_source, 'print("GUI smoke test passed.", flush=True)', "GUI smoke-test completion marker")
    require(app_source, 'requested_smoke_theme = os.environ.get("TIMBLEEPAD_APPIMAGE_THEME"', "GUI theme smoke expected override")
    require(app_source, 'window.effective_appimage_theme() != requested_smoke_theme', "GUI theme smoke override validation")
    require(app_source, 'stylesheet_active = bool(application.styleSheet().strip())', "GUI theme smoke stylesheet validation")
    require(editor_source, "class HTMLHighlighter", "HTML highlighter")
    require(editor_source, "class CSSHighlighter", "CSS highlighter")
    require(editor_source, "class XMLHighlighter", "XML highlighter")
    require(editor_source, "def _matching_tag_selections", "tag-pair highlighting")
    require(editor_source, "def _try_auto_close_html_tag", "closing-tag completion")
    require(tags_source, 'HTML5_TEMPLATE = """<!doctype html>', "HTML5 template")
    require(tags_source, "COMMON_HTML_TAGS:", "HTML tag catalogue")
    require(tags_source, "TAG_CATEGORIES:", "HTML tag categories")
    for key in ('_tag("abbr"', '_tag("iframe"', '_tag("datalist"', '_tag("search"', '_tag("math"'):
        require(tags_source, key, "expanded current HTML catalogue")
    for key in ("css:class-rule", "css:responsive-grid", "css:visually-hidden", "xml:doctype", "xml:xsd-schema", "xml:xslt-stylesheet"):
        require(library_source, key, "expanded language-aware Library catalogue")
    require(tag_io_source, 'TAG_COLLECTION_FORMAT = "timblee-pad-tag-collection"', "tag collection format")
    require(tag_io_source, "def parse_tag_collection", "tag collection parser")
    require(tag_io_source, "def build_tag_collection", "tag collection exporter")
    for suffix in ('".html"', '".htm"', '".css"', '".xml"', '".xsd"', '".xsl"', '".xslt"'):
        require(profiles_source, suffix, "document profile suffix")
    require(profiles_source, 'DOCUMENT_TYPE_ORDER = ("html", "css", "xml")', "document type order")
    forbid(profiles_source, '".svg"', "SVG document suffix")
    require(templates_source, 'CURSOR_MARKER = "[[cursor]]"', "template cursor marker")
    for template_id in ("html:html5", "css:basic", "xml:basic"):
        require(templates_source, template_id, "built-in template")
    for prefix in ('"css:', '"xml:'):
        require(library_source, prefix, "language-aware Library catalogue")
    for fragment, label in (
        ("class NewDocumentDialog(QDialog)", "New document chooser"),
        ("class DefaultNewDocumentDialog(QDialog)", "default New document chooser"),
        ("class TemplateManagerDialog(QDialog)", "template manager"),
        ('self.file_menu.addMenu("Document Type")', "Document Type menu"),
        ('self.tags_menu = self.app_menu_bar.addMenu("&Library")', "Library application menu"),
        ('http.server.ThreadingHTTPServer(("127.0.0.1", 0)', "loopback preview server"),
        ('url = f"http://127.0.0.1:{port}/', "loopback preview URL"),
        ('self.path_label.setText("No document open")', "explicit no-document status"),
    ):
        require(app_source, fragment, label)

    forbid(app_source, "ET.fromstring", "automatic XML validation")
    forbid(app_source, "_run_document_check", "automatic document checker")

    for fragment in (
        'addMenu("&Run")',
        "Launch in Terminal",
        "Launch as Admin",
        "Force Stop",
        "Make Executable",
        "Remove Executable",
        "class PythonHighlighter",
        "class ShellHighlighter",
    ):
        forbid(app_source + "\n" + editor_source, fragment, "converted application")

    combined_lightweight = (app_source + "\n" + editor_source + "\n" + templates_source + "\n" + library_source).casefold()
    for fragment in ("qwebengineview", "pyqt6.qtwebengine", "subprocess.run([\"node\"", "npm install", "eslint", "prettier"):
        forbid(combined_lightweight, fragment, "lightweight source editor")

    for fragment in (
        "python_command",
        "shell_command",
        "script_terminal_command",
        "sudo_executable",
        "launch_script",
    ):
        forbid(launcher_source, fragment, "host runtime launcher")
    require(launcher_source, 'EDITOR_OVERRIDE_VARIABLE = "TIMBLEEPAD_EDITOR"', "external editor override")
    require(launcher_source, 'parsed.scheme not in {"http", "https"}', "URL scheme guard")

    require(paths_source, 'launcher_root / "timblee_pad"', "portable package path")
    require(paths_source, 'frozen_root / "timblee_pad"', "frozen package path")
    require(paths_source, '"sheepypad" / "sheepypad.json"', "one-time Sheepy preference import")

    desktop = (PROGRAM_ROOT / "packaging/appimage/timbleepad.desktop").read_text(encoding="utf-8")
    metainfo = (PROGRAM_ROOT / "packaging/appimage/io.github.brunonlinespace.timbleepad.metainfo.xml").read_text(encoding="utf-8")
    apprun = (PROGRAM_ROOT / "packaging/appimage/AppRun").read_text(encoding="utf-8")
    build = (PROGRAM_ROOT / "packaging/fedora/build-appimage.sh").read_text(encoding="utf-8")
    spec = (PROGRAM_ROOT / "packaging/pyinstaller/timbleepad.spec").read_text(encoding="utf-8")
    portable = (PROGRAM_ROOT / "portable/run-timbleepad.sh").read_text(encoding="utf-8")
    appimage_test = (PROGRAM_ROOT / "packaging/fedora/test-appimage.sh").read_text(encoding="utf-8")

    require(desktop, "Name=Timblee Pad", "desktop identity")
    require(desktop, "MimeType=text/html;text/css;application/xml;text/xml;", "desktop MIME scope")
    forbid(desktop + "\n" + metainfo, "image/svg+xml", "SVG document MIME")
    require(metainfo, "io.github.brunonlinespace.timbleepad", "AppStream ID")
    require(metainfo, "https://github.com/brunonlinespace/timblee-pad", "AppStream homepage")
    require(apprun, 'BUNDLE="$APPDIR/usr/lib/timbleepad"', "AppRun bundle path")
    require(apprun, 'TIMBLEEPAD_APPIMAGE_THEME="dark"', "AppRun theme variable")
    forbid(apprun.casefold(), "sheepypad", "AppRun")
    require(build, 'umask 022', "hardened builder umask")
    require(build, 'PROGRAM_ROOT="${PROJECT_ROOT}/timblee_pad"', "portable build root")
    require(build, 'DIST_DIR="${OUTPUT_DIR:-${PROGRAM_ROOT}/dist}"', "contained build outputs")
    require(build, 'APPIMAGE="${DIST_DIR}/Timblee-Pad-${APP_VERSION}-${ARCH}.AppImage"', "AppImage filename")
    require(build, 'APP_NAME="Timblee Pad"', "builder application identity")
    require(build, 'APP_ID="timbleepad"', "builder platform identity")
    require(build, 'x86_64) HOST_ARCH="x86_64"', "x86_64 host architecture")
    require(build, 'aarch64|arm64) HOST_ARCH="aarch64"', "aarch64 host architecture")
    require(build, 'check_non_privileged_policy()', "non-privileged builder policy")
    require(build, 'check_host_prerequisites()', "host prerequisite checks")
    require(build, 'TIMBLEEPAD_ALLOW_UNSUPPORTED_HOST', "explicit unsupported-host override")
    require(build, 'bash "$QA_RUNNER"', "canonical nested release QA")
    require(build, '"$VENV/bin/python" -m pip check', "build environment dependency check")
    require(build, 'SOURCE_MANIFEST="${PROGRAM_ROOT}/SOURCE_MANIFEST.sha256"', "source manifest build input")
    require(build, 'COMPONENT_MANIFEST="${PROJECT_ROOT}/suite-pythoine-component.json"', "Suite component manifest build input")
    require(build, 'ROOT_README="${PROJECT_ROOT}/README.md"', "root README build input")
    require(build, 'echo "Root README SHA-256: $(sha256sum "$ROOT_README"', "root README build provenance")
    require(build, 'BUILD_REQUIREMENTS="${PROGRAM_ROOT}/packaging/pyinstaller/build-requirements.txt"', "canonical PyInstaller build requirements")
    require(build, "validate_build_root()", "guarded AppImage build root")
    require(build, 'echo "Suite component manifest SHA-256:', "Suite component manifest provenance")
    require(build, 'PYTHONPYCACHEPREFIX="${BUILD_ROOT}/pycache"', "isolated bytecode compilation")
    require(build, '"$VENV/bin/python" -m compileall -q', "pre-freeze source compilation")
    require(build, 'validate_desktop_entry_basic()', "built-in desktop validation")
    require(build, 'validate_appstream_basic()', "built-in AppStream validation")
    require(build, 'MimeType=.*text/html;', "HTML desktop validation")
    require(build, 'MimeType=.*text/css;', "CSS desktop validation")
    require(build, 'MimeType=.*application/xml;', "XML desktop validation")
    require(build, 'QT_QPA_PLATFORM=offscreen', "isolated offscreen smoke tests")
    require(build, 'timeout 30s env', "bounded smoke tests")
    require(build, 'run_gui_smoke_test()', "real GUI smoke-test harness")
    require(build, '"$@" --timbleepad-smoke-test', "packaged GUI startup probe")
    require(build, 'run_gui_smoke_test "AppDir GUI"', "AppDir GUI smoke test")
    require(build, 'run_gui_smoke_test "AppDir GUI dark-theme"', "AppDir dark GUI theme smoke test")
    require(build, 'run_gui_smoke_test "AppDir GUI light-theme"', "AppDir light GUI theme smoke test")
    require(build, 'run_gui_smoke_test "AppDir GUI system-theme"', "AppDir system GUI theme smoke test")
    require(build, 'run_gui_smoke_test "final AppImage GUI"', "final AppImage GUI smoke test")
    require(build, 'run_gui_smoke_test "final AppImage GUI dark-theme"', "final dark GUI theme smoke test")
    require(build, 'run_gui_smoke_test "final AppImage GUI light-theme"', "final light GUI theme smoke test")
    require(build, 'run_gui_smoke_test "final AppImage GUI system-theme"', "final system GUI theme smoke test")
    require(build, 'CACHE_DIR="${XDG_CACHE_HOME:-${HOME}/.cache}/timbleepad-appimage-tools"', "persistent appimagetool cache")
    require(build, 'APPIMAGETOOL_PATH', "appimagetool override")
    require(build, 'APPIMAGETOOL_SHA256', "appimagetool hash pin")
    require(build, 'releases/download/continuous/appimagetool-${ARCH}.AppImage', "appimagetool URL")
    require(build, 'local part="${destination}.part"', "temporary appimagetool download")
    require(build, 'MAX_TOOL_BYTES=$((200 * 1024 * 1024))', "bounded appimagetool size")
    require(build, "curl --proto '=https' --tlsv1.2", "HTTPS/TLS appimagetool download")
    require(build, '--max-time 300', "bounded total appimagetool download time")
    require(build, '[[ "$magic" == "7f454c46" ]]', "appimagetool ELF validation")
    require(build, 'TIMBLEEPAD_RELEASE_BUILD=1 requires APPIMAGETOOL_SHA256', "release-mode hash pin requirement")
    require(build, 'run_version_smoke_test "final AppImage dark-theme"', "final dark-theme smoke test")
    require(build, 'run_version_smoke_test "final AppImage light-theme"', "final light-theme smoke test")
    require(build, 'run_version_smoke_test "final AppImage system-theme"', "final system-theme smoke test")
    require(build, 'clean_source_python_caches()', "source cache cleanup")
    require(build, 'source_tree_sha256()', "whole-source-tree provenance hash")
    require(build, 'echo "Source tree SHA-256: $(source_tree_sha256)"', "source tree hash build metadata")
    require(build, 'echo "SOURCE_MANIFEST.sha256 SHA-256: $(sha256sum "$SOURCE_MANIFEST"', "source manifest provenance")
    require(build, 'echo "Builder SHA-256: $(sha256sum "$0"', "builder provenance")
    require(build, 'echo "Fedora release: ${FEDORA_RELEASE}"', "Fedora build provenance")
    require(build, 'echo "Privilege policy: non-privileged; no sudo/dnf/su/pkexec"', "privilege-policy provenance")
    forbid(build, "application/pdf", "Timblee desktop/AppStream validation")
    for forbidden_pdf_probe in ("Qt6Pdf", "QtPdf", "Qt6PrintSupport", "QtPrintSupport"):
        forbid(build, forbidden_pdf_probe, "Timblee AppImage builder PDF/print probe")
    forbid(build, 'APP_NAME="Portapad"', "Timblee builder identity")
    forbid(build, "releases/latest/download", "hardened AppImage builder")
    require(spec, 'collect_submodules("timblee_pad")', "PyInstaller package")
    require(spec, '"timblee_pad/assets"', "PyInstaller asset destination")
    require(spec, '"PyQt6.QtPdf"', "PyInstaller PDF exclusion")
    require(spec, '"PyQt6.QtPdfWidgets"', "PyInstaller PDF widgets exclusion")
    require(spec, '"PyQt6.QtPrintSupport"', "PyInstaller print exclusion")
    forbid(spec, "QtWebEngine", "PyInstaller spec")
    require(portable, '"$SCRIPT_DIR/../.."', "portable helper launcher root")
    require(appimage_test, 'aarch64|arm64) HOST_ARCH="aarch64"', "native AppImage test architecture")
    require(appimage_test, 'Timblee-Pad-0.2.3-${ARCH}.AppImage', "architecture-aware AppImage test filename")
    require(appimage_test, '--timbleepad-smoke-test', "standalone AppImage GUI smoke probe")

    root_readme = PROJECT_ROOT / "README.md"
    if not root_readme.is_file():
        fail("root README is missing")
    root_readme_text = root_readme.read_text(encoding="utf-8")
    require(root_readme_text, "Current release: **0.2.3**", "root README current release")

    for required in (
        PROGRAM_ROOT / "docs/README.md",
        PROGRAM_ROOT / "docs/QA.md",
        PROGRAM_ROOT / "docs/SECURITY_AUDIT.md",
        PROGRAM_ROOT / "docs/RELEASE_NOTES.md",
        PROGRAM_ROOT / "LICENSE",
        PROGRAM_ROOT / "requirements.txt",
        PROGRAM_ROOT / "portable/run-timbleepad.sh",
        PROGRAM_ROOT / "qa/tests/test_packaging.py",
    ):
        if not required.is_file():
            fail(f"missing release file: {required.relative_to(PROJECT_ROOT)}")

    for stale in (
        PROJECT_ROOT / "timbleepad",
        PROJECT_ROOT / "packaging",
        PROJECT_ROOT / "portable",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "tools",
        PROJECT_ROOT / "README",
        PROJECT_ROOT / "requirements.txt",
    ):
        if stale.exists():
            fail(f"stale top-level path remains: {stale.relative_to(PROJECT_ROOT)}")

    official_master = PROGRAM_ROOT / "assets/icons/timbleepad-master.png"
    official_master_sha256 = "ae82645ac519af475e1533d07dcdb40666e620e3247ac5ef260034285d9c1be1"
    if hashlib.sha256(official_master.read_bytes()).hexdigest() != official_master_sha256:
        fail("Official Timblee Pad master icon is not the approved 0.1.0-r2 asset")
    source_svg = PROGRAM_ROOT / "assets/icons/timbleepad.svg"
    appimage_svg = PROGRAM_ROOT / "packaging/appimage/timbleepad.svg"
    if source_svg.read_bytes() != appimage_svg.read_bytes():
        fail("Source/AppImage Timblee SVG wrappers must remain byte-identical")

    if not MANIFEST.is_file():
        fail("timblee_pad/SOURCE_MANIFEST.sha256 is missing")
    manifest: dict[str, str] = {}
    for raw_line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            digest, relative = raw_line.split("  ", 1)
        except ValueError:
            fail("malformed SOURCE_MANIFEST.sha256 entry")
        manifest[relative] = digest

    actual_files = manifest_files()
    actual_names = {f"./{path.relative_to(PROJECT_ROOT).as_posix()}" for path in actual_files}
    if set(manifest) != actual_names:
        missing = sorted(actual_names - set(manifest))
        extra = sorted(set(manifest) - actual_names)
        fail(f"source manifest file list mismatch; missing={missing[:1]} extra={extra[:1]}")
    for path in actual_files:
        relative = f"./{path.relative_to(PROJECT_ROOT).as_posix()}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest.get(relative) != digest:
            fail(f"source manifest digest mismatch: {relative}")

    print("Timblee Pad 0.2.3 static release checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
