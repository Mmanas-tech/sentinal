"""Immutable, auditable explanation cards."""
from dataclasses import dataclass, field
from typing import Any, Mapping
from types import MappingProxyType
from datetime import datetime, timezone
from sentinal.risk.engine import RiskResult
from .playbooks import load_playbooks

@dataclass(frozen=True)
class ExplanationCard:
    what: str
    why: tuple[str, ...]
    confidence: float
    factors: Mapping[str, float]
    evidence: tuple[Any, ...]
    next_steps: tuple[str, ...]
    data_gaps: tuple[str, ...]
    weights_version: str
    reasons: tuple[Mapping[str, str], ...] = field(default_factory=tuple)
    provenance: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    def __post_init__(self):
        object.__setattr__(self, 'factors', MappingProxyType(dict(self.factors)))
        object.__setattr__(self, 'confidence', max(0.0, min(1.0, float(self.confidence))))
        object.__setattr__(self, 'provenance', tuple(dict(item) for item in self.provenance))


def build_card(
    result: RiskResult,
    *,
    next_steps: list[str] | None = None,
    playbooks: Mapping[str, Any] | None = None,
) -> ExplanationCard:
    reasons = tuple(dict(r) for r in result.reasons)
    why = tuple(r.get('detail', str(r)) for r in reasons)
    evidence = tuple(result.evidence)
    if next_steps is None:
        configured = playbooks if playbooks is not None else load_playbooks()
        default_steps = configured.get("default", {}) if isinstance(configured, dict) else {}
        if isinstance(default_steps, dict) and isinstance(default_steps.get("next_steps"), list):
            selected = default_steps["next_steps"]
        else:
            selected = default_steps.get(result.level, []) if isinstance(default_steps, dict) else []
        next_steps = list(selected) if isinstance(selected, list) else []
    rationale = tuple(f"{step}: applies to {result.level} risk (score {result.score:.1f})" for step in (next_steps or []))
    return ExplanationCard(
        what=f"{result.label} risk for asset {result.asset_id} (score {result.score:.1f})",
        why=why or ('No specific reason was recorded.',), confidence=result.confidence,
        factors=result.factors, evidence=evidence, next_steps=tuple(next_steps or ()),
        data_gaps=tuple(result.data_gaps), weights_version=result.weights_version, reasons=reasons,
        provenance=tuple(result.provenance))
