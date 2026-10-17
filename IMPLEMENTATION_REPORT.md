# SENTINAL — Implementation Report

**Date:** 2026-10-17
**Scope:** Anti-mock audit follow-up and real/local integration upgrades
**Safety position:** This report distinguishes executable implementation from externally validated performance. Synthetic scenarios remain explicitly DEMO data.

## 1. Summary

SENTINAL was audited end to end and upgraded without replacing the existing architecture. The current runtime path remains:

```text
source/file/provider -> canonical Event -> SQLite + EventBus -> module pipeline
-> factor provenance -> RiskEngine -> explanation snapshot -> alert/API/WebSocket/UI
```

The highest-priority achievable gaps were implemented:

- CSV, JSONL, and NDJSON file ingestion
- Generic HTTP and HTTP NDJSON adapter boundaries
- Real Open-Meteo weather adapter
- Explicit source status and provenance reporting
- Local Isolation Forest training/artifact/inference/evaluation path
- GeoTIFF processing with optional Rasterio
- Risk contribution provenance and evidence-specific why-not responses
- Frontend DEMO/OFFLINE/degraded status behavior
- Additional integration and regression tests

No unavailable credentialed provider, live satellite catalog, labeled operational telemetry dataset, or broker deployment was invented.

## 2. Feature-by-feature result

| Feature | Previous status | New status | Evidence | Remaining blocker |
|---|---|---|---|---|
| Canonical event ingestion | JSON REST and synthetic events | **Implemented and verified** | Event validation, SQLite persistence, EventBus, pipeline tests | Production queue/backpressure and multi-worker fan-out. |
| CSV upload | Missing/unsupported | **Implemented and verified** | `CSVAdapter`, multipart API test, row errors/provenance | User-specific column mappings beyond canonical CSV schema. |
| JSONL/NDJSON upload | Missing | **Implemented and verified** | `JSONLAdapter`, parse/duplicate tests, upload API test | Chunked upload and durable dead-letter workflow. |
| Generic external HTTP source | Missing | **Implemented boundary** | `HTTPAdapter`, timeout/retry/auth/error tests | A user-approved provider URL/token is required for deployment. |
| Inbound streaming | Missing | **Implemented HTTP NDJSON boundary** | `HTTPStreamAdapter` canonical validation | MQTT/Kafka/Redis broker selection and deployment credentials. |
| Open-Meteo weather | Missing | **Real adapter implemented and live-smoke verified** | `OpenMeteoAdapter`; direct provider call returned `LIVE` and one Event | Forecast data is not an operational ground truth; rate/licensing policy must be confirmed. |
| Deterministic telemetry rules | Implemented | **Preserved and verified** | Existing telemetry suite plus pipeline tests | Rule-to-risk score semantics remain configuration/business-policy dependent. |
| Rolling z-score | Implemented | **Preserved and verified** | Telemetry tests | History is process-local. |
| Isolation Forest | Interface/underfit only | **Local artifact pipeline implemented** | Fit/save/load/checksum/inference and evaluation tests | No representative labeled operational dataset; unvalidated status is explicit. |
| Remote autoencoder | Optional remote path | **Optional, explicit, not operationally validated** | `/api/v1/ml/telemetry/analyze`; missing dependency/provider errors are explicit | TensorFlow/Hugging Face access and compatible model artifact. |
| Quarantine provenance | Event/finding only | **Extended** | SQLite model output/provenance columns and pipeline path | Review UI/API and retention policy. |
| Risk calculation | Formula implemented | **Evidence-driven provenance added** | Event/source/timestamp/weight/contribution/formula fields in `RiskResult` | Full event graph persistence and freshness policy across every module. |
| Explanations | Generic why-not/playbook fallback possible | **Deterministic evidence-grounded path** | Snapshot provenance, threshold comparison, recommendation rationale tests | More alert-type-specific playbook rules and UI evidence links. |
| Numeric satellite arrays | Implemented local | **Preserved and explicitly local** | Existing numeric API/tests | Not a real image source; remains TEST/DEMO. |
| GeoTIFF satellite processing | Missing | **Optional real implementation** | Rasterio-generated GeoTIFF tests for CRS, NoData, alignment, georeferenced hotspots | Rasterio installation, provider/catalog, cloud mask, and legally approved imagery. |
| Source status/UI | Synthetic/fallback status | **Backend-derived statuses added** | `/api/v1/status`, WebSocket status, dashboard labels | Full per-source registry and durable status history. |
| SQLite runtime | Existing | **Preserved and tested** | Persistence restart test; events/alerts/findings/quarantine/module results tables | Schema migration framework, retention, HA, and SQLAlchemy/PostGIS migration. |
| WebSocket | Local replay/broadcast | **Status-aware local broadcast** | WebSocket API test and status message | Multi-worker broker and durable cursor semantics. |
| Frontend | Mission dashboard shell | **Status/provenance/degraded fallback improved** | Vite build and source inspection | Full map overlays, loading/error component tests, and live provider visualization. |

## 3. Code changes

### Ingestion

- `sentinal/ingestion/adapters.py`
  - `IngestionAdapter`
  - `CSVAdapter`
  - `JSONLAdapter`
  - `HTTPAdapter`
  - `HTTPStreamAdapter`
  - `OpenMeteoAdapter`
- `sentinal/ingestion/__init__.py`
  - Exports synthetic generator and all adapter types without overwriting `__all__`.
- `sentinal/api/routes_core.py`
  - Routes supported file types through adapters.
  - Rejects unsupported extensions with `415 UNSUPPORTED_FORMAT`.
  - Adds Open-Meteo source ingestion route.
- `.env.example`
  - HTTP adapter, Open-Meteo override, auth, and SQLite settings.

### Telemetry ML

- `sentinal/modules/telemetry/stats.py`
  - Explicit `fit()` rather than retraining in every inference update.
  - Numeric feature extraction and conversion.
  - Median imputation.
  - Persisted artifact envelope with format/version/SHA-256/pickle payload.
  - Safe load failure and explicit disabled/unavailable/error statuses.
- `sentinal/ml/telemetry.py`
  - User-supplied CSV/JSONL loaders.
  - Labeled evaluation metrics: accuracy, precision, recall, confusion matrix.
  - `unvalidated` result when labels are absent.
- `sentinal/api/routes_ml.py`
  - Adds `/api/v1/ml/telemetry/train`.
- `sentinal/core/storage.py`
  - Stores model output and provenance in quarantine records.

### Geospatial processing

- `sentinal/modules/satellite/raster.py`
  - Optional Rasterio loading from local paths or bytes.
  - CRS, dimensions, bands, NoData, acquisition metadata, and bounds checks.
  - Reprojection/resampling to the before-image grid.
  - Valid-pixel masking, bounded relative change, changed fraction, confidence.
  - Pixel-region hotspot extraction with georeferenced polygon and center coordinates.
  - Explicit `UNAVAILABLE` when Rasterio is not installed.
- `sentinal/requirements-raster.txt`
  - Optional `rasterio>=1.3,<2` installation path.
- `sentinal/api/routes_satellite.py`
  - Supports `before_raster` and `after_raster` while preserving numeric-array API.

### Provenance and UI status

- `sentinal/risk/engine.py`
  - Adds structured per-factor provenance.
- `sentinal/core/pipeline.py`
  - Enriches evidence with event ID, source ID, UTC timestamp, and raw reference.
- `sentinal/explain/card_builder.py`
  - Snapshots provenance and recommendation rationale inputs.
- `sentinal/api/routes_alerts.py`
  - Evidence-specific why-not comparisons and insufficient-evidence results.
- `sentinal/api/main.py`
  - Ingestion status, freshness calculation, and mission diagnostics.
- `sentinal/api/websocket.py`
  - Initial status frame and status metadata on event/backfill frames.
- `sentinal/web/src/main.jsx`
  - Explicit DEMO fallback, status labels, provenance, freshness, and reconnect/degraded messaging.

## 4. External provider evidence

The documented Open-Meteo API was inspected before implementation. A direct smoke call was executed after implementation:

```text
OpenMeteoAdapter(timeout=20, retries=1).fetch_location(51.05, 13.74, forecast_hours=1)
status=LIVE events=1 errors=[]
payload={'temperature_c': 13.8, 'rainfall_mm': 0.0, 'wind_speed_mps': 1.35}
provider=Open-Meteo
```

This is evidence that the adapter can call the public provider from this environment. It is not a claim of availability, accuracy, or operational suitability for all deployments.

No credentialed external feed was configured. The generic HTTP adapter returns `OFFLINE`/`DEGRADED` with structured errors when not configured or unreachable.

The final regression result for this implementation is **104 passed, 1 skipped**; see `TEST_REPORT.md` for the exact commands and validation gaps.

## 5. Explicit non-claims

This implementation does **not** claim:

- Real-time Sentinel-2/Landsat/FIRMS or classified imagery ingestion
- Military activity/object/threat classification from satellite change
- Production-valid telemetry precision/recall without labeled data
- MQTT/Kafka/Redis deployment
- Production authentication, tenant isolation, TLS, HA, or compliance
- Operational weather truth from Open-Meteo forecast values
- Automatic commands, actuation, or autonomous decisions
