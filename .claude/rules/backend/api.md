---
scope: path
paths:
  - "backend/**/*.py"
---
<!-- Target path once applied: .claude/rules/backend/api.md -->

# Rule: Backend API Request/Response and Permission Boundaries (`backend/**/*.py` binding)

Authored 2026-09-19 (MOD-001, `ADR-005` Decision 2 binding pre-implementation
condition — see `architecture.md` for the shared authority citation, not
restated here). Grounded directly in EIP §4.3's Backend/API profile row
(`EIP_MIRROR.md` lines 1270-1277: "FastAPI/Pydantic boundaries; ... typed
errors; observability; migration safety"), TSD §24.1's permission lint
(`TSD_MIRROR.md` lines 11614-11615: "Permission lint: API commands/queries
declare action/resource/scope; unregistered permission names fail
build"), and `REQUIREMENTS.md`'s input/output data-exposure lint
obligation (round 8 P0-1, citing the EIP card's mandatory Security
baseline, `EIP_MIRROR.md` lines 4267-4271) and `IAM-002` ("authorization
enforced in the domain application layer even when the UI hides an
action", `EIP_MIRROR.md` lines 20953-20960) — read directly this session
from the owner-produced mirrors. Per this project's own convention
(`REQUIREMENTS.md` §0), the governing `.docx` wins over this
mirror-sourced text on any conflict.

This rule is active now for MOD-001's own scaffold API surface
(`app/main.py`, any harness-exposed endpoint) and binds forward to
every later domain module's real command/query endpoints under
`backend/**`.

## Required controls for `backend/**/*.py`

1. **Every request and response body is a named Pydantic model.** No
   route handler accepts or returns a bare `dict`, `Any`, or unchecked
   `**kwargs` payload as its request/response type. Every such model is
   registered in the OpenAPI contract MOD-001's screen/permission
   tooling reads from `contracts/openapi/`.

2. **Response schemas declare every field explicitly.** A response
   model may not wildcard-serialize an ORM row or other internal object
   directly onto the wire; every field the client can see is named in
   the model. An undeclared response field is exactly what the
   input/output data-exposure lint denies (a schema-level allowlist
   check, distinct from the permission lint below — it checks field
   shape, not action authorization).

3. **Request schemas reject extra/undeclared fields.** Every request
   model is configured to reject unknown fields (e.g. Pydantic's
   `model_config = ConfigDict(extra="forbid")` or the equivalent) rather
   than silently ignoring them — this closes the hidden-field-injection
   path the data-exposure lint's request-schema half checks for.

4. **Every command/query declares its `action`/`resource`/`scope`
   permission triple.** A route handler's endpoint registration states
   which action it performs, on which resource, and at what scope,
   before it can be merged. An endpoint with an undeclared or
   unregistered permission name fails the permission lint (TSD §24.1)
   with `UNREGISTERED_PERMISSION`, citing the endpoint.

5. **The permission declaration is the enforcement, not documentation.**
   The action/resource/scope check runs in the domain application layer
   the route handler calls into — never only inferred from whether a
   UI surface exposes or hides the action. This is `IAM-002`'s own
   text: "authorization enforced in the domain application layer even
   when the UI hides an action."

6. **No business logic in the route handler.** A handler parses and
   validates its request via its Pydantic model, resolves tenant
   context, calls exactly one domain application-service method, and
   maps the result to its response model. Conditional business rules,
   multi-step orchestration, or direct database access belong in the
   domain layer — see `architecture.md`.

7. **Errors crossing the API boundary are typed.** A route handler
   raises or returns a declared error type/enum (mapped to a stable
   HTTP status and machine-readable error code), never a bare exception
   string serialized to the client. This is EIP §4.3's own "typed
   errors" requirement for the Backend profile.

8. **Every command/query endpoint that performs an externally-retryable
   mutation declares and enforces the 6-element idempotency contract
   `REQUIREMENTS.md` §3 already names** ("Idempotency-contract lint,"
   `knowledge/03-Modules/MOD-001/REQUIREMENTS.md` line 584, sourced from
   `EIP_MIRROR.md` lines 4148-4157) — this is the authoring-time rule for
   what `tools/validate_idempotency_contract.py`'s CI gate mechanically
   checks (`IMPLEMENTATION.md` §3): the tool enforces this control, and
   this control is what an author must satisfy to pass it, the same
   relationship this file's controls 2/3 already state for the
   data-exposure lint and controls 4/5 state for the permission lint. It
   is also EIP §4.3's own "idempotent externally retryable mutations"
   requirement for the Backend/API profile, quoted in full (not elided)
   in `architecture.md`'s transaction-boundary control: "backend/**/*.py
   — ...; explicit transaction boundaries; **idempotent externally
   retryable mutations**; RLS/tenant context; ..." (`EIP_MIRROR.md` lines
   1270-1277). A command/query endpoint is externally retryable when a
   client may legitimately retry the same logical request (e.g. after a
   network timeout) without the caller having any reliable way to know
   whether the original request was actually applied. Every such
   endpoint's declaration must carry all six elements `REQUIREMENTS.md`
   §3 names, or it fails `tools/validate_idempotency_contract.py`'s
   named-missing-element report (`IMPLEMENTATION.md` §3: "key-tuple
   scoping, retention window, stored-hash field, 409-code reference,
   command_id propagation, or provider-derivative field"):

   a. a scoped `Idempotency-Key` tuple — the key plus whatever additional
      scoping (tenant, resource, action) makes it unique to this logical
      request, not a bare client-supplied string alone;
   b. a retention window of at least 24 hours, longer for payment/fiscal
      mutations, during which a replayed key is recognized;
   c. the original request's hash and result stored against the key, so
      a replay can be compared and answered without re-executing the
      mutation;
   d. a stable `409 IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD`
      response when the same key arrives with a request body different
      from the one stored against it;
   e. propagation of the request's `command_id` to the outbox row and
      any provider dispatch the mutation triggers, so the same logical
      command is traceable end-to-end (this is also what
      `architecture.md`'s outbox-atomicity control depends on to
      identify which outbox row belongs to which retried command); and
   f. a deterministic provider-idempotency derivative — a value derived
      deterministically from the command/key, never randomly generated
      per attempt — passed to any external provider call the mutation
      makes, so a provider-side retry is itself idempotent.

## Fail-closed rule

A route handler with an unregistered permission triple, an undeclared
response field, a request schema that accepts extra fields, or business
logic inlined in the handler body, does not merge. The permission lint
and the input/output data-exposure lint (TSD §24.1; `REQUIREMENTS.md`
round 8 P0-1) are both CI-blocking, proven by a deliberate-violation
fixture per `IMPLEMENTATION.md` §4/§6.
