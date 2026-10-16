import pytest
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
