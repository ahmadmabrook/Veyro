"""The worker runtime: the thing fourteen module entries in `CLAUDE.md` were waiting for.

`registry.py` says what the jobs are, `runner.py` says when they run and what happens when one
raises, and `names.py` is the closed set of job names that both the registry and MOD-011's
metric catalogue read. `python -m app.worker --once` runs one tick and prints what it did.
"""
