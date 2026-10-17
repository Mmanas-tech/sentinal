"""Pure, configuration-driven asset risk engine."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from .cascade import AssetRegistry
from .correlation import analyze_sources
from .hysteresis import Hysteresis


@dataclass
class FactorInput:
    """One normalized 0-100 risk factor and its source metadata."""

    score: float
    status: str = "active"
    sources: list[Any] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    certainty: float = 1.0

    def __post_init__(self) -> None:
        self.score = float(self.score)
        self.certainty = float(self.certainty)
        if not math.isfinite(self.score) or not 0 <= self.score <= 100:
            raise ValueError("factor score must be finite and between 0 and 100")
        if self.status not in {"active", "offline", "unknown", "stale", "conflict"}:
            raise ValueError("factor status must be active, offline, unknown, stale, or conflict")
        if not 0 <= self.certainty <= 1:
            raise ValueError("factor certainty must be between 0 and 1")


@dataclass
class RiskResult:
    """A complete, explainable result for one asset evaluation."""

    asset_id: str
    score: float
    label: str
    level: str
    reasons: list[dict[str, str]]
    evidence: list[Any]
    confidence: float
    factors: dict[str, float]
    factor_scores: dict[str, float]
    data_gaps: list[str]
    conflicts: list[dict[str, Any]]
    correlation_boost: float
    cascade_boost: float
    weights_version: str
    trend: str
    hysteresis_state: str
    source_status: dict[str, str]
    provenance: list[dict[str, Any]] = field(default_factory=list)


class RiskEngine:
    """Combine detector factors without persisting anything outside this object."""

    def __init__(
        self,
        config_dir: str | Path | None = None,
        assets: AssetRegistry | None = None,
    ) -> None:
        directory = Path(config_dir) if config_dir else Path(__file__).parents[1] / "config"
        self.weights: dict[str, Any] = self._read_yaml(directory / "weights.yaml")
        self.thresholds: dict[str, Any] = self._read_yaml(directory / "thresholds.yaml")
        self.registry = assets or AssetRegistry.from_yaml(directory / "assets.yaml")
        self.history: dict[str, float] = {}
        self._hysteresis: dict[str, Hysteresis] = {}
        self.weights_version = ""
        self._validate_weights()

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"configuration must be a mapping: {path}")
        return loaded

    def _validate_weights(self) -> None:
        factors = self.weights.get("factors", {})
        validation = self.weights.get("validation", {})
        target = float(validation.get("require_sum", 1.0))
        tolerance = float(validation.get("tolerance", 1e-6))
        if not isinstance(factors, dict) or not factors:
            raise ValueError("risk weights require a non-empty factors mapping")
        values = list(factors.values())
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise ValueError("risk weights must be numeric")
        if any(not math.isfinite(float(value)) or value < 0 for value in values):
            raise ValueError("risk weights must be finite and non-negative")
        total = sum(float(value) for value in values)
        if abs(total - target) > tolerance:
            raise ValueError(f"risk weights must sum to {target}; got {total}")
        self.weights_version = str(self.weights.get("version", "unknown"))

    def update_weights(self, weights: Mapping[str, float], version: str | None = None) -> str:
        """Validate and apply new weights, returning the stored version."""
        previous = copy.deepcopy(self.weights)
        self.weights["factors"] = dict(weights)
        if version is not None:
            self.weights["version"] = version
        try:
            self._validate_weights()
        except Exception:
            self.weights = previous
            self._validate_weights()
            raise
        return self.weights_version

    def evaluate(
        self,
        asset_id: str,
        factors: Mapping[str, FactorInput | Mapping[str, Any] | float],
        *,
        sources: list[Any] | None = None,
        dependency_scores: Mapping[str, float] | None = None,
        record: bool = True,
    ) -> RiskResult:
        """Evaluate an asset using the configured risk formula."""
        asset = self.registry.get(asset_id)
        configured_names = list(self.weights["factors"])
        normalized = {
            name: self._coerce_factor(factors.get(name, FactorInput(0, status="unknown")))
            for name in configured_names
        }
        extra_names = set(factors).difference(configured_names)
        data_gaps = [name for name, value in normalized.items() if value.status != "active"]
        data_gaps.extend(f"unknown_factor:{name}" for name in sorted(extra_names))

        active = {
            name: value
            for name, value in normalized.items()
            if value.status == "active"
        }
        active_weight_total = sum(float(self.weights["factors"][name]) for name in active)
        contributions = {
            name: value.score * float(self.weights["factors"][name]) / active_weight_total
            for name, value in active.items()
        } if active_weight_total else {}
        provenance = []
        for name, value in normalized.items():
            weight = float(self.weights["factors"][name])
            refs = list(value.sources) + list(value.evidence)
            event_ids = sorted({str(x.get("event_id", x.get("ref", x.get("id")))) for x in refs if isinstance(x, dict) and (x.get("event_id") or x.get("ref") or x.get("id"))})
            source_ids = sorted({str(x.get("source_id")) for x in refs if isinstance(x, dict) and x.get("source_id")})
            timestamps = sorted({str(x.get("timestamp", x.get("occurred_at", x.get("time")))) for x in refs if isinstance(x, dict) and (x.get("timestamp") or x.get("occurred_at") or x.get("time"))})
            provenance.append({"factor": name, "event_ids": event_ids, "source_ids": source_ids,
                "utc_timestamps": timestamps, "timestamps": timestamps, "source_status": value.status,
                "freshness": value.status == "active", "freshness_status": "fresh" if value.status == "active" else value.status,
                "configured_weight": weight, "normalized_contribution": contributions.get(name, 0.0),
                "calculation_inputs": {"score": value.score, "active_weight_total": active_weight_total,
                                       "certainty": value.certainty, "formula": "score * weight / active_weight_total"}})
        base = sum(contributions.values())

        source_values = sources if sources is not None else self._factor_sources(active)
        correlation_config = self.weights.get("correlation_boost", {})
        correlation_boost, conflicts, agreeing_sources = analyze_sources(
            source_values,
            per_extra=float(correlation_config.get("per_extra_source", 5)),
            maximum=float(correlation_config.get("max", 15)),
            agreement_tolerance=float(correlation_config.get("agreement_tolerance", 10)),
        )
        known_scores = dict(self.history)
        if dependency_scores is not None:
            known_scores.update(dependency_scores)
        cascade_config = self.weights.get("cascade_boost", {})
        cascade_boost = self.registry.cascade_boost(
            asset_id,
            known_scores,
            float(cascade_config.get("dependency_fraction", 0.30)),
        )

        importance_multiplier = 0.5 + 0.5 * asset.importance / 100
        score = min(100.0, base * importance_multiplier + correlation_boost + cascade_boost)
        level = self._level(score)
        previous_score = self.history.get(asset_id)
        trend = "steady" if previous_score is None or abs(score - previous_score) < 1 else (
            "rising" if score > previous_score else "falling"
        )

        hysteresis = self._hysteresis.setdefault(asset_id, self._new_hysteresis())
        state = hysteresis if record else copy.deepcopy(hysteresis)
        hysteresis_state = state.update(score)
        if record:
            self.history[asset_id] = score

        source_status = {name: value.status for name, value in normalized.items()}
        confidence = self._confidence(
            normalized,
            agreeing_sources=agreeing_sources,
            conflicts=conflicts,
        )
        reasons = self._reasons(
            contributions,
            normalized,
            data_gaps,
            conflicts,
            correlation_boost,
            cascade_boost,
        )
        evidence = [item for value in normalized.values() for item in value.evidence]
        return RiskResult(
            asset_id=asset_id,
            score=score,
            label=level.capitalize(),
            level=level,
            reasons=reasons,
            evidence=evidence,
            confidence=confidence,
            factors=contributions,
            factor_scores={name: value.score for name, value in normalized.items()},
            data_gaps=data_gaps,
            conflicts=conflicts,
            correlation_boost=correlation_boost,
            cascade_boost=cascade_boost,
            weights_version=self.weights_version,
            trend=trend,
            hysteresis_state=hysteresis_state,
            source_status=source_status,
            provenance=provenance,
        )

    def what_if(
        self,
        asset_id: str,
        factors: Mapping[str, FactorInput | Mapping[str, Any] | float],
        *,
        sources: list[Any] | None = None,
        dependency_scores: Mapping[str, float] | None = None,
    ) -> RiskResult:
        """Calculate a counterfactual without changing history or alert state."""
        return self.evaluate(
            asset_id,
            factors,
            sources=sources,
            dependency_scores=dependency_scores,
            record=False,
        )

    def rank(
        self,
        inputs: Mapping[str, Mapping[str, FactorInput | Mapping[str, Any] | float]],
        *,
        record: bool = True,
    ) -> list[RiskResult]:
        return sorted(
            (self.evaluate(asset_id, factors, record=record) for asset_id, factors in inputs.items()),
            key=lambda result: result.score,
            reverse=True,
        )

    def asset_ranking(
        self,
        inputs: Mapping[str, Mapping[str, FactorInput | Mapping[str, Any] | float]],
        *,
        record: bool = True,
    ) -> list[RiskResult]:
        return self.rank(inputs, record=record)

    def _new_hysteresis(self) -> Hysteresis:
        config = self.thresholds.get("hysteresis", {})
        return Hysteresis(
            raise_high_at=float(config.get("raise_high_at", 60)),
            clear_high_below=float(config.get("clear_high_below", 55)),
            raise_critical_at=float(config.get("raise_critical_at", 80)),
            clear_critical_below=float(config.get("clear_critical_below", 75)),
        )

    def _level(self, score: float) -> str:
        for name, bounds in self.thresholds.get("risk_levels", {}).items():
            lower = float(bounds["min"])
            upper = float(bounds["max"])
            if lower <= score < upper + 1:
                return str(name)
        return "critical"

    @staticmethod
    def _coerce_factor(value: FactorInput | Mapping[str, Any] | float) -> FactorInput:
        if isinstance(value, FactorInput):
            return value
        if isinstance(value, Mapping):
            return FactorInput(**value)
        return FactorInput(float(value))

    @staticmethod
    def _factor_sources(active: Mapping[str, FactorInput]) -> list[Any]:
        sources: list[Any] = []
        for factor_name, factor in active.items():
            for source in factor.sources:
                if isinstance(source, dict):
                    item = dict(source)
                    item.setdefault("score", factor.score)
                    item.setdefault("factor", factor_name)
                elif isinstance(source, str):
                    item = {"source_id": source, "score": factor.score, "factor": factor_name}
                else:
                    item = source
                sources.append(item)
        return sources

    def _confidence(
        self,
        factors: Mapping[str, FactorInput],
        *,
        agreeing_sources: int,
        conflicts: list[dict[str, Any]],
    ) -> float:
        total = len(factors)
        active = [value for value in factors.values() if value.status == "active"]
        data_quality = len(active) / total if total else 0.0
        if agreeing_sources >= 2:
            corroboration = 1.0
        elif agreeing_sources == 1:
            corroboration = float(self.weights.get("single_source_confidence_cap", 0.70))
        else:
            corroboration = 0.50
        certainty = sum(value.certainty for value in active) / len(active) if active else 0.0
        confidence = 0.5 * data_quality + 0.3 * corroboration + 0.2 * certainty
        if conflicts:
            confidence *= 0.85
        if any(value.status != "active" for value in factors.values()):
            confidence *= 0.85
        if agreeing_sources <= 1:
            confidence = min(
                confidence,
                float(self.weights.get("single_source_confidence_cap", 0.70)),
            )
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _reasons(
        contributions: Mapping[str, float],
        factors: Mapping[str, FactorInput],
        data_gaps: list[str],
        conflicts: list[dict[str, Any]],
        correlation_boost: float,
        cascade_boost: float,
    ) -> list[dict[str, str]]:
        reasons: list[dict[str, str]] = []
        for name, points in sorted(contributions.items(), key=lambda item: item[1], reverse=True):
            reasons.append(
                {
                    "code": f"{name.upper()}_FACTOR",
                    "detail": f"{name} score {factors[name].score:.1f} contributed {points:.1f} points",
                }
            )
        for gap in data_gaps:
            reasons.append({"code": "DATA_GAP", "detail": f"{gap} source is unavailable or unknown"})
        if conflicts:
            reasons.append(
                {
                    "code": "SOURCE_CONFLICT",
                    "detail": f"{len(conflicts)} source signal(s) disagree with the leading cluster",
                }
            )
        if correlation_boost:
            reasons.append(
                {
                    "code": "CORRELATION_BOOST",
                    "detail": f"independent sources added {correlation_boost:.1f} points",
                }
            )
        if cascade_boost:
            reasons.append(
                {
                    "code": "CASCADE_BOOST",
                    "detail": f"dependent asset risk added {cascade_boost:.1f} points",
                }
            )
        if not reasons:
            reasons.append({"code": "BASE_RISK", "detail": "no active factor exceeded zero"})
        return reasons
