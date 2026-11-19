"""A credential identifies a subject. It never authorizes anything.

TSD paragraph 4155: "QR, NFC, wallet pass, physical card and biometric token are credentials.
They identify a subject/credential record; they do not encode unrestricted authorization."
Paragraph 876 says it again as a one-line rule, and paragraph 10129 a third time. **Three
statements of the same sentence in one document is a requirement that has been got wrong
before**, so this module is built so that getting it wrong is not expressible: `resolve`
returns a subject and a credential's status and has no return value that means "allowed".

**No secret is stored here either.** A binding carries a SHA-256 of the credential's own
identifier, which is MOD-013's shape for an address: a presented token is matched by hashing
it, and nothing in this build can turn a row back into a card number. Paragraph 4161 requires
exactly that of the edge snapshot -- "only pseudonymous credential hashes" -- and a table that
could hold the raw value would be the copy the snapshot is forbidden to carry.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.access.zones import AccessError

#: What a member may present. Paragraph 4136's list, plus the staff-assisted path that is the
#: fallback when every device is down and somebody is standing at the desk.
CREDENTIAL_KINDS: tuple[str, ...] = (
    "qr_rotating", "nfc_card", "wallet_pass", "physical_card", "pin", "staff_assisted",
    "biometric",
)

#: The kinds whose token changes every time. Paragraph 4182: the member app derives a rotating
#: signed token from a device-bound enrolment secret, so what a reader presents is not what the
#: binding holds -- the binding holds the credential's identity and the token carries a counter.
ROTATING_KINDS: frozenset[str] = frozenset({"qr_rotating"})

#: Paragraph 4183's default: a rotating token lives thirty seconds, with a reader clock
#: tolerance of thirty seconds either way.
ROTATING_LIFETIME = timedelta(seconds=30)
READER_CLOCK_TOLERANCE = timedelta(seconds=30)

#: Paragraph 4162: above sixty seconds of device clock skew, rotating credentials are not
#: accepted at all and the device goes to supervised mode. A rotating token's whole protection
#: is that it expires, and a device that cannot tell the time cannot tell that it has.
MAX_DEVICE_CLOCK_SKEW = timedelta(seconds=60)

#: How long a presented token stays in the replay cache. The lifetime plus both tolerances,
#: because a token is replayable for exactly as long as a reader would still accept it.
REPLAY_WINDOW = ROTATING_LIFETIME + READER_CLOCK_TOLERANCE * 2

#: Where a binding is in its life. There is no `suspended`: a credential is usable or it is
#: not, and a membership that is suspended is a *policy* fact about the subject rather than a
#: fact about the card in their wallet -- which is this module's whole separation.
#:
#: **And there is no `expired` either, although there was.** Expiry is derived from
#: `expires_at` by `is_usable`, and nothing in the build ever wrote the state -- a declared
#: value with no writer, which is MOD-020's defect and the one this module deleted
#: `snapshot_stale` and `wrong_zone` for. A state that says what a column already says is a
#: second copy of the truth that can disagree with it, which is MOD-018's argument against a
#: stored balance applied to a card.
CREDENTIAL_STATES: tuple[str, ...] = ("active", "revoked")

_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class CredentialError(AccessError):
    """A credential this software will not resolve."""


@dataclass(frozen=True)
class Binding:
    """What the database knows about one credential, with no subject attributes at all.

    **`person_id` and nothing else about the person.** The decision needs the subject's
    entitlements, their membership state and their age, and every one of those is read from
    the module that owns it rather than carried here -- because a credential that carried
    them would be a credential that authorizes.
    """

    credential_id: str
    person_id: str
    kind: str
    state: str
    issued_at: datetime
    expires_at: datetime | None
    revocation_epoch: int


@dataclass(frozen=True)
class Presented:
    """What a reader says it was shown.

    `rotation_counter` and `nonce` are only meaningful for a rotating kind; paragraph 4182
    names them among the token's fields. `signature_verified` is the reader's own claim, which
    this build records and cannot check -- see `check_presentation`.
    """

    digest: str
    kind: str
    presented_at: datetime
    rotation_counter: int | None = None
    nonce: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    signature_verified: bool = False


def digest_of(value: str) -> str:
    """The stored form of a credential identifier.

    Hashed rather than stored, for MOD-013's reason: a bounce is remembered and a recipient
    matched without a second copy of everybody's contact details beside the one MOD-007 owns.
    Here the second copy would be a card number.
    """
    folded = value.strip()
    if not folded:
        raise CredentialError("a credential identifier is not blank")
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()


def check_digest(value: str) -> str:
    if not _DIGEST.match(value):
        raise CredentialError(
            "a credential digest is 64 lowercase hex characters; this module stores no "
            "credential in the clear")
    return value


def check_kind(kind: str) -> None:
    if kind not in CREDENTIAL_KINDS:
        raise CredentialError(
            f"{kind!r} is not a credential kind; this software knows "
            f"{', '.join(CREDENTIAL_KINDS)}")


def is_usable(binding: Binding, *, at: datetime) -> bool:
    """Whether this binding still identifies anybody.

    **Not whether it opens anything.** A usable credential belonging to a suspended member
    identifies that member perfectly well, and the refusal happens in `policy.decide`.
    """
    if binding.state != "active":
        return False
    return not (binding.expires_at is not None and at >= binding.expires_at)


def check_clock(device_skew: timedelta, *, kind: str) -> None:
    """Paragraph 4162's refusal, and it applies to the rotating kinds only.

    A card's number does not expire in thirty seconds, so a reader with a bad clock can still
    match one; a rotating token's entire anti-replay protection is a window, and a device that
    is a minute out cannot tell an expired token from a live one. The device going to
    supervised mode is MOD-021's `set_device_state`, which this module does not call: a
    refusal here is a decision about one presentation, not about the unit.
    """
    if kind not in ROTATING_KINDS:
        return
    if abs(device_skew) > MAX_DEVICE_CLOCK_SKEW:
        raise CredentialError(
            f"this reader's clock is {abs(device_skew).total_seconds():.0f} seconds out and "
            f"a rotating credential is only as good as the window it expires in; present a "
            f"card or ask the desk")


def check_presentation(presented: Presented, *, at: datetime) -> None:
    """Refuse a token outside its window, before any policy is evaluated.

    Paragraph 4183: "Edge readers validate signature, scope, revocation epoch and recent-token
    replay cache **before** policy evaluation." The order matters for the reason MOD-021's
    safety refusal comes first -- the message somebody reads has to name the reason that
    matters -- and for a second reason here: evaluating policy for a replayed token would read
    a member's entitlements on the strength of a token somebody photographed.

    **The signature is the reader's claim and this build cannot check it.** There is no key
    vault, so `signature_verified` is recorded as an assertion by a named device rather than
    verified -- MOD-021's `validated` install state and MOD-012's before it. What is *not*
    waved through is the window: a rotating token outside it is refused here whatever the
    reader says about the signature.
    """
    if presented.kind not in ROTATING_KINDS:
        return
    if presented.expires_at is None or presented.issued_at is None:
        raise CredentialError(
            "a rotating credential carries the window it was minted for; this one carries "
            "none, so nothing bounds how long it is good for")
    if presented.rotation_counter is None or not (presented.nonce or "").strip():
        raise CredentialError(
            "a rotating credential carries a rotation counter and a nonce; without them a "
            "replayed token is indistinguishable from a fresh one")
    if presented.expires_at - presented.issued_at > ROTATING_LIFETIME:
        raise CredentialError(
            f"a rotating credential is good for "
            f"{int(ROTATING_LIFETIME.total_seconds())} seconds; this one was minted for "
            f"longer, which is a screenshot somebody can still use")
    if at < presented.issued_at - READER_CLOCK_TOLERANCE:
        raise CredentialError("this credential is not valid yet")
    if at >= presented.expires_at + READER_CLOCK_TOLERANCE:
        raise CredentialError("this credential has expired; the app will show a fresh one")


def replay_key(presented: Presented) -> str:
    """What the replay cache remembers: the token, not the credential.

    Keyed on the nonce *and* the counter, so a device that reuses a nonce across counters is
    caught and a counter that goes backwards cannot find a free slot. The credential digest is
    in the key too, because two members' tokens are two different things to remember.
    """
    return digest_of(
        f"{presented.digest}:{presented.rotation_counter}:{(presented.nonce or '').strip()}")


def replay_expiry(presented: Presented, *, at: datetime) -> datetime:
    """When this token stops being worth remembering.

    **The reader's clock does not shorten it.** The expiry is measured from `at`, which is the
    server's instant, so a device claiming an old `expires_at` cannot evict its own replay
    evidence early.
    """
    return at + REPLAY_WINDOW
