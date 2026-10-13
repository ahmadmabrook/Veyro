# M1-C-06 — upstream provenance pins for gitleaks 8.30.1 and Ruff 0.16.9 (2026-10-09)

Status: **PROVENANCE MATERIAL CAPTURED. Not a qualification, registration, or approval.**
Operation `8014044d-ce14-488f-bdbe-c97db2b9a563`, subgoal `M1-C-06-UPSTREAM-PROVENANCE-PINS`,
execution role `IMPLEMENTATION` (`claude-sonnet-5-5`). Implements §7 item 2 of
`M1-C-06-CAP-ORDERING-PLAN-DECISION-2026-10-09.md` (step-A provenance/version/`content_hash`
material, per `CAPABILITY_POLICY.md` stage 5 / supply-chain fields). Read for this task:
`CAPABILITY_POLICY.md`, the ordering decision, `M1-C-06-GITLEAKS-SYNTHETIC-QUALIFICATION-2026-10-09.md`,
`M1-C-06-SCANNER-CAPABILITY-ROUTE-2026-10-09.md`, `GATE2-R1-F19-PINNED-RUFF-CONFIG-2026-10-06.md`.
No dedicated Ruff synthetic-drill note exists yet; the only Ruff note is the F19 config note.

## Boundary

- Only network reads of public upstream metadata (GitHub API / release downloads / raw LICENSE) and
  one hash-only download. All downloads went into a fresh `mktemp -d` directory (`/tmp/m1c06-prov.*`),
  outside the repo. The gitleaks tarball was hashed only: **not extracted, not executed**.
- No scanner was run on any file. The only tool invocations were `gitleaks version`,
  `ruff --version` and `pip show ruff` (version reads, no scan targets).
- No registry, BUG_REGISTRY, code, test, CI/workflow, scenario, plan, or remote change. No CAP-009 /
  CAP-010 row. `review_status` stays unassigned; `approved_by` empty. Nothing here is a stage-4
  evaluation or an approval.

## 1. gitleaks v8.30.1 (upstream: `gitleaks/gitleaks`)

| Item | Value |
|---|---|
| Release page | https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1 |
| Release API | `https://api.github.com/repos/gitleaks/gitleaks/releases/tags/v8.30.1` → HTTP 200 |
| Release state | `tag_name` `v8.30.1`, `draft` false, `prerelease` false, `immutable` false, `published_at` 2026-03-21T02:17:58Z |
| Tag → commit | `refs/tags/v8.30.1` → commit `83d9cd684c87d95d656c1458ef04895a7f1cbd8e` (`git/ref/tags/v8.30.1`, HTTP 200) |
| LICENSE source | https://raw.githubusercontent.com/gitleaks/gitleaks/v8.30.1/LICENSE → HTTP 200, 1069 bytes |
| LICENSE identity | "MIT License", "Copyright (c) 2019 Zachary Rice"; SHA-256 `e3884b252b3bfc045e55be43a34d1e80da070bc6f804ac95bf4660e97d62ebc6`; `git hash-object` `3c270b36c539ca8fbc4cc1017d3cbb7be1e44bbc` = contents-API blob sha (match) |

### Linux x64 release asset (the artifact CI would execute)

| Item | Value |
|---|---|
| Asset name | `gitleaks_8.30.1_linux_x64.tar.gz` |
| URL | https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz (HTTP 200 after redirect to `release-assets.githubusercontent.com`; the signed redirect query string is deliberately not recorded) |
| Size | **8230402** bytes — equals release-API `size` and downloaded byte count |
| **SHA-256 (computed locally)** | **`551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`** |
| Release-API `digest` | `sha256:551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` (match) |
| Official checksum file | `gitleaks_8.30.1_checksums.txt` (999 bytes; SHA-256 `061476c21adaf5441516f96f185c1a4706a83cd6329b9b38762271b3d4a52fae`, equals its API digest) — URL https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_checksums.txt |
| Checksum-file line | `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb  gitleaks_8.30.1_linux_x64.tar.gz` |
| Comparison | `grep ' gitleaks_8.30.1_linux_x64.tar.gz$' gitleaks_8.30.1_checksums.txt \| shasum -a 256 -c -` → **`gitleaks_8.30.1_linux_x64.tar.gz: OK`** |

Three independent statements agree: locally computed hash, upstream checksum file, and GitHub's
release-asset digest. The checksum file is itself served from the same release, so it detects
corruption/substitution of the tarball alone, not a compromise of the whole release; no upstream
signature/attestation file (`.sig`, `.pem`, provenance) is in the 8.30.1 asset list, and none was
verified.

Local binary (not a substitute for the above): Homebrew `gitleaks` 8.30.1,
`/opt/homebrew/Cellar/gitleaks/8.30.1/bin/gitleaks`, SHA-256
`052d18829513f92eb683b63cd15b34d845f9a7adec761fe26cd462eb3c771422`. This is the darwin arm64
build used for the local synthetic drill. It was not compared to the upstream darwin_arm64 asset
(`sha256:b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5`, from the release API),
because that would require extracting the tarball, which this task excludes. The two hashes are
different objects and are not claimed equal.

## 2. Ruff 0.16.9 (upstream: `astral-sh/ruff`)

| Item | Value |
|---|---|
| Release page | https://github.com/astral-sh/ruff/releases/tag/0.16.9 |
| Release API | `https://api.github.com/repos/astral-sh/ruff/releases/tags/0.16.9` → HTTP 200 |
| Release state | `tag_name` `0.16.9`, `draft` false, `prerelease` false, **`immutable` true**, `published_at` 2026-09-24T20:38:52Z |
| Tag → commit | `refs/tags/0.16.9` → commit `0be08a206f9c3180afd3e93bcc792ed5cb1f4db1` (equals release `target_commitish`) |
| LICENSE source | https://raw.githubusercontent.com/astral-sh/ruff/0.16.9/LICENSE → HTTP 200, 20731 bytes |
| LICENSE identity | Begins "MIT License", "Copyright (c) 2022 Charles Marsh", followed by bundled third-party license texts (one file, 20731 bytes); SHA-256 `2597d854122b77ddc71971564ca2350a37608575ce324adc5650a2b2051c8f18`; `git hash-object` `655a0c76fc5539b2f8e63b673741a5fd0e0c5799` = contents-API blob sha (match) |
| Installed here | `backend/.venv/bin/ruff --version` → `ruff 0.16.9`; `pip show ruff` → `Version: 0.16.9` |

Linux release asset, recorded from upstream only (not downloaded or hashed by this task, since
the instruction covered the gitleaks asset only):

| Item | Value |
|---|---|
| Asset | `ruff-x86_64-unknown-linux-gnu.tar.gz`, 10016146 bytes |
| Release-API `digest` | `sha256:1bfbb819b5d4f9af501748862276b60e412d336034d99387691a4d4bce7a6f13` |
| Upstream sidecar | `ruff-x86_64-unknown-linux-gnu.tar.gz.sha256` → `1bfbb819b5d4f9af501748862276b60e412d336034d99387691a4d4bce7a6f13  ruff-x86_64-unknown-linux-gnu.tar.gz` |
| Upstream `sha256.sum` | `1bfbb819b5d4f9af501748862276b60e412d336034d99387691a4d4bce7a6f13 *ruff-x86_64-unknown-linux-gnu.tar.gz` (the `sha256.sum` file's own SHA-256 is `def311fd…913cf`, equal to its API digest) |

The three upstream sources agree with each other. That is a consistency check among upstream
statements, not a locally recomputed hash.

### PyPI Linux wheel follow-up (same C06 operation, deterministic capture)

For the pip-installed CI route, queried `https://pypi.org/pypi/ruff/0.16.9/json`, downloaded
`ruff-0.16.9-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` from the file URL in
that release metadata into a disposable temporary directory, and hashed it without installing or
executing it. Downloaded size **10406494** bytes matched PyPI's size; computed SHA-256
**`a21713e629d3e5bdb2f5c2def1cc7f04f47fa8e1a7eb0571b4a28e1da64bc728`** matched
PyPI's `digests.sha256`. Source URL:
`https://files.pythonhosted.org/packages/bc/b8/9c543074918061abbefc3bd139bee22de35abedb00dde0f2d27288838962/ruff-0.16.9-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl`.
This pins the selected Linux x64 wheel, not the currently installed macOS wheel or an unverified
future CI platform. No scanner was run and no capability was approved.

## 3. Commands (reproducible)

```
curl -sS -L -H 'Accept: application/vnd.github+json' https://api.github.com/repos/gitleaks/gitleaks/releases/tags/v8.30.1
curl -sS -L -H 'Accept: application/vnd.github+json' https://api.github.com/repos/astral-sh/ruff/releases/tags/0.16.9
curl -sS -L https://api.github.com/repos/gitleaks/gitleaks/git/ref/tags/v8.30.1
curl -sS -L https://api.github.com/repos/astral-sh/ruff/git/ref/tags/0.16.9
curl -sS -L https://raw.githubusercontent.com/gitleaks/gitleaks/v8.30.1/LICENSE   ; shasum -a 256 ; git hash-object
curl -sS -L https://raw.githubusercontent.com/astral-sh/ruff/0.16.9/LICENSE       ; shasum -a 256 ; git hash-object
curl -sS -L -o gitleaks_8.30.1_linux_x64.tar.gz https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz
curl -sS -L -o gitleaks_8.30.1_checksums.txt   https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_checksums.txt
shasum -a 256 gitleaks_8.30.1_linux_x64.tar.gz gitleaks_8.30.1_checksums.txt
grep ' gitleaks_8.30.1_linux_x64.tar.gz$' gitleaks_8.30.1_checksums.txt | shasum -a 256 -c -
curl -sS -L https://github.com/astral-sh/ruff/releases/download/0.16.9/ruff-x86_64-unknown-linux-gnu.tar.gz.sha256
curl -sS -L https://github.com/astral-sh/ruff/releases/download/0.16.9/sha256.sum
```

All requests returned HTTP 200. Downloaded artifacts lived only in temp directories outside the
repo and were never extracted or executed.

## 4. Not claimed / residual gaps

- **Not a stage 4 or 7 act.** No source review, no rule-behaviour evaluation, no CAP-009/CAP-010
  row, no `content_hash` field written to any registry. The single Opus `veyro-security-reviewer`
  determination (step B) is still outstanding.
- **Ruff artifact boundary.** The project installs Ruff into `backend/.venv` (pip `Version: 0.16.9`),
  which is not the GitHub release tarball described above. The selected PyPI Linux x64 wheel is
  now locally hashed in the follow-up above. This does not verify the installed macOS wheel or
  constrain a future CI installation until the pinned wheel/hash is actually enforced there.
- **Hosting dependence.** All sources are GitHub-hosted, so the "official checksum" does not give
  independence from a GitHub-level compromise; no signature or attestation was verified for either
  project.
- **CI not run.** Nothing was executed on Linux; no claim about how a future workflow would fetch
  or verify the asset.
- SCN-MOD001-029, 094, 134, 135, 136 and the 13 C06 scenarios remain **NOT EXECUTED**; no
  GOV-01-R03/R04 criterion is closed. No paid service, real secret, or member data involved.
