"""Configuration-driven validation of telemetry packets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sentinal.core.config_loader import DEFAULT_CONFIG_DIR
from sentinal.core.schemas import Event

from .stats import IsolationForestDetector, RollingZScoreDetector


class Finding(BaseModel):
    """One rule result; validation never stops after the first finding."""

    model_config = ConfigDict(extra="forbid")

    code: str
    level: str = "WARN"
    detail: str
    field: str | None = None
    tags: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """The complete outcome for one packet."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    level: str
    findings: list[Finding]
    tags: list[str] = Field(default_factory=list)
    quarantined: bool = False
    incident_group: str | None = None


def _time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    return None


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "datetime":
        return _time(value) is not None
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


class TelemetryValidator:
    """Stateful validator with per-source sequence and jump history."""

    levels = {"OK": 0, "WARN": 1, "ERROR": 2, "CRITICAL": 3}

    def __init__(self, config_dir: str | Path | None = None, now: Any = None) -> None:
        root = DEFAULT_CONFIG_DIR if config_dir is None else Path(config_dir)
        self.schema = self._read_yaml(root / "schemas.yaml").get("telemetry_packet", {})
        self.thresholds = self._read_yaml(root / "thresholds.yaml").get("telemetry", {})
        self.state: dict[str, dict[str, Any]] = {}
        self.quarantine: list[Any] = []
        self.now = now
        self._incident_state: dict[str, tuple[datetime, str]] = {}
        self._incident_counter = 0
        self.zscore = RollingZScoreDetector(
            window=int(self.thresholds.get("rolling_window", 20)),
            threshold=float(self.thresholds.get("rolling_z_score_warn", 3.0)),
        )
        self.isolation_forest = IsolationForestDetector(
            enabled=bool(self.thresholds.get("isolation_forest_enabled", False)),
            window=int(self.thresholds.get("rolling_window", 20)),
        )

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"configuration must be a mapping: {path}")
        return loaded

    def validate(self, packet: dict[str, Any] | Event) -> ValidationResult:
        """Validate a packet or Event and return every applicable finding."""
        original = packet
        source, data, received_at = self._unpack(packet)
        if data is None:
            return self._bad(original, "MALFORMED_PACKET", "packet must be a mapping or Event")

        findings: list[Finding] = []
        tags: set[str] = set()
        fields = self.schema.get("fields", {})

        for name in self.schema.get("required", []):
            if name not in data:
                findings.append(
                    Finding(
                        code="MISSING_FIELD",
                        level="ERROR",
                        field=name,
                        detail=f"required field {name} is missing",
                    )
                )
            elif data[name] is None:
                findings.append(
                    Finding(
                        code="NULL_FIELD",
                        level="ERROR",
                        field=name,
                        detail=f"required field {name} is null",
                    )
                )

        for name, spec in fields.items():
            if name not in data or data[name] is None:
                continue
            value = data[name]
            expected = str(spec.get("type", ""))
            if not _type_matches(value, expected):
                findings.append(
                    Finding(
                        code="WRONG_TYPE",
                        level="ERROR",
                        field=name,
                        detail=f"expected {expected}",
                    )
                )
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                minimum, maximum = spec.get("min"), spec.get("max")
                if (minimum is not None and value < minimum) or (
                    maximum is not None and value > maximum
                ):
                    findings.append(
                        Finding(
                            code="OUT_OF_RANGE",
                            level="ERROR",
                            field=name,
                            detail=f"value {value} is outside configured range",
                        )
                    )
                elif expected == "float":
                    self._statistical_findings(source, name, value, findings)

        known_internal = {"source_id", "received_at", "payload", "units"}
        unknown = set(data).difference(fields).difference(known_internal)
        if unknown and self.schema.get("unknown_fields") == "warn":
            findings.append(
                Finding(
                    code="UNKNOWN_FIELD",
                    level="WARN",
                    detail=f"unknown fields: {sorted(unknown)}",
                )
            )

        self._check_units(data, findings)
        current = self._current_time(received_at)
        timestamp = _time(data.get("timestamp"))
        if timestamp is not None:
            age = (current - timestamp).total_seconds()
            stale_after = float(self.schema.get("stale_after_s", self.thresholds.get("stale_after_s", 60)))
            late_after = float(self.schema.get("late_after_s", 30))
            drift_tolerance = float(self.schema.get("clock_drift_tolerance_s", 10))
            if age > stale_after:
                findings.append(
                    Finding(
                        code="STALE_DATA",
                        level="WARN",
                        detail=f"packet age is {age:.1f}s",
                        tags=["STALE"],
                    )
                )
                tags.add("STALE")
            elif age > late_after:
                findings.append(
                    Finding(
                        code="LATE_DATA",
                        level="WARN",
                        detail=f"packet arrived {age:.1f}s after its source timestamp",
                        tags=["LATE"],
                    )
                )
                tags.add("LATE")
            if age < -drift_tolerance:
                findings.append(
                    Finding(
                        code="CLOCK_DRIFT",
                        level="WARN",
                        detail=f"source timestamp is {abs(age):.1f}s ahead of receive time",
                    )
                )

        old, reset = self._sequence_findings(source, data, findings, tags)
        if not reset:
            self._jump_findings(data, old, fields, findings)
        self._save_state(source, data, old, reset, fields)

        level = max(
            (finding.level for finding in findings),
            key=lambda value: self.levels.get(value, 0),
            default="OK",
        )
        quarantined = level in {"ERROR", "CRITICAL"}
        incident_group = self._incident_group(source, current) if quarantined else None
        result = ValidationResult(
            valid=not quarantined,
            level=level,
            findings=findings,
            tags=sorted(tags.union(tag for finding in findings for tag in finding.tags)),
            quarantined=quarantined,
            incident_group=incident_group,
        )
        if quarantined:
            self.quarantine.append(original)
        return result

    def validate_raw(self, raw: str) -> ValidationResult:
        """Parse JSON safely; malformed content is returned as quarantined data."""
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            return self._bad(None, "MALFORMED_JSON", f"invalid JSON: {exc}")
        if not isinstance(parsed, dict):
            return self._bad(parsed, "MALFORMED_JSON", "JSON packet must be an object")
        return self.validate(parsed)

    def _unpack(
        self, packet: dict[str, Any] | Event
    ) -> tuple[str, dict[str, Any] | None, Any]:
        if isinstance(packet, Event):
            data = dict(packet.payload)
            data.setdefault("timestamp", packet.timestamp)
            return packet.source_id, data, packet.received_at
        if not isinstance(packet, dict):
            return "unknown", None, None

        source = str(packet.get("source_id", packet.get("source", "unknown")))
        received_at = packet.get("received_at")
        if isinstance(packet.get("payload"), dict):
            data = dict(packet["payload"])
            if "timestamp" not in data and "timestamp" in packet:
                data["timestamp"] = packet["timestamp"]
        else:
            data = dict(packet)
        return source, data, received_at

    def _check_units(self, data: dict[str, Any], findings: list[Finding]) -> None:
        declared = data.get("units", {})
        if not isinstance(declared, dict):
            findings.append(
                Finding(code="WRONG_TYPE", level="ERROR", field="units", detail="units must be an object")
            )
            return
        expected_units = self.schema.get("units", {})
        for name, expected in expected_units.items():
            if name in declared and declared[name] != expected:
                findings.append(
                    Finding(
                        code="UNIT_MISMATCH",
                        level="ERROR",
                        field=name,
                        detail=f"expected unit {expected}, received {declared[name]}",
                    )
                )

    def _statistical_findings(
        self,
        source: str,
        sensor: str,
        value: float,
        findings: list[Finding],
    ) -> None:
        zscore = self.zscore.update(value, source=source, sensor=sensor)
        if zscore["anomalous"]:
            findings.append(
                Finding(
                    code="STATISTICAL_ANOMALY",
                    level="WARN",
                    field=sensor,
                    detail=f"rolling z-score is {zscore['z_score']:.2f}",
                )
            )
        forest = self.isolation_forest.update(value, source=source, sensor=sensor)
        if forest.get("anomalous"):
            findings.append(
                Finding(
                    code="ML_ANOMALY",
                    level="WARN",
                    field=sensor,
                    detail="Isolation Forest marked the value anomalous",
                )
            )

    def _current_time(self, received_at: Any) -> datetime:
        current = _time(received_at)
        if current is not None:
            return current
        if callable(self.now):
            current = _time(self.now())
            if current is not None:
                return current
        return datetime.now(timezone.utc)

    def _sequence_findings(
        self,
        source: str,
        data: dict[str, Any],
        findings: list[Finding],
        tags: set[str],
    ) -> tuple[dict[str, Any] | None, bool]:
        old = self.state.get(source)
        session = str(data.get("session_id", ""))
        reset = bool(old and ((session and session != old.get("session")) or data.get("boot") is True))
        if reset:
            tags.add("SESSION_RESET")
            return None, True
        if old is None:
            return None, False

        seq = data.get("seq")
        previous = old.get("seq")
        seq_spec = self.schema.get("fields", {}).get("seq", {})
        rollover = int(seq_spec.get("rollover", 65535))
        modulus = rollover + 1
        valid_seq = isinstance(seq, int) and not isinstance(seq, bool) and 0 <= seq <= rollover
        valid_previous = isinstance(previous, int) and not isinstance(previous, bool)
        if not valid_seq or not valid_previous:
            return old, False

        seen = old.get("seen_sequences", set())
        if seq in seen and not (previous == rollover and seq == 0):
            findings.append(
                Finding(
                    code="DUPLICATE_SEQUENCE",
                    level="ERROR",
                    detail=f"sequence {seq} was already received",
                    tags=["DUPLICATE"],
                )
            )
            tags.add("DUPLICATE")
            return old, False

        if previous == rollover and seq == 0:
            return old, False

        delta = (seq - previous) % modulus
        if delta > modulus // 2:
            findings.append(
                Finding(
                    code="OUT_OF_ORDER",
                    level="WARN",
                    detail=f"sequence moved backward from {previous} to {seq}",
                    tags=["LATE"],
                )
            )
            tags.add("LATE")
        else:
            max_gap = int(self.thresholds.get("max_gap", 1))
            missing = delta - 1
            if missing > max_gap:
                findings.append(
                    Finding(
                        code="SEQUENCE_GAP",
                        level="WARN",
                        detail=f"sequence gap contains {missing} missing packet(s)",
                        tags=["GAP"],
                    )
                )
                tags.add("GAP")
        return old, False

    @staticmethod
    def _jump_findings(
        data: dict[str, Any],
        old: dict[str, Any] | None,
        fields: dict[str, Any],
        findings: list[Finding],
    ) -> None:
        if old is None:
            return
        for name, spec in fields.items():
            limit = spec.get("max_jump")
            value, previous = data.get(name), old.get(name)
            if limit is None or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if not isinstance(previous, (int, float)) or isinstance(previous, bool):
                continue
            if abs(value - previous) > float(limit):
                findings.append(
                    Finding(
                        code="SUDDEN_JUMP",
                        level="WARN",
                        field=name,
                        detail=f"change {abs(value - previous):.2f} exceeds max jump {limit}",
                    )
                )

    def _save_state(
        self,
        source: str,
        data: dict[str, Any],
        old: dict[str, Any] | None,
        reset: bool,
        fields: dict[str, Any],
    ) -> None:
        previous_seen = set() if reset or old is None else set(old.get("seen_sequences", set()))
        seq = data.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool):
            previous_seen.add(seq)
        if len(previous_seen) > 2048:
            previous_seen = set(sorted(previous_seen)[-1024:])
        next_seq = seq if isinstance(seq, int) and not isinstance(seq, bool) else (old or {}).get("seq")
        if old is not None and isinstance(next_seq, int) and isinstance(old.get("seq"), int):
            rollover = int(self.schema.get("fields", {}).get("seq", {}).get("rollover", 65535))
            modulus = rollover + 1
            if (next_seq - old["seq"]) % modulus > modulus // 2:
                next_seq = old["seq"]
        self.state[source] = {
            "seq": next_seq,
            "session": str(data.get("session_id", "")),
            "seen_sequences": previous_seen,
            **{name: data.get(name) for name in fields},
        }

    def _incident_group(self, source: str, current: datetime) -> str:
        burst_window = float(self.thresholds.get("incident_burst_window_s", 60))
        previous = self._incident_state.get(source)
        if previous and (current - previous[0]).total_seconds() <= burst_window:
            return previous[1]
        self._incident_counter += 1
        group = f"telemetry:{source}:{self._incident_counter}"
        self._incident_state[source] = (current, group)
        return group

    def _bad(self, packet: Any, code: str, detail: str) -> ValidationResult:
        result = ValidationResult(
            valid=False,
            level="CRITICAL",
            findings=[Finding(code=code, level="CRITICAL", detail=detail)],
            quarantined=True,
            incident_group="telemetry:malformed",
        )
        self.quarantine.append(packet)
        return result
