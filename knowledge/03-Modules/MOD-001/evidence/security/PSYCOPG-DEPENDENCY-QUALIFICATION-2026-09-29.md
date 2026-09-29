---
doc: PSYCOPG_DEPENDENCY_QUALIFICATION
status: LIVE
module: MOD-001
updated: 2026-09-29
---

# Independent psycopg dependency qualification (`psycopg[binary]==3.3.6`)

Independently re-verified by the orchestrating session, against
authoritative package metadata (not the prior implementation report's
own claim alone), per the governing mission's explicit instruction not
to trust the prior license label without checking installed package
metadata directly.

## What was checked, and how

1. **Installed package metadata**, read directly from
   `backend/.venv/lib/python3.14/site-packages/{psycopg,psycopg_binary}-3.3.6.dist-info/METADATA`:
   `License-Expression: LGPL-3.0-only` for both `psycopg` and
   `psycopg-binary`.
2. **Bundled license text** (`.../licenses/LICENSE.txt` in both
   dist-info directories): confirmed genuinely the GNU Lesser General
   Public License, Version 3, 29 June 2007 (header text read directly,
   not inferred from the filename).
3. **Authoritative upstream source (PyPI JSON API)**, queried live,
   independent of the local wheel's own self-declared metadata: `GET
   https://pypi.org/pypi/psycopg/3.3.6/json` and the `psycopg-binary`
   equivalent both return `license_expression: LGPL-3.0-only` — matches
   the locally-installed metadata exactly, no discrepancy.
4. **Vulnerability re-check**, independent of the prior report:
   `POST https://api.osv.dev/v1/query` for `psycopg`/`psycopg-binary` at
   `3.3.6` both return `{}` (no known vulnerabilities).
5. **Provenance**: official PyPI project, author Daniele Varrazzo
   (`https://psycopg.org/`) — matches the `pip show` output and the
   PyPI project metadata.

**Conclusion: the prior implementation report's license/provenance/
vulnerability claims are accurate.** No discrepancy found between the
installed wheel's declared metadata, its bundled license text, and
PyPI's own authoritative JSON metadata.

## Whether project governance requires an owner decision here

Checked directly, not assumed:

- **`CAPABILITY_POLICY.md`'s scope** (re-read directly): "Governs every
  Skill, Rule, Plugin, MCP server, hook, or script used on this
  project." An ordinary pip runtime dependency of the product's own
  backend code is not in this list — consistent with existing project
  practice: `pytest`/`ruff`/`mypy` (added in `BUG-036`'s remediation)
  were never registered in `CAPABILITY_REGISTRY.md` either, and no
  prior session treated that as a gap. `psycopg` does not need a
  `CAPABILITY_REGISTRY.md` row for the same reason.
- **`DEVELOPMENT_CONSTITUTION.md` DC-16** (owner-reserved absolute
  restrictions): no paid service, no real member data, no Production
  deploy, and — the only potentially-relevant clause — "no material
  product, pricing, business, architecture, or scope change." Using an
  unmodified, dynamically-imported LGPL-3.0-only library as a
  server-side/test dependency, with no distribution of a modified copy
  of the library itself, is the standard use case LGPL is designed to
  permit without imposing share-back obligations on the depending
  project's own proprietary code (this is the same distinction that
  makes LGPL meaningfully different from GPL/AGPL for this purpose).
  This is not a material business/architecture/scope change to Veyro.
- **`EIP_MIRROR.md`'s engineering standard** for dependencies: "Minimal,
  maintained, licensed/secure dependencies; pin/lock where appropriate;
  supply-chain scan; remove unused packages." Satisfied: single-purpose
  driver, actively maintained (official project, current release),
  licensed and disclosed, hash-pinned in `requirements-dev.lock.txt`
  per the existing `BUG-036` mechanism, scanned (OSV, this file and the
  prior report), no unused-package concern.
- **`TSD_MIRROR.md`'s "open-source license governance"** reference
  appears under a distinct future governance area (Vendor/Partner/
  Compliance Operations, GOV-03-R07-adjacent), not GOV-01/MOD-001's own
  scope — a later-module concern, not a MOD-001 blocking gate.

**Conclusion: no owner decision is required by this project's actual
governance documents.** Not manufacturing a blocker where policy is
already satisfied, per the governing mission's explicit instruction.

## One residual item, correctly left as disclosure, not escalated

The independent Slice-5 security review (P2-1, see
`knowledge/03-Modules/MOD-001/evidence/security/SLICE5-INDEPENDENT-REVIEW-2026-09-29.md`)
separately flagged that `psycopg[binary]` sits in runtime
`[project.dependencies]` in `backend/pyproject.toml` rather than a
`dev`/`test` extra, since its only current consumer is the test
harness. That is a packaging-scope observation, not a licensing/
governance gap, and does not change the conclusion above — recorded
there, not duplicated as a second qualification blocker here.
