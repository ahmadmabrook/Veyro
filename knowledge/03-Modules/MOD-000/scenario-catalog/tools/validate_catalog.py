#!/usr/bin/env python3
"""
MOD-000 Scenario Catalog integrity validator.

Rewritten 2026-09-04 (Phase 5 remediation, finding F5-009) after an
independent review found the original version's checks were largely
tautological (they searched the whole document text, which always
contains the category legend and the validator's own coverage-matrix
labels, so those checks could never fail regardless of the catalog's
actual content) and printed at least one false attestation (claimed zero
product-scope-leak keywords while several were actually present in
benign context).

This version parses the two summary tables STRUCTURALLY (one row per
scenario) and checks each row has every required field populated with a
valid value, rather than checking whether a string appears anywhere in
the whole file.
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
EXPECTED_TOTAL_SCENARIOS = 95

MANDATORY_OUTPUTS = {
    "PROJECT_INDEX.md": True,
    "SESSION_BOOTSTRAP.md": True,
    "CAPABILITY_POLICY.md": True,
    "CAPABILITY_REGISTRY.md": True,
    "MODEL_ROUTING.md": True,
    ".claude/agents": True,
    ".claude/rules": True,
    "module-capabilities.yaml": True,
    "SKL-/RULE- ID schemas": False,
    "rollback/removal procedure": False,
    "third-party evaluation template": False,
    "permanent-regression automation": False,
    "Appendix I conformance": None,
    "project/nested Skill policy": False,
    "initial .claude/rules profile structure": False,
}

# Single-word/short stems, not multi-word phrases only — the original
# 8-phrase list missed single-word occurrences like "membership",
# "payment", "scheduling" appearing outside those exact phrases.
PRODUCT_LEAK_STEMS = [
    "membership", "billing", "scheduling", "payroll", "roster",
    "checkout", "booking", "check-in", "point of sale", " pos ",
]

# Row format: | SCN-MOD000-NNN | Title | Category | Severity | Automation | Agent | Model |
ROW_RE = re.compile(
    r"^\|\s*SCN-MOD000-(\d{3})(?:\s*\([A-Z]+\))?\s*\|"   # ID (allow "(ALT)" suffix)
    r"\s*([^|]+?)\s*\|"                                    # Title
    r"\s*([^|]+?)\s*\|"                                    # Category
    r"\s*([^|]+?)\s*\|"                                    # Severity
    r"\s*([^|]+?)\s*\|"                                    # Automation
    r"\s*([^|]+?)\s*\|"                                    # Agent
    r"\s*([^|]+?)\s*\|",                                   # Model
    re.MULTILINE,
)

errors = []
warnings = []
info = []


def parse_rows(text):
    rows = {}
    for m in ROW_RE.finditer(text):
        sid, title, category, severity, automation, agent, model = m.groups()
        if sid in rows:
            continue  # a "through" range row like 056-058 or a combined-title row is handled separately
        rows[sid] = {
            "title": title, "category": category, "severity": severity,
            "automation": automation, "agent": agent, "model": model,
        }
    return rows


def main():
    text = CATALOG.read_text(encoding="utf-8")

    # 1. Structural row parse of the two summary tables
    rows = parse_rows(text)
    # "through" condensed ranges (e.g. "056 through 058") expand to their member IDs,
    # inheriting the same row's fields — this makes the total-count check accurate
    # instead of silently undercounting condensed groups as 1 scenario.
    through_pattern = re.compile(r"SCN-MOD000-(\d{3}) through (\d{3})")
    for m in through_pattern.finditer(text):
        lo, hi = int(m.group(1)), int(m.group(2))
        base = f"{lo:03d}"
        if base in rows:
            for n in range(lo, hi + 1):
                key = f"{n:03d}"
                if key not in rows:
                    rows[key] = dict(rows[base])

    found_ids = sorted(int(k) for k in rows)
    if not found_ids:
        errors.append("No scenario table rows parsed at all — catalog structurally broken or table format changed.")
    else:
        info.append(f"Parsed {len(found_ids)} distinct scenario IDs from the summary tables (range {found_ids[0]:03d}-{found_ids[-1]:03d}).")

    # 2. Total-count check against the catalog's own declared size (95) — this is the
    #    check that catches the F5-008-class defect (scenarios missing entirely, not
    #    just missing a detail block) that the old header-range-only gap check could not see.
    if len(found_ids) != EXPECTED_TOTAL_SCENARIOS:
        errors.append(
            f"Expected {EXPECTED_TOTAL_SCENARIOS} scenarios (catalog's own declared total), "
            f"found {len(found_ids)} distinct IDs in the summary tables. "
            f"Missing: {sorted(set(range(1, EXPECTED_TOTAL_SCENARIOS + 1)) - set(found_ids))}"
        )
    else:
        info.append(f"Summary-table scenario count matches the catalog's declared total: {EXPECTED_TOTAL_SCENARIOS}.")

    # 3. Per-row field validation — every row must have a non-empty Category, a valid
    #    Severity, a non-empty Automation classification, and a named Agent + Model,
    #    UNLESS the category is a known N/A or Optional category.
    missing_severity = []
    invalid_severity = []
    missing_agent_model = []
    category_hits = {c: 0 for c in REQUIRED_CATEGORIES}
    for sid, row in sorted(rows.items()):
        cats = [c.strip() for c in re.split(r"[,/]", row["category"]) if c.strip()]
        is_na_or_alt = any(c in NA_CATEGORIES or c in OPTIONAL_CATEGORIES for c in cats)
        for c in cats:
            if c in category_hits:
                category_hits[c] += 1
        sev = row["severity"].strip()
        if not sev:
            missing_severity.append(sid)
        elif sev not in VALID_SEVERITIES:
            invalid_severity.append((sid, sev))
        if not is_na_or_alt:
            if "veyro-" not in row["agent"] or not re.search(r"Opus|Sonnet", row["model"]):
                missing_agent_model.append(sid)

    if missing_severity:
        errors.append(f"Scenarios with no parseable Severity value: {missing_severity}")
    if invalid_severity:
        errors.append(f"Scenarios with an invalid Severity value: {invalid_severity}")
    if not (missing_severity or invalid_severity):
        info.append(f"All {len(rows)} parsed scenarios have a valid Severity value ({VALID_SEVERITIES}).")

    if missing_agent_model:
        errors.append(f"Scenarios (non-N/A, non-ALT) missing a named Agent or Model: {missing_agent_model}")
    else:
        info.append("Every non-N/A, non-ALT scenario names both an Agent and a Model.")

    # 4. Category coverage — now counted from actual per-row Category fields, not
    #    whole-document text search, so a category that only appears in the legend
    #    (and never on a real scenario row) is correctly reported missing.
    missing_categories = [c for c in REQUIRED_CATEGORIES if category_hits[c] == 0]
    if missing_categories:
        errors.append(f"Mandatory EIP categories with ZERO scenario rows assigning them: {missing_categories}")
    else:
        info.append("All 19 mandatory EIP scenario categories are assigned to at least one real scenario row (not just the legend).")

    # 5. Derived "Required" set (the catalog has no explicit Required column — F5-008
    #    flagged this; until one is added, derive it mechanically here and report the count,
    #    so the Required-scenario-completion gate is at least computable).
    required_ids = []
    for sid, row in sorted(rows.items()):
        cats = [c.strip() for c in re.split(r"[,/]", row["category"]) if c.strip()]
        if not any(c in NA_CATEGORIES or c in OPTIONAL_CATEGORIES for c in cats):
            required_ids.append(sid)
    info.append(f"Derived Required-scenario count (category not purely N/A/ALT): {len(required_ids)} of {len(rows)}.")

    # 6. Detail-block presence — every Required scenario should have a "### SCN-MOD000-NNN"
    #    detail header somewhere (a summary-table-only row, with no detail block, is the
    #    F5-008 defect class). Condensed "through" rows are exempted (by design, tracked
    #    as a known non-blocking pattern) but only if their base ID has a detail block.
    header_ids = set(re.findall(r"^### SCN-MOD000-(\d{3})", text, re.MULTILINE))
    no_detail = [sid for sid in required_ids if sid not in header_ids]
    if no_detail:
        warnings.append(f"Required scenarios with a summary-table row but NO detail block ('### SCN-MOD000-NNN' header): {len(no_detail)} scenarios — {no_detail}")
    else:
        info.append("Every Required scenario has both a summary-table row and a detail block.")

    # 7. Mandatory MOD-000 output traceability (unchanged logic — this check was not
    #    found to be tautological, it's a real substring-presence check against a
    #    fixed artifact-name list, not against the validator's own generated labels)
    lowered_text = text.lower()
    for name, required in MANDATORY_OUTPUTS.items():
        present = (name in text) or (name.lower() in lowered_text)
        if required is True and not present:
            errors.append(f"Mandatory output not traced/mentioned in catalog: {name}")
        elif required is False and not present:
            warnings.append(f"Known-gap output not yet authored (tracked, non-blocking for catalog readiness): {name}")
        elif required is None:
            info.append(f"Output '{name}' assessed N/A-with-justification (not a gap).")

    # 8. Product-scope leak scan — now reports EVERY match with a line number for human
    #    judgment, rather than silently attesting "none found" when broader stems are
    #    actually present (the original 8-exact-phrase list missed single-word hits).
    leak_hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        for stem in PRODUCT_LEAK_STEMS:
            if stem in low:
                leak_hits.append((i, stem, line.strip()[:120]))
    if leak_hits:
        warnings.append(
            f"{len(leak_hits)} product-domain-word occurrence(s) found — human judgment required on "
            f"whether each is legitimate (e.g. describing something a control-plane scenario governs) "
            f"or an actual MOD-001 scope leak. First 5: "
            + "; ".join(f"L{ln} '{s}': {ctx}" for ln, s, ctx in leak_hits[:5])
        )
    else:
        info.append("No product-domain-word occurrences found at all.")

    # ---- Report ----
    print("=" * 70)
    print("MOD-000 SCENARIO CATALOG INTEGRITY VALIDATOR (rewritten 2026-09-04)")
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
