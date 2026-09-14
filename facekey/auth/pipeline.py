"""End-to-end authentication pipeline.

Runs face detection → alignment → embedding → matching → anti-spoofing → liveness
in a single pass, returning a structured result.
"""

from dataclasses import dataclass, field
from enum import Enum
import time

import cv2
import numpy as np

from facekey.antispoof import AntiSpoof
from facekey.config import AUTH_TIMEOUT_SECONDS, MAX_FAILED_ATTEMPTS, SIMILARITY_THRESHOLD
from facekey.detection import FaceDetector
from facekey.liveness import LivenessChecker
from facekey.recognition import FaceEmbedder
from facekey.storage import EmbeddingVault


class AuthStatus(Enum):
    SUCCESS = "success"
    NO_FACE = "no_face"
    NO_MATCH = "no_match"
    SPOOF_DETECTED = "spoof_detected"
    LIVENESS_FAILED = "liveness_failed"
    LOCKED_OUT = "locked_out"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class AuthResult:
    status: AuthStatus
    profile_name: str | None = None
    similarity: float = 0.0
    spoof_score: float = 0.0
    liveness_passed: bool = False
    elapsed_ms: float = 0.0
    details: dict = field(default_factory=dict)


class AuthPipeline:
    """Complete face authentication pipeline."""

    def __init__(
        self,
        detector: FaceDetector | None = None,
        embedder: FaceEmbedder | None = None,
        antispoof: AntiSpoof | None = None,
        liveness: LivenessChecker | None = None,
        vault: EmbeddingVault | None = None,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        force_cpu: bool = False,
    ):
        self.detector = detector or FaceDetector()
        self.embedder = embedder or FaceEmbedder(force_cpu=force_cpu)
        self.antispoof = antispoof or AntiSpoof(force_cpu=force_cpu)
        self.liveness = liveness or LivenessChecker()
        self.vault = vault or EmbeddingVault()
        self.similarity_threshold = similarity_threshold

        self._failed_attempts = 0
        self._lockout_until: float = 0

    def authenticate_frame(self, frame: np.ndarray) -> AuthResult:
        """Run full authentication on a single BGR frame.

        For liveness (blink detection), call this on multiple consecutive frames
        and check liveness status accumulates across calls.
        """
        start = time.perf_counter()

        if self._is_locked_out():
            return AuthResult(
                status=AuthStatus.LOCKED_OUT,
                elapsed_ms=_elapsed(start),
            )

        # Step 1: Detect face
        face = self.detector.detect_largest(frame)
        if face is None:
            return AuthResult(status=AuthStatus.NO_FACE, elapsed_ms=_elapsed(start))

        # Step 2: Anti-spoofing (soft signal — logged, not a hard gate)
        is_real, spoof_score = self.antispoof.predict(frame, face["bbox"])

        # Step 3: Align face and extract embedding
        aligned = self.detector.align_face(frame, face["landmarks"])
        embedding = self.embedder.get_embedding(aligned)

        # Step 4: Match against enrolled profiles
        best_match, best_sim = self._find_best_match(embedding)

        if best_match is None:
            self._record_failure()
            return AuthResult(
                status=AuthStatus.NO_MATCH,
                similarity=best_sim,
                spoof_score=spoof_score,
                elapsed_ms=_elapsed(start),
            )

        # Step 5: Liveness check (accumulates across frames)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        liveness_data = self.liveness.process_frame(frame_rgb)

        return AuthResult(
            status=AuthStatus.SUCCESS,
            profile_name=best_match,
            similarity=best_sim,
            spoof_score=spoof_score,
            liveness_passed=self.liveness.check_liveness(
                require_blink=True, require_movement=False
            ),
            elapsed_ms=_elapsed(start),
            details=liveness_data,
        )

    def _find_best_match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        """Find the best matching profile for an embedding."""
        all_profiles = self.vault.get_all_embeddings()
        best_name = None
        best_sim = -1.0

        for name, stored_embeddings in all_profiles.items():
            for stored_emb in stored_embeddings:
                sim = float(np.dot(embedding, stored_emb))
                if sim > best_sim:
                    best_sim = sim
                    best_name = name

        if best_sim < self.similarity_threshold:
            return None, best_sim

        return best_name, best_sim

    def _record_failure(self):
        self._failed_attempts += 1
        if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
            from facekey.config import LOCKOUT_DURATION_SECONDS
            self._lockout_until = time.time() + LOCKOUT_DURATION_SECONDS

    def _is_locked_out(self) -> bool:
        if self._failed_attempts < MAX_FAILED_ATTEMPTS:
            return False
        if time.time() >= self._lockout_until:
            self._failed_attempts = 0
            return False
        return True

    def reset(self):
        """Reset authentication state."""
        self._failed_attempts = 0
        self._lockout_until = 0
        self.liveness.reset()


def _elapsed(start: float) -> float:
    return (time.perf_counter() - start) * 1000
