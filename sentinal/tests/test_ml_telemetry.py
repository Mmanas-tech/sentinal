import numpy as np
import pytest

from sentinal.ml.telemetry import TelemetryMlError, evaluate_detector, load_telemetry_file, load_training_rows
from sentinal.modules.telemetry.stats import IsolationForestDetector


def test_load_telemetry_csv_is_numeric_and_two_dimensional(tmp_path) -> None:
    path = tmp_path / "telemetry.csv"
    path.write_text("1,2\n3,4\n", encoding="utf-8")

    values = load_telemetry_file(path)

    assert values.shape == (2, 2)
    assert values.dtype == np.float32


def test_load_telemetry_rejects_non_finite_values(tmp_path) -> None:
    path = tmp_path / "telemetry.csv"
    path.write_text("1,nan\n3,4\n", encoding="utf-8")

    with pytest.raises(TelemetryMlError, match="non-finite"):
        load_telemetry_file(path)


def test_isolation_forest_fit_save_load_and_feature_inference(tmp_path) -> None:
    rows = [{"battery_v": 12 + (index % 2), "temp_c": 20 + (index % 3)} for index in range(24)]
    detector = IsolationForestDetector(min_samples=8, contamination=0.1)

    training = detector.fit(rows, source="test-fixture")
    artifact = detector.save(tmp_path / "telemetry.iforest.json")
    loaded = IsolationForestDetector(min_samples=8)

    assert training["status"] == "trained"
    assert artifact["sha256"]
    assert loaded.load(tmp_path / "telemetry.iforest.json")
    result = loaded.update({"battery_v": 80, "temp_c": 120}, source="fixture", sensor="packet")
    assert result["status"] == "validated"
    assert result["kind"] == "model"


def test_training_loader_and_evaluation_are_explicit_about_labels(tmp_path) -> None:
    path = tmp_path / "training.jsonl"
    path.write_text(
        "\n".join('{"value": %d, "label": %d}' % (index, 1 if index > 20 else 0) for index in range(24)),
        encoding="utf-8",
    )
    rows, labels = load_training_rows(path)
    detector = IsolationForestDetector(min_samples=8, contamination=0.1)
    detector.fit(rows)

    validated = evaluate_detector(detector, rows, labels)
    unvalidated = evaluate_detector(detector, rows)

    assert validated["status"] == "validated"
    assert {"accuracy", "precision", "recall", "confusion_matrix"} <= validated.keys()
    assert unvalidated["status"] == "unvalidated"
