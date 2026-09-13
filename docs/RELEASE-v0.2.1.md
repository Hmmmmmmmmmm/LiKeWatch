# LiKeWatch v0.2.1

- Fix Windows zoom being reset to fit-to-frame when scrollbars resize the viewport. Manual zoom now survives window and panel resizing.
- Add a Zoom percentage control beside Reset zoom (1–2000%; 100% is actual image size). Mouse-wheel zoom and the percentage display stay synchronized.
- Enable Edit corners on frozen frame by default. Preserve the selection through snapshots and OCR while disabling corner interaction during active processing and monitoring.
- Start fresh profiles with no regions or rules. Existing saved profiles are preserved.

## Download

Windows 10/11 x64: download `LiKeWatch-0.2.1-Windows-x64-portable.exe` and double-click it. No Python, Tesseract, model download, administrator install, or PATH setup is required. The EXE is unsigned, so Windows may show a publisher prompt.

macOS 15+ Apple Silicon: open `LiKeWatch-0.2.1-macOS-arm64.dmg` and drag the app into Applications. This build is ad-hoc signed, not notarized.

Native CI checks include wheel zoom beyond fit, zoom persistence, startup defaults, real OCR, packaged GUI stress checks, and a separate Windows portability run without external runtime configuration. Telegram remains optional and requires your bot credentials.
