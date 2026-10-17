"""Data ingestion, adapters, and deterministic synthetic event generation."""

from .adapters import (
    AdapterError,
    AdapterResult,
    CSVAdapter,
    HTTPAdapter,
    HTTPStreamAdapter,
    JSONLAdapter,
    OpenMeteoAdapter,
)
from .synthetic_generator import SyntheticGenerator, SyntheticResult

__all__ = [
    "AdapterError",
    "AdapterResult",
    "CSVAdapter",
    "HTTPAdapter",
    "HTTPStreamAdapter",
    "JSONLAdapter",
    "OpenMeteoAdapter",
    "SyntheticGenerator",
    "SyntheticResult",
]
