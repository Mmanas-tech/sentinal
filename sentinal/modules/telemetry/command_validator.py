"""Validation boundary for spacecraft commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sentinal.core.config_loader import DEFAULT_CONFIG_DIR

from .rules import Finding, ValidationResult


class CommandValidator:
    """Validate command identity, authorization, parameters, and replay state."""

    levels = {"OK": 0, "WARN": 1, "ERROR": 2, "CRITICAL": 3}

    def __init__(
        self,
        commands: dict[str, Any] | None = None,
        allowed_senders: list[str] | None = None,
        rollover: int = 65535,
    ) -> None:
        if commands is None:
            config_path = DEFAULT_CONFIG_DIR / "schemas.yaml"
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            command_config = config.get("commands", {})
            self.commands = command_config.get("definitions", {})
            self.allowed_senders = set(
                allowed_senders or command_config.get("allowed_senders", [])
            )
        elif "definitions" in commands:
            self.commands = commands.get("definitions", {})
            self.allowed_senders = set(allowed_senders or commands.get("allowed_senders", []))
        else:
            self.commands = commands
            self.allowed_senders = set(allowed_senders or [])
        self.rollover = rollover
        self.state: dict[tuple[str, str], dict[str, Any]] = {}
        self.seen_nonces: set[tuple[str, str, str]] = set()

    def validate(self, command: dict[str, Any]) -> ValidationResult:
        if not isinstance(command, dict):
            return ValidationResult(
                valid=False,
                level="CRITICAL",
                findings=[
                    Finding(
                        code="MALFORMED_COMMAND",
                        level="CRITICAL",
                        detail="command must be an object",
                    )
                ],
                quarantined=True,
                incident_group="command:malformed",
            )

        findings: list[Finding] = []
        command_id = command.get("command_id", command.get("id"))
        sender = command.get("sender")
        session_id = str(command.get("session_id", ""))
        parameters = command.get("parameters", command.get("params", {}))

        if not command_id:
            findings.append(
                Finding(code="MISSING_COMMAND_ID", level="ERROR", detail="command_id is required")
            )
            spec: dict[str, Any] = {}
        else:
            spec = self.commands.get(command_id, {})
            if not spec:
                findings.append(
                    Finding(
                        code="UNKNOWN_COMMAND",
                        level="ERROR",
                        detail=f"unknown command ID {command_id}",
                    )
                )

        sender_allowlist = spec.get("allowed_senders", self.allowed_senders)
        if sender_allowlist and sender not in sender_allowlist:
            findings.append(
                Finding(
                    code="SENDER_NOT_ALLOWED",
                    level="ERROR",
                    detail=f"sender {sender!r} is not allowed",
                    field="sender",
                )
            )

        if not isinstance(parameters, dict):
            findings.append(
                Finding(
                    code="WRONG_TYPE",
                    level="ERROR",
                    field="parameters",
                    detail="parameters must be an object",
                )
            )
            parameters = {}
        self._parameter_findings(parameters, spec.get("parameters", {}), findings)

        sequence = command.get("seq")
        sequence_key = (str(sender), session_id)
        old = self.state.get(sequence_key)
        valid_sequence = isinstance(sequence, int) and not isinstance(sequence, bool)
        if not valid_sequence or not 0 <= sequence <= self.rollover:
            findings.append(
                Finding(
                    code="INVALID_SEQUENCE",
                    level="ERROR",
                    field="seq",
                    detail=f"seq must be an integer from 0 to {self.rollover}",
                )
            )
        elif old is not None:
            previous = old["seq"]
            if sequence == previous:
                findings.append(
                    Finding(
                        code="DUPLICATE_SEQUENCE",
                        level="ERROR",
                        field="seq",
                        detail="command sequence repeated",
                    )
                )
            elif previous == self.rollover and sequence == 0:
                pass
            else:
                delta = (sequence - previous) % (self.rollover + 1)
                if delta > (self.rollover + 1) // 2:
                    findings.append(
                        Finding(
                            code="OUT_OF_ORDER",
                            level="WARN",
                            field="seq",
                            detail="command sequence arrived out of order",
                        )
                    )
                elif delta > 1:
                    findings.append(
                        Finding(
                            code="SEQUENCE_GAP",
                            level="WARN",
                            field="seq",
                            detail=f"command sequence gap of {delta - 1}",
                        )
                    )

        nonce = command.get("nonce")
        nonce_key = (str(sender), session_id, str(nonce))
        if not isinstance(nonce, str) or not nonce:
            findings.append(
                Finding(code="INVALID_NONCE", level="ERROR", field="nonce", detail="nonce is required")
            )
        elif nonce_key in self.seen_nonces:
            findings.append(
                Finding(code="REPLAY", level="ERROR", field="nonce", detail="nonce was already used")
            )

        if valid_sequence and not any(
            finding.level in {"ERROR", "CRITICAL"} and finding.field == "seq"
            for finding in findings
        ):
            self.state[sequence_key] = {"seq": sequence}
        if isinstance(nonce, str) and nonce:
            self.seen_nonces.add(nonce_key)

        level = max(
            (finding.level for finding in findings),
            key=lambda value: self.levels.get(value, 0),
            default="OK",
        )
        return ValidationResult(
            valid=level in {"OK", "WARN"},
            level=level,
            findings=findings,
            quarantined=level in {"ERROR", "CRITICAL"},
            incident_group=f"command:{sender}" if findings else None,
        )

    @staticmethod
    def _parameter_findings(
        values: dict[str, Any],
        definitions: dict[str, Any],
        findings: list[Finding],
    ) -> None:
        for name, rule in definitions.items():
            if name not in values:
                findings.append(
                    Finding(
                        code="MISSING_PARAMETER",
                        level="ERROR",
                        field=name,
                        detail="required command parameter is missing",
                    )
                )
                continue
            value = values[name]
            kind = rule.get("type")
            valid = True
            if kind == "number":
                valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            elif kind == "integer":
                valid = isinstance(value, int) and not isinstance(value, bool)
            elif kind == "boolean":
                valid = isinstance(value, bool)
            elif kind == "string":
                valid = isinstance(value, str)
            elif kind == "enum":
                valid = value in rule.get("values", [])
            if not valid:
                findings.append(
                    Finding(
                        code="WRONG_TYPE",
                        level="ERROR",
                        field=name,
                        detail=f"parameter does not match {kind}",
                    )
                )
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if rule.get("min") is not None and value < rule["min"]:
                    findings.append(
                        Finding(
                            code="OUT_OF_RANGE",
                            level="ERROR",
                            field=name,
                            detail="parameter is below the configured minimum",
                        )
                    )
                if rule.get("max") is not None and value > rule["max"]:
                    findings.append(
                        Finding(
                            code="OUT_OF_RANGE",
                            level="ERROR",
                            field=name,
                            detail="parameter is above the configured maximum",
                        )
                    )
        unknown = set(values).difference(definitions)
        for name in sorted(unknown):
            findings.append(
                Finding(
                    code="UNKNOWN_PARAMETER",
                    level="ERROR",
                    field=name,
                    detail="parameter is not allowed for this command",
                )
            )
