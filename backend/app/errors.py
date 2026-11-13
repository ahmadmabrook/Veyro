"""Service errors shared by every module's service layer.

These were defined in `app.tenancy.service` while MOD-004 was the only module with a service.
MOD-005 needs the same four, and two parallel hierarchies would mean the HTTP exception handler
catches one of them and returns 500 for the other. They live here instead; `app.tenancy.service`
re-exports them, so nothing that imported them from there has to change.

`code` is always a fixed identifier chosen in this codebase, never interpolated from a request.
It is what reaches the client, so raw input must not travel in it.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class; `code` is a stable identifier, never raw input."""

    status = 400

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class InvalidRequest(ServiceError):
    status = 422


class Conflict(ServiceError):
    status = 409


class NotFound(ServiceError):
    status = 404
