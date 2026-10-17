"""Event-to-module-to-risk pipeline."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sentinal.core.event_bus import EventBus
from sentinal.core.schemas import Event
from sentinal.explain import build_card
from sentinal.modules.cyber import CyberAnalyzer
from sentinal.modules.environment import EnvironmentAnalyzer
from sentinal.modules.telemetry import TelemetryValidator
from sentinal.risk import FactorInput


ASSETS = {
    "flood": "asset_port_01",
    "wildfire": "asset_hospital_01",
    "satellite_fault": "asset_ground_01",
    "cyber_attack": "asset_grid_01",
}


class SatelliteAnalyzer:
    """Score numeric satellite event payloads without synthetic scenario constants."""

    def analyze(self, payload: dict[str, Any], *, signal_id: str, event_id: str) -> dict[str, Any]:
        reasons: list[dict[str, str]] = []
        evidence: list[dict[str, str]] = []
        scores: list[float] = []
        attitude = payload.get("attitude_deg")
        if isinstance(attitude, (int, float)) and not isinstance(attitude, bool):
            score = min(100.0, abs(float(attitude)) / 1.0 * 100)
            scores.append(score)
            if score > 0:
                reasons.append({"code": "attitude_deviation", "detail": f"attitude deviation is {attitude:g} degrees"})
                evidence.append({"type": "satellite", "ref": event_id, "detail": "attitude_deg"})
        signal = payload.get("signal_db")
        if isinstance(signal, (int, float)) and not isinstance(signal, bool):
            score = min(100.0, max(0.0, (-60.0 - float(signal)) * 2.5))
            scores.append(score)
            if score > 0:
                reasons.append({"code": "weak_signal", "detail": f"signal is {signal:g} dB"})
                evidence.append({"type": "satellite", "ref": event_id, "detail": "signal_db"})
        changed = payload.get("changed_fraction", payload.get("change_fraction"))
        if isinstance(changed, (int, float)) and not isinstance(changed, bool):
            score = min(100.0, max(0.0, float(changed) * 100))
            scores.append(score)
            if score > 0:
                reasons.append({"code": "surface_change", "detail": f"changed fraction is {changed:g}"})
                evidence.append({"type": "satellite", "ref": event_id, "detail": "changed_fraction"})
        score = max(scores, default=0.0)
        if not reasons:
            reasons = [{"code": "no_satellite_indicators", "detail": "no configured satellite anomaly detected"}]
        return {
            "module": "satellite",
            "signal_id": signal_id,
            "score": round(score, 2),
            "label": "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 30 else "low",
            "reasons": reasons,
            "evidence": evidence or [{"type": "satellite", "ref": event_id}],
            "confidence": 0.8 if scores else 0.5,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class EventPipeline:
    """Subscribe module analyzers to the EventBus and derive asset alerts."""

    def __init__(self, state: Any) -> None:
        self.state = state
        self.bus = EventBus()
        self.outputs: dict[str, dict[str, dict[str, Any]]] = {}
        self.telemetry = state.telemetry
        self.environment = EnvironmentAnalyzer()
        self.cyber = CyberAnalyzer()
        self.satellite = SatelliteAnalyzer()
        self.bus.subscribe("telemetry", self._telemetry)
        self.bus.subscribe("environment", self._environment)
        self.bus.subscribe("cyber", self._cyber)
        self.bus.subscribe("satellite", self._satellite)

    @staticmethod
    def asset_id(event: Event) -> str:
        scenario = event.metadata.get("scenario")
        return ASSETS.get(str(scenario), event.source_id)

    async def publish(self, event: Event) -> bool:
        published = await self.bus.publish(event)
        if published:
            self.evaluate(self.asset_id(event))
        return published

    def _store_output(self, event: Event, output: dict[str, Any]) -> None:
        asset_id = self.asset_id(event)
        self.outputs.setdefault(asset_id, {})[output["module"]] = output
        self.state.persistence.save_module_result(event.id, asset_id, output)

    async def _telemetry(self, event: Event) -> None:
        result = self.telemetry.validate(event)
        output = result.model_dump(mode="json")
        severity = {"OK": 0.0, "WARN": 1.0, "ERROR": 2.0, "CRITICAL": 3.0}[result.level]
        score = min(100.0, (len(result.findings) * 15.0) + severity * 20.0)
        output.update({
            "module": "telemetry",
            "signal_id": event.id,
            "score": round(score, 2),
            "label": "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 30 else "low",
            "reasons": [finding.model_dump() for finding in result.findings] or [{"code": "telemetry_ok", "detail": "packet passed telemetry validation"}],
            "evidence": [{"type": "event", "ref": event.id, "event_id": event.id, "source_id": event.source_id, "timestamp": event.timestamp.isoformat(), "raw_ref": event.raw_ref}],
            "confidence": 1.0 if result.level == "OK" else 0.8,
            "event_id": event.id,
        })
        self.state.persistence.save_finding(event.id, output)
        if result.quarantined:
            self.state.persistence.save_quarantine(event.id, event.model_dump(mode="json"), output)
        self._store_output(event, output)

    async def _environment(self, event: Event) -> None:
        output = self.environment.analyze(event.payload, signal_id=event.id)
        output["evidence"] = [{"type": "event", "ref": event.id, "event_id": event.id, "source_id": event.source_id, "timestamp": event.timestamp.isoformat(), "raw_ref": event.raw_ref, "detail": item.get("detail", "")} for item in output["evidence"]] or [{"type": "event", "ref": event.id, "event_id": event.id, "source_id": event.source_id, "timestamp": event.timestamp.isoformat(), "raw_ref": event.raw_ref}]
        output["event_id"] = event.id
        self._store_output(event, output)

    async def _cyber(self, event: Event) -> None:
        output = self.cyber.analyze(event.payload, signal_id=event.id)
        output["evidence"] = [{"type": "event", "ref": event.id, "event_id": event.id, "source_id": event.source_id, "timestamp": event.timestamp.isoformat(), "raw_ref": event.raw_ref, "detail": item.get("detail", "")} for item in output["evidence"]] or [{"type": "event", "ref": event.id, "event_id": event.id, "source_id": event.source_id, "timestamp": event.timestamp.isoformat(), "raw_ref": event.raw_ref}]
        output["event_id"] = event.id
        self._store_output(event, output)

    async def _satellite(self, event: Event) -> None:
        output = self.satellite.analyze(event.payload, signal_id=event.id, event_id=event.id)
        output["evidence"] = [
            {**item, "event_id": event.id, "source_id": event.source_id, "timestamp": event.timestamp.isoformat(), "raw_ref": event.raw_ref}
            for item in output.get("evidence", [])
        ] or [{"type": "event", "ref": event.id, "event_id": event.id, "source_id": event.source_id, "timestamp": event.timestamp.isoformat(), "raw_ref": event.raw_ref}]
        self._store_output(event, output)

    def evaluate(self, asset_id: str) -> dict[str, Any] | None:
        outputs = self.outputs.get(asset_id, {})
        if not outputs or asset_id not in {asset.id for asset in self.state.risk.registry}:
            return None
        factors = {
            name: FactorInput(
                output["score"],
                sources=[{
                    "source_id": (output.get("evidence") or [{}])[0].get("source_id", output["signal_id"]),
                    "event_id": output.get("event_id") or (output.get("evidence") or [{}])[0].get("event_id"),
                    "timestamp": output.get("timestamp") or (output.get("evidence") or [{}])[0].get("timestamp"),
                    "score": output["score"],
                }],
                evidence=output["evidence"],
            )
            for name, output in outputs.items()
        }
        result = self.state.risk.evaluate(asset_id, factors)
        card = build_card(result)
        alert_id = f"pipeline-{asset_id}"
        alert = {
            "id": alert_id,
            "incident_id": alert_id,
            "asset_id": asset_id,
            "status": "New",
            "level": result.level,
            "risk_score": result.score,
            "explanation": {
                "what": card.what,
                "why": list(card.why),
                "confidence": card.confidence,
                "factors": dict(card.factors),
                "evidence": list(card.evidence),
                "next_steps": list(card.next_steps),
                "data_gaps": list(card.data_gaps),
                "weights_version": card.weights_version,
                "reasons": list(card.reasons),
                "provenance": list(card.provenance),
                "recommendation_rationale": [f"{step}: applies to {result.level} risk (score {result.score:.1f})" for step in card.next_steps],
            },
        }
        existing = next((item for item in self.state.alerts if item["id"] == alert_id), None)
        if existing:
            alert["status"] = existing.get("status", "New")
            existing.update(alert)
            self.state.save_alert(existing)
            return existing
        self.state.alerts.append(alert)
        self.state.save_alert(alert)
        return alert
