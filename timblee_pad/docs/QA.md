# Timblee Pad 0.2.3 QA

Run automated QA first:

```bash
timblee_pad/qa/run-qa.sh
```

## Fedora GUI smoke tests

1. File-less Always Ask launch: confirm **Start a Document** appears in the normal workspace. In all four saved layouts, Find remains visible in the configured location but disabled; Edit commands remain visible but disabled.
2. Create/open a document and confirm Find/Edit enable without moving. Verify View Only still leaves Copy, Select All and Go To Line available while mutating commands are disabled.
3. Create/open HTML, CSS and XML-family files and confirm extension-driven type, highlighting, templates and Library content. `.svg` must be rejected as unsupported.
4. Confirm the toolbar contains File/Edit/View/Library/Help and Preview but no permanent document-type shortcut. **File → Document Type** remains available for active documents.
5. Confirm the status bar has no Type OK, Looks like…, XML check, or other document-validation indicator.
6. Open **View → Library → Left Sidebar** and **Right Sidebar**. Confirm the sidebar uses a catalogue drop-down plus × and does **not** show Add Custom/Remove Custom/Import/Export button rows. The floating Library remains tabbed and retains those controls.
7. With no favourites for the active document type, confirm **Favourites** is absent from the sidebar selector, floating Library tabs and Library menu and that **All** is selected. Add one favourite and confirm Favourites appears; remove the last favourite while Favourites is selected and confirm the Library falls back to All.
8. With Left/Right Sidebar selected, press **Ctrl+L** and the × button: each must hide/show the sidebar without changing the checked View preference. With **Floating Only** selected, Ctrl+L must open/close the floating Library.
9. Confirm Library insertion shortcuts are **Ctrl+1 … Ctrl+0**, no active Ctrl+Alt shortcut remains, and the Keyboard Shortcuts dialog displays literal `<html>`, `<head>`, `<img>` labels instead of blank rows/images.
10. Confirm file mappings: External Editor Ctrl+Shift+E, Rename F2, Duplicate File Ctrl+Shift+D, Open Containing Folder Ctrl+Shift+O, and Delete File has no shortcut.
11. Verify Library breadth and insertion for HTML/CSS/XML, including representative new HTML elements, CSS patterns/at-rules and XML/XSD/XSLT entries.
12. For **Split — Toolbar Up / Search Down**, verify a left/right Library sidebar spans the workspace height and the Find bar sits only under the editor column.
13. For **Split — Toolbar Down / Search Top**, verify the Find bar sits only above the editor column and the sidebar spans down to the bottom toolbar.
14. Re-test Inline Top/Bottom: Find stays inline in the toolbar and sidebar placement remains unchanged.
15. Toggle **Dark Editor** off/on and verify matching light/dark syntax palettes.
16. Preview saved HTML and XML through localhost; CSS Preview remains disabled.
17. Re-test templates, favourites, HTML custom tags/import/export, drag/drop modes, safe save/external-change prompts and AppImage dark/light/system theme smoke matrix.

## Packaging

- `python main.py --version` → `Timblee Pad 0.2.3`.
- Portable source root contains `README.md`, `main.py`, `suite-pythoine-component.json` and `timblee_pad/`.
- Desktop/AppStream MIME scope is HTML, CSS and XML only; no SVG document MIME.
- AppImage builder remains non-privileged and WebEngine-free.
- Final AppImage runs default/dark/light/system GUI + version smoke matrix on Fedora.
