from collections import deque
from contextlib import asynccontextmanager
from uuid import uuid4
from typing import Any
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sentinal.risk.engine import RiskEngine
from sentinal.modules.telemetry.rules import TelemetryValidator
from sentinal.ingestion.synthetic_generator import SyntheticGenerator
from sentinal.core.storage import RuntimeStore
from sentinal.core.pipeline import EventPipeline
from .errors import ApiError, api_error_handler, validation_error_handler
from .routes_core import router as core_router
from .routes_risk import router as risk_router
from .routes_telemetry import router as telemetry_router
from .routes_satellite import router as satellite_router
from .routes_alerts import router as alerts_router
from .routes_chat import router as chat_router
from .routes_ml import router as ml_router
from .websocket import router as ws_router

class State:
    def __init__(self):
        self.risk, self.telemetry, self.synthetic = RiskEngine(), TelemetryValidator(), SyntheticGenerator()
        self.config = {'version': '1', 'limits': {'upload_bytes': 5_000_000}}
        self.persistence = RuntimeStore()
        self.pipeline = EventPipeline(self)
        self.config.update(self.persistence.load_config())
        self.events = deque(self.persistence.events(), maxlen=500)
        self.alerts = self.persistence.alerts()
        self.metrics = {'ingested': 0, 'duplicates': 0, 'validation_errors': 0, 'alerts': len(self.alerts)}
        self.websocket_clients: set[Any] = set()
        self.ingestion = {'status': 'OFFLINE', 'source': 'none', 'provenance': '', 'last_successful_ingestion': None, 'freshness_seconds': None, 'errors': []}

    def ingestion_status(self):
        status = self.ingestion['status']
        if not self.ingestion['last_successful_ingestion'] and not self.events:
            status = 'OFFLINE'
        freshness = self.ingestion.get('freshness_seconds')
        last = self.ingestion.get('last_successful_ingestion')
        if last:
            try:
                parsed = datetime.fromisoformat(last.replace('Z', '+00:00'))
                freshness = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
            except ValueError:
                freshness = None
        return {**self.ingestion, 'status': status, 'freshness_seconds': freshness, 'event_count': len(self.events), 'metrics': dict(self.metrics)}

    def record_ingestion(self, *, status, source, provenance='', errors=None, accepted=0):
        now = datetime.now(timezone.utc)
        if accepted:
            self.ingestion.update({'status': status, 'source': source, 'provenance': provenance,
                'last_successful_ingestion': now.isoformat(), 'freshness_seconds': 0})
        elif errors:
            self.ingestion['status'] = 'DEGRADED' if self.ingestion.get('last_successful_ingestion') else 'OFFLINE'
        self.ingestion['errors'] = errors or []

    def append_events(self, items):
        accepted = duplicates = 0
        for item in items:
            accepted_now, duplicate = self.persistence.append_events([item])
            if accepted_now:
                self.events.append(item)
                accepted += accepted_now
            duplicates += duplicate
        self.metrics['ingested'] += accepted
        self.metrics['duplicates'] += duplicates
        return accepted, duplicates

    def save_alert(self, alert):
        self.persistence.save_alert(alert)
        self.metrics['alerts'] = len(self.alerts)

    async def broadcast(self, event: dict) -> None:
        stale = []
        for client in tuple(self.websocket_clients):
            try:
                await client.send_json({'type': 'event', 'cursor': len(self.events) - 1, 'data': event, 'status': self.ingestion_status()})
            except Exception:
                stale.append(client)
        for client in stale:
            self.websocket_clients.discard(client)

    async def publish_event(self, event: dict) -> bool:
        from sentinal.core.schemas import Event

        canonical = Event.model_validate(event)
        accepted, duplicate = self.append_events([canonical.model_dump(mode="json")])
        if duplicate or not accepted:
            return False
        published = await self.pipeline.publish(canonical)
        if published:
            await self.broadcast(canonical.model_dump(mode="json"))
        return published

@asynccontextmanager
async def lifespan(application):
    yield
    application.state.store.persistence.close()

app = FastAPI(title='SENTINAL API', version='1.0', lifespan=lifespan)
app.state.store = State()
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
for router in (core_router, risk_router, telemetry_router, satellite_router, alerts_router, chat_router, ml_router, ws_router): app.include_router(router, prefix='/api/v1' if router is not ws_router else '')

@app.get('/health')
def root_health(request: Request):
    """Compatibility health check for local tools and browser monitors."""
    return {
        'status': 'ok',
        'version': '1.0',
        'events': len(request.app.state.store.events),
    }

@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", str(uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    return response

@app.get('/api/mission')
def mission(request: Request):
    """Return a compact dashboard payload from the current in-memory state."""
    store = request.app.state.store
    alerts = store.alerts[-3:]
    if alerts:
        dashboard_alerts = [
            [alert.get("level", "WATCH").upper(), alert.get("asset_id", "Unknown asset"), alert.get("status", "New"), alert.get("id")]
            for alert in reversed(alerts)
        ]
        risk = round(float(alerts[-1].get("risk_score", 0)))
    else:
        dashboard_alerts = []
        risk = 0
    return {
        'risk': risk,
        'alerts': dashboard_alerts,
        'telemetry': [f'events buffered: {len(store.events)}', f'alerts tracked: {len(store.alerts)}', f'validation errors: {store.metrics["validation_errors"]}'],
        'diagnostics': store.ingestion_status(),
    }

web_dist = Path(__file__).parents[1] / 'web' / 'dist'
if web_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount('/', StaticFiles(directory=web_dist, html=True), name='dashboard')
