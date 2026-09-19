#!/usr/bin/env python3
"""
Capability-governance manifest validator — generalized to ANY module
(MOD-001, `REQUIREMENTS.md` §3, "Capability-governance validation gates").

Authored 2026-09-19, MOD-001 implementation slice 2. Per `REQUIREMENTS.md`
§3: "Validate `.claude/agents`/`.claude/rules`/`.claude/skills`/
`module-capabilities.yaml`; reject cyclic capability dependencies,
overdue lifecycle reviews, manifests missing mandatory privileged-surface
Rules; require every Appendix H.2 rule family to resolve to an
Appendix H.3 content standard... Reuses MOD-000's
`validate_capabilities.py`/`CAPABILITY_REGISTRY.md` pattern — extend,
don't duplicate."

## The generalization problem this script solves

`knowledge/00-System/validate_capabilities.py` (MOD-000's own validator)
extracts dependency IDs with one hardcoded pattern:
`capability_id:\s*(CAP-\d+)`. That is MOD-000's manifest shape only — a
flat `capabilities:` list of `- capability_id: CAP-NNN` entries. MOD-001's
own real manifest
(`knowledge/03-Modules/MOD-001/evidence/module-capabilities.yaml`) has no
`capability_id:` field anywhere: it references capability/Rule IDs three
different ways (`required_rule_ids`, a list of `{id: RULE-NNN, path: ...,
status: ...}` objects; `capability_evidence_ids`, free-text prose
mentioning "RULE-001 through RULE-009"; `missing_capability_blockers`,
free text about bug IDs). A validator that only recognized MOD-000's exact
field shape would silently validate zero IDs against MOD-001's manifest —
0 found, false PASS — the opposite of the fail-closed posture this policy
requires.

This script generalizes by discovering ID literals directly: a
word-boundary regex, `\b(?:CAP|RULE|SKL)-\d+\b`, is run over the manifest's
*entire* raw text, not a schema-specific field extractor. This is the same
principle `REQUIREMENTS.md` §3 states explicitly for the sibling
`validate_scenario_matrix.py` tool ("MOD-001 must generalize
[`validate_catalog.py`] to validate *any* module's catalog"), applied
here to capability/Rule ID discovery instead of scenario-row discovery.

**Disclosed cost of this approach, one real one:** a bare mention of an ID
in unrelated prose (e.g. a sentence explaining *why* an ID was chosen, or
a summary line like "RULE-001 through RULE-009 — see...") is also picked
up and checked. This is harmless for the per-ID registration/approval/
field checks below (checks 2-6): re-checking an already-valid,
already-registered ID an extra time is a no-op — same PASS, not a new
error — and those checks are run once per *distinct* ID regardless of how
many times it was textually mentioned (mirroring
`validate_capabilities.py`'s own `sorted(seen)` convention). Only a
genuinely-unregistered or non-compliant ID ever produces a new error, and
it would be a real one.

**Where this script deliberately does NOT do a literal, unscoped port —
disclosed, not hidden:** `validate_capabilities.py`'s duplicate-ID check
(#1) flags any `capability_id` occurring more than once as an error
("scope-expansion-under-existing-ID risk"). Under a *whole-document*
occurrence count, that check would misfire constantly on prose-based
manifests like MOD-001's — e.g. RULE-001 legitimately appears in
`required_rule_ids`, again in `capability_evidence_ids`'s summary
sentence, and again in `missing_capability_blockers`'s summary sentence,
none of which is a real duplicate *declaration*. Flagging that as an error
would contradict this script's own stated design goal (no new errors from
harmless repeated mentions) on real, current MOD-001 data. Check #1 is
therefore re-scoped, not deleted: `find_structural_declarations` below
looks only at YAML list-items that themselves declare an ID via a
`capability_id: <ID>` or `id: <ID>` *property line* (the real shape both
MOD-000's `capabilities:` list and MOD-001's `required_rule_ids` list
actually use for "this entry IS a dependency declaration") — a genuine
duplicate there (the same ID as the leading property of two separate list
entries) is the real integrity failure the original check existed to
catch; an incidental prose mention is not such an entry and is correctly
excluded.

## The two REQUIREMENTS.md §3 checks validate_capabilities.py does NOT do

1. **Cyclic capability dependency detection** (`CAPABILITY_POLICY.md`'s
   "Dependency-cycle prohibition": "any direct or indirect cycle among
   Skill/Rule dependencies is activation-blocking — detect and refuse
   before activating any capability whose dependency graph contains a
   cycle"). Reads the manifest's `capability_dependency_ids` field
   (present in both MOD-000's and MOD-001's real manifests, currently
   `[]` in both — no real edges to find yet) and, if it ever contains
   real edges, builds a directed graph and runs DFS cycle detection.
   Block-style YAML only (`- id: X` / `depends_on: [...]` entries, or
   equivalent — this tool scans for ID literals within each list-item's
   text the same way the rest of it does, so it is not tied to one
   exact sub-field name); inline flow-style values are not structurally
   parsed (this is a lightweight regex-based scanner, not a real YAML
   parser, consistent with every other validator in this project) and
   are treated as empty. **Currently a structural no-op against both
   real manifests** (both declare `capability_dependency_ids: []`) —
   proven only against a synthetic fixture with a real cycle (see this
   slice's evidence note, not committed under `knowledge/`).

2. **Mandatory privileged-surface Rule check.** `REQUIREMENTS.md` §3:
   "reject... manifests missing mandatory privileged-surface Rules."
   `.claude/rules/admin/admin-privileged-console-baseline.md` is this
   project's one currently-identified mandatory Rule for a specific
   surface (admin/privileged-console, binding forward to MOD-029). If any
   YAML list-item anywhere in the manifest mentions an Admin Web /
   privileged-console surface AND the literal word `ACTIVATED` *within
   that same list item* (scoped to avoid an unrelated sibling item, e.g.
   "Backend (ACTIVATED...)", leaking into an adjacent "Admin Web
   (DEFERRED...)" item — the same "scope to the structural unit, not a
   raw-text window" principle `tools/validate_baseline_binding.py`'s
   `parse_baseline_table_rows` already established for markdown table
   rows), the manifest must also reference an admin/privileged-console
   Rule path (`.claude/rules/admin/` or `admin-privileged-console`)
   somewhere in its text, or this check denies
   `MISSING_MANDATORY_PRIVILEGED_SURFACE_RULE`. **Neither MOD-000 nor
   MOD-001 currently activates that surface, so this check is currently a
   structural no-op for both** — the same disclosed-no-op precedent
   `IMPLEMENTATION.md` §3 already uses for
   `tools/validate_appendix_b_traceability.py` ("no split requirement
   exists for MOD-001 itself... this gate is currently a no-op pass; it
   is the mechanism future modules' Scenario Reviews will run").

## What is reused verbatim vs. new

Ported, not reinvented, from `knowledge/00-System/validate_capabilities.py`:
`REGISTRY_COLUMNS`, `parse_registry_rows` (generalized to match `CAP-`,
`RULE-`, and `SKL-` row prefixes, not just `CAP-`), `_EXEMPTION_RE` /
`is_exempted`, and the body of checks 2-6 (unregistered / not-APPROVED /
missing-approved_by / overdue-next_review_due / missing supply-chain
field). Self-contained (no `import validate_capabilities` — that module's
top-level code runs a `subprocess` call at import time; this matches the
same convention `tools/validate_baseline_binding.py` already established
for not coupling to a sibling script's module-level side effects).

New in this script: `discover_manifest_ids` (the generalized ID-literal
regex, replacing `parse_manifest_capability_ids`'s hardcoded
`capability_id:\s*(CAP-\d+)` pattern), `iter_yaml_list_items` /
`extract_named_field_block` (shared structural-scoping helpers),
`find_structural_declarations` (the re-scoped duplicate check),
`parse_dependency_edges` / `find_cycle` (cyclic-dependency detection), and
`check_mandatory_privileged_surface_rule`.

This tool never writes to the manifest or the registry — read-only
against both, always.
"""
import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
    cwd=Path(__file__).resolve().parent,
).stdout.strip())
assert (ROOT / ".git").exists(), f"expected repo root, got {ROOT}"

DEFAULT_REGISTRY = ROOT / "knowledge/00-System/CAPABILITY_REGISTRY.md"

# ---------------------------------------------------------------------------
# Ported verbatim from knowledge/00-System/validate_capabilities.py.
# ---------------------------------------------------------------------------

REGISTRY_COLUMNS = [
    "id", "capability", "provenance", "version", "content_hash", "scope",
    "review_status", "qualified_by", "qualified_date", "approved_by",
    "approved_date", "last_reviewed_at", "next_review_due",
    "rollback_target", "evidence",
]


def parse_registry_rows(text: str) -> dict:
    """Parse CAPABILITY_REGISTRY.md's pipe-table data rows into
    {id: {column_name: cell_text}}. Generalized from the original's
    `line.startswith("| CAP-")` to any of the registry's real ID
    prefixes (`CAP-`, `RULE-`, and `SKL-` — the registry now carries all
    three families since RULE-001..009 were registered 2026-09-19)."""
    rows = {}
    row_start_re = re.compile(r"^\|\s*(?:CAP|RULE|SKL)-\d+")
    for line in text.splitlines():
        line = line.strip()
        if not row_start_re.match(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(REGISTRY_COLUMNS):
            continue  # malformed row — a real gap, but this validator's job is
            # supply-chain field checks, not markdown-table-shape checks
        row = dict(zip(REGISTRY_COLUMNS, cells))
        rows[row["id"]] = row
    return rows


# Hardened 2026-09-06 (Phase 7 re-review, RR-3) in the original — see that
# file's own comment for the one-word-kill-switch history. Ported unchanged.
_EXEMPTION_RE = re.compile(r"first-party.{0,40}exemption", re.IGNORECASE)


def is_exempted(review_status: str) -> bool:
    return bool(_EXEMPTION_RE.search(review_status))


# ---------------------------------------------------------------------------
# New: generalized ID discovery (replaces parse_manifest_capability_ids).
# ---------------------------------------------------------------------------

_ID_TOKEN_RE = re.compile(r"\b(?:CAP|RULE|SKL)-\d+\b")


def discover_manifest_ids(manifest_text: str) -> list[str]:
    """Every CAP-/RULE-/SKL-NNN token anywhere in the manifest's raw
    text, in order, duplicates included — same contract as the original
    `parse_manifest_capability_ids` (duplicate handling is the caller's
    job). See module docstring for the generalization rationale and its
    one disclosed cost."""
    return _ID_TOKEN_RE.findall(manifest_text)


# ---------------------------------------------------------------------------
# New: shared structural-scoping helpers (shallow, regex-based — not a
# real YAML parser, consistent with every other validator in this
# project). Used by the duplicate-declaration check, the cyclic-
# dependency check, and the mandatory-privileged-surface-Rule check.
# ---------------------------------------------------------------------------

def iter_yaml_list_items(text: str) -> list[str]:
    """Every YAML block-style list-item in `text` (a line starting with
    `- ` at some indentation, plus any subsequent lines indented deeper
    than that marker, treated as the same item) as one text blob per
    item. A new list-item marker at the same-or-shallower indentation —
    or any line at or below the current item's own indentation — closes
    the current item. This is what lets proximity checks (e.g. "does
    this ID appear in the SAME item as another token") work without one
    item's content leaking into an unrelated sibling item, the same
    "scope to the structural unit, not a raw-text window" principle
    `tools/validate_baseline_binding.py`'s `parse_baseline_table_rows`
    already established for markdown table rows. Nested lists-within-
    list-items are a disclosed limitation: a nested `- ` line always
    starts a new item in this shallow scan rather than staying nested
    inside its parent — harmless for every real shape currently in this
    project's manifests (flat lists of flat mappings), but a future
    genuinely nested manifest field would need a real YAML parser."""
    lines = text.splitlines()
    items: list[str] = []
    current: list[str] = []
    current_indent = None
    for line in lines:
        if not line.strip():
            if current:
                current.append(line)
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.lstrip(" ")
        if stripped.startswith("- "):
            if current:
                items.append("\n".join(current))
            current = [stripped[2:]]
            current_indent = indent
        elif current and current_indent is not None and indent > current_indent:
            current.append(stripped)
        else:
            if current:
                items.append("\n".join(current))
            current = []
            current_indent = None
    if current:
        items.append("\n".join(current))
    return items


def extract_named_field_block(manifest_text: str, key: str) -> str:
    """Returns the raw block of lines following `<key>:` in the
    manifest. If the key's value is an inline scalar (`[]`, `~`, `null`,
    or an unsupported inline flow-style value like `[{...}]`) or the key
    is absent entirely, returns "" — this tool does not structurally
    parse inline flow-style YAML. Otherwise returns the indented
    block-style list that follows, stopping at the first subsequent line
    whose indentation is <= the key line's own indentation (the next
    sibling/top-level key)."""
    lines = manifest_text.splitlines()
    key_re = re.compile(rf"^(\s*){re.escape(key)}\s*:(.*)$")
    for i, line in enumerate(lines):
        m = key_re.match(line)
        if not m:
            continue
        key_indent = len(m.group(1))
        inline = m.group(2)
        inline_novalue = re.split(r"\s+#", inline, maxsplit=1)[0].strip()
        if inline_novalue:
            return ""  # inline scalar/flow-style value — nothing block-shaped here
        block_lines = []
        for nxt_line in lines[i + 1:]:
            if not nxt_line.strip():
                block_lines.append(nxt_line)
                continue
            nxt_indent = len(nxt_line) - len(nxt_line.lstrip(" "))
            if nxt_indent <= key_indent:
                break
            block_lines.append(nxt_line)
        return "\n".join(block_lines)
    return ""  # key not present at all


# ---------------------------------------------------------------------------
# New: re-scoped duplicate-declaration check (see module docstring for
# why this replaces a literal whole-document occurrence count).
# ---------------------------------------------------------------------------

_DECL_PROPERTY_RE = re.compile(r"^(?:capability_id|id)\s*:\s*((?:CAP|RULE|SKL)-\d+)\s*$")


def find_structural_declarations(manifest_text: str) -> list[str]:
    """Every list-item (see `iter_yaml_list_items`) that itself declares
    an ID via a `capability_id: <ID>` or `id: <ID>` property line — the
    real shape both MOD-000's `capabilities:` list (`capability_id:`)
    and MOD-001's `required_rule_ids` list (`id:`) actually use for
    "this entry IS a dependency declaration." Returns the declared ID
    for each such item, in order, duplicates included (dedup is the
    caller's job, matching `discover_manifest_ids`'s own contract).
    A free-text list item (e.g. `capability_evidence_ids`'s "RULE-001
    through RULE-009 — see...") has no line matching this property
    shape and is correctly excluded — it is a mention, not a
    declaration."""
    declared = []
    for item in iter_yaml_list_items(manifest_text):
        for line in item.splitlines():
            m = _DECL_PROPERTY_RE.match(line.strip())
            if m:
                declared.append(m.group(1))
                break  # one declared id per item — first matching property line wins
    return declared


# ---------------------------------------------------------------------------
# New: cyclic capability dependency detection (CAPABILITY_POLICY.md's
# "Dependency-cycle prohibition").
# ---------------------------------------------------------------------------

def parse_dependency_edges(manifest_text: str) -> dict[str, set[str]]:
    """Reads the `capability_dependency_ids` field's block (if any) and
    builds a directed graph: for each list-item in that block, the
    FIRST ID literal found is treated as the source (the capability that
    has the dependency) and every OTHER ID literal in that same item is
    a target it depends on — generalizing across field-name variations
    (`depends_on`/`dependencies`/`requires`/etc.) the same way the rest
    of this tool generalizes over `capability_id`/`required_rule_ids`/
    free-text mentions, by scanning for ID literals rather than assuming
    one field-naming convention. Returns {} (no edges) if the field is
    absent or an empty/null scalar — the real, current state of both
    MOD-000's and MOD-001's manifests (`capability_dependency_ids: []`
    in both)."""
    block = extract_named_field_block(manifest_text, "capability_dependency_ids")
    if not block.strip():
        return {}
    edges: dict[str, set[str]] = {}
    for item in iter_yaml_list_items(block):
        ids_in_item = _ID_TOKEN_RE.findall(item)
        if not ids_in_item:
            continue
        source = ids_in_item[0]
        targets = {t for t in ids_in_item[1:] if t != source}
        if targets:
            edges.setdefault(source, set()).update(targets)
    return edges


def find_cycle(edges: dict[str, set]) -> list[str] | None:
    """Standard DFS white/gray/black cycle detection over the directed
    graph `edges` (source -> set(targets)). Returns the cycle as a list
    of IDs (e.g. `['CAP-010', 'CAP-011', 'CAP-010']`) if one exists,
    else None. Deterministic (nodes and neighbors visited in sorted
    order) so the same input always reports the same cycle path."""
    nodes = set(edges.keys())
    for targets in edges.values():
        nodes.update(targets)
    color = {n: 0 for n in nodes}  # 0=white (unvisited), 1=gray (on stack), 2=black (done)
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = 1
        path.append(node)
        for nxt in sorted(edges.get(node, ())):
            if color[nxt] == 1:
                start = path.index(nxt)
                return path[start:] + [nxt]
            if color[nxt] == 0:
                found = dfs(nxt)
                if found:
                    return found
        path.pop()
        color[node] = 2
        return None

    for n in sorted(nodes):
        if color[n] == 0:
            found = dfs(n)
            if found:
                return found
    return None


# ---------------------------------------------------------------------------
# New: mandatory privileged-surface Rule check.
# ---------------------------------------------------------------------------

_ADMIN_SURFACE_RE = re.compile(
    r"admin[\s-]?web|privileged[\s-]?console|admin[\s-]?console", re.IGNORECASE
)
_ADMIN_RULE_REF_RE = re.compile(
    r"\.claude/rules/admin/|admin-privileged-console", re.IGNORECASE
)


def check_mandatory_privileged_surface_rule(manifest_text: str) -> list[dict]:
    """REQUIREMENTS.md §3: "reject... manifests missing mandatory
    privileged-surface Rules." A surface is "activated" for this
    purpose when some single YAML list-item mentions an Admin Web /
    privileged-console surface AND the literal word ACTIVATED within
    that SAME item (scoping is what prevents an unrelated sibling item
    like "Backend (ACTIVATED...)" from falsely activating an adjacent
    "Admin Web (DEFERRED...)" item — see `iter_yaml_list_items`). If
    activated, the manifest must also reference an admin/privileged-
    console Rule path somewhere in its text, or this denies
    MISSING_MANDATORY_PRIVILEGED_SURFACE_RULE. Currently a structural
    no-op for both real manifests (neither activates this surface) —
    see module docstring."""
    activated_items = [
        item for item in iter_yaml_list_items(manifest_text)
        if _ADMIN_SURFACE_RE.search(item) and re.search(r"\bACTIVATED\b", item)
    ]
    if not activated_items:
        return []
    if _ADMIN_RULE_REF_RE.search(manifest_text):
        return []
    return [{
        "code": "MISSING_MANDATORY_PRIVILEGED_SURFACE_RULE",
        "detail": (
            f"{len(activated_items)} activated Admin Web/privileged-console surface "
            "item(s) found in this manifest, but no admin/privileged-console Rule "
            "(e.g. .claude/rules/admin/admin-privileged-console-baseline.md) is "
            "referenced anywhere in it."
        ),
    }]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Capability-governance manifest validator, generalized to any "
                     "module's module-capabilities.yaml (MOD-001, REQUIREMENTS.md §3). "
                     "Read-only against both the manifest and the registry, always."
    )
    p.add_argument(
        "--manifest", type=Path, required=True,
        help="Path to the module-capabilities.yaml to validate (required — this tool "
             "works against any module's manifest, not a hardcoded MOD-000/MOD-001 path).",
    )
    p.add_argument(
        "--registry", type=Path, default=DEFAULT_REGISTRY,
        help=f"Path to CAPABILITY_REGISTRY.md (default: {DEFAULT_REGISTRY}).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path: Path = args.manifest
    registry_path: Path = args.registry

    if not manifest_path.exists():
        print(f"BLOCKED: CAPABILITY_MANIFEST_UNREADABLE — {manifest_path} does not exist.")
        return 1
    if not registry_path.exists():
        print(f"BLOCKED: CAPABILITY_REGISTRY_UNREADABLE — {registry_path} does not exist.")
        return 1

    manifest_text = manifest_path.read_text(encoding="utf-8", errors="replace")
    registry_text = registry_path.read_text(encoding="utf-8", errors="replace")

    ids_raw = discover_manifest_ids(manifest_text)
    seen = sorted(set(ids_raw))
    registry_rows = parse_registry_rows(registry_text)

    errors: list[str] = []
    info: list[str] = []

    # 1. Duplicate structural declaration (re-scoped — see module docstring).
    declared_raw = find_structural_declarations(manifest_text)
    dup_seen: set[str] = set()
    dup_found: set[str] = set()
    for did in declared_raw:
        if did in dup_seen:
            dup_found.add(did)
        dup_seen.add(did)
    if dup_found:
        errors.append(
            f"Duplicate structural ID declaration (same 'capability_id:'/'id:' "
            f"list-entry property value declared by more than one entry — "
            f"scope-expansion-under-existing-ID risk): {sorted(dup_found)}"
        )
    else:
        info.append(
            f"{len(dup_seen)} structurally-declared ID(s) via 'capability_id:'/'id:' "
            f"list-entry properties, no duplicates. ({len(ids_raw)} raw ID-token "
            f"occurrence(s) across the full manifest text; {len(seen)} distinct ID(s) "
            f"after dedup — checks 2-6 below run once per distinct ID.)"
        )

    today = date.today().isoformat()

    # 2-6, ported from validate_capabilities.py, run once per distinct discovered ID.
    for cid in seen:
        row = registry_rows.get(cid)
        if row is None:
            errors.append(
                f"BLOCKED: CAPABILITY_UNREGISTERED — {cid} is mentioned in "
                f"{manifest_path.name} but has no row in {registry_path}."
            )
            continue

        review_status = row.get("review_status", "")
        exempt = is_exempted(review_status)

        if "approved" not in review_status.lower():
            errors.append(
                f"{cid}: review_status '{review_status}' does not contain APPROVED — "
                f"cannot satisfy a module dependency (QUALIFIED/BLOCKED-only is "
                f"insufficient per CAPABILITY_POLICY.md's fail-closed reminder)."
            )

        approved_by = row.get("approved_by", "")
        if not exempt and (not approved_by or approved_by.upper().startswith("N/A")):
            errors.append(
                f"{cid}: no named approved_by and no documented first-party/harness "
                f"exemption — an approval with no accountable Opus reviewer."
            )

        next_review_due = row.get("next_review_due", "")
        if not exempt:
            m = re.match(r"(\d{4}-\d{2}-\d{2})", next_review_due)
            if not m:
                errors.append(
                    f"{cid}: next_review_due '{next_review_due}' is not a parseable "
                    f"date and is not exempted."
                )
            elif m.group(1) < today:
                errors.append(
                    f"{cid}: next_review_due {m.group(1)} is in the past "
                    f"(today: {today}) — cannot satisfy any gate until re-evaluated."
                )

        for field in ("provenance", "version", "content_hash"):
            value = row.get(field, "")
            if not exempt and not value:
                errors.append(f"{cid}: required supply-chain field '{field}' is empty and not exempted.")

        # (the CAPABILITY_UNREGISTERED case above already `continue`d before
        # reaching here, so every cid that gets here is registered — this
        # only needs to check whether checks 3-6 above added an error for
        # THIS cid specifically, matching validate_capabilities.py's own
        # `all(not e.startswith(cid) for e in errors)` convention, tightened
        # to `f"{cid}:"` so e.g. CAP-001 can never accidentally match an
        # error string that actually belongs to CAP-010)
        if all(not e.startswith(f"{cid}:") for e in errors):
            info.append(f"{cid}: registered, {review_status[:60]}{'...' if len(review_status) > 60 else ''}")

    # New check A: cyclic capability dependency detection.
    edges = parse_dependency_edges(manifest_text)
    if edges:
        cycle = find_cycle(edges)
        if cycle:
            errors.append(
                f"CYCLIC_CAPABILITY_DEPENDENCY — cycle detected in capability_dependency_ids: "
                f"{' -> '.join(cycle)}."
            )
        else:
            info.append(f"capability_dependency_ids: {len(edges)} source node(s) with real edges, no cycle found.")
    else:
        info.append("capability_dependency_ids: no real edges declared (empty/absent) — cyclic-dependency check is a structural no-op.")

    # New check B: mandatory privileged-surface Rule.
    admin_denials = check_mandatory_privileged_surface_rule(manifest_text)
    if admin_denials:
        for d in admin_denials:
            errors.append(f"{d['code']} — {d['detail']}")
    else:
        info.append("mandatory-privileged-surface-Rule check: no activated Admin Web/privileged-console surface found — structural no-op.")

    print("=" * 70)
    print("CAPABILITY-GOVERNANCE MANIFEST VALIDATOR (any module)")
    print("=" * 70)
    print(f"\nManifest: {manifest_path}\nRegistry: {registry_path}")
    print(f"\n--- INFO ({len(info)}) ---")
    for i in info:
        print(f"  [i] {i}")
    print(f"\n--- ERRORS ({len(errors)}) ---")
    for e in errors:
        print(f"  [X] {e}")
    print("\n" + "=" * 70)
    if errors:
        print(f"RESULT: FAIL — {len(errors)} error(s) found.")
        return 1
    print(f"RESULT: PASS — {len(seen)} capability/Rule ID(s) discovered, all registered "
          f"and APPROVED with required fields present; no cyclic dependency; no missing "
          f"mandatory privileged-surface Rule.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
