-- MOD-017 -- a lifecycle change records which agreement it moved onto.
--
-- **Two things needed this column and neither of them is cosmetic.**
--
-- The first is the history. COM-01-R07's as-of reconstruction is argued "for disputes and
-- audits", and until now an `upgrade` row said the kind, the date and what it cost and not a
-- word about *what the member moved onto* -- so the one record a dispute is argued from could
-- not answer the first question anybody asks about an upgrade. The agreement chain carries the
-- same fact, which is why this is a reference and not a copy of the amount: the agreement is
-- the authority and a second figure here could disagree with it, which is `invoice_id`'s own
-- reasoning three columns up.
--
-- The second is idempotency, and it is the sharper one. `change_membership_plan` derives its
-- own kind from the two prices, so a retry cannot be recognised by a kind the caller sent --
-- and a key compared on fewer fields than the command takes is this build's most-repeated
-- idempotency defect, found in MOD-016, MOD-017, MOD-018, MOD-019, MOD-021 and MOD-022. With
-- the target on the row a retry is compared against what the first call actually did.
--
-- **Nullable, because most change kinds move no agreement**, and constrained so that the two
-- that do always name one: a plan change with no target would be an `upgrade` nobody can
-- trace, and a freeze that named one would be a reference nothing reads.
ALTER TABLE plt01.mem_lifecycle_changes
    ADD COLUMN to_agreement_id uuid;

ALTER TABLE plt01.mem_lifecycle_changes
    ADD CONSTRAINT mem_lifecycle_changes_to_agreement
        FOREIGN KEY (tenant_id, to_agreement_id)
        REFERENCES plt01.mem_agreements (tenant_id, agreement_id);

ALTER TABLE plt01.mem_lifecycle_changes
    ADD CONSTRAINT mem_lifecycle_changes_plan_change_names_its_agreement
        CHECK ((change_kind IN ('upgrade', 'downgrade'))
               = (to_agreement_id IS NOT NULL));

-- The history is insert-only in full, so the column needs no grant of its own: `GRANT SELECT,
-- INSERT` on the table already covers it and there is no UPDATE grant to extend. Stated rather
-- than left for a reader to infer, because every other module's migration lists its grants and
-- an absence here would read as an omission.
COMMENT ON COLUMN plt01.mem_lifecycle_changes.to_agreement_id IS
    'For an upgrade or a downgrade, the agreement the membership moved onto. A reference, not '
    'a copy of its amount: the agreement is the authority.';
