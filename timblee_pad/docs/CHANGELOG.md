# Changelog

## 0.2.3 — root README filename correction

- Rename the locked public source-root file from `README` to `README.md`.
- Update portable-root QA, source manifest and Fedora AppImage build provenance to use the corrected filename.
- Preserve the 0.2.2 Sheepy editor-scrolling/gutter corrective unchanged.
- No editor, Library, Preview, shortcut, theme, file-handling, dependency, branding, document-type, or AppImage-policy behavior changes.

## 0.2.2 — Sheepy editor scrolling convergence

- Match Sheepy Pad by disabling QPlainTextEdit global center-on-scroll, eliminating the exaggerated blank scroll region below short documents.
- Preserve explicit `centerCursor()` behavior for Go To Line.
- Match Sheepy Pad's line-number gutter geometry so the gutter stops above a visible native horizontal scrollbar.
- Add Sheepy-equivalent static regression coverage for all three contracts.
- No Library, Preview, shortcut, theme, file-handling, dependency, branding, or packaging behavior changes.

## 0.2.1 — locked public root README

- Add the approved public-facing `README` at the source root.
- Lock that root README content for future releases: only the version number may change unless an explicit README edit is requested.
- Extend the portable-root QA contract to allow and require `README` alongside `main.py`, `suite-pythoine-component.json`, and `timblee_pad/`.
- Make the Fedora AppImage builder require the root README and record its SHA-256 in build provenance.
- No editor, Library, Preview, shortcut, theme, or file-handling behavior changes.

## 0.2.0 — AppImage/portable packaging normalization

- Adopt the canonical Suite Pythoine root component manifest and portable entrypoint contract.
- Standardize AppImage build requirements under `packaging/pyinstaller/`.
- Validate component identity/version/routing from the Fedora builder and record manifest provenance.
- Guard `BUILD_ROOT` cleanup so generated data remains beneath `timblee_pad/build/`.
- Synchronize packaging metadata to 0.2.0 and correct the Pad-family slogan to **Friendly. Fast. Focused.**
- No editor, Library, theme, shortcut, routing or document-workflow behavior changes.

## 0.1.1-exp1-r6 — conditional Favourites presentation

- Hide Favourites from the sidebar selector and floating Library tabs when the active document type has no favourites.
- Default an empty-favourites Library to All, including clean fallback when the last favourite is removed.
- Hide the Library → My Favourites submenu while empty and restore it automatically when favourites exist.
- Added no dependencies; application version remains `0.1.1-exp1`.

## 0.1.1-exp1-r5 — Library enrichment and shortcut harmonisation

- Expanded built-ins additively to 114 HTML, 148 CSS and 94 XML entries; no prior built-in snippet was removed.
- Kept sidebar Library compact by removing its custom/import/export button rows while preserving the floating controls and adding a menu-level Remove Custom HTML Tag command.
- Made Ctrl+L placement-aware: toggle configured sidebar or floating Library; sidebar × no longer rewrites the saved placement.
- Replaced the HTML insertion Ctrl+Alt scheme with Ctrl+1 through Ctrl+0.
- Changed file shortcuts to Ctrl+Shift+E / F2 / Ctrl+Shift+D / Ctrl+Shift+O and removed the Delete File shortcut.
- Fixed Keyboard Shortcuts angle-bracket labels by rendering action names as plain text.
- Added no dependencies; application version remains `0.1.1-exp1`.

## 0.1.1-exp1-r4 — scope simplification and split/sidebar layout

- Removed the automatic document checker/status surface; Timblee no longer claims Type OK, format mismatch, or XML well-formedness.
- Removed the permanent toolbar Document Type shortcut; File → Document Type remains.
- Dropped SVG as a document type, including `.svg` routing/MIME, dedicated templates and Library catalogue.
- Changed the Library sidebar to a catalogue drop-down with a small close button; floating Library retains tabs.
- Changed Split layouts so Find belongs only to the editor column while a left/right Library sidebar spans the full workspace height.
- Added no dependencies; application version remains `0.1.1-exp1`.

## 0.1.1-exp1-r3 — no-document command-state alignment

- Kept the persisted Find bar visible on **Start a Document**, but disabled/greyed until a document is active; the selected Inline/Split position remains unchanged.
- Kept the **Edit** menu visible on the no-document screen while disabling every Edit command there.
- Restored Find and Edit command availability automatically when a document becomes active.
- Preserved **View Only** semantics separately: with an active document, modifying Edit commands are disabled but Copy, Select All and Go To Line remain available.
- Added Delete Line to the View Only mutating-action state set.
- Application version remains `0.1.1-exp1`; this is an experimental source revision only.

## 0.1.1-exp1-r2 — startup layout and editor-palette refinement

- Made **Start a Document** share the same workspace slot as the editor, so all four saved toolbar/search layouts are respected before a document is opened.
- Added persistent **View → Dark Editor**, enabled by default; unticking it switches the editor canvas, gutter, selections and HTML/CSS/XML/SVG syntax colours to the matching light palette independently of AppImage chrome.
- Renamed **View → Behaviour** to **File Drag and Drop** with **Opens on Active Window** / **Opens on New Window**.
- Application version remains `0.1.1-exp1`; this is an experimental source revision only.

## 0.1.1-exp1-r1 — UI/assets correction

- Restored the exact official 0.1.0-r2 Timblee Pad icon family.
- Refined Edit: separator after Toggle Comment, **Duplicate Line / Selection**, and **Delete Line** (`Ctrl+Shift+K`).
- Shortened the toolbar action to **Preview**.
- Moved the document-type selector from the status bar to the toolbar after Help and before Preview.

## 0.1.1-exp1 — XML-first experimental branch

- Added explicit HTML/CSS/XML/SVG document profiles.
- Added `.xml`, `.xsd`, `.xsl`, `.xslt` and `.svg` routing/metadata.
- Added XML/SVG syntax highlighting, case-sensitive matching/indentation/autoclose and well-formedness checking.
- Added no-splash **Start a Document** state for file-less launch when New defaults are set to Always Ask.
- Added configurable New document type+template defaults, New Type, and quick Document Type switching.
- Added clear document-type/check state to the status bar and guarded filename/type mismatch handling.
- Renamed user-facing Tags menu to Library and made its catalogue language-aware.
- Added CSS/XML/SVG Library entries while preserving the existing HTML catalogue, custom tags and collection import/export.
- Added built-in HTML/CSS/XML/SVG templates plus bounded editable custom templates with `[[cursor]]` placement.
- Reworked Preview to use a loopback-only HTTP server so `.html/.htm` editor associations cannot route Preview back into Timblee/Suite.
- Kept CSS non-previewable and added no JavaScript runtime/IDE stack.

## 0.1.0-r2

- Asset-only reissue of 0.1.0-r1 with the approved Timblee Pad notebook identity; application code unchanged.

## 0.1.0-r1

- Packaging hotfix: control incidental Qt PDF/PrintSupport collection through PyInstaller exclusions rather than fatal post-freeze probes.

## 0.1.0

- Promoted the hardened 0.0.1 line and added full AppImage default/dark/light/system GUI smoke-test coverage.
