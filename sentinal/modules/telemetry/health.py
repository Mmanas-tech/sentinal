"""Subsystem health and transport metrics for telemetry sources."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


class HealthTracker:
    """Track power, thermal, communications, loss, and latency per source."""

    def __init__(self, max_latency_s: float = 10.0) -> None:
        self.max_latency_s = max_latency_s
        self.subsystems: dict[str, dict[str, float]] = defaultdict(dict)
        self.sent: defaultdict[str, int] = defaultdict(int)
        self.received: defaultdict[str, int] = defaultdict(int)
        self.latencies: defaultdict[str, list[float]] = defaultdict(list)

    def update(
        self,
        subsystem: str,
        healthy: bool = True,
        *,
        source: str = "default",
        sent: int = 0,
        received: int = 0,
        latency_s: float | None = None,
    ) -> dict[str, Any]:
        self.subsystems[source][subsystem] = 100.0 if healthy else 0.0
        self.sent[source] += sent
        self.received[source] += received
        if latency_s is not None:
            self.latencies[source].append(float(latency_s))
        return self.snapshot(source)

    def record_packet(
        self,
        source: str,
        latency_s: float,
        lost: bool = False,
        packet: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record one packet and derive subsystem scores when values are present."""
        self.sent[source] += 1
        if not lost:
            self.received[source] += 1
        self.latencies[source].append(float(latency_s))

        if packet is not None and not lost:
            self.subsystems[source]["power"] = self._power_score(packet)
            self.subsystems[source]["thermal"] = self._thermal_score(packet)
        comms = 100.0 if not lost else 0.0
        if latency_s > self.max_latency_s:
            comms = _clamp(100.0 - (latency_s - self.max_latency_s) * 10.0)
        self.subsystems[source]["comms"] = comms
        return self.snapshot(source)

    def snapshot(self, source: str = "default") -> dict[str, Any]:
        sent = self.sent[source]
        received = self.received[source]
        loss = max(0, sent - received) / sent * 100 if sent else 0.0
        latencies = self.latencies[source]
        return {
            "subsystems": dict(self.subsystems[source]),
            "packet_loss_pct": loss,
            "latency_s": sum(latencies) / len(latencies) if latencies else None,
            "packets_sent": sent,
            "packets_received": received,
        }

    @staticmethod
    def _power_score(packet: dict[str, Any]) -> float:
        values: list[float] = []
        battery = packet.get("battery_v")
        solar = packet.get("solar_current_a")
        if isinstance(battery, (int, float)) and not isinstance(battery, bool):
            values.append(_clamp(float(battery) / 50.0 * 100.0))
        if isinstance(solar, (int, float)) and not isinstance(solar, bool):
            values.append(_clamp(float(solar) / 30.0 * 100.0))
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _thermal_score(packet: dict[str, Any]) -> float:
        temperature = packet.get("temp_c")
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            return 0.0
        distance_from_nominal = max(0.0, abs(float(temperature) - 25.0) - 25.0)
        return _clamp(100.0 - distance_from_nominal * 2.0)
