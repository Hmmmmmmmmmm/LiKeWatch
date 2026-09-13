# Managed release procedure

1. Resolve dependency changes explicitly with `scripts/lock_environment.py --resolve`. The native qualification workflow resolves only at build time and emits fully hashed native locks and payloads. Source-only production builds restore an already qualified payload using `scripts/restore_payload.py`; they do not solve packages again.
2. Run Managed native qualification on the intended source branch. Download the two small `managed-report-*` artifacts and commit their `locks/*.json` to `deployment/locks/`. These locks include the exact Python, native helper, wheel, and maintenance dependencies. Rerun qualification at the final source commit.
3. The pinned public authority is `deployment/public-keys.json`. Configure `LIKEWATCH_RELEASE_KEY` with base64 of a raw 32-byte Ed25519 private key. Keep an independently protected local backup. Never commit private keys or use qualification fixture keys for production.
4. Dispatch Publish managed release from that exact source commit with the successful qualification run ID, stable tag, and strictly increasing sequence. Signing checks the run identity, result, and repository. Each native production installer restores the qualified payload, compares committed locks, and passes offline installed-launcher OCR tests before publication.
5. Verify the remote tag commit, signed manifest, checksums, and both downloadable installers. Keep v0.2.x available for recovery. Never replace a previously published tag or reuse a sequence.

The release metadata expires after 90 days for new update selection. Previously installed source remains launchable offline after metadata expiry. Renewed metadata must be signed by the trusted authority. Maintenance code and trusted key changes require a full installer; application-only updates cannot upgrade the maintenance layer.

The legacy PyInstaller workflow is manual and does not publish releases. Fixture installers are named LiKeWatchTest and are never production assets. CI artifacts expire after 14 days; publish or retain qualified payloads before then.
