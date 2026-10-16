# SENTINAL

SENTINAL is a decision-support platform for space and defence intelligence. **Phase 12 is complete:** the repository contains the core contracts, deterministic synthetic scenarios, telemetry/command validation, risk analysis, explainability, alerts, API/WebSocket, dashboard shell, satellite/chat analysis, cyber/environment modules, reports, exports, replay, and an offline demo.

## Architecture

The intended flow is `sources -> ingestion -> normalizer -> event bus -> modules -> signal store -> risk engine -> explainability -> API/dashboard`. Modules are independent detectors for satellite, telemetry, cyber, and environment data. Rules and configuration are external so later implementations can replace rule-based detectors with ML without changing their interfaces.

Every detector accepts a canonical `Event` and returns the module contract: `module`, `signal_id`, `score` (0–1), `label`, `reasons[]`, `evidence[]`, `confidence`, and UTC `timestamp`. The contract rejects any result without at least one reason; evidence is always represented as a structured list and may be empty when a detector has no external reference yet. Risk combines normalized factors using `weights.yaml`, applies asset importance, correlation, and cascade boosts, then maps the result to the configured level. Playbooks provide the next steps for an explanation card.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -r sentinal/requirements.txt
```

The current implementation is intentionally offline-first and synthetic. No external API keys or network services are needed for the demo or local dashboard.

## Commands

```bash
make test
make dev
```

`make test` runs `python -m pytest -q sentinal/tests`. `make dev` installs/builds the frontend and runs `python -m uvicorn api.main:app --reload --app-dir sentinal`, serving the dashboard at <http://127.0.0.1:8000/>.

## Configuration

- `sentinal/config/schemas.yaml` — canonical event and telemetry packet fields, types, units, ranges, sequence, lateness, and staleness rules.
- `sentinal/config/weights.yaml` — normalized risk-factor weights (sum 1.0), confidence and correlation/cascade policies.
- `sentinal/config/thresholds.yaml` — risk bands, hysteresis, telemetry limits, and synthetic hazard/cyber thresholds.
- `sentinal/config/playbooks.yaml` — alert-level and alert-type next-step recommendations.
- `sentinal/config/assets.yaml` — small synthetic asset registry with WGS84 coordinates, importance, and dependencies.
- `sentinal/config/scenarios.yaml` — scenario profiles, event cadence, baseline telemetry, noise/drift, and planted fault values.

`sentinal.core.config_loader.load_config()` reads the complete configuration directory into a bundle keyed by filename and validates that the risk factors in `weights.yaml` are finite, non-negative, and sum to the configured target.

All timestamps are UTC and coordinates are WGS84 (`EPSG:4326`). Values are synthetic and suitable for validator/risk-engine fixtures, not operational decisions or real asset control.

## Synthetic scenarios

The generator emits one telemetry packet per requested sample plus a matching scenario-specific event when configured:

```python
from sentinal.ingestion import SyntheticGenerator

generator = SyntheticGenerator()
result = generator.generate(
    "flood",
    count=24,
    seed=7,
    plant_anomalies=["all"],
)

print(len(result.events))
print(result.planted_anomalies)
```

Supported scenarios are `flood`, `wildfire`, `satellite_fault`, and `cyber_attack`. The seven supported telemetry faults are `missing_field`, `out_of_range`, `wrong_type`, `duplicate_sequence`, `gap_out_of_order`, `stale_data`, and `sudden_jump`. Use an explicit list to plant only selected faults. `count` refers to telemetry packets, so a scenario with one side-channel profile produces two events per sample.

## Telemetry validation

`sentinal.modules.telemetry.TelemetryValidator` consumes either a telemetry mapping, a canonical `Event`, or raw JSON through `validate_raw()`. It returns every finding for the packet, its highest level (`OK`, `WARN`, `ERROR`, or `CRITICAL`), tags such as `LATE`, `STALE`, `GAP`, and `DUPLICATE`, and a quarantine decision. Validation is stateful per source so sequence rollover, session/boot resets, sudden jumps, burst grouping, packet latency, and replay-safe command checks can be evaluated without a database.

The rolling z-score detector is enabled through its shared detector interface. `IsolationForestDetector` uses the same interface but is disabled by default in `sentinal/config/thresholds.yaml`; enabling it is an explicit configuration choice and underfit/ML errors do not stop rule validation. `CommandValidator` reads command IDs, sender allow-lists, and parameter constraints from `sentinal/config/schemas.yaml`. `HealthTracker` reports power, thermal, communications, packet-loss, and latency metrics.

## Risk engine

`sentinal.risk.RiskEngine` combines four 0–100 factors using the versioned weights in `sentinal/config/weights.yaml`, applies asset importance, correlation, and dependency cascade boosts, and returns a result with the exact score, level, factor contributions, confidence, reasons, evidence, conflicts, data gaps, trend, hysteresis state, and `weights_version`.

Offline or unknown factors are marked as data gaps and active weights are redistributed proportionally; they are never silently treated as zero-confidence healthy sources. `AssetRegistry` validates missing dependencies and cycles. `what_if()` evaluates a counterfactual without changing score history or hysteresis state, while `asset_ranking()` returns assets sorted by risk.

## API and operations

The versioned API includes ingest (`POST /api/v1/ingest/{type}`), scenario execution (`POST /api/v1/scenarios/{name}/run`), telemetry validation, risk assets/what-if, alert workflow, satellite query/change, config, GeoJSON export, PDF report download, and health. WebSocket clients connect to `/ws/stream` and can request bounded backfill. All API errors use `{ "error": { "code", "message", "details" } }`.

Reports and exports are offline: CSV/GeoJSON use the standard library, PDF uses ReportLab, and timeline replay sorts all events in UTC. Telegram notification is an optional injected transport and remains a no-op unless explicitly configured with environment variables.

## Phase 12 offline demo

The final polish includes a deterministic three-minute walkthrough of `flood`, `wildfire`, `satellite_fault`, and `cyber_attack`. It validates every planted telemetry fault, computes risk, builds a complete explanation card, and creates an alert using local modules only:

```bash
python -m sentinal.demo
python -m pytest -q sentinal/tests
```

No API keys, network, or external services are required. Optional packages such as `scikit-learn` (statistical detector), `fastapi`, and `uvicorn` support integrations but are not needed for the offline walkthrough. Synthetic outputs are decision-support fixtures, not operational advice or autonomous control.
