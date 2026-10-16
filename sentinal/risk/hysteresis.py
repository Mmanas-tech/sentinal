"""Alert-state hysteresis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hysteresis:
    """Prevent high/critical alert state from flickering at boundaries."""

    raise_high_at: float = 60.0
    clear_high_below: float = 55.0
    raise_critical_at: float = 80.0
    clear_critical_below: float = 75.0
    state: str = "low"

    def update(self, score: float) -> str:
        if self.state == "critical":
            if score >= self.raise_critical_at:
                return self.state
            if score >= self.clear_critical_below:
                self.state = "high"
            elif score >= self.clear_high_below:
                self.state = "high"
            elif score >= 30:
                self.state = "medium"
            else:
                self.state = "low"
            return self.state

        if self.state == "high":
            if score >= self.raise_critical_at:
                self.state = "critical"
            elif score < self.clear_high_below:
                self.state = "medium" if score >= 30 else "low"
            return self.state

        if self.state == "medium":
            if score >= self.raise_critical_at:
                self.state = "critical"
            elif score >= self.raise_high_at:
                self.state = "high"
            elif score < 30:
                self.state = "low"
            return self.state

        if score >= self.raise_critical_at:
            self.state = "critical"
        elif score >= self.raise_high_at:
            self.state = "high"
        elif score >= 30:
            self.state = "medium"
        else:
            self.state = "low"
        return self.state
