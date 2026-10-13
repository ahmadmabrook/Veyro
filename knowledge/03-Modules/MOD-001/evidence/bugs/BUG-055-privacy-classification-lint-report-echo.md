---
doc: BUG-055
module: MOD-001
status: FIXED_LOCAL_AWAITING_SHARED_ASSURANCE
priority: P2
requirement: GOV-01-R03
scenarios: SCN-MOD001-043
---

# BUG-055 — Privacy-classification candidate echoes untrusted manifest strings

Independent post-implementation probe under runner `ea8eefe9-3e55-4ea7-a006-bf4074e6903b` found a concrete report-echo defect in `tools/validate_privacy_classification.py`. The lint denies malformed/unclassified entries, but `render_report` prints attacker-controlled `field_id` and unexpected entry key names. A synthetic sentinel `SYNTHETIC_DO_NOT_ECHO_VALUE_67382` used as either an unclassified `field_id` or an unexpected key is present in the DENY report in both cases. The code's stated “value-free by construction” invariant is therefore false: arbitrary manifest strings can occupy identifier/key slots and reach output. This is a local fixture/report confidentiality defect, not an observed real-data exposure.

Reproducer: construct an explicitly synthetic manifest with vocabulary `['Restricted']`, then set one field to `{'field_id': sentinel}`; separately set one field to `{'field_id': 'fixture', 'classification': 'Restricted', sentinel: 'value'}`. Call `lint_manifest` and `render_report`; both DENY, both contain the sentinel. The focused suite still passes 5/5 because it tests a sentinel only in an unexpected key's *value*, not in the key or field identifier. Source SHA-256 `c89dce73706c6f2f03de51dc9494db7b7f179bf02462e9d57d1f238cdaa7bf3a`; tests SHA-256 `f2d1cd934784ffe815fd1f904a3e81eee258a8e0a3ac9e311675d467e80668db`.

**Status: FIXED LOCALLY, AWAITING SHARED ASSURANCE (2026-10-09).** Runner `1114b1f8-824d-426e-bdb6-67124011f2ee` changed reports to stable field indices/counts and constant codes instead of manifest-derived identifiers, labels or unexpected/duplicate key names. Independent replay of both original sentinel probes: named DENY retained and sentinel absent; focused pytest **6/6**, Ruff check/format and compile **PASS**. Source SHA-256 `c1da15a90c382900c45733cedffcd03cdfcd785030eadc6d22b29197aa1d0802`; tests SHA-256 `69856614a0f83c6a605fbfba59b600d7417569cd293959e737d65140c15f4b35`. SCN-043 remains NOT EXECUTED; CI and shared C06 assurance remain pending. No new plan operation or review entitlement was created.
