# Timblee Pad 0.2.3 — root README filename correction audit

## Scope

0.2.3 is based only on Timblee Pad 0.2.2. It corrects the public source-root README filename from `README` to `README.md` and updates only the release/package contracts that reference that root file.

## Locked root README

The approved public-facing document now lives at source root as exactly `README.md`. Its content is unchanged from the approved 0.2.2 README except for current-release version references advancing from 0.2.2 to 0.2.3. Future releases must not alter its content other than version-number updates unless an explicit README content change is requested.

## Preserved 0.2.2 corrective

The Sheepy Pad editor-scrolling convergence remains unchanged: global center-on-scroll stays disabled, Go To Line retains explicit centering, and the line-number gutter remains constrained above a visible horizontal scrollbar.

## QA

The release gate requires the exact root set `README.md`, `main.py`, `suite-pythoine-component.json`, and `timblee_pad/`; requires the Fedora builder to consume and provenance-hash `${PROJECT_ROOT}/README.md`; rejects the stale extensionless root `README`; and retains all existing editor-scrolling regressions.
