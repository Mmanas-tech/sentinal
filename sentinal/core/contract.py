"""Validation boundary for detector outputs."""

from typing import Any

from pydantic import ValidationError

from .schemas import ModuleResult


class ModuleContractError(ValueError):
    """Raised when a detector output cannot enter the pipeline."""


def validate_module_result(result: ModuleResult | dict[str, Any]) -> ModuleResult:
    """Parse and enforce the explainability invariant for a detector result."""
    try:
        parsed = result if isinstance(result, ModuleResult) else ModuleResult.model_validate(result)
    except ValidationError as exc:
        raise ModuleContractError(str(exc)) from exc

    if not parsed.reasons:
        raise ModuleContractError("module result must contain at least one reason")
    return parsed


def accept_module_result(result: ModuleResult | dict[str, Any]) -> ModuleResult:
    """Named entry point used by future module adapters."""
    return validate_module_result(result)
