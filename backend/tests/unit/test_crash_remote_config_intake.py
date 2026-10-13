"""Unit tests for `app.crash_remote_config_intake` — GOV-01-R07, `SCN-MOD001-117`.

Stdlib only (`unittest`, `hmac`, `hashlib`, `json`), so these run under
`python -m unittest` without the project's pytest harness, while still
being collectable by it later. No database, no network, no sockets, no
mocking of the subject.

Every value here is synthetic: the verifying key is an explicitly-labeled
fake per `.claude/rules/infra/secrets.md` control 1, the crash reports and
release decisions are fabricated, the crash fingerprints are digests of
literal test strings, and no real client, store, crash backend, or
remote-config backend is touched.

Coverage maps to `SCN-MOD001-117`'s three parts:

- (a) a fabricated crash report is recorded and surfaced — and every
  rejection is surfaced too, so no submission is silently dropped;
- (b) a rollout-percentage change is published and read back without
  changing the disposition `version_negotiation.negotiate` produced,
  including while an authorized forced-update block is in effect;
- (c) an activation attempt that is not an authorized release decision is
  denied, citing missing authorization, with the same body `negotiate`
  itself returns.
"""

from __future__ import annotations

import hmac
import json
import unittest
from hashlib import sha256

from app.crash_remote_config_intake import (
    INTAKE_API_VERSION,
    KILL_SWITCH_NOT_AUTHORIZED_BY_DECISION,
    MAX_CRASH_REPORT_BYTES,
    PROBLEM_TYPE_BASE,
    ClientBootstrap,
    CrashPlatform,
    CrashReportIntake,
    CrashReportReceipt,
    EntryKind,
    EntryOutcome,
    IntakeJournal,
    JournalAtCapacity,
    KillSwitchActivationAttempt,
    KillSwitchActivationRecord,
    RolloutConfig,
    RolloutConfigStore,
    request_kill_switch_activation,
    resolve_client_bootstrap,
)
from app.version_negotiation import (
    API_VERSION,
    PROBLEM_CONTENT_TYPE,
    AppVersion,
    Disposition,
    ForcedUpdateReason,
    HmacSha256Verifier,
    NegotiationOutcome,
    NegotiationRequest,
    ProblemDetails,
    SignedReleaseDecision,
    negotiate,
)
from app.version_negotiation import (
    PROBLEM_TYPE_BASE as NEGOTIATION_PROBLEM_TYPE_BASE,
)

# Synthetic, non-secret, never a real credential.
SYNTHETIC_KEY = b"EXAMPLE_NOT_A_REAL_KEY-release-authorization"
SYNTHETIC_OTHER_KEY = b"EXAMPLE_NOT_A_REAL_KEY-different-authority"
SYNTHETIC_DECISION_ID = "SYNTHETIC-RELEASE-DECISION-0001"

# A digest of a literal test string — not a real stack trace.
SYNTHETIC_FINGERPRINT = sha256(b"SYNTHETIC_CRASH_FINGERPRINT_A").hexdigest()
OTHER_FINGERPRINT = sha256(b"SYNTHETIC_CRASH_FINGERPRINT_B").hexdigest()


def _sign(payload: bytes, key: bytes = SYNTHETIC_KEY) -> str:
    """The issuing authority's half, deliberately in the test: neither
    `version_negotiation` nor the intake module has a signing method."""
    return hmac.new(key, payload, sha256).hexdigest()


def _verifier() -> HmacSha256Verifier:
    return HmacSha256Verifier(key=SYNTHETIC_KEY)


def _crash_payload(
    *,
    report_id: str = "SYNTHETIC-CRASH-0001",
    app_version: str = "1.4.2",
    platform: str = "android",
    occurred_at: str = "2026-10-09T11:22:33+00:00",
    fingerprint: str = SYNTHETIC_FINGERPRINT,
    overrides: dict[str, object] | None = None,
    drop: str | None = None,
) -> bytes:
    body: dict[str, object] = {
        "report_id": report_id,
        "app_version": app_version,
        "platform": platform,
        "occurred_at": occurred_at,
        "fingerprint": fingerprint,
    }
    if overrides:
        body.update(overrides)
    if drop is not None:
        body.pop(drop, None)
    return json.dumps(body, sort_keys=True).encode("utf-8")


def _rollout_payload(
    *, config_version: int = 1, rollout_percentage: int = 10, **extra: object
) -> bytes:
    body: dict[str, object] = {
        "config_version": config_version,
        "rollout_percentage": rollout_percentage,
    }
    body.update(extra)
    return json.dumps(body, sort_keys=True).encode("utf-8")


def _decision_payload(
    *,
    minimum: str = "2.0.0",
    forced: bool = False,
    reason: str | None = None,
    decision_id: str = SYNTHETIC_DECISION_ID,
) -> bytes:
    body: dict[str, object] = {
        "decision_id": decision_id,
        "minimum_supported_version": minimum,
        "forced_update_required": forced,
        "forced_update_reason": reason,
    }
    return json.dumps(body, sort_keys=True).encode("utf-8")


def _negotiation_request(
    *,
    client: str,
    payload: bytes,
    signature: str | None = None,
) -> NegotiationRequest:
    return NegotiationRequest(
        api_version=API_VERSION,
        client_app_version=client,
        signed_decision=SignedReleaseDecision(
            payload=payload,
            signature=_sign(payload) if signature is None else signature,
        ),
    )


def _forced_decision_payload() -> bytes:
    return _decision_payload(minimum="2.0.0", forced=True, reason="security")


# --- (a) crash-report intake ----------------------------------------------


class CrashReportRecordedTest(unittest.TestCase):
    """`SCN-MOD001-117`(a): a fabricated crash report is recorded/surfaced,
    not silently dropped."""

    def setUp(self) -> None:
        self.journal = IntakeJournal()
        self.intake = CrashReportIntake(self.journal)

    def test_a_fabricated_report_is_accepted_recorded_and_surfaced(self) -> None:
        result = self.intake.record(INTAKE_API_VERSION, _crash_payload())

        assert isinstance(result, CrashReportReceipt)
        self.assertEqual(result.report_id, "SYNTHETIC-CRASH-0001")
        self.assertEqual(result.sequence, 1)
        self.assertFalse(result.replayed)

        # Surface 1: the intake's own recorded set.
        self.assertEqual(self.intake.recorded_count, 1)
        recorded = self.intake.recorded[0]
        self.assertEqual(recorded.report_id, "SYNTHETIC-CRASH-0001")
        self.assertEqual(recorded.app_version, AppVersion(1, 4, 2))
        self.assertEqual(recorded.platform, CrashPlatform.ANDROID)
        self.assertEqual(recorded.fingerprint, SYNTHETIC_FINGERPRINT)
        self.assertEqual(recorded.occurred_at.utcoffset().total_seconds(), 0)

        # Surface 2: the append-only journal.
        entries = self.journal.entries_of_kind(EntryKind.CRASH_REPORT)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].outcome, EntryOutcome.RECORDED)
        self.assertEqual(entries[0].subject_id, "SYNTHETIC-CRASH-0001")
        self.assertEqual(
            entries[0].to_record(),
            {
                "sequence": 1,
                "kind": "crash_report",
                "outcome": "recorded",
                "subject_id": "SYNTHETIC-CRASH-0001",
                "detail_code": "android",
            },
        )

    def test_reports_are_groupable_by_fingerprint(self) -> None:
        self.intake.record(INTAKE_API_VERSION, _crash_payload(report_id="A"))
        self.intake.record(INTAKE_API_VERSION, _crash_payload(report_id="B"))
        self.intake.record(
            INTAKE_API_VERSION,
            _crash_payload(report_id="C", fingerprint=OTHER_FINGERPRINT, platform="ios"),
        )

        self.assertEqual(self.intake.recorded_count, 3)
        self.assertEqual(len(self.intake.reports_with_fingerprint(SYNTHETIC_FINGERPRINT)), 2)
        self.assertEqual(len(self.intake.reports_with_fingerprint(OTHER_FINGERPRINT)), 1)
        self.assertEqual(
            self.intake.reports_with_fingerprint(OTHER_FINGERPRINT)[0].platform,
            CrashPlatform.IOS,
        )

    def test_a_resubmitted_report_id_is_recorded_once_and_visibly_replayed(self) -> None:
        first = self.intake.record(INTAKE_API_VERSION, _crash_payload())
        second = self.intake.record(INTAKE_API_VERSION, _crash_payload())

        assert isinstance(first, CrashReportReceipt)
        assert isinstance(second, CrashReportReceipt)
        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(second.sequence, first.sequence)
        self.assertEqual(self.intake.recorded_count, 1)

        outcomes = [entry.outcome for entry in self.journal.entries_of_kind(EntryKind.CRASH_REPORT)]
        self.assertEqual(outcomes, [EntryOutcome.RECORDED, EntryOutcome.REPLAYED])


class CrashReportRejectionTest(unittest.TestCase):
    """A rejection is an outcome, not a drop: every refused submission
    returns an RFC 7807 problem *and* leaves a journal entry."""

    def setUp(self) -> None:
        self.journal = IntakeJournal()
        self.intake = CrashReportIntake(self.journal)

    def _assert_problem(self, result: object, slug: str, status: int) -> ProblemDetails:
        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.problem_type, f"{PROBLEM_TYPE_BASE}{slug}")
        self.assertEqual(result.status, status)
        self.assertEqual(result.content_type, PROBLEM_CONTENT_TYPE)
        self.assertEqual(sorted(result.to_body()), ["detail", "status", "title", "type"])
        return result

    def test_an_unsupported_intake_api_version_is_refused_and_journaled(self) -> None:
        result = self.intake.record("v0", _crash_payload())
        self._assert_problem(result, "unsupported-intake-api-version", 400)
        self.assertEqual(self.intake.recorded_count, 0)
        entries = self.journal.entries_of_kind(EntryKind.CRASH_REPORT)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].outcome, EntryOutcome.REJECTED)
        self.assertEqual(entries[0].detail_code, "unsupported_intake_api_version")

    def test_every_malformed_shape_is_refused_and_journaled(self) -> None:
        cases: dict[str, bytes] = {
            "unrecognized field": _crash_payload(overrides={"stack_trace": "x"}),
            "missing field": _crash_payload(drop="fingerprint"),
            "empty report_id": _crash_payload(report_id=""),
            "non-ascii report_id": _crash_payload(report_id="crash-é"),
            "oversized report_id": _crash_payload(report_id="x" * 129),
            "non-canonical app_version": _crash_payload(app_version="1.4"),
            "unsupported platform": _crash_payload(platform="web"),
            "naive occurred_at": _crash_payload(occurred_at="2026-10-09T11:22:33"),
            "non-utc occurred_at": _crash_payload(occurred_at="2026-10-09T11:22:33+02:00"),
            "short fingerprint": _crash_payload(fingerprint="abc123"),
            "uppercase fingerprint": _crash_payload(fingerprint=SYNTHETIC_FINGERPRINT.upper()),
            "non-hex fingerprint": _crash_payload(fingerprint="z" * 64),
            "wrong type for platform": _crash_payload(overrides={"platform": 7}),
            "duplicate key": b'{"report_id": "A", "report_id": "B"}',
            "not an object": b'["not", "an", "object"]',
            "not json": b"{not json",
            "oversized payload": b'{"report_id": "' + b"x" * MAX_CRASH_REPORT_BYTES + b'"}',
        }
        for label, payload in cases.items():
            with self.subTest(case=label):
                before = len(self.journal.entries)
                result = self.intake.record(INTAKE_API_VERSION, payload)
                self._assert_problem(result, "malformed-crash-report", 422)
                self.assertEqual(len(self.journal.entries), before + 1)
                self.assertEqual(self.journal.entries[-1].outcome, EntryOutcome.REJECTED)

        self.assertEqual(self.intake.recorded_count, 0)

    def test_a_rejection_detail_never_echoes_a_submitted_value(self) -> None:
        secretish = "SYNTHETIC-VALUE-THAT-MUST-NOT-BE-ECHOED"
        result = self.intake.record(
            INTAKE_API_VERSION, _crash_payload(overrides={"breadcrumbs": secretish})
        )
        assert isinstance(result, ProblemDetails)
        self.assertNotIn(secretish, result.detail)
        # Field *names* are not echoed either for unrecognized fields — only
        # a count is reported.
        self.assertNotIn("breadcrumbs", result.detail)

    def test_recorded_report_capacity_is_refused_rather_than_overwritten(self) -> None:
        intake = CrashReportIntake(self.journal, max_recorded=1)
        first = intake.record(INTAKE_API_VERSION, _crash_payload(report_id="A"))
        assert isinstance(first, CrashReportReceipt)

        overflow = intake.record(INTAKE_API_VERSION, _crash_payload(report_id="B"))
        self._assert_problem(overflow, "intake-capacity-exhausted", 503)
        self.assertEqual(intake.recorded_count, 1)
        self.assertEqual(intake.recorded[0].report_id, "A")

    def test_a_full_journal_refuses_the_report_rather_than_recording_it_unaudited(self) -> None:
        journal = IntakeJournal(max_entries=1)
        intake = CrashReportIntake(journal)
        first = intake.record(INTAKE_API_VERSION, _crash_payload(report_id="A"))
        assert isinstance(first, CrashReportReceipt)

        overflow = intake.record(INTAKE_API_VERSION, _crash_payload(report_id="B"))
        self._assert_problem(overflow, "intake-capacity-exhausted", 503)
        self.assertEqual(intake.recorded_count, 1)
        # Even the unrecordable refusal is counted, so it is not invisible.
        self.assertEqual(journal.refused_appends, 1)
        self.assertTrue(journal.at_capacity)


class JournalTest(unittest.TestCase):
    def test_entries_are_append_only_and_sequenced(self) -> None:
        journal = IntakeJournal()
        journal.append(
            kind=EntryKind.CRASH_REPORT,
            outcome=EntryOutcome.RECORDED,
            subject_id="A",
            detail_code="android",
        )
        journal.append(
            kind=EntryKind.ROLLOUT_CONFIG_PUBLISH,
            outcome=EntryOutcome.RECORDED,
            subject_id="1",
            detail_code="rollout_percentage=10",
        )
        self.assertEqual([entry.sequence for entry in journal.entries], [1, 2])
        # `entries` is a copy: a caller cannot mutate the journal through it.
        self.assertIsInstance(journal.entries, tuple)
        with self.assertRaises(AttributeError):
            journal.entries[0].outcome = EntryOutcome.DENIED  # type: ignore[misc]

    def test_capacity_refuses_the_append_instead_of_evicting(self) -> None:
        journal = IntakeJournal(max_entries=1)
        journal.append(
            kind=EntryKind.CRASH_REPORT,
            outcome=EntryOutcome.RECORDED,
            subject_id="A",
            detail_code="android",
        )
        with self.assertRaises(JournalAtCapacity):
            journal.append(
                kind=EntryKind.CRASH_REPORT,
                outcome=EntryOutcome.RECORDED,
                subject_id="B",
                detail_code="android",
            )
        self.assertEqual(len(journal.entries), 1)
        self.assertEqual(journal.entries[0].subject_id, "A")
        self.assertEqual(journal.refused_appends, 1)

    def test_a_zero_capacity_journal_is_refused_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            IntakeJournal(max_entries=0)


# --- (b) rollout-only remote config ---------------------------------------


class RolloutConfigTest(unittest.TestCase):
    """`SCN-MOD001-117`(b), first half: a rollout-percentage change is
    published and read back."""

    def setUp(self) -> None:
        self.journal = IntakeJournal()
        self.store = RolloutConfigStore(self.journal)

    def test_a_published_rollout_percentage_is_readable(self) -> None:
        published = self.store.publish(INTAKE_API_VERSION, _rollout_payload(rollout_percentage=25))
        assert isinstance(published, RolloutConfig)
        self.assertEqual(published, RolloutConfig(config_version=1, rollout_percentage=25))

        fetched = self.store.fetch(INTAKE_API_VERSION)
        self.assertEqual(fetched, published)
        self.assertEqual(self.store.current, published)

        entries = self.journal.entries_of_kind(EntryKind.ROLLOUT_CONFIG_PUBLISH)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].outcome, EntryOutcome.RECORDED)
        self.assertEqual(entries[0].detail_code, "rollout_percentage=25")

    def test_an_advancing_config_version_replaces_the_previous_rollout(self) -> None:
        self.store.publish(
            INTAKE_API_VERSION, _rollout_payload(config_version=1, rollout_percentage=5)
        )
        self.store.publish(
            INTAKE_API_VERSION, _rollout_payload(config_version=2, rollout_percentage=100)
        )
        self.assertEqual(
            self.store.current, RolloutConfig(config_version=2, rollout_percentage=100)
        )

    def test_an_unpublished_surface_answers_explicitly_rather_than_emptily(self) -> None:
        result = self.store.fetch(INTAKE_API_VERSION)
        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.problem_type, f"{PROBLEM_TYPE_BASE}rollout-config-not-published")
        self.assertEqual(result.status, 404)

    def test_a_release_control_field_in_remote_config_is_refused(self) -> None:
        """TSD §24.3: remote config controls rollout, not the contract. Each
        of these is an attempt to steer release control through the rollout
        channel."""
        for field, value in (
            ("kill_switch", True),
            ("kill_switch_active", True),
            ("forced_update_required", True),
            ("forced_update_reason", "security"),
            ("minimum_supported_version", "9.9.9"),
            ("decision_id", "SYNTHETIC-FORGED-0001"),
            ("disposition", "allowed"),
            ("blocked", False),
        ):
            with self.subTest(field=field):
                store = RolloutConfigStore(IntakeJournal())
                result = store.publish(INTAKE_API_VERSION, _rollout_payload(**{field: value}))
                assert isinstance(result, ProblemDetails)
                self.assertEqual(
                    result.problem_type,
                    f"{PROBLEM_TYPE_BASE}rollout-config-field-not-permitted",
                )
                self.assertEqual(result.status, 422)
                self.assertIsNone(store.current)

    def test_malformed_rollout_payloads_are_refused(self) -> None:
        cases: dict[str, bytes] = {
            "percentage above range": _rollout_payload(rollout_percentage=101),
            "negative percentage": _rollout_payload(rollout_percentage=-1),
            "boolean percentage": _rollout_payload(rollout_percentage=True),
            "string percentage": _rollout_payload(rollout_percentage="50"),
            "float percentage": _rollout_payload(rollout_percentage=12.5),
            "zero config_version": _rollout_payload(config_version=0),
            "boolean config_version": _rollout_payload(config_version=True),
            "unrecognized field": _rollout_payload(cohort="beta"),
            "missing field": b'{"rollout_percentage": 10}',
            "duplicate key": b'{"config_version": 1, "config_version": 2, "rollout_percentage": 1}',
            "not an object": b"42",
            "not json": b"{",
        }
        for label, payload in cases.items():
            with self.subTest(case=label):
                store = RolloutConfigStore(IntakeJournal())
                result = store.publish(INTAKE_API_VERSION, payload)
                assert isinstance(result, ProblemDetails)
                self.assertEqual(
                    result.problem_type, f"{PROBLEM_TYPE_BASE}malformed-rollout-config"
                )
                self.assertEqual(result.status, 422)
                self.assertIsNone(store.current)

    def test_a_non_advancing_config_version_is_refused(self) -> None:
        self.store.publish(
            INTAKE_API_VERSION, _rollout_payload(config_version=4, rollout_percentage=40)
        )
        for replayed_version in (4, 3, 1):
            with self.subTest(config_version=replayed_version):
                result = self.store.publish(
                    INTAKE_API_VERSION,
                    _rollout_payload(config_version=replayed_version, rollout_percentage=0),
                )
                assert isinstance(result, ProblemDetails)
                self.assertEqual(
                    result.problem_type,
                    f"{PROBLEM_TYPE_BASE}rollout-config-version-not-advancing",
                )
                self.assertEqual(result.status, 409)
        self.assertEqual(self.store.current, RolloutConfig(config_version=4, rollout_percentage=40))

    def test_an_unsupported_intake_api_version_is_refused_on_publish_and_fetch(self) -> None:
        published = self.store.publish("v0", _rollout_payload())
        assert isinstance(published, ProblemDetails)
        self.assertEqual(published.status, 400)
        self.assertIsNone(self.store.current)

        fetched = self.store.fetch("v0")
        assert isinstance(fetched, ProblemDetails)
        self.assertEqual(fetched.status, 400)


class RolloutDoesNotBypassTheKillSwitchTest(unittest.TestCase):
    """`SCN-MOD001-117`(b)'s companion check: a remote-config change alone
    does NOT bypass `SCN-MOD001-115`'s kill-switch block."""

    def setUp(self) -> None:
        self.journal = IntakeJournal()
        self.store = RolloutConfigStore(self.journal)
        self.verifier = _verifier()
        self.blocked_request = _negotiation_request(
            client="1.0.0", payload=_forced_decision_payload()
        )

    def test_the_block_holds_at_every_rollout_percentage(self) -> None:
        reference = negotiate(self.blocked_request, self.verifier)
        assert isinstance(reference, NegotiationOutcome)
        self.assertEqual(reference.disposition, Disposition.BLOCKED_FORCED_UPDATE)

        for index, percentage in enumerate((0, 1, 50, 99, 100), start=1):
            with self.subTest(rollout_percentage=percentage):
                published = self.store.publish(
                    INTAKE_API_VERSION,
                    _rollout_payload(config_version=index, rollout_percentage=percentage),
                )
                assert isinstance(published, RolloutConfig)

                result = resolve_client_bootstrap(self.blocked_request, self.verifier, self.store)
                assert isinstance(result, ClientBootstrap)

                # The rollout change is genuinely applied and readable...
                self.assertEqual(result.rollout, published)
                self.assertEqual(result.rollout.rollout_percentage, percentage)
                # ...and the disposition is byte-for-byte the one `negotiate`
                # produced with no rollout document in scope at all.
                self.assertEqual(result.negotiation, reference)
                self.assertEqual(result.negotiation.disposition, Disposition.BLOCKED_FORCED_UPDATE)
                self.assertTrue(result.negotiation.blocked)
                self.assertEqual(
                    result.negotiation.forced_update_reason, ForcedUpdateReason.SECURITY
                )

    def test_an_absent_rollout_document_does_not_change_the_disposition(self) -> None:
        result = resolve_client_bootstrap(self.blocked_request, self.verifier, self.store)
        assert isinstance(result, ClientBootstrap)
        self.assertIsNone(result.rollout)
        self.assertEqual(result.negotiation.disposition, Disposition.BLOCKED_FORCED_UPDATE)

    def test_a_rollout_document_does_not_block_a_client_that_negotiates_cleanly(self) -> None:
        self.store.publish(INTAKE_API_VERSION, _rollout_payload(rollout_percentage=100))
        allowed_request = _negotiation_request(client="2.1.0", payload=_forced_decision_payload())

        result = resolve_client_bootstrap(allowed_request, self.verifier, self.store)
        assert isinstance(result, ClientBootstrap)
        self.assertEqual(result.negotiation.disposition, Disposition.ALLOWED)
        self.assertFalse(result.negotiation.blocked)
        self.assertEqual(result.rollout, RolloutConfig(config_version=1, rollout_percentage=100))

    def test_a_negotiation_failure_is_returned_before_any_rollout_read(self) -> None:
        class _NeverFetchedStore(RolloutConfigStore):
            def fetch(self, api_version: str) -> ProblemDetails | RolloutConfig:
                raise AssertionError("rollout config must not be read for a failed negotiation")

        unauthorized = _negotiation_request(
            client="1.0.0", payload=_forced_decision_payload(), signature=""
        )
        result = resolve_client_bootstrap(
            unauthorized, self.verifier, _NeverFetchedStore(self.journal)
        )
        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 401)

    def test_the_negotiation_request_has_no_rollout_input_to_begin_with(self) -> None:
        """The structural half of the property: there is no field through
        which a rollout value could enter the decision."""
        self.assertEqual(
            sorted(NegotiationRequest.__dataclass_fields__),
            ["api_version", "client_app_version", "signed_decision"],
        )


# --- (c) kill-switch activation attempt -----------------------------------


class KillSwitchActivationDeniedTest(unittest.TestCase):
    """`SCN-MOD001-117`(c): an activation attempt made through any path other
    than an authorized release decision is denied, citing missing
    authorization."""

    def setUp(self) -> None:
        self.journal = IntakeJournal()
        self.verifier = _verifier()

    def _attempt(
        self,
        *,
        signed: SignedReleaseDecision | None,
        requested_by: str = "synthetic-operator",
        api_version: str = INTAKE_API_VERSION,
    ) -> KillSwitchActivationAttempt:
        return KillSwitchActivationAttempt(
            api_version=api_version,
            signed_decision=signed,
            requested_by=requested_by,
        )

    def _assert_unauthorized(self, result: object) -> ProblemDetails:
        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 401)
        self.assertEqual(
            result.problem_type,
            f"{NEGOTIATION_PROBLEM_TYPE_BASE}release-decision-unauthorized",
        )
        self.assertEqual(result.content_type, PROBLEM_CONTENT_TYPE)
        self.assertIn("authorized release decision", result.detail)
        return result

    def test_an_attempt_with_no_authorization_at_all_is_denied(self) -> None:
        result = request_kill_switch_activation(
            self._attempt(signed=None), self.verifier, self.journal
        )
        self._assert_unauthorized(result)

        entries = self.journal.entries_of_kind(EntryKind.KILL_SWITCH_ACTIVATION_ATTEMPT)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].outcome, EntryOutcome.DENIED)
        self.assertEqual(entries[0].detail_code, "release_decision_unauthorized")

    def test_an_empty_signature_is_denied(self) -> None:
        payload = _forced_decision_payload()
        result = request_kill_switch_activation(
            self._attempt(signed=SignedReleaseDecision(payload=payload, signature="")),
            self.verifier,
            self.journal,
        )
        self._assert_unauthorized(result)

    def test_a_signature_from_another_key_is_denied(self) -> None:
        payload = _forced_decision_payload()
        result = request_kill_switch_activation(
            self._attempt(
                signed=SignedReleaseDecision(
                    payload=payload, signature=_sign(payload, SYNTHETIC_OTHER_KEY)
                )
            ),
            self.verifier,
            self.journal,
        )
        self._assert_unauthorized(result)

    def test_a_payload_swapped_under_a_genuine_signature_is_denied(self) -> None:
        signed_for = _decision_payload(minimum="2.0.0", forced=False, reason=None)
        forged = _forced_decision_payload()
        result = request_kill_switch_activation(
            self._attempt(
                signed=SignedReleaseDecision(payload=forged, signature=_sign(signed_for))
            ),
            self.verifier,
            self.journal,
        )
        self._assert_unauthorized(result)

    def test_the_denial_body_is_identical_to_the_negotiation_surface_denial(self) -> None:
        """One denial text, one problem type: the two surfaces give a caller
        no differing oracle for why authorization failed."""
        payload = _forced_decision_payload()
        from_intake = request_kill_switch_activation(
            self._attempt(signed=SignedReleaseDecision(payload=payload, signature="")),
            self.verifier,
            self.journal,
        )
        from_negotiation = negotiate(
            _negotiation_request(client="1.0.0", payload=payload, signature=""), self.verifier
        )
        assert isinstance(from_intake, ProblemDetails)
        assert isinstance(from_negotiation, ProblemDetails)
        self.assertEqual(from_intake.to_body(), from_negotiation.to_body())

    def test_a_requester_label_cannot_substitute_for_authorization(self) -> None:
        for label in ("release-manager", "ci-pipeline", "owner", "root"):
            with self.subTest(requested_by=label):
                result = request_kill_switch_activation(
                    self._attempt(signed=None, requested_by=label),
                    self.verifier,
                    IntakeJournal(),
                )
                self._assert_unauthorized(result)

    def test_an_attempt_carries_no_field_for_asserting_its_own_forced_update(self) -> None:
        self.assertEqual(
            sorted(KillSwitchActivationAttempt.__dataclass_fields__),
            ["api_version", "requested_by", "signed_decision"],
        )

    def test_a_malformed_requester_label_is_refused(self) -> None:
        for label in ("", "x" * 129):
            with self.subTest(requested_by=label):
                result = request_kill_switch_activation(
                    self._attempt(signed=None, requested_by=label),
                    self.verifier,
                    IntakeJournal(),
                )
                assert isinstance(result, ProblemDetails)
                self.assertEqual(
                    result.problem_type, f"{PROBLEM_TYPE_BASE}malformed-activation-attempt"
                )

    def test_an_unsupported_intake_api_version_is_refused_before_authorization(self) -> None:
        class _NeverCalledVerifier:
            def verify(self, payload: bytes, signature: str) -> bool:
                raise AssertionError("authorization must not be consulted for this request")

        payload = _forced_decision_payload()
        result = request_kill_switch_activation(
            self._attempt(
                signed=SignedReleaseDecision(payload=payload, signature=_sign(payload)),
                api_version="v0",
            ),
            _NeverCalledVerifier(),
            self.journal,
        )
        assert isinstance(result, ProblemDetails)
        self.assertEqual(result.status, 400)


class KillSwitchActivationAuthorizedTest(unittest.TestCase):
    """An authorized activation produces a derived record — not a stored
    flag, and not a second authority."""

    def setUp(self) -> None:
        self.journal = IntakeJournal()
        self.verifier = _verifier()

    def _authorized_attempt(self, payload: bytes) -> KillSwitchActivationAttempt:
        return KillSwitchActivationAttempt(
            api_version=INTAKE_API_VERSION,
            signed_decision=SignedReleaseDecision(payload=payload, signature=_sign(payload)),
            requested_by="synthetic-operator",
        )

    def test_a_signed_forced_update_decision_authorizes_and_is_audited(self) -> None:
        payload = _forced_decision_payload()
        result = request_kill_switch_activation(
            self._authorized_attempt(payload), self.verifier, self.journal
        )

        assert isinstance(result, KillSwitchActivationRecord)
        self.assertEqual(result.decision_id, SYNTHETIC_DECISION_ID)
        self.assertEqual(result.minimum_supported_version, AppVersion(2, 0, 0))
        self.assertEqual(result.forced_update_reason, ForcedUpdateReason.SECURITY)
        self.assertEqual(result.requested_by, "synthetic-operator")

        entries = self.journal.entries_of_kind(EntryKind.KILL_SWITCH_ACTIVATION_ATTEMPT)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].outcome, EntryOutcome.AUTHORIZED)
        self.assertEqual(entries[0].subject_id, SYNTHETIC_DECISION_ID)
        self.assertEqual(entries[0].detail_code, "security")

    def test_an_authorized_decision_that_requires_no_forced_update_cannot_activate(self) -> None:
        payload = _decision_payload(minimum="2.0.0", forced=False, reason=None)
        result = request_kill_switch_activation(
            self._authorized_attempt(payload), self.verifier, self.journal
        )
        assert isinstance(result, ProblemDetails)
        self.assertEqual(
            result.problem_type,
            f"{PROBLEM_TYPE_BASE}{KILL_SWITCH_NOT_AUTHORIZED_BY_DECISION.slug}",
        )
        self.assertEqual(result.status, 422)

    def test_an_unreserved_forced_update_reason_is_refused_by_the_shared_contract(self) -> None:
        payload = _decision_payload(minimum="2.0.0", forced=True, reason="marketing")
        result = request_kill_switch_activation(
            self._authorized_attempt(payload), self.verifier, self.journal
        )
        assert isinstance(result, ProblemDetails)
        self.assertEqual(
            result.problem_type,
            f"{NEGOTIATION_PROBLEM_TYPE_BASE}forced-update-reason-not-reserved",
        )
        self.assertEqual(result.status, 422)

    def test_a_malformed_but_authorized_decision_is_refused_by_the_shared_contract(self) -> None:
        payload = json.dumps({"decision_id": "A"}, sort_keys=True).encode("utf-8")
        result = request_kill_switch_activation(
            self._authorized_attempt(payload), self.verifier, self.journal
        )
        assert isinstance(result, ProblemDetails)
        self.assertEqual(
            result.problem_type,
            f"{NEGOTIATION_PROBLEM_TYPE_BASE}malformed-release-decision",
        )

    def test_an_activation_record_confers_no_block_of_its_own(self) -> None:
        """No parallel kill-switch state: the authoritative disposition still
        comes only from presenting the signed decision to `negotiate`."""
        forced_payload = _forced_decision_payload()
        record = request_kill_switch_activation(
            self._authorized_attempt(forced_payload), self.verifier, self.journal
        )
        assert isinstance(record, KillSwitchActivationRecord)

        store = RolloutConfigStore(self.journal)

        # A client at or above the minimum is still allowed, activation or not.
        at_minimum = resolve_client_bootstrap(
            _negotiation_request(client="2.0.0", payload=forced_payload), self.verifier, store
        )
        assert isinstance(at_minimum, ClientBootstrap)
        self.assertEqual(at_minimum.negotiation.disposition, Disposition.ALLOWED)

        # And a *different*, non-forced decision is unaffected by the
        # activation record that was just produced.
        optional_payload = _decision_payload(minimum="2.0.0", forced=False, reason=None)
        below_minimum = resolve_client_bootstrap(
            _negotiation_request(client="1.0.0", payload=optional_payload), self.verifier, store
        )
        assert isinstance(below_minimum, ClientBootstrap)
        self.assertEqual(
            below_minimum.negotiation.disposition, Disposition.ALLOWED_WITH_UPDATE_PROMPT
        )


class ModuleSurfaceTest(unittest.TestCase):
    """Structural properties the module's own docstring claims."""

    def test_the_module_holds_no_mutable_module_level_state(self) -> None:
        import app.crash_remote_config_intake as module

        mutable = [
            name
            for name, value in vars(module).items()
            if not name.startswith("__") and isinstance(value, (list, dict, set, bytearray))
        ]
        self.assertEqual(mutable, [])

    def test_the_module_defines_no_signing_or_kill_switch_toggle_callable(self) -> None:
        """Only names *defined here* are checked: `SignedReleaseDecision` and
        friends are imported from `version_negotiation`, which is the point —
        this module reuses that contract rather than minting its own."""
        import app.crash_remote_config_intake as module

        defined = [
            name
            for name, value in vars(module).items()
            if callable(value) and getattr(value, "__module__", None) == module.__name__
        ]
        self.assertNotEqual(defined, [])
        for name in defined:
            lowered = name.lower()
            with self.subTest(name=name):
                self.assertNotIn("sign", lowered)
                self.assertFalse(lowered.startswith(("set_", "activate_", "enable_", "disable_")))
        self.assertFalse(hasattr(module, "sign"))

    def test_the_intake_surface_is_versioned(self) -> None:
        self.assertEqual(INTAKE_API_VERSION, "v1")
        self.assertTrue(PROBLEM_TYPE_BASE.startswith("https://veyro.invalid/problems/"))


if __name__ == "__main__":
    unittest.main()
