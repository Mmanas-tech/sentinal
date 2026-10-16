import pytest
import io
import json
from datetime import datetime, timezone
fastapi = pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from sentinal.api.main import app, State

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINAL_DB_PATH", str(tmp_path / "test.db"))
    app.state.store = State()
    with TestClient(app) as test_client:
        yield test_client

def test_health_and_ingest(client):
    assert client.get('/health').json()['status'] == 'ok'
    assert client.get('/api/v1/health').json()['status'] == 'ok'
    out = client.post('/api/v1/ingest', json={'events': [{
        'id': 'api-ingest-x',
        'source_id': 'test-source',
        'type': 'telemetry',
        'timestamp': '2026-01-01T00:00:00Z',
        'received_at': '2026-01-01T00:00:01Z',
        'raw_ref': 'test://api-ingest-x',
        'payload': {'seq': 1},
    }]})
    assert out.status_code == 200 and out.json()['accepted'] == 1

def test_bad_scenario_is_structured_error(client):
    response = client.post('/api/v1/scenarios/run', json={'scenario': 'nope'})
    assert response.status_code == 400
    assert set(response.json()['error']) == {'code', 'message', 'details'}

def test_assets_pagination(client):
    response = client.get('/api/v1/risk/assets?limit=1')
    assert response.status_code == 200
    assert {'items', 'page', 'limit', 'total'} <= response.json().keys()

def test_versioned_phase_routes_and_exports(client):
    typed = client.post('/api/v1/ingest/telemetry', json={'events': [{'id': 'typed-1'}]})
    scenario = client.post('/api/v1/scenarios/flood/run', json={'count': 1, 'seed': 2})
    query = client.post('/api/v1/satellite/query', json={'question': 'what changed?'})
    geojson = client.get('/api/v1/export/geojson')
    report = client.get('/api/v1/reports/demo')

    assert typed.status_code == 200
    assert scenario.status_code == 200
    assert query.status_code == 200
    assert geojson.headers['content-type'].startswith('application/geo+json')
    assert report.status_code == 200
    assert report.content.startswith(b'%PDF')


def test_satellite_change_api_returns_analysis_and_chat(client):
    response = client.post(
        '/api/v1/satellite/change',
        json={
            'before': [[0, 0], [0, 0]],
            'after': [[0, 1], [0, 0]],
            'threshold': 0.5,
            'question': 'How much changed?',
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['changed_fraction'] == pytest.approx(0.25)
    assert body['chat']['intent'] == 'how_much'
    assert body['hotspots'][0]['size'] == 1


def test_json_upload_imports_events(client):
    event = {
        'id': 'uploaded-1',
        'source_id': 'upload-source',
        'type': 'satellite',
        'timestamp': '2026-01-01T00:00:00Z',
        'received_at': '2026-01-01T00:00:01Z',
        'raw_ref': 'upload://uploaded-1',
        'payload': {},
    }
    response = client.post(
        '/api/v1/upload',
        files={'file': ('events.json', io.BytesIO(json.dumps({'events': [event]}).encode()), 'application/json')},
    )
    assert response.status_code == 200
    assert response.json()['imported_events'] == 1
    queried = client.get('/api/v1/satellite/query')
    assert queried.json()['total'] >= 1


def test_chat_api_is_evidence_only(client):
    response = client.post(
        '/api/v1/chat',
        json={'question': 'What changed?', 'analysis': {'status': 'ok', 'changed_fraction': 0.25}},
    )
    assert response.status_code == 200
    assert response.json() == {
        'intent': 'what_changed',
        'answer': 'Detected change in the analyzed area.',
        'evidence': {'changed_fraction': 0.25},
    }


def test_diagnostics_csv_and_websocket_replay(client):
    event = {
        'id': 'stream-1',
        'source_id': 'stream-source',
        'type': 'telemetry',
        'timestamp': '2026-01-01T00:00:00Z',
        'received_at': '2026-01-01T00:00:01Z',
        'raw_ref': 'stream://1',
        'payload': {'seq': 1},
    }
    assert client.post('/api/v1/ingest', json=event).json()['accepted'] == 1
    assert client.get('/api/v1/ready').json()['status'] == 'ready'
    assert client.get('/api/v1/metrics').json()['metrics']['ingested'] == 1
    assert client.get('/api/v1/export/csv').headers['content-type'].startswith('text/csv')
    with client.websocket_connect('/ws/stream?since=0') as websocket:
        assert websocket.receive_json()['data']['id'] == 'stream-1'
        websocket.send_json({'type': 'backfill', 'limit': 1})
        assert websocket.receive_json()['type'] == 'event'
        websocket.send_json({'type': 'backfill', 'limit': 0})
        assert websocket.receive_json()['code'] == 'INVALID_BACKFILL_LIMIT'


def test_mutating_routes_support_opt_in_authentication(client, monkeypatch):
    monkeypatch.setenv("SENTINAL_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SENTINAL_API_TOKEN", "test-token")
    denied = client.put('/api/v1/config', json={'mode': 'locked'})
    assert denied.status_code == 401
    allowed = client.put(
        '/api/v1/config',
        json={'mode': 'locked'},
        headers={'Authorization': 'Bearer test-token', 'X-SENTINAL-ROLE': 'admin'},
    )
    assert allowed.status_code == 200


def test_alert_workflow_requires_valid_transition(client):
    scenario = client.post('/api/v1/scenarios/flood/run', json={'count': 1, 'seed': 21})
    assert scenario.status_code == 200
    alert = client.get('/api/v1/alerts').json()['items'][-1]
    acknowledged = client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={'status': 'Acknowledged'},
    )
    assert acknowledged.status_code == 200
    invalid = client.patch(
        f"/api/v1/alerts/{alert['id']}",
        json={'status': 'New'},
    )
    assert invalid.status_code == 400
    assert invalid.json()['error']['code'] == 'INVALID_ALERT_TRANSITION'
