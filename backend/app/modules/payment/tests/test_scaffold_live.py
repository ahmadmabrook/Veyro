"""GOV-01-R02 scaffold-live proof for the payment domain — SCN-MOD001-132.

Empty-but-wired placeholder: proves test discovery, a real fixture DB
connection, and the shared `_shared.tenant_context` resolver contract are
live for this domain path. Asserts no product behavior — payment's real
logic belongs to whichever module eventually claims this domain.
"""

from __future__ import annotations

from uuid import uuid4

from app.modules._shared.tenant_context import TenantContext
from app.modules.conftest import Conn
from tests.harness.tenant_context import StaticTenantContextResolver


def test_scaffold_live(scaffold_db: Conn) -> None:
    assert scaffold_db.execute("SELECT 1").fetchone() == (1,)

    tenant_id = uuid4()
    resolver = StaticTenantContextResolver(TenantContext(tenant_id))
    assert resolver.resolve().tenant_id == tenant_id
