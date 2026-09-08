LiKeWatch 0.1 provides local camera, desktop screenshot and image OCR monitoring.

- Three-panel Qt desktop UI with multiple independently rectified four-corner regions.
- English/numeric OCR, raw text/confidence, strict Decimal parsing and explicit invalid/stale states.
- Nested AND/OR comparisons, consecutive confirmation, hysteresis recovery and durable incident history.
- Telegram alerts and routine data via a persistent outbox; credentials in the OS credential store.
- Windows x64 portable executable and macOS 15+ Apple Silicon application installer (DMG).
- Python, Qt, native OCR libraries and the English OCR model are bundled.

Both native builds run the unit/integration suite and a packaged real-OCR plus Qt
smoke test. Camera permissions, physical cameras, mixed-DPI desktops and a real
Telegram destination still require testing on the target user's setup.

The Windows executable is unsigned. The Mac app is ad-hoc signed, not Developer ID
signed/notarized. See INSTALL.md in the repository/DMG for platform launch steps.

Known v0.1 boundaries: one active source; 32 regions; 64 rules; reminders and image
attachments are not implemented. The UI displays the last 100 events; terminal
history is pruned after 30 days. Uncertain sends require manual review/retry.
