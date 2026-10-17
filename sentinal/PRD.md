# SENTINAL Product Requirements Document

**Status:** as-built requirements and roadmap baseline
**Scope:** the inspected workspace
**Safety position:** SENTINAL is decision support, not an autonomous control system. Qualified operators verify outputs before acting.

**Companion documents:** [`README.md`](README.md) contains setup and operations instructions; [`pitch.md`](pitch.md) contains the judge-facing story and demo script.

## 1. Executive summary

SENTINAL is an offline-first Python/FastAPI prototype that turns synthetic space/defence telemetry and related environmental, satellite, and cyber observations into validated signals, explainable asset risk, alerts, and reports. It demonstrates a deterministic walkthrough across four scenarios and seven intentionally planted telemetry faults. The implementation is local, configuration-driven, and deliberately safe to demonstrate: it has an in-process event bus, a bounded in-memory view backed by local SQLite, and no live external feeds.

This document distinguishes verified workspace behavior from the original aspirational roadmap. **Implemented** means supported by code and tests; **Partial** means a scaffold, placeholder, or optional path; **Future** means proposed work only.

## 2. Problem statement

Operators need to triage heterogeneous observations without losing provenance or trusting an opaque score. Raw packets may be malformed, late, stale, duplicated, or inconsistent; sources may conflict; and a high score without reasons is not actionable. SENTINAL normalizes events, validates telemetry, combines factors with explicit weights and dependency/correlation boosts, exposes confidence and data gaps, and provides recommended next steps. Synthetic fixtures make behavior reproducible and prevent the demo from implying operational truth.

## 3. Users and personas

| Persona | Need | Workspace outcome |
|---|---|---|
| Mission/operations analyst | Identify what changed, severity, and reason quickly | Risk ranking, alert workflow, explanation, replay |
| Telemetry engineer | Find packet-quality and command faults | Stateful validator, seven faults, health metrics |
| Intelligence/environment analyst | Correlate environmental, satellite, and cyber evidence | Rule analyzers and risk factors |
| Incident lead | Track, assign, resolve, and export an incident | Alert transitions and offline reports |
| Developer/integrator | Replace synthetic sources safely | Canonical contracts and YAML configuration |
| Demo/evaluation reviewer | Verify repeatability and safety | Offline demo, deterministic seeds, tests |

## 4. Goals and non-goals

### Goals
1. Provide a reproducible offline multi-source decision-support demonstration.
2. Reject malformed canonical data and expose telemetry quality findings.
3. Produce bounded, explainable risk with confidence, evidence, conflicts, and gaps.
4. Keep module boundaries and configuration stable for later adapters.
5. Provide local API, WebSocket, dashboard shell, alert, replay, and report paths.

### Non-goals in this workspace
- Autonomous command, targeting, actuation, evacuation, or mission control.
- Real-time operational accuracy or replacement of qualified judgment.
- PostgreSQL/PostGIS persistence, a multi-tenant service, or production identity/security.
- Operational satellite, telemetry, or cyber feeds; live map tiles; or production identity/security.
- Production-grade forecasting/ML, HA deployment, model governance, or compliance certification.

## 5. Current built solution

Verified code and tests cover: Python package setup; Pydantic schemas; YAML loading and weight validation; deterministic `SyntheticGenerator`; `flood`, `wildfire`, `satellite_fault`, and `cyber_attack`; seven named faults; telemetry and command validation; rolling z-score and optional Isolation Forest interfaces; health tracking; satellite change masks/indices/hotspots; cyber and environment analyzers; weighted risk with asset importance, correlation, dependency cascade, confidence, data gaps, trend, hysteresis, and what-if; explanation/playbooks; alert grouping/workflow/replay/audit helpers; FastAPI routes and WebSocket; React/Vite dashboard assets; CSV, GeoJSON, and ReportLab PDF exports; chat intent routing; and the offline demo.

Runtime state uses a bounded in-memory view backed by a local SQLite store for events, alerts, findings, quarantine, module results, audit entries, and configuration snapshots. CSV/JSONL/NDJSON file adapters and a real Open-Meteo weather adapter now feed canonical events. The optional Rasterio path processes actual GeoTIFFs; numeric satellite arrays remain explicitly demo/test mode. `/api/mission` exposes current buffered state and diagnostics. Optional bearer authentication/roles, correlation IDs, readiness, metrics, source status, and bounded WebSocket validation are available. There is no operational satellite feed, HA deployment, production identity provider, or complete compliance hardening.

## 6. User journeys

### 6.1 Demonstrate a scenario
Run `python -m sentinal.demo`; generate a seeded profile, optionally with `plant_anomalies=["all"]`; validate packets; analyze side-channel events; evaluate asset risk; build an explanation card; create an alert; and export/report results.

### 6.2 Triage an alert
Open the local dashboard or alert API; inspect level, label, reasons, evidence, confidence, trend, and gaps; assign/acknowledge/resolve or mark false positive; follow playbook next steps; export a report. The operator remains accountable.

### 6.3 Investigate telemetry
Submit a packet or raw JSON; inspect every finding and highest level; use `LATE`, `STALE`, `GAP`, and `DUPLICATE` tags; quarantine bad data and replay after correction.

### 6.4 Explore risk
Request ranked assets or `/risk/whatif`; compare factor contributions, correlation/cascade boosts, confidence, and source status. Counterfactuals must not mutate score history or hysteresis state.

## 7. Functional requirements and status

| ID | Requirement | Status |
|---|---|---|
| FR-001 | Accept canonical UTC events with typed geography, payload, schema version, raw reference, and metadata. | Implemented |
| FR-002 | Reject naive timestamps, invalid coordinates/polygons, and extra fields. | Implemented |
| FR-003 | Deduplicate publication per `(source_id,event.id)` in an async in-process bus. | Implemented |
| FR-004 | Generate deterministic seeded scenario streams from YAML. | Implemented |
| FR-005 | Plant and report seven telemetry fault types. | Implemented |
| FR-006 | Validate fields, types, ranges, units, sequence, lateness, staleness, jumps, and statistical findings. | Implemented |
| FR-007 | Validate commands against configured IDs, senders, and parameters. | Implemented |
| FR-008 | Enforce a fixed module result with at least one reason. | Implemented |
| FR-009 | Analyze telemetry, environment, cyber, and satellite-derived inputs. | Implemented for synthetic/local inputs; Open-Meteo and optional GeoTIFF paths are implemented, while operational imagery/catalogs remain future |
| FR-010 | Compute configurable, explainable asset risk. | Implemented |
| FR-011 | Treat missing/unknown factors as gaps and redistribute active weights. | Implemented |
| FR-012 | Apply correlation, dependency cascade, importance, and hysteresis. | Implemented |
| FR-013 | Provide non-mutating what-if and ranked assets. | Implemented |
| FR-014 | Build plain/technical explanation cards with evidence, confidence, and playbooks. | Implemented |
| FR-015 | Group/rate-limit and transition alerts; retain false-positive feedback. | Implemented in memory |
| FR-016 | Expose versioned API, consistent errors, bounded WebSocket backfill, and health. | Implemented; hardening partial |
| FR-017 | Serve a local dashboard and mission summary. | Implemented local summary and connected scenario/chat workflows; map and some operator controls remain partial |
| FR-018 | Export CSV, GeoJSON, PDF; replay timelines and what-if adapters. | Implemented offline |
| FR-019 | Route bounded chat intents without an LLM dependency. | Implemented rule-based |
| FR-020 | Ingest real feeds, process real imagery, provide live tiles, durable storage, and external notifications. | Partial: local SQLite, file adapters, generic HTTP/NDJSON, Open-Meteo, and optional GeoTIFF exist; operational feeds, live tiles, broker streaming, and guaranteed external delivery remain future |
| FR-021 | Add production auth/RBAC, tenant isolation, encryption/key management, HA, and compliance. | Partial foundation: opt-in local auth/roles and correlation/diagnostics exist; enterprise identity, isolation, encryption, HA, and compliance are future |

## 8. Architecture and module boundaries

Intended flow: `sources -> ingestion/normalizer -> contracts -> event bus -> detectors -> risk -> explainability -> alerts/API/dashboard/reports`. Current execution is local and directly connected through typed API boundaries, a durable local runtime store, and an in-process event bus. File adapters, generic HTTP/NDJSON, and Open-Meteo are real integration seams; no broker-backed distributed deployment exists.

- `core`: Pydantic schemas, contracts, YAML loader, event bus.
- `ingestion`: synthetic generator, CSV/JSONL adapters, generic HTTP/NDJSON boundary, and Open-Meteo provider adapter.
- `modules/telemetry`: packet/command rules, statistics, health.
- `modules/satellite`: numeric change detection, indices, hotspots, and optional Rasterio GeoTIFF alignment/change processing.
- `modules/cyber`, `environment`: rule-based analyzers.
- `risk`: factor normalization, weighted engine, correlation, cascade, hysteresis.
- `explain`: cards, confidence, templates, playbooks.
- `alerts`: workflow, grouping, notifier, audit/replay helpers.
- `api`: FastAPI routes, durable local runtime state, errors, WebSocket.
- `reports`: offline serializers/exporters.
- `chat`: deterministic intent router.
- `web`: Vite/React dashboard build.
- `config`: versioned YAML policy and fixture data.

Modules consume `Event` (or documented mappings) and emit `ModuleResult`; they do not own risk policy, UI state, or transport credentials. Risk owns score semantics, explanation owns presentation, and API owns transport/errors.

## 9. Canonical contracts

### 9.1 Event

```json
{
  "id": "stable-id",
  "source_id": "source-1",
  "type": "telemetry",
  "timestamp": "2026-01-01T00:00:00Z",
  "received_at": "2026-01-01T00:00:01Z",
  "geo": {"lat": 35.0, "lon": -100.0},
  "payload": {},
  "schema_version": "1.0",
  "raw_ref": "synthetic://stable-id",
  "metadata": {}
}
```
`id`, `source_id`, `type`, `raw_ref`, and schema version are non-empty. Timestamps must be timezone-aware and normalized to UTC. `geo` is a validated WGS84 `GeoPoint`, validated minimal GeoJSON `Polygon`, or null. Payload and metadata are mappings.

### 9.2 ModuleResult

```json
{
  "module": "telemetry",
  "signal_id": "battery-range",
  "score": 0.82,
  "label": "high",
  "reasons": [{"code": "OUT_OF_RANGE", "detail": "battery_v=999"}],
  "evidence": [{"type": "event", "ref": "stable-id", "detail": "packet"}],
  "confidence": 0.9,
  "timestamp": "2026-01-01T00:00:01Z"
}
```
Scores and confidence are 0–1; reasons are required; evidence is structured and may be empty; timestamp is UTC; unknown fields are rejected. `validate_module_result` is the contract gate.

## 10. Data and configuration model

YAML files are the source of current policy: `schemas.yaml` (event/packet fields, units, limits, sequence/lateness/staleness), `weights.yaml` (factor weights, versions, correlation/cascade policies), `thresholds.yaml` (risk bands, hysteresis and detector limits), `playbooks.yaml` (next steps), `assets.yaml` (four synthetic WGS84 assets and dependencies), and `scenarios.yaml` (four profiles, cadence, baseline, noise/drift, faults). `load_config` validates the bundle and risk weights sum to the configured target.

The risk engine keeps process-local history and hysteresis. Events, alerts, findings, quarantine records, module results, audit entries, and configuration snapshots are durable in SQLite; process-local risk history, EventBus state, and WebSocket clients are not. Timestamps are UTC; coordinates are WGS84/EPSG:4326. Synthetic values are test fixtures, not operational data.

## 11. Domain requirements

### 11.1 Synthetic scenarios and planted faults

The generator emits one telemetry event per requested sample plus a profile-specific side event. Supported scenarios are `flood`, `wildfire`, `satellite_fault`, and `cyber_attack`. `count` is packet count, seed controls repeatability, and `noise`/`drift` are configurable. `plant_anomalies=["all"]` plants one each of:

1. `missing_field` (configured `temp_c` removed)
2. `out_of_range` (`battery_v=999`)
3. `wrong_type` (`temp_c` becomes non-numeric)
4. `duplicate_sequence`
5. `gap_out_of_order` (sequence jump and timestamp offset)
6. `stale_data` (timestamp aged by 180 seconds)
7. `sudden_jump` (temperature delta)

The result records event ID, index, and fault type. Unknown faults, duplicate selections, non-positive counts, and invalid numeric parameters are rejected.

### 11.2 Telemetry and command validation

The validator must report all findings, highest level (`OK`, `WARN`, `ERROR`, `CRITICAL`), tags, quarantine decision, and incident grouping. It tracks source state for sequence rollover, resets, packet latency, bursts, replay safety, stale data, gaps, duplicates, and jumps. Optional rolling z-score and disabled-by-default Isolation Forest use the shared detector interface. Health covers power, thermal, communications, packet loss, and latency.

### 11.3 Satellite

Numeric utilities and local API routes calculate difference masks, spectral indices, land-cover classification, and ranked hotspots from supplied numeric arrays. The optional Rasterio pipeline accepts actual GeoTIFF paths/bytes, validates CRS/dimensions/bands/NoData/acquisition metadata, aligns grids, masks invalid pixels, and emits georeferenced hotspot geometries plus provenance. Rasterio is optional and missing dependency returns `UNAVAILABLE`; STAC/catalog/cloud service/live tile integration remains future.

### 11.4 Environment

Environment analysis consumes supplied mappings and rule thresholds, with optional station/satellite hooks. The Open-Meteo adapter provides a real public weather path that normalizes hourly forecast observations into canonical events and reports `LIVE` only after a successful response. Additional station history, provider licensing, and operational weather validation remain future.

### 11.5 Cyber

Cyber analysis consumes supplied indicators such as protocol, source IP, failed logins, and packets/sec and returns rule-based severity/evidence. It is not a network sensor, IDS, packet capture, attribution engine, or production security boundary. Trusted scanners and live SIEM integrations are future.

### 11.6 Risk and cascade

Risk combines configured normalized factors (currently four configured factors) with active-weight redistribution, asset importance, source correlation, dependency cascade, and hysteresis. It returns exact score, level, label, factor contributions/scores, reasons, evidence, confidence, data gaps, conflicts, boosts, trend, hysteresis state, source status, and `weights_version`. Asset registry rejects missing dependencies and cycles. `what_if` is side-effect free.

### 11.7 Explainability

Every alert/result must be readable in plain mode and support a technical mode. Cards include what happened, why, score/level, confidence, evidence references, data gaps/conflicts, trend, and playbook next steps. “Why not” responses explain insufficient evidence or threshold failure. Templates are rule-based; there is no claim of LLM-generated factual grounding.

### 11.8 Alerts

Alerts have ID, asset, level, state, assignee, explanation/card-derived content, and feedback. Workflow supports transitions, assignment, resolution, and false-positive marking. Grouping/rate limiting is process-local. Telegram is optional injected transport; production email/SMS/webhooks and durable alert history are future.

### 11.9 API and WebSocket

Implemented route families include `/api/v1/health`, `/api/v1/status`, diagnostics, ingest, named scenarios, CSV/JSON/JSONL upload, Open-Meteo source fetch, config, event export, incident report, telemetry validation, ML train/analyze, risk assets/what-if, alerts/explanation/why-not/update, satellite query/change, and `/ws/stream`. Errors use `{ "error": { "code", "message", "details" } }`; FastAPI validation is handled centrally. WebSocket clients can request bounded backfill and receive in-process new-event broadcasts. Authentication, rate limiting, API version migration policy, broker fan-out, and durable pagination are not production-complete.

### 11.10 Dashboard

The local React/Vite build is served when `web/dist` exists. It presents current mission summary, risk, alerts, telemetry, scenario launch, and evidence-only chat. It is not a live operational map; live map tiles, full interaction coverage, and accessibility audit remain work.

### 11.11 Reports and exports

CSV and GeoJSON use standard-library serializers; PDF uses ReportLab; timeline replay sorts events in UTC and supports a what-if adapter. Exports are local and do not enforce role permissions because roles do not exist. Retention, redaction, signed reports, and archival storage are future.

## 12. Reliability, security, accessibility, and observability

### Reliability requirements
- Deterministic seed and configuration version must reproduce a run.
- Invalid input must fail at a boundary without crashing unrelated processing.
- Module failures should be isolated and surfaced as data gaps in a future orchestrator.
- Health must report service status and buffered counts.
- Current limitation: local SQLite persistence exists, but no queue, retry, HA, or backpressure system exists.

### Security requirements
- Validate all API inputs and file sizes/types; never execute uploaded content.
- Keep secrets out of source and use environment/vault integration when transports are enabled.
- Preserve source references and audit changes where available.
- Current limitation: opt-in local bearer auth/roles exist, but there is no enterprise identity, tenant isolation, TLS deployment, encryption/key management, dependency policy, or complete threat model. Synthetic demo data must not be treated as classified/operational data.

### Accessibility and usability
- Plain-language explanation by default; technical detail on demand.
- Never encode severity by color alone; provide text/icons and keyboard-accessible controls.
- Target WCAG AA contrast and an alert readable in under ten seconds.
- Current limitation: no verified WCAG audit or end-user study.

### Observability
- Preserve correlation/event IDs in logs and evidence.
- Measure ingest rate, queue/buffer depth, module latency, alert counts, validation findings, and false-positive feedback.
- Current workspace provides health/readiness, correlation IDs, and local counters but no structured logging pipeline, metrics backend, tracing, or ops page.

## 13. Edge cases

Naive or non-UTC timestamps; invalid latitude/longitude; open/invalid polygon rings; unknown scenario/fault; duplicate fault request; count smaller than requested faults; non-finite/negative noise or interval; wrong packet JSON/type; missing required fields; out-of-range and unit mismatch; sequence rollover/reset; duplicate, gap, out-of-order, stale, late, or sudden-jump packets; duplicate event publication; unknown asset/factor; missing/offline factors; conflicting sources; dependency cycle/missing dependency; empty reasons/evidence; score/confidence outside bounds; what-if accidentally mutating history; malformed config/weights; oversized upload; missing WebSocket client; empty alert/report query; and process restart loss must all have deterministic validation or an explicit documented degraded response.

## 14. Testing and validation

The repository contains focused tests for API, core contracts/bus, cyber/environment, explainability/alerts, phase polish, reports/replay, risk, satellite/chat, synthetic generation, and telemetry. The standard check is `python -m pytest -q sentinal/tests` (also `make test`); the offline walkthrough is `python -m sentinal.demo`.

Required validation includes: unit coverage for every validator rule and seven faults; canonical schema/contract rejection tests; deterministic seed golden outputs; risk weight-sum, boundary, missing-factor, correlation, cascade, hysteresis, and non-mutating what-if tests; explanation schema checks; scenario end-to-end expected alerts; API error and upload-limit tests; report parseability; malformed/injection-like input tests; and dashboard smoke/accessibility checks. Load replay, chaos/recovery, real imagery IoU, security penetration, and user comprehension testing are acceptance gates for later phases, not evidence that the current prototype has passed them.

## 15. Acceptance criteria

### Current prototype acceptance
- All four scenarios run offline with a fixed seed.
- `plant_anomalies=["all"]` produces one recorded instance of each seven faults and validation identifies them.
- Canonical events reject invalid time/geo/extra-field input.
- Every accepted module result has at least one reason and valid bounds.
- Risk output contains score, level, factor contributions, reasons, confidence, evidence/gaps, source status, and weights version.
- What-if does not change history or hysteresis.
- Explanation cards contain what/why/evidence/next steps and can render plain text.
- Alert transitions, exports, replay, API health, and the local demo complete without network credentials.
- `pytest` suite passes; documentation distinguishes local SQLite/file/provider paths from operational feeds, live tiles, production security, and unvalidated ML performance.

### Future production acceptance
- Real-feed provenance and outage behavior are demonstrated.
- Durable storage, RBAC, audit retention, TLS, rate limits, backup/restore, HA, and threat review are independently verified.
- Imagery QA/ground truth, performance SLOs, accessibility audit, and operator usability evidence are recorded.

## 16. Demo success metrics

For the current demo: complete all four scenarios in under three minutes on a developer workstation; zero network/API credentials; deterministic output for a fixed seed; seven of seven planted faults detected; every displayed alert has reasons and evidence or an explicit gap; risk and what-if are reproducible; and the full test suite passes. These are engineering/demo metrics, not operational accuracy or false-positive claims.

## 17. Current limitations and verified gaps

- Local SQLite persistence exists for events, alerts, findings, quarantine, module results, audit, and config snapshots; PostgreSQL/PostGIS/TimescaleDB do not.
- A real public Open-Meteo weather adapter and generic HTTP/NDJSON boundaries exist; no operational satellite catalog, live cyber/SIEM feed, broker transport, or live map tile contract exists.
- Real GeoTIFF processing exists behind optional Rasterio with local fixture coverage; satellite catalogs, cloud services, imagery licensing, and operational imagery QA are not implemented.
- Dashboard map, reports navigation, and some operator controls remain incomplete.
- Risk history/hysteresis, EventBus state, and WebSocket clients are process-local; durable alert/event tables exist in SQLite but retention and migrations are incomplete.
- No production authentication, RBAC, tenant boundaries, TLS deployment, secrets vault, encryption, or compliance evidence.
- Telegram is optional/no-op without injected configuration; no guaranteed delivery.
- Local Isolation Forest training/save/load/inference and labeled/unlabeled evaluation paths exist, but no representative operational dataset, calibration, model registry, or validated production performance claim exists.
- No HA queue, retry/dead-letter handling, durable metrics/tracing, or formal SLOs.
- Synthetic results must not be used as operational decisions or control inputs.

## 18. Future roadmap

| Phase | Scope | Status |
|---|---|---|
| Prototype/polish | Synthetic scenarios, contracts, telemetry, risk, explanation, alerts, API/dashboard shell, reports, replay, chat | Built in workspace |
| Pilot | Real public Sentinel/FIRMS/weather feeds, imagery pipeline, Postgres/PostGIS, auth/RBAC, notifications, calibrated statistical detectors | Future |
| Product | Kafka/queue, STAC catalog, model registry, CNN/LSTM/forecasting, multi-tenant cloud, offline/mobile modes, multilingual UX | Future |
| Operational | HA, external command-system integrations, governance, compliance, human-in-the-loop review, audited SLOs | Future |

Roadmap items must not be presented as current capability until code, tests, operational configuration, and evidence land in this workspace.

## 19. Integration points

Current integration seams are canonical `Event` and `ModuleResult`, YAML configuration, FastAPI JSON routes, WebSocket stream, synthetic adapter, optional station/satellite hooks in environment analysis, optional trusted scanners in cyber analysis, injected Telegram transport, CSV/GeoJSON/PDF exporters, and replay/what-if callbacks. Planned integrations include CCSDS/custom telemetry, Sentinel-2/FIRMS/STAC, weather/station APIs, SIEM/SOC feeds, Postgres/PostGIS/TimescaleDB, Kafka/Redis, identity providers, email/SMS/webhooks, map providers, model registries, and external command systems. Each must define provenance, auth, rate limits, outage/degraded mode, retention, and human approval boundaries.

## 20. Open questions

1. Which real public and operational feeds, formats, licensing, and provenance rules are required?
2. Which imagery QA, cloud-cover, AOI, and ground-truth standards define acceptable change detection?
3. Which identity provider, roles, tenant model, retention, and audit policy apply?
4. What latency, availability, replay, and recovery SLOs are needed?
5. Which alert channels and delivery guarantees are authorized?
6. Who owns factor calibration, false-positive review, and model/version approval?
7. What is the approved boundary between decision support and any external command system?
8. Which map provider and offline tile strategy are acceptable?
9. Which data classifications and redaction rules govern exports and reports?
10. What operator research defines alert comprehension and accessibility success?

## 21. Definition of done for the current release

The offline demo, tests, and local API/dashboard run from documented commands; all current requirements marked Implemented are exercised; seven planted telemetry faults are visible in results; explanations retain reasons and provenance; the safety positioning is visible; and documentation clearly labels placeholders, in-memory behavior, synthetic data, and roadmap work.

> **Positioning line:** SENTINAL does not replace experts. It helps them decide faster, with clear reasons.
