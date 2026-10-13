# M1-C-06 — SCN-033/065 local personal-data pattern inventory (2026-10-09)

Status: **LOCAL INVENTORY ONLY; NO SCENARIO PASS OR INDEPENDENT PRIVACY VERDICT.** This is a distinct R03 data-boundary step under M1-C-06. It does not change a scanner capability, run CI, consume review authority, or modify product code.

## Scope and method

Enumerated 1,155 Git-tracked plus non-ignored untracked paths with `git ls-files -co --exclude-standard -z` on the current working tree. The initial pass scanned 1,150 ordinary text files. **Correction, same date:** despite the original wording, that pass skipped rather than extracted four DOCX files. A bounded follow-up extracted their `word/*.xml` with Python's standard-library `zipfile`, bringing the parsed-file count to 1,154; one binary thumbnail remains omitted. No ignored local raw credential file was opened. Patterns counted email-shaped strings, Jordanian `+962 7[789]` phones, `NNN-NN-NNNN` SSNs, and broad 13–19-digit card-shaped sequences. Results below are **counts, not values**. The card-shaped regex is intentionally broad and does not imply card validity or personal data.

| Pattern | Raw matches | Interpretation at this boundary |
|---|---:|---|
| Email-shaped | 181 | 31 inside MOD-001 evidence use reserved example domains; 60 MOD-001 matches use non-reserved domains, of which 57 are repeated `e.com` fixture-shaped references in SCN-070 evidence, two are `pytest.fixture` matches, and one has `github.com` domain. These are not a verified zero-real-data finding. |
| Jordanian phone-shaped | 26 | All outside the MOD-001 evidence subtree; the pre-existing design-bundle mockup was previously identified as containing plausible-number examples. The pattern cannot establish whether any mailbox/number is real. |
| SSN-shaped | 0 | No match in the scanned material. |
| Broad card-shaped | 216 | The initial 208 text-file matches plus eight DOCX XML matches. Mostly hash/numeric fragments are likely; not individually adjudicated and not a zero-real-data finding. |

The four DOCX files contributed **zero** email, Jordanian-phone or SSN matches. This correction changes only the broad card-shaped count; it does not create a scenario verdict. The initial 208 count is preserved here as the observed first-pass result, not silently treated as complete.

The existing MOD-000 `DATA_CLASSIFICATION_AUDIT.md` correction already discloses plausible-looking demo contacts in the frozen design baseline. This inventory neither republishes their values nor overwrites that finding. It also does not assert that all untracked/ignored or binary content has been classified.

## Exact remaining criterion

SCN-MOD001-033 requires a **real repo-wide pattern scan and classification of matches** against MOD-001's new files, ending in zero real personal data. SCN-MOD001-065 separately requires manual qualified privacy judgment that each data fixture is synthetic. The scan portion is now observed, but the match classification/manual assurance remains; both scenarios stay **NOT EXECUTED / not promoted**. Next legal C06 step: use this non-value inventory to perform bounded file-context classification of MOD-001 candidates, preserving the privacy reviewer boundary and without treating a regex non-match as evidence of absence.
