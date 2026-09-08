# LiKeWatch 0.1.2

- Keep image zoom after editing region control points.
- Always show the corrected region and final OCR input in the middle panel.
- Move session delivery enablement to the main panel.
- Display Telegram event types in one settings row with explanation tooltips.
- On macOS 27, expose application tables as accessible text summaries, avoiding
  Qt Cocoa's synthesized table-cell objects implicated in native accessibility
  crashes. Visual table operation and keyboard selection remain available;
  screen-reader navigation no longer exposes individual table cells on macOS 27.
  Other platforms retain normal table accessibility.

Native segmentation faults cannot safely be caught and resumed in Python. This
release bypasses the suspected native table path rather than attempting recovery
inside corrupted process state. Native fault logs remain enabled.

Validation: 52 regression tests, including zoom retention, preview selection,
delivery state, and accessibility-summary row changes; packaged native UI/OCR
smoke checks cover settings cycles, region deletion, and control-point dragging.
