"""Tenant-context resolver contract — GOV-01-R02 scaffold, SCN-MOD001-132.

This is NOT product authentication or tenant-resolution logic. Per TSD
`TEN-002`, real tenant context is resolved server-side from an
authenticated identity a later domain module establishes against its real
provider (TSD ADR-009: Veyro does not implement credential cryptography
itself). This module is only the minimal shared *contract* — a
`TenantContext` value and a `TenantContextResolver` protocol — that the six
GOV-01-R02 domain scaffolds import to prove a cross-cutting dependency is
live before any domain owns real logic.

Per `.claude/rules/backend/architecture.md` control 3, only domain-free
code belongs in `_shared/`; this file makes no claim about how a real
resolver authenticates a caller. A test-only implementation of this
protocol lives in `tests/harness/tenant_context.py`, not here — a
production package is not the place for a fixture class, per
independent code review `CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class TenantContext:
    """The one fact every domain needs: which tenant a request is scoped to."""

    tenant_id: UUID


class TenantContextResolver(Protocol):
    """Resolves the current request's `TenantContext`.

    A real resolver (owned by whichever module first needs it) derives this
    from server-side-authenticated identity — never from a client-supplied
    value (`TEN-002`). This protocol states that contract; it performs no
    resolution itself.
    """

    def resolve(self) -> TenantContext: ...
