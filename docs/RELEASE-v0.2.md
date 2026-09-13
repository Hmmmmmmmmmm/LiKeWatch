# LiKeWatch v0.2

## Download and run

- **Windows 10/11 x64:** download `LiKeWatch-0.2.0-Windows-x64-portable.exe` and double-click it. No installation, administrator access, Python, Tesseract, model download, or PATH configuration is required. The runtime extracts automatically into the user temporary directory; profiles and history use local application data.
- **macOS 15+ Apple Silicon:** open `LiKeWatch-0.2.0-macOS-arm64.dmg` and drag LiKeWatch into Applications.
- SHA-256 files accompany both downloads. Windows is unsigned; macOS is ad-hoc signed and not notarized. OS security prompts may appear.

## Changes

- Include the latest Telegram snapshot test, reply acknowledgement, and unambiguous standalone ACK fixes.
- Record test incidents and delivery changes in history and the activity log, including while Settings is open.
- Improve bot-token controls and stale-reading wording.
- Verify the packaged Windows EXE on a separate runner without development setup, with external Python and OCR configuration removed from its launch environment.

## First run

Choose Snapshot in Demo mode, then Trigger OCR on still image. Expected readings: 83.2 and 18.4. Camera/screen selection and monitoring regions are configured in the app. Telegram delivery is optional and requires your bot token and destination; delivery starts disabled.

Native builds run the test suite and embedded real-OCR/GUI smoke tests before publication. Camera hardware, mixed-DPI displays, and live Telegram delivery still require target-system qualification.
