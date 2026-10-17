from typing import Any

from fastapi import APIRouter, Request

from sentinal.chat import route
from sentinal.modules.satellite import analyze_change, rank_hotspots

router = APIRouter()


def _current_change(request: Request) -> dict[str, Any]:
    for event in reversed(request.app.state.store.events):
        if event.get("type") != "satellite":
            continue
        values = event.get("payload") or {}
        if "before" not in values or "after" not in values:
            continue
        result = analyze_change(
            values["before"],
            values["after"],
            threshold=float(values.get("threshold", 0.15)),
            cloud_cover=float(values.get("cloud_cover", 0.0)),
            aoi=values.get("aoi"),
        )
        if result.get("status") != "ok":
            return result
        import numpy as np
        before = np.asarray(values["before"], dtype=float)
        after = np.asarray(values["after"], dtype=float)
        difference = np.abs(after - before) / np.maximum(np.abs(before), 1e-9)
        result["hotspots"] = rank_hotspots(result["difference_mask"], np.minimum(difference, 1.0))
        result.pop("difference_mask", None)
        return result
    return {"status": "missing", "message": "Missing current scenario satellite data: a satellite event with payload.before and payload.after is required."}


@router.post("/chat")
def chat(request: Request, payload: dict[str, Any]):
    question = payload.get("question")
    intent = route(question).get("intent")
    if intent == "why_flagged":
        alert_id = payload.get("alert_id")
        if not alert_id:
            return route(question, {"status": "refused", "message": "Missing alert_id required to fetch the alert explanation."})
        for alert in reversed(request.app.state.store.alerts):
            if alert.get("id") == alert_id:
                explanation = alert.get("explanation") or {}
                return route(question, {
                    "status": "ok",
                    "why": explanation.get("why") or alert.get("reasons") or [],
                    "confidence": explanation.get("confidence"),
                    "factors": explanation.get("factors", {}),
                    "evidence": explanation.get("evidence", []),
                })
        return route(question, {"status": "refused", "message": f"Missing alert explanation: alert_id '{alert_id}' was not found."})
    if intent in {"what_changed", "worst_area", "how_much"}:
        analysis = _current_change(request)
        return route(question, analysis)
    return route(question)
