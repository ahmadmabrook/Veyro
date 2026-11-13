"""Control-plane database access for MOD-004.

Two pools, one per plane, and the split is a security boundary rather than a convenience:

* the **tenant plane** runs as ``veyro_cp_app``, which holds privileges only on ``plt01`` and
  nothing at all on the tenant registry, and
* the **platform plane** runs as ``veyro_cp_platform``, which holds the registry and the
  lifecycle history and nothing in ``plt01``.

Neither role is a member of the other -- ADR-0002 D6.1 bars membership edges -- so a connection
pinned to one plane cannot reach the other by switching role at runtime. ``SET ROLE`` is issued
once when a connection enters the pool, so even a deployment that logs in with a wider account
(a local superuser, say) is constrained to the plane's privileges from its first statement.

Tenant context is set with ``set_config(..., true)``: the third argument is ``is_local``, so the
setting is discarded when the transaction ends and a pooled connection can never hand the next
request the previous request's tenant. The value is passed as a query parameter, never
interpolated, so a tenant identifier cannot carry SQL. ``tenant_scope`` is the only way this
module exposes a connection that can read ``plt01`` at all.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg_pool import ConnectionPool

Pool = ConnectionPool[Connection[Any]]

TENANT_ROLE = "veyro_cp_app"
PLATFORM_ROLE = "veyro_cp_platform"

# Same shape the S0 envelope validator accepts, so a value that passed the edge is accepted here.
_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.ASCII,
)


class TenantContextError(ValueError):
    """A tenant identifier was not a canonical lower-case UUID."""


def _pin_role(role: str) -> Callable[[Connection[Any]], None]:
    def configure(conn: Connection[Any]) -> None:
        # Not parameterisable: SET ROLE takes an identifier, not a value. `role` is one of this
        # module's two constants and never reaches here from a request.
        conn.execute(f"SET ROLE {role}")
        conn.commit()

    return configure


def make_tenant_pool(dsn: str) -> Pool:
    """A pool whose every connection is pinned to the tenant-facing role."""
    return ConnectionPool(dsn, configure=_pin_role(TENANT_ROLE), open=True)


def make_platform_pool(dsn: str) -> Pool:
    """A pool whose every connection is pinned to the platform-plane role."""
    return ConnectionPool(dsn, configure=_pin_role(PLATFORM_ROLE), open=True)


@contextmanager
def tenant_scope(
    pool: Pool, tenant_id: str
) -> Iterator[Connection[Any]]:
    """Yield a connection inside a transaction scoped to one tenant.

    Every statement issued on the yielded connection is filtered by the row-level security
    policies, because ``app.tenant_id`` is set for the life of this transaction and for no
    longer. Leaving the block commits; raising rolls back and the context is discarded either
    way.
    """
    if not _UUID.fullmatch(tenant_id):
        raise TenantContextError("tenant_id must be a canonical lower-case UUID")
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
            yield conn


@contextmanager
def platform_scope(pool: Pool) -> Iterator[Connection[Any]]:
    """Yield a connection inside a transaction on the platform plane.

    No tenant context is set and none is wanted: the registry is not tenant-scoped, and this
    role holds nothing in ``plt01``, so a stray query against a tenant table fails on privilege
    rather than returning another tenant's rows.
    """
    with pool.connection() as conn:
        with conn.transaction():
            yield conn
