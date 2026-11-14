"""MOD-014 PPL-01-R04: deciding that two person records are probably one person.

Paragraph 1317 asks for "duplicate detection and merge workflow using identity, contact and
contextual signals". This module is the detection half and it decides nothing about merging --
`merge.py` does that, and a human does the deciding.

**The score is explainable or it is useless.** An operator being asked to merge two member
records is being asked to destroy one of them, and "0.82" is not a reason to do that. Every
signal is named, the weights are stated here in one table, and `score` is the sum of the named
signals rather than a model nobody can interrogate. A reviewer, an operator and a support agent
all read the same list.

**Nothing here is fuzzy.** There is no edit distance, no phonetic match and no trigram
similarity, because every one of those produces a confident wrong answer on the input that
matters: two siblings at one address with one family email, or a father and son sharing a name.
What is left is exact matching on normalized values, which under-detects and does not
over-merge. The under-detection is a stated gap, not a surprise -- and it fails toward leaving
two records alone, which is recoverable, rather than toward merging two people, which is the
thing paragraph 10200 wants reviewable because it is hard to undo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: What each signal is worth, out of 100. The numbers are a judgement and the ordering is the
#: part that matters: a verified shared email is near-conclusive, a shared surname is nearly
#: nothing. They are here rather than in a table because two tenants disagreeing about whether a
#: shared phone number means anything would make a merge queue mean different things in each.
WEIGHTS: dict[str, int] = {
    # The same verified email or phone is the strongest signal available without an identity
    # document. Verified, because an unverified address is whatever somebody typed.
    "verified_email_match": 60,
    "verified_phone_match": 55,
    # Unverified, which is the common case in a gym's records.
    "email_match": 40,
    "phone_match": 35,
    # Same date of birth *and* the same legal name is the classic duplicate from a paper import.
    "name_and_birth_date_match": 45,
    # On their own these are weak, and the family cases are why.
    "birth_date_match": 15,
    "legal_name_match": 10,
    # Both records sit under one household relationship already, so somebody has linked them.
    # That makes a duplicate *less* likely, not more: a household is how two real people who
    # share an address are correctly represented.
    "same_household": -25,
}

#: At or above this, the pair is queued for review. Below it, nothing is written: a queue full of
#: single weak signals is a queue nobody reads, and an unread queue is worse than none because it
#: looks like the control is running.
REVIEW_THRESHOLD = 40

#: There is no auto-merge threshold, and that is the decision. Paragraph 10200 requires merges to
#: be reviewable; a score high enough to merge without a human would make the review optional
#: exactly where the consequences are largest. The constant exists so a reader looking for it
#: finds the reason instead.
AUTO_MERGE_THRESHOLD: int | None = None


class DedupError(ValueError):
    """A deduplication input this module will not accept."""


@dataclass(frozen=True)
class Candidate:
    """Two people and why this module thinks they are one."""

    person_id: str
    other_person_id: str
    score: int
    signals: tuple[str, ...]

    @property
    def ordered(self) -> tuple[str, str]:
        """The pair, lower id first.

        The storage orders the pair so the same two people cannot be queued twice in opposite
        directions -- which would let two operators each merge one into the other.
        """
        return (min(self.person_id, self.other_person_id),
                max(self.person_id, self.other_person_id))


@dataclass(frozen=True)
class PersonSignals:
    """Everything this module compares, already normalized by the caller.

    Normalized by the caller because the normalizer is MOD-007's and there is exactly one of
    them in the build: a second spelling rule here would make a duplicate invisible to whichever
    module disagreed, which is the failure mode this comparison exists to find.
    """

    person_id: str
    legal_name_folded: str
    date_of_birth: date | None = None
    #: Normalized values, so the comparison is on what MOD-007 would match.
    emails: frozenset[str] = frozenset()
    phones: frozenset[str] = frozenset()
    verified_emails: frozenset[str] = frozenset()
    verified_phones: frozenset[str] = frozenset()
    household_ids: frozenset[str] = frozenset()


def fold_name(value: str) -> str:
    """The form names are compared in: trimmed, lowercased, inner whitespace collapsed.

    Not a fuzzy form. "Ahmad  Mabrouk" and "ahmad mabrouk" are the same entry typed twice;
    "Ahmed" and "Ahmad" are two names and this module will not guess that they are one.
    """
    return " ".join(value.split()).lower()


def compare(a: PersonSignals, b: PersonSignals) -> Candidate:
    """Score one pair, naming every signal that fired.

    A pair with no signals scores zero and is still returned: the caller decides whether to
    store it, and a function that returned `None` for "no match" would make "we compared these
    and found nothing" indistinguishable from "we never compared these".
    """
    if a.person_id == b.person_id:
        raise DedupError("a_person_is_not_their_own_duplicate")

    signals: list[str] = []
    if a.verified_emails & b.verified_emails:
        signals.append("verified_email_match")
    elif a.emails & b.emails:
        signals.append("email_match")
    if a.verified_phones & b.verified_phones:
        signals.append("verified_phone_match")
    elif a.phones & b.phones:
        signals.append("phone_match")

    names_match = bool(a.legal_name_folded) and a.legal_name_folded == b.legal_name_folded
    births_match = (a.date_of_birth is not None and a.date_of_birth == b.date_of_birth)
    if names_match and births_match:
        # The combined signal replaces its two halves rather than adding to them: scoring all
        # three would count the same evidence twice and push a weak pair over the threshold.
        signals.append("name_and_birth_date_match")
    else:
        if births_match:
            signals.append("birth_date_match")
        if names_match:
            signals.append("legal_name_match")

    if a.household_ids & b.household_ids:
        signals.append("same_household")

    raw = sum(WEIGHTS[name] for name in signals)
    # Clamped to the range the column accepts, which is also the range an operator can read as a
    # percentage. The negative household signal is what makes the lower clamp necessary.
    score = max(0, min(100, raw))
    return Candidate(person_id=a.person_id, other_person_id=b.person_id, score=score,
                     signals=tuple(signals))


def worth_reviewing(candidate: Candidate) -> bool:
    """Whether this pair goes in front of a human."""
    return candidate.score >= REVIEW_THRESHOLD


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """Highest score first, then by the pair, so a list is stable between runs.

    Stable because an operator working down a queue needs the order not to change under them
    when somebody else adds a candidate -- and because a test comparing two runs of the detector
    should be comparing the detection, not the sort.
    """
    return sorted(candidates, key=lambda c: (-c.score, c.ordered))
