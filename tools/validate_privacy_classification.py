"""
Privacy-classification lint (MOD-001, GOV-01-R03 — the card's mandatory
Security-scope baseline control "privacy classification"; SCN-MOD001-043).

`IMPLEMENTATION.md` §6 draws the split this tool is built to respect: "real
privacy classification of real data fields" is explicitly *not* MOD-001's
obligation ("no real fields exist yet"); MOD-001's obligation is "the *lint*
that will enforce a classification tag once fields exist". `REQUIREMENTS.md`
line 617 names this scenario's subject as "data-classification tagging",
distinguishing it from SCN-029 (committed-file secrets), SCN-MOD001-122 (log
statements) and SCN-MOD001-126 (response/request field shape). The upstream
authority both files cite is the card's Security-scope baseline
(`EIP_MIRROR.md` lines 4267-4271), cited here secondhand via those two project
files rather than quoted.

SCN-MOD001-043's own steps are the whole acceptance surface: run the lint
"against a synthetic field tagged `Restricted` and one left untagged", and the
untagged field must be "flagged as needing an explicit classification before it
can be persisted — proves the lint exists and fires, even though no real data
field exists yet."

## What this is, and deliberately is not

It is a pure, offline lint over one declarative JSON manifest of *field
declarations*. It is NOT a data-classification taxonomy, NOT a scan of any real
model/schema source, and NOT a generic policy engine.

The taxonomy is deliberately the **manifest's own**, never this tool's: a
manifest declares its vocabulary in `declared_classifications`, and the lint
enforces only that every field carries an explicit tag drawn from that declared
vocabulary. Inventing a project-wide classification taxonomy here would be a
material product/architecture decision MOD-001 has no mandate to make — the
baselines use labels like `Restricted` and `Confidential` in module cards, but
no MOD-001 planning document commits this module to enumerating them, and
`IMPLEMENTATION.md` §6 assigns the real classification of real fields to the
later modules that will own those fields. So this lint answers "is every
persisted field explicitly classified against a declared vocabulary?" and
never "is `Restricted` the correct label for this field?"

## Manifest shape

    {
      "manifest_kind": "synthetic-persistence-field-manifest",  # exact label
      "synthetic": true,                                        # literally true
      "manifest_id": "...",
      "declared_classifications": ["Restricted", ...],  # the manifest's own
                                                        # vocabulary, non-empty
      "fields": [
        {"field_id": "...", "classification": "Restricted"},  # classified
        {"field_id": "..."}                                   # FLAGGED
      ]
    }

A field entry's keys are a strict allowlist — exactly `field_id` and the
optional `classification`. Nothing else is accepted, which is what makes it
structurally impossible for a manifest to carry a field *value* under an
accepted key: this lint reasons about declarations, so there is no accepted key
a sample value, example row or default could arrive under.

## What makes the report value-free (BUG-055)

The key allowlist alone does **not** make the report value-free, and an earlier
revision of this file claimed that it did. BUG-055
(`knowledge/03-Modules/MOD-001/evidence/bugs/`) recorded that claim as false:
a manifest the lint *denies* can still put an arbitrary string into an
identifier slot (`field_id`), into a key *name*, into `manifest_id`, or into a
declared classification label, and the earlier report echoed all four.

So the report is value-free by construction *of the report*, not by filtering.
`render_report` and every `Finding` are assembled from exactly four sources:

  * the operator-supplied manifest path (it comes from argv, not the manifest);
  * counts and 0-based indices — `fields[3]`, `declared[0]`, "2 label(s)";
  * this tool's own finding codes and key-name constants; and
  * fixed English prose.

No manifest-derived string reaches the report — not a field identifier, not a
classification label, not a manifest id, not an unexpected or duplicated key
name. A denied declaration is located by its index in `fields`, which is stable,
is enough to point a reader at the offending entry, and carries no manifest
text. The only diagnostic sourced from outside this tool is `json`'s own decode
message, drawn from the stdlib's fixed phrase vocabulary, which never embeds
document text.

## Fail-closed

Anything the lint cannot fully understand is DENIED, never passed: an
unreadable or non-JSON manifest, duplicate JSON object keys (which `json.loads`
would otherwise silently resolve last-wins, hiding one classification behind
another), a manifest missing the synthetic label, a missing/malformed declared
vocabulary, an empty field list, a malformed or unexpectedly-keyed field entry,
a duplicate `field_id`, a non-string or empty `classification`, and a
classification outside the manifest's own declared vocabulary. An absent
`classification` key is the scenario's own central case and is flagged
`CLASSIFICATION_REQUIRED`.

Dependency-free (stdlib only) and read-only: this tool never writes to the
manifest it reads.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_KIND = "synthetic-persistence-field-manifest"

# A field declaration's keys, exactly. See the module docstring: the allowlist
# is what makes a field *value* unrepresentable in this manifest format.
REQUIRED_FIELD_KEYS = ("field_id",)
OPTIONAL_FIELD_KEYS = ("classification",)
ALLOWED_FIELD_KEYS = REQUIRED_FIELD_KEYS + OPTIONAL_FIELD_KEYS

# Finding codes. CLASSIFICATION_REQUIRED is SCN-MOD001-043's central negative.
CODE_UNREADABLE_MANIFEST = "UNREADABLE_MANIFEST"
CODE_MALFORMED_MANIFEST = "MALFORMED_MANIFEST"
CODE_DUPLICATE_JSON_KEY = "DUPLICATE_JSON_KEY"
CODE_MANIFEST_NOT_LABELED_SYNTHETIC = "MANIFEST_NOT_LABELED_SYNTHETIC"
CODE_MALFORMED_DECLARED_CLASSIFICATIONS = "MALFORMED_DECLARED_CLASSIFICATIONS"
CODE_NO_FIELDS = "NO_FIELDS"
CODE_MALFORMED_FIELD_ENTRY = "MALFORMED_FIELD_ENTRY"
CODE_DUPLICATE_FIELD_ID = "DUPLICATE_FIELD_ID"
CODE_CLASSIFICATION_REQUIRED = "CLASSIFICATION_REQUIRED"
CODE_MALFORMED_CLASSIFICATION = "MALFORMED_CLASSIFICATION"
CODE_CLASSIFICATION_NOT_DECLARED = "CLASSIFICATION_NOT_DECLARED"


@dataclass
class Finding:
    """One denial. `subject` is a stable locator — `fields[<index>]`, a manifest
    key name this tool owns, or the operator-supplied path — and `detail` is
    built from counts, indices, codes and fixed prose. Neither ever carries a
    string taken from the manifest (BUG-055; see the module docstring)."""

    subject: str
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.subject}: {self.code}: {self.detail}"


@dataclass
class ClassifiedField:
    """A field declaration that passed. `field_id` and `classification` are the
    manifest's own strings, retained for programmatic callers only; the report
    renders `index` and `classification_index` in their place so that neither
    string is echoed (BUG-055)."""

    field_id: str
    classification: str
    index: int
    classification_index: int


@dataclass
class LintOutcome:
    # Presence only. The manifest id is manifest-derived text with no role in
    # the lint's decisions, so it is never retained, let alone rendered.
    manifest_id_present: bool = False
    declared_classifications: list[str] = field(default_factory=list)
    fields_inspected: int = 0
    classified: list[ClassifiedField] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def denied(self) -> bool:
        return bool(self.findings)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


class _DuplicateObjectKeys(ValueError):
    """Carries the *count* of duplicated key names, never the names themselves:
    a key name is manifest-derived text (BUG-055). Precedent for counting rather
    than naming untrusted keys: `offline_snapshot_fixture.py`'s
    `unexpected_count`."""

    def __init__(self, count: int) -> None:
        super().__init__(f"{count} duplicated object key name(s)")
        self.count = count


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """`json.loads` object hook that refuses duplicate keys instead of silently
    keeping the last one — a duplicated `classification` key would otherwise let
    an unclassified or wrongly-classified declaration hide behind a valid one.
    Precedent: `validate_architecture_gates.py`'s own strict-JSON loader."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        raise _DuplicateObjectKeys(len(duplicates))
    return dict(pairs)


def _validate_declared_classifications(raw: Any) -> tuple[list[str], list[Finding]]:
    """The manifest's own vocabulary. Non-empty, all non-empty strings, unique —
    anything else leaves the lint with no vocabulary to check tags against, so
    it denies rather than defaulting to one of its own."""
    subject = "declared_classifications"
    if not isinstance(raw, list) or not raw:
        return [], [
            Finding(
                subject,
                CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
                "must be a non-empty list of classification labels; the lint never "
                "supplies a default taxonomy of its own",
            )
        ]
    if not all(_is_nonempty_str(label) for label in raw):
        return [], [
            Finding(
                subject,
                CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
                "every declared classification must be a non-empty string",
            )
        ]
    labels = [label for label in raw]
    # Counted, not named: a declared label is manifest-derived text (BUG-055).
    repeated = len({label for label in labels if labels.count(label) > 1})
    if repeated:
        return [], [
            Finding(
                subject,
                CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
                f"declared classifications must be unique; {repeated} label(s) are repeated "
                f"(the labels themselves are counted, never echoed)",
            )
        ]
    return labels, []


def _validate_field_entry(
    entry: Any,
    *,
    index: int,
    declared: list[str],
    first_seen_index: dict[str, int],
) -> tuple[ClassifiedField | None, list[Finding]]:
    """Check one field declaration. Returns the classified field on success, or
    the findings that deny it — never both.

    The subject is this entry's index in `fields` for every outcome, including
    the ones that have already read a `field_id`: a field identifier is
    manifest-derived text and is never echoed (BUG-055)."""
    subject = f"fields[{index}]"
    if not isinstance(entry, dict):
        return None, [
            Finding(subject, CODE_MALFORMED_FIELD_ENTRY, "field declaration must be a JSON object")
        ]

    # Counted, not named: an unexpected key's *name* is manifest-derived text,
    # and echoing it was half of BUG-055.
    unexpected = sum(1 for key in entry if key not in ALLOWED_FIELD_KEYS)
    if unexpected:
        return None, [
            Finding(
                subject,
                CODE_MALFORMED_FIELD_ENTRY,
                f"{unexpected} unexpected key(s); a field declaration carries exactly "
                f"{list(ALLOWED_FIELD_KEYS)} (names only — a declaration never carries a "
                f"field value, and an unexpected key's own name is not echoed)",
            )
        ]

    field_id = entry.get("field_id")
    if not _is_nonempty_str(field_id):
        return None, [
            Finding(subject, CODE_MALFORMED_FIELD_ENTRY, "`field_id` must be a non-empty string")
        ]

    if field_id in first_seen_index:
        return None, [
            Finding(
                subject,
                CODE_DUPLICATE_FIELD_ID,
                f"same `field_id` as fields[{first_seen_index[field_id]}]; one field cannot "
                f"carry two classifications",
            )
        ]

    if "classification" not in entry:
        return None, [
            Finding(
                subject,
                CODE_CLASSIFICATION_REQUIRED,
                "no explicit `classification` declared; this field needs an explicit "
                "classification before it can be persisted",
            )
        ]

    classification = entry["classification"]
    if not _is_nonempty_str(classification):
        return None, [
            Finding(
                subject,
                CODE_MALFORMED_CLASSIFICATION,
                "`classification` must be a non-empty string; an absent, null or blank tag "
                "is not an explicit classification",
            )
        ]
    if classification not in declared:
        return None, [
            Finding(
                subject,
                CODE_CLASSIFICATION_NOT_DECLARED,
                f"the tag declared here is not one of the {len(declared)} label(s) in this "
                f"manifest's own declared vocabulary; neither the tag nor the vocabulary is "
                f"echoed",
            )
        ]
    return ClassifiedField(field_id, classification, index, declared.index(classification)), []


def lint_manifest(manifest: Any) -> LintOutcome:
    """Lint one already-parsed manifest. Every field is inspected before
    returning, so the report names every unclassified field in one run rather
    than stopping at the first."""
    outcome = LintOutcome()
    if not isinstance(manifest, dict):
        outcome.findings.append(
            Finding("<manifest>", CODE_MALFORMED_MANIFEST, "top level must be a JSON object")
        )
        return outcome

    outcome.manifest_id_present = _is_nonempty_str(manifest.get("manifest_id"))

    if manifest.get("manifest_kind") != MANIFEST_KIND or manifest.get("synthetic") is not True:
        outcome.findings.append(
            Finding(
                "<manifest>",
                CODE_MANIFEST_NOT_LABELED_SYNTHETIC,
                f"`manifest_kind` must be {MANIFEST_KIND!r} and `synthetic` must be literally "
                f"true; this lint reads synthetic field declarations only",
            )
        )
        return outcome

    declared, declared_findings = _validate_declared_classifications(
        manifest.get("declared_classifications")
    )
    if declared_findings:
        outcome.findings.extend(declared_findings)
        return outcome
    outcome.declared_classifications = declared

    entries = manifest.get("fields")
    if not isinstance(entries, list) or not entries:
        outcome.findings.append(
            Finding(
                "fields",
                CODE_NO_FIELDS,
                "must be a non-empty list of field declarations; a manifest with nothing to "
                "classify is denied, never reported as a pass",
            )
        )
        return outcome

    outcome.fields_inspected = len(entries)
    # `field_id` -> the index of its first declaration, so a duplicate can be
    # pointed back at the entry it collides with by index rather than by name.
    first_seen_index: dict[str, int] = {}
    for index, entry in enumerate(entries):
        classified, findings = _validate_field_entry(
            entry, index=index, declared=declared, first_seen_index=first_seen_index
        )
        if isinstance(entry, dict) and _is_nonempty_str(entry.get("field_id")):
            first_seen_index.setdefault(entry["field_id"], index)
        if findings:
            outcome.findings.extend(findings)
        elif classified is not None:
            outcome.classified.append(classified)
    return outcome


def load_manifest(path: Path) -> tuple[Any, list[Finding]]:
    """Read and parse a manifest, failing closed on anything unreadable, not
    valid JSON, or carrying duplicate object keys."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, [
            Finding(
                str(path), CODE_UNREADABLE_MANIFEST, f"could not be read ({type(exc).__name__})"
            )
        ]
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys), []
    except _DuplicateObjectKeys as exc:
        return None, [
            Finding(
                str(path),
                CODE_DUPLICATE_JSON_KEY,
                f"{exc.count} key name(s) appear more than once inside one JSON object; "
                f"last-wins resolution could hide one classification behind another. The "
                f"duplicated names are counted, never echoed",
            )
        ]
    except json.JSONDecodeError as exc:
        # `exc.msg` is the stdlib's own fixed phrase vocabulary ("Expecting
        # value", ...); it never embeds a substring of the document.
        return None, [
            Finding(f"{path}:{exc.lineno}", CODE_MALFORMED_MANIFEST, f"not valid JSON ({exc.msg})")
        ]
    except ValueError as exc:
        # Fail closed on anything else the strict loader raises, by type name
        # only — never by rendering the offending text.
        return None, [
            Finding(
                str(path),
                CODE_MALFORMED_MANIFEST,
                f"could not be parsed ({type(exc).__name__})",
            )
        ]


def run_validation(path: Path) -> LintOutcome:
    manifest, load_findings = load_manifest(path)
    if load_findings:
        return LintOutcome(findings=load_findings)
    return lint_manifest(manifest)


def render_report(outcome: LintOutcome, *, path: Path) -> str:
    """The operator-supplied path, counts, indices and finding codes only. No
    manifest-derived string is rendered — not a field identifier, not a
    classification label, not the manifest id, not a key name (BUG-055; see the
    module docstring for why the key allowlist alone was not enough)."""
    declared_count = len(outcome.declared_classifications)
    lines = [
        "=" * 70,
        "MOD-001 PRIVACY-CLASSIFICATION LINT (GOV-01-R03, SCN-MOD001-043)",
        "=" * 70,
        "",
        f"Manifest file: {path}",
        f"Manifest id:   {'<declared, not echoed>' if outcome.manifest_id_present else '<absent>'}",
        "Declared classifications: "
        + (f"{declared_count} label(s), not echoed" if declared_count else "<none resolved>"),
        f"Field declarations inspected: {outcome.fields_inspected}",
        f"Explicitly classified: {len(outcome.classified)}",
    ]
    if outcome.classified:
        lines.append("")
        lines.extend(
            f"  OK     fields[{item.index}] classification=declared[{item.classification_index}]"
            for item in outcome.classified
        )
    if outcome.findings:
        lines.extend(["", f"DENY: {len(outcome.findings)} problem(s) found:"])
        lines.extend(f"  - {finding}" for finding in outcome.findings)
    else:
        lines.extend(
            [
                "",
                (
                    "PASS - every declared field carries an explicit classification drawn "
                    "from this manifest's own declared vocabulary."
                ),
            ]
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Privacy-classification lint (MOD-001, GOV-01-R03, SCN-MOD001-043). "
        "Denies any field declaration in an explicitly-synthetic JSON manifest that does "
        "not carry an explicit classification drawn from that manifest's own declared "
        "vocabulary. The taxonomy is the manifest's, never this tool's: it checks that a "
        "field is explicitly classified, not whether the label chosen is correct. "
        "Dependency-free and read-only; fails closed (exit 1) on anything it cannot fully "
        "understand, and never prints any manifest-derived string — field identifiers, "
        "classification labels, the manifest id and key names are all located by index or "
        "count instead.",
    )
    p.add_argument(
        "manifest",
        type=Path,
        help="Path to an explicitly-synthetic persistence-field manifest "
        f"(`manifest_kind: {MANIFEST_KIND}`, `synthetic: true`). Required: the lint has no "
        "default manifest, so it can never pass green over a path nobody named.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outcome = run_validation(args.manifest)
    print(render_report(outcome, path=args.manifest))
    return 1 if outcome.denied else 0


if __name__ == "__main__":
    sys.exit(main())
