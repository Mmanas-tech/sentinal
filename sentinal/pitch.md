# SENTINAL — Judge Pitch

> **From raw signals to explained action.**

SENTINAL is an offline-first, synthetic-data decision-support platform for space and defence intelligence. It brings telemetry, satellite change, cyber indicators, environmental hazards, and asset dependencies into one mission-control workflow. Its defining rule is simple:

> **No alert is allowed to exist without a reason, an evidence field, confidence, and a next step.** If evidence is unavailable, the gap is shown explicitly rather than hidden.

This document contains the judge-facing story, the live demo script, the technical explanation, the proof points, and prepared answers to likely questions.

---

## 1. The 30-second pitch

Operators do not suffer from a lack of data. They suffer from disconnected data and alerts that say **what** happened but not **why**.

SENTINAL turns raw, noisy signals into one explainable decision. It validates telemetry, detects satellite change, scores cyber and environmental hazards, combines them into a risk score, correlates independent sources, accounts for asset importance and dependency cascades, and produces an explanation card with evidence and next steps.

The prototype runs offline on synthetic data, so the demo is repeatable and safe. In one command, a judge can launch four scenarios, see all seven planted telemetry fault classes detected, inspect a risk score, read why the alert exists, and follow the evidence trail.

**SENTINAL helps experts decide faster without pretending to replace them.**

---

## 2. The one-line positioning

**SENTINAL is the explainable intelligence layer between raw multi-source signals and a human decision.**

---

## 3. The problem

Mission operators may receive, at the same time:

- Telemetry packets from spacecraft, gateways, or infrastructure
- Before/after satellite imagery
- Weather and environmental measurements
- Cybersecurity logs and indicators
- Asset importance and dependency information
- Alerts from independent systems with different confidence levels

These signals are usually split across tools. The operator must manually answer:

1. Is this signal valid or corrupted?
2. Is it a real anomaly or normal variation?
3. Do other sources agree?
4. Which asset or zone matters most?
5. How severe is the combined risk?
6. What is the evidence?
7. What should happen next?

Traditional dashboards often expose a red number without the reasoning chain. That creates two dangerous outcomes:

- **Alert fatigue:** too many unexplained alerts are ignored.
- **False confidence:** one clean-looking score hides missing, stale, or conflicting data.

The problem is not only detection. It is **trustworthy, explainable prioritization under uncertainty**.

---

## 4. The solution

SENTINAL uses a pipeline:

```text
Raw signal
   ↓
Canonical event
   ↓
Validation and detector modules
   ↓
Normalized factor scores
   ↓
Correlation + asset importance + dependency cascade
   ↓
One risk score and level
   ↓
Explanation snapshot
   ↓
Alert workflow, dashboard, report, or chat answer
```

Every detector is replaceable because modules communicate through stable contracts. Rules are used first, while ML and real data can be added behind the same interfaces later.

The important output is not merely:

```text
Risk: 72
```

It is:

```text
Risk: 72 / High
Why: telemetry anomaly, environmental hazard, source agreement
Confidence: 0.63
Evidence: packet IDs, scenario evidence, source references
Data gap: cyber source offline
Next steps: verify independently, notify the duty controller
```

---

## 5. Why this is different

### 5.1 Explainability is a pipeline invariant

The system rejects module results without `reasons[]`. Explanation is not a UI decoration added after scoring. It is enforced at the contract boundary.

### 5.2 Missing data is not treated as a clean signal

Offline or unknown sources become explicit data gaps. Active weights are redistributed instead of silently interpreting unavailable data as zero risk.

### 5.3 Independent agreement increases priority, not certainty by magic

Correlation adds a bounded boost when independent sources agree. Conflicts stay visible. Confidence is reduced when sources are missing or disagree.

### 5.4 Asset importance and dependency cascades are first-class

A moderate signal near a high-importance hospital, ground station, or grid asset may matter more than a stronger signal near a low-importance asset. Dependency graphs model cascading impact.

### 5.5 The demo is deterministic and safe

There are no live credentials, classified feeds, or network dependencies. Every judge sees the same reproducible scenarios while still seeing realistic noise, drift, stale packets, out-of-order events, and planted anomalies.

---

## 6. What is built today

### Ingestion and synthetic data

- Canonical UTC events with WGS84 location support
- Four scenarios:
  - `flood`
  - `wildfire`
  - `satellite_fault`
  - `cyber_attack`
- Configurable seed, noise, cumulative drift, event cadence, and locations
- Seven planted telemetry fault types:
  - Missing field
  - Out-of-range value
  - Wrong type
  - Duplicate sequence
  - Gap/out-of-order sequence
  - Stale data
  - Sudden jump
- Null values are tested separately from missing fields and are rejected safely.
- Malformed data is quarantined rather than crashing the pipeline

### Telemetry and command safety

- YAML-driven field types, units, ranges, required fields, and sequence rules
- Duplicate/gap/out-of-order detection
- Sequence rollover at `65535 → 0`
- Session and boot reset handling
- Clock drift and late/stale packet handling
- Unknown field warnings
- Unit mismatch checks
- Rolling z-score anomaly detection
- Optional Isolation Forest interface, disabled by default
- Command ID, sender, parameter, sequence, and nonce/replay validation
- Power, thermal, communications, packet-loss, and latency health metrics

### Satellite analysis

- Before/after difference masks
- Percentage and changed-area calculations
- AOI boundary validation
- Resolution mismatch refusal with a clear message
- Cloud-cover confidence reduction and warnings above 40%
- Connected hotspot regions ranked by size and severity
- NDVI, NDWI, and NBR
- Basic land-cover labels: vegetation, water, burnt, bare
- Safe Q&A intents:
  - What changed?
  - Which area is worst?
  - How much changed?
  - Compare dates
  - Why was this flagged?

### Cyber and environment

- Failed-login and source-IP threshold scoring
- Port scans, odd traffic, malware, and untrusted scanner indicators
- Trusted scanner allow-list
- Rainfall, smoke, flood level, wind, and temperature scoring
- Optional nearby-station and satellite comparison hooks
- Cross-source correlation, including GPS-spoofing indicators

### Risk and prioritization

- Four normalized factors: satellite, telemetry, cyber, environment
- Configurable weights from YAML
- Versioned weights on every result
- Asset importance multiplier
- Independent-source correlation boost capped at +15
- Dependency cascade boost
- Low/Medium/High/Critical levels
- Trend arrow: rising, steady, falling
- Hysteresis to prevent alert flicker
- Asset ranking table
- Side-effect-free what-if simulation
- Conflict and data-gap visibility

### Explainability and workflow

- Immutable explanation snapshots
- What, why, confidence, factors, evidence, next steps, data gaps, and weight version
- Plain and technical render modes
- YAML playbooks for next steps
- Alert lifecycle:
  - New
  - Acknowledged
  - Assigned
  - Resolved
  - False Positive
- False-positive feedback field
- Alert grouping and rate-limit hooks

### Delivery surfaces

- Versioned FastAPI routes under `/api/v1`
- WebSocket stream with recent-event backfill
- React/Vite dark mission-control dashboard
- Risk gauge, feed, telemetry stream, ranking table, sliders, scenario launcher, and chat shell
- PDF, CSV, and GeoJSON exports
- Append-only JSONL audit utility
- UTC timeline replay utility
- Optional Telegram transport hook

---

## 7. The live demo: three minutes

### Before starting

From the repository root:

```bash
make dev
```

Open `http://127.0.0.1:8000/` in a browser.

For a terminal-only demonstration:

```bash
python -m sentinal.demo
```

### 0:00–0:20 — Establish the problem

Say:

> “This is not another dashboard that gives an unexplained red number. SENTINAL validates every signal, combines independent sources, and makes the reason for every alert visible.”

Point out the dark mission-control layout: risk gauge, alert feed, telemetry stream, ranking, explanation area, scenario launcher, and assistant.

### 0:20–0:50 — Launch a flood scenario

Run the `flood` scenario.

Explain:

- The generator is deterministic but not simplistic.
- It adds noise and drift.
- It plants telemetry faults intentionally for validation testing.
- The flood scenario adds environmental hazard evidence.

Show the resulting alert and read its explanation card:

1. What happened
2. Why it was flagged
3. Confidence
4. Evidence
5. Data gaps
6. Recommended next step

### 0:50–1:20 — Prove telemetry validation

Open the telemetry results or terminal demo output.

Say:

> “The validator does not stop at the first error. It returns all findings, quarantines unsafe packets, and keeps the source history needed for sequence, lateness, and jump checks.”

Mention the seven planted fault classes and the special handling for rollover, resets, stale data, and malformed JSON.

### 1:20–1:50 — Show cross-source risk

Launch `wildfire` or `cyber_attack`.

Show:

- The risk score changing
- The factor contribution bars
- Asset importance changing priority
- Correlation or cascade boost
- Confidence reduction when a source is missing
- The exact `weights_version`

Say:

> “An unavailable source is not silently scored as zero. SENTINAL tells the operator what is missing and lowers confidence.”

### 1:50–2:20 — Ask the satellite assistant

Use a supported question:

- “What changed?”
- “How much changed?”
- “Which area is worst?”
- “Why was this flagged?”

Explain that the router is keyword-first and the answer can only expose numbers returned by the analysis function. It cannot invent measurements.

If asked about an unsupported question, show the safe refusal.

### 2:20–2:45 — Show workflow and export

Demonstrate:

- Acknowledge or assign an alert
- Mark a false positive with feedback
- Open an explanation snapshot
- Export GeoJSON or CSV
- Generate a PDF report
- Replay the UTC event timeline

### 2:45–3:00 — Close with the value

Say:

> “SENTINAL does not replace the analyst, controller, commander, or responder. It shortens the path from raw signal to trusted understanding. The score tells you priority; the explanation tells you whether to trust it and what to do next.”

---

## 8. Technical explanation for judges

### 8.1 The contract boundary

Every detector result must contain:

```json
{
  "module": "telemetry_validator",
  "signal_id": "sig_001",
  "score": 0.82,
  "label": "abnormal_value",
  "reasons": [
    {"code": "OUT_OF_RANGE", "detail": "battery_v=999 exceeds 0-50 V"}
  ],
  "evidence": [
    {"type": "packet", "ref": "evt_001"}
  ],
  "confidence": 0.95,
  "timestamp": "2026-01-01T00:00:00Z"
}
```

The contract validator rejects a result with no reason. This prevents silent or opaque detections from entering the risk pipeline.

### 8.2 The canonical event

```json
{
  "id": "evt_001",
  "source_id": "telemetry-01",
  "type": "telemetry",
  "timestamp": "2026-01-01T00:00:00Z",
  "received_at": "2026-01-01T00:00:01Z",
  "geo": {"lat": 51.05, "lon": 13.74},
  "payload": {},
  "schema_version": "1.0",
  "raw_ref": "synthetic://evt_001"
}
```

All timestamps are timezone-aware and normalized to UTC. Geographic points are WGS84.

### 8.3 Risk formula

Each factor is normalized to 0–100.

```text
Base = w_satellite * Satellite
     + w_telemetry * Telemetry
     + w_cyber * Cyber
     + w_environment * Environment

Risk = min(
  100,
  Base * (0.5 + 0.5 * AssetImportance / 100)
  + CorrelationBoost
  + CascadeBoost
)
```

Correlation boost is bounded. Cascade boost is a configured fraction of the highest known dependency risk. Weight updates are validated and versioned.

### 8.4 Why confidence is separate from risk

Risk answers:

> “How severe could this be?”

Confidence answers:

> “How much should the operator trust the current evidence?”

A high-risk result can have lower confidence when a source is offline, only one source reports, cloud cover is high, or independent sources conflict.

### 8.5 Why the LLM is not required

The current chat router is keyword-first and deterministic. Any future LLM is constrained to reword structured analysis output. It is not allowed to call arbitrary tools or invent numbers. This protects the most important trust boundary: facts come from analysis functions, not generated prose.

---

## 9. Proof points

The current workspace verifies:

- **71 automated tests passing**
- All four synthetic scenarios run successfully
- All planted telemetry fault classes are detected
- Risk calculation, boundaries, hysteresis, cascade, correlation, and what-if are covered
- Explanation completeness and alert transitions are covered
- Satellite edge cases and safe chat behavior are covered
- Cyber/environment scoring and GPS-spoofing correlation are covered
- PDF, CSV, GeoJSON, audit, replay, and API smoke paths are covered
- Frontend production build succeeds with Vite
- The complete offline demo runs without API keys or network services

The most important proof is reproducibility: a judge can run the same command and receive the same scenario data, scores, explanations, and test result.

---

## 10. Product impact

### For analysts

- Faster evidence review
- Searchable reasons instead of unexplained scores
- Satellite change and hotspot context in the same workflow

### For mission controllers

- Packet-level validation
- Quarantine and source health
- Sequence, stale-data, jump, and replay checks

### For commanders

- One prioritized risk view
- Asset importance and dependency awareness
- Clear confidence and data gaps

### For responders

- Plain-language next steps
- Alert state and assignment workflow
- Exportable incident evidence

---

## 11. Why synthetic data is the right demo choice

The demo is explicitly synthetic for three reasons:

1. **Safety:** no classified or operational data is required.
2. **Repeatability:** judges can reproduce the exact result.
3. **Coverage:** faults can be planted deliberately, including rare edge cases that are difficult to guarantee with live feeds.

Synthetic data is not presented as operational truth. It is a test harness for the architecture, contracts, explanations, and failure handling. Real adapters can replace the generator later without rewriting the downstream modules.

---

## 12. Likely judge questions and answers

### “Why do you need this if operators already have dashboards?”

Existing dashboards usually specialize in one source and leave cross-source interpretation to a human. SENTINAL is the decision-support layer that validates, correlates, prioritizes, and explains across sources.

### “What stops the system from hallucinating?”

The baseline is rule-based. Every number comes from a structured analysis function. The contract requires reasons, and the chat router only exposes values present in the analysis result. A future LLM may reword facts but cannot invent numbers or call arbitrary tools.

### “How do you handle missing data?”

Missing or offline factors are explicit data gaps, not zeros. Active weights are redistributed, confidence is reduced, and the explanation tells the user what is unavailable.

### “How do you prevent alert fatigue?”

The design uses validation before scoring, bounded correlation boosts, alert grouping, rate-limit hooks, hysteresis, confidence, and explanation snapshots. The current prototype also supports false-positive feedback for future tuning.

### “Can you swap in real data or ML?”

Yes. Ingestion adapters produce canonical events, detectors return the module contract, and the risk/explainability layers consume structured results. A real satellite adapter, real telemetry stream, or ML detector can replace a synthetic/rule-based component behind that boundary.

### “Why is persistence not in the demo?”

The prototype prioritizes a fast, reproducible, offline demonstration. The current state is in-memory. SQLite/SQLAlchemy or PostgreSQL/PostGIS is the next persistence step, while the contracts and exports already separate storage from analysis.

### “Is this an autonomous command or control system?”

No. SENTINAL is decision support. It validates commands as data, but it does not send commands to spacecraft, infrastructure, or physical systems.

### “What is the most important feature?”

The explanation invariant. The score is useful only when an operator can understand the reasons, evidence, confidence, gaps, and next action.

### “What happens if a module crashes?”

The architecture isolates modules and exposes degraded/unknown source states. The rest of the pipeline can continue with lower confidence. Production deployment would add durable queues, health supervision, and retries.

### “Does it work offline?”

Yes. The four scenarios, rule-based analyzers, dashboard fallback, reports, replay, and demo all run locally without credentials or network access.

---

## 13. Honest limitations

The current hackathon/MVP implementation intentionally does not claim:

- Real classified or public data integration
- Durable SQLite/PostgreSQL persistence
- Production authentication or RBAC
- Live map tile integration
- Full GeoTIFF upload and reprojection pipeline
- High-availability deployment
- Production-grade notification delivery
- Autonomous command execution
- Calibrated operational probabilities

These are future engineering steps, not hidden assumptions.

---

## 14. Future scope

### Near term

- SQLite/SQLAlchemy persistence and durable alert history
- Real upload normalization for CSV, JSON, PNG/JPG, and GeoTIFF
- Complete API wiring for satellite arrays and chat analysis
- Leaflet map layers and Recharts telemetry/factor charts
- Durable audit trail and user/role management
- Real Telegram/email delivery adapters

### Pilot scope

- Sentinel-2/Landsat/FIRMS/weather adapters
- PostgreSQL/PostGIS
- Redis Streams or Kafka
- Real identity, RBAC, audit retention, and policy enforcement
- Calibrated thresholds and operator feedback loops

### Product scope

- ML detectors behind the same contracts
- Forecasting and six-hour risk projection
- Multi-language explanations
- Offline field mode and cached map tiles
- Model governance, drift monitoring, and explainability review

---

## 15. Closing statement

> **SENTINAL makes intelligence actionable without making it opaque.**

The system does not ask an operator to trust a black-box score. It gives them a prioritized risk, the reasons behind it, the evidence supporting it, the confidence level, the missing data, and the next step.

That is the difference between an alert dashboard and a decision-support platform.
