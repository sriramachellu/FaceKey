"""MiniFASNetV2-SE anti-spoofing classifier via ONNX Runtime.

Given a frame and face bounding box, crops with a 2.7x margin and classifies
as real face vs presentation attack (print / screen replay).
"""

import cv2
import numpy as np

from facekey.config import ANTISPOOF_INPUT_SIZE, ANTISPOOF_MODEL, ANTISPOOF_THRESHOLD
from facekey.models import create_session, get_model_path

CROP_SCALE = 2.7


class AntiSpoof:
    """Anti-spoofing classifier: real face vs presentation attack."""

    def __init__(self, force_cpu: bool = False):
        model_path = get_model_path(ANTISPOOF_MODEL)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Anti-spoof model not found at {model_path}. Run 'facekey setup' first."
            )
        self._session = create_session(model_path, force_cpu=force_cpu)
        self._input_name = self._session.get_inputs()[0].name
        self._input_size = ANTISPOOF_INPUT_SIZE

    def predict(self, frame: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[bool, float]:
        """Classify a face as real or spoof.

        Args:
            frame: Full BGR frame from camera.
            bbox: (x, y, w, h) face bounding box from detector.

        Returns:
            (is_real, confidence) where confidence is the probability of being real.
        """
        crop = _crop_with_scale(frame, bbox, CROP_SCALE, self._input_size)

        img = crop.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)

        outputs = self._session.run(None, {self._input_name: img})
        logits = outputs[0].flatten()

        # Output: [live, print_attack, replay_attack]
        probs = _softmax(logits)
        real_score = float(probs[0])

        is_real = real_score >= ANTISPOOF_THRESHOLD
        return is_real, real_score


def _crop_with_scale(
    frame: np.ndarray,
    bbox: tuple[int, int, int, int],
    scale: float,
    output_size: tuple[int, int],
) -> np.ndarray:
    """Crop face from frame with a scale factor around the bbox center."""
    h, w = frame.shape[:2]
    x, y, bw, bh = bbox

    cx = x + bw / 2.0
    cy = y + bh / 2.0

    side = max(bw, bh) * scale
    half = side / 2.0

    x1 = int(max(0, cx - half))
    y1 = int(max(0, cy - half))
    x2 = int(min(w, cx + half))
    y2 = int(min(h, cy + half))

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        crop = frame

    return cv2.resize(crop, output_size)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()
