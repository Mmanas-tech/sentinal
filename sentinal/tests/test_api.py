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

def test_real_geotiff_upload_api_when_rasterio_is_available(client):
    rasterio = pytest.importorskip('rasterio')
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    def tif(value):
        with MemoryFile() as memory:
            with memory.open(driver='GTiff', height=2, width=2, count=1, dtype='float32', crs='EPSG:4326', transform=from_origin(13, 52, .01, .01)) as dataset:
                dataset.write(np.full((2, 2), value, dtype='float32'), 1)
            return memory.read()

    response = client.post(
        '/api/v1/satellite/change-upload',
        files={
            'before_file': ('before.tif', io.BytesIO(tif(1)), 'image/tiff'),
            'after_file': ('after.tif', io.BytesIO(tif(2)), 'image/tiff'),
        },
    )

    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert response.json()['provenance']['mode'] == 'REAL_RASTER'


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

def test_csv_and_jsonl_uploads_are_processed_and_unsupported_is_rejected(client):
    csv_event = "id,source_id,type,timestamp,received_at,raw_ref,payload\n" \
        f"csv-1,csv-source,environment,2026-01-01T00:00:00Z,2026-01-01T00:00:01Z,csv://1,{json.dumps({'rainfall_mm': 2})}\n"
    csv_response = client.post('/api/v1/upload', files={'file': ('events.csv', io.BytesIO(csv_event.encode()), 'text/csv')})
    jsonl_response = client.post('/api/v1/upload', files={'file': ('events.jsonl', io.BytesIO((json.dumps({
        'id': 'jsonl-1', 'source_id': 'jsonl-source', 'type': 'environment',
        'timestamp': '2026-01-01T00:00:00Z', 'received_at': '2026-01-01T00:00:01Z',
        'raw_ref': 'jsonl://1', 'payload': {'rainfall_mm': 3},
    }) + '\n').encode()), 'application/x-ndjson')})
    unsupported = client.post('/api/v1/upload', files={'file': ('events.txt', io.BytesIO(b'not supported'), 'text/plain')})

    assert csv_response.status_code == 200
    assert csv_response.json()['accepted'] == 1
    assert jsonl_response.status_code == 200
    assert jsonl_response.json()['accepted'] == 1
    assert unsupported.status_code == 415
    assert unsupported.json()['error']['code'] == 'UNSUPPORTED_FORMAT'
    assert client.get('/api/v1/status').json()['status'] == 'FILE-BASED'

def test_file_event_reaches_sqlite_backed_websocket_replay(client):
    event = {
        'id': 'file-stream-1', 'source_id': 'file-stream', 'type': 'environment',
        'timestamp': '2026-01-01T00:00:00Z', 'received_at': '2026-01-01T00:00:01Z',
        'raw_ref': 'file://stream-1', 'payload': {'rainfall_mm': 5},
    }
    response = client.post('/api/v1/upload', files={'file': ('events.jsonl', io.BytesIO((json.dumps(event) + '\n').encode()), 'application/x-ndjson')})
    assert response.status_code == 200
    with client.websocket_connect('/ws/stream?since=0') as websocket:
        assert websocket.receive_json()['type'] == 'status'
        replayed = websocket.receive_json()
        assert replayed['data']['id'] == 'file-stream-1'
        assert replayed['status']['status'] == 'FILE-BASED'

def test_sqlite_persistence_survives_state_restart(tmp_path, monkeypatch):
    database = tmp_path / 'persistent.db'
    monkeypatch.setenv('SENTINAL_DB_PATH', str(database))
    first = State()
    event = {
        'id': 'persistent-1', 'source_id': 'persistent-source', 'type': 'telemetry',
        'timestamp': '2026-01-01T00:00:00Z', 'received_at': '2026-01-01T00:00:01Z',
        'raw_ref': 'test://persistent-1', 'payload': {'seq': 1},
    }
    import asyncio
    assert asyncio.run(first.publish_event(event))
    first.persistence.close()

    second = State()
    try:
        assert any(item['id'] == 'persistent-1' for item in second.events)
        assert second.ingestion_status()['status'] == 'OFFLINE'
    finally:
        second.persistence.close()


def test_chat_api_is_evidence_only(client):
    response = client.post(
        '/api/v1/chat',
        json={'question': 'What changed?'},
    )
    assert response.status_code == 200
    assert response.json()['intent'] == 'what_changed'
    assert response.json()['answer'] == 'Missing current scenario satellite data: a satellite event with payload.before and payload.after is required.'


def test_chat_api_runs_change_analysis_from_current_satellite_event(client):
    event = {
        'id': 'chat-satellite-1',
        'source_id': 'chat-satellite',
        'type': 'satellite',
        'timestamp': '2026-01-01T00:00:00Z',
        'received_at': '2026-01-01T00:00:01Z',
        'raw_ref': 'satellite://chat-1',
        'payload': {
            'before': [[0, 0], [0, 0]],
            'after': [[0, 0], [0, 1]],
            'threshold': 0.5,
        },
    }
    assert client.post('/api/v1/ingest', json=event).json()['accepted'] == 1

    assert client.post('/api/v1/chat', json={'question': 'What changed?'}).json() == {
        'intent': 'what_changed',
        'answer': 'Detected 25.0% mean change; 25.0% of valid pixels crossed the change threshold.',
        'evidence': {
            'percent_change': 25.0,
            'changed_fraction': 0.25,
            'confidence': 1.0,
            'hotspots': [{
                'region_id': 'hotspot_1',
                'size': 1,
                'severity': 1.0,
                'mean_score': 1.0,
                'bounds': [1, 1, 2, 2],
                'pixels': [{'row': 1, 'col': 1}],
            }],
            'warnings': [],
        },
    }
    assert client.post('/api/v1/chat', json={'question': 'How much changed?'}).json()['answer'] == \
        '25.0% mean change was measured across the analyzed area.'
    assert client.post('/api/v1/chat', json={'question': 'Where is the worst area?'}).json()['answer'] == \
        'Worst area: hotspot_1 with 1 changed pixels and severity 1.000.'


def test_chat_api_reads_real_alert_explanation_for_flag_question(client):
    alert = {
        'id': 'chat-alert-1',
        'asset_id': 'asset_port_01',
        'level': 'high',
        'risk_score': 75.0,
        'status': 'New',
        'explanation': {
            'why': ['environment score 100.0 exceeded the flood threshold'],
            'confidence': 0.9,
            'factors': {'environment': 100.0},
            'evidence': [{'type': 'event', 'ref': 'event-1'}],
        },
    }
    client.app.state.store.alerts.append(alert)

    assert client.post('/api/v1/chat', json={
        'question': 'Why was this flagged?',
        'alert_id': 'chat-alert-1',
    }).json() == {
        'intent': 'why_flagged',
        'answer': 'Flag reason: environment score 100.0 exceeded the flood threshold.',
        'evidence': {
            'confidence': 0.9,
            'factors': {'environment': 100.0},
            'evidence': [{'type': 'event', 'ref': 'event-1'}],
        },
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
        assert websocket.receive_json()['type'] == 'status'
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

def test_local_telemetry_model_training_route(tmp_path, client):
    training = tmp_path / 'training.jsonl'
    training.write_text('\n'.join(json.dumps({'value': index}) for index in range(24)), encoding='utf-8')
    artifact = tmp_path / 'model.json'
    response = client.post('/api/v1/ml/telemetry/train', json={
        'file_path': str(training), 'artifact_path': str(artifact), 'min_samples': 8,
    })

    assert response.status_code == 200
    assert response.json()['status'] == 'unvalidated'
    assert artifact.exists()


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
