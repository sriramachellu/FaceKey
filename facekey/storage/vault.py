"""Encrypted face embedding storage using Windows DPAPI.

Embeddings are stored as DPAPI-encrypted blobs — only the same Windows user
account on the same machine can decrypt them.
"""

import json
from pathlib import Path

import numpy as np
import win32crypt

from facekey.config import EMBEDDINGS_DIR


class EmbeddingVault:
    """Store and retrieve face embeddings encrypted with Windows DPAPI."""

    def __init__(self, storage_dir: Path = EMBEDDINGS_DIR):
        self._dir = storage_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _profile_path(self, profile_name: str) -> Path:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in profile_name)
        return self._dir / f"{safe_name}.enc"

    def save_profile(self, profile_name: str, embeddings: list[np.ndarray]) -> None:
        """Save face embeddings for a profile, encrypted with DPAPI."""
        data = {
            "profile_name": profile_name,
            "embeddings": [emb.tolist() for emb in embeddings],
            "count": len(embeddings),
        }
        raw = json.dumps(data).encode("utf-8")
        encrypted = win32crypt.CryptProtectData(raw, profile_name, None, None, None, 0)

        path = self._profile_path(profile_name)
        path.write_bytes(encrypted)

    def load_profile(self, profile_name: str) -> list[np.ndarray]:
        """Load and decrypt face embeddings for a profile."""
        path = self._profile_path(profile_name)
        if not path.exists():
            raise FileNotFoundError(f"No profile found: {profile_name}")

        encrypted = path.read_bytes()
        _, raw = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)

        data = json.loads(raw.decode("utf-8"))
        return [np.array(emb, dtype=np.float32) for emb in data["embeddings"]]

    def delete_profile(self, profile_name: str) -> bool:
        """Delete a profile's encrypted embedding file."""
        path = self._profile_path(profile_name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_profiles(self) -> list[str]:
        """List all stored profile names."""
        profiles = []
        for f in self._dir.glob("*.enc"):
            try:
                encrypted = f.read_bytes()
                _, raw = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
                data = json.loads(raw.decode("utf-8"))
                profiles.append(data["profile_name"])
            except Exception:
                continue
        return profiles

    def profile_exists(self, profile_name: str) -> bool:
        return self._profile_path(profile_name).exists()

    def get_all_embeddings(self) -> dict[str, list[np.ndarray]]:
        """Load all profiles and their embeddings."""
        result = {}
        for name in self.list_profiles():
            try:
                result[name] = self.load_profile(name)
            except Exception:
                continue
        return result
