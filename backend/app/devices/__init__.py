"""MOD-021, ECO-03: hardware abstraction, the edge runtime's contract and the device fleet.

**This module operates no hardware, and that is the honest shape rather than a gap in it.**
TSD paragraph 3061 puts the authority in a "control-plane device registry + edge-local SQLite
WAL", and the edge half is a Kotlin/JVM service on a gateway that this repository does not
contain (paragraph 134). So what is built here is the half that must be correct whatever the
gateway turns out to be: the registry, the capability vocabulary, the certificate lifecycle,
the command contract, the signed snapshot's bounds, and the commissioning gate. A row saying a
turnstile opened, written by nothing that drives a turnstile, is the fabricated-evidence shape
this codebase has been bitten by six times.

**The life-safety rules are refusals, not features.** Paragraph 4173: "Egress is never
conditioned on Veyro membership, cloud reachability or software authorization." A module that
can issue a command to a door has to be unable to issue the one that holds it shut, and
paragraph 4175 says a failed safety test *blocks opening the access point in production*. Both
are implemented as things the software cannot do rather than as settings somebody could change,
and `safety.py` is where they live.
"""

__all__ = [
    "capabilities",
    "certificates",
    "commands",
    "enrollment",
    "fleet",
    "safety",
    "snapshots",
]
