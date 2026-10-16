import pytest

from sentinal.risk import Asset, AssetRegistry, FactorInput, Hysteresis, RiskEngine, analyze_sources


def all_factors(score: float = 0.0) -> dict[str, float]:
    return {
        "satellite": score,
        "telemetry": score,
        "cyber": score,
        "environment": score,
    }


def test_prd_formula_and_explainable_result() -> None:
    engine = RiskEngine()

    result = engine.evaluate("asset_grid_01", all_factors(100), record=False)

    # Importance 85 -> multiplier 0.925; all factors produce a base of 100.
    assert result.score == pytest.approx(92.5)
    assert result.level == "critical"
    assert result.label == "Critical"
    assert result.reasons
    assert result.weights_version == "1.0"
    assert set(result.factors) == {"satellite", "telemetry", "cyber", "environment"}


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "low"),
        (29.9, "low"),
        (30, "medium"),
        (59.9, "medium"),
        (60, "high"),
        (79.9, "high"),
        (80, "critical"),
    ],
)
def test_risk_levels_use_continuous_boundaries(score: float, expected: str) -> None:
    engine = RiskEngine()

    assert engine._level(score) == expected


def test_offline_factor_is_a_gap_and_active_weights_are_redistributed() -> None:
    engine = RiskEngine()
    factors = {
        "satellite": FactorInput(100, sources=["satellite-a"]),
        "telemetry": FactorInput(100, status="offline"),
        "cyber": FactorInput(0, status="unknown"),
        "environment": FactorInput(0, status="unknown"),
    }

    result = engine.evaluate("asset_grid_01", factors, record=False)

    assert result.factors["satellite"] == pytest.approx(100)
    assert "telemetry" in result.data_gaps
    assert "cyber" in result.data_gaps
    assert result.factor_scores["telemetry"] == 100
    assert result.confidence < 1
    assert any(reason["code"] == "DATA_GAP" for reason in result.reasons)


def test_correlation_boost_caps_and_conflicts_remain_visible() -> None:
    boost, conflicts, agreeing = analyze_sources(
        [
            {"source_id": "sat-1", "score": 80},
            {"source_id": "tele-1", "score": 82},
            {"source_id": "env-1", "score": 79},
            {"source_id": "cyber-1", "score": 20},
        ]
    )

    assert boost == 10
    assert agreeing == 3
    assert conflicts == [{"source_id": "cyber-1", "score": 20.0}]


def test_risk_result_exposes_correlation_and_conflict() -> None:
    engine = RiskEngine()
    result = engine.evaluate(
        "asset_ground_01",
        all_factors(60),
        sources=[
            {"source_id": "a", "score": 60},
            {"source_id": "b", "score": 62},
            {"source_id": "c", "score": 10},
        ],
        record=False,
    )

    assert result.correlation_boost == 5
    assert result.conflicts
    assert any(reason["code"] == "SOURCE_CONFLICT" for reason in result.reasons)


def test_cascade_uses_highest_dependency_risk() -> None:
    engine = RiskEngine()
    engine.history["asset_grid_01"] = 80

    result = engine.evaluate("asset_hospital_01", all_factors(0), record=False)

    assert result.cascade_boost == pytest.approx(24)
    assert result.score == pytest.approx(24)
    assert any(reason["code"] == "CASCADE_BOOST" for reason in result.reasons)


def test_asset_registry_rejects_missing_dependencies_and_cycles() -> None:
    with pytest.raises(ValueError, match="missing dependencies"):
        AssetRegistry([Asset("a", dependencies=("missing",))])
    with pytest.raises(ValueError, match="circular"):
        AssetRegistry(
            [
                Asset("a", dependencies=("b",)),
                Asset("b", dependencies=("a",)),
            ]
        )


def test_hysteresis_raises_and_clears_at_separate_thresholds() -> None:
    state = Hysteresis()

    assert state.update(60) == "high"
    assert state.update(58) == "high"
    assert state.update(54) == "medium"
    assert state.update(80) == "critical"
    assert state.update(76) == "high"
    assert state.update(54) == "medium"
    assert state.update(29) == "low"


def test_what_if_does_not_mutate_history_or_hysteresis() -> None:
    engine = RiskEngine()
    baseline = engine.evaluate("asset_grid_01", all_factors(10))
    history_before = dict(engine.history)
    state_before = engine._hysteresis["asset_grid_01"].state

    counterfactual = engine.what_if("asset_grid_01", all_factors(100))

    assert counterfactual.score > baseline.score
    assert engine.history == history_before
    assert engine._hysteresis["asset_grid_01"].state == state_before


def test_weights_are_versioned_and_invalid_updates_roll_back() -> None:
    engine = RiskEngine()
    old_version = engine.weights_version

    assert engine.update_weights(
        {"satellite": 0.25, "telemetry": 0.25, "cyber": 0.25, "environment": 0.25},
        version="2.0",
    ) == "2.0"
    with pytest.raises(ValueError, match="sum"):
        engine.update_weights(
            {"satellite": 0.7, "telemetry": 0.2, "cyber": 0.1, "environment": 0.1},
            version="bad",
        )

    assert engine.weights_version == "2.0"
    assert engine.weights_version != old_version


def test_trend_and_asset_ranking() -> None:
    engine = RiskEngine()
    engine.evaluate("asset_grid_01", all_factors(10))
    rising = engine.evaluate("asset_grid_01", all_factors(40))
    ranking = engine.asset_ranking(
        {
            "asset_grid_01": all_factors(50),
            "asset_hospital_01": all_factors(50),
        },
        record=False,
    )

    assert rising.trend == "rising"
    assert [item.asset_id for item in ranking] == ["asset_hospital_01", "asset_grid_01"]
