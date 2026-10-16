"""Load and validate the YAML configuration bundle."""

import math
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised for missing, malformed, or inconsistent configuration."""


DEFAULT_CONFIG_DIR = Path(__file__).parents[1] / "config"
REQUIRED_CONFIGS = {"schemas", "weights", "thresholds", "playbooks", "assets", "scenarios"}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError(f"configuration must be a YAML mapping: {path}")
    return loaded


def _validate_weights(data: dict[str, Any]) -> None:
    """Validate the normalized factor weights used by the risk engine."""
    factors = data.get("factors", data.get("weights"))
    if not isinstance(factors, dict) or not factors:
        raise ConfigError("weights configuration requires a non-empty factors mapping")

    values = list(factors.values())
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ConfigError("risk weights must be numeric")
    if any(not math.isfinite(float(value)) or value < 0 for value in values):
        raise ConfigError("risk weights must be finite and non-negative")

    validation = data.get("validation", {})
    if not isinstance(validation, dict):
        raise ConfigError("weights.validation must be a mapping")
    required_sum = float(validation.get("require_sum", 1.0))
    tolerance = float(validation.get("tolerance", 1e-6))
    total = sum(float(value) for value in values)
    if abs(total - required_sum) > tolerance:
        raise ConfigError(f"risk weights must sum to {required_sum}; got {total}")


def load_config(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load one YAML file or the complete Phase 1 configuration directory.

    Directory results are keyed by filename stem, for example
    ``bundle["weights"]["factors"]``. A single file is returned using its stem
    as the key so callers get the same shape in both modes.
    """
    source = Path(path) if path is not None else DEFAULT_CONFIG_DIR
    if not source.exists():
        raise ConfigError(f"configuration not found: {source}")

    if source.is_file():
        files = [source]
    else:
        files = sorted([*source.glob("*.yaml"), *source.glob("*.yml")])
        if not files:
            raise ConfigError(f"no YAML configuration found in {source}")

    bundle = {file.stem: _read_yaml(file) for file in files}
    if "weights" not in bundle:
        raise ConfigError("configuration requires weights.yaml")
    _validate_weights(bundle["weights"])

    if source.is_dir() and source == DEFAULT_CONFIG_DIR:
        missing = REQUIRED_CONFIGS.difference(bundle)
        if missing:
            names = ", ".join(f"{name}.yaml" for name in sorted(missing))
            raise ConfigError(f"configuration is missing: {names}")
    return bundle
