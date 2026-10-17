import asyncio

import pytest
from fastapi.testclient import TestClient

from sentinal.api.main import State, app
from sentinal.core.pipeline import EventPipeline
from sentinal.core.schemas import Event


def event(event_id: str, event_type: str, payload: dict, scenario: str = "flood") -> Event:
    return Event(
        id=event_id,
        source_id=f"{scenario}-source",
        type=event_type,
        timestamp="2026-01-01T00:00:00Z",
        received_at="2026-01-01T00:00:01Z",
        raw_ref=f"test://{event_id}",
        payload=payload,
        metadata={"scenario": scenario},
    )


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINAL_DB_PATH", str(tmp_path / "pipeline.db"))
    return State()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINAL_DB_PATH", str(tmp_path / "api.db"))
    app.state.store = State()
    with TestClient(app) as test_client:
        yield test_client


def test_same_module_input_produces_same_score(state):
    pipeline = EventPipeline(state)
    first = event("environment-1", "environment", {"water_level_m": 3.2})
    second = event("environment-2", "environment", {"water_level_m": 3.2})

    asyncio.run(pipeline.publish(first))
    first_score = pipeline.outputs["asset_port_01"]["environment"]["score"]
    asyncio.run(pipeline.publish(second))
    second_score = pipeline.outputs["asset_port_01"]["environment"]["score"]

    assert first_score == second_score


def test_changed_input_changes_module_score(state):
    pipeline = EventPipeline(state)
    asyncio.run(pipeline.publish(event("environment-1", "environment", {"water_level_m": 3.2})))
    first_score = pipeline.outputs["asset_port_01"]["environment"]["score"]
    asyncio.run(pipeline.publish(event("environment-2", "environment", {"water_level_m": 0.1})))

    assert pipeline.outputs["asset_port_01"]["environment"]["score"] != first_score


def test_flood_scenario_derives_environment_and_telemetry_factors(client):
    response = client.post("/api/v1/scenarios/flood/run", json={"count": 2, "seed": 3})
    assert response.status_code == 200

    alert = client.get("/api/v1/alerts").json()["items"][0]
    factors = alert["explanation"]["factors"]
    evidence = alert["explanation"]["evidence"]

    assert {"environment", "telemetry"} <= set(factors)
    assert factors["environment"] > 0
    assert any(item["type"] == "event" for item in evidence)
    assert all(item.get("ref") != "flood" for item in evidence)


def test_bad_telemetry_packet_raises_telemetry_factor(client):
    response = client.post(
        "/api/v1/ingest",
        json={
            "id": "bad-telemetry-1",
            "source_id": "river-gauge-01",
            "type": "telemetry",
            "timestamp": "2026-01-01T00:00:00Z",
            "received_at": "2026-01-01T00:00:01Z",
            "raw_ref": "test://bad-telemetry-1",
            "payload": {"seq": 1, "session_id": "s", "battery_v": 999},
            "metadata": {"scenario": "flood"},
        },
    )
    assert response.status_code == 200

    alert = client.get("/api/v1/alerts").json()["items"][0]
    assert alert["explanation"]["factors"]["telemetry"] > 0
