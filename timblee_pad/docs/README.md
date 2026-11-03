# Timblee Pad 0.2.3

**A lightweight source editor for HTML, CSS and XML.**

Timblee Pad keeps one plain-text editor and one file-safety layer. Document profiles select highlighting, indentation, Library content, templates and Preview behaviour. It deliberately does not add a browser engine, Node/npm, a language server, a linter, or a document validator.

Repository: https://github.com/brunonlinespace/timblee-pad

## Document types

- HTML: `.html`, `.htm`
- CSS: `.css`
- XML family: `.xml`, `.xsd`, `.xsl`, `.xslt`

SVG is no longer a Timblee Pad document type. A future dedicated graphics-oriented Pad can address SVG/ICO separately if desired.

Opening an existing file selects its document type from the extension. New unsaved documents carry an explicit type. **File → Document Type** can change Timblee's interpretation without rewriting the source.

## Starting Timblee Pad

There is no splash screen. With **Default New Document** set to **Always Ask**, a file-less launch displays **Start a Document** with Document type, Template, **Use this type and template as my default**, **Create Document**, and **Open Existing File…**.

`Ctrl+N` follows the configured default. **File → New Type…** always opens the chooser, and **File → Default New Document…** changes or resets the default.

The Start screen uses the same saved Inline/Split layout as an active document. The Find bar stays visible in its selected position but disabled until a document becomes active. The Edit menu likewise remains visible with all commands disabled.

## Layout

The four saved layouts remain:

- Inline — Top
- Inline — Bottom
- Split — Toolbar Up / Search Down
- Split — Toolbar Down / Search Top

For **Split** layouts, the Find bar belongs to the editor column only. When the Library is a left or right sidebar, the sidebar spans the full workspace height between the toolbar edge and the opposite window edge; the split Find bar does not run under or over the sidebar.

## Library

The Library follows the active document type:

- HTML: 114 built-ins covering the current non-obsolete HTML element set plus inline SVG/MathML roots, while preserving every previous built-in tag.
- CSS: 148 built-ins spanning selectors, layout, sizing, positioning, box model, typography, colour, media, motion, responsive rules, at-rules, variables, interaction, scrolling, tables and practical patterns.
- XML: 94 built-ins covering the original generic XML set plus document/DTD/entity helpers, XML Schema (XSD) and XSLT constructs.

**View → Library → Left Sidebar / Right Sidebar / Floating Only** controls placement. In sidebar mode the catalogue is selected from a compact drop-down instead of tabs. The sidebar keeps only Insert/Favourite controls; custom-tag and import/export buttons remain in the floating Library, while the Library menu provides Add/Remove/Import/Export commands. The small × button hides a configured sidebar without changing its saved left/right preference.

**Ctrl+L** follows that saved placement: for Left/Right Sidebar it shows or hides that sidebar; for Floating Only it opens/closes the floating Library. The floating Library keeps its tabbed catalogue. Favourites is shown in the sidebar selector, floating tabs and Library menu only when the active document type has favourites; otherwise the Library defaults to All.

## Templates

Built-in templates are immutable:

- HTML: Blank HTML, HTML5 Document
- CSS: Blank Stylesheet, Basic Stylesheet
- XML: Blank XML, Basic XML Document

**Library → Templates → Manage Templates…** manages bounded custom templates. One `[[cursor]]` marker may select the initial caret location.

## Editing behaviour

- HTML, CSS and XML syntax highlighting.
- HTML/XML tag matching and conservative closing-tag completion.
- XML matching is case-sensitive; HTML retains HTML-specific case/void-element rules.
- HTML/XML markup indentation and CSS brace indentation.
- CSS `/* … */` comments and markup `<!-- … -->` comments.
- Line numbers, Find/Replace, Go To Line, View Only, external-change protection and safe saves.
- **View → Dark Editor** is on by default and independently switches the editor canvas/syntax palette between dark and light.

Timblee does not claim validation or linting. The status bar reports ordinary editor/file state only; there is no `Type OK`, format-mismatch, XML-well-formedness, or other pseudo-validation surface. Users remain responsible for validation/linting with the tools appropriate to their work.

## Preview

**Preview in default browser** (`F5`) is available for saved HTML and XML documents. CSS remains intentionally non-previewable by itself.

Preview uses a small server bound only to `127.0.0.1` and opens an HTTP URL in the normal browser. Timblee does not embed Qt WebEngine and does not itself execute JavaScript.

## Portable source layout

```text
Timblee-Pad-0.2.3-source/
├── README.md
├── main.py
├── suite-pythoine-component.json
└── timblee_pad/
```

## Running from source

Requirements: Python 3.11+ and PyQt6.

```bash
python -m pip install -r timblee_pad/requirements.txt
python main.py
```

Examples:

```bash
python main.py index.html
python main.py data.xml
```

Release QA:

```bash
timblee_pad/qa/run-qa.sh
```

## AppImage

The Fedora builder remains non-privileged and retains the existing hardened packaging/theme-smoke flow. Expected development output:

```text
timblee_pad/dist/Timblee-Pad-0.2.3-${ARCH}.AppImage
```

## Preferences

Linux: `~/.config/brunonlinespace/timbleepad/timbleepad.json`

Windows: `%APPDATA%/brunonlinespace/TimbleePad/timbleepad.json`

## Licence

GNU General Public License v3 or later. See `timblee_pad/LICENSE`.
