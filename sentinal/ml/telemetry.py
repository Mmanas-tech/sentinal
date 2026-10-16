"""NASA-style telemetry loading and optional Hugging Face anomaly scoring."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np


class TelemetryMlError(RuntimeError):
    """A user-actionable error from the optional ML adapter."""


def load_telemetry_file(path: str | Path) -> np.ndarray:
    """Load a numeric CSV or NPY telemetry matrix as [time, channels]."""
    source = Path(path)
    if not source.is_file():
        raise TelemetryMlError(f"telemetry file does not exist: {source}")
    try:
        values = np.load(source) if source.suffix.lower() == ".npy" else np.loadtxt(source, delimiter=",", ndmin=2)
    except (OSError, ValueError) as exc:
        raise TelemetryMlError(f"could not read telemetry file: {source}") from exc
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 1:
        raise TelemetryMlError("telemetry must be a 2D matrix with at least two rows")
    if not np.isfinite(values).all():
        raise TelemetryMlError("telemetry contains non-finite values")
    return values


def _load_huggingface_model(repo_id: str) -> Any:
    try:
        from huggingface_hub import snapshot_download
        import tensorflow as tf
    except ImportError as exc:
        raise TelemetryMlError(
            "ML scoring requires optional dependencies; install sentinal/requirements-ml.txt"
        ) from exc
    try:
        directory = Path(snapshot_download(repo_id=repo_id, allow_patterns=["*.keras", "*.h5"]))
        candidates = sorted(directory.glob("*.keras")) + sorted(directory.glob("*.h5"))
        if not candidates:
            raise TelemetryMlError(f"no Keras model artifact found in Hugging Face repository: {repo_id}")
        return tf.keras.models.load_model(candidates[0], compile=False)
    except TelemetryMlError:
        raise
    except Exception as exc:
        raise TelemetryMlError(f"could not load Hugging Face model {repo_id}: {exc}") from exc


def analyze_telemetry(
    values: np.ndarray,
    *,
    model_repo: str | None = None,
    window: int = 24,
) -> dict[str, Any]:
    """Score telemetry windows with the Hugging Face autoencoder.

    The model is intentionally opt-in and its result is returned as evidence;
    callers decide how to combine it with SENTINAL's deterministic risk rules.
    """
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] < window:
        raise TelemetryMlError(f"telemetry requires at least {window} rows")
    if window < 2:
        raise TelemetryMlError("window must be at least 2")
    repo = model_repo or os.getenv("SENTINAL_HF_TELEMETRY_MODEL", "keras-io/timeseries-anomaly-detection")
    model = _load_huggingface_model(repo)
    windows = np.stack([matrix[index - window:index] for index in range(window, len(matrix) + 1)])
    try:
        reconstructed = np.asarray(model.predict(windows, verbose=0))
    except Exception as exc:
        raise TelemetryMlError(f"Hugging Face model could not score telemetry: {exc}") from exc
    if reconstructed.shape != windows.shape:
        raise TelemetryMlError(
            f"model output shape {reconstructed.shape} does not match telemetry windows {windows.shape}"
        )
    errors = np.mean(np.square(windows - reconstructed), axis=(1, 2))
    threshold = float(np.percentile(errors, 95))
    return {
        "model": repo,
        "window": window,
        "samples": int(len(matrix)),
        "channels": int(matrix.shape[1]),
        "threshold": threshold,
        "anomaly_score": float(errors.max()),
        "anomalous_windows": int(np.sum(errors >= threshold)),
        "window_errors": [float(error) for error in errors],
        "source": "real_telemetry",
    }
