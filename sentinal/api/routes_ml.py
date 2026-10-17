from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sentinal.ml.telemetry import TelemetryMlError, analyze_telemetry, load_telemetry_file
from sentinal.ml.telemetry import evaluate_detector, load_training_rows
from sentinal.modules.telemetry.stats import IsolationForestDetector
from .security import require_role
from .errors import ApiError

router = APIRouter()


class TelemetryAnalysisRequest(BaseModel):
    samples: list[list[float]] | None = None
    file_path: str | None = None
    model_repo: str | None = None
    window: int = Field(default=24, ge=2, le=2048)


class TelemetryTrainingRequest(BaseModel):
    file_path: str
    artifact_path: str
    min_samples: int = Field(default=20, ge=8, le=100000)
    contamination: str | float = "auto"


@router.post("/ml/telemetry/analyze")
def analyze_real_telemetry(payload: TelemetryAnalysisRequest):
    if bool(payload.samples) == bool(payload.file_path):
        raise ApiError("INVALID_ML_INPUT", "provide exactly one of samples or file_path")
    try:
        values = (
            load_telemetry_file(payload.file_path)
            if payload.file_path
            else load_telemetry_file_from_samples(payload.samples or [])
        )
        result = analyze_telemetry(values, model_repo=payload.model_repo, window=payload.window)
    except TelemetryMlError as exc:
        raise ApiError("ML_UNAVAILABLE", str(exc), status_code=503) from exc
    return result


@router.post("/ml/telemetry/train")
def train_telemetry_model(payload: TelemetryTrainingRequest, _: str = Depends(require_role("admin"))):
    """Train and persist a local model only from a user-supplied dataset."""
    try:
        rows, labels = load_training_rows(payload.file_path)
        detector = IsolationForestDetector(min_samples=payload.min_samples, contamination=payload.contamination)
        training = detector.fit(rows, source=payload.file_path)
        artifact = detector.save(payload.artifact_path)
        evaluation = evaluate_detector(detector, rows, labels)
    except (TelemetryMlError, ValueError, OSError) as exc:
        raise ApiError("ML_TRAINING_FAILED", str(exc), status_code=422) from exc
    return {"training": training, "artifact": artifact, "evaluation": evaluation, "status": "validated" if labels is not None else "unvalidated"}


def load_telemetry_file_from_samples(samples: list[list[float]]):
    import numpy as np

    try:
        values = np.asarray(samples, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise TelemetryMlError("samples must be a numeric 2D matrix") from exc
    if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 1:
        raise TelemetryMlError("samples must be a numeric 2D matrix with at least two rows")
    if not np.isfinite(values).all():
        raise TelemetryMlError("samples contain non-finite values")
    return values
