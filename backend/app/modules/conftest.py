"""Session-scoped disposable-Postgres fixture shared by the six GOV-01-R02
domain scaffold suites (`app/modules/<domain>/tests/test_scaffold_live.py`).

Proves the harness itself — not product behavior — is live for each domain
path: test discovery, a real fixture DB connection, and the shared
`_shared.tenant_context` resolver contract. See SCN-MOD001-132. One
disposable container is shared across all six domains in the same pytest
session, the same sharing pattern `backend/tests/integration/conftest.py`
already uses.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import TupleRow

from tests.harness.postgres import DisposablePostgres, disposable_postgres

Conn = psycopg.Connection[TupleRow]


@pytest.fixture(scope="session")
def scaffold_pg() -> Iterator[DisposablePostgres]:
    with disposable_postgres() as instance:
        yield instance


@pytest.fixture(scope="session")
def scaffold_db(scaffold_pg: DisposablePostgres) -> Iterator[Conn]:
    with psycopg.connect(scaffold_pg.superuser_dsn, autocommit=True) as conn:
        yield conn
