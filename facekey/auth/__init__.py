"""Authentication pipeline — ties detection, recognition, anti-spoofing, and liveness together."""

from facekey.auth.pipeline import AuthPipeline, AuthResult

__all__ = ["AuthPipeline", "AuthResult"]
