from collections import deque
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sentinal.risk.engine import RiskEngine
from sentinal.modules.telemetry.rules import TelemetryValidator
from sentinal.ingestion.synthetic_generator import SyntheticGenerator
from .errors import ApiError, api_error_handler, validation_error_handler
from .routes_core import router as core_router
from .routes_risk import router as risk_router
from .routes_telemetry import router as telemetry_router
from .routes_satellite import router as satellite_router
from .routes_alerts import router as alerts_router
from .websocket import router as ws_router

class State:
    def __init__(self):
        self.risk, self.telemetry, self.synthetic = RiskEngine(), TelemetryValidator(), SyntheticGenerator()
        self.config = {'version': '1', 'limits': {'upload_bytes': 5_000_000}}
        self.events = deque(maxlen=500)
        self.alerts = []

app = FastAPI(title='SENTINAL API', version='1.0')
app.state.store = State()
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
for router in (core_router, risk_router, telemetry_router, satellite_router, alerts_router, ws_router): app.include_router(router, prefix='/api/v1' if router is not ws_router else '')

@app.get('/api/mission')
def mission(request: Request):
    """Small dashboard payload; the UI also has an offline fallback."""
    store = request.app.state.store
    return {
        'risk': 72,
        'alerts': [['CRITICAL', 'Power bus variance', 'SAT-04 · 2 min ago'],
                   ['HIGH', 'Thermal trend rising', 'NODE-17 · 8 min ago'],
                   ['WATCH', 'Link latency elevated', 'GROUND-02 · 14 min ago']],
        'telemetry': [f'events buffered: {len(store.events)}', 'synthetic feed available'],
    }

web_dist = Path(__file__).parents[1] / 'web' / 'dist'
if web_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount('/', StaticFiles(directory=web_dist, html=True), name='dashboard')
