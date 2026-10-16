from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
State = Literal['New','Acknowledged','Assigned','Resolved','False Positive']
@dataclass
class Alert:
    id: str
    asset_id: str
    what: str
    reasons: list[Any]
    evidence: list[Any]
    state: State = 'New'
    assignee: str | None = None
    feedback: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def transition(self, state: State, *, assignee: str | None = None) -> 'Alert':
        allowed = {'New': {'Acknowledged','False Positive'}, 'Acknowledged': {'Assigned','Resolved','False Positive'}, 'Assigned': {'Resolved','False Positive'}, 'Resolved': set(), 'False Positive': set()}
        if state not in allowed[self.state]: raise ValueError(f'invalid transition {self.state} -> {state}')
        self.state = state
        if assignee is not None: self.assignee = assignee
        return self
    def mark_false_positive(self, feedback: str) -> 'Alert':
        self.feedback = feedback; return self.transition('False Positive')

def alert_from_card(alert_id: str, asset_id: str, card: Any) -> Alert:
    return Alert(alert_id, asset_id, card.what, list(card.reasons or card.why), list(card.evidence))
