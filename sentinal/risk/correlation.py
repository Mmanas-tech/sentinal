"""Cross-source agreement and conflict analysis."""

from __future__ import annotations

from typing import Any, Iterable


def _source_id(source: Any) -> str:
    if isinstance(source, dict):
        return str(source.get("id", source.get("source_id", "unknown")))
    return str(getattr(source, "id", getattr(source, "source_id", "unknown")))


def _source_score(source: Any) -> float | None:
    if isinstance(source, dict):
        value = source.get("score", source.get("value"))
    else:
        value = getattr(source, "score", getattr(source, "value", None))
    if value is None:
        return None
    return float(value)


def analyze_sources(
    sources: Iterable[Any] | None,
    per_extra: float = 5.0,
    maximum: float = 15.0,
    agreement_tolerance: float = 10.0,
) -> tuple[float, list[dict[str, Any]], int]:
    """Return the agreement boost, conflicts, and agreeing source count."""
    values: list[tuple[str, float]] = []
    for source in sources or []:
        score = _source_score(source)
        if score is not None:
            values.append((_source_id(source), score))
    if not values:
        return 0.0, [], 0

    clusters: list[list[tuple[str, float]]] = []
    for item in sorted(values, key=lambda pair: pair[1]):
        matching = [
            cluster
            for cluster in clusters
            if abs(item[1] - (sum(score for _, score in cluster) / len(cluster)))
            <= agreement_tolerance
        ]
        if matching:
            matching[0].append(item)
        else:
            clusters.append([item])

    winner = max(clusters, key=lambda cluster: len({_id for _id, _ in cluster}))
    agreeing_ids = sorted({_id for _id, _ in winner})
    winner_ids = set(agreeing_ids)
    conflicts = [
        {"source_id": source_id, "score": score}
        for source_id, score in values
        if source_id not in winner_ids
    ]
    boost = min(maximum, per_extra * max(0, len(agreeing_ids) - 1))
    return boost, conflicts, len(agreeing_ids)


def correlate_signals(physical=None, telemetry=None, cyber=None, *, gps_spoofing=False):
    """Rule-based cross-source correlation; malformed inputs are ignored."""
    signals = [x for x in (physical, telemetry, cyber) if isinstance(x, dict)]
    scores = [float(x.get("score", 0)) for x in signals if isinstance(x.get("score", 0), (int, float))]
    reasons = []
    if len(scores) >= 2 and sum(v >= 60 for v in scores) >= 2:
        reasons.append({"code": "multi_source_agreement", "detail": "multiple sources indicate elevated risk"})
    if gps_spoofing or any(isinstance(x, dict) and x.get("gps_spoofing") for x in signals):
        reasons.append({"code": "gps_spoofing", "detail": "GPS spoofing indicator correlated across signals"})
    score = min(100.0, max(scores, default=0) + (15 if len(reasons) else 0))
    return {"module": "correlation", "score": score, "label": "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 30 else "low", "reasons": reasons or [{"code":"no_correlation","detail":"no cross-source correlation detected"}], "evidence": [{"type":"source","ref":str(i)} for i in range(len(signals))], "confidence": min(1.0, .5 + .1*len(signals))}
