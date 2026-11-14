"""MOD-012 ECO-02: what an adapter contract may say, and what it may never say.

An integration definition describes a provider this build can be connected to: the capabilities
it offers, the scopes it needs, the configuration it takes, the regions it serves, and -- for a
critical one -- what happens when it is unavailable and how a tenant leaves it. A published
version is immutable, as a plan version is in MOD-015, because an install snapshots the version
it was made against and an old install has to stay reconstructible.

**Definitions are rows, not code, and that is the opposite call from the last four modules.**
Permissions (MOD-008), event types (MOD-010) and metrics (MOD-011) are code because they are
facts about what *this software* can do, and two tenants disagreeing about them would be
unresolvable. An integration definition is not that: ECO-02's own model has partners publishing
their own integrations into a marketplace, so the set is open by design and the authority is
whoever published the version. It lives in `plt01_platform` with no runtime-role grant, exactly
where `saas_plans` lives and for the same reason.

**No definition may declare a configuration field that holds a secret.** There is no vault in
this repository -- MOD-007 says so about TOTP seeds and MOD-009 says so about crypto-shred -- so
a definition inviting a tenant to paste an API key into a config value would be inviting this
build to store one in a table that is read by every list route. Credentials go through
`int_credential_refs`, which holds a *reference* to a secret kept somewhere this build cannot
read, and never a value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KEY = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)*$", re.ASCII)
SCOPE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*(\.[a-z0-9]+(_[a-z0-9]+)*)+$", re.ASCII)
#: The same shape `int_connections_region_shape` enforces, so a definition cannot declare a
#: region no connection could ever be made in.
REGION = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$", re.ASCII)

#: The provider domains paragraph 3026 names. A closed set, because a capability nothing in the
#: product consumes is a capability no install can be useful for -- and because an install's
#: permission check is written against these names.
CAPABILITIES = (
    "payments", "messaging", "accounting", "access_control", "wearables", "identity",
    "storage", "analytics", "hr",
)

#: How much a tenant is expected to lose when the provider is down. `critical` carries the
#: obligations in paragraph 3033: a fallback, a reconciliation procedure and an exit plan.
CRITICALITIES = ("convenience", "important", "critical")

#: What a configuration field may hold. There is no `secret`, and its absence is the control --
#: see the module docstring. `reference` is for an opaque external identifier (an account id, a
#: workspace handle), which is not a credential and is safe in a row somebody can list.
FIELD_TYPES = ("string", "integer", "boolean", "reference", "enum")


class ContractError(ValueError):
    """A definition, version or install this build will not accept."""


@dataclass(frozen=True)
class ConfigField:
    name: str
    field_type: str
    required: bool = False
    values: tuple[str, ...] = ()
    """The closed set, for `enum`. Empty for every other type."""
    description: str = ""


@dataclass(frozen=True)
class DefinitionVersion:
    definition_key: str
    version: int
    capabilities: tuple[str, ...]
    scopes: tuple[str, ...]
    """Every scope this version can ask for, least first. An install grants a subset."""
    required_scopes: tuple[str, ...]
    """The subset without which the integration cannot do its job at all."""
    config_fields: tuple[ConfigField, ...] = field(default_factory=tuple)
    regions: tuple[str, ...] = ()
    """Empty means every region. A non-empty set refuses a connection from anywhere else."""


def check_field(field_: ConfigField) -> None:
    if not KEY.fullmatch(field_.name):
        raise ContractError(f"{field_.name!r} is not a configuration field name")
    if field_.field_type not in FIELD_TYPES:
        raise ContractError(
            f"{field_.field_type!r} is not a configuration field type; a credential is not a "
            f"configuration value and belongs in a credential reference"
        )
    if field_.field_type == "enum" and not field_.values:
        raise ContractError(f"{field_.name!r} is an enum and declares no values")
    if field_.field_type != "enum" and field_.values:
        raise ContractError(f"{field_.name!r} declares values but is not an enum")


def check_version(version: DefinitionVersion) -> None:
    """Everything a single version has to satisfy to be published."""
    if not KEY.fullmatch(version.definition_key):
        raise ContractError("definition_key_is_not_a_key")
    if version.version < 1:
        raise ContractError("version_is_not_positive")
    if not version.capabilities:
        raise ContractError("a_definition_declares_at_least_one_capability")
    for capability in version.capabilities:
        if capability not in CAPABILITIES:
            raise ContractError(f"{capability!r} is not a capability this build knows")
    if len(set(version.capabilities)) != len(version.capabilities):
        raise ContractError("a_capability_is_declared_twice")
    for scope in version.scopes:
        if not SCOPE.fullmatch(scope):
            raise ContractError(f"{scope!r} is not a scope name")
    if len(set(version.scopes)) != len(version.scopes):
        raise ContractError("a_scope_is_declared_twice")
    missing = set(version.required_scopes) - set(version.scopes)
    if missing:
        raise ContractError(
            f"required scopes {sorted(missing)} are not among the declared scopes; a scope an "
            f"install cannot be granted cannot be required of it"
        )
    # Regions were checked by nothing, so a duplicate or a blank one reached the entries
    # insert as a 500 and an upper-case one registered fine and then made the definition
    # permanently unconnectable -- `int_connections_region_shape` refuses it at authorization,
    # by which time the version is published and immutable. Found by review.
    for region in version.regions:
        if not REGION.fullmatch(region):
            raise ContractError(f"{region!r} is not a region name")
    if len(set(version.regions)) != len(version.regions):
        raise ContractError("a_region_is_declared_twice")
    names = [f.name for f in version.config_fields]
    if len(set(names)) != len(names):
        raise ContractError("a_configuration_field_is_declared_twice")
    for field_ in version.config_fields:
        check_field(field_)


def check_succession(earlier: DefinitionVersion, later: DefinitionVersion) -> None:
    """What a later version of one definition may change.

    Paragraph 3032 makes backward compatibility a contractual commitment, so the three refusals
    here are the ones that would break an install that already exists:

    * **A capability may not be dropped.** A tenant installed this definition *for* a
      capability; removing it in a later version turns their install into one that no longer
      does what they chose it for, and nothing would say so.
    * **A required configuration field may not be added.** Every existing install has no value
      for it, so adding one makes them all invalid at once -- discovered at the next sync rather
      than at publication.
    * **A required scope may not be added.** An existing connection was authorized against the
      old set, so the new requirement is one its grant cannot satisfy; the install would read as
      active and be silently under-privileged, which is the failure that surfaces as a provider
      refusing one call in twenty.

    Adding an optional field, an optional scope or a capability is all fine: an install ignores
    what it does not know about.
    """
    if later.definition_key != earlier.definition_key:
        raise ContractError("succession_compares_one_definition")
    dropped = set(earlier.capabilities) - set(later.capabilities)
    if dropped:
        raise ContractError(
            f"v{later.version} drops capabilities {sorted(dropped)} that v{earlier.version} "
            f"declared; an install made for one of those would silently stop doing it"
        )
    was_required = {f.name for f in earlier.config_fields if f.required}
    now_required = {f.name for f in later.config_fields if f.required}
    added = now_required - was_required
    if added:
        raise ContractError(
            f"v{later.version} newly requires configuration {sorted(added)}; every install on "
            f"v{earlier.version} has no value for it"
        )
    added_scopes = set(later.required_scopes) - set(earlier.required_scopes)
    if added_scopes:
        raise ContractError(
            f"v{later.version} newly requires scopes {sorted(added_scopes)}; a connection "
            f"authorized on v{earlier.version} cannot satisfy it and would read as active"
        )


def check_grant(version: DefinitionVersion, granted: list[str]) -> None:
    """Paragraph 3032: third parties receive only the data and permissions they need.

    Two directions, as every other validation in this codebase does. A scope the definition
    never declared cannot be granted -- it is either a typo or an escalation, and neither
    should reach a provider. And the scopes the definition marks required have to be there, or
    the install is one that will fail in the middle of its first sync instead of at authorization.
    """
    undeclared = set(granted) - set(version.scopes)
    if undeclared:
        raise ContractError(
            f"scopes {sorted(undeclared)} are not declared by this definition version"
        )
    if len(set(granted)) != len(granted):
        raise ContractError("a_scope_is_granted_twice")
    missing = set(version.required_scopes) - set(granted)
    if missing:
        raise ContractError(f"required scopes {sorted(missing)} were not granted")


def check_config(version: DefinitionVersion, config: dict[str, object]) -> None:
    """The supplied configuration against the version's declared fields, in both directions."""
    declared = {f.name: f for f in version.config_fields}
    undeclared = set(config) - set(declared)
    if undeclared:
        raise ContractError(f"this definition declares no configuration {sorted(undeclared)}")
    for name, field_ in declared.items():
        if name not in config:
            if field_.required:
                raise ContractError(f"configuration {name!r} is required")
            continue
        value = config[name]
        if field_.field_type == "integer" and not isinstance(value, int) or (
                field_.field_type == "integer" and isinstance(value, bool)):
            raise ContractError(f"configuration {name!r} is an integer")
        if field_.field_type == "boolean" and not isinstance(value, bool):
            raise ContractError(f"configuration {name!r} is a boolean")
        if field_.field_type in ("string", "reference", "enum") and not isinstance(value, str):
            raise ContractError(f"configuration {name!r} is text")
        if field_.field_type == "enum" and value not in field_.values:
            raise ContractError(
                f"configuration {name!r} does not take {value!r}; declared values are "
                f"{sorted(field_.values)}"
            )


def check_region(version: DefinitionVersion, region: str) -> None:
    """A connection from a region the provider does not serve.

    Refused rather than allowed-and-logged, because the residency decision belongs to the
    definition's publisher and a connection made outside it is data leaving a region somebody
    promised it would stay in -- which is MOD-009's territory, not something an operator should
    be able to wave through at install time.
    """
    if version.regions and region not in version.regions:
        raise ContractError(
            f"this definition serves {sorted(version.regions)} and not {region!r}"
        )
