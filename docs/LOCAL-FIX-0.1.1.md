# Local update 0.1.1

The Desktop command continues to open `dist/LiKeWatch.app`.

- Snapshot captures and freezes an image. It no longer implicitly runs OCR.
- Trigger OCR on still image analyzes that exact frame, without reacquiring it
  or advancing live alert confirmation. Start monitoring remains the live path.
- Add, edit and remove region controls are enabled only on a still frame.
  Pause / freeze converts the last analyzed live frame to a still frame.
- Point selection and dragging display a 5x source-pixel loupe beside the cursor.
- Settings, rule editors, confirmations and file selection use embedded pages,
  without nested QDialog.exec() event loops or native secondary dialogs.
- Table cells retain their identity across updates. Graphics item changes are
  deferred until mouse dispatch has returned; row removal suppresses reentrant
  selection callbacks.
- macOS screen capture checks OS permission and uses the native screencapture
  utility instead of the deprecated MSS pixel capture path. Black frames are
  rejected with a visible error; an earlier usable still frame is retained.
  Monitor zero still combines all displays. Camera acquisition includes warmup.
- Rotating application/error logs and per-process native fault traces are saved
  under ~/Library/Logs/LiKeWatch on macOS (temporary-directory fallback if the
  normal log location is unavailable). Use Open error logs in the bottom band.

The supplied report identified SIGSEGV in Qt's Cocoa accessibility handling during
QDialog.exec on macOS 27. The update removes the implicated nested-dialog flow
and unsafe item replacement. Python exceptions are recorded and pause monitoring;
fatal native faults can be recorded but cannot safely be caught and continued.

Validation: 47 automated tests; real Tesseract OCR; native Cocoa and packaged GUI
stress checks with 30 settings cycles, region removal and actual mouse dragging.
A live screen image could not be verified from the test process because macOS
screen-recording permission was denied. Grant LiKeWatch Screen & System Audio
Recording access when requested and restart the application before capture.

This is a local repair build. The published v0.1 release remains unchanged.
