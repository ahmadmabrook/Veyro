"""MOD-004 local-domain-slice lane root: pure tenant-domain logic.

Nothing here is an authenticated principal, an authorization decision about a real caller,
tenant isolation, a database constraint or integration evidence. Tenant isolation is enforced
by PostgreSQL row-level security, which this lane cannot write and does not evidence.
"""
