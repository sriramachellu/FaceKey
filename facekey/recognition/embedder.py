"""ArcFace face embedding extraction via ONNX Runtime."""

import cv2
import numpy as np

from facekey.config import RECOGNITION_INPUT_SIZE, RECOGNITION_MODEL, SIMILARITY_THRESHOLD
from facekey.models import create_session, get_model_path


class FaceEmbedder:
    """Extract 512-dimensional face embeddings using ArcFace."""

    def __init__(self, force_cpu: bool = False):
        model_path = get_model_path(RECOGNITION_MODEL)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Recognition model not found at {model_path}. Run 'facekey setup' first."
            )
        self._session = create_session(model_path, force_cpu=force_cpu)
        self._input_name = self._session.get_inputs()[0].name
        self._input_size = RECOGNITION_INPUT_SIZE

    def get_embedding(self, aligned_face: np.ndarray) -> np.ndarray:
        """Extract a 512-d embedding from an aligned face image (BGR, 112x112).

        Returns a unit-normalized float32 vector of shape (512,).
        """
        img = cv2.resize(aligned_face, self._input_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32)
        img = (img - 127.5) / 127.5  # normalize to [-1, 1]
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)  # add batch dim

        outputs = self._session.run(None, {self._input_name: img})
        embedding = outputs[0].flatten()

        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    @staticmethod
    def compute_similarity(embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings. Returns value in [-1, 1]."""
        return float(np.dot(embedding1, embedding2))

    @staticmethod
    def is_match(
        embedding1: np.ndarray,
        embedding2: np.ndarray,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> tuple[bool, float]:
        """Check if two embeddings match. Returns (is_match, similarity_score)."""
        sim = float(np.dot(embedding1, embedding2))
        return sim >= threshold, sim
