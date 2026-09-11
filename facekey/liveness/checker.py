"""Blink detection and head pose estimation using MediaPipe Face Landmarker (Tasks API)."""

import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

from facekey.config import BLINK_CONSECUTIVE_FRAMES, BLINK_EAR_THRESHOLD, HEAD_POSE_YAW_THRESHOLD
from facekey.models.downloader import get_model_path

# MediaPipe Face Mesh landmark indices for eye contours
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]

# Landmarks for head pose estimation
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_CORNER = 263
RIGHT_EYE_CORNER = 33

LANDMARKER_MODEL = "face_landmarker.task"


class LivenessChecker:
    """Detect blinks and head movement to verify liveness."""

    def __init__(self):
        model_path = get_model_path(LANDMARKER_MODEL)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Face landmarker model not found at {model_path}. Run 'facekey setup' first."
            )

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            output_face_blendshapes=False,
        )
        self._landmarker = FaceLandmarker.create_from_options(options)
        self._blink_counter = 0
        self._blink_total = 0
        self._ear_history: list[float] = []
        self._yaw_history: list[float] = []

    def process_frame(self, frame_rgb: np.ndarray) -> dict:
        """Process a single RGB frame and return liveness signals."""
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._landmarker.detect(mp_image)

        if not result.face_landmarks:
            return {"face_detected": False}

        landmarks = result.face_landmarks[0]
        h, w = frame_rgb.shape[:2]

        pts = np.array([(lm.x * w, lm.y * h, lm.z * w) for lm in landmarks])

        ear_left = _eye_aspect_ratio(pts, LEFT_EYE)
        ear_right = _eye_aspect_ratio(pts, RIGHT_EYE)
        ear_avg = (ear_left + ear_right) / 2.0

        is_blinking = ear_avg < BLINK_EAR_THRESHOLD
        if is_blinking:
            self._blink_counter += 1
        else:
            if self._blink_counter >= BLINK_CONSECUTIVE_FRAMES:
                self._blink_total += 1
            self._blink_counter = 0

        self._ear_history.append(ear_avg)

        yaw, pitch, roll = _estimate_head_pose(pts)
        self._yaw_history.append(yaw)

        has_head_movement = False
        if len(self._yaw_history) >= 10:
            recent = self._yaw_history[-30:]
            yaw_range = max(recent) - min(recent)
            has_head_movement = yaw_range > HEAD_POSE_YAW_THRESHOLD

        return {
            "face_detected": True,
            "ear_left": ear_left,
            "ear_right": ear_right,
            "ear_avg": ear_avg,
            "is_blinking": is_blinking,
            "blink_count": self._blink_total,
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
            "has_head_movement": has_head_movement,
        }

    def reset(self):
        """Reset liveness state for a new authentication attempt."""
        self._blink_counter = 0
        self._blink_total = 0
        self._ear_history.clear()
        self._yaw_history.clear()

    def check_liveness(self, require_blink: bool = True, require_movement: bool = False) -> bool:
        """Check if accumulated evidence indicates a live person."""
        blink_ok = (not require_blink) or self._blink_total >= 1
        movement_ok = (not require_movement) or (
            len(self._yaw_history) >= 10
            and (max(self._yaw_history[-30:]) - min(self._yaw_history[-30:])) > HEAD_POSE_YAW_THRESHOLD
        )
        return blink_ok and movement_ok

    def close(self):
        self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _eye_aspect_ratio(pts: np.ndarray, eye_indices: list[int]) -> float:
    """Compute the Eye Aspect Ratio (EAR) for blink detection."""
    p = pts[eye_indices]
    v1 = np.linalg.norm(p[1] - p[5])
    v2 = np.linalg.norm(p[2] - p[4])
    h = np.linalg.norm(p[0] - p[3])
    if h == 0:
        return 0.3
    return (v1 + v2) / (2.0 * h)


def _estimate_head_pose(pts: np.ndarray) -> tuple[float, float, float]:
    """Rough head pose estimation from facial landmarks. Returns (yaw, pitch, roll) in degrees."""
    nose = pts[NOSE_TIP][:2]
    left_eye = pts[LEFT_EYE_CORNER][:2]
    right_eye = pts[RIGHT_EYE_CORNER][:2]

    eye_center = (left_eye + right_eye) / 2.0
    eye_width = np.linalg.norm(left_eye - right_eye)

    if eye_width < 1e-6:
        return 0.0, 0.0, 0.0

    nose_offset = (nose[0] - eye_center[0]) / eye_width
    yaw = float(np.degrees(np.arctan2(nose_offset, 1.0)))

    vert_offset = (nose[1] - eye_center[1]) / eye_width
    pitch = float(np.degrees(np.arctan2(vert_offset, 1.0)))

    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    roll = float(np.degrees(np.arctan2(dy, dx)))

    return yaw, pitch, roll
