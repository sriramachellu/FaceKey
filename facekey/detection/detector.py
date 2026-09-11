"""YuNet face detection via OpenCV's built-in DNN module."""

import cv2
import numpy as np

from facekey.config import DETECTION_MODEL, DETECTION_NMS_THRESHOLD, DETECTION_SCORE_THRESHOLD
from facekey.models.downloader import get_model_path


class FaceDetector:
    """Detect faces using OpenCV's YuNet detector."""

    def __init__(
        self,
        model_path: str | None = None,
        score_threshold: float = DETECTION_SCORE_THRESHOLD,
        nms_threshold: float = DETECTION_NMS_THRESHOLD,
    ):
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self._model_path = model_path or str(get_model_path(DETECTION_MODEL))
        self._detector: cv2.FaceDetectorYN | None = None

    def _get_detector(self, width: int, height: int) -> cv2.FaceDetectorYN:
        """Create or reconfigure the detector for the given frame size."""
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN.create(
                self._model_path, "", (width, height),
                self.score_threshold, self.nms_threshold,
            )
        else:
            self._detector.setInputSize((width, height))
        return self._detector

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Detect faces in a BGR frame.

        Returns a list of dicts, each containing:
            - bbox: (x, y, w, h) bounding box
            - score: detection confidence
            - landmarks: 5 facial landmarks as (x, y) pairs
              [right_eye, left_eye, nose, right_mouth, left_mouth]
        """
        h, w = frame.shape[:2]
        detector = self._get_detector(w, h)
        _, raw = detector.detect(frame)

        if raw is None:
            return []

        faces = []
        for det in raw:
            x, y, bw, bh = det[0:4].astype(int)
            score = float(det[14])

            landmarks = []
            for i in range(5):
                lx = float(det[4 + i * 2])
                ly = float(det[4 + i * 2 + 1])
                landmarks.append((lx, ly))

            faces.append({
                "bbox": (x, y, bw, bh),
                "score": score,
                "landmarks": landmarks,
            })

        faces.sort(key=lambda f: f["bbox"][2] * f["bbox"][3], reverse=True)
        return faces

    def detect_largest(self, frame: np.ndarray) -> dict | None:
        """Detect and return only the largest face."""
        faces = self.detect(frame)
        return faces[0] if faces else None

    @staticmethod
    def crop_face(frame: np.ndarray, bbox: tuple, margin: float = 0.3) -> np.ndarray:
        """Crop face from frame with a margin around the bounding box."""
        h, w = frame.shape[:2]
        x, y, bw, bh = bbox

        mx = int(bw * margin)
        my = int(bh * margin)

        x1 = max(0, x - mx)
        y1 = max(0, y - my)
        x2 = min(w, x + bw + mx)
        y2 = min(h, y + bh + my)

        return frame[y1:y2, x1:x2]

    @staticmethod
    def align_face(
        frame: np.ndarray, landmarks: list[tuple], output_size: tuple = (112, 112)
    ) -> np.ndarray:
        """Align face using the 5 facial landmarks (ArcFace standard alignment)."""
        dst_landmarks = np.array([
            [38.2946, 51.6963],
            [73.5318, 51.5014],
            [56.0252, 71.7366],
            [41.5493, 92.3655],
            [70.7299, 92.2041],
        ], dtype=np.float32)

        if output_size != (112, 112):
            scale_x = output_size[0] / 112.0
            scale_y = output_size[1] / 112.0
            dst_landmarks[:, 0] *= scale_x
            dst_landmarks[:, 1] *= scale_y

        src_landmarks = np.array(landmarks, dtype=np.float32)
        tfm = cv2.estimateAffinePartial2D(src_landmarks, dst_landmarks)[0]

        if tfm is None:
            x, y, bw, bh = 0, 0, frame.shape[1], frame.shape[0]
            cropped = frame[y:y+bh, x:x+bw]
            return cv2.resize(cropped, output_size)

        aligned = cv2.warpAffine(frame, tfm, output_size, borderValue=0)
        return aligned
