"""MOD-022, OPS-03: check-in, access control and entitlement decisions.

**A credential identifies; policy and entitlement authorize.** TSD paragraph 4155 states it
and paragraph 876 repeats it, and it is the whole shape of this module: `credentials.py`
resolves a presented token to a subject and says nothing about whether the door opens, and
`policy.py` decides, from facts about the subject that the credential never carried.

The three planes this joins already exist and none of them knew about the others. MOD-021 has
the door and the command that opens it; MOD-017 has the entitlement that says whether somebody
may train; MOD-014 has the person. This module is the pipeline between them, and the evidence
it leaves behind.
"""

__all__ = [
    "credentials",
    "occupancy",
    "offline",
    "passback",
    "policy",
    "zones",
]
