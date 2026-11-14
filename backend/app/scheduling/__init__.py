"""MOD-019 OPS-01: scheduling, resources and capacity.

The decision functions are here and the I/O is in `service.py`, as in every module since
MOD-005. Two of these are worth reading before the rest: `recurrence.py`, because a schedule
that is right in one timezone and wrong after a clock change is the defect nobody notices until
somebody misses a class; and `conflicts.py`, because paragraph 1842 makes an unoverridable
conflict a Critical Control and the override is therefore a permission rather than a flag.
"""
