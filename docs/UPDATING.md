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
