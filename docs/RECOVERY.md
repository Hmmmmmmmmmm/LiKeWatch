# Recovery

The repair script uses private maintenance Python even if Qt or OCR cannot import.

```sh
./RepairLiKeWatch.command doctor
./RunLiKeWatch.command rollback
./RepairLiKeWatch.command repair
./RunLiKeWatch.command cleanup
```

Use `.cmd` on Windows. Close the managed application before rollback or repair. Another managed process holds the run lock. A legacy application's existing data lock also prevents candidate startup; never delete that lock to force an update.

Rollback switches to the previous verified source/environment only if it can read the current data schemas. History, acknowledgements, delivery outcomes, and polling offsets are never rewound. A failed trial leaves the previous active record in place. Session logs are under `state/sessions/`; transaction records are under `state/transactions/`.

Explicit repair preserves a changed worktree under `preserved/` and recreates source from the trusted local Git cache. It does not reset or clean a developer checkout. Environment repair preserves the damaged prefix for diagnosis and rebuilds at its original final path from authenticated seed/cache packages, or a hash-verified release payload when available. Real OCR/GUI qualification must pass before completion. If trusted metadata, source objects, payloads, or maintenance Python are unavailable, install the full package at a new local prefix. Do not move a conda installation or copy a development virtual environment as a repair.

Cleanup previews eligible source and environment removal. Run `cleanup --apply` to remove clean, authenticated, unreferenced artifacts. Active and previous deployments, current-generation plans, dirty or unknown source, and modified or unsealed environments are preserved. Cleanup takes the run and update locks; close the app first. No automatic deletion of old portable EXEs/apps, credentials, profiles, or unrelated environments occurs.
