"""Keyword-first, evidence-only satellite question router."""

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
    """Return an answer whose numeric evidence comes only from ``analysis``."""
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

    evidence_keys = (
        "percent_change",
        "changed_fraction",
        "confidence",
        "hotspots",
        "before_date",
        "after_date",
    )
    evidence = {key: data[key] for key in evidence_keys if key in data}
    text = {
        "what_changed": "Detected change in the analyzed area.",
        "worst_area": "The ranked hotspot regions are shown in the evidence.",
        "how_much": "The analyzed percentage change is reported in the evidence.",
        "compare_dates": "The before/after comparison is complete.",
        "why_flagged": "The area was flagged because observed change exceeded the configured threshold.",
    }[intent]
    return {"intent": intent, "answer": text, "evidence": evidence}
