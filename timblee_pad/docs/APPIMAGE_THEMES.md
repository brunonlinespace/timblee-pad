# Timblee Pad AppImage themes

Timblee Pad keeps the lightweight bundled QSS theme approach and does not use Qt WebEngine.

One-launch overrides:

```bash
./Timblee-Pad-0.2.3-x86_64.AppImage --appimage-theme=dark
./Timblee-Pad-0.2.3-x86_64.AppImage --appimage-theme=light
./Timblee-Pad-0.2.3-x86_64.AppImage --appimage-theme=system
```

`TIMBLEEPAD_APPIMAGE_THEME=dark|light|system` is the corresponding environment override.

The Fedora builder retains the default/dark/light/system GUI + exact-version smoke matrix against both AppDir and final AppImage. XML support adds no theme/runtime dependency.
