"""Webcam capture with automatic resolution and FPS configuration."""

import cv2
import numpy as np

from facekey.config import CAMERA_FPS, CAMERA_FRAME_HEIGHT, CAMERA_FRAME_WIDTH


class Camera:
    """Webcam wrapper with context manager support."""

    def __init__(
        self,
        index: int = 0,
        width: int = CAMERA_FRAME_WIDTH,
        height: int = CAMERA_FRAME_HEIGHT,
        fps: int = CAMERA_FPS,
    ):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        """Open the camera."""
        self._cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera at index {self.index}")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)

    def read(self) -> np.ndarray:
        """Read a single frame. Raises RuntimeError if camera is closed or read fails."""
        if self._cap is None or not self._cap.isOpened():
            raise RuntimeError("Camera is not open")

        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise RuntimeError("Failed to read frame from camera")

        return frame

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def close(self) -> None:
        """Release the camera."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def actual_resolution(self) -> tuple[int, int]:
        """Return the actual resolution the camera is using."""
        if self._cap is None:
            return (0, 0)
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def list_cameras(max_index: int = 5) -> list[int]:
        """Probe for available camera indices."""
        available = []
        for i in range(max_index):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available
