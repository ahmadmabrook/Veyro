"""Crash-report intake and rollout-only remote config — GOV-01-R07, `SCN-MOD001-117`.

The companion half of `backend/app/version_negotiation.py`, per
`IMPLEMENTATION.md` §12's own split: that file is the version/kill-switch
*enforcement*, this file is "synthetic backend-side intake endpoints for
(a) crash-report ingestion (recorded/surfaced, not silently dropped) and
(b) remote-config fetch (rollout-percentage changes only — TSD §24.3:
remote config controls rollout, not contract repair, so this endpoint
cannot itself bypass `version_negotiation.py`'s kill-switch block)."

Governing source, TSD §24.3 (`TSD_MIRROR.md` lines 11670-11700), verbatim
on the two clauses this file governs: "Remote config controls rollout but
cannot repair an incompatible API contract"; "Minimum supported version,
optional/forced update and kill-switch policy are explicit." Plus
`EIP_MIRROR.md` lines 17572-17575 ("crash monitoring and remote
configuration") and `REQUIREMENTS.md` GOV-01-R07's security-implications
text: forced-update/kill-switch "must not be triggerable without the
equivalent of an authorized release decision."

`SCN-MOD001-117`'s three parts map to three entry points here:

- (a) `CrashReportIntake.record` — a fabricated crash report is validated,
  recorded, and surfaced on two independent surfaces (the returned
  receipt and the append-only `IntakeJournal`). A rejected report is
  surfaced too, as an RFC 7807 problem plus a journal entry: the one
  outcome this intake never produces is *silence*.
- (b) `RolloutConfigStore` + `resolve_client_bootstrap` — a rollout
  percentage is published and read back, while the negotiation
  disposition is produced by `version_negotiation.negotiate` and returned
  verbatim. Rollout is read *after* the decision and is never an input to
  it, so a rollout change cannot lift an authorized forced-update block.
- (c) `request_kill_switch_activation` — an activation attempt that is not
  accompanied by an authorized (signed) release decision is denied,
  citing missing authorization.

What this module is, exactly:

- **Pure in-process contracts.** No FastAPI route, no network binding, no
  socket, no environment variable, no file, no database, and no log line.
  The word "endpoint" in §12 describes the integration *point* a real
  crash/remote-config SDK will later be pointed at; the HTTP binding is
  not created by this slice. State lives in explicit, caller-constructed
  objects (`IntakeJournal`, `CrashReportIntake`, `RolloutConfigStore`), so
  this module holds no module-level mutable state at all.
- **Versioned** (`INTAKE_API_VERSION`/`SUPPORTED_INTAKE_API_VERSIONS`) and
  failing with RFC 7807 `application/problem+json` bodies, per
  `ADR_CONFORMANCE.md`'s ADR-004 obligation on this exact file. That ADR's
  conformance state stays PLANNED until `SCN-MOD001-119`(a) executes.
- **No parallel kill-switch state and no second signing authority.** This
  module stores no kill-switch flag, exposes no activation toggle, and
  implements no verification of its own: authorization is the injected
  `ReleaseAuthorizationVerifier` and the decision contract is
  `version_negotiation.parse_release_decision`, consulted in that same
  order. The denial body for an unauthorized activation is
  `version_negotiation`'s own, reused rather than restated, so the two
  surfaces cannot drift into giving a caller two different oracles.
- **Verify-only, and symmetric.** As in `version_negotiation.py`, there is
  no signing method here, and the synthetic HMAC verifier nevertheless
  holds a symmetric key — a process holding it could compute signatures.
  This slice establishes **no** production signer/verifier separation.
- **No free-text, no PII.** The crash-report contract carries an opaque
  SHA-256-shaped fingerprint, never a stack trace, breadcrumb trail, log
  excerpt, device identifier, or user field — so there is no channel
  through which member data could enter
  (`.claude/rules/backend/performance.md` controls 5-6). Problem `detail`
  strings are fixed authored text that never echo untrusted input.
- **Fail-closed and bounded.** Unsupported version, malformed payload,
  duplicate key, oversized body, non-advancing config version, exhausted
  capacity, and absent authorization are all explicit denials. Nothing
  defaults to allow and nothing is dropped on the floor.

Synthetic only: no real crash report, no real remote-config backend, no
real key, no real client, no store action, no Production activation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Final

# The one private name imported across the module boundary, deliberately:
# an unauthorized activation must return the *same* denial body
# `negotiate` returns, so a caller cannot use the difference between two
# surfaces as an oracle for why authorization failed. Restating the text
# here would be a second source of truth for it.
from app.version_negotiation import _UNAUTHORIZED_DETAIL as _NEGOTIATION_UNAUTHORIZED_DETAIL
from app.version_negotiation import (
    FORCED_UPDATE_REASON_NOT_RESERVED,
    MALFORMED_RELEASE_DECISION,
    RELEASE_DECISION_UNAUTHORIZED,
    AppVersion,
    ForcedUpdateReason,
    ForcedUpdateReasonNotReserved,
    MalformedReleaseDecision,
    NegotiationOutcome,
    NegotiationRequest,
    ProblemDetails,
    ReleaseAuthorizationVerifier,
    SignedReleaseDecision,
    negotiate,
    parse_release_decision,
)

# --- Versioned surface (ADR-004: "Versioned REST command/query APIs") ------

# This surface is versioned independently of the negotiation surface: the
# two are separate contracts and may diverge, so neither reads the other's
# version constant.
INTAKE_API_VERSION: Final = "v1"
SUPPORTED_INTAKE_API_VERSIONS: Final[frozenset[str]] = frozenset({INTAKE_API_VERSION})

# --- RFC 7807 problem surface (ADR-004: "RFC 7807 errors") -----------------

# RFC 2606 `.invalid` TLD, as in `version_negotiation.py`: a deliberately
# non-resolvable base, so no real Veyro domain is committed to.
PROBLEM_TYPE_BASE: Final = "https://veyro.invalid/problems/crash-remote-config-intake/"

# Bounds. Every one is a fail-closed input/resource guard, not a tuning knob.
MAX_CRASH_REPORT_BYTES: Final = 4096
MAX_ROLLOUT_CONFIG_BYTES: Final = 1024
MAX_REPORT_ID_LENGTH: Final = 128
MAX_REQUESTED_BY_LENGTH: Final = 128
FINGERPRINT_LENGTH: Final = 64
MAX_RECORDED_CRASH_REPORTS: Final = 1024
MAX_JOURNAL_ENTRIES: Final = 4096

# Used as a journal subject when a payload was rejected before any
# identifier in it could be trusted. Never an identifier from the payload.
UNIDENTIFIED_SUBJECT: Final = "unidentified"


@dataclass(frozen=True)
class _ProblemKind:
    """This module's own problem namespace.

    Shaped like `version_negotiation.py`'s equivalent rather than imported
    from it: the `type` URIs differ by design (a distinct surface gets a
    distinct problem namespace), and the renderer is the shared public
    `ProblemDetails`, which is what callers actually depend on.
    """

    slug: str
    title: str
    status: int

    def detailed(self, detail: str) -> ProblemDetails:
        return ProblemDetails(
            problem_type=f"{PROBLEM_TYPE_BASE}{self.slug}",
            title=self.title,
            status=self.status,
            detail=detail,
        )


UNSUPPORTED_INTAKE_API_VERSION: Final = _ProblemKind(
    slug="unsupported-intake-api-version",
    title="Unsupported intake API version",
    status=400,
)
MALFORMED_CRASH_REPORT: Final = _ProblemKind(
    slug="malformed-crash-report",
    title="Malformed crash report",
    status=422,
)
INTAKE_CAPACITY_EXHAUSTED: Final = _ProblemKind(
    slug="intake-capacity-exhausted",
    title="Intake capacity exhausted",
    status=503,
)
MALFORMED_ROLLOUT_CONFIG: Final = _ProblemKind(
    slug="malformed-rollout-config",
    title="Malformed rollout configuration",
    status=422,
)
ROLLOUT_CONFIG_FIELD_NOT_PERMITTED: Final = _ProblemKind(
    slug="rollout-config-field-not-permitted",
    title="Remote config controls rollout only",
    status=422,
)
ROLLOUT_CONFIG_VERSION_NOT_ADVANCING: Final = _ProblemKind(
    slug="rollout-config-version-not-advancing",
    title="Rollout configuration version does not advance",
    status=409,
)
ROLLOUT_CONFIG_NOT_PUBLISHED: Final = _ProblemKind(
    slug="rollout-config-not-published",
    title="No rollout configuration has been published",
    status=404,
)
KILL_SWITCH_NOT_AUTHORIZED_BY_DECISION: Final = _ProblemKind(
    slug="kill-switch-not-authorized-by-decision",
    title="The release decision does not authorize a kill switch",
    status=422,
)
MALFORMED_ACTIVATION_ATTEMPT: Final = _ProblemKind(
    slug="malformed-activation-attempt",
    title="Malformed kill-switch activation attempt",
    status=422,
)

_CAPACITY_DETAIL: Final = (
    "The intake is at its declared capacity and is refusing new records rather than discarding one."
)


class MalformedIntakePayload(ValueError):
    """A submitted payload whose shape/types are not the closed contract.

    A `ValueError` subclass for the same reason
    `version_negotiation.MalformedReleaseDecision` is one: a payload that
    does not satisfy its contract is one rejection class, whether the
    offending field was absent, the wrong type, or out of range — the
    caller maps it to one problem type rather than leaking the distinction.
    """


# --- Append-only journal (the "surfaced, not silently dropped" surface) ----


class EntryKind(Enum):
    """The three intake subjects `SCN-MOD001-117` names, and only those."""

    CRASH_REPORT = "crash_report"
    ROLLOUT_CONFIG_PUBLISH = "rollout_config_publish"
    KILL_SWITCH_ACTIVATION_ATTEMPT = "kill_switch_activation_attempt"


class EntryOutcome(Enum):
    """What happened to one submission. `REPLAYED` exists so that a
    recognized duplicate is still visibly *handled* rather than silently
    discarded."""

    RECORDED = "recorded"
    REPLAYED = "replayed"
    REJECTED = "rejected"
    AUTHORIZED = "authorized"
    DENIED = "denied"


class JournalAtCapacity(RuntimeError):
    """The journal refused an append rather than evicting an existing entry.

    An append-only audit surface that silently drops its oldest entries
    under pressure is the exact "silently dropped" failure part (a) exists
    to rule out, so the bound denies the *new* write and the caller turns
    that into an explicit RFC 7807 response.
    """


@dataclass(frozen=True)
class JournalEntry:
    """One append-only, immutable record of one submission.

    Carries identifiers and codes only — never payload bytes, never a
    signature, never a key, never free text from a caller. `to_record()` is
    the field-keyed structured shape
    `.claude/rules/backend/performance.md` control 4 requires, produced for
    an observability sink to consume; this module emits no log line itself.
    """

    sequence: int
    kind: EntryKind
    outcome: EntryOutcome
    subject_id: str
    detail_code: str

    def to_record(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "outcome": self.outcome.value,
            "subject_id": self.subject_id,
            "detail_code": self.detail_code,
        }


class IntakeJournal:
    """A bounded, append-only, in-memory journal.

    Append-only in the `.claude/rules/backend/concurrency.md` control 5
    sense: entries are never mutated in place, so no optimistic-version
    column applies. In-memory only — this slice adds no table and no
    migration.
    """

    def __init__(self, *, max_entries: int = MAX_JOURNAL_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError("a journal must permit at least one entry")
        self._max_entries = max_entries
        self._entries: list[JournalEntry] = []
        self._refused_appends = 0

    @property
    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    @property
    def refused_appends(self) -> int:
        """How many appends were refused at capacity.

        Still observable when the journal itself can no longer record
        anything, so even the capacity failure is counted rather than lost.
        """
        return self._refused_appends

    @property
    def at_capacity(self) -> bool:
        return len(self._entries) >= self._max_entries

    def entries_of_kind(self, kind: EntryKind) -> tuple[JournalEntry, ...]:
        return tuple(entry for entry in self._entries if entry.kind is kind)

    def append(
        self,
        *,
        kind: EntryKind,
        outcome: EntryOutcome,
        subject_id: str,
        detail_code: str,
    ) -> JournalEntry:
        if self.at_capacity:
            self._refused_appends += 1
            raise JournalAtCapacity("journal is at its declared capacity")
        entry = JournalEntry(
            sequence=len(self._entries) + 1,
            kind=kind,
            outcome=outcome,
            subject_id=subject_id,
            detail_code=detail_code,
        )
        self._entries.append(entry)
        return entry


# --- (a) Crash-report intake ----------------------------------------------


class CrashPlatform(Enum):
    """The two platforms TSD §24.3's release policy governs. A closed set:
    an unrecognized platform is rejected, not recorded as "other"."""

    ANDROID = "android"
    IOS = "ios"


@dataclass(frozen=True)
class CrashReport:
    """A validated crash report.

    Note what is absent: no stack trace, no log excerpt, no breadcrumb, no
    device or user identifier, no free-text message. `fingerprint` is an
    opaque client-computed digest, which is all this integration point
    needs in order to group and count crashes — and is the reason no
    member data can reach this record at all.
    """

    report_id: str
    app_version: AppVersion
    platform: CrashPlatform
    occurred_at: datetime
    fingerprint: str


@dataclass(frozen=True)
class CrashReportReceipt:
    """Proof to the submitter that the report was recorded, not dropped.

    `replayed` is true when this receipt answers a resubmission of an
    already-recorded `report_id`: the original sequence is returned and the
    report is recorded exactly once.
    """

    report_id: str
    sequence: int
    replayed: bool


_CRASH_REPORT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "report_id",
        "app_version",
        "platform",
        "occurred_at",
        "fingerprint",
    }
)

_HEX_DIGITS: Final[frozenset[str]] = frozenset("0123456789abcdef")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """JSON's last-key-wins default would let a duplicated field shadow the
    one that was validated. Reject instead — the same control
    `version_negotiation.parse_release_decision` applies to decisions."""
    seen: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise MalformedIntakePayload("duplicate field in payload")
        seen[key] = value
    return seen


def _decode_json_object(payload: bytes, *, max_bytes: int) -> dict[str, object]:
    """Decode a bounded JSON object, rejecting duplicates.

    Raises `MalformedIntakePayload`.
    """
    if len(payload) > max_bytes:
        raise MalformedIntakePayload("payload exceeds the permitted size")
    try:
        parsed = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedIntakePayload("payload is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise MalformedIntakePayload("payload must be a JSON object")
    return parsed


def _require_closed_field_set(parsed: dict[str, object], expected: frozenset[str]) -> None:
    """Only field *names* drawn from the closed contract, or a count, are
    reported — never a field value."""
    present = frozenset(parsed)
    if present != expected:
        missing = sorted(expected - present)
        unrecognized = sorted(present - expected)
        raise MalformedIntakePayload(
            f"field set is not the closed contract "
            f"(missing={missing}, unrecognized={len(unrecognized)})"
        )


def _parse_utc_instant(raw: object) -> datetime:
    """Parse a strict ISO-8601 instant that explicitly carries UTC.

    A naive timestamp is rejected rather than assumed to be UTC: "assume
    the server's clock" is how a crash's own ordering quietly becomes
    wrong.
    """
    if not isinstance(raw, str):
        raise MalformedIntakePayload("occurred_at must be a string")
    if len(raw) > 64:
        raise MalformedIntakePayload("occurred_at exceeds the permitted length")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise MalformedIntakePayload("occurred_at is not a valid ISO-8601 instant") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise MalformedIntakePayload("occurred_at must carry an explicit UTC offset")
    return parsed


def parse_crash_report(payload: bytes) -> CrashReport:
    """Validate a crash-report payload against its closed contract.

    Raises `MalformedIntakePayload` with a message that names only field
    names and reasons — never a submitted value.
    """
    parsed = _decode_json_object(payload, max_bytes=MAX_CRASH_REPORT_BYTES)
    _require_closed_field_set(parsed, _CRASH_REPORT_FIELDS)

    report_id = parsed["report_id"]
    if not isinstance(report_id, str) or not report_id:
        raise MalformedIntakePayload("report_id must be a non-empty string")
    if len(report_id) > MAX_REPORT_ID_LENGTH:
        raise MalformedIntakePayload("report_id exceeds the permitted length")
    if not report_id.isascii() or not report_id.isprintable():
        raise MalformedIntakePayload("report_id must be printable ASCII")

    raw_version = parsed["app_version"]
    if not isinstance(raw_version, str):
        raise MalformedIntakePayload("app_version must be a string")
    try:
        app_version = AppVersion.parse(raw_version)
    except ValueError as exc:
        raise MalformedIntakePayload(
            "app_version is not a canonical MAJOR.MINOR.PATCH version"
        ) from exc

    raw_platform = parsed["platform"]
    if not isinstance(raw_platform, str):
        raise MalformedIntakePayload("platform must be a string")
    try:
        platform = CrashPlatform(raw_platform)
    except ValueError as exc:
        raise MalformedIntakePayload("platform is outside the supported android/ios set") from exc

    occurred_at = _parse_utc_instant(parsed["occurred_at"])

    fingerprint = parsed["fingerprint"]
    if not isinstance(fingerprint, str):
        raise MalformedIntakePayload("fingerprint must be a string")
    if len(fingerprint) != FINGERPRINT_LENGTH or not _HEX_DIGITS.issuperset(fingerprint):
        raise MalformedIntakePayload("fingerprint must be a lowercase 64-character hex digest")

    return CrashReport(
        report_id=report_id,
        app_version=app_version,
        platform=platform,
        occurred_at=occurred_at,
        fingerprint=fingerprint,
    )


class CrashReportIntake:
    """`SCN-MOD001-117`(a): the crash-monitoring integration point.

    A submitted report always produces one of exactly two visible results —
    a receipt, or an RFC 7807 problem — and in both cases a journal entry.
    There is no code path that accepts a submission and returns nothing.
    """

    def __init__(
        self,
        journal: IntakeJournal,
        *,
        max_recorded: int = MAX_RECORDED_CRASH_REPORTS,
    ) -> None:
        if max_recorded < 1:
            raise ValueError("an intake must permit at least one recorded report")
        self._journal = journal
        self._max_recorded = max_recorded
        self._recorded: list[CrashReport] = []
        self._receipts: dict[str, CrashReportReceipt] = {}

    @property
    def recorded(self) -> tuple[CrashReport, ...]:
        """The recorded reports, in submission order — the "surfaced" half of
        part (a), independent of the journal."""
        return tuple(self._recorded)

    @property
    def recorded_count(self) -> int:
        return len(self._recorded)

    def reports_with_fingerprint(self, fingerprint: str) -> tuple[CrashReport, ...]:
        """Grouping by fingerprint is the whole point of recording one: this
        is what a crash-monitoring surface reads to count an occurrence."""
        return tuple(report for report in self._recorded if report.fingerprint == fingerprint)

    def record(self, api_version: str, payload: bytes) -> ProblemDetails | CrashReportReceipt:
        if api_version not in SUPPORTED_INTAKE_API_VERSIONS:
            return self._rejected(
                UNSUPPORTED_INTAKE_API_VERSION.detailed(
                    f"This intake speaks only API version(s): "
                    f"{', '.join(sorted(SUPPORTED_INTAKE_API_VERSIONS))}."
                ),
                subject_id=UNIDENTIFIED_SUBJECT,
                detail_code="unsupported_intake_api_version",
            )

        try:
            report = parse_crash_report(payload)
        except MalformedIntakePayload as exc:
            return self._rejected(
                MALFORMED_CRASH_REPORT.detailed(str(exc)),
                subject_id=UNIDENTIFIED_SUBJECT,
                detail_code="malformed_crash_report",
            )

        existing = self._receipts.get(report.report_id)
        if existing is not None:
            replayed = CrashReportReceipt(
                report_id=existing.report_id,
                sequence=existing.sequence,
                replayed=True,
            )
            try:
                self._journal.append(
                    kind=EntryKind.CRASH_REPORT,
                    outcome=EntryOutcome.REPLAYED,
                    subject_id=report.report_id,
                    detail_code="duplicate_report_id",
                )
            except JournalAtCapacity:
                return INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL)
            return replayed

        if len(self._recorded) >= self._max_recorded:
            return self._rejected(
                INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL),
                subject_id=report.report_id,
                detail_code="recorded_report_capacity_exhausted",
            )

        # Journal first: if the audit surface cannot accept the entry, the
        # report is refused rather than recorded unaudited.
        try:
            self._journal.append(
                kind=EntryKind.CRASH_REPORT,
                outcome=EntryOutcome.RECORDED,
                subject_id=report.report_id,
                detail_code=report.platform.value,
            )
        except JournalAtCapacity:
            return INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL)

        self._recorded.append(report)
        receipt = CrashReportReceipt(
            report_id=report.report_id,
            sequence=len(self._recorded),
            replayed=False,
        )
        self._receipts[report.report_id] = receipt
        return receipt

    def _rejected(
        self,
        problem: ProblemDetails,
        *,
        subject_id: str,
        detail_code: str,
    ) -> ProblemDetails:
        """A rejection is journaled too — a refusal is an outcome, not a drop."""
        try:
            self._journal.append(
                kind=EntryKind.CRASH_REPORT,
                outcome=EntryOutcome.REJECTED,
                subject_id=subject_id,
                detail_code=detail_code,
            )
        except JournalAtCapacity:
            return INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL)
        return problem


# --- (b) Rollout-only remote config ---------------------------------------


@dataclass(frozen=True)
class RolloutConfig:
    """A validated remote-config document.

    Two fields, and only two. There is no minimum-supported-version field,
    no forced-update field, and no kill-switch field, because TSD §24.3
    puts those inside a *signed release decision* and gives remote config
    rollout only.
    """

    config_version: int
    rollout_percentage: int


_ROLLOUT_CONFIG_FIELDS: Final[frozenset[str]] = frozenset({"config_version", "rollout_percentage"})

# Names that belong to the signed release decision, or that a caller might
# reach for when trying to steer release control through remote config.
# Presence of any one of them is reported as a *release-control* refusal
# rather than a generic unknown-field refusal, so the attempt is legible in
# the journal instead of being flattened into "malformed". The authoritative
# decision contract remains `version_negotiation.parse_release_decision`'s;
# this set exists only to classify a refusal.
_RELEASE_CONTROL_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "decision_id",
        "minimum_supported_version",
        "forced_update_required",
        "forced_update_reason",
        "forced_update",
        "kill_switch",
        "kill_switch_active",
        "disposition",
        "blocked",
    }
)


class ReleaseControlFieldNotPermitted(MalformedIntakePayload):
    """A rollout payload carrying a release-control field.

    Distinct from a generic malformed payload because it is the specific
    TSD §24.3 boundary being crossed, and the caller maps it to its own
    problem type.
    """


def parse_rollout_config(payload: bytes) -> RolloutConfig:
    """Validate a rollout-config payload against its closed contract.

    Raises `ReleaseControlFieldNotPermitted` or `MalformedIntakePayload`.
    """
    parsed = _decode_json_object(payload, max_bytes=MAX_ROLLOUT_CONFIG_BYTES)

    intruding = frozenset(parsed) & _RELEASE_CONTROL_FIELD_NAMES
    if intruding:
        raise ReleaseControlFieldNotPermitted(
            f"remote config carries rollout only; release-control field(s) "
            f"{sorted(intruding)} belong to a signed release decision"
        )
    _require_closed_field_set(parsed, _ROLLOUT_CONFIG_FIELDS)

    config_version = parsed["config_version"]
    # `isinstance(True, int)` is True, so an exact type check is required.
    if type(config_version) is not int or config_version < 1:
        raise MalformedIntakePayload("config_version must be a positive JSON integer")
    if config_version > 2**31 - 1:
        raise MalformedIntakePayload("config_version exceeds the permitted range")

    rollout_percentage = parsed["rollout_percentage"]
    if type(rollout_percentage) is not int:
        raise MalformedIntakePayload("rollout_percentage must be a JSON integer")
    if not 0 <= rollout_percentage <= 100:
        raise MalformedIntakePayload("rollout_percentage must be between 0 and 100 inclusive")

    return RolloutConfig(config_version=config_version, rollout_percentage=rollout_percentage)


class RolloutConfigStore:
    """`SCN-MOD001-117`(b): the remote-config integration point.

    Holds exactly one current rollout document. Deliberately *not* a
    general-purpose config store: there is no key/value surface a release
    flag could be smuggled through, and the only mutable field is a
    percentage.
    """

    def __init__(self, journal: IntakeJournal) -> None:
        self._journal = journal
        self._current: RolloutConfig | None = None

    @property
    def current(self) -> RolloutConfig | None:
        return self._current

    def publish(self, api_version: str, payload: bytes) -> ProblemDetails | RolloutConfig:
        if api_version not in SUPPORTED_INTAKE_API_VERSIONS:
            return self._rejected(
                UNSUPPORTED_INTAKE_API_VERSION.detailed(
                    f"This intake speaks only API version(s): "
                    f"{', '.join(sorted(SUPPORTED_INTAKE_API_VERSIONS))}."
                ),
                detail_code="unsupported_intake_api_version",
            )

        try:
            config = parse_rollout_config(payload)
        except ReleaseControlFieldNotPermitted as exc:
            return self._rejected(
                ROLLOUT_CONFIG_FIELD_NOT_PERMITTED.detailed(str(exc)),
                detail_code="release_control_field_not_permitted",
            )
        except MalformedIntakePayload as exc:
            return self._rejected(
                MALFORMED_ROLLOUT_CONFIG.detailed(str(exc)),
                detail_code="malformed_rollout_config",
            )

        current = self._current
        if current is not None and config.config_version <= current.config_version:
            # A replayed or rolled-back config version is refused: otherwise
            # an old document could silently re-take effect.
            return self._rejected(
                ROLLOUT_CONFIG_VERSION_NOT_ADVANCING.detailed(
                    "config_version must be greater than the currently published one."
                ),
                detail_code="config_version_not_advancing",
            )

        try:
            self._journal.append(
                kind=EntryKind.ROLLOUT_CONFIG_PUBLISH,
                outcome=EntryOutcome.RECORDED,
                subject_id=str(config.config_version),
                detail_code=f"rollout_percentage={config.rollout_percentage}",
            )
        except JournalAtCapacity:
            return INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL)

        self._current = config
        return config

    def fetch(self, api_version: str) -> ProblemDetails | RolloutConfig:
        """Read the current rollout document. A read is not journaled — it
        changes nothing — but an absent document is an explicit problem
        rather than a silent empty answer."""
        if api_version not in SUPPORTED_INTAKE_API_VERSIONS:
            return UNSUPPORTED_INTAKE_API_VERSION.detailed(
                f"This intake speaks only API version(s): "
                f"{', '.join(sorted(SUPPORTED_INTAKE_API_VERSIONS))}."
            )
        current = self._current
        if current is None:
            return ROLLOUT_CONFIG_NOT_PUBLISHED.detailed(
                "No rollout configuration has been published for this surface."
            )
        return current

    def _rejected(self, problem: ProblemDetails, *, detail_code: str) -> ProblemDetails:
        try:
            self._journal.append(
                kind=EntryKind.ROLLOUT_CONFIG_PUBLISH,
                outcome=EntryOutcome.REJECTED,
                subject_id=UNIDENTIFIED_SUBJECT,
                detail_code=detail_code,
            )
        except JournalAtCapacity:
            return INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL)
        return problem


@dataclass(frozen=True)
class ClientBootstrap:
    """A negotiation disposition plus the rollout document, side by side.

    `negotiation` is whatever `version_negotiation.negotiate` returned,
    unmodified. `rollout` is `None` when nothing has been published —
    absence of a rollout document is not an error and does not alter the
    disposition.
    """

    negotiation: NegotiationOutcome
    rollout: RolloutConfig | None


def resolve_client_bootstrap(
    request: NegotiationRequest,
    verifier: ReleaseAuthorizationVerifier,
    rollout_store: RolloutConfigStore,
    *,
    intake_api_version: str = INTAKE_API_VERSION,
) -> ProblemDetails | ClientBootstrap:
    """`SCN-MOD001-117`(b)'s companion check, as code rather than a comment.

    Order is the control, and it is the whole point of this function:

    1. `negotiate(request, verifier)` decides. The rollout store is **not**
       passed to it and cannot be — `NegotiationRequest` has no field for
       it — so no rollout value is in scope when the disposition is formed.
    2. The rollout document is read afterwards and attached unchanged.

    A `BLOCKED_FORCED_UPDATE` disposition therefore survives any rollout
    value, including a 100% rollout: "remote config controls rollout but
    cannot repair an incompatible API contract" (TSD §24.3).
    """
    negotiated = negotiate(request, verifier)
    if isinstance(negotiated, ProblemDetails):
        return negotiated

    fetched = rollout_store.fetch(intake_api_version)
    if isinstance(fetched, ProblemDetails):
        if fetched.problem_type == f"{PROBLEM_TYPE_BASE}{ROLLOUT_CONFIG_NOT_PUBLISHED.slug}":
            return ClientBootstrap(negotiation=negotiated, rollout=None)
        return fetched
    return ClientBootstrap(negotiation=negotiated, rollout=fetched)


# --- (c) Kill-switch activation attempt -----------------------------------


@dataclass(frozen=True)
class KillSwitchActivationAttempt:
    """An attempt to activate the kill switch.

    `signed_decision` is `None` when the attempt carries no authorization at
    all — the shape `SCN-MOD001-117`(c) names ("a request lacking the
    release-authorization credential/signature"). `requested_by` is an audit
    label only: it is recorded, never consulted for authorization, and never
    echoed into a problem body. There is deliberately no field through which
    an attempt could assert its own reason or its own forced-update flag;
    those live only inside the signed decision.
    """

    api_version: str
    signed_decision: SignedReleaseDecision | None
    requested_by: str


@dataclass(frozen=True)
class KillSwitchActivationRecord:
    """An authorized activation, derived entirely from the signed decision.

    This is a *record*, not a state change. Nothing in this module stores
    it, and no negotiation consults it: the authoritative block is still
    produced by `version_negotiation.negotiate` when the same signed
    decision is presented with a client version. Holding this object confers
    nothing.
    """

    decision_id: str
    minimum_supported_version: AppVersion
    forced_update_reason: ForcedUpdateReason
    requested_by: str


def request_kill_switch_activation(
    attempt: KillSwitchActivationAttempt,
    verifier: ReleaseAuthorizationVerifier,
    journal: IntakeJournal,
) -> ProblemDetails | KillSwitchActivationRecord:
    """`SCN-MOD001-117`(c): deny an activation that is not an authorized
    release decision.

    Every authorization step here is `version_negotiation`'s, in
    `negotiate`'s own order — the injected verifier over the exact received
    bytes first, then the closed decision contract — and the denial body is
    `negotiate`'s own. This function adds no verification, no key, no
    signing, and no kill-switch state of its own.
    """
    if attempt.api_version not in SUPPORTED_INTAKE_API_VERSIONS:
        return _denied(
            journal,
            UNSUPPORTED_INTAKE_API_VERSION.detailed(
                f"This intake speaks only API version(s): "
                f"{', '.join(sorted(SUPPORTED_INTAKE_API_VERSIONS))}."
            ),
            subject_id=UNIDENTIFIED_SUBJECT,
            detail_code="unsupported_intake_api_version",
            outcome=EntryOutcome.REJECTED,
        )

    if not attempt.requested_by or len(attempt.requested_by) > MAX_REQUESTED_BY_LENGTH:
        return _denied(
            journal,
            MALFORMED_ACTIVATION_ATTEMPT.detailed(
                "requested_by must be a non-empty label within the permitted length."
            ),
            subject_id=UNIDENTIFIED_SUBJECT,
            detail_code="malformed_requested_by",
            outcome=EntryOutcome.REJECTED,
        )

    signed = attempt.signed_decision
    # Absent authorization and non-matching authorization take the same
    # branch and produce the same body: no oracle for which one it was.
    if signed is None or not verifier.verify(signed.payload, signed.signature):
        return _denied(
            journal,
            RELEASE_DECISION_UNAUTHORIZED.detailed(_NEGOTIATION_UNAUTHORIZED_DETAIL),
            subject_id=UNIDENTIFIED_SUBJECT,
            detail_code="release_decision_unauthorized",
            outcome=EntryOutcome.DENIED,
        )

    try:
        decision = parse_release_decision(signed.payload)
    except ForcedUpdateReasonNotReserved as exc:
        return _denied(
            journal,
            FORCED_UPDATE_REASON_NOT_RESERVED.detailed(str(exc)),
            subject_id=UNIDENTIFIED_SUBJECT,
            detail_code="forced_update_reason_not_reserved",
            outcome=EntryOutcome.DENIED,
        )
    except MalformedReleaseDecision as exc:
        return _denied(
            journal,
            MALFORMED_RELEASE_DECISION.detailed(str(exc)),
            subject_id=UNIDENTIFIED_SUBJECT,
            detail_code="malformed_release_decision",
            outcome=EntryOutcome.DENIED,
        )

    reason = decision.forced_update_reason
    if not decision.forced_update_required or reason is None:
        # Authorized, but authorized for something else. An optional-update
        # decision is not a kill switch, and is not promoted into one.
        return _denied(
            journal,
            KILL_SWITCH_NOT_AUTHORIZED_BY_DECISION.detailed(
                "The authorized release decision does not require a forced update, "
                "so it cannot activate the kill switch."
            ),
            subject_id=decision.decision_id,
            detail_code="decision_does_not_require_forced_update",
            outcome=EntryOutcome.DENIED,
        )

    try:
        journal.append(
            kind=EntryKind.KILL_SWITCH_ACTIVATION_ATTEMPT,
            outcome=EntryOutcome.AUTHORIZED,
            subject_id=decision.decision_id,
            detail_code=reason.value,
        )
    except JournalAtCapacity:
        return INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL)

    return KillSwitchActivationRecord(
        decision_id=decision.decision_id,
        minimum_supported_version=decision.minimum_supported_version,
        forced_update_reason=reason,
        requested_by=attempt.requested_by,
    )


def _denied(
    journal: IntakeJournal,
    problem: ProblemDetails,
    *,
    subject_id: str,
    detail_code: str,
    outcome: EntryOutcome,
) -> ProblemDetails:
    """Record the denial, then return it. A refused activation is audited."""
    try:
        journal.append(
            kind=EntryKind.KILL_SWITCH_ACTIVATION_ATTEMPT,
            outcome=outcome,
            subject_id=subject_id,
            detail_code=detail_code,
        )
    except JournalAtCapacity:
        return INTAKE_CAPACITY_EXHAUSTED.detailed(_CAPACITY_DETAIL)
    return problem
