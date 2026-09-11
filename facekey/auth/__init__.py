"""Authentication pipeline — ties detection, recognition, anti-spoofing, and liveness together."""

from facekey.auth.pipeline import AuthPipeline, AuthResult
from facekey.auth.fast_pipeline import FastPipeline

__all__ = ["AuthPipeline", "AuthResult", "FastPipeline"]
