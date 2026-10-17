"""Streaming statistical anomaly detectors with one interchangeable interface."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import MutableMapping
from typing import Any, Mapping, Sequence
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np


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
    """Local, explicitly trained Isolation Forest detector.

    Models are never trained during ``update``.  Artifacts contain a versioned
    feature schema and checksum, so an unavailable or corrupted model is
    reported as such rather than silently falling back to rules.
    """
    ARTIFACT_VERSION = 1

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
        self.window = window
        self.values: MutableMapping[tuple[str, str], deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self.model = None
        self.feature_names: list[str] = []
        self.medians: dict[str, float] = {}
        self.artifact_path: Path | None = None
        self.provenance: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        return bool(self.enabled and self.model is not None)

    @staticmethod
    def _features(row: Mapping[str, Any] | float, names: Sequence[str] | None = None) -> tuple[list[str], dict[str, float | None]]:
        if isinstance(row, (int, float)):
            return ["value"], {"value": float(row)}
        values: dict[str, float | None] = {}
        for key, value in row.items():
            if value is None or value == "":
                values[str(key)] = None
                continue
            try:
                if isinstance(value, bool):
                    continue
                values[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        selected = list(names) if names else sorted(values)
        return selected, {name: values.get(name) for name in selected}

    def fit(self, rows: Sequence[Mapping[str, Any] | float], *, source: str = "user_supplied") -> dict[str, Any]:
        if len(rows) < self.min_samples:
            raise ValueError(f"at least {self.min_samples} training rows are required")
        names, first = self._features(rows[0])
        parsed = [self._features(row, names)[1] for row in rows]
        self.feature_names = names
        self.medians = {}
        for name in names:
            values = [np.nan if row[name] is None else row[name] for row in parsed]
            if np.isnan(values).all():
                self.medians[name] = 0.0
            else:
                self.medians[name] = float(np.nanmedian(values))
        matrix = np.asarray([[self.medians[name] if r[name] is None else r[name] for name in names] for r in parsed], dtype=float)
        from sklearn.ensemble import IsolationForest
        self.model = IsolationForest(contamination=self.contamination, random_state=0, n_estimators=100)
        self.model.fit(matrix)
        self.enabled = True
        self.provenance = {"source": source, "rows": len(rows), "feature_names": names}
        return {"status": "trained", "samples": len(rows), "features": names}

    def save(self, path: str | Path) -> dict[str, Any]:
        if self.model is None:
            raise ValueError("fit a model before saving")
        payload = {"artifact_version": self.ARTIFACT_VERSION, "feature_names": self.feature_names, "medians": self.medians, "model": self.model, "provenance": self.provenance}
        blob = pickle.dumps(payload, protocol=4)
        record = {"format": "sentinal-isolation-forest", "artifact_version": self.ARTIFACT_VERSION, "sha256": hashlib.sha256(blob).hexdigest(), "payload": blob.hex()}
        target = Path(path); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        self.artifact_path = target
        return {"path": str(target), "sha256": record["sha256"], "artifact_version": self.ARTIFACT_VERSION}

    def load(self, path: str | Path) -> bool:
        target = Path(path)
        try:
            record = json.loads(target.read_text(encoding="utf-8")); blob = bytes.fromhex(record["payload"])
            if record.get("format") != "sentinal-isolation-forest" or record.get("artifact_version") != self.ARTIFACT_VERSION or hashlib.sha256(blob).hexdigest() != record.get("sha256"):
                return False
            payload = pickle.loads(blob)
            self.model, self.feature_names, self.medians = payload["model"], payload["feature_names"], payload["medians"]
            self.provenance = payload.get("provenance", {}); self.enabled = True; self.artifact_path = target
            return True
        except (OSError, ValueError, KeyError, json.JSONDecodeError, pickle.PickleError):
            return False

    def update(
        self,
        value: float | Mapping[str, Any],
        *,
        source: str = "default",
        sensor: str = "default",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"kind": "model", "status": "disabled", "score": 0.0, "anomalous": False, "disabled": True, "samples": 0}

        numeric = float(value) if isinstance(value, (int, float)) else 0.0
        history = self.values[(source, sensor)]
        history.append(numeric)
        if not self.available:
            return {
                "kind": "model", "status": "unavailable", "score": 0.0,
                "anomalous": False,
                "disabled": False,
                "underfit": True,
                "samples": len(history),
            }

        try:
            if isinstance(value, Mapping):
                _, parsed = self._features(value, self.feature_names)
                vector = [[self.medians[name] if parsed.get(name) is None else float(parsed[name]) for name in self.feature_names]]
            else:
                vector = [[float(value) if name == "value" else self.medians[name] for name in self.feature_names]]
            decision = float(self.model.decision_function(vector)[0])
            anomalous = self.model.predict(vector)[0] < 0
            return {
                "kind": "model", "status": "validated",
                "score": max(0.0, -decision),
                "anomalous": bool(anomalous),
                "disabled": False,
                "underfit": False,
                "samples": len(history),
            }
        except Exception as exc:  # ML must not stop deterministic validation.
            return {
                "kind": "model", "status": "error",
                "score": 0.0,
                "anomalous": False,
                "disabled": False,
                "underfit": False,
                "samples": len(history),
                "error": type(exc).__name__,
            }
