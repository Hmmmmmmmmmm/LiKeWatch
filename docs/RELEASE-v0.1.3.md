# LiKeWatch 0.1.3

- Add **Text contains**, a case-sensitive literal substring comparison for text
  variables. For example, `Step 14 ready` contains `14`. Empty search strings are
  rejected. Missing, stale, or invalid OCR remains UNKNOWN and cannot trigger an
  alert through this operator.
- Restrict comparison operators to the selected variable type. Text supports
  equality, inequality, and contains; numbers retain numeric comparisons.
- Validate thresholds inside the comparison editor and show inline errors before
  adding a condition. Numeric-looking text is a literal string for text variables.
- Extend the macOS 27 accessibility workaround to all Qt item views, including
  condition trees and dropdown lists. The previous table-only workaround missed
  those widgets. The native bridge receives bounded text summaries instead of
  synthesized rows/cells; visual controls and keyboard interaction are unchanged.

Validation includes native Cocoa tests for nested comparison editing, type changes,
invalid thresholds, literal text matching, stale/missing observations, and repeated
condition-tree mutation with accessibility queries. Native fault logging remains
active; bypassing this path is a mitigation, not a general SIGSEGV recovery mechanism.
