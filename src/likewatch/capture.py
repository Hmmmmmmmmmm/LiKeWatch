"""Source adapters. No acquisition occurs until explicitly requested."""

import cv2
import numpy as np


def demo_frame():
    frame = np.full((650, 1000, 3), 244, np.uint8)
    cv2.putText(
        frame,
        "LiKeWatch / demonstration",
        (45, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (65, 65, 65),
        2,
    )
    cv2.putText(
        frame, "TEMPERATURE", (70, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (90, 90, 90), 2
    )
    cv2.putText(
        frame, "83.2", (70, 270), cv2.FONT_HERSHEY_SIMPLEX, 2.7, (10, 10, 10), 5
    )
    cv2.putText(
        frame, "PRESSURE", (570, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (90, 90, 90), 2
    )
    cv2.putText(
        frame, "18.4", (570, 270), cv2.FONT_HERSHEY_SIMPLEX, 2.7, (10, 10, 10), 5
    )
    cv2.putText(
        frame, "STATUS", (70, 410), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (90, 90, 90), 2
    )
    cv2.putText(frame, "READY", (70, 490), cv2.FONT_HERSHEY_SIMPLEX, 2, (10, 10, 10), 4)
    cv2.putText(
        frame,
        "Local OCR. No outbound messages until enabled.",
        (45, 605),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (90, 90, 90),
        1,
    )
    return frame


class Capture:
    def __init__(self):
        self.camera = None
        self.device = None

    def read(self, profile):
        if profile.source != "camera":
            self.close()
        if profile.source == "demo":
            return demo_frame()
        if profile.source == "image":
            frame = cv2.imread(profile.image_path)
            if frame is None:
                raise RuntimeError("Cannot read the selected image")
            return frame
        if profile.source == "screen":
            import mss

            with mss.mss() as screen:
                if not 0 <= profile.device < len(screen.monitors):
                    raise RuntimeError(
                        "Monitor unavailable; select another monitor index"
                    )
                return np.asarray(screen.grab(screen.monitors[profile.device]))[
                    :, :, :3
                ].copy()
        if self.camera is None or self.device != profile.device:
            self.close()
            self.camera = cv2.VideoCapture(profile.device)
            self.device = profile.device
        if not self.camera.isOpened():
            self.close()
            raise RuntimeError(
                "Camera unavailable. Check device index and camera permission"
            )
        ok, frame = self.camera.read()
        if not ok:
            self.close()
            raise RuntimeError("Camera frame unavailable")
        return frame

    def close(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None
