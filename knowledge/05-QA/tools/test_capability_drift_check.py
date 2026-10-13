"""Regression tests for capability_drift_check.py (BUG-043, 2026-10-01):
snapshot-vs-live-table parse confusion, retired-capability false material-
change findings, and pending-capability compared-as-approved findings.
Run: backend/.venv/bin/python -m pytest <this file> -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import capability_drift_check as cdc


def _row(review_status="**APPROVED** (fresh review)", version="v1", content_hash="hash1"):
    row = {c: "" for c in cdc.REGISTRY_COLUMNS}
    row["version"] = version
    row["content_hash"] = content_hash
    row["review_status"] = review_status
    return row


# ---- parse separation (the core BUG-043 defect) ----

def test_snapshot_rows_not_misparsed_as_unparseable_live_rows():
    text = (
        "| CAP-001 | cap | prov | v1 | h1 | scope | **APPROVED** | q | qd | a | ad | lr | nrd | rb | ev |\n"
        "\n" + cdc.SNAPSHOT_MARKER + "\n\n"
        "| CAP-001 | v1 | h1 |\n"
        "| CAP-002 | some version text | some hash text |\n"
    )
    rows, unparsed = cdc.parse_registry_rows(text)
    assert unparsed == [], f"snapshot rows must not be reported as unparseable live rows, got {unparsed}"
    assert set(rows) == {"CAP-001"}


def test_malformed_live_row_still_fails_closed():
    text = (
        "| CAP-001 | only three cells |\n"
        "\n" + cdc.SNAPSHOT_MARKER + "\n\n"
        "| CAP-001 | v1 | h1 |\n"
    )
    rows, unparsed = cdc.parse_registry_rows(text)
    assert rows == {}
    assert len(unparsed) == 1
    assert "CAP-001" in unparsed[0][0]


def test_snapshot_parse_unaffected_by_split():
    text = (
        "| CAP-001 | cap | prov | v1 | h1 | scope | **APPROVED** | q | qd | a | ad | lr | nrd | rb | ev |\n"
        "\n" + cdc.SNAPSHOT_MARKER + "\n\n"
        "| CAP-001 | v1 | h1 |\n"
    )
    snap = cdc.parse_snapshot(text)
    assert snap == {"CAP-001": ("v1", "h1")}


# ---- retired/revoked capabilities ----

def test_resolve_lifecycle_matches_existing_convention_when_corroborated():
    # Superseded 2026-10-01 (BUG-045): a status-update marker alone is no
    # longer sufficient -- it must be corroborated by the Lifecycle-status
    # section's own field sentence. See test_run_regression.py /
    # BUG-045 for the fuller lifecycle-resolution regression suite
    # (reinstatement-wins, unauthorized-marker, same-date-conflict).
    text = (
        "prose\n\n**CAP-007 status update (2026-09-28): RETIRED.** more text\n"
        "CAP-007's `lifecycle_status` is now **`REVOKED`**\n"
    )
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert resolved == {"CAP-007": "RETIRED"}
    assert conflicts == []


def test_resolve_lifecycle_fails_closed_without_corroboration():
    text = "**CAP-001 status update (2026-10-05): RETIRED.** no field sentence anywhere\n"
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert resolved == {}, "an unbacked marker must never resolve to RETIRED"
    assert len(conflicts) == 1 and "no corroborating" in conflicts[0]


def test_retired_capability_with_drifted_version_is_info_not_error():
    row = _row(review_status="**APPROVED**", version="v2-changed", content_hash="h2-changed")
    errors, info = cdc.evaluate_capability("CAP-007", row, ("v1", "h1"), "RETIRED")
    assert errors == [], f"retired capability must not error on drift, got {errors}"
    assert len(info) == 1 and "RETIRED" in info[0] and "non-live" in info[0]


def test_retired_capability_with_no_drift_is_still_info():
    row = _row(review_status="**APPROVED**", version="v1", content_hash="h1")
    errors, info = cdc.evaluate_capability("CAP-007", row, ("v1", "h1"), "RETIRED")
    assert errors == []
    assert len(info) == 1 and "RETIRED" in info[0]


# ---- pending/unapproved capabilities ----

def test_is_approved_rejects_pending():
    assert cdc.is_approved("**PENDING — found unregistered**") is False
    assert cdc.is_approved("APPROVED (narrowed scope above)") is True
    assert cdc.is_approved("**APPROVED, scope de-rated**") is True


def test_pending_capability_with_drift_is_info_not_error():
    row = _row(review_status="**PENDING — not yet qualified**", version="v2", content_hash="h2")
    errors, info = cdc.evaluate_capability("CAP-008", row, ("v1", "h1"), None)
    assert errors == [], f"pending capability must not be compared as though approved, got {errors}"
    assert len(info) == 1 and "not yet approved" in info[0]


def test_pending_capability_with_no_snapshot_is_info_not_error():
    row = _row(review_status="**PENDING**", version="v1", content_hash="h1")
    errors, info = cdc.evaluate_capability("CAP-008", row, None, None)
    assert errors == [], "missing snapshot for a pending capability must not fail closed"
    assert len(info) == 1 and "not yet approved" in info[0]


# ---- fail-closed preserved for the real target case ----

def test_approved_capability_with_drift_still_errors():
    row = _row(review_status="**APPROVED**", version="v2-changed", content_hash="h1")
    errors, info = cdc.evaluate_capability("CAP-001", row, ("v1", "h1"), None)
    assert len(errors) == 1 and "MATERIAL CHANGE DETECTED" in errors[0]
    assert info == []


def test_approved_capability_missing_snapshot_still_errors():
    row = _row(review_status="**APPROVED**", version="v1", content_hash="h1")
    errors, info = cdc.evaluate_capability("CAP-001", row, None, None)
    assert len(errors) == 1 and "no snapshot row recorded" in errors[0]


def test_approved_capability_no_drift_is_clean_info():
    row = _row(review_status="**APPROVED**", version="v1", content_hash="h1")
    errors, info = cdc.evaluate_capability("CAP-001", row, ("v1", "h1"), None)
    assert errors == []
    assert len(info) == 1 and "no drift" in info[0]


# ---- BUG-045: fail-closed lifecycle resolution (latest-dated, corroborated) ----

def _lifecycle_text(*status_updates, field=None):
    """Build synthetic registry prose: status_updates is a list of
    (cap_id, date, word) tuples; field is {cap_id: word} for the
    Lifecycle-status section's own corroborating sentence."""
    lines = [f"**{cid} status update ({date}): {word}.**" for cid, date, word in status_updates]
    if field:
        for cid, word in field.items():
            lines.append(f"{cid}'s `lifecycle_status` is now **`{word}`**")
    return "\n".join(lines) + "\n"


def test_later_reinstatement_marker_wins_over_earlier_retirement():
    text = _lifecycle_text(
        ("CAP-007", "2026-09-28", "RETIRED"),
        ("CAP-007", "2026-10-10", "REINSTATED"),
        field={"CAP-007": "ACTIVE"},
    )
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert conflicts == []
    assert resolved == {"CAP-007": "ACTIVE"}, "the later REINSTATED marker must supersede the earlier RETIRED one"


def test_reinstated_capability_is_not_passed_as_retired_to_evaluate_capability():
    text = _lifecycle_text(
        ("CAP-007", "2026-09-28", "RETIRED"),
        ("CAP-007", "2026-10-10", "REINSTATED"),
        field={"CAP-007": "ACTIVE"},
    )
    resolved, _ = cdc.resolve_capability_lifecycle(text)
    retired_status = resolved.get("CAP-007")
    assert retired_status != "RETIRED"
    # Mirrors main()'s own guard: only a 'RETIRED' bucket is ever forwarded.
    passed_through = retired_status if retired_status == "RETIRED" else None
    row = _row(review_status="**APPROVED**", version="v2-changed", content_hash="h1")
    errors, info = cdc.evaluate_capability("CAP-007", row, ("v1", "h1"), passed_through)
    assert len(errors) == 1 and "MATERIAL CHANGE DETECTED" in errors[0], (
        "once reinstated, real drift must be gated normally again, not silently waved through"
    )


def test_unauthorized_retirement_marker_does_not_suppress_drift():
    # A RETIRED marker with no corroborating lifecycle_status field --
    # must not resolve to RETIRED, and the capability's real drift must
    # still be caught as an error (not suppressed).
    text = _lifecycle_text(("CAP-001", "2026-10-05", "RETIRED"))
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert "CAP-001" not in resolved
    assert len(conflicts) == 1 and "no corroborating" in conflicts[0]

    row = _row(review_status="**APPROVED**", version="v2-changed", content_hash="h1")
    errors, info = cdc.evaluate_capability("CAP-001", row, ("v1", "h1"), resolved.get("CAP-001"))
    assert len(errors) == 1 and "MATERIAL CHANGE DETECTED" in errors[0]


def test_unauthorized_marker_disagreeing_with_field_also_fails_closed():
    # Marker says RETIRED, field sentence says ACTIVE -- disagreement.
    text = _lifecycle_text(("CAP-001", "2026-10-05", "RETIRED"), field={"CAP-001": "ACTIVE"})
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert "CAP-001" not in resolved
    assert len(conflicts) == 1 and "disagreement" in conflicts[0]


def test_same_date_conflicting_markers_fails_closed():
    text = _lifecycle_text(
        ("CAP-007", "2026-09-28", "RETIRED"),
        ("CAP-007", "2026-09-28", "REINSTATED"),
        field={"CAP-007": "REVOKED"},
    )
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert "CAP-007" not in resolved
    assert len(conflicts) == 1 and "same date" in conflicts[0]


def test_duplicate_identical_same_date_marker_is_not_a_conflict():
    # The exact same (date, word) repeated is not a conflict -- only a
    # genuine disagreement on the same date is.
    text = _lifecycle_text(
        ("CAP-007", "2026-09-28", "RETIRED"),
        ("CAP-007", "2026-09-28", "RETIRED"),
        field={"CAP-007": "REVOKED"},
    )
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert conflicts == []
    assert resolved == {"CAP-007": "RETIRED"}


def test_real_registry_cap007_resolves_retired_with_no_conflicts():
    text = cdc.REGISTRY.read_text(encoding="utf-8", errors="replace")
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert conflicts == [], f"real registry must have no unresolved lifecycle conflicts, got {conflicts}"
    assert resolved.get("CAP-007") == "RETIRED"


def test_capability_with_no_marker_at_all_is_simply_absent():
    text = _lifecycle_text(field={"CAP-001": "ACTIVE"})  # field sentence alone, no marker
    resolved, conflicts = cdc.resolve_capability_lifecycle(text)
    assert resolved == {}
    assert conflicts == []


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
