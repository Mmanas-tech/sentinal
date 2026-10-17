# SENTINAL — Test Report

**Date:** 2026-10-17
**Environment:** Python 3.11, Windows host, local repository; Rasterio installed from optional requirements for real GeoTIFF fixture coverage.
**Policy:** Only commands actually run are reported as passing.

## 1. Baseline before the audit upgrades

```text
python -m pytest -q sentinal/tests
87 passed
```

Also run:

```text
python -m compileall -q sentinal
passed

python -m sentinal.demo
all four scenarios completed; all planted telemetry faults detected
```

## 2. Focused upgrade checks

```text
python -m pytest -q sentinal/tests/test_ingestion_adapters.py sentinal/tests/test_raster.py sentinal/tests/test_provenance.py
9 passed
```

```text
python -m pytest -q sentinal/tests/test_ml_telemetry.py
4 passed
```

```text
python -m pytest -q sentinal/tests/test_api.py
15 passed
```

```text
python -m pytest -q sentinal/tests/test_raster.py
2 passed, 1 skipped
```

The skipped test is the explicit no-Rasterio behavior test; it skips when Rasterio is installed because the same file contains real Rasterio fixture coverage in that environment.

## 3. Full regression result after upgrades

```text
python -m pytest -q sentinal/tests
104 passed, 1 skipped
```

The full suite includes:

- Core schema/contract/event-bus tests
- Synthetic generator and all seven planted fault tests
- Telemetry rules, edge cases, command validation, health, z-score, and Isolation Forest
- Cyber/environment/cross-source tests
- Risk formula, weights, correlation, cascade, hysteresis, what-if, and provenance
- Explanation/alert workflow and evidence-specific why-not
- CSV/JSONL/HTTP/Open-Meteo adapter tests
- SQLite persistence and API integration tests
- GeoTIFF fixture tests for CRS/grid alignment, NoData, metadata, and hotspots
- Satellite numeric mode and safe chat tests
- Reports, exports, audit, replay, and demo polish tests

## 4. Frontend and syntax checks

```text
npm --prefix sentinal/web run build
success

python -m compileall -q sentinal
success
```

## 5. External provider smoke check

Executed against the documented public Open-Meteo forecast endpoint:

```text
OpenMeteoAdapter(timeout=20, retries=1).fetch_location(51.05, 13.74, forecast_hours=1)
status=LIVE events=1 errors=[]
```

This verifies the adapter/provider contract from this environment only. It is not a performance or availability guarantee.

## 6. Validation gaps

The following checks were not claimed as passed because the required deployment/data was not supplied:

- Provider-authenticated Sentinel/Landsat/FIRMS/SIEM/telemetry integration tests
- MQTT/Kafka/Redis broker integration
- Operational labeled telemetry precision/recall/F1/false-positive validation
- Live STAC/catalog imagery download and cloud-mask validation
- Multi-worker WebSocket fan-out and HA recovery
- Production security/penetration/accessibility audits
- Load, chaos, backup/restore, and retention/SLO testing
