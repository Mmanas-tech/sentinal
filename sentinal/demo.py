"""Offline three-minute SENTINAL demonstration.

Run from the repository root with ``python -m sentinal.demo``.  The demo uses
only deterministic synthetic events and the repository's validator, risk,
explanation, and alert modules.
"""
from __future__ import annotations

from collections import Counter
from sentinal.alerts import alert_from_card
from sentinal.explain import build_card
from sentinal.ingestion import SyntheticGenerator
from sentinal.modules.telemetry import TelemetryValidator
from sentinal.risk import FactorInput, RiskEngine

SCENARIOS = ("flood", "wildfire", "satellite_fault", "cyber_attack")
FAULT_CODES = {"missing_field": "MISSING_FIELD", "out_of_range": "OUT_OF_RANGE", "wrong_type": "WRONG_TYPE",
               "duplicate_sequence": "DUPLICATE_SEQUENCE", "gap_out_of_order": "SEQUENCE_GAP",
               "stale_data": "STALE_DATA", "sudden_jump": "SUDDEN_JUMP"}
ASSETS = ("asset_port_01", "asset_hospital_01", "asset_ground_01", "asset_grid_01")


def run() -> int:
    generator, engine = SyntheticGenerator(), RiskEngine()
    print("SENTINAL offline demo | deterministic telemetry -> risk -> explanation -> alert")
    for number, (scenario, asset) in enumerate(zip(SCENARIOS, ASSETS), 1):
        result = generator.generate(scenario, count=14, seed=120 + number, plant_anomalies=["all"])
        validator = TelemetryValidator()
        telemetry = [event for event in result.events if event.type == "telemetry"]
        findings = [validator.validate(event) for event in telemetry]
        observed = {finding.code for outcome in findings for finding in outcome.findings}
        expected = {FAULT_CODES[item["type"]] for item in result.planted_anomalies}
        missing = expected - observed
        if missing:
            raise RuntimeError(f"{scenario}: planted faults not detected: {sorted(missing)}")
        anomaly_score = min(100.0, 25.0 + 75.0 * len(expected) / len(telemetry))
        factors = {name: FactorInput(0.0, status="unknown") for name in ("satellite", "telemetry", "cyber", "environment")}
        factors["telemetry"] = FactorInput(anomaly_score, evidence=[{"scenario": scenario, "findings": len(observed)}])
        primary = {"flood": "environment", "wildfire": "environment", "satellite_fault": "satellite", "cyber_attack": "cyber"}[scenario]
        factors[primary] = FactorInput(min(100.0, anomaly_score + 20), evidence=[{"scenario": scenario}])
        risk = engine.evaluate(asset, factors, sources=[scenario, "telemetry"])
        card = build_card(risk, next_steps=["Review telemetry evidence", "Confirm operator response"])
        alert = alert_from_card(f"demo-{number}", asset, card)
        print(f"[{number}/4] {scenario:15} packets={len(telemetry):2} faults={len(result.planted_anomalies):2} "
              f"findings={len(observed):2} risk={risk.score:5.1f} {risk.label:8} alert={alert.state}")
        if not card.what or not card.why or not card.evidence or not card.next_steps or not card.weights_version:
            raise RuntimeError(f"{scenario}: incomplete explanation card")
    print("Demo complete: all planted telemetry faults detected and all four scenarios evaluated.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as exc:
        print(f"DEMO FAILED: {exc}")
        raise SystemExit(1)
