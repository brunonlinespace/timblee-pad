# Building Timblee Pad 0.2.3

## Source run

```bash
python -m pip install -r timblee_pad/requirements.txt
python main.py --version
python main.py
```

Expected version output: `Timblee Pad 0.2.3`.

## Release checks

```bash
timblee_pad/qa/run-qa.sh
```

QA checks HTML/CSS/XML scope, absence of SVG document routing and automatic validation claims, Library sidebar drop-down/close behaviour, split editor-column Find placement, no-document Find/Edit state, Preview, portable-root and hardened AppImage contracts.

## Fedora AppImage

Canonical builder: `timblee_pad/packaging/fedora/build-appimage.sh`.

Run without sudo. Fedora 43/44 native x86_64/aarch64 policy, isolated venv, PyInstaller, metadata validation, GUI theme smoke matrix, appimagetool provenance and source-cleanliness checks are retained.

Expected output:

```text
timblee_pad/dist/Timblee-Pad-0.2.3-${ARCH}.AppImage
```

No validator/linter dependency, Qt WebEngine, Node or JavaScript runtime is added.
