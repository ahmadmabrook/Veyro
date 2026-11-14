"""MOD-020 OPS-02: booking, waitlist, no-show policy and appeals.

**This module owns no capacity.** Paragraph 4141 divides the two: "Schedule owns published
occurrences/resources/capacity. Booking owns member reservation/waitlist/cancel/attendance
intent." So a booking *cites* a MOD-019 capacity hold taken in the same transaction, and the
two invariants paragraph 4697 names come from that rather than from anything here -- capacity
never falls below zero because MOD-019's trigger counts it under a row lock, and a duplicate
waitlist promotion cannot consume two seats because MOD-019's one-live-hold-per-person index
refuses the second. A second counter in this module would be a second authority that can
disagree with the first, which is MOD-018's argument about balances applied to seats.
"""

__all__ = ["appeals", "attendance", "consequence", "denial", "policy", "waitlist"]
