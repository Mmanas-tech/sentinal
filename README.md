# SENTINAL

**Synthetic, offline decision support for space and defence telemetry**

SENTINAL turns deterministic synthetic events into validated findings, explainable risk, alerts, reports, and a small local mission-control dashboard. It is an engineering prototype for testing operator workflows and module contracts; it is not a production command-and-control system.

> **Safety disclaimer:** All bundled data, locations, alerts, scores, and scenarios are synthetic. SENTINAL must not be used to direct spacecraft, weapons, emergency response, or other real-world operations. Treat every result as decision support and have qualified operators independently verify evidence before acting. Do not put classified, personal, or operationally sensitive data into this repository or its demo.

## Contents

- [What is implemented](#what-is-implemented)
- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Install and run](#install-and-run)
- [Offline demo](#offline-demo)
- [Tests and frontend build](#tests-and-frontend-build)
- [API](#api)
- [WebSocket stream](#websocket-stream)
- [Contracts](#contracts)
- [Configuration](#configuration)
- [Scenarios and seven faults](#scenarios-and-seven-faults)
- [Subsystem behavior](#subsystem-behavior)
- [Troubleshooting](#troubleshooting)
- [Deployment and limitations](#deployment-and-limitations)
- [Contributing](#contributing)
- [License](#license)

For the full product requirements and roadmap, read [`PRD.md`](PRD.md). For the judge narrative, live demo script, and prepared Q&A, read [`pitch.md`](pitch.md).

## What is implemented

The current prototype includes:

- Canonical timezone-aware `Event` and explainability-enforced `ModuleResult` models.
- Deterministic synthetic generation for `flood`, `wildfire`, `satellite_fault`, and `cyber_attack`.
- Telemetry validation for required fields, nulls, types, ranges, units, sequence gaps/duplicates, stale/late packets, clock drift, and sudden jumps; command validation and optional statistical detectors also exist in the telemetry package.
- Rule-based satellite change detection, connected-region hotspot ranking, NDVI/NDWI/NBR indices, land-cover labels, and evidence-only keyword chat routing.
- Cyber and environment analyzers, weighted risk, thresholds, correlation, dependency/cascade handling, hysteresis, data-gap reporting, and non-destructive what-if evaluation.
- Explanation cards with what/why/confidence/factors/evidence/next steps, alert state transitions, grouping, audit/replay helpers, CSV/GeoJSON/PDF exporters, and FastAPI routes.
- A React/Vite dashboard with backend-derived provenance/status labels and an explicitly labelled DEMO fallback when the API is unavailable.
- A local SQLite runtime store for events, alerts, audit entries, and configuration snapshots; set `SENTINAL_DB_PATH` to choose another database file.
- Optional bearer authentication and role checks for mutating operations. Set `SENTINAL_AUTH_REQUIRED=true` and `SENTINAL_API_TOKEN=...` to enable it; local development remains open by default.
- File adapters for canonical CSV, JSONL, and NDJSON uploads with row/line errors, provenance, duplicate detection, and `FILE-BASED` status.
- A generic authenticated HTTP/NDJSON stream boundary and a real Open-Meteo weather adapter. The Open-Meteo adapter reports `LIVE` only after a successful provider response; it never substitutes synthetic weather values.
- A local Isolation Forest artifact pipeline with feature extraction, median imputation, versioned/checksummed artifacts, and explicit `validated`/`unvalidated` evaluation status.
- An optional Rasterio GeoTIFF pipeline for CRS/dimension/band/NoData validation, grid alignment, georeferenced change masks, hotspot geometries, and provenance. Numeric arrays remain explicitly local demo/test mode.

Optional or future-facing pieces include additional provider-specific adapters, MQTT or broker-backed streaming, production identity/RBAC, queues/backpressure, durable model registry, labeled operational telemetry evaluation, and richer map overlays. The current system does not claim live satellite imagery, operational threat classification, or validated ML accuracy.

## Architecture

```text
synthetic files / REST events
          |
       ingestion -> canonical Event -> in-process EventBus
          |                         |
  telemetry | satellite | cyber | environment analyzers
          `------------ ModuleResult ----------------'
                              |
                   risk / correlation / cascade
                              |
                  explanation cards and alerts
                              |
              FastAPI REST + WebSocket -> React/Vite UI
                              |
                     CSV / GeoJSON / PDF exports
```

The API creates one runtime `State` containing the risk engine, telemetry validator, synthetic generator, a bounded event deque (500 items), alert state, ingestion diagnostics, and a SQLite-backed `RuntimeStore`. Events, alerts, findings, quarantine records, module results, audit entries, and config snapshots survive a process restart. The in-process EventBus, module outputs, and WebSocket client set are not multi-worker durable services.

## Repository layout

```text
.
├── Makefile                         # root dev/test orchestration
├── PRD.md                           # product requirements and roadmap
├── README.md                        # this guide
└── sentinal/
    ├── Makefile                     # package-local dev/test targets
    ├── requirements.txt             # pinned Python dependencies
    ├── demo.py                      # deterministic four-scenario offline demo
    ├── api/                         # FastAPI app, REST routers, errors, WebSocket
    ├── alerts/                      # alert workflow, grouping, audit, replay, notifier
    ├── chat/                        # keyword-first evidence-only question router
    ├── config/                      # YAML assets, schemas, scenarios, thresholds, weights, playbooks
    ├── core/                        # Pydantic contracts, config loader, event bus
    ├── explain/                     # cards, confidence, templates, playbooks, rendering
    ├── ingestion/                   # synthetic generator and CSV/JSONL/HTTP/provider adapters
    ├── modules/                     # telemetry, satellite, cyber, environment analyzers
    ├── reports/                     # CSV, GeoJSON, and PDF exporters
    ├── risk/                        # engine, correlation, cascade, hysteresis
    ├── tests/                       # pytest suite
    └── web/
        ├── package.json             # Vite/React scripts and dependencies
        ├── vite.config.js           # frontend build configuration
        ├── index.html                # dashboard entry document
        ├── src/                      # React app, provenance/status UI, fallback, styles
        └── dist/                    # generated static build (when present)
```

Important additional modules include `sentinal/core/storage.py` (SQLite runtime store), `sentinal/core/pipeline.py` (event-to-module-to-risk path), `sentinal/ingestion/adapters.py` (CSV/JSONL/HTTP/Open-Meteo boundaries), `sentinal/modules/satellite/raster.py` (optional real GeoTIFF processing), and `sentinal/ml/telemetry.py` plus `sentinal/modules/telemetry/stats.py` (user-supplied model training/evaluation).

## Prerequisites

- Python 3.11 or newer (the code uses modern typing and Pydantic v2).
- Node.js and npm for the dashboard build; the checked-in `package-lock.json` is used by npm.
- GNU Make for the one-command targets on Linux/macOS. Windows users can run the equivalent PowerShell commands below.
- No credentials, database, external API, or network service is required for the offline demo. `reportlab` is required for PDF reports and is pinned in `sentinal/requirements.txt`.
- Open-Meteo is a public weather provider and does not require a key for its normal public endpoint; network access is required for that adapter. The generic HTTP adapter uses `.env` configuration and an optional bearer token.
- Real GeoTIFF processing is optional: install `sentinal/requirements-raster.txt` in an environment with a compatible Rasterio/GDAL wheel.
- Real telemetry ML is optional and requires TensorFlow, Hugging Face Hub, and Kaggle tooling:
  ```powershell
   .\.venv\Scripts\python.exe -m pip install -r .\sentinal\requirements-ml.txt
  ```
  Configure Kaggle credentials using Kaggle's supported local configuration, never in source control. Keep downloaded datasets outside Git and set `SENTINAL_HF_TELEMETRY_MODEL` only when selecting a different compatible Keras model.

## Install and run

### Linux/macOS

From a clone's root:

```bash
git clone https://github.com/Mmanas-tech/sentinal.git
cd sentinal
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r sentinal/requirements.txt
cp .env.example .env  # reference only; export/set values in the shell that starts Uvicorn
```

Run the deterministic demo:

```bash
.venv/bin/python -m sentinal.demo
```

Real GeoTIFF change analysis is available through `sentinal.modules.satellite.raster` and
the `/api/v1/satellite/change` request fields `before_raster` and `after_raster` (local
 paths). Install Rasterio separately for this optional path:

```bash
python -m pip install -r sentinal/requirements-raster.txt
```

Without Rasterio the result is explicitly `UNAVAILABLE`; numeric `before`/`after`
arrays remain local demo/test mode.

Start the API and built dashboard in one command:

```bash
make dev
```

Open <http://127.0.0.1:8000/>. The root target installs `sentinal/web` dependencies, builds the dashboard, and runs Uvicorn with `--reload`, `--reload-dir sentinal`, and `--app-dir sentinal`. Restricting the reload directory prevents changes inside `.venv` dependencies from restarting the server.

### Windows PowerShell

```powershell
git clone https://github.com/Mmanas-tech/sentinal.git
Set-Location sentinal
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r sentinal\requirements.txt
Copy-Item .env.example .env  # reference only; set values in the PowerShell session
```

Run the demo and dashboard build/API with the exact equivalents:

```powershell
.\.venv\Scripts\python.exe -m sentinal.demo
npm --prefix sentinal/web install --no-audit --no-fund
npm --prefix sentinal/web run build
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --reload-dir sentinal --app-dir sentinal
```

If GNU Make is installed on Windows, `make dev` and `make test` are also available. PowerShell does not provide `make` by default.

## Offline demo

`python -m sentinal.demo` (or the venv path above) uses no network calls and runs four deterministic scenarios. It generates 14 telemetry packets per scenario, plants all seven faults, validates them, evaluates risk, builds an explanation, and creates an alert. A successful run ends with `Demo complete: all planted telemetry faults detected and all four scenarios evaluated.` The demo's four scenarios are `flood`, `wildfire`, `satellite_fault`, and `cyber_attack`.

## Tests and frontend build

From the repository root:

```bash
.venv/bin/python -m pytest -q sentinal/tests
# or
make test
```

The package Makefile runs the same pytest command. Build only the frontend with:

```bash
npm --prefix sentinal/web install --no-audit --no-fund
npm --prefix sentinal/web run build
```

The build writes the Vite output to `sentinal/web/dist`; FastAPI serves that directory when it exists. The frontend has a fallback payload if `/api/mission` is unavailable.

## Real telemetry ML (optional)

The local artifact path is the preferred reproducible implementation:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/ml/telemetry/train `
  -H "Content-Type: application/json" `
  -d "{\"file_path\":\"C:\\data\\telemetry.jsonl\",\"artifact_path\":\"C:\\data\\sentinal.iforest.json\",\"min_samples\":20}"
```

The input file must be user-supplied CSV/JSONL/NDJSON numeric records. If it has no `label` field, the response is explicitly `unvalidated`. With labels, the response includes accuracy, precision, recall, and a confusion matrix. The saved artifact contains the feature schema, imputation medians, version, provenance, and SHA-256 checksum.

The optional remote autoencoder path is deliberately narrow:

1. **Dataset:** NASA SMAP/MSL spacecraft telemetry anomaly benchmark. A Kaggle export may be used as a convenient mirror, but the NASA benchmark remains the provenance reference. The adapter accepts a numeric CSV or NPY matrix and does not commit downloaded data.
2. **Model:** Hugging Face `keras-io/timeseries-anomaly-detection`, a Keras autoencoder baseline. It is not claimed to be NASA-specific; SENTINAL returns its reconstruction errors and model name as evidence.
3. **Decision logic:** deterministic validation and the existing risk engine remain active. ML scores are not silently substituted for a risk factor.
4. **Credentials:** Kaggle credentials are read only from Kaggle's local configuration when you use its CLI/API. Never put `kaggle.json`, API keys, downloaded data, or model caches in Git.

Install the optional dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\sentinal\requirements-ml.txt
```

Then analyze a local export:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/ml/telemetry/analyze `
  -H "Content-Type: application/json" `
  -d "{\"file_path\":\"C:\\data\\smap\\channel_1.csv\",\"window\":24}"
```

Or send a small matrix directly:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/ml/telemetry/analyze `
  -H "Content-Type: application/json" `
  -d "{\"samples\":[[0.1,0.2],[0.2,0.2],[0.1,0.3]],\"window\":2}"
```

## API

The versioned REST base is `/api/v1`. The unversioned dashboard payload is `/api/mission`; the WebSocket is `/ws/stream`.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/mission` | Small dashboard payload; UI has an offline fallback. |
| GET | `/health` | Compatibility health check for local tools. |
| GET | `/api/v1/health` | Health, version, diagnostics, and buffered-event count. |
| GET | `/api/v1/ready` | Readiness and persistence status. |
| GET | `/api/v1/metrics` | Local runtime counters for ingestion, duplicates, validation errors, and alerts. |
| POST | `/api/v1/ingest` | Append one event, an `events` list, or a body list; max 500 items. |
| POST | `/api/v1/ingest/{event_type}` | Same ingest behavior with type defaulted to telemetry, satellite, cyber, or environment. |
| POST | `/api/v1/scenarios/run` | Generate and store a named synthetic scenario; accepts `scenario`, `count`, `seed`, `plant_anomalies`. |
| POST | `/api/v1/scenarios/{name}/run` | Named form of scenario execution. |
| POST | `/api/v1/upload` | Imports `.json`, `.csv`, `.jsonl`, and `.ndjson` through file adapters; returns accepted/rejected counts, errors, provenance, and source status. Other types return `415`. |
| POST | `/api/v1/sources/open-meteo` | Fetches documented Open-Meteo hourly weather data for WGS84 coordinates and runs it through the canonical event pipeline. |
| GET | `/api/v1/status` | Current source status (`LIVE`, `FILE-BASED`, `DEMO`, `DEGRADED`, or `OFFLINE`), provenance, freshness, and errors. |
| GET | `/api/v1/diagnostics` | Ingestion status plus runtime counters. |
| GET/PUT | `/api/v1/config` | Read/update in-memory API config. |
| GET/PUT | `/api/v1/config/{config_type}` | Read YAML bundle types or store a config payload; `weights` also updates the live risk engine. |
| POST | `/api/v1/telemetry/validate` | Validate one telemetry payload and return findings. |
| GET | `/api/v1/risk/assets` | Paginated in-memory risk asset registry. |
| POST | `/api/v1/risk/whatif` | Non-persistent risk what-if evaluation. |
| POST | `/api/v1/satellite/change` | Analyze 2D numeric `before`/`after` arrays with threshold, cloud-cover, AOI, hotspots, and an optional evidence-only chat question. |
| POST | `/api/v1/satellite/change-upload` | Process two uploaded GeoTIFF files with Rasterio when installed; otherwise returns explicit unavailable/refused status. |
| GET/POST | `/api/v1/satellite/query` | Query buffered synthetic satellite events with pagination and optional `source_id`/`scenario` filters. |
| POST | `/api/v1/chat` | Route a bounded evidence-only question through the local keyword intent router. |
| POST | `/api/v1/ml/telemetry/analyze` | Optional Hugging Face autoencoder scoring for a real numeric telemetry matrix; requires `requirements-ml.txt`. |
| POST | `/api/v1/ml/telemetry/train` | Trains and persists a local Isolation Forest from a user-supplied CSV/JSONL dataset; returns `validated` metrics only when labels are present. |
| GET | `/api/v1/alerts` | Paginated stored alerts. |
| GET | `/api/v1/alerts/explanation/{alert_id}` | Return the stored explanation snapshot for an alert. |
| GET | `/api/v1/alerts/{alert_id}/explanation` | Stored explanation snapshot, or unavailable/data-gap response. |
| GET | `/api/v1/alerts/{alert_id}/why-not` | Generic why-not response. |
| GET | `/api/v1/alerts/{alert_id}/why-not/{zone}` | Zone-specific generic why-not response. |
| PATCH | `/api/v1/alerts/{alert_id}` | Update stored status, assignee, or feedback. |
| GET | `/api/v1/export/geojson` | Export buffered events as GeoJSON. |
| GET | `/api/v1/export/csv` | Export buffered events as CSV. |
| GET | `/api/v1/reports/{incident_id}` | Generate a PDF report from matching stored alert records. |

FastAPI also exposes its normal documentation at `/docs` and `/openapi.json` while the server is running.

## WebSocket stream

Connect to `ws://127.0.0.1:8000/ws/stream`. On connection the server sends buffered events as JSON objects shaped like `{"type":"event","cursor": 0, "data": ..., "status": ...}`. An optional `?since=N` starts from the bounded replay list index `N`. After the initial replay, send `{"type":"backfill","limit":50}` to receive up to the last 500 buffered events. Newly accepted events are broadcast to connected clients in-process. This is not a multi-worker broker and cursors are bounded by the local SQLite/deque view.

## Contracts

### Canonical `Event`

```json
{
  "id": "evt_example",
  "source_id": "sensor-1",
  "type": "telemetry",
  "timestamp": "2026-01-01T00:00:00Z",
  "received_at": "2026-01-01T00:00:01Z",
  "geo": {"lat": 35.0, "lon": -100.0},
  "payload": {"seq": 1},
  "schema_version": "1.0",
  "raw_ref": "synthetic://evt_example",
  "metadata": {}
}
```

`timestamp` and `received_at` must be timezone-aware and are normalized to UTC. `geo` is a WGS84 point or closed polygon, and extra top-level fields are forbidden.

### Canonical `ModuleResult`

```json
{
  "module": "telemetry_validator",
  "signal_id": "sig_1",
  "score": 0.82,
  "label": "abnormal_value",
  "reasons": [{"code": "OUT_OF_RANGE", "detail": "battery_v=55"}],
  "evidence": [{"type": "packet", "ref": "pkt_1", "detail": null}],
  "confidence": 0.95,
  "timestamp": "2026-01-01T00:00:00Z"
}
```

Scores and confidence are in `[0, 1]`; reasons are required and each has a non-empty `code` and `detail`. Evidence entries have `type`, `ref`, and optional `detail`. The contract rejects extra fields and missing reasons.

## Configuration

All runtime YAML is under `sentinal/config/`:

- `schemas.yaml`: event/telemetry fields, units, ranges, sequence, stale/late, and command definitions.
- `scenarios.yaml`: four scenario profiles, deterministic defaults, locations, side-channel payloads, and fault parameters.
- `thresholds.yaml`: analyzer thresholds.
- `weights.yaml`: risk factor weights and version.
- `assets.yaml`: asset registry and dependencies/importance.
- `playbooks.yaml`: explanation next-step playbooks.

`GET /api/v1/config/{config_type}` reads the loaded YAML bundle. `PUT` updates are stored in the local SQLite config table and update the current process; they do not rewrite source YAML files and are not a production configuration registry.

## Scenarios and seven faults

`SyntheticGenerator.generate()` supports `plant_anomalies=["all"]` or a subset of:

1. `missing_field` → `MISSING_FIELD` (removes `temp_c`).
2. `out_of_range` → `OUT_OF_RANGE` (`battery_v=999.0`).
3. `wrong_type` → `WRONG_TYPE` (`temp_c` becomes text).
4. `duplicate_sequence` → duplicate sequence number.
5. `gap_out_of_order` → sequence jump plus a timestamp offset.
6. `stale_data` → timestamp aged by 180 seconds.
7. `sudden_jump` → `temp_c` increases by 40°C.

The generator also accepts `count`, `seed`, `noise`, and `drift`; invalid scenarios and invalid parameters raise structured errors in the API.

## Subsystem behavior

- **Telemetry:** distinguishes missing, null, zero, unknown fields, bad types, units, ranges, stale/late packets, sequence errors, jumps, and quarantine. Validation returns `OK`, `WARN`, `ERROR`, or `CRITICAL` with all findings.
- **Risk:** combines satellite, telemetry, cyber, and environment factors with configurable weights; levels are Low `<30`, Medium `30–<60`, High `60–<80`, Critical `≥80`. It reports confidence, data gaps, correlation/conflict, and dependency cascade effects. What-if evaluation does not save changes.
- **Explainability and alerts:** explanation cards expose what, why, confidence, factors, evidence, next steps, data gaps, and weight version. Alert transitions and false-positive feedback are implemented in Python; notification is optional and unconfigured offline.
- **Satellite:** numerical analysis functions and the change API implement pixel change fraction/percentage, cloud-confidence warnings, AOI/resolution refusal, connected hotspots, spectral indices, land-cover labels, and evidence-only chat.
- **Satellite real raster path:** `analyze_rasters()` reads GeoTIFFs with Rasterio when installed, validates CRS/bands/dimensions/NoData, aligns grids, emits georeferenced hotspot geometries, and returns source/parameter provenance. Missing Rasterio is an explicit `UNAVAILABLE` result.
- **Chat:** keyword-first intents are `what_changed`, `worst_area`, `how_much`, `compare_dates`, and `why_flagged`; unsupported or unavailable questions return safe evidence-only responses. It does not call an LLM.
- **Cyber/environment:** rule-based analyzers score synthetic payloads and return reasons/evidence; environment supports flood/wildfire-style fields and a failure-safe comparison hook.
- **Reports/replay:** Python helpers export CSV, GeoJSON, PDF, audit JSONL, and sorted/paged replay; the API currently exposes GeoJSON and incident PDF routes.
- **Frontend:** the React screen renders the current synthetic mission overview, filters alerts, launches scenarios, inspects explanation snapshots, acknowledges alerts, records false positives, links PDF reports, and uses the evidence-only chat API. The map and some navigation remain presentation-only.
- **Runtime foundation:** events, alerts, findings, quarantine records, module results, audit entries, and config snapshots use the local SQLite store; `/ready`, `/metrics`, `/status`, correlation IDs, optional bearer auth, and bounded WebSocket validation provide local operational hardening. This is not HA or a production identity system.

## Troubleshooting

- **`ModuleNotFoundError` or wrong Python:** activate/use `.venv` and run commands from the repository root; the Uvicorn command relies on `--app-dir sentinal`.
- **`npm`/Node errors:** install a current Node.js/npm, then rerun `npm --prefix sentinal/web install --no-audit --no-fund`.
- **Port 8000 is busy:** stop the other process or run Uvicorn with a different `--port`; update the URL accordingly.
- **Dashboard is missing:** run the frontend build; FastAPI serves `sentinal/web/dist` only when that directory exists.
- **PDF report unavailable:** confirm the pinned `reportlab` dependency installed successfully.
- **Unexpected empty alerts/events:** events and alerts are persisted in SQLite, but the WebSocket/UI view is bounded to 500 events. Check `SENTINAL_DB_PATH`, `/api/v1/ready`, and `/api/v1/status`; run a DEMO scenario or upload a FILE-BASED fixture first.
- **`UNAVAILABLE` raster response:** install `sentinal/requirements-raster.txt` and verify Rasterio imports in the same Python environment as Uvicorn. Do not interpret numeric-array mode as real imagery.
- **`DEGRADED` external source:** inspect the returned adapter error, URL, timeout, retry, and token configuration. No synthetic fallback is applied to a failed external adapter.
- **ML result says `unvalidated`:** labels were not supplied. This is expected and is not a real-world precision/recall claim.
- **A test mutates shared API state:** use a fresh process for manual API experiments; the application store is process-global.

## Deployment and limitations

This is a local prototype with a bounded production foundation. For any real deployment, add TLS, a production identity provider, tenant isolation, queue/back-pressure, multi-worker-safe state, secrets management/vault integration, retention controls, HA, provider-specific rate limits, model registry governance, and an independent safety review. Do not expose the development server or `--reload` configuration to an untrusted network. The Open-Meteo adapter is real but forecast data is not an operational ground truth; no live satellite imagery or operational threat classification is claimed.

## Contributing

Keep changes small and module-oriented. Preserve the canonical contracts, UTC/WGS84 rules, explainability requirement, deterministic synthetic behavior, and offline operation. Update the relevant YAML when changing thresholds, weights, schemas, assets, scenarios, or playbooks. Add focused pytest coverage for behavior changes, run `make test`, and run the frontend build when touching `sentinal/web`. Do not commit secrets, classified data, generated dependency trees, or real operational data.

## License

No license file is currently present in the repository. **License: to be determined by the project owner.**
