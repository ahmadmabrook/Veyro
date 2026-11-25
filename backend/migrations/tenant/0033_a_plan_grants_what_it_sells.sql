-- MOD-017 · COM-01-R03: the edge between a plan and the rights it sells.
--
-- **`mem_entitlement_policies` has had a consumer and no producer since this module was
-- built.** `mem_entitlement_grants` carries everything a plan would need to hand out -- the
-- policy, a quantity, a window, a brand, a location, a time-of-day band, the membership, and
-- `source_kind = 'membership'` -- and `grep -rn 'source_kind="membership"' backend/` returns
-- three hits, all of them in `test_commercial_api.py`. The only writer in the product is
-- `POST /member-entitlements`, which a human calls by hand. So activating a membership grants
-- nothing, every Member 360's entitlements block is empty for every member, and
-- `change_membership_plan` says in its own response that it cannot know what the plan being
-- left gave.
--
-- This is the inverse of this build's most-repeated finding. A column implying a control
-- nobody implemented is one shape; a *model* with a consumer and no producer is this one, and
-- it reads as complete from every direction: the policies have a writer, the grants have a
-- writer, the balance read works, the reservation is atomic and under a lock. One edge was
-- missing and nothing in the schema said so.
--
-- Design record: `knowledge/00-Decisions/ADR-0013-mod017-what-a-plan-grants.md`.
-- ADM-MSH-06's canvas is what needs it: "She loses: Access to Abdoun and Sweifieh · 2 monthly
-- PT sessions · her 4 unused PT credits expire on 1 Sep."

-- ---------------------------------------------------------------- what a variant grants

CREATE TABLE plt01.mem_plan_entitlements (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    plan_entitlement_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- **Per variant, not per product** (ADR-0013 D1). A variant is a term length and "2 PT
    -- sessions monthly" is a figure per billing period, so an annual variant of the same
    -- product legitimately grants twenty-four where a monthly one grants two. Per product
    -- that is unexpressible, and it would force a second product for every term length.
    variant_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    -- NULL for an uncounted right -- "access to Abdoun", which is a yes/no over a window
    -- rather than a number. The CHECK below ties this to the policy's own `is_counted`
    -- through the service rather than the schema, because `is_counted` lives on the policy
    -- and a CHECK cannot read another row; what the schema holds is that a quantity is
    -- positive when there is one.
    quantity integer,
    -- **The same four scope columns a grant has, copied through** (ADR-0013 D3). The
    -- canvas's distinction *is* these: "all-clubs access" is a `location_access` row with no
    -- location, and "access to Abdoun and Sweifieh" is two rows each naming one. A `scope`
    -- enum would be a second vocabulary this module then has to interpret twice.
    brand_id uuid,
    location_id uuid,
    usable_from_minute integer,
    usable_to_minute integer,
    -- **No period column** (ADR-0013 D4). `mem_membership_terms.billing_period` is where a
    -- quantity refreshes, and two places stating that is two places that can disagree about
    -- how many sessions a member has -- this build's most-repeated defect, created on purpose.
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    -- **Withdrawn rather than deleted**, for the reason every operational statement in this
    -- build is: "did this plan grant PT sessions in August, and who stopped it" is asked when
    -- a member disputes what they were sold.
    withdrawn_at timestamptz,
    withdrawn_by uuid,
    withdraw_reason text,
    PRIMARY KEY (tenant_id, plan_entitlement_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, policy_id)
        REFERENCES plt01.mem_entitlement_policies (tenant_id, policy_id),
    -- **The scope columns carry parents, as the grant's do.** Found by writing the sweep: a
    -- scope with no reference can name a brand that does not exist, and the activation would
    -- then copy it into `mem_entitlement_grants` -- which *is* referenced -- so the refusal
    -- would arrive at the grant, in the transaction that activates a membership, naming a
    -- table the operator never touched.
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT mem_plan_entitlements_quantity_positive
        CHECK (quantity IS NULL OR (quantity > 0 AND quantity <= 10000)),
    -- A band is both ends or neither, and ordered -- the same pairing the grant's own band has.
    CONSTRAINT mem_plan_entitlements_band_paired
        CHECK ((usable_from_minute IS NULL) = (usable_to_minute IS NULL)),
    CONSTRAINT mem_plan_entitlements_band_bounded
        CHECK (usable_from_minute IS NULL
               OR (usable_from_minute >= 0 AND usable_from_minute < 1440
                   AND usable_to_minute > usable_from_minute AND usable_to_minute <= 1440)),
    -- A withdrawal states who and why, or none of the three. MOD-009's rule: evidence with
    -- nobody's name on it answers nothing, and a `coalesce` so a NULL reason is refused as
    -- surely as a blank one.
    CONSTRAINT mem_plan_entitlements_withdrawal_attributed
        CHECK ((withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdraw_reason IS NULL)
               OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL
                   AND coalesce(withdraw_reason, '') ~ '[^[:space:]]'))
);

ALTER TABLE plt01.mem_plan_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_plan_entitlements FORCE ROW LEVEL SECURITY;

CREATE POLICY mem_plan_entitlements_tenant ON plt01.mem_plan_entitlements
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- One live row per (variant, policy, brand, location), so a plan cannot grant the same right
-- twice at the same scope -- which would double a member's quantity on activation with nothing
-- saying which row was the mistake. Partial on the withdrawal, so a withdrawn row leaves the
-- slot free for a corrected one.
CREATE UNIQUE INDEX mem_plan_entitlements_one_live
    ON plt01.mem_plan_entitlements (tenant_id, variant_id, policy_id,
                                    coalesce(brand_id, '00000000-0000-0000-0000-000000000000'),
                                    coalesce(location_id, '00000000-0000-0000-0000-000000000000'))
    WHERE withdrawn_at IS NULL;

CREATE INDEX mem_plan_entitlements_by_variant
    ON plt01.mem_plan_entitlements (tenant_id, variant_id)
    WHERE withdrawn_at IS NULL;

-- A withdrawal is final, and a CHECK cannot see `OLD`. `sec_legal_holds`' precedent: the row
-- is kept precisely so "how long did this plan grant that" stays answerable, and a release
-- that could be rewound or re-dated rewrites exactly that.
CREATE OR REPLACE FUNCTION plt01.mem_plan_entitlements_withdrawal_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    IF OLD.withdrawn_at IS NOT NULL
       AND (NEW.withdrawn_at IS DISTINCT FROM OLD.withdrawn_at
            OR NEW.withdrawn_by IS DISTINCT FROM OLD.withdrawn_by) THEN
        RAISE EXCEPTION
            'a withdrawn plan entitlement keeps the moment and the actor it was withdrawn by';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION plt01.mem_plan_entitlements_withdrawal_is_final() FROM PUBLIC;

CREATE TRIGGER mem_plan_entitlements_withdrawal_is_final
    BEFORE UPDATE ON plt01.mem_plan_entitlements
    FOR EACH ROW EXECUTE FUNCTION plt01.mem_plan_entitlements_withdrawal_is_final();

GRANT SELECT, INSERT ON plt01.mem_plan_entitlements TO veyro_cp_app, veyro_cp_worker;
-- **The withdrawal columns only.** What a plan grants and at what scope cannot be edited: a
-- quantity that moved would change what every *future* member gets with no record of the
-- change, and re-pointing `policy_id` would make an old grant's provenance a lie. Correcting
-- a row is withdrawing it and declaring the corrected one, which is MOD-019's rota rule.
GRANT UPDATE (withdrawn_at, withdrawn_by, withdraw_reason)
    ON plt01.mem_plan_entitlements TO veyro_cp_app, veyro_cp_worker;

-- ------------------------------------------------- which plan gave a grant

-- **`source_kind = 'membership'` with `source_id` is not enough** (ADR-0013 D6). A membership
-- outlives a plan change, so "this grant came from this membership" cannot tell a downgrade
-- which rights the plan being left gave. The variant can, and it is the same id the mapping is
-- keyed on.
ALTER TABLE plt01.mem_entitlement_grants
    ADD COLUMN from_variant_id uuid;

COMMENT ON COLUMN plt01.mem_entitlement_grants.from_variant_id IS
    'The variant whose plan entitlements produced this grant, where one did. NULL for a '
    'goodwill, corporate, migration or bundle grant, and for every grant written before '
    '0033 -- which is why it is nullable rather than NOT NULL with a backfill: a grant made '
    'by hand has no plan behind it and inventing one would make a provenance up.';

ALTER TABLE plt01.mem_entitlement_grants
    ADD CONSTRAINT mem_entitlement_grants_variant_fk
        FOREIGN KEY (tenant_id, from_variant_id)
        REFERENCES plt01.cat_variants (tenant_id, variant_id);

-- A grant naming a plan is one a membership produced. The reverse does not hold: a membership
-- grant written by hand before this migration, or by a route that names no variant, is still a
-- membership grant.
ALTER TABLE plt01.mem_entitlement_grants
    ADD CONSTRAINT mem_entitlement_grants_variant_is_a_membership
        CHECK (from_variant_id IS NULL OR source_kind = 'membership');

CREATE INDEX mem_entitlement_grants_by_membership_variant
    ON plt01.mem_entitlement_grants (tenant_id, membership_id, from_variant_id)
    WHERE status = 'active';
