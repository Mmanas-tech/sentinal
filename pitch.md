# SENTINAL — Audit-Ready Pitch

## One sentence

**SENTINAL turns raw multi-source signals into an evidence-grounded risk decision without hiding missing data or inventing facts.**

## The problem

Operators must combine telemetry, satellite observations, weather, cyber indicators, and asset dependencies across separate tools. Existing alert surfaces often show a score without the reasoning chain. That creates alert fatigue and makes it difficult to distinguish a genuine anomaly from bad data, stale data, or a source outage.

## What is real in this repository

- Canonical Event validation and SQLite persistence
- Deterministic synthetic demo scenarios for safe repeatability
- CSV/JSONL/NDJSON file ingestion with provenance and rejection details
- A real Open-Meteo weather adapter that was called successfully in this environment
- Rule-based telemetry, cyber, environment, risk, correlation, cascade, and alert processing
- A local Isolation Forest artifact pipeline that does not claim accuracy without labels
- Real optional GeoTIFF processing with Rasterio-generated fixture tests
- Evidence-specific risk provenance and why-not comparisons
- FastAPI, WebSocket, React dashboard, reports, exports, replay, and audit helpers

## What is deliberately not claimed

- No classified data
- No autonomous control
- No military activity classification from imagery
- No live satellite catalog or operational cyber feed
- No production ML accuracy without representative labels
- No HA or production identity/security certification

## Three-minute judge demo

1. Run `make dev` and open `http://127.0.0.1:8000/`.
2. Launch `flood` and show the dashboard label `DEMO`, not `LIVE`.
3. Show the alert explanation: score, factors, event evidence, provenance, confidence, data gaps, and next steps.
4. Point out that the telemetry validator detects all seven planted fault classes and quarantines bad packets.
5. Upload a CSV or JSONL file and show `FILE-BASED`, accepted/rejected counts, and provenance.
6. Call the Open-Meteo source route with coordinates if network is available; show `LIVE` only after the provider responds.
7. Submit a GeoTIFF pair through the satellite change route in an environment with Rasterio; show CRS/grid/NoData checks and georeferenced hotspots.
8. Ask “How much changed?” or “Why was this flagged?” and point out that the response uses returned analysis/evidence only.
9. Close with the phrase: **“The score tells the operator priority; the evidence tells the operator whether to trust it.”**

## Technical differentiators

### Explainability is enforced

Module results require non-empty reasons. Explanation snapshots preserve the inputs and provenance at alert time. Generic why-not is replaced by actual score/threshold/factor comparisons where data exists; missing evidence returns an explicit limitation.

### Missing data is visible

`OFFLINE`, `DEGRADED`, `FILE-BASED`, `DEMO`, and `LIVE` are separate states. A failed provider is not converted to synthetic data and presented as live.

### Real functionality is bounded honestly

The Open-Meteo adapter is real and testable. GeoTIFF processing is real when Rasterio is installed. The numeric satellite path remains explicitly synthetic/test-oriented. The ML pipeline can train and persist a model but reports `unvalidated` without labels.

### Modules are swappable

Adapters emit Events. Detectors emit structured results. Risk consumes factors. Explainability consumes structured risk. A future STAC, MQTT, SIEM, or model-registry integration can replace a boundary without rewriting the risk formula.

## Proof

```text
python -m pytest -q sentinal/tests
104 passed, 1 skipped

npm --prefix sentinal/web run build
success

python -m sentinal.demo
all four scenarios complete; all planted telemetry faults detected
```

## Likely judge questions

### Is this just synthetic data?

The demo scenarios are synthetic by design and clearly labeled `DEMO`. The repository also contains real local file adapters, a live-smoke-tested Open-Meteo provider adapter, a user-supplied telemetry ML artifact pipeline, and actual GeoTIFF processing. The system never claims synthetic output is operational truth.

### What happens when a source is unavailable?

The adapter returns `OFFLINE` or `DEGRADED`, records the error, and the risk explanation exposes the data gap. No arbitrary score is silently substituted.

### Does the ML model have real accuracy?

Not claimed. The model pipeline accepts user-supplied data and produces evaluation metrics only when labels are supplied. Without labels it returns `unvalidated`.

### Why not use an LLM for everything?

Numbers and facts must come from analysis functions. The current chat router is deterministic and evidence-only. An LLM can be added later as a rewording layer, not as an authority for measurements or tool execution.

### Can it process real satellite imagery?

Yes for local GeoTIFFs when Rasterio is installed: CRS, bands, dimensions, NoData, acquisition metadata, grid alignment, change masks, and georeferenced hotspots are processed. There is no claim of live catalog access or threat classification.

## Closing

SENTINAL is not a red-number dashboard. It is a trust layer between raw signals and human judgment. It makes the priority, the evidence, the uncertainty, and the next investigation step visible—while being explicit about what is real, what is synthetic, and what still requires deployment data or credentials.
