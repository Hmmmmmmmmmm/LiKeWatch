# LiKeWatch 0.1.4

- Keep the mid-panel age display tied to analyzed frames; remove independent age
  refreshes. Rename Fit image to Reset zoom.
- Automatically save valid settings to the local last-profile.json file. Delivery
  remains session-only and imported profiles cannot enable transmission. Bot
  tokens remain in the OS credential store, never in JSON.
- Place data-send interval beside capture interval. Rename Freshness to Maximum
  reading age: older OCR observations are excluded from rule evaluation.
- Move Test send into Settings and remove the TEST route toggle. Test sends still
  require the main-panel delivery switch. Event help supports both hover and click.
- Optional incident attachments combine the source image with numbered, corrected
  region enlargements in a separate grid. Insets cannot obscure other regions.
- Send compact HTML alerts with escaped user text, rule/condition, values, source,
  timestamp and event ID. Long text is shortened without breaking HTML entities.
- Optional local alarms beep repeatedly and flash the full-width Acknowledge
  button every 0.5 seconds until acknowledged. At monitor start, enabled alarms
  log the current output volume (WARNING below 10%, INFO otherwise). Unavailable
  volume information produces a warning. The application does not change volume.
- Poll Telegram replies at the capture interval, without overlapping requests,
  while sent incidents await acknowledgement and delivery is enabled. A human
  reply containing ACK (case-insensitive) must reference an accepted incident
  message in the same configured chat and topic. Message IDs and poll offsets are
  durable. ACK stops its local alarm and updates incident acknowledgement.
- Bot-token reveal/copy requires OS authentication: macOS device-owner
  authentication or verification of the current Windows account password. Revealed
  text and unchanged copied credentials expire after 30 seconds. Clipboard history
  managers may retain their own copies.
- On startup, remove LiKeWatch diagnostic log records/files older than seven days.
  Incident history and pending deliveries retain their separate existing policy.

Telegram getUpdates requires a bot without an active webhook or another competing
poller. LiKeWatch logs polling failures and does not remove webhooks automatically.
Anyone able to reply in the configured chat/topic can acknowledge that incident.

Validation uses synthetic images and mocked Telegram responses; no live bot
messages or stored-credential reveals are performed as part of automated tests.
