# Updating

Open **Updates**, choose **Check for updates**, then pause monitoring before **Download and validate update**. After validation choose **Update and restart**. Monitoring and Telegram remain paused so the acquisition gap is visible and the user can review the result.

Normal launch never fetches Git or solves dependencies. An unavailable server, rate limit, or expired manifest blocks only the update check. It is not reported as “up to date.” A release without authenticated source metadata cannot be applied.

Equivalent maintenance commands (use `.cmd` on Windows):

```sh
./RunLiKeWatch.command status --json
./RunLiKeWatch.command check
./RunLiKeWatch.command prepare
./RunLiKeWatch.command validate TRANSACTION_ID
# Close the current app before external CLI activation:
./RunLiKeWatch.command apply TRANSACTION_ID
```

Preparation never modifies the active worktree. Validation uses a synthetic demo and does not access production credentials or hardware. The GUI requires monitoring to be paused before validation. CLI users must similarly pause resource-intensive work before validation.

A source-only release reuses the environment identity; dependency or native-helper changes create a separate environment. Public downloads require no GitHub token. Source releases are selected by signed published metadata, never arbitrary commits on main.

## Publishing

For the first release, run **Managed native qualification**, then **Publish managed release** in `full` mode with the successful run ID for the exact commit. Signing requires the pinned production public key and repository secret `LIKEWATCH_RELEASE_KEY`. Both final offline installers must pass before publication.

For subsequent application-only changes, run **Source-only native qualification** with a published full installer's tag. This downloads and verifies the existing installer, installs it offline, and validates the exact candidate through its unchanged installed manager. No constructor build, dependency resolution, or native compilation is required. Manager, bootstrap, pinned keys, dependency declarations, native helper, or lock changes require `full` mode. Once qualification passes, publish in `source` mode with that exact run ID. Signed metadata references the existing environment payload; release notes link new users to the seed installer.

Release signing checks consistent version declarations, clean tracked source, manifest validity, and increasing version/sequence relative to the latest signed release. Workflow actions are pinned to commit hashes. Protocol record schemas are in `deployment/schemas`; regenerate them with `python scripts/export_schemas.py` after intentional protocol changes.
