import pytest
import io
fastapi = pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from sentinal.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_and_ingest(client):
    assert client.get('/api/v1/health').json()['status'] == 'ok'
    out = client.post('/api/v1/ingest', json={'events': [{'id': 'x'}]})
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
    response = client.post(
        '/api/v1/upload',
        files={'file': ('events.json', io.BytesIO(b'{"events":[{"id":"uploaded-1","type":"satellite"}]}'), 'application/json')},
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
