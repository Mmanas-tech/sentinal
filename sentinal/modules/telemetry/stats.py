"""Streaming statistical anomaly detectors with one interchangeable interface."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import MutableMapping
from typing import Any


class Detector:
    """Small interface shared by rule and ML-backed anomaly detectors."""

    def update(
        self,
        value: float,
        *,
        source: str = "default",
        sensor: str = "default",
    ) -> dict[str, Any]:
        raise NotImplementedError


class RollingZScoreDetector(Detector):
    """Compute a z-score from values observed before the current value."""

    def __init__(self, window: int = 20, threshold: float = 3.0, min_samples: int = 3) -> None:
        if window < 2 or min_samples < 2:
            raise ValueError("window and min_samples must be at least 2")
        self.window = window
        self.threshold = threshold
        self.min_samples = min_samples
        self.values: MutableMapping[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )

    def update(
        self,
        value: float,
        *,
        source: str = "default",
        sensor: str = "default",
    ) -> dict[str, Any]:
        numeric = float(value)
        history = self.values[(source, sensor)]
        if not history:
            score = 0.0
        else:
            mean = sum(history) / len(history)
            variance = sum((item - mean) ** 2 for item in history) / len(history)
            deviation = variance**0.5
            if deviation == 0:
                score = self.threshold + 1.0 if numeric != mean else 0.0
            else:
                score = abs(numeric - mean) / deviation
        anomalous = len(history) >= self.min_samples and score >= self.threshold
        history.append(numeric)
        return {
            "score": float(score),
            "z_score": float(score),
            "anomalous": anomalous,
            "samples": len(history),
        }


class IsolationForestDetector(Detector):
    """Optional ML detector; disabled and side-effect-free by default."""

    def __init__(
        self,
        enabled: bool = False,
        contamination: str | float = "auto",
        window: int = 100,
        min_samples: int = 20,
    ) -> None:
        self.enabled = enabled
        self.contamination = contamination
        self.min_samples = min_samples
        self.values: MutableMapping[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=window)
        )

    def update(
        self,
        value: float,
        *,
        source: str = "default",
        sensor: str = "default",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"score": 0.0, "anomalous": False, "disabled": True, "samples": 0}

        history = self.values[(source, sensor)]
        history.append(float(value))
        if len(history) < self.min_samples:
            return {
                "score": 0.0,
                "anomalous": False,
                "disabled": False,
                "underfit": True,
                "samples": len(history),
            }

        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(
                contamination=self.contamination,
                random_state=0,
            )
            rows = [[item] for item in history]
            model.fit(rows)
            decision = float(model.decision_function([[float(value)]])[0])
            anomalous = model.predict([[float(value)]])[0] < 0
            return {
                "score": max(0.0, -decision),
                "anomalous": bool(anomalous),
                "disabled": False,
                "underfit": False,
                "samples": len(history),
            }
        except Exception as exc:  # ML is optional and must not stop validation.
            return {
                "score": 0.0,
                "anomalous": False,
                "disabled": False,
                "underfit": False,
                "samples": len(history),
                "error": type(exc).__name__,
            }
