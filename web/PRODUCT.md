# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Veyro is operated by the staff of a gym or fitness club, not by its members. Five
audiences, in the order this surface serves them:

- **The gym owner or operator.** Opens Veyro in the morning to learn whether the
  business is healthy and what needs a decision today. Reads money, retention and
  occupancy. Does not want a module tour.
- **The club manager.** Runs one site or one brand. Answers staffing gaps, class
  schedules, member problems and the day's exceptions. Their scope is a club, and the
  product is expected to bound what they see to it.
- **The receptionist / front-desk employee.** Stands at a counter with a person in front
  of them, often mid-sentence. Checks members in, resolves a refused door, starts a
  walk-in trial, opens and closes a till. Speed and a legible next action matter more
  than completeness; they are looking at the person, not the screen.
- **The trainer or coach.** Reads their own rota, their class rosters and who turned up.
- **The platform operator (Veyro's own staff).** Runs the tenant registry, plans and
  billing across customers. A separate surface with the strongest sign-in in the product.

Members themselves are a separate surface and do not use the operator app.

## Product Purpose

Multi-tenant management software for gyms and fitness clubs: memberships and the
contracts behind them, class and personal-training scheduling, door access, payments and
the ledger, people records, leads and trials, staff and permissions, devices, and the
operational tasks and exceptions that come out of all of it.

Success is that the person who opens it in the morning knows, without hunting, what the
business did and what needs them today — and that the person at the front desk can finish
what a member is asking for before the member has finished asking.

## Positioning

Veyro is built around the distinction most gym software collapses: **what a member is
entitled to, what they owe, and whether a door opens for them are three separate facts.**
A frozen membership is not an unpaid one; an unpaid invoice does not by itself revoke
access; whether somebody may train right now is a question only their entitlement grants
answer. Every screen that touches a member has to keep those three apart, and the product
is honest about which one it is showing.

The second claim a competitor could not truthfully copy: Veyro states what it does not
know. Where a figure cannot be derived, the product says so rather than printing a
plausible number.

## Operating Context

- **Region: Jordan.** Currency is JOD, stored in fils (three minor digits) and displayed
  with two. The week starts on Sunday. The working week is Sunday–Thursday; Friday is the
  short day. Tax filing goes through a national adapter.
- **Bilingual, and both directions.** English and Arabic are first-class. Arabic is RTL
  and is not a translation layer bolted on — the numeral system (Latin vs Arabic-Indic
  digits) is a tenant setting that every rendered quantity follows, while money figures
  and identifiers a person reads back stay Latin.
- **Light and dark.** Front-desk screens run under bright gym lighting; back-office work
  happens early and late.
- **Hardware is in the room.** Turnstiles, readers and gateways are part of the scene. A
  reader that is down is a receptionist apologising for something they could not see.
- **The physical scene.** A reception counter, a studio floor, a rota on a wall, a till
  drawer handed from one shift to the next, a phone held by somebody mid-conversation.
- **Multi-site.** A tenant has an organization, brands, and locations; a club manager is
  scoped to locations, and timezone and opening hours belong to the location.

## Capabilities and Constraints

**Built and working on the server** (each with an HTTP surface the web app reads):
tenancy and the org hierarchy; configuration and feature flags; identity, passwords,
passkeys, device sessions and assurance levels; authorization with roles, scoped
assignments, approvals and a hash-chained audit log; privacy, consent and data-subject
requests; a domain-event outbox; observability, objectives and rate limiting;
integrations; notifications (authored, never sent); people, profiles and Member 360;
plans, subscriptions and metering; the product catalog, pricing and promotions;
memberships, contracts, entitlements and invoicing; the financial ledger, wallet and cash
sessions; scheduling, resources and capacity; booking, waitlist and attendance; device
fleet; access control and door decisions; tasks, cases and SLAs; CRM leads and trials.

**Constraints that shape the interface:**

- **Every read is permission-gated, and refusals are ordinary.** A screen must render a
  refusal as a state, not an error — and must distinguish "you may not see this", "a
  stronger sign-in would show it", and "we could not ask".
- **Fields come back masked.** A person's legal name, birth date, contact details and
  health notes arrive redacted depending on the caller's permissions and assurance level.
  A masked value must read as withheld, never as absent — and the remedy shown beside it
  has to be one that reader actually has.
- **Some writes need a stronger sign-in.** Financial-class actions require a stepped-up
  session. A form may offer the step-up; a button that simply fails is worse than none.
- **Money is integer minor units.** No floating point anywhere near a figure.
- **Several figures genuinely cannot be derived yet** — occupancy against capacity, a
  revenue interpretation, a working-week default. The product names these rather than
  guessing.
- **Nothing sends and nothing charges.** Messaging and payment providers are not
  connected, so a screen must not imply a message went out or a card was charged.
- **Not deployed.** This runs locally and in development only.

**Terminology that belongs to users, not to the codebase:** member, membership, contract,
freeze, class, booking, waitlist, check-in, no-show, drawer, shift, lead, trial, club.
Internal module identifiers, table names, UUIDs and gap notes addressed to engineers are
not product language and must not reach an operator's screen.

## Brand Commitments

- The product name is **Veyro**. No other brand marks, logos or trade dress exist.
- Bilingual parity is a commitment, not a feature: anything a reader is shown in English
  must exist in Arabic.
- Accessibility is a commitment: every surface is expected to hold up to a keyboard, a
  screen reader, reduced motion, and a 375px phone.
