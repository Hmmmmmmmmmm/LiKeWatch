# LiKeWatch

Local camera and screen OCR monitoring for Windows and macOS. Select independent
four-corner regions, turn readings into typed variables, and define nested
AND/OR alerts with confirmation and hysteresis. Telegram alerts and routine data
use the same durable queue. OCR runs locally; outbound delivery is opt-in.

## Download and run

Get the [**v0.2 release**](https://github.com/Hmmmmmmmmmm/LiKeWatch/releases/tag/v0.2): Windows x64 portable EXE or macOS
15+ Apple Silicon DMG. Both include Python, Qt, Tesseract and English model data.
See [installation and first run](docs/INSTALL.md). No signing credentials are
included; this release has unsigned Windows and ad-hoc-signed macOS binaries.

## Develop

Use Python 3.13 on the target OS:

```sh
python -m venv .venv
# Activate .venv using your shell's activation command.
python -m pip install -e ".[dev]"
python -m likewatch
python -m pytest -q
python -m likewatch --self-test
python scripts/build.py
```

For a checkout in OneDrive or another synced folder, keep the virtual environment
and installed app outside that folder. Set `PYINSTALLER_CONFIG_DIR`,
`LIKEWATCH_WORK_DIR`, and `LIKEWATCH_BUILD_DIR` to local, unsynced directories
when building so native frameworks and symbolic links remain intact.

`--self-test` uses real OCR against a generated demo, then runs the desktop
pipeline offscreen. It does not access cameras or send Telegram messages.

## Architecture

`domain` and `rules` contain typed observations and deterministic three-valued
logic without GUI/network dependencies. `capture`, `imaging` and `ocr` provide
source adapters, normalized geometry and a supervised persistent OCR subprocess.
`runtime` keeps acquisition/OCR and delivery off the GUI thread. One pending
request prevents backlog; revisions discard obsolete results. `storage` persists
incidents/events/outbox in SQLite. `messaging` handles Telegram without leaking
tokens into profiles or errors. `ui` owns Qt widgets and configuration dialogs.

ScoreSight's MIT sources are preserved under `vendor/scoresight`; its persistent
OCR adapter is extracted and adapted. See [reuse audit](docs/UPSTREAM.md) and
[third-party notices](THIRD_PARTY_NOTICES.md).

## Behavior and limits

Invalid or stale readings are unavailable, never zero or fresh last-good values.
Rules use a same-frame snapshot. Unknown data cannot recover an active incident.
Acknowledgement is independent of recovery and message delivery. Active incident
IDs survive restart; measurement freshness does not. Telegram acceptance is not a
read receipt, and uncertain sends may duplicate after an explicit retry.

The monitor starts in a labeled demo. Camera/screen access begins only after a
snapshot or Start. Imported profiles and restarts keep delivery disabled. Queue
entries capture their destination at creation; inspect pending events before
re-enabling a profile. Logs are bounded at 1,000 visible lines; event history shows
100 events and retains terminal events for 30 days. Active incidents and unresolved
outbox entries are preserved.

Target-hardware qualification remains necessary for camera availability, screen
permissions, mixed DPI, OCR accuracy and actual Telegram delivery. No measured
1 Hz performance guarantee is made. This release supports one source and optional incident image attachments.
Repeated reminders and Intel Mac artifacts are not included.

### Telegram test incidents and acknowledgement

Enable delivery, then use **Test send** in Settings. With **Attach snapshot** enabled,
this sends the current preview (or captures the configured source when no preview
exists) as a JPEG with a caption. Capture failure is reported instead of silently
sending a text-only test. Test incidents appear in event history and the activity
log, and exercise the local alarm when enabled without activating a monitoring rule.

Reply to the incident message with **ACK** to acknowledge it. The message opens a
reply prompt in supported Telegram clients. A standalone `ACK` or `/ack` also works
when exactly one unacknowledged incident exists in that chat/topic. With multiple
incidents, reply to the specific message. Group privacy mode may hide standalone
messages from bots; replying to the bot message avoids that limitation. Keep
LiKeWatch running with delivery enabled. ACK polling runs every 1–5 seconds;
an active webhook or another consumer of this bot's updates can prevent polling.

Implementation references: Telegram's [sendPhoto](https://core.telegram.org/bots/api#sendphoto)
uses multipart upload and a caption of at most 1024 characters after entity parsing;
[getUpdates](https://core.telegram.org/bots/api#getupdates) supplies incoming replies;
[ForceReply](https://core.telegram.org/bots/api#forcereply) provides the reply prompt.
