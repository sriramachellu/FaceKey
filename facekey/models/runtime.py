"""ONNX Runtime session management with automatic CPU/GPU detection."""

from pathlib import Path

import onnxruntime as ort


def get_device_info() -> dict:
    """Detect available execution providers and return device info."""
    available = ort.get_available_providers()
    has_cuda = "CUDAExecutionProvider" in available

    return {
        "available_providers": available,
        "has_cuda": has_cuda,
        "active_provider": "CUDAExecutionProvider" if has_cuda else "CPUExecutionProvider",
    }


def create_session(model_path: str | Path, force_cpu: bool = False) -> ort.InferenceSession:
    """Create an ONNX Runtime inference session with best available hardware.

    Tries CUDA first, falls back to CPU. Pass force_cpu=True to skip GPU.
    """
    model_path = str(model_path)
    providers = []

    if not force_cpu:
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            providers.append(("CUDAExecutionProvider", {
                "device_id": 0,
                "arena_extend_strategy": "kNextPowerOfTwo",
                "cudnn_conv_algo_search": "EXHAUSTIVE",
            }))

    providers.append("CPUExecutionProvider")

    session_opts = ort.SessionOptions()
    session_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session_opts.intra_op_num_threads = 0  # auto

    return ort.InferenceSession(model_path, sess_options=session_opts, providers=providers)
