LiKeWatch 0.1.1 fixes the macOS dialog-crash path and frozen-image workflow.

- Five-times magnified source-pixel view follows the cursor while selecting or dragging corners.
- Snapshot captures a still image; Trigger OCR analyzes that exact image without advancing live alerts.
- Region editing is disabled during live monitoring and capture/OCR operations.
- Editors and confirmations are embedded in the main window without nested native dialog loops.
- Stable table items and deferred graphics changes avoid deleting objects during accessibility/mouse dispatch.
- macOS capture uses the native capture utility, checks screen permission and reports black frames explicitly.
- Persistent rotating error logs and native fault traces are accessible from Open error logs.

Validated with 47 automated tests, real OCR and native macOS GUI stress checks.
Live screen capture still requires OS permission. A segmentation fault cannot
safely be caught and continued; native faults are recorded for diagnosis.

Windows builds remain unsigned. Mac builds remain ad-hoc signed and unnotarized.
