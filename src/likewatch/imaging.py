"""Image-coordinate geometry; every ROI has its own homography."""
import cv2
import numpy as np


def validate_corners(corners):
    p = np.asarray(corners, dtype=np.float32)
    if p.shape != (4, 2) or not np.isfinite(p).all() or (p < 0).any() or (p > 1).any():
        raise ValueError("Choose four points inside the image")
    edges = np.roll(p, -1, axis=0) - p
    cross = [float(edges[i,0]*edges[(i+1)%4,1] - edges[i,1]*edges[(i+1)%4,0]) for i in range(4)]
    if not (all(x > 1e-6 for x in cross) or all(x < -1e-6 for x in cross)):
        raise ValueError("Corners must form a convex, uncrossed quadrilateral")
    if abs(cv2.contourArea(p)) < 0.00002:
        raise ValueError("Region is too small")


def rectify(frame, region):
    validate_corners(region.corners)
    h, w = frame.shape[:2]
    p = np.asarray(region.corners, np.float32) * [w-1, h-1]
    width = int(max(np.linalg.norm(p[1]-p[0]), np.linalg.norm(p[2]-p[3])))
    height = int(max(np.linalg.norm(p[3]-p[0]), np.linalg.norm(p[2]-p[1])))
    if width < 5 or height < 5:
        raise ValueError("Region must be at least 5 pixels on each side")
    if region.aspect:
        width = int(height * region.aspect)
    width, height = max(5, min(width, 2048)), max(5, min(height, 2048))
    target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
    matrix = cv2.getPerspectiveTransform(p.astype(np.float32), target)
    corrected = cv2.warpPerspective(frame, matrix, (width, height))
    x0, y0 = np.floor(p.min(axis=0)).astype(int)
    x1, y1 = np.ceil(p.max(axis=0)).astype(int)
    original = frame[y0:y1+1, x0:x1+1].copy()
    return original, corrected


def preprocess(image, recipe):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scale = min(3, max(1, 60 / gray.shape[0]))
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if recipe == "invert":
        gray = 255 - gray
    elif recipe == "otsu":
        _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif recipe == "adaptive":
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    return cv2.copyMakeBorder(gray, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
