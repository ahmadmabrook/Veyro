# R1-F01 / R2-N01 — D6.7 ONLY and bare-form signal root cause

Operation: `ed64e2a1-f885-4807-8908-d3f1d20bb67e`. Deterministic analysis only; no scanner/test edit, Claude dispatch, review, scenario promotion, or CTE state-3 wiring. The U1/U2 B HOLD persists. Formal R1-F01/R2-N01 remains OPEN and R2 remains BLOCKED.

## Reproduction

Executed fresh isolated module-dependency fixtures with a `membership_` importer, a `billing_` owner, and identical SQL text once as `repo.sql` and once as a Python `QUERY` string. Also inspected `_table_position_results` for the same text. Results were identical across both surfaces:

| SQL shape | Position identifiers now | Live status/code now | Required distinction |
| --- | --- | --- | --- |
| `SELECT * FROM ONLY membership_roster` | `ONLY` | ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED` | `ONLY` modifies the `FROM` target; `membership_roster` is the one owned position, so clean |
| `SELECT * FROM membership_roster, ONLY billing_invoice` | `membership_roster`, `ONLY` | ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED` | Second position is `billing_invoice`; cross-domain FAIL, not an unattributed modifier |
| `SELECT * FROM membership_roster, ONLY membership_events` | `membership_roster`, `ONLY` | ERROR / `MODULE_DEPS_TABLE_UNATTRIBUTED` | Both owned positions; clean |
| `TRUNCATE membership_roster, billing_invoice` | none | ERROR / `MODULE_DEPS_SOURCE_UNINSPECTABLE` via I-1 | Two positions, including a cross-domain target; FAIL after attribution |
| `COPY billing_invoice TO STDOUT` | none | ERROR / `MODULE_DEPS_SOURCE_UNINSPECTABLE` via I-1 | One cross-domain table position; FAIL after attribution |
| `GRANT SELECT ON billing_invoice TO someone` | none | ERROR / `MODULE_DEPS_SOURCE_UNINSPECTABLE` via I-1 | Contextual `ON` introduces one cross-domain table position; FAIL after attribution |
| `SELECT * FROM membership_roster JOIN billing_invoice USING (id)` | `membership_roster`, `billing_invoice` | FAIL / `CROSS_DOMAIN_SQL_IMPORT` | `USING (id)` is a column-list non-signal; keep this behavior |
| `SELECT 1` | none | PASS | No table-position signal; keep this behavior |

The existing I-1 ERROR for a wholly unextracted bare form is fail-closed, but it does not satisfy D6.7.2–.3's **per-element attribution and count**. A mixed statement with another extracted table can also disarm a statement-wide I-1 fallback. The `ONLY` result is a false attribution, not an omitted independent signal: treating `ONLY` as a second table-position keyword would double-count or continue to misclassify the modifier.

## Structural seam and next bounded implementation

`_TABLE_POSITION_SIGNAL_SOURCES` feeds the sole `_table_position_results` stream; `_positions_for_signal` sends list-bearing signals into the sole `_table_list_positions` walker. `_extract_table_identifiers`, `_dangling_keywords`, and the live scanner already project that stream. The missing behavior belongs **before or within that shared signal/target seam**, not in D8 text, vocabulary-only `_TABLE_POSITION_KEYWORDS`, a duplicate extractor, or a statement-wide fallback.

1. `ONLY` is an optional modifier on a target introduced by an existing signal (`FROM`, `JOIN`, or a comma continuation). Make the shared target lexer/list walk consume it before the identifier, without emitting a separate position. A dangling `FROM ONLY` must remain one unresolved position. Do not add context-free `ONLY` to the signal-source tuple.
2. A later separate increment should provide context-sensitive bare-form signal sources for `TRUNCATE`/`COPY` and `GRANT`/`REVOKE ... ON`, each routing to the same `_positions_for_signal`/list walk. A generic `ON` source would be wrong because JOIN predicates use `ON` without introducing a new table; generic `TO`/`FROM` handling would also confuse COPY direction. Preserve the D6.3 backstop for unrecognized/unresolved forms.

First bounded code/test increment: **ONLY modifier in the shared target walk**, with both `.py` and `.sql` live fixtures. Assert exact position records and status/codes for the three ONLY cases above, `FROM ONLY` unresolved, `JOIN ... USING (id)` as column-list negative, and `SELECT 1` no-position positive. Mutation controls: (a) remove modifier consumption: own ONLY cases return spurious ERROR and exact-record assertions fail; (b) treat ONLY as independent signal: position cardinality/identifier assertions fail; (c) skip the continuation after ONLY: cross-domain second element is missing and FAIL assertion fails. The subsequent bare-form increment needs exact-record/cardinality plus own-table PASS/cross-domain FAIL for each family on both surfaces, and must kill omission of each source and generic-ON overreach with a JOIN-ON predicate control.

No D6.7.2 totality proof, full N/P/M corpus, D8 complete-coverage assertion, F14 historical byte-exact replay disposition, independent assurance, or formal closure follows from this diagnosis.
