# Install the source-managed LiKeWatch

## Windows x64

Run the constructor installer and choose a per-user local folder. It includes private Python, Git, Qt, and OCR dependencies. Start the installed `RunLiKeWatch.cmd`. Do not move the installation after setup; reinstall at a new prefix if needed. The old v0.2 portable EXE remains a separate legacy distribution.

## macOS 15+ Apple Silicon

Run the downloaded shell installer from Terminal:

```sh
bash LiKeWatch-0.3.0-MacOSX-arm64.sh -b -p "$HOME/LiKeWatch"
"$HOME/LiKeWatch/RunLiKeWatch.command"
```

Use the actual downloaded filename. The setup prepares its private environments, installs bundled wheels offline, verifies source, and runs isolated real-OCR tests before marking installation complete. It does not initialize the user's shell, change system PATH, register a default Python, or activate an unrelated environment.

A script launch does not bypass macOS camera/screen/keychain authorization. Permissions may be attributed differently from the old frozen application. Native hardware and permission qualification is separate from offscreen CI. The authentication helper is precompiled; no Swift compiler is needed by the installed app.

## Upgrade from v0.2.x

Close the old application. Install v0.3 in its own local folder, then use the new stable launcher. Existing application-data paths, profile IDs, QSettings identity (`LiKeWatch` / `LiKeWatch`), keyring service/account names, SQLite history, and Telegram state remain unchanged. Nothing automatically removes the old app or your old launcher. Retire old shortcuts manually to avoid opening the wrong version.

Fresh profiles start empty with corner editing enabled. Choose a source, take a Snapshot, add regions, and trigger OCR. Zoom controls remain beside Reset zoom. Telegram delivery is optional and starts disabled. Existing profiles are restored instead of being replaced by new defaults.

See [Updating](UPDATING.md), [Recovery](RECOVERY.md), and [Deployment architecture](DEPLOYMENT-ARCHITECTURE.md). Qualification results and installer sizes are recorded separately; do not infer Windows or hardware support from a local offscreen Mac test alone.
