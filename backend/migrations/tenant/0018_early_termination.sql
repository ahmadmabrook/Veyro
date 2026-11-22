-- MOD-017 (COM-01): a contract may let a member leave inside the minimum term, for a price.
--
-- **Found by building ADM-MSH-07, and the finding is that the design and the implementation
-- disagreed about a money figure.** The canvas discloses "his 12-month commitment runs to
-- March. Cancelling now triggers a two-month fee of JOD 80.00, and his access ends on
-- 7 September after the notice period" -- a commitment broken, a buy-out charged, access
-- ending after notice. `cancellation_effective_on` implemented the opposite and argued for
-- it in its own docstring: "a member inside their commitment cannot cancel out of it by
-- giving notice: the notice runs, and the effective date is whichever is later". Under that
-- rule Tareq's access ends in March and no fee arises at all.
--
-- Both readings are defensible from the sources, which name a "contract version, signature,
-- start/end, minimum term, notice, renewal and cancellation policy" and never say what the
-- cancellation policy is. The design is the authority on what the product does, so the
-- buy-out is what gets implemented -- and the divergence is worth recording rather than
-- quietly resolved, because nothing had noticed it: no screen rendered the fee, so the only
-- reader of that arithmetic was a test asserting the arithmetic. **A figure with no reader
-- is a figure nobody has checked against the design**, which is this build's "a writer with
-- no reader" shape pointed at a number instead of a table.
--
-- **Nullable, because zero is a term and not an absence.** `NULL` is "this contract holds
-- them to the term", which is what every contract in this build said until now and what the
-- lifecycle still enforces for one. `0` is "they may leave free", which is a different
-- product a tenant may legitimately sell. An integer is the buy-out in months of the
-- agreement amount. A boolean beside a count would let the two disagree, which is MOD-020's
-- "two caller-supplied keys that nothing relates are two halves of a control".
ALTER TABLE plt01.mem_contract_versions
    ADD COLUMN early_termination_months integer;

ALTER TABLE plt01.mem_contract_versions
    ADD CONSTRAINT mem_contract_versions_early_termination_sane
        CHECK (early_termination_months IS NULL
               OR early_termination_months BETWEEN 0 AND 120),
    -- **A buy-out of a term that does not exist is a column implying a control nobody
    -- implemented**, which is MOD-012's finding and this build's most repeated one.
    -- `cancellation_fee` charges the buy-out only where the agreement carries a
    -- `minimum_term_ends_on`, and that is written from `minimum_term_months`, so a value
    -- here on a rolling contract is inert -- it reads as a fee on an ordinary cancellation
    -- and can never be one. Refused at the row rather than left to the service, because the
    -- service's choice of SQL is not the writer this constraint exists for.
    ADD CONSTRAINT mem_contract_versions_early_termination_needs_a_term
        CHECK (early_termination_months IS NULL OR minimum_term_months > 0);

-- **No grant moves, and that is the control.** The table carries `SELECT, INSERT` and a
-- column-scoped `UPDATE (status, published_at, published_by, publish_correlation_id)`, so
-- the new column is settable when a version is drafted and immutable afterwards -- like
-- every other policy number beside it. The terms a member agreed to on the fourteenth have
-- to still read the same a year later, and a buy-out price that could be edited after
-- signature is the one number somebody would want to edit.

COMMENT ON COLUMN plt01.mem_contract_versions.early_termination_months IS
    'Months of the agreement amount charged for leaving inside the minimum term. NULL means '
    'the contract does not permit it and the minimum term decides when access ends; 0 means '
    'it permits it at no charge.';
