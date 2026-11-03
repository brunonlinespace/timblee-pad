#!/usr/bin/env python3
"""Static regressions for Timblee Pad product scope and packaging."""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
import unittest
from pathlib import Path

from timblee_pad.html_tags import COMMON_HTML_TAGS, ESSENTIAL_TAGS, HTML5_TEMPLATE, TAG_CATEGORIES, custom_tag
from timblee_pad.library_catalog import CSS_LIBRARY, XML_LIBRARY

ROOT = Path(__file__).resolve().parents[3]
PROGRAM_ROOT = ROOT / "timblee_pad"


class PackagingRegressionTests(unittest.TestCase):
    def test_version_probe_works_without_loading_gui(self) -> None:
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), "--version"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "Timblee Pad 0.2.3")

    def test_gui_smoke_probe_is_hidden_but_reaches_real_gui_main(self) -> None:
        launcher = (ROOT / "main.py").read_text(encoding="utf-8")
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("--timbleepad-smoke-test", launcher)
        self.assertIn('"--timbleepad-smoke-test"', app_source)
        self.assertIn("help=argparse.SUPPRESS", app_source)
        self.assertIn("window = TimbleePadWindow(valid_files[0] if valid_files else None)", app_source)
        self.assertIn('print("GUI smoke test passed.", flush=True)', app_source)
        self.assertIn("QTimer.singleShot(0, finish_smoke_test)", app_source)
        self.assertIn("status = application.exec()", app_source)

    def test_identity_and_native_file_scope(self) -> None:
        init_source = (PROGRAM_ROOT / "__init__.py").read_text(encoding="utf-8")
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('APP_NAME = "Timblee Pad"', init_source)
        self.assertIn('SUPPORTED_WEB_SUFFIXES = SUPPORTED_SOURCE_SUFFIXES', app_source)
        profiles = (PROGRAM_ROOT / "document_profiles.py").read_text(encoding="utf-8")
        for suffix in ('".html"', '".htm"', '".css"', '".xml"', '".xsd"', '".xsl"', '".xslt"'):
            self.assertIn(suffix, profiles)
        self.assertNotIn('".svg"', profiles)
        self.assertIn("Timblee Source Files (*.html *.htm *.css *.xml *.xsd *.xsl *.xslt)", profiles)
        self.assertIn("Celebrating Tim Berners-Lee\'s contribution to the work.", app_source)

    def test_preview_and_library_replace_run_controls(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('addMenu("&Library")', app_source)
        self.assertIn('"Preview in default browser"', app_source)
        self.assertIn("def preview_in_default_browser", app_source)
        self.assertIn("def _show_launch_error", app_source)
        self.assertIn('"Library..."', app_source)
        self.assertIn('"My Favourites"', app_source)
        self.assertIn('"Remove Custom HTML Tag..."', app_source)
        self.assertIn('"Import HTML Tags..."', app_source)
        self.assertIn('"Export HTML Tags..."', app_source)
        self.assertIn("def import_tags", app_source)
        self.assertIn("def export_tags", app_source)
        self.assertNotIn('addMenu("&Run")', app_source)
        for forbidden in ("Launch in Terminal", "Launch as Admin", "Force Stop", "Make Executable"):
            self.assertNotIn(forbidden, app_source)

    def test_html_css_and_xml_highlighters_replace_script_highlighters(self) -> None:
        source = (PROGRAM_ROOT / "code_editor.py").read_text(encoding="utf-8")
        self.assertIn("class HTMLHighlighter", source)
        self.assertIn("class CSSHighlighter", source)
        self.assertIn("class XMLHighlighter", source)
        self.assertIn("def _matching_tag_selections", source)
        self.assertIn("def _try_auto_close_html_tag", source)
        self.assertNotIn("class PythonHighlighter", source)
        self.assertNotIn("class ShellHighlighter", source)

    def test_light_editor_syntax_colours_meet_contrast_floor(self) -> None:
        source = (PROGRAM_ROOT / "code_editor.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        schemes = None
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "EDITOR_COLOR_SCHEMES":
                schemes = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(schemes)
        light = schemes["light"]

        def luminance(colour: str) -> float:
            values = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        background = luminance(light["background"])
        for role in ("foreground", "tag", "attribute", "value", "comment", "entity", "doctype", "selector", "property", "number", "at_rule", "keyword"):
            fg = luminance(light[role])
            contrast = (max(background, fg) + 0.05) / (min(background, fg) + 0.05)
            self.assertGreaterEqual(contrast, 4.5, role)

    def test_html5_template_and_library_baseline(self) -> None:
        folded = HTML5_TEMPLATE.casefold()
        for fragment in ("<!doctype html>", '<html lang="en">', '<meta charset="utf-8">', 'name="viewport"', "<title>", "<body>"):
            self.assertIn(fragment, folded)
        keys = {spec.key for spec in COMMON_HTML_TAGS}
        for required in ("html", "head", "title", "body", "header", "main", "section", "h1", "h6", "p", "br", "hr", "a", "img", "ul", "table", "form"):
            self.assertIn(required, keys)
        self.assertGreaterEqual(len(COMMON_HTML_TAGS), 60)
        self.assertEqual(custom_tag("my-card").opening, "<my-card>")
        with self.assertRaises(ValueError):
            custom_tag("bad tag")


    def test_tag_library_categories_and_sidebar_controls(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertEqual(
            TAG_CATEGORIES,
            (
                "Document", "Structure", "Text", "Links & Media", "Lists",
                "Tables", "Forms", "Interactive", "Graphics", "Advanced", "Custom",
            ),
        )
        self.assertIn("class TagLibraryPanel(QWidget)", app_source)
        self.assertIn('self.tabs = QTabWidget(self)', app_source)
        self.assertIn('self.catalog_combo = QComboBox(self)', app_source)
        self.assertIn('self.close_sidebar_button.setText("×")', app_source)
        self.assertIn('base = ("All", *self.window.library_categories())', app_source)
        self.assertIn('return ("Favourites", *base) if has_favourites else base', app_source)
        self.assertIn('self.catalog_combo.currentText() or categories[0]', app_source)
        self.assertIn('self.favourites_menu.menuAction().setVisible(bool(specs))', app_source)
        self.assertNotIn('No favourites for this document type', app_source)
        self.assertIn('self.view_menu.addMenu("Library")', app_source)
        self.assertIn('"left": "Left Sidebar"', app_source)
        self.assertIn('"right": "Right Sidebar"', app_source)
        self.assertIn('"disabled": "Floating Only"', app_source)
        library_index = app_source.index('self.view_menu.addMenu("Library")')
        layout_index = app_source.index('self.view_menu.addMenu("Layout")')
        self.assertLess(library_index, layout_index)
        self.assertIn("self.view_menu.addSeparator()", app_source[library_index:layout_index])
        self.assertIn('self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal, self)', app_source)
        self.assertIn('"tag_library_sidebar_position": self.tag_library_sidebar_position', app_source)
        self.assertIn('self.import_button = QPushButton("Import Tags…", self)', app_source)
        self.assertIn('self.export_button = QPushButton("Export Tags…", self)', app_source)

    def test_empty_favourites_are_omitted_and_library_falls_back_to_all(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('base = ("All", *self.window.library_categories())', app_source)
        self.assertIn('return ("Favourites", *base) if has_favourites else base', app_source)
        self.assertIn('self.catalog_combo.currentText() or categories[0]', app_source)
        self.assertIn('index = self.catalog_combo.findText("All")', app_source)
        self.assertIn('target = self.tabs.indexOf(self._lists.get("All"))', app_source)
        self.assertIn('self.favourites_menu.menuAction().setVisible(bool(specs))', app_source)
        self.assertNotIn('No favourites for this document type', app_source)

    def test_tag_library_tab_signal_is_connected_after_detail_controls_exist(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        insert_index = app_source.index('self.insert_button = QPushButton("Insert", self)')
        favourite_index = app_source.index('self.favourite_button = QPushButton("Add to My Favourites", self)')
        remove_index = app_source.index('self.remove_custom_button = QPushButton("Remove Custom", self)')
        connect_index = app_source.index('self.tabs.currentChanged.connect(lambda _index: self._update_details())')
        self.assertGreater(connect_index, insert_index)
        self.assertGreater(connect_index, favourite_index)
        self.assertGreater(connect_index, remove_index)


    def test_exp1_r1_ui_contract_and_official_r2_assets(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        editor_source = (PROGRAM_ROOT / "code_editor.py").read_text(encoding="utf-8")
        self.assertIn('"Duplicate Line / Selection"', app_source)
        self.assertIn('"Delete Line"', app_source)
        self.assertIn('QKeySequence("Ctrl+Shift+K")', app_source)
        self.assertIn("def delete_current_line", editor_source)
        self.assertIn('"Preview", self.preview_in_default_browser', app_source)
        menu_index = app_source.index("primary_layout.addWidget(self.menu_buttons_container)")
        preview_index = app_source.index("primary_layout.addWidget(self.preview_button)")
        self.assertLess(menu_index, preview_index)
        self.assertNotIn("document_type_button", app_source)
        self.assertIn('self.file_menu.addMenu("Document Type")', app_source)

        expected = {
            "timbleepad-128.png": "cc383b092eb941c74d3895c55c07e8f193f1221378f89f9d145bf13f92e7ad00",
            "timbleepad-16.png": "b5c12e8e50a0bdc466f6355ee50e25ed0fbfd8de679b99fdf7a4b71b4691fcc9",
            "timbleepad-24.png": "046f8bf3b02f63018e8dd0a80aef7085bb07b16e847546f103d655d2cb1508ac",
            "timbleepad-256.png": "8ecf4a0901c45ded576330c539ef86bfaee0f169c40e8278175c03157c862cb8",
            "timbleepad-32.png": "d8779ccd0105c77cc5aa66b16021393370fe2c0c7e7ebe4a5a27c4785a16e327",
            "timbleepad-48.png": "15b33ba40f12b1e820357acad736ccd3f23672160142d619eb5b49edeb503b4a",
            "timbleepad-512.png": "4176c93a395ff31d8dace018b92d7e6d3de9de2739f53c8b7c41930d260148a6",
            "timbleepad-64.png": "c21b872121db58bdbd6423f8df8fa3ca99887882dc22b62b80fc6581f43bc5c1",
            "timbleepad-master.png": "ae82645ac519af475e1533d07dcdb40666e620e3247ac5ef260034285d9c1be1",
            "timbleepad.png": "4176c93a395ff31d8dace018b92d7e6d3de9de2739f53c8b7c41930d260148a6",
            "timbleepad.svg": "8036f12b61e2f6776487ae635805428e82c04a21a00c26a6849f12d1156a300f",
        }
        for name, digest in expected.items():
            path = PROGRAM_ROOT / "assets/icons" / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        wrapper = PROGRAM_ROOT / "packaging/appimage/timbleepad.svg"
        self.assertEqual(
            hashlib.sha256(wrapper.read_bytes()).hexdigest(),
            expected["timbleepad.svg"],
        )

    def test_exp1_r2_start_layout_dark_editor_and_dragdrop_contract(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")

        # The Start a Document page must be an alternate workspace page, not
        # a separate outer-layout widget that can displace saved chrome.
        self.assertIn("QStackedWidget", app_source)
        self.assertIn("self.workspace_host = QStackedWidget(self)", app_source)
        self.assertIn("self.workspace_host.addWidget(self.start_panel)", app_source)
        self.assertIn("self.workspace_host.addWidget(self.editor)", app_source)
        self.assertIn("self.workspace_splitter.addWidget(self.document_column)", app_source)
        layout_start = app_source.index("    def _apply_layout_mode(self) -> None:")
        layout_end = app_source.index("    def set_tag_library_sidebar_position", layout_start)
        layout_source = app_source[layout_start:layout_end]
        self.assertIn("self.workspace_host", layout_source)
        self.assertIn("self.workspace_splitter", layout_source)
        start_start = app_source.index("    def _show_start_panel(self) -> None:")
        start_end = app_source.index("    def _show_document_workspace", start_start)
        start_source = app_source[start_start:start_end]
        self.assertIn("self.workspace_host.setCurrentWidget(self.start_panel)", start_source)
        self.assertIn("self._apply_layout_mode()", start_source)
        self.assertNotIn("self.search_container.hide()", start_source)
        self.assertNotIn("self.bottom_search.hide()", start_source)

        # Editor palette is independent of AppImage chrome and persists.
        self.assertIn("self.dark_editor = True", app_source)
        self.assertIn('boolean_value("dark_editor", True)', app_source)
        self.assertIn('"dark_editor": self.dark_editor', app_source)
        self.assertIn('"Dark Editor"', app_source)
        self.assertIn("def toggle_dark_editor", app_source)
        self.assertIn('self.editor.set_color_scheme("dark" if self.dark_editor else "light")', app_source)

        # User-facing drag/drop wording follows the Pad-family convention.
        self.assertIn('self.view_menu.addMenu("File Drag and Drop")', app_source)
        self.assertIn('"active_window": "Opens on Active Window"', app_source)
        self.assertIn('"new_window": "Opens on New Window"', app_source)
        self.assertNotIn('self.view_menu.addMenu("Behaviour")', app_source)
        self.assertNotIn("Drag and drop opens on active window", app_source)
        self.assertNotIn("Drag and drop opens on new window", app_source)

    def test_exp1_r3_start_find_and_edit_disabled_state_contract(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")

        start_start = app_source.index("    def _show_start_panel(self) -> None:")
        start_end = app_source.index("    def _show_document_workspace", start_start)
        start_source = app_source[start_start:start_end]
        self.assertIn("self._apply_layout_mode()", start_source)
        self.assertIn("self._update_find_bar_state()", start_source)
        self.assertIn("self._update_edit_action_state()", start_source)
        self.assertNotIn("self.search_container.hide()", start_source)
        self.assertNotIn("self.bottom_search.hide()", start_source)

        find_start = app_source.index("    def _update_find_bar_state(self) -> None:")
        find_end = app_source.index("    def toggle_word_wrap", find_start)
        find_source = app_source[find_start:find_end]
        self.assertIn("enabled = self.document_active", find_source)
        self.assertIn("self.search_container.setEnabled(enabled)", find_source)
        self.assertIn("self.bottom_search.setEnabled(enabled)", find_source)
        for action_name in (
            "self.focus_find_action",
            "self.find_next_action",
            "self.find_previous_action",
            "self.clear_search_action",
        ):
            self.assertIn(action_name, find_source)

        edit_start = app_source.index("    def _update_edit_action_state(self) -> None:")
        edit_end = app_source.index("    def _update_find_bar_state", edit_start)
        edit_source = app_source[edit_start:edit_end]
        self.assertIn("if not self.document_active:", edit_source)
        for action_name in (
            "self.undo_action",
            "self.redo_action",
            "self.cut_action",
            "self.copy_action",
            "self.paste_action",
            "self.delete_text_action",
            "self.comment_action",
            "self.duplicate_action",
            "self.delete_line_action",
            "self.select_all_action",
            "self.go_to_line_action",
            "self.replace_action",
        ):
            self.assertIn(action_name, edit_source)
        # View Only remains narrower than the no-document state: selection,
        # copy and navigation stay enabled when a document is active.
        mutating_start = edit_source.index("editing_enabled = not self.view_only")
        mutating_source = edit_source[mutating_start:]
        self.assertNotIn("self.copy_action", mutating_source)
        self.assertNotIn("self.select_all_action", mutating_source)
        self.assertNotIn("self.go_to_line_action", mutating_source)
        self.assertIn("self.delete_line_action", mutating_source)

        workspace_start = app_source.index("    def _show_document_workspace(self) -> None:")
        workspace_end = app_source.index("    def _handle_startup_without_file", workspace_start)
        workspace_source = app_source[workspace_start:workspace_end]
        self.assertIn("self._update_find_bar_state()", workspace_source)
        self.assertIn("self._update_edit_action_state()", workspace_source)

    def test_portable_root_contains_expected_release_files(self) -> None:
        entries = {path.name for path in ROOT.iterdir()}
        self.assertEqual(entries, {"README.md", "main.py", "suite-pythoine-component.json", "timblee_pad"})

    def test_root_readme_is_locked_public_release_file(self) -> None:
        readme = ROOT / "README.md"
        self.assertTrue(readme.is_file())
        text = readme.read_text(encoding="utf-8")
        self.assertIn("# Timblee Pad", text)
        self.assertIn("Current release: **0.2.3**", text)
        self.assertNotIn("Current release: **0.2.0**", text)

    def test_appimage_metadata_covers_html_css_xml_only(self) -> None:
        desktop = (PROGRAM_ROOT / "packaging/appimage/timbleepad.desktop").read_text(encoding="utf-8")
        metainfo = (PROGRAM_ROOT / "packaging/appimage/io.github.brunonlinespace.timbleepad.metainfo.xml").read_text(encoding="utf-8")
        apprun = (PROGRAM_ROOT / "packaging/appimage/AppRun").read_text(encoding="utf-8")
        self.assertIn("MimeType=text/html;text/css;application/xml;text/xml;", desktop)
        self.assertNotIn("image/svg+xml", desktop + metainfo)
        self.assertIn("https://github.com/brunonlinespace/timblee-pad", metainfo)
        self.assertIn('BUNDLE="$APPDIR/usr/lib/timbleepad"', apprun)
        self.assertIn('TIMBLEEPAD_APPIMAGE_THEME="dark"', apprun)
        self.assertNotIn("sheepypad", apprun.casefold())

    def test_appimage_filename_uses_application_version(self) -> None:
        script = (PROGRAM_ROOT / "packaging/fedora/build-appimage.sh").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION="0.2.3"', script)
        self.assertIn('APPIMAGE="${DIST_DIR}/Timblee-Pad-${APP_VERSION}-${ARCH}.AppImage"', script)
        self.assertIn('APPDIR="${BUILD_ROOT}/TimbleePad.AppDir"', script)
        self.assertIn('ARCH="$ARCH" VERSION="$APP_VERSION"', script)

    def test_hardened_appimage_builder_contract(self) -> None:
        script = (PROGRAM_ROOT / "packaging/fedora/build-appimage.sh").read_text(encoding="utf-8")
        self.assertIn("umask 022", script)
        self.assertIn('APP_NAME="Timblee Pad"', script)
        self.assertIn('APP_ID="timbleepad"', script)
        self.assertIn('aarch64|arm64) HOST_ARCH="aarch64"', script)
        self.assertIn("check_non_privileged_policy()", script)
        self.assertIn("check_host_prerequisites()", script)
        self.assertIn("validate_build_root()", script)
        self.assertIn('COMPONENT_MANIFEST="${PROJECT_ROOT}/suite-pythoine-component.json"', script)
        self.assertIn('ROOT_README="${PROJECT_ROOT}/README.md"', script)
        self.assertIn('echo "Root README SHA-256: $(sha256sum "$ROOT_README"', script)
        self.assertIn('BUILD_REQUIREMENTS="${PROGRAM_ROOT}/packaging/pyinstaller/build-requirements.txt"', script)
        self.assertIn("TIMBLEEPAD_ALLOW_UNSUPPORTED_HOST", script)
        self.assertIn('bash "$QA_RUNNER"', script)
        self.assertIn('"$VENV/bin/python" -m pip check', script)
        self.assertIn("validate_desktop_entry_basic()", script)
        self.assertIn("validate_appstream_basic()", script)
        self.assertIn("QT_QPA_PLATFORM=offscreen", script)
        self.assertIn("timeout 30s env", script)
        self.assertIn("APPIMAGETOOL_PATH", script)
        self.assertIn("APPIMAGETOOL_SHA256", script)
        self.assertIn('releases/download/continuous/appimagetool-${ARCH}.AppImage', script)
        self.assertIn('local part="${destination}.part"', script)
        self.assertIn('MAX_TOOL_BYTES=$((200 * 1024 * 1024))', script)
        self.assertIn("curl --proto '=https' --tlsv1.2", script)
        self.assertIn('[[ "$magic" == "7f454c46" ]]', script)
        self.assertIn("TIMBLEEPAD_RELEASE_BUILD=1 requires APPIMAGETOOL_SHA256", script)
        self.assertIn('run_version_smoke_test "final AppImage dark-theme"', script)
        self.assertIn('run_version_smoke_test "final AppImage light-theme"', script)
        self.assertIn('run_version_smoke_test "final AppImage system-theme"', script)
        self.assertNotIn("releases/latest/download", script)

    def test_hardened_builder_preserves_r7_source_cleanliness_and_provenance(self) -> None:
        script = (PROGRAM_ROOT / "packaging/fedora/build-appimage.sh").read_text(encoding="utf-8")
        self.assertIn("clean_source_python_caches()", script)
        self.assertIn("source_tree_sha256()", script)
        self.assertIn('echo "Source tree SHA-256: $(source_tree_sha256)"', script)
        self.assertNotIn('APP_NAME="Portapad"', script)
        self.assertNotIn("application/pdf", script)
        for forbidden_pdf_probe in ("Qt6Pdf", "QtPdf", "Qt6PrintSupport", "QtPrintSupport"):
            self.assertNotIn(forbidden_pdf_probe, script)

        spec = (PROGRAM_ROOT / "packaging/pyinstaller/timbleepad.spec").read_text(encoding="utf-8")
        for excluded_module in ("PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtPrintSupport"):
            self.assertIn(excluded_module, spec)


    def test_010_builder_keeps_r9_gui_smoke_compile_and_richer_provenance(self) -> None:
        script = (PROGRAM_ROOT / "packaging/fedora/build-appimage.sh").read_text(encoding="utf-8")
        self.assertIn('SOURCE_MANIFEST="${PROGRAM_ROOT}/SOURCE_MANIFEST.sha256"', script)
        self.assertIn('PYTHONPYCACHEPREFIX="${BUILD_ROOT}/pycache"', script)
        self.assertIn('"$VENV/bin/python" -m compileall -q', script)
        self.assertIn("run_gui_smoke_test()", script)
        self.assertIn('"$@" --timbleepad-smoke-test', script)
        self.assertIn('run_gui_smoke_test "AppDir GUI"', script)
        self.assertIn('run_gui_smoke_test "AppDir GUI dark-theme"', script)
        self.assertIn('run_gui_smoke_test "AppDir GUI light-theme"', script)
        self.assertIn('run_gui_smoke_test "AppDir GUI system-theme"', script)
        self.assertIn('run_gui_smoke_test "final AppImage GUI"', script)
        self.assertIn('run_gui_smoke_test "final AppImage GUI dark-theme"', script)
        self.assertIn('run_gui_smoke_test "final AppImage GUI light-theme"', script)
        self.assertIn('run_gui_smoke_test "final AppImage GUI system-theme"', script)
        self.assertIn("--max-time 300", script)
        self.assertIn('echo "SOURCE_MANIFEST.sha256 SHA-256: $(sha256sum "$SOURCE_MANIFEST"', script)
        self.assertIn('echo "Builder SHA-256: $(sha256sum "$0"', script)
        self.assertIn('echo "Fedora release: ${FEDORA_RELEASE}"', script)
        self.assertIn('echo "Privilege policy: non-privileged; no sudo/dnf/su/pkexec"', script)
        self.assertIn('run_version_smoke_test "final AppImage dark-theme"', script)
        self.assertIn('run_version_smoke_test "final AppImage light-theme"', script)
        self.assertIn('run_version_smoke_test "final AppImage system-theme"', script)



    def test_010_r1_builder_has_no_pdf_or_printsupport_bundle_probes(self) -> None:
        script = (PROGRAM_ROOT / "packaging/fedora/build-appimage.sh").read_text(encoding="utf-8")
        for forbidden_pdf_probe in ("Qt6Pdf", "QtPdf", "Qt6PrintSupport", "QtPrintSupport", "application/pdf"):
            self.assertNotIn(forbidden_pdf_probe, script)

        spec = (PROGRAM_ROOT / "packaging/pyinstaller/timbleepad.spec").read_text(encoding="utf-8")
        for excluded_module in ("PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtPrintSupport"):
            self.assertIn(excluded_module, spec)

    def test_010_gui_smoke_validates_packaged_theme_application(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('requested_smoke_theme = os.environ.get("TIMBLEEPAD_APPIMAGE_THEME"', app_source)
        self.assertIn('window.effective_appimage_theme() != requested_smoke_theme', app_source)
        self.assertIn('stylesheet_active = bool(application.styleSheet().strip())', app_source)
        self.assertIn('requested_smoke_theme in {"dark", "light"} and not stylesheet_active', app_source)
        self.assertIn('requested_smoke_theme == "system" and stylesheet_active', app_source)

    def test_appimage_test_helper_tracks_native_architecture(self) -> None:
        script = (PROGRAM_ROOT / "packaging/fedora/test-appimage.sh").read_text(encoding="utf-8")
        self.assertIn('aarch64|arm64) HOST_ARCH="aarch64"', script)
        self.assertIn('Timblee-Pad-0.2.3-${ARCH}.AppImage', script)
        self.assertIn('--timbleepad-smoke-test', script)
        self.assertIn('QT_QPA_PLATFORM=offscreen', script)

    def test_html_css_xml_document_model_and_localhost_preview_contract(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        templates_source = (PROGRAM_ROOT / "templates.py").read_text(encoding="utf-8")
        library_source = (PROGRAM_ROOT / "library_catalog.py").read_text(encoding="utf-8")
        self.assertIn("class NewDocumentDialog(QDialog)", app_source)
        self.assertIn("class DefaultNewDocumentDialog(QDialog)", app_source)
        self.assertIn("class TemplateManagerDialog(QDialog)", app_source)
        self.assertIn('self.file_menu.addMenu("Document Type")', app_source)
        self.assertIn('self.tags_menu = self.app_menu_bar.addMenu("&Library")', app_source)
        self.assertIn('http.server.ThreadingHTTPServer(("127.0.0.1", 0)', app_source)
        self.assertIn('url = f"http://127.0.0.1:{port}/', app_source)
        self.assertNotIn("ET.fromstring", app_source)
        self.assertNotIn("document_check", app_source)
        self.assertNotIn("Type OK", app_source)
        self.assertIn('CURSOR_MARKER = "[[cursor]]"', templates_source)
        for key in ("html:html5", "css:basic", "xml:basic"):
            self.assertIn(key, templates_source)
        for prefix in ('"css:', '"xml:'):
            self.assertIn(prefix, library_source)
        combined = (app_source + "\n" + templates_source + "\n" + library_source).casefold()
        for forbidden in ('subprocess.run(["node"', "npm install", "eslint", "prettier", "qwebengineview"):
            self.assertNotIn(forbidden, combined)

    def test_r4_simplifies_type_status_sidebar_and_split_layout(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")
        profiles = (PROGRAM_ROOT / "document_profiles.py").read_text(encoding="utf-8")
        self.assertNotIn("document_type_button", app_source)
        self.assertNotIn("document_check_label", app_source)
        self.assertNotIn("document_check_summary", app_source)
        self.assertIn('DOCUMENT_TYPE_ORDER = ("html", "css", "xml")', profiles)
        self.assertNotIn('"svg": DocumentProfile', profiles)
        self.assertIn("sidebar_mode=True", app_source)
        self.assertIn('self.catalog_combo = QComboBox(self)', app_source)
        self.assertIn('self.close_sidebar_button.setText("×")', app_source)
        self.assertIn('self.document_column_layout.addWidget(self.bottom_search)', app_source)
        self.assertIn('self.workspace_splitter.insertWidget(0, sidebar)', app_source)
        self.assertIn('self.workspace_splitter.insertWidget(1, content)', app_source)
        self.assertNotIn('self.main_layout.addWidget(self.bottom_search)', app_source)

    def test_r5_enriches_library_and_harmonises_shortcuts(self) -> None:
        app_source = (PROGRAM_ROOT / "app.py").read_text(encoding="utf-8")

        # Preserve the full r4 baseline while adding broad current-language coverage.
        html_keys = {spec.key for spec in COMMON_HTML_TAGS}
        self.assertGreaterEqual(len(COMMON_HTML_TAGS), 114)
        for key in (
            "html", "head", "title", "body", "meta", "link", "style", "script",
            "header", "nav", "main", "section", "article", "aside", "footer",
            "div", "span", "h1", "h6", "p", "br", "hr", "strong", "em",
            "a", "img", "picture", "audio", "video", "source", "ul", "ol",
            "table", "form", "input", "textarea", "button", "details", "dialog",
            "canvas", "svg", "template",
            "abbr", "address", "area", "base", "bdi", "bdo", "cite", "col",
            "colgroup", "data", "datalist", "del", "dfn", "embed", "hgroup",
            "iframe", "ins", "kbd", "map", "menu", "noscript", "object",
            "optgroup", "output", "ruby", "search", "slot", "time", "track",
            "var", "wbr", "math",
        ):
            self.assertIn(key, html_keys)

        css_keys = {spec.key for spec in CSS_LIBRARY}
        self.assertEqual(len(css_keys), len(CSS_LIBRARY))
        self.assertGreaterEqual(len(CSS_LIBRARY), 140)
        for key in (
            "css:rule", "css:media", "css:grid", "css:flex", "css:gap",
            "css:color", "css:background", "css:font-family", "css:font-size",
            "css:box-sizing", "css:margin", "css:padding",
            "css:class-rule", "css:grid-columns", "css:flex-shorthand",
            "css:position-sticky", "css:border-radius", "css:transition",
            "css:keyframes", "css:container", "css:supports", "css:font-face",
            "css:custom-property", "css:responsive-grid", "css:visually-hidden",
        ):
            self.assertIn(key, css_keys)

        xml_keys = {spec.key for spec in XML_LIBRARY}
        self.assertEqual(len(xml_keys), len(XML_LIBRARY))
        self.assertGreaterEqual(len(XML_LIBRARY), 90)
        for key in (
            "xml:declaration", "xml:element", "xml:self-closing", "xml:attribute",
            "xml:comment", "xml:cdata", "xml:namespace", "xml:namespace-prefix",
            "xml:processing", "xml:doctype", "xml:xml-lang", "xml:schema-location",
            "xml:xsd-schema", "xml:xsd-element", "xml:xsd-complex-type",
            "xml:xsd-sequence", "xml:xsd-restriction", "xml:xsd-import",
            "xml:xslt-stylesheet", "xml:xslt-template-match",
            "xml:xslt-apply-templates", "xml:xslt-value-of", "xml:xslt-for-each",
            "xml:xslt-choose", "xml:xslt-variable",
        ):
            self.assertIn(key, xml_keys)

        self.assertEqual(
            ESSENTIAL_TAGS,
            (
                ("html", "Ctrl+1"), ("head", "Ctrl+2"), ("title", "Ctrl+3"),
                ("body", "Ctrl+4"), ("main", "Ctrl+5"), ("section", "Ctrl+6"),
                ("p", "Ctrl+7"), ("a", "Ctrl+8"), ("img", "Ctrl+9"),
                ("h1", "Ctrl+0"),
            ),
        )
        self.assertNotIn("Ctrl+Alt", app_source)
        self.assertIn('QKeySequence("Ctrl+L")', app_source)
        self.assertIn('QKeySequence("Ctrl+Shift+E")', app_source)
        self.assertIn('QKeySequence("F2")', app_source)
        self.assertIn('QKeySequence("Ctrl+Shift+D")', app_source)
        self.assertIn('QKeySequence("Ctrl+Shift+O")', app_source)
        delete_start = app_source.index("self.delete_action = self._add_action(")
        delete_end = app_source.index("self.more_actions_menu.addSeparator()", delete_start)
        delete_chunk = app_source[delete_start:delete_end]
        self.assertNotIn("QKeySequence", delete_chunk)
        self.assertNotIn("Ctrl+Delete", app_source)

        # Ctrl+L uses the saved placement preference as a transient visibility toggle.
        self.assertIn("def toggle_library_visibility(self) -> None:", app_source)
        self.assertIn("self.tag_library_sidebar_hidden = False", app_source)
        self.assertIn("self.tag_library_sidebar_hidden = not self.tag_library_sidebar_hidden", app_source)
        self.assertIn("self.window.hide_tag_library_sidebar", app_source)

        # Sidebar remains compact; custom/transfer controls exist only in floating mode.
        sidebar_guard = app_source.index("if not self.sidebar_mode:")
        add_custom = app_source.index('self.add_custom_button = QPushButton("Add Custom Tag…", self)')
        import_button = app_source.index('self.import_button = QPushButton("Import Tags…", self)')
        self.assertLess(sidebar_guard, add_custom)
        self.assertLess(sidebar_guard, import_button)

        # Angle-bracket action names must be forced to plain text in the shortcut dialog.
        self.assertIn("action_label.setTextFormat(Qt.TextFormat.PlainText)", app_source)
        self.assertIn("action_label.setText(action_name)", app_source)
        self.assertIn("*((TAG_BY_KEY[key].label, shortcut) for key, shortcut in ESSENTIAL_TAGS)", app_source)

    def test_printing_and_embedded_browser_stacks_are_absent(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in PROGRAM_ROOT.glob("*.py")
        )
        for forbidden in ("PyQt6.QtPrintSupport", "QPrinter", "QPrintDialog", "QWebEngineView", "PyQt6.QtWebEngine"):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
