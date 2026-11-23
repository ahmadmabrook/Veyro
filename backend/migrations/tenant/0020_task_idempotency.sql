-- MOD-026 slice 1b — a create has to be idempotent to the caller.
--
-- `0019` gave tasks and cases no idempotency key, which `0019` should have done: every other
-- module's create takes one, and MOD-017's review found the defect this closes in three
-- commands at once -- "a client whose request timed out after the commit was told the work had
-- failed", and for an approval that means a second approver is asked for a decision already
-- made. Here it means a second task, or a second case, for one request.
--
-- **A unique index is not enough on its own and it is what makes the rest possible.** The
-- service answers a repeat from the row it already wrote rather than returning 409, because a
-- caller told "conflict" cannot tell a duplicate request from a real collision -- which is
-- MOD-017's own finding, and `tsk_cases.case_number` would otherwise have been the only
-- thing refusing a retry.
--
-- **NOT NULL rather than nullable with a partial index.** Nothing is deployed anywhere, so
-- there are no rows to accommodate, and a nullable key is one a caller can omit -- which
-- makes the command idempotent only for callers who opt in. MOD-021, MOD-022 and MOD-020
-- each shipped an idempotency key compared on fewer fields than the command took; an absent
-- one is the same defect with the comparison removed entirely.

ALTER TABLE plt01.tsk_tasks
    ADD COLUMN idempotency_key text NOT NULL,
    ADD CONSTRAINT tsk_tasks_idempotency_key_shape
        CHECK (idempotency_key ~ '[^[:space:]]' AND length(idempotency_key) <= 200);

ALTER TABLE plt01.tsk_cases
    ADD COLUMN idempotency_key text NOT NULL,
    ADD CONSTRAINT tsk_cases_idempotency_key_shape
        CHECK (idempotency_key ~ '[^[:space:]]' AND length(idempotency_key) <= 200);

-- **Scoped to the tenant and to nothing else, which is deliberate.** MOD-018's "an
-- idempotency namespace a caller can write into is not a namespace" is about two *commands*
-- sharing one key column: a decoy journal keyed `wallet-credit-TOPUP-9` was handed back as
-- the repeat of a wallet credit keyed `TOPUP-9`. Tasks and cases are different tables, so
-- their namespaces are already separate; what matters is that neither is shared with a
-- command that means something else.
CREATE UNIQUE INDEX tsk_tasks_one_per_key ON plt01.tsk_tasks (tenant_id, idempotency_key);
CREATE UNIQUE INDEX tsk_cases_one_per_key ON plt01.tsk_cases (tenant_id, idempotency_key);

-- Not granted UPDATE: a key identifies the request that created the row, so moving it would
-- let a later request claim an earlier row's identity.
