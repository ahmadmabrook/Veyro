"""MOD-005 PLT-02: configuration resolution, flag evaluation and experiment assignment.

Everything in this module is a pure function over values the caller has already read. No I/O, no
clock, no randomness. That is not tidiness for its own sake: PLT-02's required outcome is that
"every evaluation remains tenant-safe and every change is reversible" (TSD paragraph 1021), and an
evaluation that cannot be reproduced from its inputs cannot be audited after an incident. Given the
same stored rows and the same context, every function here returns the same answer forever.

The service layer in `app.configuration.service` supplies the rows; it never re-implements a
decision made here.

**Assignment is hashed, not random.** `bucket` is SHA-256 over the parts joined by a NUL byte,
first eight bytes big-endian, modulo 10000. Three properties follow, and all three are tested in
`backend/tests/test_configuration_evaluation.py`:

* *Stable* -- a subject keeps its bucket across processes, restarts and database rebuilds, so a
  percentage rollout never reshuffles who is in it.
* *Independent* -- the rule id (for flags) and the experiment salt (for experiments) are part of
  the hashed input, so two rules at 50% do not select the same half, and two experiments do not
  correlate their arms.
* *Tenant-scoped* -- `tenant_id` leads the input, so the subset chosen in one tenant says nothing
  about the subset chosen in another.

`random` would satisfy none of them and `hash()` is salted per process, so neither is usable here.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

BUCKETS = 10_000
"""Basis points. A rollout is `rollout_bp` out of this, so 2500 is 25.00%."""

_KEY = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)+$", re.ASCII)

VALUE_TYPES = ("boolean", "integer", "number", "string", "json")


class ValidationError(ValueError):
    """A configuration value does not satisfy its definition. Carries a stable machine code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- hashing

def bucket(*parts: str) -> int:
    """Map the parts to a stable bucket in [0, BUCKETS).

    Parts are joined by a NUL byte, which cannot occur in any of them, so ("ab", "c") and
    ("a", "bc") hash differently. Without a separator a rollout could be moved between rules by
    choosing adjacent ids that concatenate to the same string.
    """
    digest = hashlib.sha256(b"\x00".join(p.encode("utf-8") for p in parts)).digest()
    return int.from_bytes(digest[:8], "big") % BUCKETS


# --------------------------------------------------------------------------- definitions

def validate_key(key: str) -> str:
    """Config, flag and experiment keys share one shape, mirrored by a CHECK in the migration."""
    if not _KEY.fullmatch(key):
        raise ValidationError("bad_key", f"{key!r} is not a dotted lower-case key")
    return key


def validate_value(value_type: str, validation: dict[str, Any], value: Any) -> None:
    """Check a value against its definition's type and optional constraints (PLT-02-R01).

    Constraints are deliberately few -- `enum`, `minimum`, `maximum`, `max_length` -- and unknown
    keys are rejected rather than ignored. A validation rule that is silently not applied is worse
    than no rule, because it reads as protection in the registry while enforcing nothing.
    """
    if value_type not in VALUE_TYPES:
        raise ValidationError("bad_value_type", f"{value_type!r} is not a known value type")

    unknown = set(validation) - {"enum", "minimum", "maximum", "max_length"}
    if unknown:
        raise ValidationError("unknown_constraint", f"unsupported constraints: {sorted(unknown)}")

    if value_type == "boolean" and not isinstance(value, bool):
        raise ValidationError("type_mismatch", "expected a boolean")
    # bool is a subclass of int in Python; an integer definition must not accept True.
    if value_type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValidationError("type_mismatch", "expected an integer")
    if value_type == "number" and (isinstance(value, bool) or not isinstance(value, int | float)):
        raise ValidationError("type_mismatch", "expected a number")
    if value_type == "string" and not isinstance(value, str):
        raise ValidationError("type_mismatch", "expected a string")

    allowed = validation.get("enum")
    if allowed is not None and value not in allowed:
        raise ValidationError("not_in_enum", f"value is not one of {allowed}")

    low, high = validation.get("minimum"), validation.get("maximum")
    if (low is not None or high is not None) and value_type not in ("integer", "number"):
        raise ValidationError("constraint_not_applicable", "minimum/maximum need a numeric type")
    if low is not None and value < low:
        raise ValidationError("below_minimum", f"value is below {low}")
    if high is not None and value > high:
        raise ValidationError("above_maximum", f"value is above {high}")

    limit = validation.get("max_length")
    if limit is not None:
        if value_type != "string":
            raise ValidationError("constraint_not_applicable", "max_length needs a string type")
        if len(value) > limit:
            raise ValidationError("too_long", f"value is longer than {limit}")


# --------------------------------------------------------------------------- value resolution

@dataclass(frozen=True)
class ValueRow:
    """One published version of a configuration value at one scope."""

    scope_type: str
    brand_id: str | None
    location_id: str | None
    value: Any
    version: int


@dataclass(frozen=True)
class Resolved:
    value: Any
    scope_type: str
    version: int | None
    """None when the definition's default was used, since a default has no published version."""


_SPECIFICITY = {"location": 3, "brand": 2, "tenant": 1}


def resolve_value(
    default: Any,
    rows: list[ValueRow],
    *,
    brand_id: str | None = None,
    location_id: str | None = None,
) -> Resolved:
    """Resolve one definition for one scope (PLT-02-R01 inheritance).

    The most specific scope that applies wins -- location, then brand, then tenant, then the
    definition's default -- and within a scope the highest version wins, because `cfg_values` is
    append-only and keeps every version.

    A location row applies only to the asked-for location, and a brand row only to the asked-for
    brand. Resolving for a location therefore does *not* pick up that location's brand row unless
    the caller passes `brand_id` too; the caller knows the hierarchy, this function does not.

    ponytail: rows for one definition are filtered in Python rather than by a `DISTINCT ON` query,
    which is fine while a definition has tens of versions. If history grows into the thousands,
    push the per-scope latest into SQL -- the signature does not change.
    """
    best: ValueRow | None = None
    for row in rows:
        if row.scope_type == "brand" and row.brand_id != brand_id:
            continue
        if row.scope_type == "location" and row.location_id != location_id:
            continue
        if row.scope_type not in _SPECIFICITY:
            continue
        if best is None or (_SPECIFICITY[row.scope_type], row.version) > (
            _SPECIFICITY[best.scope_type],
            best.version,
        ):
            best = row
    if best is None:
        return Resolved(value=default, scope_type="default", version=None)
    return Resolved(value=best.value, scope_type=best.scope_type, version=best.version)


# --------------------------------------------------------------------------- flags

@dataclass(frozen=True)
class Rule:
    rule_id: str
    priority: int
    match: dict[str, str] = field(default_factory=dict)
    rollout_bp: int = BUCKETS
    variant: str = "on"


@dataclass(frozen=True)
class Flag:
    flag_key: str
    enabled: bool
    default_variant: str
    kill_switch_engaged: bool
    version: int


@dataclass(frozen=True)
class Decision:
    variant: str
    reason: str
    """Why this variant was chosen: `kill_switch`, `disabled`, `rule:<id>` or `default`."""
    rule_id: str | None = None
    bucket: int | None = None


def matches(match: dict[str, str], context: dict[str, str]) -> bool:
    """A rule matches when every attribute it names equals the context's value for it.

    An empty `match` therefore matches everything, which is how a plain percentage rollout with no
    targeting is written. A rule naming an attribute the context does not carry does not match --
    an absent attribute is not a wildcard, because treating it as one would turn a rule meant for
    one brand into a rule for every caller that forgot to send `brand`.
    """
    return all(context.get(name) == want for name, want in match.items())


def evaluate_flag(
    flag: Flag,
    rules: list[Rule],
    *,
    context: dict[str, str],
    subject_id: str,
    tenant_id: str,
) -> Decision:
    """Evaluate one flag for one subject (PLT-02-R02, PLT-02-R03).

    Order, and why:

    1. **Kill switch first** (PLT-02-R03). An engaged switch returns `off` whatever the flag or
       its rules say. The switch exists to stop payments, AI actions or hardware immediately; a
       targeting rule that could still return `on` would defeat its only purpose.
    2. A disabled flag returns its default variant.
    3. Rules in ascending `priority`, ties broken by `rule_id` so the order is total and stable.
       A rule whose `match` fits is admitted; if it carries a partial rollout the subject's bucket
       decides. **A subject that matches a rule but falls outside its rollout continues to the
       next rule** rather than stopping at the default -- that is what lets "25% of brand A on the
       new path, brand A otherwise on the fallback" be written as two rules.
    4. Otherwise the flag's default variant.
    """
    if flag.kill_switch_engaged:
        return Decision(variant="off", reason="kill_switch")
    if not flag.enabled:
        return Decision(variant=flag.default_variant, reason="disabled")

    for rule in sorted(rules, key=lambda r: (r.priority, r.rule_id)):
        if not matches(rule.match, context):
            continue
        if rule.rollout_bp >= BUCKETS:
            return Decision(variant=rule.variant, reason=f"rule:{rule.rule_id}",
                            rule_id=rule.rule_id)
        drawn = bucket(tenant_id, flag.flag_key, rule.rule_id, subject_id)
        if drawn < rule.rollout_bp:
            return Decision(variant=rule.variant, reason=f"rule:{rule.rule_id}",
                            rule_id=rule.rule_id, bucket=drawn)
    return Decision(variant=flag.default_variant, reason="default")


# --------------------------------------------------------------------------- experiments

@dataclass(frozen=True)
class Variant:
    variant_key: str
    weight: int


@dataclass(frozen=True)
class Experiment:
    experiment_key: str
    status: str
    salt: str


def assign_variant(
    experiment: Experiment,
    variants: list[Variant],
    *,
    subject_id: str,
    tenant_id: str,
) -> str | None:
    """Assign a subject to a variant, or None when the experiment is not running (PLT-02-R04).

    Variants are walked in `variant_key` order with their weights accumulated, so the split is
    determined by the weights alone and not by insertion order or by what the database happened to
    return. Changing a weight moves the boundary and therefore reassigns some subjects; that is
    inherent to weight changes, which is why `cfg_exposures` records the variant a subject was
    actually shown rather than recomputing it later.
    """
    if experiment.status != "running" or not variants:
        return None
    total = sum(v.weight for v in variants)
    if total <= 0:
        return None
    drawn = bucket(tenant_id, experiment.experiment_key, experiment.salt, subject_id)
    # Scale the bucket onto the weight total; BUCKETS is 10000 so weights up to 10000 are exact.
    position = drawn * total // BUCKETS
    seen = 0
    for variant in sorted(variants, key=lambda v: v.variant_key):
        seen += variant.weight
        if position < seen:
            return variant.variant_key
    return sorted(variants, key=lambda v: v.variant_key)[-1].variant_key
