from fastapi.testclient import TestClient

from sentinal.api.main import State, app
from sentinal.risk import FactorInput, RiskEngine


def test_risk_provenance_contains_event_and_calculation_inputs() -> None:
    result = RiskEngine().evaluate(
        "asset_grid_01",
        {
            "environment": FactorInput(
                80,
                sources=[{"source_id": "weather-1", "event_id": "evt-weather", "timestamp": "2026-01-01T00:00:00Z"}],
                evidence=[{"type": "event", "ref": "evt-weather"}],
            )
        },
        record=False,
    )

    environment = next(item for item in result.provenance if item["factor"] == "environment")
    assert environment["event_ids"] == ["evt-weather"]
    assert environment["source_ids"] == ["weather-1"]
    assert environment["configured_weight"] > 0
    assert environment["calculation_inputs"]["formula"]


def test_why_not_is_evidence_specific_and_missing_data_is_explicit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTINAL_DB_PATH", str(tmp_path / "why-not.db"))
    app.state.store = State()
    with TestClient(app) as client:
        response = client.post("/api/v1/scenarios/flood/run", json={"count": 1, "seed": 91})
        assert response.status_code == 200
        alert = client.get("/api/v1/alerts").json()["items"][0]
        why_not = client.get(f"/api/v1/alerts/{alert['id']}/why-not/environment")

    assert why_not.status_code == 200
    assert why_not.json()["why_not"] in {"threshold-met", "threshold-not-met"}
    assert "comparison" in why_not.json()
