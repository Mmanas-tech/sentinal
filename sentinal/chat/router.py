"""Keyword-first, evidence-only analysis question router."""

from __future__ import annotations

import re
from typing import Any


def _intent(question: str) -> str | None:
    text = re.sub(r"[^a-z0-9%]+", " ", question.lower()).strip()
    if "how much" in text or "percentage" in text or "percent" in text:
        return "how_much"
    if "compare" in text or "before and after" in text or "dates" in text:
        return "compare_dates"
    if "worst" in text or "hotspot" in text or "most affected" in text:
        return "worst_area"
    if "why" in text and "flag" in text:
        return "why_flagged"
    if "what changed" in text or re.search(r"\bchange(?:d|s)?\b", text):
        return "what_changed"
    return None


def route(question: str, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    """Format answers from a completed analysis, without inventing facts."""
    if not isinstance(question, str):
        return {
            "intent": "unsupported",
            "answer": "Please ask a text question about detected changes, hotspots, percentages, dates, or flag rationale.",
            "evidence": {},
        }
    intent = _intent(question)
    data = analysis if isinstance(analysis, dict) else {}
    if intent is None:
        return {
            "intent": "unsupported",
            "answer": "I can answer questions about detected changes, hotspots, percent change, date comparisons, and flag rationale.",
            "evidence": {},
        }
    if data.get("status") != "ok":
        return {
            "intent": intent,
            "answer": data.get("message", "Analysis results are unavailable."),
            "evidence": {},
        }

    evidence_keys = ("percent_change", "changed_fraction", "confidence", "hotspots", "warnings", "factors", "evidence")
    evidence = {key: data[key] for key in evidence_keys if key in data}
    percent = float(data.get("percent_change", 0.0))
    changed = float(data.get("changed_fraction", 0.0)) * 100.0
    if intent == "what_changed":
        text = f"Detected {percent:.1f}% mean change; {changed:.1f}% of valid pixels crossed the change threshold."
    elif intent == "how_much":
        text = f"{percent:.1f}% mean change was measured across the analyzed area."
    elif intent == "worst_area":
        hotspots = data.get("hotspots") or []
        if not hotspots:
            text = "No changed hotspot areas were found in the analyzed data."
        else:
            hotspot = hotspots[0]
            text = f"Worst area: {hotspot['region_id']} with {hotspot['size']} changed pixels and severity {float(hotspot['severity']):.3f}."
    elif intent == "why_flagged":
        reasons = data.get("why") or data.get("reasons") or []
        text = f"Flag reason: {'; '.join(str(reason) for reason in reasons)}." if reasons else "The alert explanation contains no reasons."
    else:
        text = "Before/after comparison is unavailable because date fields are not present."
    return {"intent": intent, "answer": text, "evidence": evidence}
