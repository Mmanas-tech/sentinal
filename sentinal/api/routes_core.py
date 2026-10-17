from fastapi import APIRouter, Request, UploadFile, File, Response, Depends
from sentinal.core.config_loader import load_config
from sentinal.reports.geojson_export import export_geojson
from sentinal.reports.csv_export import export_csv
from sentinal.reports.pdf_report import generate_pdf
from .errors import ApiError
from .security import require_role
from sentinal.ingestion import OpenMeteoAdapter
import os
router=APIRouter()
def store(r): return r.app.state.store
@router.get('/health')
def health(request: Request): return {'status':'ok','version':'1.0','events':len(store(request).events),'diagnostics':dict(store(request).metrics)}
@router.get('/ready')
def ready(request: Request):
    runtime = store(request)
    return {'status': 'ready', 'persistence': str(runtime.persistence.path), 'events': len(runtime.events)}
@router.get('/status')
def status(request: Request):
    return store(request).ingestion_status()
@router.get('/diagnostics')
def diagnostics(request: Request):
    return {'ingestion': store(request).ingestion_status(), 'metrics': dict(store(request).metrics)}
@router.get('/metrics')
def metrics(request: Request):
    return {'metrics': dict(store(request).metrics)}
async def _ingest(request: Request, event_type: str | None = None):
    body=await request.json()
    items=body if isinstance(body,list) else body.get('events', [body]) if isinstance(body,dict) else []
    if len(items)>500: raise ApiError('LIMIT_EXCEEDED','too many events',{'max':500},413)
    accepted=0; errors=[]
    for item in items:
        if not isinstance(item,dict): errors.append({'error':'event must be object'}); continue
        item = dict(item)
        if event_type:
            item.setdefault('type', event_type)
        try:
            from sentinal.core.schemas import Event
            event = Event.model_validate(item)
        except Exception as exc:
            store(request).metrics['validation_errors'] += 1
            errors.append({'error':'invalid canonical event','details':str(exc)})
            continue
        try:
            published = await store(request).publish_event(event.model_dump(mode="json"))
        except Exception as exc:
            raise ApiError("EVENT_PROCESSING_FAILED", str(exc)) from exc
        accepted += int(published)
        if not published:
            errors.append({'error':'duplicate event','id':event.id,'source_id':event.source_id})
    store(request).record_ingestion(status='LIVE', source='api', provenance='api://ingest', errors=errors, accepted=accepted)
    return {'accepted':accepted,'rejected':len(errors),'errors':errors,'duplicates':store(request).metrics['duplicates'], 'status': store(request).ingestion_status()}
@router.post('/ingest')
async def ingest(request: Request):
    return await _ingest(request)
@router.post('/ingest/{event_type}')
async def ingest_typed(event_type: str, request: Request):
    if event_type not in {'telemetry','satellite','cyber','environment'}:
        raise ApiError('INVALID_EVENT_TYPE', 'unsupported event type', {'type': event_type})
    return await _ingest(request, event_type)
@router.post('/scenarios/run')
async def run(request: Request, payload: dict):
    try: result=store(request).synthetic.generate(payload.get('scenario','flood'), payload.get('count'), payload.get('seed',0), payload.get('plant_anomalies'))
    except Exception as e: raise ApiError('SCENARIO_INVALID',str(e))
    for event in result.events:
        await store(request).publish_event(event.model_dump(mode="json"))
    store(request).record_ingestion(status='DEMO', source='synthetic-generator', provenance=f'synthetic://{result.scenario}', accepted=len(result.events))
    return result.model_dump(mode='json')
@router.post('/scenarios/{name}/run')
async def run_named(name: str, request: Request, payload: dict | None = None):
    values = dict(payload or {})
    values['scenario'] = name
    return await run(request, values)
@router.post('/upload')
async def upload(request: Request, file: UploadFile=File(...), _: str = Depends(require_role('admin', 'operator'))):
    data=await file.read(store(request).config['limits']['upload_bytes']+1)
    if len(data)>store(request).config['limits']['upload_bytes']: raise ApiError('LIMIT_EXCEEDED','upload too large',None,413)
    imported = 0
    if file.filename and file.filename.lower().endswith(".json"):
        import json
        try:
            decoded = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError("INVALID_UPLOAD", "JSON upload could not be parsed") from exc
        items = decoded if isinstance(decoded, list) else decoded.get("events", [decoded]) if isinstance(decoded, dict) else []
        if not items or not all(isinstance(item, dict) for item in items):
            raise ApiError("INVALID_UPLOAD", "JSON upload must contain an event object or events list")
        if len(items) > 500:
            raise ApiError("LIMIT_EXCEEDED", "too many events", {"max": 500}, 413)
        canonical = []
        from sentinal.core.schemas import Event
        for item in items:
            try:
                canonical.append(Event.model_validate(item).model_dump(mode='json'))
            except Exception as exc:
                raise ApiError("INVALID_UPLOAD", "upload contains an invalid canonical event", str(exc)) from exc
        upload_errors = []
        for event in canonical:
            if await store(request).publish_event(event):
                imported += 1
            else:
                upload_errors.append({'error': 'duplicate event', 'id': event['id'], 'source_id': event['source_id']})
        store(request).record_ingestion(status='FILE-BASED', source='upload', provenance=f'upload://{file.filename}', errors=upload_errors, accepted=imported)
        return {'status': 'partial' if upload_errors else 'accepted', 'filename': file.filename, 'bytes': len(data), 'accepted': imported,
                'rejected': len(upload_errors), 'imported_events': imported, 'errors': upload_errors,
                'provenance': f'upload://{file.filename}', 'diagnostics': store(request).ingestion_status()}
    elif file.filename and file.filename.lower().endswith((".csv", ".jsonl", ".ndjson")):
        import tempfile
        from pathlib import Path
        from sentinal.ingestion.adapters import CSVAdapter, JSONLAdapter
        suffix = Path(file.filename).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(data); temp_path = temp.name
        try:
            result = (CSVAdapter('upload').read(temp_path) if suffix == '.csv' else JSONLAdapter('upload').read(temp_path))
        finally:
            Path(temp_path).unlink(missing_ok=True)
        for event in result.events:
            await store(request).publish_event(event.model_dump(mode='json'))
        imported = len(result.events)
        errors = [error.__dict__ for error in result.errors]
        store(request).record_ingestion(status='FILE-BASED', source=result.source_id, provenance=result.provenance, errors=errors, accepted=imported)
        return {'status': 'partial' if errors else 'accepted', 'filename': file.filename, 'bytes': len(data), 'accepted': imported,
                'rejected': len(errors), 'imported_events': imported, 'errors': errors, 'provenance': result.provenance,
                'diagnostics': store(request).ingestion_status()}
    elif file.filename:
        raise ApiError('UNSUPPORTED_FORMAT', 'supported uploads are .json, .csv, .jsonl, and .ndjson', {'filename': file.filename}, 415)
    else:
        raise ApiError('INVALID_UPLOAD', 'filename is required')
    store(request).record_ingestion(status='FILE-BASED', source='upload', provenance=f'upload://{file.filename}', accepted=imported)
    return {'status':'accepted','filename':file.filename,'bytes':len(data),'imported_events':imported,'accepted': imported,'rejected': 0,'errors': [], 'provenance': f'upload://{file.filename}', 'diagnostics': store(request).ingestion_status()}

@router.post('/sources/open-meteo')
async def open_meteo(request: Request, payload: dict, _: str = Depends(require_role('admin', 'operator'))):
    try:
        latitude = float(payload['latitude'])
        longitude = float(payload['longitude'])
        forecast_hours = int(payload.get('forecast_hours', 1))
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError('INVALID_SOURCE_REQUEST', 'latitude and longitude are required numeric values', status_code=422) from exc
    adapter = OpenMeteoAdapter(endpoint=os.getenv('SENTINAL_OPEN_METEO_URL') or None)
    result = adapter.fetch_location(latitude, longitude, forecast_hours=forecast_hours)
    for event in result.events:
        await store(request).publish_event(event.model_dump(mode='json'))
    store(request).record_ingestion(status=result.status, source=result.source_id, provenance=result.provenance, errors=[error.__dict__ for error in result.errors], accepted=len(result.events))
    return {'accepted': len(result.events), 'rejected': len(result.errors), 'errors': [error.__dict__ for error in result.errors], 'status': store(request).ingestion_status()}
@router.get('/config')
def get_config(request: Request): return store(request).config
@router.put('/config')
def put_config(request: Request, payload: dict, _: str = Depends(require_role('admin'))):
    if not isinstance(payload,dict): raise ApiError('INVALID_CONFIG','config must be object')
    store(request).config.update(payload)
    for name, value in payload.items():
        store(request).persistence.save_config(name, value)
    return store(request).config

@router.get('/config/{config_type}')
def get_config_type(request: Request, config_type: str):
    try:
        bundle = load_config()
        if config_type not in bundle:
            raise KeyError(config_type)
        return bundle[config_type]
    except KeyError as exc:
        raise ApiError('CONFIG_NOT_FOUND', 'unknown configuration type', {'type': str(exc.args[0])}, 404)

@router.put('/config/{config_type}')
def put_config_type(request: Request, config_type: str, payload: dict, _: str = Depends(require_role('admin'))):
    if not isinstance(payload, dict):
        raise ApiError('INVALID_CONFIG', 'configuration must be an object')
    if config_type == 'weights':
        factors = payload.get('factors', payload.get('weights'))
        if not isinstance(factors, dict):
            raise ApiError('INVALID_CONFIG', 'weights requires a factors mapping')
        try:
            version = payload.get('version', f"api-{len(store(request).events)}")
            store(request).risk.update_weights(factors, version=version)
        except ValueError as exc:
            raise ApiError('INVALID_CONFIG', str(exc)) from exc
    store(request).config[config_type] = payload
    store(request).persistence.save_config(config_type, payload)
    return payload

@router.get('/export/geojson')
def export_events(request: Request):
    data = export_geojson(list(store(request).events))
    return Response(content=data, media_type='application/geo+json')

@router.get('/export/csv')
def export_events_csv(request: Request):
    data = export_csv(list(store(request).events))
    return Response(content=data, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="events.csv"'})

@router.get('/reports/{incident_id}')
def incident_report(request: Request, incident_id: str):
    records = [item for item in store(request).alerts if item.get('incident_id', item.get('id')) == incident_id]
    try:
        data = generate_pdf(records or [{'incident_id': incident_id, 'status': 'no stored alert records'}])
    except RuntimeError as exc:
        raise ApiError('REPORT_UNAVAILABLE', str(exc), {'incident_id': incident_id}, 503) from exc
    return Response(content=data, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{incident_id}.pdf"'})
