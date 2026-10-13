"""
Unit tests for tools/validate_privacy_classification.py (MOD-001, GOV-01-R03 —
the card's mandatory Security-scope baseline control "privacy classification";
SCN-MOD001-043).

SCN-MOD001-043's own steps are the whole acceptance surface and drive tests
1-3: run the lint "against a synthetic field tagged `Restricted` and one left
untagged" and expect the untagged field to be "flagged as needing an explicit
classification before it can be persisted."

  1. test_explicitly_classified_field_passes - the positive: a field tagged
     `Restricted` against a manifest declaring `Restricted` -> PASS, exit 0,
     no findings.
  2. test_untagged_field_is_flagged - the negative: the same manifest plus one
     field left untagged -> DENY with exactly one CLASSIFICATION_REQUIRED
     finding locating the untagged field by its index in `fields`, while the
     `Restricted` field is still reported as explicitly classified. This is the
     scenario's own tagged-passes/untagged-flagged pair in one manifest.
  3. test_cli_distinguishes_tagged_from_untagged - the same two manifests
     driven through `main()` as a real subprocess: exit 0 vs exit 1.
  4. test_malformed_manifests_all_fail_closed - every malformed class denies,
     never silently passes: non-object top level, missing/false synthetic
     label, missing/malformed/duplicated declared vocabulary, empty or
     non-list field list, non-object field entry, unexpected field key,
     missing/blank `field_id`, duplicate `field_id`, null/blank/non-string
     classification, a classification outside the declared vocabulary,
     duplicate JSON keys, non-JSON text, and an unreadable path.
  5. test_report_cannot_echo_a_field_value - a manifest that tries to smuggle
     a sentinel value under an extra key is denied as malformed, and neither
     the sentinel nor the extra key's own name appears in the report or CLI
     output.
  6. test_report_never_echoes_a_manifest_string - BUG-055's direct regression.
     The earlier revision claimed the field-key allowlist alone made reporting
     value-free; it did not, because a denied manifest can still put an
     arbitrary string into `field_id`, a key *name*, `manifest_id`, or a
     declared classification label, and all four were echoed. This drives one
     sentinel through every such slot in turn (including duplicate JSON keys
     and malformed JSON text) and asserts the sentinel reaches neither the
     report nor the CLI, while the named DENY code and exit status for each
     case stay correct.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validate_privacy_classification import (
    CODE_CLASSIFICATION_NOT_DECLARED,
    CODE_CLASSIFICATION_REQUIRED,
    CODE_DUPLICATE_FIELD_ID,
    CODE_DUPLICATE_JSON_KEY,
    CODE_MALFORMED_CLASSIFICATION,
    CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
    CODE_MALFORMED_FIELD_ENTRY,
    CODE_MALFORMED_MANIFEST,
    CODE_MANIFEST_NOT_LABELED_SYNTHETIC,
    CODE_NO_FIELDS,
    CODE_UNREADABLE_MANIFEST,
    MANIFEST_KIND,
    lint_manifest,
    main,
    render_report,
    run_validation,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LINT_SCRIPT = REPO_ROOT / "tools" / "validate_privacy_classification.py"

# The one classification label SCN-MOD001-043 itself names. The lint owns no
# taxonomy, so the label only has meaning because the manifest declares it.
RESTRICTED = "Restricted"

# A distinctive synthetic sentinel, so test 5 can prove no field value can
# reach the report. Never credential-shaped.
SENTINEL_VALUE = "SYNTHETIC-SENTINEL-VALUE-DO-NOT-ECHO"

# BUG-055's own sentinel, driven through every untrusted manifest slot by
# test 6. Also explicitly synthetic and never credential-shaped.
ECHO_SENTINEL = "SYNTHETIC_DO_NOT_ECHO_VALUE_67382"

TAGGED_FIELD = {"field_id": "synthetic_restricted_field", "classification": RESTRICTED}
UNTAGGED_FIELD = {"field_id": "synthetic_untagged_field"}


def _manifest(fields: list[dict], **overrides) -> dict:
    manifest = {
        "manifest_kind": MANIFEST_KIND,
        "synthetic": True,
        "manifest_id": "SYNTHETIC-FIELD-MANIFEST-001",
        "declared_classifications": [RESTRICTED],
        "fields": fields,
    }
    manifest.update(overrides)
    return manifest


def _codes(outcome) -> list[str]:
    return [finding.code for finding in outcome.findings]


def _run_cli(manifest: dict, tmp: str, name: str) -> subprocess.CompletedProcess:
    path = Path(tmp) / name
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(LINT_SCRIPT), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_explicitly_classified_field_passes():
    outcome = lint_manifest(_manifest([TAGGED_FIELD]))

    assert outcome.findings == [], _codes(outcome)
    assert outcome.denied is False
    assert outcome.fields_inspected == 1
    assert [(f.field_id, f.classification) for f in outcome.classified] == [
        ("synthetic_restricted_field", RESTRICTED)
    ]

    rendered = render_report(outcome, path=Path("manifest.json"))
    assert "PASS" in rendered
    # The passing declaration is reported by index into `fields` and into the
    # manifest's declared vocabulary; neither its identifier nor its label is
    # echoed (BUG-055).
    assert "fields[0] classification=declared[0]" in rendered
    assert "synthetic_restricted_field" not in rendered
    assert RESTRICTED not in rendered
    assert "SYNTHETIC-FIELD-MANIFEST-001" not in rendered


def test_untagged_field_is_flagged():
    outcome = lint_manifest(_manifest([TAGGED_FIELD, UNTAGGED_FIELD]))

    assert outcome.denied is True
    assert _codes(outcome) == [CODE_CLASSIFICATION_REQUIRED]
    finding = outcome.findings[0]
    # Located by index, not by identifier (BUG-055) — the untagged declaration
    # is `fields[1]` in this manifest.
    assert finding.subject == "fields[1]"
    assert "explicit classification before it can be persisted" in finding.detail

    # The tagged field is still recognised as explicitly classified: the lint
    # flags the untagged declaration, it does not reject the whole manifest.
    assert [f.field_id for f in outcome.classified] == ["synthetic_restricted_field"]
    assert outcome.fields_inspected == 2

    rendered = render_report(outcome, path=Path("manifest.json"))
    assert "DENY" in rendered
    assert CODE_CLASSIFICATION_REQUIRED in rendered
    assert "fields[1]" in rendered
    assert "synthetic_untagged_field" not in rendered

    # Both untagged fields in a manifest are located in one run, not just the first.
    second = lint_manifest(
        _manifest([UNTAGGED_FIELD, {"field_id": "other_untagged_field"}, TAGGED_FIELD])
    )
    assert _codes(second) == [CODE_CLASSIFICATION_REQUIRED, CODE_CLASSIFICATION_REQUIRED]
    assert [f.subject for f in second.findings] == ["fields[0]", "fields[1]"]
    # The one passing declaration keeps its own index, not its position among
    # the classified fields.
    assert [(f.index, f.classification_index) for f in second.classified] == [(2, 0)]


def test_cli_distinguishes_tagged_from_untagged():
    with tempfile.TemporaryDirectory() as tmp:
        tagged = _run_cli(_manifest([TAGGED_FIELD]), tmp, "tagged.json")
        assert tagged.returncode == 0, tagged.stdout + tagged.stderr
        assert "SCN-MOD001-043" in tagged.stdout
        assert "PASS" in tagged.stdout

        mixed = _run_cli(_manifest([TAGGED_FIELD, UNTAGGED_FIELD]), tmp, "mixed.json")
        assert mixed.returncode == 1, mixed.stdout + mixed.stderr
        assert CODE_CLASSIFICATION_REQUIRED in mixed.stdout
        assert "fields[1]" in mixed.stdout
        assert "synthetic_untagged_field" not in mixed.stdout + mixed.stderr


def test_malformed_manifests_all_fail_closed():
    cases: list[tuple[str, object, str]] = [
        ("non-object top level", ["not", "a", "manifest"], CODE_MALFORMED_MANIFEST),
        (
            "missing kind label",
            _manifest([TAGGED_FIELD], manifest_kind="something-else"),
            CODE_MANIFEST_NOT_LABELED_SYNTHETIC,
        ),
        (
            "synthetic not literally true",
            _manifest([TAGGED_FIELD], synthetic="true"),
            CODE_MANIFEST_NOT_LABELED_SYNTHETIC,
        ),
        (
            "declared vocabulary absent",
            {
                "manifest_kind": MANIFEST_KIND,
                "synthetic": True,
                "fields": [TAGGED_FIELD],
            },
            CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
        ),
        (
            "declared vocabulary empty",
            _manifest([TAGGED_FIELD], declared_classifications=[]),
            CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
        ),
        (
            "declared vocabulary not a list of strings",
            _manifest([TAGGED_FIELD], declared_classifications=[RESTRICTED, 7]),
            CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
        ),
        (
            "declared vocabulary has a blank label",
            _manifest([TAGGED_FIELD], declared_classifications=[RESTRICTED, "  "]),
            CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
        ),
        (
            "declared vocabulary repeats a label",
            _manifest([TAGGED_FIELD], declared_classifications=[RESTRICTED, RESTRICTED]),
            CODE_MALFORMED_DECLARED_CLASSIFICATIONS,
        ),
        ("field list empty", _manifest([]), CODE_NO_FIELDS),
        ("field list not a list", {**_manifest([]), "fields": TAGGED_FIELD}, CODE_NO_FIELDS),
        ("field entry not an object", _manifest(["synthetic_field"]), CODE_MALFORMED_FIELD_ENTRY),
        (
            "field entry carries an unexpected key",
            _manifest([{**TAGGED_FIELD, "sample_value": SENTINEL_VALUE}]),
            CODE_MALFORMED_FIELD_ENTRY,
        ),
        (
            "field_id absent",
            _manifest([{"classification": RESTRICTED}]),
            CODE_MALFORMED_FIELD_ENTRY,
        ),
        (
            "field_id blank",
            _manifest([{"field_id": "   ", "classification": RESTRICTED}]),
            CODE_MALFORMED_FIELD_ENTRY,
        ),
        (
            "field_id not a string",
            _manifest([{"field_id": 1, "classification": RESTRICTED}]),
            CODE_MALFORMED_FIELD_ENTRY,
        ),
        (
            "classification null",
            _manifest([{"field_id": "synthetic_field", "classification": None}]),
            CODE_MALFORMED_CLASSIFICATION,
        ),
        (
            "classification blank",
            _manifest([{"field_id": "synthetic_field", "classification": "  "}]),
            CODE_MALFORMED_CLASSIFICATION,
        ),
        (
            "classification not a string",
            _manifest([{"field_id": "synthetic_field", "classification": ["Restricted"]}]),
            CODE_MALFORMED_CLASSIFICATION,
        ),
        (
            "classification outside the declared vocabulary",
            _manifest([{"field_id": "synthetic_field", "classification": "Confidential"}]),
            CODE_CLASSIFICATION_NOT_DECLARED,
        ),
    ]

    for label, manifest, expected_code in cases:
        outcome = lint_manifest(manifest)
        assert outcome.denied, f"{label}: expected a denial, got a pass"
        assert expected_code in _codes(outcome), f"{label}: codes were {_codes(outcome)}"
        assert outcome.classified == [], f"{label}: nothing may be reported as classified"

    # A repeated `field_id` is its own shape: the manifest is denied, and the
    # *first* declaration stays validly classified while the duplicate (which
    # could carry a different classification) is the one refused.
    duplicated = lint_manifest(
        _manifest(
            [TAGGED_FIELD, {"field_id": TAGGED_FIELD["field_id"], "classification": RESTRICTED}]
        )
    )
    assert duplicated.denied is True
    assert _codes(duplicated) == [CODE_DUPLICATE_FIELD_ID]
    assert [f.field_id for f in duplicated.classified] == [TAGGED_FIELD["field_id"]]
    # The collision is reported as a pair of indices, never as the shared
    # identifier (BUG-055).
    assert duplicated.findings[0].subject == "fields[1]"
    assert "fields[0]" in duplicated.findings[0].detail
    assert TAGGED_FIELD["field_id"] not in str(duplicated.findings[0])

    # Duplicate JSON object keys would otherwise resolve last-wins, letting an
    # unclassified declaration hide behind a classified one.
    with tempfile.TemporaryDirectory() as tmp:
        duplicate_keys = Path(tmp) / "duplicate_keys.json"
        duplicate_keys.write_text(
            json.dumps(_manifest([TAGGED_FIELD])).replace(
                '"classification": "Restricted"',
                '"classification": null, "classification": "Restricted"',
            ),
            encoding="utf-8",
        )
        outcome = run_validation(duplicate_keys)
        assert _codes(outcome) == [CODE_DUPLICATE_JSON_KEY]

        not_json = Path(tmp) / "not_json.json"
        not_json.write_text("{this is not JSON", encoding="utf-8")
        assert _codes(run_validation(not_json)) == [CODE_MALFORMED_MANIFEST]

        missing = Path(tmp) / "absent.json"
        assert _codes(run_validation(missing)) == [CODE_UNREADABLE_MANIFEST]

        # A directory stands in for any unreadable path: never a silent skip.
        assert _codes(run_validation(Path(tmp))) == [CODE_UNREADABLE_MANIFEST]

        assert main([str(missing)]) == 1


def test_report_cannot_echo_a_field_value():
    smuggled = _manifest([{**TAGGED_FIELD, "sample_value": SENTINEL_VALUE}])

    outcome = lint_manifest(smuggled)
    assert _codes(outcome) == [CODE_MALFORMED_FIELD_ENTRY]
    # Neither the smuggled value nor the extra key's own name is reported: the
    # key is counted instead (BUG-055).
    rendered = render_report(outcome, path=Path("manifest.json"))
    assert "1 unexpected key(s)" in rendered
    assert "sample_value" not in rendered
    assert SENTINEL_VALUE not in rendered

    with tempfile.TemporaryDirectory() as tmp:
        completed = _run_cli(smuggled, tmp, "smuggled.json")
        assert completed.returncode == 1, completed.stdout + completed.stderr
        assert SENTINEL_VALUE not in completed.stdout + completed.stderr
        assert "sample_value" not in completed.stdout + completed.stderr


def _probe_no_echo(label: str, manifest_text: str, expected_codes: list[str], exit_code: int):
    """Drive one raw manifest text through `run_validation`, `render_report`
    and the CLI, asserting `ECHO_SENTINEL` reaches none of them while the named
    DENY codes and exit status stay exactly as expected. The temporary file name
    deliberately never contains the sentinel, so the one manifest-external
    string the report is allowed to print (the operator-supplied path) cannot
    mask a real echo."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.json"
        path.write_text(manifest_text, encoding="utf-8")

        outcome = run_validation(path)
        assert _codes(outcome) == expected_codes, f"{label}: codes were {_codes(outcome)}"
        assert outcome.denied is bool(expected_codes), f"{label}: wrong denied flag"

        rendered = render_report(outcome, path=path)
        assert ECHO_SENTINEL not in rendered, f"{label}: sentinel echoed in the report"

        completed = subprocess.run(
            [sys.executable, str(LINT_SCRIPT), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == exit_code, f"{label}: exit {completed.returncode}"
        assert ECHO_SENTINEL not in completed.stdout + completed.stderr, (
            f"{label}: sentinel echoed on the CLI"
        )


def test_report_never_echoes_a_manifest_string():
    tagged_json = json.dumps(_manifest([TAGGED_FIELD]))
    cases: list[tuple[str, str, list[str], int]] = [
        # BUG-055's two reproducers, verbatim in shape.
        (
            "sentinel as an untagged `field_id`",
            json.dumps(_manifest([TAGGED_FIELD, {"field_id": ECHO_SENTINEL}])),
            [CODE_CLASSIFICATION_REQUIRED],
            1,
        ),
        (
            "sentinel as an unexpected field-entry key name",
            json.dumps(_manifest([{**TAGGED_FIELD, ECHO_SENTINEL: "declared"}])),
            [CODE_MALFORMED_FIELD_ENTRY],
            1,
        ),
        # The slot the original suite already covered, kept under the sentinel.
        (
            "sentinel as an unexpected field-entry key's value",
            json.dumps(_manifest([{**TAGGED_FIELD, "sample_value": ECHO_SENTINEL}])),
            [CODE_MALFORMED_FIELD_ENTRY],
            1,
        ),
        # `manifest_id`, on both a passing and a denied manifest: the passing
        # path renders the manifest-id line too.
        (
            "sentinel as `manifest_id`, manifest otherwise passing",
            json.dumps(_manifest([TAGGED_FIELD], manifest_id=ECHO_SENTINEL)),
            [],
            0,
        ),
        (
            "sentinel as `manifest_id` on a denied manifest",
            json.dumps(_manifest([UNTAGGED_FIELD], manifest_id=ECHO_SENTINEL)),
            [CODE_CLASSIFICATION_REQUIRED],
            1,
        ),
        # Classification labels: declared-and-used (passes, so the OK line must
        # not echo it), outside the vocabulary, and repeated in the vocabulary.
        (
            "sentinel as a declared classification label in use",
            json.dumps(
                _manifest(
                    [{"field_id": "synthetic_field", "classification": ECHO_SENTINEL}],
                    declared_classifications=[ECHO_SENTINEL],
                )
            ),
            [],
            0,
        ),
        (
            "sentinel as a classification outside the declared vocabulary",
            json.dumps(
                _manifest([{"field_id": "synthetic_field", "classification": ECHO_SENTINEL}])
            ),
            [CODE_CLASSIFICATION_NOT_DECLARED],
            1,
        ),
        (
            "sentinel as a repeated declared classification label",
            json.dumps(
                _manifest(
                    [TAGGED_FIELD],
                    declared_classifications=[RESTRICTED, ECHO_SENTINEL, ECHO_SENTINEL],
                )
            ),
            [CODE_MALFORMED_DECLARED_CLASSIFICATIONS],
            1,
        ),
        (
            "sentinel as a duplicated `field_id`",
            json.dumps(
                _manifest(
                    [
                        {"field_id": ECHO_SENTINEL, "classification": RESTRICTED},
                        {"field_id": ECHO_SENTINEL, "classification": RESTRICTED},
                    ]
                )
            ),
            [CODE_DUPLICATE_FIELD_ID],
            1,
        ),
        # Raw text, so the strict loader rather than the lint is the surface.
        (
            "sentinel as a duplicated JSON object key name",
            '{"' + ECHO_SENTINEL + '": 1, "' + ECHO_SENTINEL + '": 2}',
            [CODE_DUPLICATE_JSON_KEY],
            1,
        ),
        (
            "sentinel hidden behind a duplicated `classification` key",
            tagged_json.replace(
                '"classification": "Restricted"',
                f'"classification": "{ECHO_SENTINEL}", "classification": "Restricted"',
            ),
            [CODE_DUPLICATE_JSON_KEY],
            1,
        ),
        (
            "sentinel inside text that is not valid JSON",
            '{"manifest_id": "' + ECHO_SENTINEL + '", ',
            [CODE_MALFORMED_MANIFEST],
            1,
        ),
    ]

    for label, manifest_text, expected_codes, exit_code in cases:
        assert ECHO_SENTINEL in manifest_text, f"{label}: probe does not carry the sentinel"
        _probe_no_echo(label, manifest_text, expected_codes, exit_code)
