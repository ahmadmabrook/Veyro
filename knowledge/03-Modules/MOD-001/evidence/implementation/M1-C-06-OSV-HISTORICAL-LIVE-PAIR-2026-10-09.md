# M1-C-06 — disposable historical OSV pair, local live check (2026-10-09)

Status: **local scanner input evidence only**. This is not a CI run, a
SCN-MOD001-094 PASS, an independent security verdict, or capability approval.
Sole runner operation: `ca684e85-00be-4244-9990-bed3fae08b30`.

## Boundary and source

The C06 route selects a project-authored stdlib OSV client and requires
SCN-094's vulnerable pin to live only in a throwaway lockfile. I used the
historical PyPI `PyYAML` pair `5.3.1` / `5.4.1`, with no package download or
installation. OSV's [PYSEC-2021-142](https://osv.dev/vulnerability/PYSEC-2021-142)
identifies CVE-2020-14343 and the pre-5.4 affected range. OSV's
[package-version query contract](https://osv.dev/) names the exact
`package`/`ecosystem`/`version` request shape. The disposable lock pins used
the SHA-256 **sdist metadata** values returned by the official
[PyPI 5.3.1 metadata](https://pypi.org/pypi/PyYAML/5.3.1/json) and
[PyPI 5.4.1 metadata](https://pypi.org/pypi/PyYAML/5.4.1/json):

| Version | Filename | PyPI SHA-256 |
|---|---|---|
| 5.3.1 | `PyYAML-5.3.1.tar.gz` | `b8eac752c5e14d3eca0e6dd9199cd627518cb5ec06add0de9d32baeee6fe645d` |
| 5.4.1 | `PyYAML-5.4.1.tar.gz` | `607774cbba28732bfa802b54baa7484215f530991055bb562efbed5b2f20a45e` |

Those are metadata readbacks, **not** downloaded-archive integrity checks.
The fixture existed only in a Python `TemporaryDirectory` and was removed
after the two executions. It was never added to the repository or installed.

## Observed run

At approximately 2026-10-09 13:35 UTC, the unchanged
`tools/scan_dependency_advisories.py` source SHA-256 was
`2a75b00985adee5fe03555045d53cb72dba39a22621af1f78af4e8a30d42bbe4`
(test SHA-256 `1b06ecec12d34260faf908b075a1cca1d29e79f62e99a27fa8144596bedbb7db`),
HEAD `e481b814a80923849dddfe7a49319112aae7b023`.
The project venv Python invoked the client separately on each temporary
one-package lock; the client made its live `POST https://api.osv.dev/v1/query`
request for PyPI/name/version. A direct read-only API probe immediately before
the scanner showed HTTP 200 for both versions: `5.3.1` returned two advisory
IDs, both aliasing CVE-2020-14343; `5.4.1` returned `{}`.

| Disposable pin | Local scanner observation |
|---|---|
| `PyYAML==5.3.1` | Exit **1 / DENY**; `GHSA-8q59-q68h-6hv4` and `PYSEC-2021-142` each cited `CVE-2020-14343`; result `2 validated advisory finding(s)` |
| `PyYAML==5.4.1` | Exit **0 / ALLOW**; `CLEAN (valid empty advisory result)`; result `1 package(s), every one a valid empty result` |

The script queried one package per lock. It did not scan
`backend/requirements-dev.lock.txt`, did not use a qualified third-party
scanner, and did not run in CI. This demonstrates live advisory-source shape
and a local positive/negative historical pair on this source snapshot only.
It does **not** establish that the real dependency tree is clean, that the
required vulnerability CI job blocks a PR, or that the SCN-094 criterion is
complete. SCN-MOD001-094 remains **NOT EXECUTED** as a CI scenario; its
catalog-required CI failure/clean companion and independent Opus judgment
remain separate. No review entitlement, CAP status, or finding counter changed.
