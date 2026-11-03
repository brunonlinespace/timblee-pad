# Timblee Pad 0.1.1-exp1-r4 — security and resilience notes

## Source boundary

Normal file workflows accept `.html`, `.htm`, `.css`, `.xml`, `.xsd`, `.xsl` and `.xslt`. `.svg` is no longer routed as a Timblee document. Existing regular-file checks, 25 MiB synchronous-open cap, bounded editor content, external-change snapshots, symlink-aware guarded saves and atomic/no-clobber behaviour remain shared across supported types.

## Validation boundary

Timblee performs no automatic document validation or linting. The prior content-hint/XML-well-formedness status machinery has been removed rather than expanded. No parser, schema engine or external validation dependency is introduced.

## Preview boundary

Preview uses `http.server.ThreadingHTTPServer` bound explicitly to `127.0.0.1` and serves the active document's containing directory. The generated URL is passed to the existing HTTP/HTTPS-only URL opener. No Qt WebEngine/embedded browser is used.

## Templates and Library

Custom templates remain bounded preference data. Existing HTML custom-tag validation and bounded `.timbleetags` import/export remain intact. CSS/XML catalogues are fixed application data.

## Removed/absent attack surface

No script runner, terminal/admin launch, Node/npm, JavaScript runtime, language server, debugger, project package manager, validator/linter engine, Qt WebEngine, Qt PDF or printing subsystem is added.

## Packaging

The existing hardened native Fedora AppImage builder remains non-privileged, runs canonical QA, uses isolated Python build dependencies and smoke tests, and retains appimagetool transport/hash/provenance protections.
