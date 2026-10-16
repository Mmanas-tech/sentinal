from sentinal.modules.cyber import CyberAnalyzer
from sentinal.modules.environment import EnvironmentAnalyzer
from sentinal.risk.correlation import correlate_signals


def test_cyber_scoring_uses_thresholds_and_allowlist() -> None:
    trusted = CyberAnalyzer(trusted_scanners={"scanner-1"})
    trusted_result = trusted.analyze({"failed_logins": 50, "scanner": "scanner-1", "asset_importance": 90})
    untrusted_result = trusted.analyze({"failed_logins": 50, "scanner": "unknown"})

    assert trusted_result["score"] >= 45
    assert any(reason["code"] == "failed_logins_10m" for reason in trusted_result["reasons"])
    assert any(reason["code"] == "untrusted_scanner" for reason in untrusted_result["reasons"])


def test_cyber_scenario_aliases_and_malformed_input_are_safe() -> None:
    analyzer = CyberAnalyzer()
    result = analyzer.analyze({"failed_logins": 10, "packets_per_second": 120})
    empty = analyzer.analyze("not a mapping")

    assert result["score"] > 0
    assert result["reasons"]
    assert empty["score"] == 0
    assert empty["reasons"]


def test_environment_hazards_support_synthetic_scenario_field_names() -> None:
    analyzer = EnvironmentAnalyzer()

    flood = analyzer.analyze({"water_level_m": 3.2, "rainfall_mm": 100})
    wildfire = analyzer.analyze({"smoke_index": 0.9, "wind_speed_mps": 30})

    assert flood["score"] >= 75
    assert wildfire["score"] >= 75
    assert flood["evidence"] and wildfire["evidence"]


def test_environment_comparison_hook_failure_does_not_crash() -> None:
    def broken(_: dict) -> dict:
        raise RuntimeError("station offline")

    result = EnvironmentAnalyzer(station_hook=broken).analyze({"rainfall_24h_mm": 100})

    assert result["score"] > 0


def test_cross_source_correlation_reports_agreement_and_gps_spoofing() -> None:
    result = correlate_signals(
        {"score": 80},
        {"score": 75, "gps_spoofing": True},
        {"score": 70},
    )

    assert result["score"] == 95
    assert {reason["code"] for reason in result["reasons"]} >= {"multi_source_agreement", "gps_spoofing"}
