# Source-managed deployment (protocol 1)

The v0.3 feature branch changes distribution, not the PySide6 monitoring framework.
A constructor installation contains private maintenance Python/conda/Git, an independently locked application environment, signed seed metadata, and a bare Git repository. Detached release worktrees contain ordinary app source. A deployment record selects the source commit and environment together.

The maintenance package does not import LiKeWatch, Qt, NumPy, OpenCV, tesserocr, or keyring. Launch is offline. The runner uses isolated Python startup and binds a specific source root before importing the app; spawned OCR inherits that same context. Scripts find their own installation, not the current working directory. Environments are built at their final prefixes and are not relocatable.

`check` verifies published stable metadata with an installer-supplied Ed25519 public key. `prepare` fetches the signed tag into shared Git storage and creates a detached candidate. `validate` runs native OCR and UI tests using isolated settings, data, logs, and disabled hardware/messaging/authentication. A changed environment is installed side by side from verified conda packages and hashed wheels, with no user-side online solve.

Activation requires the managed app to stop cooperatively and return a nonce-bound restart request. The supervisor starts a paused trial and checks its PID, session, nonce, source, environment, and transaction before atomically replacing the active record. The previous tuple remains available. Ordinary app exit does not restart or roll back. Interrupted pre-commit transactions leave the previous deployment selected; an atomic committed record always contains a complete source/environment pair.

Profiles, SQLite history, outbox state, Telegram offsets, and the production QSettings/keyring identities are separate from source/environment selection. SQLite backup uses its backup API. Rollback changes code and environment only and refuses incompatible current schemas. It never restores an older operational database automatically.

The initial release does not self-update its maintenance interpreter or trusted keys. Those require a complete verified installer. Cleanup is a retention preview; it does not automatically delete user-modified worktrees or retained environments. Modified active source can be preserved under `preserved/` by explicit repair before recreating the signed worktree. Missing/broken environments currently require a replacement installer at a new prefix.

Production and test installers are distinct. Fixture builds are named LiKeWatchTest and accept only their temporary fixture authority. Production publication requires separately configured signing infrastructure. Installer signing/notarization and update metadata signing are separate qualifications.
