from dataclasses import dataclass
from time import monotonic
@dataclass
class AlertGrouper:
    window_seconds: float = 300
    def __post_init__(self): self._seen = {}
    def key(self, alert): return (getattr(alert, 'asset_id', None), getattr(alert, 'label', None))
    def should_group(self, alert) -> bool:
        key = self.key(alert); now = monotonic(); previous = self._seen.get(key)
        self._seen[key] = now
        return previous is not None and now - previous <= self.window_seconds
class RateLimiter(AlertGrouper): pass
