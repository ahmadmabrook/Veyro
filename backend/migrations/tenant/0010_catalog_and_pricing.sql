-- MOD-016 COM-02: the commercial catalog, price books, promotions, coupons and bundles, plus
-- the explanation every price resolution leaves behind. Tables are module-prefixed `cat_`.
--
-- Every table repeats the four protections documented at the head of
-- `0001_organization_hierarchy.sql`: tenant-leading primary key, ENABLE plus FORCE row level
-- security, the `current_setting('app.tenant_id', true)` predicate that is NULL when no context
-- is set, and composite foreign keys carrying `tenant_id` into every parent -- including the
-- reference to `plt01_platform.tenants`. Checks 67 to 72 sweep all of it from the catalogue,
-- seat both runtime roles, compare every foreign key as a set and every UPDATE column grant per
-- role, assert the primary keys and the nullability, and carry a case per side of every
-- constraint -- the full shape the MOD-014 review arrived at, written in from the start.
--
-- Seven decisions are specific to this module.
--
--   * **A price's figures are never updated, and that is requirement COM-02-R07.** "Versioned
--     price changes that do not rewrite historical transactions": `cat_prices` carries no
--     UPDATE grant on the amount, the currency, the variant, the book or the window, so
--     re-pricing is a new row with a later `effective_from` and the old row keeps its window.
--     An order resolved last March can be re-derived from the rows that were in force then,
--     which is the only way paragraph 4076's "immutable order/invoice line snapshots with
--     source policy/version" is true of anything. The grant covers the supersession columns
--     and nothing else. Earlier drafts of this comment and of the two beside `cat_prices`
--     said "no UPDATE grant at all", which was false three times over while the grant below
--     still included `effective_to` -- the one column whose value decides whether a price is
--     in force. A reviewer found the prose, not the grant, which is the better way round and
--     still a claim this file made about a control it did not have.
--
--   * **Every resolution is recorded with its explanation.** Paragraph 10220: "pricing
--     resolution is deterministic and returns an explanation". `cat_price_resolutions` is that
--     explanation, insert-only, naming every input and every step -- the list price it started
--     from, each promotion that applied and why, each that did not and why not, and the policy
--     versions. A resolver that returned a number and no reasoning would be impossible to
--     dispute at a counter, which is where these numbers are read out loud.
--
--   * **A manual override is a separate, approved act.** The same paragraph: "manual price
--     overrides and high discounts require explicit permission and audit."
--     `cat_discount_approvals` is insert-only and carries the approver, the reason and the
--     amount, and the service refuses an override above the configured threshold without one.
--     A discount field on the resolution request would have been the same authority bought with
--     a body field, which is the shape MOD-009, MOD-013 and MOD-014 each shipped once.
--
--   * **There is no tax rate here.** `cat_tax_categories` names a category and nothing else.
--     Paragraph 4077: "tax rules are regional configuration/providers; tax rate is never
--     globally hard-coded", and the sources state no rates. MOD-015 made the same refusal --
--     `issue_invoice` takes a rate from its caller -- and a column holding a number nobody
--     sourced would be worse than the gap, because an invoice would then carry it.
--
--   * **Stacking is decided by group and priority, not by order of arrival.** Two promotions
--     in one stacking group cannot both apply; across groups they combine in priority order and
--     each is applied to the running subtotal. Determinism is the requirement, so the sort is
--     total: priority, then stacking group, then the promotion key. Without the last two a
--     resolution would depend on which row the planner returned first.
--
--   * **A coupon redemption is a row, not a counter.** `cat_coupon_redemptions` is insert-only
--     and the limits are counted from it. A `times_redeemed` column would be a second copy of
--     the truth that can disagree with the ledger beside it, which is MOD-011's argument
--     against a metric that duplicates a table, and here it would also be the thing two
--     concurrent redemptions race on.
--
--   * **A bundle links a sale to fulfilment and does not perform it.** COM-02-R03 asks for
--     bundles "linking commercial sale to operational fulfillment and entitlements", and the
--     modules that fulfil -- COM-01's entitlement grants, OPS-01's bookings -- are not built.
--     So a bundle declares what it owes and `cat_bundle_fulfilments` records what somebody says
--     was delivered, with an actor on the row. A module that wrote "fulfilled" with nothing
--     having fulfilled anything is the fabricated-evidence shape this build has been bitten by
--     five times.

-- ---------------------------------------------------------------- tax categories

-- **A name, and no rate.** Paragraph 4077 puts rates in regional configuration or a provider,
-- and the sources state none; MOD-015 refused the same way. What this table is for is letting a
-- product say which regime it falls under so whatever resolves a rate later has something to
-- resolve against.
CREATE TABLE plt01.cat_tax_categories (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    tax_category_id uuid NOT NULL DEFAULT gen_random_uuid(),
    category_key text NOT NULL,
    display_name text NOT NULL,
    -- What a tax engine would key on. Free text because a jurisdiction code system is a
    -- product decision the sources do not state.
    jurisdiction_note text,
    retired_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, tax_category_id),
    UNIQUE (tenant_id, category_key),
    CONSTRAINT cat_tax_categories_key_shape
        CHECK (category_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT cat_tax_categories_display_not_blank
        CHECK (length(btrim(display_name)) > 0),
    CONSTRAINT cat_tax_categories_note_not_blank
        CHECK (jurisdiction_note IS NULL OR length(btrim(jurisdiction_note)) > 0)
);
ALTER TABLE plt01.cat_tax_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_tax_categories FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_tax_categories_tenant ON plt01.cat_tax_categories
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- products

-- One commercial thing a tenant sells. The eight types are COM-02-R01's list exactly, as a
-- CHECK rather than a lookup table: a product type decides which other module fulfils the sale,
-- so two tenants disagreeing about what types exist would be unresolvable -- the same argument
-- MOD-008 makes for permissions and MOD-010 for event types.
CREATE TABLE plt01.cat_products (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    product_id uuid NOT NULL DEFAULT gen_random_uuid(),
    product_key text NOT NULL,
    product_type text NOT NULL,
    tax_category_id uuid,
    status text NOT NULL DEFAULT 'draft',
    -- Where it may be sold. Optional: a product with none is sold everywhere in the tenant,
    -- which is the ordinary case for a membership. (There is no `location_id` here; an earlier
    -- version of this comment said "both optional" and named a column that does not exist.)
    brand_id uuid,
    -- COM-02-R06's merchandising order. Lower sorts first; ties break on the key, so a listing
    -- is stable between runs.
    merchandising_rank integer NOT NULL DEFAULT 1000,
    version integer NOT NULL DEFAULT 1,
    published_at timestamptz,
    published_by uuid,
    retired_at timestamptz,
    retired_by uuid,
    retire_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, product_id),
    FOREIGN KEY (tenant_id, tax_category_id)
        REFERENCES plt01.cat_tax_categories (tenant_id, tax_category_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    UNIQUE (tenant_id, product_key),
    CONSTRAINT cat_products_key_shape CHECK (product_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    -- COM-02-R01, in full. A ninth type is a product decision, not a migration.
    CONSTRAINT cat_products_type CHECK (product_type IN (
        'membership', 'service', 'session_credit', 'class_credit', 'retail_sku',
        'subscription_addon', 'event', 'gift_card')),
    CONSTRAINT cat_products_status CHECK (status IN ('draft', 'published', 'retired')),
    -- A published product names who published it and when, and nothing else does. "Published"
    -- is the state that makes it sellable on every channel, so it is the one an auditor asks
    -- about.
    CONSTRAINT cat_products_publication_attributed CHECK (
        (published_at IS NULL AND published_by IS NULL)
        OR (published_at IS NOT NULL AND published_by IS NOT NULL)),
    CONSTRAINT cat_products_published_is_attributed
        CHECK (status <> 'published' OR published_at IS NOT NULL),
    CONSTRAINT cat_products_retired_at
        CHECK ((status = 'retired') = (retired_at IS NOT NULL)),
    -- Retirement is the act that stops a product being sold, so it names who did it on the
    -- same terms publication does. The first version had `retired_at` and no `retired_by`,
    -- beside a publication that carried both.
    CONSTRAINT cat_products_retirement_attributed CHECK (
        (retired_at IS NULL AND retired_by IS NULL AND retire_correlation_id IS NULL)
        OR (retired_at IS NOT NULL AND retired_by IS NOT NULL
            AND retire_correlation_id IS NOT NULL)),
    CONSTRAINT cat_products_rank_sane CHECK (merchandising_rank BETWEEN 0 AND 1000000),
    CONSTRAINT cat_products_version_positive CHECK (version >= 1)
);
CREATE INDEX cat_products_listing
    ON plt01.cat_products (tenant_id, status, merchandising_rank, product_key);
ALTER TABLE plt01.cat_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_products FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_products_tenant ON plt01.cat_products
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- COM-02-R06: localized names, descriptions and terms. One row per product per locale, because
-- a `jsonb` blob keyed by locale would be a column no sweep can read and no constraint can
-- shape -- MOD-010's finding about what hides inside `jsonb`, applied before it happens.
CREATE TABLE plt01.cat_product_texts (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    product_id uuid NOT NULL,
    locale text NOT NULL,
    display_name text NOT NULL,
    description text,
    -- The terms a member agrees to when they buy this. Shown at the point of sale, so it is
    -- part of the catalog rather than a document somewhere else.
    terms text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, product_id, locale),
    FOREIGN KEY (tenant_id, product_id) REFERENCES plt01.cat_products (tenant_id, product_id),
    CONSTRAINT cat_product_texts_locale CHECK (locale ~ '^[a-z]{2}(-[A-Z]{2})?$'),
    CONSTRAINT cat_product_texts_name_not_blank CHECK (length(btrim(display_name)) > 0),
    CONSTRAINT cat_product_texts_description_not_blank
        CHECK (description IS NULL OR length(btrim(description)) > 0),
    CONSTRAINT cat_product_texts_terms_not_blank
        CHECK (terms IS NULL OR length(btrim(terms)) > 0)
);
ALTER TABLE plt01.cat_product_texts ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_product_texts FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_product_texts_tenant ON plt01.cat_product_texts
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- What is actually priced and sold: a twelve-month membership, a ten-session pack, a large
-- shirt. A product with one variant is the common case and the variant still exists, because a
-- price that hung off the product would have nowhere to go the day a second size appears.
CREATE TABLE plt01.cat_variants (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    variant_id uuid NOT NULL DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL,
    variant_key text NOT NULL,
    display_name text NOT NULL,
    -- What one unit of this entitles the buyer to, for the modules that fulfil it. Both
    -- optional: a retail SKU grants nothing and a membership's term is its own.
    entitlement_quantity integer,
    term_days integer,
    -- The tenant's own stock-keeping code, where it has one.
    sku text,
    status text NOT NULL DEFAULT 'active',
    merchandising_rank integer NOT NULL DEFAULT 1000,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES plt01.cat_products (tenant_id, product_id),
    UNIQUE (tenant_id, product_id, variant_key),
    CONSTRAINT cat_variants_key_shape CHECK (variant_key ~ '^[a-z0-9][a-z0-9_.-]{0,62}$'),
    CONSTRAINT cat_variants_name_not_blank CHECK (length(btrim(display_name)) > 0),
    CONSTRAINT cat_variants_status CHECK (status IN ('active', 'discontinued')),
    CONSTRAINT cat_variants_quantity_positive
        CHECK (entitlement_quantity IS NULL OR entitlement_quantity > 0),
    CONSTRAINT cat_variants_term_positive CHECK (term_days IS NULL OR term_days > 0),
    CONSTRAINT cat_variants_sku_not_blank CHECK (sku IS NULL OR length(btrim(sku)) > 0),
    CONSTRAINT cat_variants_rank_sane CHECK (merchandising_rank BETWEEN 0 AND 1000000),
    CONSTRAINT cat_variants_version_positive CHECK (version >= 1)
);
-- A SKU identifies one variant, which is the only thing it is for.
CREATE UNIQUE INDEX cat_variants_sku ON plt01.cat_variants (tenant_id, sku)
    WHERE sku IS NOT NULL;
ALTER TABLE plt01.cat_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_variants FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_variants_tenant ON plt01.cat_variants
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- price books and prices

-- COM-02-R02's seven dimensions, as columns rather than as a rule language: brand, location,
-- channel, currency, tax regime, customer segment and an effective window. Columns because the
-- resolver has to match on them deterministically and explain the match, and a rule language
-- would make both harder without buying anything the seven named dimensions need.
CREATE TABLE plt01.cat_price_books (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    price_book_id uuid NOT NULL DEFAULT gen_random_uuid(),
    price_book_key text NOT NULL,
    display_name text NOT NULL,
    currency char(3) NOT NULL,
    brand_id uuid,
    location_id uuid,
    -- Where the sale happens. `any` is the wildcard, written as a value rather than as NULL so
    -- the resolver's specificity ordering has something total to sort on.
    channel text NOT NULL DEFAULT 'any',
    customer_segment text NOT NULL DEFAULT 'any',
    tax_category_id uuid,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    -- Higher wins when two books match equally well. The resolver explains which it used.
    priority integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'draft',
    -- **Activating a book is what makes every price in it live**, so it names who did it. The
    -- first version had no such columns, while `cat_products.published_by`,
    -- `cat_promotions.activated_by` and `cat_coupons.revoked_by` all existed beside it --
    -- and `activate_price_book` took an actor and a correlation id and wrote neither.
    activated_at timestamptz,
    activated_by uuid,
    activate_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, price_book_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id) REFERENCES plt01.locations (tenant_id, location_id),
    FOREIGN KEY (tenant_id, tax_category_id)
        REFERENCES plt01.cat_tax_categories (tenant_id, tax_category_id),
    UNIQUE (tenant_id, price_book_key),
    CONSTRAINT cat_price_books_key_shape
        CHECK (price_book_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT cat_price_books_name_not_blank CHECK (length(btrim(display_name)) > 0),
    CONSTRAINT cat_price_books_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT cat_price_books_channel CHECK (channel IN (
        'any', 'pos', 'member_app', 'admin_web', 'crm', 'kiosk', 'web')),
    CONSTRAINT cat_price_books_segment_shape
        CHECK (customer_segment ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT cat_price_books_status CHECK (status IN ('draft', 'active', 'retired')),
    CONSTRAINT cat_price_books_window
        CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT cat_price_books_priority_sane CHECK (priority BETWEEN -1000 AND 1000),
    CONSTRAINT cat_price_books_activation_attributed CHECK (
        (activated_at IS NULL AND activated_by IS NULL
         AND activate_correlation_id IS NULL)
        OR (activated_at IS NOT NULL AND activated_by IS NOT NULL
            AND activate_correlation_id IS NOT NULL)),
    CONSTRAINT cat_price_books_active_is_activated
        CHECK (status <> 'active' OR activated_at IS NOT NULL)
);
CREATE INDEX cat_price_books_matching
    ON plt01.cat_price_books (tenant_id, status, currency, effective_from);
ALTER TABLE plt01.cat_price_books ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_price_books FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_price_books_tenant ON plt01.cat_price_books
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **COM-02-R07, as a privilege.** "Versioned price changes that do not rewrite historical
-- transactions": this table carries no UPDATE grant for any runtime role at all, so a price
-- cannot be edited -- re-pricing is a new row with a later `effective_from`, and the superseded
-- row keeps its window. An order resolved last March re-derives from the rows that were in
-- force then, which is the only way paragraph 4076's immutable line snapshot is true of
-- anything. Withdrawing a price before it takes effect is a `superseded_by` pointer, which is
-- the one column that moves.
CREATE TABLE plt01.cat_prices (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    price_id uuid NOT NULL DEFAULT gen_random_uuid(),
    price_book_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    -- Integer minor units, as everything in this build is. Zero is a real price -- a free trial
    -- variant -- and negative is not.
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    superseded_by uuid,
    -- Withdrawing a price is a price change, so it names who. `supersede_price` took an actor
    -- and a correlation id and recorded neither, and published no event either.
    superseded_at timestamptz,
    superseded_by_actor uuid,
    supersede_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, price_id),
    FOREIGN KEY (tenant_id, price_book_id)
        REFERENCES plt01.cat_price_books (tenant_id, price_book_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, superseded_by) REFERENCES plt01.cat_prices (tenant_id, price_id),
    CONSTRAINT cat_prices_amount_not_negative CHECK (amount_minor >= 0),
    -- Bounded well inside `bigint`, so an absurd figure is a 422 rather than an overflow
    -- reaching the caller as a 500. MOD-011 and MOD-012 each shipped that once.
    CONSTRAINT cat_prices_amount_sane CHECK (amount_minor <= 1000000000000),
    CONSTRAINT cat_prices_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT cat_prices_window CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT cat_prices_not_self CHECK (superseded_by IS NULL OR superseded_by <> price_id),
    CONSTRAINT cat_prices_supersession_attributed CHECK (
        (superseded_by IS NULL AND superseded_at IS NULL
         AND superseded_by_actor IS NULL AND supersede_correlation_id IS NULL)
        OR (superseded_by IS NOT NULL AND superseded_at IS NOT NULL
            AND superseded_by_actor IS NOT NULL
            AND supersede_correlation_id IS NOT NULL))
);
-- A resolution cites a price *and* the book it priced from, and this is what lets the database
-- insist the two agree -- `cat_price_resolutions` carries a composite foreign key against it.
-- Without one, a stored receipt could name a book that does not contain the price beside it.
CREATE UNIQUE INDEX cat_prices_by_book
    ON plt01.cat_prices (tenant_id, price_book_id, price_id);
-- One price per variant per book per start instant. Two would make the resolution depend on
-- which row the planner returned first, and "deterministic" is the requirement.
CREATE UNIQUE INDEX cat_prices_one_per_start
    ON plt01.cat_prices (tenant_id, price_book_id, variant_id, effective_from);
CREATE INDEX cat_prices_lookup
    ON plt01.cat_prices (tenant_id, variant_id, price_book_id, effective_from DESC);
ALTER TABLE plt01.cat_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_prices FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_prices_tenant ON plt01.cat_prices
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- promotions and coupons

-- COM-02-R04's five kinds in one table, because they differ in how they are *reached* rather
-- than in what they do: an automatic promotion applies itself, a coupon is reached by a code, a
-- corporate rate and a member tier by a segment, a staff discount by a role. The discount
-- arithmetic is identical, so splitting them into five tables would mean five copies of the
-- stacking rules.
CREATE TABLE plt01.cat_promotions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    promotion_id uuid NOT NULL DEFAULT gen_random_uuid(),
    promotion_key text NOT NULL,
    display_name text NOT NULL,
    promotion_kind text NOT NULL,
    -- Exactly one of the two is set, which the constraint below enforces: a promotion is a
    -- percentage or a fixed amount and never both, because a reader of a receipt has to be able
    -- to say which.
    percent_bp integer,
    amount_minor bigint,
    currency char(3),
    -- **Stacking, COM-02-R05.** Two promotions in one group cannot both apply; across groups
    -- they combine. `priority` orders them, and the resolver's sort is total so the answer does
    -- not depend on the planner.
    stacking_group text NOT NULL DEFAULT 'default',
    priority integer NOT NULL DEFAULT 0,
    -- **Approval threshold, COM-02-R05.** A resolution whose total discount reaches this needs
    -- a recorded approval; zero means none is ever required.
    approval_threshold_bp integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'draft',
    activated_at timestamptz,
    activated_by uuid,
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, promotion_id),
    UNIQUE (tenant_id, promotion_key),
    CONSTRAINT cat_promotions_key_shape
        CHECK (promotion_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT cat_promotions_name_not_blank CHECK (length(btrim(display_name)) > 0),
    CONSTRAINT cat_promotions_kind CHECK (promotion_kind IN (
        'automatic', 'coupon', 'corporate_rate', 'member_tier', 'staff_discount', 'manual')),
    -- A percentage or an amount, never both and never neither.
    CONSTRAINT cat_promotions_one_discount_shape
        CHECK ((percent_bp IS NULL) <> (amount_minor IS NULL)),
    -- A fixed amount carries its currency, and a percentage does not: a percentage is
    -- currency-agnostic and a currency on one would read as a restriction nobody applies.
    CONSTRAINT cat_promotions_amount_has_currency
        CHECK ((amount_minor IS NULL) = (currency IS NULL)),
    CONSTRAINT cat_promotions_currency_shape
        CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
    -- **A discount cannot exceed the price**, which is what a percentage above 100% would mean.
    CONSTRAINT cat_promotions_percent_range
        CHECK (percent_bp IS NULL OR percent_bp BETWEEN 1 AND 10000),
    CONSTRAINT cat_promotions_amount_positive
        CHECK (amount_minor IS NULL OR (amount_minor > 0 AND amount_minor <= 1000000000000)),
    CONSTRAINT cat_promotions_group_shape
        CHECK (stacking_group ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT cat_promotions_priority_sane CHECK (priority BETWEEN -1000 AND 1000),
    CONSTRAINT cat_promotions_threshold_range
        CHECK (approval_threshold_bp BETWEEN 0 AND 10000),
    CONSTRAINT cat_promotions_status CHECK (status IN ('draft', 'active', 'ended')),
    CONSTRAINT cat_promotions_activation_attributed CHECK (
        (activated_at IS NULL AND activated_by IS NULL)
        OR (activated_at IS NOT NULL AND activated_by IS NOT NULL)),
    CONSTRAINT cat_promotions_active_is_activated
        CHECK (status <> 'active' OR activated_at IS NOT NULL),
    CONSTRAINT cat_promotions_window
        CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX cat_promotions_applicable
    ON plt01.cat_promotions (tenant_id, status, effective_from);
ALTER TABLE plt01.cat_promotions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_promotions FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_promotions_tenant ON plt01.cat_promotions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- COM-02-R05's eligibility, as rows rather than as an expression language. One row is one
-- condition and the resolver explains each by name, which is the half an expression language
-- loses: "this promotion did not apply" is useless at a counter, and "minimum spend of 50.00
-- not met, subtotal was 40.00" is not.
CREATE TABLE plt01.cat_eligibility_rules (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    rule_id uuid NOT NULL DEFAULT gen_random_uuid(),
    promotion_id uuid NOT NULL,
    -- There is no separate domain CHECK on this column, deliberately. `operand_matches_kind`
    -- below names all seven kinds, so any eighth value fails it -- which made a domain CHECK
    -- beside it untestable: every mutation that would violate the domain violates the
    -- operand constraint too, so the case passed on the sibling's refusal and kept passing
    -- with the domain CHECK dropped. MOD-014's compound-CHECK finding; the repair is one
    -- constraint rather than two, since the one that remains is the stronger statement.
    rule_kind text NOT NULL,
    -- One of these carries the rule's operand, depending on the kind. Separate typed columns
    -- rather than one text field, so a constraint can shape each and a sweep can read them.
    amount_minor bigint,
    quantity integer,
    text_value text,
    date_from date,
    date_to date,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, rule_id),
    FOREIGN KEY (tenant_id, promotion_id)
        REFERENCES plt01.cat_promotions (tenant_id, promotion_id),
    CONSTRAINT cat_eligibility_rules_amount_positive
        CHECK (amount_minor IS NULL OR (amount_minor > 0 AND amount_minor <= 1000000000000)),
    CONSTRAINT cat_eligibility_rules_quantity_positive
        CHECK (quantity IS NULL OR (quantity > 0 AND quantity <= 1000000)),
    CONSTRAINT cat_eligibility_rules_text_not_blank
        CHECK (text_value IS NULL OR length(btrim(text_value)) > 0),
    CONSTRAINT cat_eligibility_rules_dates_ordered
        CHECK (date_from IS NULL OR date_to IS NULL OR date_to >= date_from),
    -- **Each kind carries the operand it needs and no other.** A rule with the wrong operand is
    -- a rule the evaluator reads as vacuous, which is the direction that silently grants a
    -- discount nobody meant to give.
    CONSTRAINT cat_eligibility_rules_operand_matches_kind CHECK (
        (rule_kind = 'minimum_spend' AND amount_minor IS NOT NULL AND quantity IS NULL
         AND text_value IS NULL AND date_from IS NULL)
        OR (rule_kind IN ('customer_segment', 'product_type', 'channel')
            AND text_value IS NOT NULL AND amount_minor IS NULL AND quantity IS NULL
            AND date_from IS NULL)
        OR (rule_kind = 'blackout_dates' AND date_from IS NOT NULL AND date_to IS NOT NULL
            AND amount_minor IS NULL AND quantity IS NULL AND text_value IS NULL)
        OR (rule_kind IN ('max_total_redemptions', 'max_per_subject')
            AND quantity IS NOT NULL AND amount_minor IS NULL AND text_value IS NULL
            AND date_from IS NULL))
);
CREATE INDEX cat_eligibility_rules_by_promotion
    ON plt01.cat_eligibility_rules (tenant_id, promotion_id, rule_kind);
ALTER TABLE plt01.cat_eligibility_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_eligibility_rules FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_eligibility_rules_tenant ON plt01.cat_eligibility_rules
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- A code that reaches a promotion. Separate from the promotion because one campaign routinely
-- has many codes -- per-partner, per-mailing -- and because a code is the thing that gets
-- leaked, so revoking one must not end the campaign.
CREATE TABLE plt01.cat_coupons (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    coupon_id uuid NOT NULL DEFAULT gen_random_uuid(),
    promotion_id uuid NOT NULL,
    -- Stored uppercase and matched uppercase, so `SAVE10` and `save10` are one code. A code
    -- that depended on how somebody typed it would be a support call per campaign.
    code text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    revoked_at timestamptz,
    revoked_by uuid,
    revoke_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, coupon_id),
    FOREIGN KEY (tenant_id, promotion_id)
        REFERENCES plt01.cat_promotions (tenant_id, promotion_id),
    UNIQUE (tenant_id, code),
    CONSTRAINT cat_coupons_code_shape CHECK (code ~ '^[A-Z0-9][A-Z0-9_-]{2,31}$'),
    CONSTRAINT cat_coupons_status CHECK (status IN ('active', 'revoked')),
    -- A revocation carries who, when and why, or none of them -- and the `coalesce` is
    -- load-bearing, because a CHECK passes on NULL and this build has paid for that four times.
    CONSTRAINT cat_coupons_revocation_attributed CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)
        OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
            AND length(btrim(coalesce(revoke_reason, ''))) > 0)),
    CONSTRAINT cat_coupons_revoked_is_attributed
        CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))
);
ALTER TABLE plt01.cat_coupons ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_coupons FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_coupons_tenant ON plt01.cat_coupons
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **Insert-only, and the usage limits are counted from it.** A `times_redeemed` column on the
-- coupon would be a second copy of the truth that can disagree with the ledger beside it --
-- MOD-011's argument against a metric that duplicates a table -- and it would also be the row
-- two concurrent redemptions contend on.
--
-- **What makes the counting safe is a lock on the coupon, not the unique index below.** An
-- earlier version of this comment claimed the index did it; the index is on the idempotency
-- key, which makes a *retry* free and says nothing about two distinct sales. A reviewer ran six
-- concurrent redemptions of a single-use code from a barrier and four were accepted. The
-- service now takes `FOR UPDATE` on the coupon row before it counts, which serialises every
-- redemption of that code and nothing else.
CREATE TABLE plt01.cat_coupon_redemptions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    redemption_id uuid NOT NULL DEFAULT gen_random_uuid(),
    coupon_id uuid NOT NULL,
    promotion_id uuid NOT NULL,
    -- Who redeemed it. A `person_id` from MOD-014 where there is one, and no foreign key: a
    -- coupon is routinely redeemed by somebody who is not yet a person record, which is most of
    -- what a coupon is for.
    subject_id uuid,
    -- What the redemption was against, so a reversal can find it. Free of a foreign key for the
    -- same reason `evt_outbox` has none: the order plane is COM-01's and is not built.
    order_reference text,
    -- The caller's own handle, which is what makes a retry free.
    idempotency_key text NOT NULL,
    -- Computed by the service from the promotion and the sale, never supplied: the first
    -- version took it from the request body, so this ledger recorded whatever figure the
    -- caller typed in a table with no UPDATE grant and therefore no correction path.
    discount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- The resolution this redemption discounted, where the sale went through this module's
    -- pricing. Nullable because `redeem_coupon` exists for a caller with its own subtotal, and
    -- no foreign key would be satisfiable then.
    resolution_id uuid,
    redeemed_at timestamptz NOT NULL DEFAULT now(),
    redeemed_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, redemption_id),
    FOREIGN KEY (tenant_id, coupon_id) REFERENCES plt01.cat_coupons (tenant_id, coupon_id),
    FOREIGN KEY (tenant_id, promotion_id)
        REFERENCES plt01.cat_promotions (tenant_id, promotion_id),
    -- One redemption per idempotency key, which is what stops a retried POS request taking a
    -- second use off a single-use coupon.
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT cat_coupon_redemptions_discount_positive
        CHECK (discount_minor > 0 AND discount_minor <= 1000000000000),
    CONSTRAINT cat_coupon_redemptions_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT cat_coupon_redemptions_key_not_blank
        CHECK (length(btrim(idempotency_key)) > 0),
    CONSTRAINT cat_coupon_redemptions_reference_not_blank
        CHECK (order_reference IS NULL OR length(btrim(order_reference)) > 0)
);
CREATE INDEX cat_coupon_redemptions_by_coupon
    ON plt01.cat_coupon_redemptions (tenant_id, coupon_id, redeemed_at DESC);
CREATE INDEX cat_coupon_redemptions_by_subject
    ON plt01.cat_coupon_redemptions (tenant_id, coupon_id, subject_id)
    WHERE subject_id IS NOT NULL;
ALTER TABLE plt01.cat_coupon_redemptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_coupon_redemptions FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_coupon_redemptions_tenant ON plt01.cat_coupon_redemptions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- bundles

-- COM-02-R03: a bundle links a commercial sale to operational fulfilment and entitlements. It
-- is a product in its own right -- it has a key, a price and a place in the listing -- and it
-- owes a set of items when it is sold.
CREATE TABLE plt01.cat_bundles (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    bundle_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The product this bundle is sold as, so a bundle is priced through the same books as
    -- everything else rather than through a second pricing path.
    product_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, bundle_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES plt01.cat_products (tenant_id, product_id),
    -- One bundle definition per product. Two would make "what does this sale owe" ambiguous at
    -- the moment somebody has already paid.
    UNIQUE (tenant_id, product_id),
    CONSTRAINT cat_bundles_status CHECK (status IN ('draft', 'active', 'retired')),
    CONSTRAINT cat_bundles_version_positive CHECK (version >= 1)
);
ALTER TABLE plt01.cat_bundles ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_bundles FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_bundles_tenant ON plt01.cat_bundles
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.cat_bundle_items (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    bundle_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    quantity integer NOT NULL DEFAULT 1,
    -- What delivering this item means, for the module that will deliver it. Named rather than
    -- inferred from the product type, because a membership sold inside a bundle may be a grant
    -- rather than an agreement and only the person composing the bundle knows which.
    fulfilment_kind text NOT NULL,
    -- Attributed like every other insert-only row in this module. This was the only one
    -- without an actor, beside a fulfilment table that argues at length for having one.
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, bundle_id, variant_id),
    FOREIGN KEY (tenant_id, bundle_id) REFERENCES plt01.cat_bundles (tenant_id, bundle_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    CONSTRAINT cat_bundle_items_quantity_positive
        CHECK (quantity > 0 AND quantity <= 1000),
    CONSTRAINT cat_bundle_items_fulfilment_kind CHECK (fulfilment_kind IN (
        'entitlement_grant', 'membership_agreement', 'physical_goods', 'digital_delivery',
        'booking_credit'))
);
ALTER TABLE plt01.cat_bundle_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_bundle_items FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_bundle_items_tenant ON plt01.cat_bundle_items
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **What somebody says was delivered, with their name on it.** Nothing in this build fulfils
-- anything: COM-01's entitlement grants and OPS-01's bookings are not written. So this is the
-- ledger whatever does the fulfilling writes to, insert-only, and a row saying "delivered" that
-- no fulfilment produced is the fabricated-evidence shape this codebase has been bitten by five
-- times -- which is why the actor and the correlation are NOT NULL rather than optional.
CREATE TABLE plt01.cat_bundle_fulfilments (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    fulfilment_id uuid NOT NULL DEFAULT gen_random_uuid(),
    bundle_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    order_reference text NOT NULL,
    subject_id uuid,
    quantity integer NOT NULL,
    outcome text NOT NULL,
    -- The caller's own handle, which is what makes a retry free -- and which is the whole of
    -- what the removed `UNIQUE (tenant_id, order_reference, bundle_id, variant_id)` was
    -- actually providing. That index said "one record per item per order", which both
    -- `bundles.outstanding` and `bundles.check_fulfilment` contradicted: they count only
    -- `delivered` rows and sum partial deliveries, neither of which it allowed. So a
    -- transient provider failure recorded `failed` and the retry was refused for ever -- no
    -- UPDATE grant, no DELETE grant, no second row permitted -- leaving a member who had paid
    -- with an obligation no call in the module could satisfy.
    idempotency_key text NOT NULL,
    -- What the fulfilling module produced, so the two sides can be reconciled. No foreign key:
    -- the modules that would be referenced are not built.
    external_reference text,
    detail text,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, fulfilment_id),
    FOREIGN KEY (tenant_id, bundle_id, variant_id)
        REFERENCES plt01.cat_bundle_items (tenant_id, bundle_id, variant_id),
    -- One record per handle. Over-delivery is refused by the arithmetic in
    -- `bundles.check_fulfilment`, which is where it belongs: it is a sum against what the sale
    -- owes, and no index can express that.
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT cat_bundle_fulfilments_quantity_positive
        CHECK (quantity > 0 AND quantity <= 1000),
    -- `reversed` subtracts, and it is the only correction path there is: this table has no
    -- UPDATE and no DELETE grant, so a delivery recorded in error was otherwise permanent.
    -- MOD-015's credit note, applied to an obligation -- and the reason
    -- `catalog.bundle.fulfil` can be `financial` without being irreversible, which is
    -- MOD-013's rule that irreversible state must not be declarable.
    CONSTRAINT cat_bundle_fulfilments_outcome
        CHECK (outcome IN ('delivered', 'failed', 'cancelled', 'reversed')),
    CONSTRAINT cat_bundle_fulfilments_reference_not_blank
        CHECK (length(btrim(order_reference)) > 0),
    CONSTRAINT cat_bundle_fulfilments_external_not_blank
        CHECK (external_reference IS NULL OR length(btrim(external_reference)) > 0),
    -- A failure says why. The `coalesce` is load-bearing: a CHECK passes on NULL.
    CONSTRAINT cat_bundle_fulfilments_failure_explained
        CHECK (outcome = 'delivered' OR length(btrim(coalesce(detail, ''))) > 0)
);
ALTER TABLE plt01.cat_bundle_fulfilments ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_bundle_fulfilments FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_bundle_fulfilments_tenant ON plt01.cat_bundle_fulfilments
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- resolutions and approvals

-- **The explanation paragraph 10220 requires, kept.** Insert-only, one row per resolution, with
-- the inputs, the list price, the discount, the final amount and the reasoning as an ordered
-- list of named steps. A resolver that returned a number and no reasoning would be impossible
-- to dispute at a counter, which is exactly where these numbers are read out loud -- and a
-- resolution that was not kept could not be compared against the order that cited it.
CREATE TABLE plt01.cat_price_resolutions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    resolution_id uuid NOT NULL DEFAULT gen_random_uuid(),
    variant_id uuid NOT NULL,
    price_book_id uuid NOT NULL,
    price_id uuid NOT NULL,
    -- The request, snapshotted: the same inputs tomorrow against the same rows give the same
    -- answer, and if they do not, this row says which input moved.
    channel text NOT NULL,
    customer_segment text NOT NULL,
    quantity integer NOT NULL,
    subject_id uuid,
    resolved_at timestamptz NOT NULL,
    -- The arithmetic, in integer minor units throughout.
    list_amount_minor bigint NOT NULL,
    discount_minor bigint NOT NULL,
    final_amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- The reasoning, as ordered named steps rather than prose: one line per promotion that
    -- applied and one per promotion that did not, each with its reason code. `text[]` rather
    -- than `jsonb` for MOD-010's reason -- a sweep matching column names cannot see inside
    -- `jsonb`, and this is the one table a tenant's own campaign names end up in.
    applied_promotions text[] NOT NULL DEFAULT ARRAY[]::text[],
    rejected_promotions text[] NOT NULL DEFAULT ARRAY[]::text[],
    explanation text[] NOT NULL,
    -- Which code the resolver ran, so a changed rule is visible as a changed version rather
    -- than as an unexplained difference in the number.
    policy_version integer NOT NULL,
    -- Set when a manual override was applied, which is the one path that needs an approval.
    approval_id uuid,
    requested_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, resolution_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, price_book_id)
        REFERENCES plt01.cat_price_books (tenant_id, price_book_id),
    -- The price *and* the book it came from, as one reference against `cat_prices_by_book`, so
    -- a stored receipt cannot name a book that does not contain the price beside it. Two
    -- independent references would each be satisfied by a mismatched pair.
    FOREIGN KEY (tenant_id, price_book_id, price_id)
        REFERENCES plt01.cat_prices (tenant_id, price_book_id, price_id),
    CONSTRAINT cat_price_resolutions_quantity_positive
        CHECK (quantity > 0 AND quantity <= 1000000),
    -- Three constraints, each of which can be violated on its own -- which is the only way a
    -- mutation sweep can prove any of them. The first draft wrote
    -- `list >= 0 AND discount >= 0 AND final >= 0` beside the two below, and both of the
    -- others were then untestable: every row with `discount > list` also has `final < 0`
    -- once the arithmetic holds, and every row with `list < 0` also has `discount > list`
    -- once the discount is non-negative. MOD-014's compound-CHECK finding, in this module.
    -- What is left implies the two that went: `list >= discount >= 0`, so `final >= 0`.
    CONSTRAINT cat_price_resolutions_discount_not_negative CHECK (discount_minor >= 0),
    -- **The arithmetic has to add up**, in the row itself. A resolution whose parts do not sum
    -- to its total is the one defect nobody would spot by reading the number.
    CONSTRAINT cat_price_resolutions_adds_up
        CHECK (final_amount_minor = list_amount_minor - discount_minor),
    -- And a discount cannot exceed what is being discounted.
    CONSTRAINT cat_price_resolutions_discount_bounded
        CHECK (discount_minor <= list_amount_minor),
    CONSTRAINT cat_price_resolutions_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT cat_price_resolutions_explained CHECK (cardinality(explanation) > 0),
    CONSTRAINT cat_price_resolutions_policy_version_positive CHECK (policy_version >= 1),
    CONSTRAINT cat_price_resolutions_segment_shape
        CHECK (customer_segment ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    -- The snapshot is only reproducible if every field in it is a value the resolver would
    -- accept. This column was NOT NULL free text with no domain while `cat_price_books.channel`
    -- was constrained to the seven, so a stored resolution could record a channel that is not
    -- one.
    CONSTRAINT cat_price_resolutions_channel CHECK (channel IN (
        'any', 'pos', 'member_app', 'admin_web', 'crm', 'kiosk', 'web'))
);
-- **An approval is spendable once.** The uniqueness lives here, on the citing side, because
-- `cat_discount_approvals` has no UPDATE grant and so cannot be marked consumed -- and a
-- partial index is the whole mechanism, with no column to forget to write. Three reviewers
-- independently showed a one-off goodwill approval being spent five times by the cheapest
-- permission in the module: `_check_approval` verified the variant, the list amount and the
-- depth, and then nothing ever happened to the row.
CREATE UNIQUE INDEX cat_price_resolutions_one_per_approval
    ON plt01.cat_price_resolutions (tenant_id, approval_id)
    WHERE approval_id IS NOT NULL;
CREATE INDEX cat_price_resolutions_by_variant
    ON plt01.cat_price_resolutions (tenant_id, variant_id, resolved_at DESC);
ALTER TABLE plt01.cat_price_resolutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_price_resolutions FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_price_resolutions_tenant ON plt01.cat_price_resolutions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **"Manual price overrides and high discounts require explicit permission and audit."**
-- Insert-only, with the approver, the reason and the amount. The permission is MOD-008's and
-- the audit is this table -- MOD-008 audits denials rather than allowed actions, so without a
-- row here an approved override would be recorded nowhere at all, which is the shape MOD-012's
-- `release_run`, MOD-011's `ops_synthetic_results` and MOD-014's `verify_contact_point` each
-- shipped once.
-- **The request half, which is what makes the separation of duties real.** The first version
-- had only the approvals table and took `requested_by` from the request body -- so the CHECK
-- below compared one derived identity against one the approver typed, and all three reviewers
-- independently demonstrated a single person approving their own override naming a requester
-- who does not exist. A control keyed on a field the caller supplies, shape-checked and never
-- checked for correspondence, is the shape this build has now shipped four times
-- (MOD-009's `guardian_subject_id`, MOD-013's `bypass_policy_ref`, MOD-014's guardian field).
--
-- Collapsing the two acts made the control unverifiable *in principle*, not merely unverified:
-- there was nothing a stricter check could have consulted. MOD-008 has the shape right in
-- `iam.approval_requests` -- one identity asks, another decides, both rows kept.
CREATE TABLE plt01.cat_discount_requests (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    request_id uuid NOT NULL DEFAULT gen_random_uuid(),
    variant_id uuid NOT NULL,
    list_amount_minor bigint NOT NULL,
    override_amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    reason text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    -- Derived from the requester's own session by the route. Nothing accepts this field.
    requested_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, request_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    CONSTRAINT cat_discount_requests_amounts_sane CHECK (
        list_amount_minor > 0 AND list_amount_minor <= 1000000000000
        AND override_amount_minor >= 0 AND override_amount_minor <= list_amount_minor),
    CONSTRAINT cat_discount_requests_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT cat_discount_requests_reason_not_blank CHECK (length(btrim(reason)) > 0)
);
ALTER TABLE plt01.cat_discount_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_discount_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_discount_requests_tenant ON plt01.cat_discount_requests
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.cat_discount_approvals (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    approval_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The request this decides. Every figure on this row is copied from it by the service, so
    -- an approval cannot be issued for terms nobody asked for.
    request_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    -- What was asked for and what it was measured against, so the threshold decision can be
    -- re-derived rather than believed.
    list_amount_minor bigint NOT NULL,
    override_amount_minor bigint NOT NULL,
    discount_bp integer NOT NULL,
    currency char(3) NOT NULL,
    reason text NOT NULL,
    approved_at timestamptz NOT NULL DEFAULT now(),
    -- **An approval expires.** Paragraph 10220 states no window, so the length is a judgement
    -- (`service.APPROVAL_VALID_FOR`) -- but *some* window is required, because the alternative
    -- is a standing authority to sell at that price for ever.
    expires_at timestamptz NOT NULL,
    approved_by uuid NOT NULL,
    -- Copied from the request, never from the body. This is what the CHECK below compares.
    requested_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, approval_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, request_id)
        REFERENCES plt01.cat_discount_requests (tenant_id, request_id),
    -- One decision per request, so a refused-then-reasked discount is a new request.
    UNIQUE (tenant_id, request_id),
    CONSTRAINT cat_discount_approvals_amounts_sane CHECK (
        list_amount_minor > 0 AND list_amount_minor <= 1000000000000
        AND override_amount_minor >= 0 AND override_amount_minor <= list_amount_minor),
    CONSTRAINT cat_discount_approvals_bp_range CHECK (discount_bp BETWEEN 1 AND 10000),
    CONSTRAINT cat_discount_approvals_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT cat_discount_approvals_reason_not_blank CHECK (length(btrim(reason)) > 0),
    -- **An approver cannot approve their own request.** MOD-008's separation of duties, applied
    -- to the one act in this module that lets somebody choose the price.
    CONSTRAINT cat_discount_approvals_approver_is_not_requester
        CHECK (approved_by <> requested_by),
    CONSTRAINT cat_discount_approvals_expires_after_approval
        CHECK (expires_at > approved_at)
);
ALTER TABLE plt01.cat_discount_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.cat_discount_approvals FORCE ROW LEVEL SECURITY;
CREATE POLICY cat_discount_approvals_tenant ON plt01.cat_discount_approvals
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The resolution points at its approval, declared after both tables exist.
ALTER TABLE plt01.cat_price_resolutions
    ADD CONSTRAINT cat_price_resolutions_approval_fkey
    FOREIGN KEY (tenant_id, approval_id)
    REFERENCES plt01.cat_discount_approvals (tenant_id, approval_id);

-- ---------------------------------------------------------------- privileges

GRANT SELECT, INSERT ON plt01.cat_tax_categories TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, jurisdiction_note, retired_at) ON plt01.cat_tax_categories
    TO veyro_cp_app, veyro_cp_worker;

-- A product's *type* carries no UPDATE grant. Changing it re-routes fulfilment for everything
-- already sold -- a membership that becomes a retail SKU is an agreement nobody will honour --
-- and the key is what every integration and every export refers to.
GRANT SELECT, INSERT ON plt01.cat_products TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (tax_category_id, status, brand_id, merchandising_rank, version, published_at,
              published_by, retired_at, retired_by, retire_correlation_id, updated_at)
    ON plt01.cat_products TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.cat_product_texts TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, description, terms, updated_at, updated_by, correlation_id)
    ON plt01.cat_product_texts TO veyro_cp_app, veyro_cp_worker;

-- A variant's `product_id` and `variant_key` do not move, for the same reason.
GRANT SELECT, INSERT ON plt01.cat_variants TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, entitlement_quantity, term_days, sku, status,
              merchandising_rank, version, updated_at)
    ON plt01.cat_variants TO veyro_cp_app, veyro_cp_worker;

-- A price book's *dimensions* do not move either: changing the currency or the segment of a
-- book that prices have been written into would silently re-aim every one of them -- and
-- `priority` and `effective_to` are dimensions by that test, which is why they are no longer
-- in this grant. `priority` is a matching input in `choose_book` and `effective_to` is what
-- closes the book, so either one re-aims every price already written into it. Nothing in the
-- service ever wrote them; they were granted and unused, which is how a control that reads as
-- deliberate turns out to be neither. Closing a book is a new book plus a supersession, on the
-- same terms as re-pricing.
GRANT SELECT, INSERT ON plt01.cat_price_books TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, status, activated_at, activated_by, activate_correlation_id)
    ON plt01.cat_price_books TO veyro_cp_app, veyro_cp_worker;

-- **COM-02-R07 as a privilege: a price carries no UPDATE on any figure it states.** Only the
-- supersession columns move, so re-pricing is a new row and an order resolved last March still
-- re-derives. `effective_to` used to be in this grant, which made the claim above false while
-- it was written three times over in this file: `effective_to` is the column whose value
-- decides whether a price is in force, so granting UPDATE on it is granting the power to
-- withdraw a price with no record of who did it. Nothing in the service wrote it. Withdrawal
-- is `superseded_by`, which is attributed.
GRANT SELECT, INSERT ON plt01.cat_prices TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (superseded_by, superseded_at, superseded_by_actor, supersede_correlation_id)
    ON plt01.cat_prices TO veyro_cp_app, veyro_cp_worker;

-- A promotion's discount shape and its stacking do not move once it is active: a campaign that
-- could be re-pointed after the fact would make every resolution citing it unexplainable.
GRANT SELECT, INSERT ON plt01.cat_promotions TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (display_name, status, activated_at, activated_by, effective_to)
    ON plt01.cat_promotions TO veyro_cp_app, veyro_cp_worker;
-- An eligibility rule is insert-only in full. Editing one changes what a past resolution would
-- have decided, which is the thing the resolution snapshot exists to make answerable.
GRANT SELECT, INSERT ON plt01.cat_eligibility_rules TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.cat_coupons TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, revoked_at, revoked_by, revoke_reason) ON plt01.cat_coupons
    TO veyro_cp_app, veyro_cp_worker;
-- Insert-only: a redemption happened, and the usage limits are counted from these rows.
GRANT SELECT, INSERT ON plt01.cat_coupon_redemptions TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.cat_bundles TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (status, version) ON plt01.cat_bundles TO veyro_cp_app, veyro_cp_worker;
-- A bundle's composition is insert-only: what a sale owed is what it owed on the day.
GRANT SELECT, INSERT ON plt01.cat_bundle_items TO veyro_cp_app, veyro_cp_worker;
-- And what was delivered is evidence, so it is insert-only in full.
GRANT SELECT, INSERT ON plt01.cat_bundle_fulfilments TO veyro_cp_app, veyro_cp_worker;

-- **The explanation is insert-only in full.** A resolution that could be edited afterwards
-- would be a receipt somebody can rewrite, which is the opposite of what paragraph 10220 asks
-- the explanation to be for.
GRANT SELECT, INSERT ON plt01.cat_price_resolutions TO veyro_cp_app, veyro_cp_worker;
-- As is the request that asked for an override, and the approval that permitted it. Neither
-- carries an UPDATE grant on anything: the request states what was asked and the approval
-- states what was decided, and single use is enforced by a unique index on the resolution
-- that cites the approval rather than by a column here that could be forgotten.
GRANT SELECT, INSERT ON plt01.cat_discount_requests TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.cat_discount_approvals TO veyro_cp_app, veyro_cp_worker;
