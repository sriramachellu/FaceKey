"""Download ONNX models from HuggingFace Hub."""

from pathlib import Path

from huggingface_hub import hf_hub_download

from facekey.config import (
    ANTISPOOF_MODEL,
    DETECTION_MODEL,
    HF_REPO_ID,
    MODELS_DIR,
    RECOGNITION_MODEL,
)

ALL_MODELS = [DETECTION_MODEL, RECOGNITION_MODEL, ANTISPOOF_MODEL]


def get_model_path(filename: str) -> Path:
    """Return the local path for a model file."""
    return MODELS_DIR / filename


def download_model(filename: str, repo_id: str = HF_REPO_ID) -> Path:
    """Download a single model from HuggingFace Hub."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    local_path = get_model_path(filename)

    if local_path.exists():
        return local_path

    downloaded = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=str(MODELS_DIR),
        local_dir_use_symlinks=False,
    )
    return Path(downloaded)


def download_models(repo_id: str = HF_REPO_ID) -> dict[str, Path]:
    """Download all required models. Returns dict of filename -> local path."""
    paths = {}
    for model_name in ALL_MODELS:
        print(f"  Downloading {model_name}...")
        paths[model_name] = download_model(model_name, repo_id)
        print(f"  ✓ {model_name}")
    return paths


def models_available() -> bool:
    """Check if all models are already downloaded."""
    return all(get_model_path(m).exists() for m in ALL_MODELS)
