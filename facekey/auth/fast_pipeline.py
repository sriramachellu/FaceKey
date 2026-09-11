"""Optimized authentication pipeline with threaded capture and skip-frame strategy."""

import threading
import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from facekey.antispoof import AntiSpoof
from facekey.auth.pipeline import AuthResult, AuthStatus
from facekey.camera import Camera
from facekey.config import (
    AUTH_TIMEOUT_SECONDS, DEFAULT_CAMERA_INDEX, MAX_FAILED_ATTEMPTS,
    SIMILARITY_THRESHOLD,
)
from facekey.detection import FaceDetector
from facekey.liveness import LivenessChecker
from facekey.recognition import FaceEmbedder
from facekey.storage import EmbeddingVault


class FrameGrabber:
    """Background thread that continuously grabs camera frames."""

    def __init__(self, camera: Camera):
        self._camera = camera
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame

    def _loop(self):
        while self._running:
            try:
                frame = self._camera.read()
                with self._lock:
                    self._frame = frame
            except Exception:
                time.sleep(0.01)


class FastPipeline:
    """Optimized auth pipeline: threaded capture, skip-frame, result caching.

    - Runs detection every frame (~5ms)
    - Runs embedding + match only every `process_interval` frames
    - Caches last match result for `cache_frames` frames after success
    - Liveness runs every frame (lightweight via MediaPipe)
    """

    def __init__(
        self,
        force_cpu: bool = False,
        camera_index: int = DEFAULT_CAMERA_INDEX,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        process_interval: int = 3,
        cache_frames: int = 15,
    ):
        self._force_cpu = force_cpu
        self._camera_index = camera_index
        self._similarity_threshold = similarity_threshold
        self._process_interval = process_interval
        self._cache_frames = cache_frames

        self._detector: FaceDetector | None = None
        self._embedder: FaceEmbedder | None = None
        self._antispoof: AntiSpoof | None = None
        self._liveness: LivenessChecker | None = None
        self._vault: EmbeddingVault | None = None

        self._camera: Camera | None = None
        self._grabber: FrameGrabber | None = None

        self._frame_count = 0
        self._cached_result: AuthResult | None = None
        self._cache_countdown = 0
        self._failed_attempts = 0
        self._lockout_until: float = 0

        self._initialized = False
        self._running = False
        self._latency_history: deque[float] = deque(maxlen=30)

    def initialize(self):
        self._vault = EmbeddingVault()
        self._detector = FaceDetector()
        self._embedder = FaceEmbedder(force_cpu=self._force_cpu)
        self._antispoof = AntiSpoof(force_cpu=self._force_cpu)
        self._liveness = LivenessChecker()

        self._camera = Camera(index=self._camera_index)
        self._camera.open()

        time.sleep(1.5)
        for _ in range(10):
            self._camera.read()

        self._grabber = FrameGrabber(self._camera)
        self._grabber.start()
        self._initialized = True
        self._running = True

    def process_frame(self) -> tuple[np.ndarray | None, AuthResult | None]:
        """Get latest frame and run auth (with skip-frame optimization).

        Returns (frame, result). Frame is always the latest camera frame.
        Result may be cached from a recent full pipeline run.
        """
        if not self._initialized or not self._running:
            return None, None

        frame = self._grabber.get_frame()
        if frame is None:
            return None, None

        start = time.perf_counter()
        self._frame_count += 1

        # Lockout check
        if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
            if time.time() < self._lockout_until:
                return frame, AuthResult(
                    status=AuthStatus.LOCKED_OUT,
                    elapsed_ms=_elapsed(start),
                )
            self._failed_attempts = 0

        # Always run detection (fast, ~5ms)
        face = self._detector.detect_largest(frame)
        if face is None:
            self._cache_countdown = 0
            return frame, AuthResult(
                status=AuthStatus.NO_FACE,
                elapsed_ms=_elapsed(start),
            )

        # If we have a cached successful result, return it
        if self._cache_countdown > 0 and self._cached_result is not None:
            self._cache_countdown -= 1
            # Still run liveness to accumulate blink data
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            liveness_data = self._liveness.process_frame(frame_rgb)
            liveness_passed = self._liveness.check_liveness(
                require_blink=True, require_movement=False,
            )
            elapsed = _elapsed(start)
            self._latency_history.append(elapsed)
            return frame, AuthResult(
                status=self._cached_result.status,
                profile_name=self._cached_result.profile_name,
                similarity=self._cached_result.similarity,
                spoof_score=self._cached_result.spoof_score,
                liveness_passed=liveness_passed,
                elapsed_ms=elapsed,
                details=liveness_data,
            )

        # Skip-frame: only run full pipeline every N frames
        if self._frame_count % self._process_interval != 0:
            elapsed = _elapsed(start)
            self._latency_history.append(elapsed)
            # Return lightweight result with just detection info
            return frame, AuthResult(
                status=AuthStatus.NO_FACE if face is None else (
                    self._cached_result.status if self._cached_result else AuthStatus.NO_MATCH
                ),
                profile_name=self._cached_result.profile_name if self._cached_result else None,
                similarity=self._cached_result.similarity if self._cached_result else 0.0,
                elapsed_ms=elapsed,
            )

        # Full pipeline run
        is_real, spoof_score = self._antispoof.predict(frame, face["bbox"])
        if not is_real:
            self._failed_attempts += 1
            if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
                from facekey.config import LOCKOUT_DURATION_SECONDS
                self._lockout_until = time.time() + LOCKOUT_DURATION_SECONDS
            elapsed = _elapsed(start)
            self._latency_history.append(elapsed)
            result = AuthResult(
                status=AuthStatus.SPOOF_DETECTED,
                spoof_score=spoof_score,
                elapsed_ms=elapsed,
            )
            self._cached_result = result
            return frame, result

        aligned = self._detector.align_face(frame, face["landmarks"])
        embedding = self._embedder.get_embedding(aligned)

        best_name, best_sim = self._find_best_match(embedding)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        liveness_data = self._liveness.process_frame(frame_rgb)
        liveness_passed = self._liveness.check_liveness(
            require_blink=True, require_movement=False,
        )

        if best_name is None:
            self._failed_attempts += 1
            if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
                from facekey.config import LOCKOUT_DURATION_SECONDS
                self._lockout_until = time.time() + LOCKOUT_DURATION_SECONDS
            result = AuthResult(
                status=AuthStatus.NO_MATCH,
                similarity=best_sim,
                spoof_score=spoof_score,
                elapsed_ms=_elapsed(start),
            )
            self._cached_result = result
            return frame, result

        self._failed_attempts = 0
        elapsed = _elapsed(start)
        self._latency_history.append(elapsed)

        result = AuthResult(
            status=AuthStatus.SUCCESS,
            profile_name=best_name,
            similarity=best_sim,
            spoof_score=spoof_score,
            liveness_passed=liveness_passed,
            elapsed_ms=elapsed,
            details=liveness_data,
        )
        self._cached_result = result
        self._cache_countdown = self._cache_frames
        return frame, result

    def _find_best_match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        all_profiles = self._vault.get_all_embeddings()
        best_name = None
        best_sim = -1.0

        for name, stored_embeddings in all_profiles.items():
            for stored_emb in stored_embeddings:
                sim = float(np.dot(embedding, stored_emb))
                if sim > best_sim:
                    best_sim = sim
                    best_name = name

        if best_sim < self._similarity_threshold:
            return None, best_sim
        return best_name, best_sim

    @property
    def avg_latency(self) -> float:
        if not self._latency_history:
            return 0.0
        return sum(self._latency_history) / len(self._latency_history)

    @property
    def profiles_loaded(self) -> list[str]:
        if self._vault is None:
            return []
        return self._vault.list_profiles()

    def reset_liveness(self):
        if self._liveness:
            self._liveness.reset()

    def shutdown(self):
        self._running = False
        if self._grabber:
            self._grabber.stop()
        if self._camera:
            self._camera.close()
            self._camera = None


def _elapsed(start: float) -> float:
    return (time.perf_counter() - start) * 1000
