# Third-party notices

LiKeWatch adapts ScoreSight's persistent Tesseract API adapter and retains its
source snapshot in `vendor/scoresight`. Upstream: https://github.com/royshil/scoresight
at commit `b6da66e514f52ca0cc7cf49eda8ed3d5f45c69fe`.
Copyright (c) 2024 OCC AI: Open tools for Content Creators and Streamers.
MIT license: `vendor/scoresight/LICENSE`.

The English OCR model is Tesseract `tessdata_fast/eng.traineddata` (Apache-2.0).
Its license is included in `assets/tessdata/LICENSE`.

Native distributions include Python (PSF), PySide6/Qt (LGPL-3.0 and component
licenses), OpenCV (Apache-2.0), NumPy (BSD-3-Clause), Pillow (HPND), Tesseract
and tesserocr (Apache-2.0/MIT), Leptonica (BSD-style), MSS (MIT), HTTPX (BSD-3-Clause),
keyring (MIT), platformdirs (MIT), and their dependencies. The distribution
includes package metadata and licenses retained by PyInstaller. Qt is dynamically
linked. Source and installation metadata identify the exact component versions;
users may rebuild with compatible replacement libraries. No restriction on
reverse engineering for debugging modifications to LGPL libraries is imposed.

See `docs/UPSTREAM.md` for scope and provenance. No GPL NormCap code is included.
