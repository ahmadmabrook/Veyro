"""Test-only implementation of `app.modules._shared.tenant_context`'s
resolver protocol — GOV-01-R02 scaffold, SCN-MOD001-132.

Kept here, not in the production `_shared/` package, because a fixture
class has no place in product code (independent code review
`CR-MOD001-GOV01-R02-DOMAIN-SCAFFOLDS-2026-10-03.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules._shared.tenant_context import TenantContext


@dataclass(frozen=True)
class StaticTenantContextResolver:
    """Test-only `TenantContextResolver` that always returns a fixed,
    caller-supplied context.

    Exists only so the GOV-01-R02 scaffold suites can prove the shared
    resolver contract is importable and callable. It makes no
    authentication claim and must never be wired into a real request path.
    """

    context: TenantContext

    def resolve(self) -> TenantContext:
        return self.context
