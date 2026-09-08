"""Source adapters. No acquisition occurs until explicitly requested."""

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
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
            if sys.platform == "darwin":
                return mac_screen(profile.device)
            import mss

            with mss.mss() as screen:
                if not 0 <= profile.device < len(screen.monitors):
                    raise RuntimeError(
                        "Monitor unavailable; select another monitor index"
                    )
                return checked_frame(
                    np.asarray(screen.grab(screen.monitors[profile.device]))[
                        :, :, :3
                    ].copy(),
                    "screen",
                )
        newly_opened = self.camera is None or self.device != profile.device
        if newly_opened:
            self.close()
            self.camera = cv2.VideoCapture(profile.device)
            self.device = profile.device
        if not self.camera.isOpened():
            self.close()
            raise RuntimeError(
                "Camera unavailable. Check device index and camera permission"
            )
        # Cameras commonly return black frames while exposure initializes.
        started = time.monotonic()
        for _ in range(30):
            ok, frame = self.camera.read()
            if (
                ok
                and frame is not None
                and (not newly_opened or time.monotonic() - started >= 0.4)
            ):
                try:
                    return checked_frame(frame, "camera")
                except RuntimeError:
                    pass
            if time.monotonic() - started > 2:
                break
            time.sleep(0.05)
        self.close()
        raise RuntimeError(
            "Camera returned no usable frame. Check camera permission, lens cover and device index."
        )

    def close(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None


def checked_frame(frame, source):
    if frame is None or frame.size == 0:
        raise RuntimeError(f"No {source} image returned")
    if frame.max() <= 2:
        raise RuntimeError(
            f"A black {source} frame was returned. Check screen-recording permission, display lock or camera lens; the previous image is retained."
        )
    return frame


def screen_permission(request=False):
    if sys.platform != "darwin":
        return True
    core = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    function = (
        core.CGRequestScreenCaptureAccess
        if request
        else core.CGPreflightScreenCaptureAccess
    )
    function.restype = ctypes.c_bool
    function.argtypes = []
    return bool(function())


def composite_displays(images, monitors):
    # Bounds are desktop coordinates (possibly negative); crops are physical pixels.
    scale = max(
        image.shape[1] / monitor["width"] for image, monitor in zip(images, monitors)
    )
    left = min(m["left"] for m in monitors)
    top = min(m["top"] for m in monitors)
    width = round((max(m["left"] + m["width"] for m in monitors) - left) * scale)
    height = round((max(m["top"] + m["height"] for m in monitors) - top) * scale)
    if width * height > 64_000_000:
        raise RuntimeError(
            "Combined desktop is too large; select one monitor in Settings"
        )
    output = np.zeros((height, width, 3), np.uint8)
    for image, monitor in zip(images, monitors):
        x = round((monitor["left"] - left) * scale)
        y = round((monitor["top"] - top) * scale)
        w = round(monitor["width"] * scale)
        h = round(monitor["height"] * scale)
        output[y : y + h, x : x + w] = cv2.resize(
            image, (w, h), interpolation=cv2.INTER_LINEAR
        )
    return output


def mac_screen(device):
    if not screen_permission():
        raise RuntimeError(
            "Screen recording permission is required. Enable LiKeWatch in System Settings → Privacy & Security → Screen & System Audio Recording, then restart LiKeWatch."
        )
    import mss

    with mss.mss() as screen:
        monitors = screen.monitors[1:]
    if not 0 <= device <= len(monitors):
        raise RuntimeError("Monitor unavailable; select another monitor index")
    indices = list(range(1, len(monitors) + 1)) if device == 0 else [device]
    images = []
    # The system capture utility uses the current macOS capture implementation;
    # MSS's deprecated CGDisplayCreateImage path can return black on newer macOS.
    with tempfile.TemporaryDirectory(prefix="likewatch-screen-") as directory:
        for index in indices:
            path = Path(directory) / f"display-{index}.png"
            environment = os.environ.copy()
            environment.pop("DYLD_LIBRARY_PATH", None)
            result = subprocess.run(
                [
                    "/usr/sbin/screencapture",
                    "-x",
                    "-D",
                    str(index),
                    "-t",
                    "png",
                    str(path),
                ],
                capture_output=True,
                timeout=15,
                env=environment,
            )
            if result.returncode or not path.exists():
                raise RuntimeError(
                    "macOS screen capture failed. Check screen-recording permission and whether the display is unlocked."
                )
            images.append(checked_frame(cv2.imread(str(path)), "screen"))
    if len(images) == 1:
        return images[0]
    return composite_displays(images, [monitors[i - 1] for i in indices])
