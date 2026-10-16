"""Confidence and counterfactual helpers."""
from typing import Any, Mapping

def calculate_confidence(*, active: int, total: int, certainty: float = 1.0, corroborating: int = 0, conflicts: int = 0) -> float:
    quality = active / total if total else 0.0
    corroboration = 1.0 if corroborating >= 2 else (0.7 if corroborating == 1 else 0.5)
    value = (.5 * quality + .3 * corroboration + .2 * certainty) * (0.85 if conflicts else 1)
    return max(0.0, min(1.0, value))

def why_not(result: Any, alternatives: Mapping[str, float]) -> list[dict[str, Any]]:
    """Return ranked counterfactual deltas explaining why alternatives were not selected."""
    score = float(getattr(result, 'score', 0.0))
    return [{'alternative': name, 'score': float(value), 'delta': float(value) - score,
             'reason': f"{name} scores {float(value):.1f}, below current {score:.1f}"}
            for name, value in sorted(alternatives.items(), key=lambda x: x[1], reverse=True)]
