# LiKeWatch v0.3

LiKeWatch now runs ordinary Git-managed application source using its own private Python runtime. Windows setup includes Python, Git, Qt, OCR, and English model data; no separate runtime installation or environment configuration is required. The macOS installer provides the same separation through a Terminal installer and a double-clickable `.command` launcher.

Updates verify Ed25519-signed release metadata, download a detached source candidate, and test actual OCR and GUI startup before activation. Dependency changes install another private environment beside the current one. The app shuts down cooperatively and restarts paused. Rollback selects the previous source and environment without restoring old history or Telegram state.

The v0.2.1 image zoom controls, enabled corner editing, empty fresh profiles, and Telegram fixes are retained. Existing profiles, OS credential identities, history, outbox, and acknowledgement offsets remain in their existing data location.

## Installation

Windows x64: download and run the `.exe` installer, then start `RunLiKeWatch.cmd` in the chosen installation folder.

macOS 15+ Apple Silicon: run the downloaded `.sh` installer with `bash`, then start `RunLiKeWatch.command`. See [installation instructions](https://github.com/Hmmmmmmmmmm/LiKeWatch/blob/main/docs/INSTALL.md).

Use a local path without spaces; use ASCII characters on Windows. Installed environments cannot be moved; reinstall at a new prefix instead. This replaces the single portable executable distribution. Metadata signing is separate from Windows Authenticode and Apple notarization; the installer may still prompt under OS download policies.

## Validation and limits

Publication is gated on native Windows and macOS tests, offline installation, generated-launcher OCR tests, and signed update/rollback qualification. Local Apple Silicon testing also exercises real OCR, source updates, failed-candidate preservation, and database preservation.

Camera/screen permission attribution and actual Telegram delivery require hardware/account testing. Cleanup currently previews retained versions. A damaged environment or maintenance-runtime upgrade requires a new installer. Intel Mac builds are not included.
