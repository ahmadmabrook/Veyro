"""GOV-01-R02 critical-workflow harnesses (MOD-001 Slice 5).

Shared, importable test infrastructure later modules plug their real suites
into: `postgres` (disposable local Postgres), `tenant_isolation` (RLS
negative-role harness), `authn` (negative-credential fixture pattern).
Test-only code — nothing here is product code or may be imported by `app/`.
"""
