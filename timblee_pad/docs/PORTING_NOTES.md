# Timblee Pad architecture / porting notes

## Baseline

Timblee Pad remains a single lightweight source editor with small document-language profiles.

## Deliberate choices

1. **Source text is canonical.** HTML/XML are never converted into a rich document model.
2. **Document type is explicit.** Existing files use extension routing; unsaved files have a selected type. File → Document Type changes interpretation only.
3. **No pseudo-validation.** Timblee does not claim Type OK, auto-lint HTML/CSS, or well-form XML. Validation/linting remains the user's responsibility.
4. **Scope is HTML/CSS/XML.** SVG document support was removed; icon files named `.svg` are packaging artwork only, not an editable document type.
5. **External browser Preview stays lightweight.** `F5` uses loopback HTTP and the host browser; Qt WebEngine remains absent.
6. **Library is shared.** The active document profile selects the catalogue. Sidebar presentation is compact drop-down + close control; floating presentation remains tabbed.
7. **Split Find belongs to the editor column.** A side Library spans the full workspace height instead of sharing the Find row.
8. **Templates are bounded data.** Built-ins are immutable and custom templates support only a literal `[[cursor]]` placement marker.
9. **No JavaScript runtime/IDE stack.** Highlighting does not imply execution, Node/npm, LSP or debugger integration.
