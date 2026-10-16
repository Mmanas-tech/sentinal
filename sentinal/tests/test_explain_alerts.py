import pytest

from sentinal.alerts import Alert, AlertGrouper, TelegramNotifier, alert_from_card
from sentinal.explain import build_card, render
from sentinal.risk import FactorInput, RiskEngine


def make_card():
    result = RiskEngine().evaluate(
        "asset_grid_01",
        {name: FactorInput(50, sources=[name]) for name in ("satellite", "telemetry", "cyber", "environment")},
        record=False,
    )
    return build_card(result)


def test_explanation_card_is_complete_immutable_and_playbook_backed() -> None:
    card = make_card()

    assert card.what
    assert card.why
    assert card.evidence == ()
    assert card.next_steps
    assert card.weights_version
    with pytest.raises(TypeError):
        card.factors["new"] = 1

    plain = render(card, "plain")
    technical = render(card, "technical")
    assert "Confidence:" in plain
    assert "Factors:" in technical


def test_alert_workflow_transitions_and_feedback() -> None:
    alert = alert_from_card("alert-1", "asset_grid_01", make_card())

    assert alert.state == "New"
    alert.transition("Acknowledged").transition("Assigned", assignee="controller").transition("Resolved")
    assert alert.state == "Resolved"
    with pytest.raises(ValueError, match="invalid transition"):
        alert.transition("New")

    false_positive = Alert("alert-2", "asset_grid_01", "what", ["why"], [])
    false_positive.mark_false_positive("test fixture")
    assert false_positive.state == "False Positive"
    assert false_positive.feedback == "test fixture"


def test_grouping_and_optional_notifier_are_safe() -> None:
    grouper = AlertGrouper(window_seconds=30)
    first = Alert("a", "asset_grid_01", "what", [], [])
    second = Alert("b", "asset_grid_01", "what", [], [])

    assert not grouper.should_group(first)
    assert grouper.should_group(second)
    assert not TelegramNotifier().configured
    assert not TelegramNotifier().send("offline")
