# ADR-0012 — MOD-014: a member lookup is not a search, and the index already there cannot do it

- ID: ADR-0012
- Status: ACCEPTED
- Decision-Key: mod014-member-lookup-not-search
- Covers: backend/app/people/, backend/migrations/tenant/, web/src/app/desk/

**Dated 2026-11-25. Scope: FD-02, and the one capability two notes in this repository
disagree about.** Authority is
`knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md`, which delegates
ordinary product and architecture decisions. The sources are `veyro-product-experience-design/`
— FD-02's canvas and its registry line — and `backend/app/people/` as it stands.

## The two notes that disagree

MOD-014's own gap list says:

> **No search.** Paragraph 4218's permission-aware search index with a mandatory query
> pre-filter is ENG-01's, and a `LIKE` scan presented as search would be a read path with no
> freshness contract and no pre-filter.

`design:coverage`'s reason for FD-02 says the opposite about the same screen:

> `GET /people/contact-match` is the exact-match half and is deliberately exact … A gated,
> masked read by name over `ppl_contact_points_by_value` is this module's own work rather than
> MOD-059's index.

Both cannot be acted on. And the second is wrong in a detail that matters:
`ppl_contact_points_by_value` indexes normalized *contact values* — a phone number, an email —
and holds no name at all, so "a read by name over" it names an index that cannot answer the
question. FD-02's canvas types `hala`.

## The decision

**A lookup and a search are different reads, and FD-02 is the first.** Four properties
separate them, and the lookup has all four:

- **One entity.** FD-02 finds a person. Paragraph 4218's search is across entities, which is
  what a command bar is for and what ADM-SRCH-01 draws.
- **One tenant, enforced below the query.** The "mandatory query pre-filter" paragraph 4218
  asks for exists to stop a search index returning another tenant's rows, because an index is
  a second copy of the data with its own access rules. A lookup has no second copy: it reads
  `ppl_persons` under forced RLS, so the pre-filter *is* the predicate the database applies,
  and it is not something this module has to remember to add.
- **No freshness contract, because there is nothing to be stale.** The objection to "a `LIKE`
  scan presented as search" is that a search surface promises its index is current and a scan
  silently answers from the table instead. A read that *is* the table makes no such promise and
  cannot break one.
- **Bounded, gated and masked.** The result set is a page a receptionist reads while somebody
  stands in front of them, every row goes through MOD-014's own gate, and a name this session
  may not read comes back as the marker rather than as a name.

So MOD-014's "no search" note stands unchanged — ADM-SRCH-01 and its pg_trgm index remain
MOD-059's — and FD-02's lookup is this module's work. `design:coverage`'s reason is corrected to
say *by name over `ppl_persons`*, which is where a name is.

## What that costs, measured rather than reasoned about

`0009` already carries `CREATE INDEX ppl_persons_by_name ON plt01.ppl_persons (tenant_id,
lower(legal_name))`, and **it cannot serve a prefix query**, because this database is
`en_US.utf8` rather than C. Measured against 60,002 rows:

```
-- (tenant_id, lower(legal_name))
Seq Scan on people
  Filter: ((tenant_id = …) AND (lower(legal_name) ~~ 'hala%'))

-- (tenant_id, lower(legal_name) text_pattern_ops)
Index Scan using probe_by_name_prefix on people
  Index Cond: ((tenant_id = …) AND (lower(legal_name) ~>=~ 'hala') AND (lower(legal_name) ~<~ 'halb'))
```

The existing index serves the *equality* `find_duplicates` uses — `lower(legal_name) = …` — and
nothing else, which is correct for what it was written for and is the reason this is not a
one-line screen. A second index with `text_pattern_ops` on the same expression is what a prefix
lookup needs: one line, no extension, and no pre-emption of MOD-059, because it answers "a name
beginning with" and nothing more.

**It is a second index on one expression and that is a cost worth stating.** Two b-trees over
the same column double the write amplification on a person's name, which changes on a merge and
on an ordinary correction. The alternative — replacing the existing index with the
`text_pattern_ops` one — does not work: `text_pattern_ops` compares byte by byte, so an
equality lookup through it is correct only for the exact bytes, and `find_duplicates` folds the
name before comparing. Both indexes earn their place.

## What this does not decide

- **A partial *phone* is still exact.** `GET /people/contact-match` normalizes and matches the
  whole value, and its own reason holds: "a mistyped digit finding somebody else is worse than
  finding nobody". FD-02's "or partial" is answered for a name and refused for a number, which
  the screen says rather than implies — a suffix match on a phone number would need its own
  index and its own argument about which half of a number identifies somebody.
- **No photo.** FD-02's canvas confirms identity visually and the registry line says so twice.
  An object store is the third external blocker, so the screen names the absence rather than
  rendering a placeholder that reads as "no photo on file".
- **"Let in" is MOD-022's override**, which exists and is attributed. Whether FD-02 draws it is
  that screen's own question and is settled when it is built, not here.
- **No ranking.** Two matches are listed side by side, which the canvas requires in as many
  words — "ambiguous matches list side by side rather than guessing" — so the order is the
  name's and there is no score. A relevance score over two rows is a confident answer about
  which person is standing there.
