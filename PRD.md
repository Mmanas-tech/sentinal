# SENTINAL Product Requirements Document

**Status:** as-built product requirements and upgrade baseline
**Safety:** SENTINAL is decision support, not an autonomous command, targeting, or control system. All synthetic results require qualified human verification.

## 1. Executive summary

SENTINAL turns heterogeneous space-and-defence signals into a validated, traceable decision-support result. The platform accepts canonical events from REST, local JSON/CSV/JSONL/NDJSON files, deterministic demo scenarios, a documented Open-Meteo weather adapter, and generic HTTP/NDJSON boundaries. Events are validated, persisted in local SQLite, processed by independently swappable modules, combined by the risk engine, and exposed through explanation snapshots, alerts, REST, WebSocket, reports, exports, and a React dashboard.

The key product invariant is:

> Every accepted detector result and every alert must explain what happened, why it matters, what evidence supports it, what data is missing, how confident the system is, and what the next investigation step is.

This repository contains a working local prototype. It does not claim operational satellite intelligence, classified data handling, production identity, HA, or validated real-world ML performance.

## 2. Problem statement

Operators receive telemetry, imagery, environmental observations, cyber indicators, and asset reports in separate systems. Manual cross-checking is slow and error-prone. An unexplained score creates alert fatigue; a clean-looking score can hide stale, missing, or conflicting data.

SENTINAL addresses the trust gap between raw signals and human decisions by providing validation, correlation, prioritization, provenance, and explanation in one workflow.

## 3. Users

| Persona | Need | SENTINAL surface |
|---|---|---|
| Analyst | Investigate evidence and change | Satellite functions, chat, explanation cards, exports |
| Mission controller | Detect bad or suspicious telemetry | Validator, quarantine, health, WebSocket |
| Commander | Prioritize assets and zones | Risk gauge, ranking, confidence, reports |
| Responder | Act on clear next steps | Alerts, playbooks, plain-language explanations |
| Integrator | Replace synthetic modules safely | Canonical Event/ModuleResult contracts and adapters |

## 4. Goals and non-goals

### Goals

- Normalize diverse inputs into canonical UTC/WGS84 events.
- Reject malformed, duplicate, stale, invalid, or unsupported inputs safely.
- Detect rule violations and statistical anomalies without conflating them.
- Combine telemetry, satellite, cyber, and environment factors through the configured risk formula.
- Preserve event/source/timestamp provenance through risk and explanation outputs.
- Make missing data, conflicts, confidence, and limitations visible.
- Provide deterministic offline scenarios and real local file/GeoTIFF/provider paths.
- Keep adapters and detectors replaceable without rewriting the risk core.

### Non-goals in this release

- Autonomous command or control.
- Military activity, object, threat, or attribution classification from imagery.
- Production identity, tenant isolation, HA, TLS, compliance, or classified-data handling.
- Claiming operational ML precision/recall without a representative labeled dataset.
- Claiming a failed or unconfigured provider is LIVE.

## 5. Current built solution

```text
source/file/provider
        ↓
adapter + validation + provenance
        ↓
canonical Event → SQLite → EventBus
        ↓
telemetry / satellite / cyber / environment modules
        ↓
factor scores + source status + event provenance
        ↓
RiskEngine: weights + importance + correlation + cascade + hysteresis
        ↓
ExplanationCard + Alert workflow
        ↓
FastAPI / WebSocket / React / PDF / CSV / GeoJSON / replay
```

The runtime store is local SQLite through `sentinal/core/storage.py`. The bounded in-memory view, EventBus, risk history, hysteresis, and WebSocket clients remain process-local.

## 6. Requirements and status

| ID | Requirement | Status |
|---|---|---|
| REQ-001 | Canonical UTC/WGS84 Event with raw reference and metadata | Implemented and tested |
| REQ-002 | Module result with score, label, reasons, evidence, confidence, timestamp | Implemented and tested |
| REQ-003 | Seeded flood, wildfire, satellite fault, cyber attack scenarios | Implemented and tested |
| REQ-004 | Seven planted telemetry fault classes | Implemented and tested |
| REQ-005 | CSV, JSONL, NDJSON file adapters with row/line errors | Implemented and tested |
| REQ-006 | Generic HTTP and HTTP NDJSON adapter boundaries | Implemented; provider configuration required |
| REQ-007 | Real public weather adapter | Open-Meteo implemented and live-smoke verified |
| REQ-008 | Deterministic telemetry rules, quarantine, command validation | Implemented and tested |
| REQ-009 | Local Isolation Forest artifact training/inference/evaluation | Implemented; unvalidated without labels |
| REQ-010 | Risk formula, gaps, conflicts, provenance, what-if, hysteresis | Implemented and tested |
| REQ-011 | Evidence-grounded explanation and why-not | Implemented for stored factor data; UI linking partial |
| REQ-012 | Numeric satellite change/indices/hotspots | Implemented as TEST/DEMO mode |
| REQ-013 | Real GeoTIFF change pipeline | Optional Rasterio implementation and fixture tests |
| REQ-014 | Cyber/environment rule analyzers and correlation | Implemented for supplied payloads |
| REQ-015 | Alert workflow, audit, replay, reports, exports | Implemented locally; operational delivery partial |
| REQ-016 | API and WebSocket status/provenance | Implemented locally; broker/HA partial |
| REQ-017 | React mission-control UI | Implemented local shell; full map/control coverage partial |

## 7. Canonical contracts

### Event

```json
{
  "id": "evt-001",
  "source_id": "source-1",
  "type": "telemetry",
  "timestamp": "2026-01-01T00:00:00Z",
  "received_at": "2026-01-01T00:00:01Z",
  "geo": {"lat": 51.05, "lon": 13.74},
  "payload": {},
  "schema_version": "1.0",
  "raw_ref": "source://evt-001",
  "metadata": {"source_status": "FILE-BASED"}
}
```

Timestamps must be timezone-aware and are normalized to UTC. Geo is WGS84. Events are deduplicated by `(source_id, id)`.

### ModuleResult

```json
{
  "module": "telemetry_validator",
  "signal_id": "sig-001",
  "score": 0.82,
  "label": "high",
  "reasons": [{"code": "OUT_OF_RANGE", "detail": "battery_v=999"}],
  "evidence": [{"type": "event", "ref": "evt-001"}],
  "confidence": 0.8,
  "timestamp": "2026-01-01T00:00:01Z"
}
```

The contract rejects missing reasons, out-of-range score/confidence, naive timestamps, and unexpected fields.

## 8. Domain requirements

### Ingestion

Adapters must validate input, attach source/provenance/raw references, preserve UTC timestamps, report errors, detect duplicates, and expose one of `LIVE`, `FILE-BASED`, `DEMO`, `DEGRADED`, or `OFFLINE`. A provider failure must not silently become synthetic data.

### Telemetry

Rules cover required/null fields, types, ranges, units, unknown fields, sequence duplicates/gaps/out-of-order, rollover, session/boot reset, late/stale data, clock drift, sudden jumps, quarantine, and incident grouping. Isolation Forest is explicit and artifact-backed; evaluation is `unvalidated` unless labels are supplied.

### Risk

```text
Base = Σ(weight_i × factor_i)
Risk = min(100, Base × (0.5 + 0.5 × importance / 100)
          + correlation_boost + cascade_boost)
```

Risk outputs include contributions, event/source/timestamp provenance, weights version, confidence, data gaps, conflicts, trend, and hysteresis state.

### Explainability

Cards are snapshots. They include alert identity, what, why, factors, score contributions, evidence, provenance, confidence, data gaps, next steps, recommendation rationale, and weights version. Why-not uses stored score/factor/threshold evidence and returns `insufficient-evidence` when evidence is absent.

### Satellite

Numeric arrays are labeled TEST/DEMO. Real GeoTIFF processing is optional and validates CRS, dimensions, bands, NoData, acquisition tags, grid alignment, and provenance before producing georeferenced masks/hotspots. It does not classify military activity.

## 9. API surface

The API is under `/api/v1` and uses `{ "error": { "code", "message", "details" } }` for structured errors. Important paths include:

- `POST /ingest`, `POST /ingest/{type}`
- `POST /upload`
- `POST /sources/open-meteo`
- `POST /scenarios/{name}/run`
- `POST /telemetry/validate`
- `POST /ml/telemetry/analyze`, `POST /ml/telemetry/train`
- `GET /risk/assets`, `POST /risk/whatif`
- `POST /satellite/change`, `GET/POST /satellite/query`
- `POST /satellite/change-upload` for two GeoTIFF uploads when Rasterio is installed
- `POST /chat`
- `GET /alerts`, `PATCH /alerts/{id}`
- `GET /alerts/{id}/explanation`, `GET /alerts/{id}/why-not/{zone}`
- `GET /status`, `GET /diagnostics`, `GET /health`, `GET /ready`, `GET /metrics`
- `GET /export/csv`, `GET /export/geojson`, `GET /reports/{incident_id}`
- WebSocket `/ws/stream`

## 10. Testing and acceptance

The current workspace verifies:

- `104 passed, 1 skipped` with `python -m pytest -q sentinal/tests`.
- Vite frontend production build succeeds.
- The offline demo runs all four scenarios and detects all planted telemetry faults.
- Open-Meteo returned one normalized LIVE event in the direct provider smoke test.
- Rasterio-generated GeoTIFF fixtures verify NoData, CRS/grid alignment, provenance, and georeferenced hotspots.

The release does not claim operational accuracy, provider uptime, HA recovery, or production security.

## 11. Roadmap

1. Add approved Sentinel/Landsat/STAC/FIRMS and telemetry/SIEM adapters with credentials and licensing.
2. Add MQTT/Kafka/Redis transport with broker auth, replay, backpressure, and multi-worker fan-out.
3. Add representative labeled telemetry/raster datasets, calibration, model registry, drift monitoring, and independent evaluation.
4. Add PostGIS, migrations, retention, RBAC/identity, TLS, audit retention, backups, HA, and observability.
5. Add live map overlays, cloud masks, tile caching, richer geospatial QA, and operator usability/accessibility validation.
