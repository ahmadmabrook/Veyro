"""Service errors shared by every module's service layer.

There are five. These were defined in `app.tenancy.service` while MOD-004 was the only module
with a service.
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


class TooManyRequests(ServiceError):
    """A rate limit refused this request (MOD-011's ApplyRateLimit).

    429 rather than 403, because the caller may be entitled to do this and is simply doing it
    too fast -- and because a client that reads 403 stops while one that reads 429 backs off.

    `retry_after_seconds` rides on the exception and reaches the client as a `Retry-After`
    header. Computing a backoff and then not sending it leaves the client nothing to back off
    by, which makes the choice of 429 over 403 decorative.
    """

    status = 429

    def __init__(self, code: str, retry_after_seconds: int = 1) -> None:
        super().__init__(code)
        self.retry_after_seconds = max(1, retry_after_seconds)
