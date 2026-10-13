# M1-C-06 C09-X item 3 — default global allowlist non-vacuity (CAP-009 gitleaks 8.30.1) — 2026-10-09

Implementation evidence (Sonnet, operation `9beffd75-bd69-42b9-aa7d-7097c9b92399`). It is **not** a capability approval, a scenario result, a CI result, or a real-tree scan. It closes only the evidence gap of determination §5.2 / §10.1 item 3 (`M1-C-06-CAP-REAL-SCOPE-EXTENSION-DETERMINATION-2026-10-09.md`) for mandatory GOV-01-R03.

## Isolation
Every scanner invocation was `gitleaks dir` against a disposable pytest `tmp_path` tree (or, for the path-species probe, a `mktemp` tree under `/tmp`), cwd also outside the repository. No Veyro path, copy of a Veyro file, Git index or history was a target. Homebrew gitleaks was not used. The planted value is the runtime-assembled `EXAMPLE_NOT_A_REAL_KEY` placeholder; `--redact=100`; the test asserts the value is absent from the report and both streams. Output below is value-free.

## Binary identity (verified before use)
- Archive `gitleaks_8.30.1_darwin_arm64.tar.gz` (upstream release asset, downloaded into a fresh empty directory): SHA-256 `b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5` — equals the registry pin; checked before extraction.
- Contained binary SHA-256 `ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f` — equals the eligible-executable pin (CAP-009 content_hash cell); `gitleaks version` = `8.30.1`. The test re-verifies this digest on every run via `$VEYRO_GITLEAKS_BIN` and fails closed on mismatch.

## Observed path-species exclusion (shipped default config, no `--config`)
Probe: the placeholder planted in one synthetic file per path; scan exit code with `--exit-code 42` (42 = detected, 0 = clean).

| Synthetic path | rc | Meaning |
|---|---|---|
| `ctrl/p.py` | 42 | detected (control) |
| `node_modules/p.py` | 0 | **excluded** |
| `backend/.venv/lib/python3.14/site-packages/p.py` | 0 | **excluded** |
| `yarn.lock`, `poetry.lock` | 0 | **excluded** |
| `a.docx`, `a.png` | 0 | **excluded** |
| `vendor/p.py` | 42 | NOT excluded |
| `requirements.lock.txt` | 42 | NOT excluded |
| `x.dist-info/METADATA` | 42 | NOT excluded |

**Observed mismatch with the earlier candidate species list (recorded, not corrected here):** the determination §5.2 (inherited from the first determination §3 item 4) names `vendor/`, `*.dist-info` and "lock files" as excluded. In the pinned 8.30.1 binary, `vendor/`, `*.dist-info` and a `*.lock.txt` file are **not** excluded under this probe; `node_modules/`, venv `lib/pythonX.Y` trees, `yarn.lock`/`poetry.lock`, `.docx` and image extensions are. The species list is therefore neither a superset nor an exact match of the observed set; the table above is the observed lower bound for the probed paths only (probe was not exhaustive: `.mypy_cache/`, `.git`, `gitleaks.toml`, other binary/font extensions were not probed).

## Test added
`tools/tests/test_gitleaks_governed_qualification.py::test_default_global_allowlist_misses_planted_placeholder_and_manifest_declares_it`, parametrized over `node_modules/p.py` and `p.docx`. For each case it:
1. plants the placeholder at `ctrl/p.py` and proves detection in the default shape and in the governed shape (`_governed_scan`) — the unsuppressed control, so the later miss is caused by the path;
2. removes the control and plants the same content at the excluded path (non-empty file);
3. shows the default shape returns rc 0 / zero findings **and** the governed shape also returns rc 0 / zero findings (the wrapper's non-empty-file pre-check passes, so this is a vacuous pass produced by the allowlist, indistinguishable at the exit code from a clean scan);
4. reads `tools/governed_scanner_targets.json` and asserts the declared-exclusion set is non-empty, its count matches, and — for the `.docx` species — it equals exactly the tracked `.docx` paths; for the `node_modules/` species it asserts no tracked path belongs to that species.

No wrapper, workflow, manifest or policy file was changed.

## C09-X item 3 branch chosen: **out of coverage, declared**
The governed configuration does **not** detect the planted placeholder in an allowlisted path (governed flags change suppression surfaces, not the global allowlist). The honest branch is therefore "declared out of coverage with the affected path set". The reviewed target manifest `tools/governed_scanner_targets.json` already records this exclusion species: `declared_allowlist_excluded` lists the four tracked `.docx` paths (`Gym_OS_Master_Product_Blueprint_v1_English.docx`, `Veyro_Engineering_Implementation_Plan_v1.4.1_English_FINAL_APPROVED_GOVERNING_BASELINE.docx`, `Veyro_Technical_System_Design_v1.4.1_English_FINAL.docx`, `veyro-product-experience-design/project/uploads/Gym_OS_Master_Product_Blueprint_v1_English.docx`), and the test verifies that set equals the tracked `.docx` set.

A zero-finding scan must **not** be read as complete secret coverage. Residual gaps this record does not close: (a) the manifest's note says the species list was recorded from the determination rather than derived from the shipped config; this run derived the `.docx` species empirically and found other species in that list (`vendor/`, `*.dist-info`, lock-file text names) not excluded, while the tracked set contains no `node_modules/`, venv, `yarn.lock`/`poetry.lock` or image paths to declare (image check was not asserted); (b) the "registry row enumerates the excluded path set" half of item 3 is not done here (registry changes are out of scope for this task); (c) the probe was non-exhaustive.

## Focused result
- `VEYRO_GITLEAKS_BIN=<verified binary> backend/.venv/bin/python -m pytest -p no:cacheprovider tools/tests/test_gitleaks_governed_qualification.py -k "allowlist or pinned"` → **3 passed** (binary pin + two parametrized cases).
- Whole governed-qualification file with the same binary → **14 passed** (12 pre-existing + 2 new parametrized cases).
- Test file SHA-256 after change: `f6806c96114dac018d719c97ee6a4ea4fa5f6eab2bc19886b1f60f0240b262c7` (the CAP-009 registry row still cites the earlier hash `cb82662f…8a5725`; not updated — registry out of scope).

No capability approval, scenario promotion or policy change is claimed.
