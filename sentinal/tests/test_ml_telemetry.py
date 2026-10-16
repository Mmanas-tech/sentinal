import numpy as np
import pytest

from sentinal.ml.telemetry import TelemetryMlError, load_telemetry_file


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
