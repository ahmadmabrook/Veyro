# R1-F01 / R2-N01 — D6.7 remaining position-signal failures: root-cause qualification (2026-10-06)

**Operation:** `8f0a10b2-a4bc-4cd6-927f-fe4eb49cac12`, kind `root_cause`, subgoal
`R04-GATE2-R2-N01-D67-REMAINING-SIGNAL-ROOT-CAUSE`. Sole-runner MOD-001 GOV-01-R04 gate-2
slice.

**What this record is.** A root-cause qualification only, as the strategy reconciliation in
`GATE2-R2-N01-D67-STAGNATION-PREFLIGHT-RECONCILIATION-2026-10-06.md` §Strategy requires
("stop serial implementation increments… the next bounded legal operation is root-cause
qualification… It must not replay D8, alter source now, open review, or infer PASS").

**What this record is not.** No implementation, no test edit, no ADR edit, no review, no
scenario promotion, no D8 replay, no live CTE state-3 wiring, no verdict, no owner approval
sought or implied. No source or test file was modified: `tools/validate_architecture_gates.py`
is still SHA-256 `50e86cca714db89484149bd64f3cb7079cef4b243fb9a4b6c4196597ea65fe9b` and
`tools/tests/test_validate_architecture_gates.py` still
`13f61a4c997e3c872f84c371bfa1d6bd8d17a51ddc40cedca4e23e516c5dc965` — byte-identical to the
preflight record's preserved snapshot, re-hashed by this session. `git status --porcelain
tools/` shows both still untracked WIP with no modification; HEAD `e481b81` unchanged. All
pre-existing uncommitted WIP preserved. Every probe below ran from throwaway files under
`/tmp/veyro-rc-probe/` and throwaway fixture trees under `tempfile.TemporaryDirectory()`,
never against the repository tree.

**Governing state retained verbatim, not advanced by this record:** R1-F01 formal ledger
**OPEN**; round-2 **BLOCKED P0=1/P1=1/P2=2/P3=2**; U1/U2 **B HOLD** in force with its
exhaustive §4 prohibition list and four-item re-opening bar
(`GATE2-R1-D6-U1-U2-QUALIFIED-REDECISION-2026-10-05.md`); the D8 table-reference figure
remains a disclosed **lower bound** per ADR-011 D6.7.5; SCN-MOD001-006/-007/-095/-096 remain
**NOT EXECUTED** and unpromoted — **no scenario PASS**; MOD-001 uncertified; WIP=1 holds and
MOD-002 stays locked. Live CTE state-3 wiring remains forbidden and was not touched.

---

## 1. Headline classification

The two remaining failures named in the preflight record are **both real and both confirmed
by independent reproduction**, but they are **not the same severity class**, and the
difference decides the legal fix order.

| | Failure | Polarity | Classification |
|---|---|---|---|
| **(1)** | `_revoke_grantee_exclusion_offset` suppresses an unrelated later ordinary `FROM` in an unsplit segment | **under**-extraction | **Demonstrated gate-level false PASS.** Exit 0, on both `.py` and `.sql` surfaces, with a cross-domain reference lost and the D8 note simultaneously asserting its count "complete for this run". P0-class, same shape as the original R2-N01 P0 |
| **(2)** | `GRANT UPDATE`/`REFERENCES ON` privilege words misread as table-position targets around `ON` | **over**-extraction | **White-box extractor defect, no false PASS.** Every probed form fails closed at exit 2. Defeats D3.2 state precision and inflates/duplicates the D8 count, but cannot admit a clean pass. P2-class |

The preflight record's own wording for (1) — "that specific live fixture is not a demonstrated
false PASS" — was accurate **for the fixture it probed** (which carries a lexically certain
`;`). It understates the finding: a sibling fixture with **no depth-0 semicolon** is one
unsplit subject, and that fixture does reach **PASS exit 0**. This record supplies it.

The materially new result is §5: **(2) is currently an accidental backstop that masks a subset
of (1)'s false-PASS surface**, so closing (2) first — the next increment the GRANT/REVOKE
record's own residual §1 proposed — would *widen* the demonstrated false-PASS surface while
all 524 tests stayed green.

---

## 2. Failure (1) — exact reproducer, mechanism, source line

### 2.1 Mechanism

`tools/validate_architecture_gates.py:3642-3646`:

```python
    on = _grant_revoke_object_on_match(text, kw)
    if on is None:
        return None
    grantee = _GRANTEE_FROM_RE.search(text, on.end())
    return None if grantee is None else grantee.start()
```

`_GRANTEE_FROM_RE.search(text, on.end())` is an **unbounded forward search with no clause,
statement or terminator bound**. Its result is added to the exclusion set at
`:3685-3688` and consumed at `:3689-3692`, where a matching `FROM` is `continue`d out of the
`_TABLE_KEYWORD_RE` stream. When the `REVOKE` has no grantee `FROM` of its own, the search
runs on and claims the **next `FROM` anywhere in the subject**, deleting an unrelated
statement's table position.

### 2.2 The asymmetry with the pattern it claims to copy

The docstring at `:3673-3680` asserts the exclusion is "**Same shape as COPY's — positively
computed per keyword match, offset equality, only `FROM` ever checked**", and the test comment
at `tools/tests/test_validate_architecture_gates.py:3979-3981` repeats it ("the same shape as
COPY's direction exclusion"). The last two clauses are true. **The first is false.** COPY's
`_copy_direction_exclusion_offset` (`:3442-3449`) walks the target positively, then
**anchor-matches** at that exact offset:

```python
    pos = _COPY_WS_RE.match(text, target[1]).end()
    ...
    direction = _COPY_DIRECTION_FROM_RE.match(text, pos)
    return None if direction is None else direction.start()
```

`.match` at a computed offset cannot reach past the token it is anchored to. `.search` can
reach the end of the text. Measured contrast (pure-function probe, `/tmp/veyro-rc-probe/pure.py`):

| probe | result |
|---|---|
| `_copy_direction_exclusion_offset('COPY mem_roster TO STDOUT\nSELECT a FROM bil_invoices')` | `None` — the later `FROM` is never reached |
| `_copy_direction_exclusion_offset('COPY mem_roster FROM STDIN\nSELECT a FROM bil_invoices')` | `16` — its own direction `FROM` only; the later `FROM`@36 retained |
| `_revoke_grantee_exclusion_offset('REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices')` | **`37`** — the *unrelated* statement's `FROM`, `text[37:41] == 'FROM'` |
| `_revoke_grantee_exclusion_offset('REVOKE SELECT ON mem_roster FROM r\nSELECT a FROM bil_invoices')` | `28` — correct, its own grantee `FROM` |

Both durable claims of structural identity are therefore false **in the reassuring
direction**, which is a DC-12 obligation in its own right (§7 item e).

### 2.3 Why the subject is unsplit

`_d8_statement_subjects` (`:5143`, body `:5194-5237`) cuts only on a **depth-0 `;`**, and
`:5227-5229` returns `[text]` when there is none ("No lexically certain boundary anywhere: the
one subject it already was"). Two statements separated by a newline alone are therefore **one
subject**, confirmed by probe:

```
_d8_statement_subjects('REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices')
  -> ['REVOKE SELECT ON mem_roster\nSELECT a FROM bil_invoices']        # one subject
_d8_statement_subjects('REVOKE SELECT ON mem_roster; SELECT a FROM bil_invoices')
  -> ['REVOKE SELECT ON mem_roster', ' SELECT a FROM bil_invoices']     # two subjects
```

So the segmenter — not the extractor — is the only thing that stood between this defect and a
false clean, and it stops working the moment a semicolon is absent. Reachable shapes with a
`REVOKE … ON` and no grantee `FROM` of its own include an interpolated grantee clause
(`f"REVOKE SELECT ON mem_roster {grantee}"`), a truncated or templated DDL blob, and the
plain `TO`-for-`FROM` authoring error — a lint must not reward any of them with exit 0.

### 2.4 Position stream: the loss

```
### REVOKE-no-FROM + later ordinary FROM (one unsplit subject)
    signal='ON'@14 elem@17 ident='mem_roster' unresolved=None
    # the ordinary FROM -> bil_invoices is ABSENT

### control: identical text without the REVOKE line
    signal='FROM'@9 elem@14 ident='bil_invoices' unresolved=None
```

---

## 3. Failure (1) — gate-level outcomes (the false PASS)

Fixture: the existing synthetic tree and manifest from
`GATE2-R1-F14-RAW-TABLE-CLI-CAPTURE-2026-10-06.json` (membership `MEM-01`/`mem_`, billing
`BIL-02`/`bil_`), subject written to `app/modules/membership/repo.sql` (`.sql` surface) or
`app/modules/membership/dao.py` (`.py` string-literal surface). Invocation
`validate_architecture_gates.py --gate module-deps --modules-dir … --module-manifest …` under
`backend/.venv/bin/python`. Fixture-scoped only: `contracts/modules/ownership.json` is absent,
so **no real-tree ownership assurance is claimed**.

### 3.1 Negative rows (must fail closed; currently do not)

| # | Surface | Subject | Observed | Expected under D6.7 |
|---|---|---|---|---|
| **1A** | `.sql` | `REVOKE SELECT ON mem_roster`⏎`SELECT a FROM bil_invoices` | **PASS exit 0** | nonzero |
| **1H** | `.sql` | `REVOKE SELECT ON mem_roster`⏎`SELECT a FROM mem_x, bil_invoices` | **PASS exit 0** | nonzero |
| **1F** | `.py` | `SQL = """`⏎`REVOKE SELECT ON mem_roster`⏎`SELECT a FROM bil_invoices`⏎`"""` | **PASS exit 0** | nonzero |

1A's own D8 disclosure, emitted alongside the exit 0:

> `note: ADR-011 D8 table-reference attribution: 1 table-position identifier reference(s)
> extracted and attributed -- own (D3.2 state 1) 1, another module's (state 2, FAIL
> CROSS_DOMAIN_SQL_IMPORT) 0 …`
> `note: ADR-011 D6.3/D8 zero-table triggered statements: of 1 recognised subject(s), 0
> carried no table position at all …, 0 yielded no usable table identifier and are ERROR --
> 0 refused by the dangling-keyword rule and 0 by the D6.3 I-1 backstop`
> `note: 0 unattributed table identifier reference(s)`

A silently deleted cross-domain reference, reported as one cleanly attributed own-domain
reference, with every refusal counter at zero. **1H is the stronger row**: the deleted signal
was a *list* introducer, so the whole `FROM` list — including its cross-domain second
element — vanished from the stream, not merely one element.

### 3.2 Discriminating controls (each isolates one variable; all behave correctly)

| # | Subject | Observed | What it isolates |
|---|---|---|---|
| **1B** | `SELECT a FROM bil_invoices` | **FAIL exit 1** `CROSS_DOMAIN_SQL_IMPORT: … table 'bil_invoices' owned by 'billing'` | the `REVOKE` line is the whole suppressor — not the fixture, manifest or surface |
| **1C** | `REVOKE SELECT ON mem_roster;`⏎`SELECT a FROM bil_invoices` | **FAIL exit 1** | a depth-0 `;` rescues it ⇒ the defect is gated by segmentation, not by extraction |
| **1D** | `REVOKE SELECT ON mem_roster FROM r`⏎`SELECT a FROM bil_invoices` | **FAIL exit 1** | a REVOKE with its own grantee `FROM` is correct ⇒ the bound, not the exclusion, is the defect |
| **1G** | `.py`, two separate literals (`A = "REVOKE …"`, `B = "SELECT a FROM bil_invoices"`) | **FAIL exit 1** | the loss is scoped to one subject; literal boundaries hold |

### 3.3 Positive / non-vacuity controls (must stay clean; a fix must not break them)

| # | Subject | Observed |
|---|---|---|
| **1E** | `REVOKE SELECT ON mem_roster FROM r` (own-domain, alone) | **PASS exit 0** — the exclusion's intended job, preserved |
| **2H** | `SELECT a FROM mem_roster, mem_events` (ADR §Follow-up's named control) | **PASS exit 0** |
| **2I** | `SELECT a FROM mem_x JOIN mem_y USING (id)` (ADR §Follow-up's named control) | **PASS exit 0** |

### 3.4 Governing invariant violated

ADR-011 **D6.7.2**, stated as an invariant:

> For any statement text T, the gate's outcome must be **no weaker** — on the ordering
> `clean < FAIL/ERROR` — than the outcome it would produce for T if the extractor had
> returned nothing. **Partial extraction may never be safer than total extraction failure.**

1A/1F/1H violate it directly. Had the extractor returned nothing, the D6.3 I-1 backstop would
have refused the subject at exit 2. Returning exactly one clean own-domain position is
strictly weaker than returning none — the identical polarity inversion the D6.7 addendum was
written to eliminate ("**In the original design, extracting one identifier is strictly less
safe than extracting none**"), now re-instantiated by the D6.7 remediation's own new code.
Also violated: **D6.7.1** (narrowing the extractor is never a free optimisation; where the
lexer must guess it guesses toward extracting — an unbounded search guesses toward
suppressing), **D6.7.5** (the completeness claim above is affirmatively false for this run),
and **D6.7.6** (a silently-unextracted position must be `MODULE_DEPS_SOURCE_UNINSPECTABLE`,
never invisible).

### 3.5 The structural root cause, stated once

D6.7.2's accounting compares **recognised signals** against **attributed identifiers**. Both
failures live in the same blind spot: **signal production and signal suppression both happen
upstream of that accounting seam.** `_table_keyword_position_matches`'s `continue` deletes the
signal *before* it is ever recognised, so the accounting is structurally incapable of noticing
— there is no record to compare. An exclusion is therefore categorically unlike a
non-extraction: non-extraction yields an unresolved `_TablePositionResult` and ERRORs;
exclusion yields nothing and is invisible. Every future signal family that needs a context
filter will add another filter in that same blind spot, which is exactly how the GRANT/REVOKE
increment introduced a brand-new false PASS while its own analysis correctly concluded it
"adds real target attribution … but does not remove the ERROR".

---

## 4. Failure (2) — exact reproducer, mechanism, and why it is not a false PASS

### 4.1 Mechanism

`UPDATE` is a `_TABLE_KEYWORD_RE` member reaching the stream through
`_table_keyword_position_matches` (`_TABLE_POSITION_SIGNAL_SOURCES` index 0, `:3719`);
`REFERENCES` reaches it through `_REFERENCES_KEYWORD_RE.finditer` (index 1, `:3720`). Neither
source is privilege-context-sensitive — only `_truncate_table_position_matches` is. Both are
also `_LIST_POSITION_SIGNALS` members (`:3780-3783`), so each spurious signal additionally
runs its own comma walk. Pure-function probe:

```
'GRANT UPDATE ON mem_roster TO r'
    signal='UPDATE'@6  elem@13 ident='ON'          # spurious: the reserved word
    signal='ON'@13      elem@16 ident='mem_roster'  # the real target
'GRANT REFERENCES ON mem_roster TO r'
    signal='REFERENCES'@6 elem@17 ident='ON'
    signal='ON'@17        elem@20 ident='mem_roster'
'GRANT SELECT, INSERT, UPDATE ON mem_a, bil_invoices TO r'
    signal='UPDATE'@22 elem@29 ident='ON'
    signal='UPDATE'@22 elem@39 ident='bil_invoices'   # <-- re-count of the object list
    signal='ON'@29     elem@32 ident='mem_a'
    signal='ON'@29     elem@39 ident='bil_invoices'   # same element_start 39, twice
```

Two corrections to the residual as previously recorded. First, the spurious position is a
**resolved** identifier (`identifier='ON'`, `unresolved=None`), not an unresolved one — it
reaches D3.2 **state 6** by attribution failure (`no module owns 'on'`), not by the
dangling-keyword rule. Second, the double-count's cause is specifically
`_LIST_POSITION_SIGNALS` membership of the privilege word: both signals walk the same comma
list and emit two positions at the identical `element_start`.

### 4.2 Gate-level rows

| # | Subject | Observed | Note |
|---|---|---|---|
| **2A** | `GRANT UPDATE ON mem_roster TO r` | **ERROR exit 2** `MODULE_DEPS_TABLE_UNATTRIBUTED: … table 'ON': no module owns 'on'` | a wholly own-domain, legitimate grant is refused, naming a table nobody wrote |
| **2B** | `GRANT REFERENCES ON mem_roster TO r` | **ERROR exit 2**, same code | |
| **2C** | `GRANT UPDATE ON bil_invoices TO r` | **ERROR exit 2**; the correct `CROSS_DOMAIN_SQL_IMPORT` *is* emitted, but status is ERROR because the ERROR class dominates (D7.2) | the true violation is reported, mislabelled at status level |
| **2D** | `GRANT SELECT, INSERT, UPDATE ON mem_a, bil_invoices TO r` | **ERROR exit 2**; `CROSS_DOMAIN_SQL_IMPORT` for `bil_invoices` printed **twice**; D8 reports **4** references where 2 real ones exist | D6.7.5 count defect, in the inflating direction |
| **2E** | `GRANT SELECT ON mem_roster TO r` (no privilege collision) | **PASS exit 0** | isolates the privilege word as the sole cause |

### 4.3 Positive / non-vacuity controls a fix must not mask

| # | Subject | Observed | Why it matters |
|---|---|---|---|
| **2F** | `UPDATE bil_invoices SET x = 1` | **FAIL exit 1** | an ordinary `UPDATE` table position |
| **2G** | `CREATE TABLE mem_t (c int REFERENCES bil_invoices)` | **FAIL exit 1** | an ordinary `REFERENCES` table position — §6.3's textbook foreign-key instance |
| **2H**, **2I** | the ADR's two named controls | **PASS exit 0** | unchanged |

### 4.4 Classification and governing invariant

(2) is **pure over-extraction**, which ADR-011 **D6.7.1** names as the *safe* direction ("an
over-extracted identifier reaches state 6 and ERRORs — loud, bounded, correctable"). No probed
form is clean, and no composition of (2) alone produces a clean pass: the spurious identifier
is the literal string `ON`, which no manifest prefix owns. It is therefore **not** a
soundness defect and **not** a demonstrated gate-level false PASS. What it does violate is
**D6.7.5** (the D8 attribution figure is inflated and duplicated while the note asserts
completeness) and D3.2 state precision — SCN-MOD001-007 requires the denial to *name the right
thing*, and 2C/2D name `ON`. Closing it is a **narrowing** of the extractor, which D6.7.1
says "requires its own recorded decision" — hence the ADR dependency in §6.3.

---

## 5. The composite result: (2) currently masks part of (1)

| # | Subject | Observed |
|---|---|---|
| **1A** | `REVOKE SELECT ON mem_roster`⏎`SELECT a FROM bil_invoices` | **PASS exit 0** |
| **3A** | `REVOKE UPDATE ON mem_roster`⏎`SELECT a FROM bil_invoices` | **ERROR exit 2** `MODULE_DEPS_TABLE_UNATTRIBUTED: … table 'ON'` |

The same false-PASS text fails closed when the privilege happens to be `UPDATE` rather than
`SELECT`, and it fails closed **only because of failure (2)** — the spurious `UPDATE -> 'ON'`
position raises state 6 and the ERROR class dominates. Failure (2) is an accidental backstop
over a subset of failure (1)'s surface.

**Consequence, and the reason this record exists.** Closing (2) on its own — exactly the "next
code/test increment" proposed in `GATE2-R2-N01-D67-GRANT-REVOKE-ON-LOCAL-VERIFICATION-2026-10-06.md`
§Exact residuals item 1 — would remove that backstop and **widen the demonstrated false-PASS
surface** from `REVOKE SELECT …` to the `REVOKE UPDATE/REFERENCES …` spellings as well, while
524/524 tests stayed green and the change's own analysis correctly showed it added only ERROR
surface locally. That is a measured, not speculative, argument that the two failures cannot be
taken in that order, and it is the concrete content of "stop serial implementation increments".

---

## 6. One atomic bounded correction seam

### 6.1 The seam

**Make signal suppression a decision taken inside the accounted stream, under a
positively-bounded precondition.** One rule governs both failures:

> A recognised table-position signal may be suppressed **only** when the suppressing
> statement's own region containing it has been **positively computed** by an anchored walk.
> Where no such bound can be computed, the signal is **retained** (D6.7.1's safe direction),
> and the retention is what the D6.7.2 accounting then sees.

Both failures are instances of a single missing primitive: **the extent of a `GRANT`/`REVOKE`
statement's own privilege-list, object-list and grantee regions.** `_grant_revoke_object_on_match`
(`:3547-3567`) already computes the privilege-list region's end — the object `ON` — and
**no consumer uses that interval**. The seam is to compute the region triple once and consume
it at the one existing merge point, `_table_position_results`' `for source in
_TABLE_POSITION_SIGNAL_SOURCES` loop (`:3892-3894`), rather than inside any individual source:

- **half (1), the bound:** replace `_GRANTEE_FROM_RE.search(text, on.end())` with the anchored
  walk COPY already uses — consume the object list positively (optional `TABLE`/`ONLY`
  modifier, identifier, `(, identifier)*` at the same depth), then `.match` `\bFROM\b` at that
  exact offset. No bound ⇒ `None` ⇒ no suppression ⇒ the `FROM` stays a position.
- **half (2), the context:** a `_TABLE_KEYWORD_RE` or `_REFERENCES_KEYWORD_RE` match whose
  `start()` lies in the already-computed half-open interval `[verb.end(), object_on.start())`
  is a privilege word, not a table position.

This is a **conformance repair to an existing approved pattern**, not a new design: half (1)
makes the two exclusions actually structurally identical, which both the source docstring
(`:3673-3680`) and the test comment (`test_…:3979-3981`) already claim they are.

### 6.2 Feasibility, measured without modifying anything

Simulated in `/tmp/veyro-rc-probe/seam.py` (probe-local functions; the repository source was
never patched), current behaviour vs. the candidate:

| Row | current | candidate |
|---|---|---|
| `REVOKE SELECT ON mem_roster`⏎`SELECT a FROM bil_invoices` | `37` (steals) | **`None`** (no `FROM` anchored at 28; `'SELECT a FRO'`) |
| `REVOKE SELECT ON mem_roster`⏎`SELECT a FROM mem_x, bil_invoices` | `37` (steals) | **`None`** |
| `REVOKE SELECT ON mem_roster FROM r` (+ victim) | `28` | `28` ✔ |
| `REVOKE SELECT ON mem_roster, mem_events FROM r` | `40` | `40` ✔ |
| `REVOKE SELECT ON ONLY mem_roster FROM r` | `33` | `33` ✔ |
| `REVOKE SELECT ON TABLE mem_roster FROM r` | `34` | `34` ✔ |
| `REVOKE SELECT ON sb.mem_roster FROM r` | `31` | `31` ✔ |
| `REVOKE SELECT ON "mem roster" FROM r` | `30` | `30` ✔ |
| `REVOKE SELECT (col) ON mem_roster FROM r` | `34` | `34` ✔ |
| `REVOKE GRANT OPTION FOR SELECT ON mem_t FROM r` | `40` | `40` ✔ |
| `REVOKE admin FROM r` (role revocation) | `None` | `None` ✔ |
| `REVOKE SELECT ON` (dangling) | `None` | `None` ✔ |
| `REVOKE ALL ON ALL TABLES IN SCHEMA sb FROM r` | `38` | `None` — **disclosed delta**, see §6.4 |

Half (2)'s predicate, over the same corpus, suppresses **exactly** the four spurious signals
(`UPDATE`@6, `REFERENCES`@6, `UPDATE`@22, `UPDATE`@7) and **nothing** in 2E, 2F, 2G, 2H or
2I — so it closes the collision and the double-count without masking any ordinary `UPDATE` or
`REFERENCES` table position. Both halves are lexically decidable with stdlib regex and an
offset walk; **D9's third-party-parser deferral stands and is not a dependency.**

### 6.3 Exact dependency, per half

- **Half (1) needs no new ADR clause.** It strictly *adds* retained signals and therefore only
  adds ERROR surface. It is already mandated by D6.7.1/.2/.6 — it is a conformance repair to a
  live violation, not a new decision. It is independently legal on that basis.
- **Half (2) is blocked on the ADR-011 **D6.8** amendment** the preflight record already names
  downstream. It *removes* positions, i.e. narrows the extractor, which D6.7.1 states
  "requires its own recorded decision"; the recordable losslessness argument is available
  (the suppressed identifier is the reserved word `ON`, never a real table, and
  `GRANT UPDATE ON x` still yields `ON -> x`, so no real table position is lost) but it is
  `veyro-lead`'s to adjudicate, not this record's.
- **Ordering is forced by §5.** If the D6.8 adjudication delays half (2), half (1) must still
  land **first or alone**. Half (2) must **never** land before half (1) — doing so would widen
  the false-PASS surface. This is the exact dependency, not a preference.

### 6.4 Disclosed behavioural delta the implementer must assert, not discover

`REVOKE ALL ON ALL TABLES IN SCHEMA sb FROM r` changes refusal *reason* under half (1): today
the grantee `FROM` is excluded, leaving zero positions and a D6.3 I-1 ERROR; under the
candidate the `FROM` is retained, resolves to the role `r`, and ERRORs at D3.2 state 6. **Both
are ERROR exit 2 — fail-closed either way**, and the change is in D6.7.1's safe direction.
Checked against the live test file: the pinned non-table-object cases are all **`GRANT`**
spellings (`_D67_GRANT_NON_TABLE_OBJECT = "GRANT USAGE ON SCHEMA mem_private TO r"` at
`test_…:3662`, asserted I-1 at `:3851`; `"GRANT SELECT ON ALL TABLES IN SCHEMA mem_private
TO r"` asserted `[]` at `:3949`), and the exclusion loop runs over `_REVOKE_KEYWORD_RE` only —
so **no existing assertion is broken by this delta**; it needs a new row, not a reconciliation.

### 6.5 Existing-test compatibility (checked, not assumed)

- `test_…:3982-3986` pins `_revoke_grantee_exclusion_offset` to `index("FROM")` for
  `REVOKE SELECT ON bil_invoices FROM r` and to `None` for `REVOKE admin FROM r`. The
  candidate satisfies **both** (§6.2 rows 3 and 11). Half (1) breaks no pinned assertion.
- `test_…:3963-3977` deliberately does **not** pin the stray privilege position's outcome,
  stating in terms that a later increment "must be free to turn these statements clean without
  rewriting this assertion", and asserts only that `mem_roster` is extracted. Half (2)
  satisfies that and breaks no pinned assertion either.

So the seam's cost is new rows plus the §7e docstring/comment corrections — not a rewrite of
the pinned corpus.

---

## 7. Criterion for actual original-finding blocker reduction

R1-F01's blocker list reduces **only** when every item below holds. This is a reduction
criterion for the *blocker list*, not a closure criterion for the finding.

- **(a) The three negative rows invert.** 1A, 1F, 1H each exit **nonzero** on their own
  surface, and the emitted code names the suppressed signal — `MODULE_DEPS_SOURCE_UNINSPECTABLE`
  (D6.7.6) or `CROSS_DOMAIN_SQL_IMPORT` for the recovered `bil_invoices`. Exit 0 on any of the
  three means no reduction.
- **(b) Every control in §3.2/§3.3/§4.3 holds unchanged.** 1B/1C/1D/1G/2F/2G stay exit 1;
  1E/2E/2H/2I stay exit 0. A negative row inverted at the cost of a positive control is not a
  reduction.
- **(c) Both halves' mutants are killed.** M-B1: restore the unbounded `.search` ⇒ at least one
  of 1A/1F/1H returns to exit 0. M-B2: invert the "no bound ⇒ retain" rule to "no bound ⇒
  suppress" ⇒ likewise. M-B3: drop the privilege-interval predicate ⇒ 2A/2B return to exit 2
  and 2D's duplicate `CROSS_DOMAIN_SQL_IMPORT` line returns. A surviving mutant is a blocker,
  not a note (ADR-011 §Addendum follow-up).
- **(d) D6.7.5 truthfulness restored for these rows.** No run that suppressed a signal without
  a positively computed bound asserts its table-reference count "complete for this run"; the
  D8 figure stays a disclosed **lower bound**. 2D's D8 count stops double-counting
  (4 → the real number).
- **(e) The two false structural-identity claims are corrected** (DC-12): the source docstring
  at `:3673-3680` and the test comment at `test_…:3979-3981`, each of which currently asserts
  the REVOKE exclusion is positively computed like COPY's when it is an unbounded search. Also
  the module docstring at `:249-257`, which ADR-011 §Addendum follow-up already makes a
  precondition for any D6.7 remediation record claiming completion.
- **(f) No regression in the existing suites:** 524/524 `tools/tests/test_validate_architecture_gates.py`,
  597/597 tools tests, Ruff and `py_compile` PASS. Not re-run by this record (the preflight
  snapshot's figures are carried forward unverified by this turn, as that record itself states).
- **(g) Formal state is unmoved by (a)–(f).** Local satisfaction reduces the blocker list and
  nothing else: **R1-F01 stays formally OPEN**, round-2 stays **BLOCKED**, and closure needs
  the independent fresh-context round-3 `veyro-code-reviewer` review ADR-011's follow-up
  specifies — whose charge includes re-executing the eleven-row reproducer and hunting for any
  statement in which one cleanly-extracted identifier still suppresses a refusal elsewhere.
  §3 is a direct answer to that charge and an **input** to that review, never an approval of
  it (DC-14).

---

## 8. Why this differs materially from another keyword patch

Every D6.7 increment in this lineage so far — `ONLY`, `TRUNCATE`, `COPY`, the four-signal
shared walk, `GRANT/REVOKE ON` — has the same shape: a token added to a vocabulary set
(`_TABLE_POSITION_KEYWORDS`, `_LIST_POSITION_SIGNALS`) plus a context-sensitive signal source.
ADR-011 D6.7.4 says in terms that vocabulary is "**a floor, not the mechanism**", and the
addendum's own Alternatives table rejects "Widen `_TABLE_KEYWORD_RE` only" as "the treadmill
this ADR's own Alternatives table already rejected once". Three measured reasons this is not
the sixth lap:

1. **Neither failure is a vocabulary gap, and neither is fixed by any keyword edit.** (1)'s
   vocabulary is already complete — `FROM` is recognised; the defect is the *bound* on a
   predicate. (2) requires `UPDATE` and `REFERENCES` to **stay** in the vocabulary.
2. **The vocabulary route is demonstrably unsound for (2), not merely inelegant.** Rows 2F and
   2G are at exit 1 *because* `UPDATE` and `REFERENCES` are keywords. Removing either to kill
   the collision converts a measured FAIL into a false clean — a strictly worse trade than the
   ERROR noise it removes. The fix must be positional, and position is what a keyword set
   cannot express.
3. **The defect class is one architectural level above vocabulary** (§3.5): D6.7.2's accounting
   sits **downstream** of signal production, so every pre-accounting filter is outside the
   invariant's reach. A keyword patch adds a sixth filter in that blind spot — which is
   precisely how an increment that correctly reasoned it "adds real target attribution … but
   does not remove the ERROR" nonetheless shipped a new exit-0 false clean. The seam in §6
   moves suppression *inside* the accounted stream under a bounded precondition, once, for
   every family present and future. §5 then shows the two failures are not independently
   patchable **in either order of convenience**: the safe order is forced.

The honest limit on this argument: the seam is a repair to the *suppression* half of the blind
spot. The *production* half — full residue accounting, classifying every identifier-shaped
token — remains the ADR's rejected-for-now alternative, tied to D9's parser trigger. This
record does not claim otherwise.

---

## 9. State after this record

R1-F01 formally **OPEN**. Round-2 **BLOCKED P0=1/P1=1/P2=2/P3=2**. U1/U2 **B HOLD** in force,
untouched. D8 table-reference figure remains a disclosed **lower bound**. **No scenario PASS**;
SCN-MOD001-006/-007/-095/-096 NOT EXECUTED and unpromoted. MOD-001 uncertified; WIP=1;
MOD-002 locked. Live CTE state-3 wiring untouched and still forbidden. No ADR edited — the
**D6.8** amendment and the independent round-3 assurance both remain downstream and
unperformed. No verdict is claimed and no owner approval is sought or implied; the one
owner-reserved item on this surface (binding the six `backend/app/modules/` scaffolds to
domain codes and owned table prefixes) remains **`BLOCKED: OWNER_APPROVAL_REQUIRED`**,
untouched, and is not a dependency of anything above.

Next bounded legal operation, per §6.3: the **D6.8** adjudication for half (2), and/or the
half-(1) bounding repair, which §6.3 establishes needs no new ADR clause and must not be
preceded by half (2). Nothing in this record authorises either dispatch.
