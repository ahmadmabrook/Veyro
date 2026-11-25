# ADR-0018 — MOD-019: a room has a capacity, and a format can take a bike per attendee

- ID: ADR-0018
- Status: ACCEPTED
- Decision-Key: mod019-resource-capacity
- Covers: backend/migrations/tenant/, backend/app/scheduling/, backend/app/main.py, web/src/

**Dated 2026-11-26. Scope: ADM-SCH-06, and the ceiling ADM-SCH-03 draws and names as absent.**
Authority is `knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which
delegates ordinary product and architecture decisions. The source is the drawn canvas in
`veyro-product-experience-design/project/Veyro V1 Batch I Scheduling and Access.dc.html`, read
in the batch file rather than in `veyro-screen.js` — ADR-0015's finding, where the prototype and
the deliverable disagreed about which fields exist.

## The canvas

ADM-SCH-06 is a small read-only card: a label, a three-column table templated as
`{{ r.name }} · {{ r.cap }} · {{ r.equip }}`, and one sentence.

> Capacity here is the ceiling every class inherits. Double-booking is impossible because
> ADM-SCH-03 reads this list — the constraint lives in one place, not in each scheduler's
> memory.

**No header, no action, no add control.** So the screen is a read, and the two facts it draws
have to be settable where a resource is already written: `POST /scheduling/resources` exists and
`GET /scheduling/resources` exists, which is what makes this a column slice rather than a form.

ADM-SCH-03, which is built, draws the other half and this repository already records it as
absent: *"Studio 2 holds 20 bikes. Capacity cannot exceed the room"* needs **one fact nothing
records — that a class format takes one unit of equipment per attendee.**

## What was actually missing, checked rather than assumed

The backlog entry said `sch_resources` has `quantity` — "how many of a thing there are" — that
capacity lives on a template's own policy per class, and that there is no equipment column at
all, so the screen as drawn would have one real column and two invented ones. All three are
true, and the migration says so in its own comment: *"For `equipment`: how many there are.
Twenty bikes is one row with a quantity of twenty, never twenty rows, because the question a
booking asks is 'are there enough'."*

So there are **three different numbers** and the build had one of them:

| fact | where it lives | before |
| --- | --- | --- |
| how many of a thing there are | `sch_resources.quantity` | built |
| how many people a space holds | ADM-SCH-06's `cap` | **absent** |
| how many places a class offers | `sch_capacity_policies.capacity` | built |

and one relation: **which space a piece of equipment is in**, which ADM-SCH-06's `equip` column
draws and which nothing recorded — `sch_resources.location_id` is a *club*, not a room.

## Decisions

**D1. A space's capacity is a column on the resource, nullable, and only a space has one.** One
fact about one row, so it is a column rather than a table; nullable because a coach, a service
and a composite have no capacity and a zero would read as "holds nobody". The kinds that may
carry one are `room`, `zone` and `court` — the three of OPS-01-R01's seven that are places — and
a CHECK says so, because a capacity on a `staff` row is a number no reader could interpret.

**D2. It is a ceiling and not a default.** A template's policy keeps its own `capacity`, which
is what a session snapshots; what the room adds is a refusal when the policy exceeds it. The
alternative — inheriting the room's capacity when a template states none — would make the
class's own figure optional and leave two columns that can disagree about how many places a
session has, which is this build's most-repeated finding. The canvas's word is *ceiling*.

**D3. Equipment sits inside a space, by a self-reference, and only equipment does.**
`parent_resource_id` on `sch_resources`, nullable, with a composite foreign key to the same
tenant. Three rules, and the third needs a trigger because a CHECK cannot see another row: only
an `equipment` row may have a parent, only a space may be one, and the two must be at the same
location — twenty bikes in Khalda are not twenty bikes in Sweifieh, and a ceiling computed
across clubs is the defect this exists to prevent.

**D4. "A bike per attendee" is a flag on the requirement, not a second quantity.**
`sch_template_requirements.per_attendee`, default false. The requirement already carries a
`quantity`; what the flag says is whether that quantity is *per session* (one studio, one coach)
or *per attendee* (one bike each). A second integer column would be two numbers that can
disagree about the same requirement, and the existing `quantity` is already the right figure for
the per-session case. **Refused for a named resource**, because a requirement naming *that*
resource is for one of it — the sibling constraint `sch_template_requirements_named_is_one`
already says a named requirement has `quantity = 1`, and per-attendee is meaningless against it.

**D5. The ceiling is one pure function and both callers read it.** `capacity.ceiling` takes the
spaces a template requires and its per-attendee requirements and answers the lowest of them,
with *which one* bound it. Two callers: the capacity-policy write refuses a policy above it, and
ADM-SCH-03's conflict check reports it so the screen can say "capacity cannot exceed the room"
before anybody saves. One definition, because a figure a screen shows and a write then refuses
is this build's one-module-two-definitions finding on the number a manager types.

**D6. The refusal names the resource, not the number.** "Capacity 30 exceeds Studio 2, which
holds 20" is actionable; "capacity too high" sends somebody to guess. The error carries the
binding resource's code and its figure, which is MOD-016's `in_window_is_not_the_resolved_price`
reasoning applied to a refusal.

## What this does not do

**It does not enforce the ceiling on a session that is already published.** A room's capacity
can be lowered after a class was generated against the old one, and the session keeps the policy
it snapshotted — which is MOD-019's own premise (*"raising a class's capacity next month does not
retrospectively change what last month's class held"*) and means a lowered room leaves published
sessions above its ceiling. The remedy is the republish path, whose impact assessment already
names what it would move; what is *not* built is a report of the sessions a lowering would put
over, and that is named rather than silently absent.

**It does not count bikes against holds.** The per-attendee figure bounds a class's *declared*
capacity; whether twenty people actually turned up with twenty bikes is attendance, and
`sch_capacity_holds` counts places rather than equipment. A hold per bike would be a second
capacity mechanism beside the one paragraph 4146 asks for.

**It does not model a space inside a space.** A zone inside a room is expressible by the same
self-reference and is refused: only equipment may have a parent, because a nested space makes
"which capacity binds" a walk rather than a comparison, and nothing in the design draws one.
