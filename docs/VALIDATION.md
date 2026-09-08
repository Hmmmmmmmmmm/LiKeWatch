# v0.1 validation

Automated coverage includes 37 tests for strict Decimal parsing (including signs,
precision, scientific notation and invalid strings), confidence/range handling,
three-valued logic, stale observations, consecutive confirmation, sample gaps,
recovery hysteresis, frame consistency, quadrilateral rejection and normalized
coordinates, profile import, persistent incident restart, outbox deduplication,
ordering and coalescing, Telegram response classes and lost-response uncertainty.

Runtime integration tests use fake OCR explicitly to isolate lifecycle behavior:
source changes cannot recover active incidents, and obsolete configuration
results cannot produce alerts. A Qt editor test covers imported comparison roots.

Separately, `--self-test` runs real Tesseract against generated 83.2 / 18.4 demo
crops and exercises the complete GUI acquisition pipeline. The release workflow
runs this inside each frozen Windows/macOS binary after the test suite. It fails
the release if either native build or smoke test fails. Qt offscreen screenshots
were visually inspected locally for the three-panel layout and displayed values.

Target-hardware acceptance is still open: physical cameras, camera/screen OS
permissions, negative-origin and mixed-DPI desktops, device disconnect/reconnect,
long-running soak behavior, intended instrument fonts/lighting, and actual
Telegram destination delivery. HTTP transport tests use mocks and do not send
messages. Demo OCR accuracy is not an instrument-corpus benchmark.

No Apple Developer ID or Windows signing certificate was available. Mac builds
are ad-hoc signed and not notarized; Windows builds are unsigned.
