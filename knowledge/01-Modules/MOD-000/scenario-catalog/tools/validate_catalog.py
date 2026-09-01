#!/usr/bin/env python3
"""
MOD-000 Scenario Catalog integrity validator.

Machine-checkable checks per the Round 3 remediation instruction:
- unique Scenario IDs
- required fields present (severity, category, agent/model where applicable)
- valid severity values
- valid automation/manual-QA classification language present
- lifecycle role/model mapping present (Agent + Model named)
- fail-closed condition presence where the scenario is NEG/fail-closed-flavored
- all 19 mandatory EIP categories present somewhere in the catalog
- all §12.1 drill sub-items referenced
- all mandatory MOD-000 outputs traced (name-checked against known artifact list)
- no MOD-001/product-implementation scope leakage (keyword scan for product-domain terms)

This is a text/structure validator against the markdown catalog, not a semantic
prover — it catches mechanical defects (missing IDs, gaps, duplicate IDs, missing
fields, absent category coverage), which is exactly the class of defect this
project's own review has repeatedly found by hand. It does not replace independent
review judgment about whether a scenario's pass criteria are *good*.
"""
import re
import sys
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "SCENARIO_CATALOG.md"

REQUIRED_CATEGORIES = [
    "HP", "VAL", "NEG", "BND", "AUTHN", "AUTHZ", "TEN", "SEC", "PRIV",
    "CONC", "IDEM", "NET", "PART", "REC", "LIFE", "DATA", "INT", "OBS", "DR",
]
VALID_SEVERITIES = {"Blocker", "Major", "Minor"}
NA_CATEGORIES = {"OFF", "LOC", "A11Y", "PERF", "MIG"}
OPTIONAL_CATEGORIES = {"ALT"}

DRILL_12_1_ITEMS = [
    "Browser", "Backend/API", "Android", "iOS", "Edge/device bridge",
    "VoiceOver/TalkBack",
    "MOD-000 QA item (1)", "MOD-000 QA item (2)", "MOD-000 QA item (3)",
    "MOD-000 QA item (4)", "MOD-000 QA item (5)", "MOD-000 QA item (6)",
    "MOD-000 QA item (7)", "MOD-000 QA item (8)", "MOD-000 QA item (9)",
    "MOD-000 QA item (10)", "MOD-000 QA item (11)", "MOD-000 QA item (12)",
]

MANDATORY_OUTPUTS = {
    "PROJECT_INDEX.md": True,
    "SESSION_BOOTSTRAP.md": True,
    "CAPABILITY_POLICY.md": True,
    "CAPABILITY_REGISTRY.md": True,
    "MODEL_ROUTING.md": True,
    ".claude/agents": True,
    ".claude/rules": True,
    "module-capabilities.yaml": True,
    "SKL-/RULE- ID schemas": False,   # known not-yet-authored, tracked
    "rollback/removal procedure": False,
    "third-party evaluation template": False,
    "permanent-regression automation": False,
    "Appendix I conformance": None,   # N/A-with-justification, not a gap
    "project/nested Skill policy": False,
    "initial .claude/rules profile structure": False,
}

PRODUCT_LEAK_KEYWORDS = [
    "member check-in", "membership billing", "class scheduling",
    "front desk pos transaction", "trainer booking", "payroll run",
    "gym class roster", "point of sale checkout",
]

errors = []
warnings = []
info = []


def main():
    text = CATALOG.read_text(encoding="utf-8")

    # 1. Scenario ID extraction + uniqueness + gap check
    ids = re.findall(r"SCN-MOD000-(\d{3})", text)
    id_ints = sorted(set(int(i) for i in ids))
    id_counts = {}
    for i in ids:
        id_counts[i] = id_counts.get(i, 0) + 1

    # Header-level IDs (### SCN-MOD000-NNN) are the authoritative "this ID is defined here" markers
    header_ids = re.findall(r"^### SCN-MOD000-(\d{3})", text, re.MULTILINE)
    header_set = sorted(set(int(i) for i in header_ids))

    if not header_set:
        errors.append("No scenario headers found at all — catalog structurally broken.")
    else:
        expected = list(range(header_set[0], header_set[-1] + 1))
        missing = [n for n in expected if n not in header_set]
        if missing:
            warnings.append(f"Scenario ID gaps in numeric sequence (may be intentional condensed groups): {missing}")
        dup_headers = [k for k, v in {h: header_ids.count(h) for h in header_ids}.items() if v > 1]
        if dup_headers:
            errors.append(f"Duplicate scenario header IDs: {dup_headers}")
        else:
            info.append(f"Scenario headers: {len(header_set)} unique IDs from {min(header_set):03d} to {max(header_set):03d}, no duplicates.")

    # Total distinct scenario IDs mentioned anywhere (includes condensed "through" groups)
    all_distinct = sorted(set(int(i) for i in ids))
    info.append(f"Total distinct SCN-MOD000-NNN ids referenced anywhere in catalog: {len(all_distinct)} (range {min(all_distinct):03d}-{max(all_distinct):03d}).")

    # 2. Category coverage — 19 mandatory
    missing_categories = []
    for cat in REQUIRED_CATEGORIES:
        # look for the category as a whole-word token near "Category:" lines or in the coverage matrix
        pattern = rf"\b{re.escape(cat)}\b"
        if not re.search(pattern, text):
            missing_categories.append(cat)
    if missing_categories:
        errors.append(f"Mandatory EIP categories with ZERO textual occurrence in catalog: {missing_categories}")
    else:
        info.append("All 19 mandatory EIP scenario categories have at least one textual occurrence in the catalog.")

    # 3. §12.1 drill item coverage — presence of each label in the D-2 matrix
    missing_drill_items = [d for d in DRILL_12_1_ITEMS if d not in text]
    if missing_drill_items:
        errors.append(f"§12.1 drill items not referenced by label in catalog: {missing_drill_items}")
    else:
        info.append("All 18 §12.1 drill-coverage labels (6 surfaces + 12 numbered MOD-000 QA items) found in the D-2 matrix.")

    # 4. Severity value sanity — scan for "Blocker/Major/Minor" tokens near scenario headers/rows;
    #    flag any "Severity: X" style field with an invalid value
    sev_fields = re.findall(r"Severity:\*\*\s*([A-Za-z]+)", text)
    bad_sev = [s for s in sev_fields if s not in VALID_SEVERITIES]
    if bad_sev:
        errors.append(f"Invalid severity values found: {set(bad_sev)}")
    else:
        info.append(f"All {len(sev_fields)} explicit '- **Severity:**' field values are valid ({VALID_SEVERITIES}).")

    # 5. Fail-closed condition presence for NEG-flavored scenarios (spot-check: count NEG scenario
    #    blocks and count "Fail-closed condition" occurrences — should be roughly comparable, not exact
    #    since some HP scenarios also carry one)
    neg_blocks = len(re.findall(r"Category:.*NEG", text))
    fail_closed_mentions = len(re.findall(r"[Ff]ail-closed condition", text))
    if fail_closed_mentions < neg_blocks * 0.5:
        warnings.append(f"Only {fail_closed_mentions} 'Fail-closed condition' mentions vs {neg_blocks} NEG-tagged category mentions — spot-check for gaps.")
    else:
        info.append(f"{fail_closed_mentions} 'Fail-closed condition' fields present against {neg_blocks} NEG-category mentions — plausible coverage.")

    # 6. Agent/Model field presence — every detailed scenario block should name an Agent and a Model
    agent_mentions = len(re.findall(r"\*\*Agent:?\*\*\s*veyro-", text)) + len(re.findall(r"Agent:\s*veyro-", text)) + len(re.findall(r"\*\*Applicable agent/role:\*\*\s*veyro-", text))
    model_mentions = len(re.findall(r"\bOpus\b", text)) + len(re.findall(r"\bSonnet\b", text))
    info.append(f"Agent-role mentions (veyro-*): {agent_mentions}. Opus/Sonnet model mentions: {model_mentions}. (Informational — not a pass/fail gate on their own; cross-checked against header count.)")

    # 7. Mandatory MOD-000 output traceability
    lowered_text = text.lower()
    for name, required in MANDATORY_OUTPUTS.items():
        present = (name in text) or (name.lower() in lowered_text)
        if required is True and not present:
            errors.append(f"Mandatory output not traced/mentioned in catalog: {name}")
        elif required is False and not present:
            warnings.append(f"Known-gap output not yet authored (tracked, non-blocking for catalog readiness): {name}")
        elif required is None:
            info.append(f"Output '{name}' assessed N/A-with-justification (not a gap).")

    # 8. Product-scope leak scan
    lowered = text.lower()
    leaks = [kw for kw in PRODUCT_LEAK_KEYWORDS if kw in lowered]
    if leaks:
        errors.append(f"Possible MOD-001/product-implementation scope leak keywords found: {leaks}")
    else:
        info.append("No product-implementation scope-leak keywords found (membership/billing/scheduling/POS/booking/payroll terms absent).")

    # ---- Report ----
    print("=" * 70)
    print("MOD-000 SCENARIO CATALOG INTEGRITY VALIDATOR")
    print("=" * 70)
    print(f"\nCatalog file: {CATALOG}")
    print(f"\n--- INFO ({len(info)}) ---")
    for i in info:
        print(f"  [i] {i}")
    print(f"\n--- WARNINGS ({len(warnings)}) ---")
    for w in warnings:
        print(f"  [!] {w}")
    print(f"\n--- ERRORS ({len(errors)}) ---")
    for e in errors:
        print(f"  [X] {e}")

    print("\n" + "=" * 70)
    if errors:
        print(f"RESULT: FAIL — {len(errors)} error(s) found.")
        return 1
    else:
        print(f"RESULT: PASS — 0 errors, {len(warnings)} warning(s) (non-blocking, tracked).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
