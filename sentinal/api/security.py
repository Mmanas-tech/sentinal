"""Opt-in local authentication and role checks."""

from __future__ import annotations

import os
from typing import Callable

from fastapi import Request

from .errors import ApiError


def _required() -> bool:
    return os.getenv("SENTINAL_AUTH_REQUIRED", "").lower() in {"1", "true", "yes"}


def require_role(*roles: str) -> Callable[[Request], str]:
    allowed = set(roles)

    def dependency(request: Request) -> str:
        if not _required():
            return request.headers.get("x-sentinal-role", "admin")
        expected = os.getenv("SENTINAL_API_TOKEN")
        authorization = request.headers.get("authorization", "")
        if not expected or authorization != "Bearer " + expected:
            raise ApiError("AUTH_REQUIRED", "valid bearer authentication is required", status_code=401)
        role = request.headers.get("x-sentinal-role", "observer")
        if role not in allowed:
            raise ApiError("FORBIDDEN", "role is not permitted for this operation", {"required": sorted(allowed)}, 403)
        return role

    return dependency
