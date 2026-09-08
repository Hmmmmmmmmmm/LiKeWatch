# ScoreSight reuse audit

Reviewed 2026-09-08: `royshil/scoresight`, commit
`b6da66e514f52ca0cc7cf49eda8ed3d5f45c69fe`, MIT.

The upstream Python sources, README, license and requirements are preserved
unchanged in `vendor/scoresight`. Upstream remains separately available through
the `upstream` Git remote. The preserved snapshot is reference source, not a
second bundled application; broadcast/OBS/NDI dependencies are not installed.

`src/likewatch/ocr.py:TextDetector` extracts the persistent PyTessBaseAPI,
PIL image input and recognition sequence from upstream `src/tesseract.py`.
The new adapter defaults to English, returns raw text and confidence, and runs
in a supervised process. It omits scoreboard substitution and change skipping.

The capture adapter follows the read/release interface in upstream
`base_video_capture.py`; camera acquisition uses OpenCV directly. Independent
normalized quadrilaterals replace upstream's source-wide homography. Monitoring
rules, durable outbox and application UI are new modules because the upstream
Qt/storage/broadcast coupling does not provide those contracts.

Deviation from the planning recommendation: the legacy ScoreSight application
was not reproduced with all its obsolete native broadcast dependencies. Its
source is preserved and the useful OCR path was extracted into a separately
runnable monitor. Native feasibility is verified against LiKeWatch's actual
packaged OCR path, not asserted for legacy ScoreSight.
