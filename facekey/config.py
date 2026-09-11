"""Global configuration and constants."""

from pathlib import Path
import os

APP_NAME = "FaceKey"
APP_VERSION = "0.1.0"

# Directories
APP_DATA_DIR = Path(os.environ.get("APPDATA", "~")) / "FaceKey"
MODELS_DIR = APP_DATA_DIR / "models"
EMBEDDINGS_DIR = APP_DATA_DIR / "embeddings"

# HuggingFace model repository
HF_REPO_ID = "sriramamurthychellu/facekey-models"

# Model filenames (downloaded from HuggingFace)
DETECTION_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNITION_MODEL = "w600k_r50.onnx"
ANTISPOOF_MODEL = "MiniFASNetV2.onnx"

# Face detection
DETECTION_SCORE_THRESHOLD = 0.7
DETECTION_NMS_THRESHOLD = 0.3
DETECTION_INPUT_SIZE = (320, 320)

# Face recognition
RECOGNITION_INPUT_SIZE = (112, 112)
SIMILARITY_THRESHOLD = 0.45
MAX_ENROLLED_FACES = 10

# Anti-spoofing
ANTISPOOF_INPUT_SIZE = (80, 80)
ANTISPOOF_THRESHOLD = 0.5

# Liveness detection
BLINK_EAR_THRESHOLD = 0.18
BLINK_CONSECUTIVE_FRAMES = 2
HEAD_POSE_YAW_THRESHOLD = 15.0

# Authentication
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 60
AUTH_TIMEOUT_SECONDS = 10

# Camera
DEFAULT_CAMERA_INDEX = 0
CAMERA_FRAME_WIDTH = 640
CAMERA_FRAME_HEIGHT = 480
CAMERA_FPS = 30
