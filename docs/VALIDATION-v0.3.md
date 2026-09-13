# v0.3 qualification record

Local platform: Apple Silicon, macOS; tested 2026-09-14. Production publication remains gated by the release workflow and signing setup.

## Passed locally

- 135 unit/integration tests, including signatures, expiry, URL restrictions, bounded/streamed payloads, archive containment, OS-held operation locks, detached Git worktrees, tag retargeting, dirty source, schema protection, credential isolation, launcher arguments, and mismatched trial identity.
- Actual constructor installer: offline install with proxy destinations deliberately unreachable and system-only PATH, at a Unicode path without spaces.
- Generated installed launcher: real spawned OCR reads 83.2 and 18.4; reports parent/child source commit, module origin, private interpreter, and environment identity. Native Qt stress test checks zoom at 250%, resize preservation, empty defaults, corner editing, settings pages, and region editing. The rendered application was visually inspected.
- Supervisor termination closes an intentionally held-open GUI through its lifetime pipe; no PID-reuse assumption is used.
- Signed source-only update reuses the application environment and leaves the old detached source unchanged.
- GUI adapter prepares and validates a signed dependency update through a separate maintenance process, requests cooperative shutdown, restarts, and activates another immutable environment.
- Actual rollback returns to the previous source/environment. Ordinary close exits without a restart loop. Stale plans and a deliberately failing candidate are rejected without switching the active deployment.
- Two additional rollback launches preserve fixture profiles, event history, acknowledged incidents, pending outbox records and attempt counts, and Telegram polling offsets. Production data and credentials were not used.

Native Windows and Mac baseline qualification passed at commit `a6d80be` in [run 34763927994](https://github.com/Hmmmmmmmmmm/LiKeWatch/actions/runs/34763927994), including offline installation, generated launchers, real OCR, GUI updates, environment rollback, and operational-record preservation. Native recovery qualification also passed on both platforms at commit `3415a66` in [run 34764971789](https://github.com/Hmmmmmmmmmm/LiKeWatch/actions/runs/34764971789). Supervisor-interruption handling and the strict-schema/retention integration passed locally using the installed fixture with updated maintenance code. The latest local fixture candidates derive from `177909c`; its data path contains spaces and Unicode. The release workflow still requires a successful native run for its exact final commit; hardware/account scenarios remain separate.

## Explicit limits and release gates

- Windows constructor rejects installation paths containing characters outside the system code page. Qualification uses ASCII paths; documentation recommends ASCII without spaces. Mac Unicode paths passed, but spaces are unsupported by the conda maintenance base.
- Camera/screen permission attribution, native OS authentication, and real Telegram delivery are not part of this isolated run. They remain manual hardware/account checks.
- Environment repair preserves the damaged copy, rebuilds from authenticated offline packages, and passes real OCR validation; local testing left the operational database unchanged. Missing maintenance Python or recovery inputs require a new installer at another prefix. Explicit retention cleanup removed failed-candidate source while preserving active and previous deployments; unit tests also cover protected and modified artifacts. The maintenance runtime and trusted signing keys require full-installer updates.
- Production release signing requires an explicitly approved private-key setup. Fixture keys and LiKeWatchTest installers must never be published as production assets.
- The production workflow requires successful qualification reports for its exact source commit and both final offline installer tests before publishing a tag or assets.

Source-only publication preflight has local tests for application-only changes and rejection of manager, native-helper, and dependency changes. Its native workflow needs a previously signed full release and has not yet run against production. Workflow YAML, Bash, and embedded Python parse successfully.
