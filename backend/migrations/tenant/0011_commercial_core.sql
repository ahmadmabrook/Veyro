-- MOD-017, COM-01 and COM-03: the commercial agreement a member signs, the operational rights
-- it grants, and the money it generates. Twenty-two tables in two families, every one
-- tenant-scoped under the forced row-level security every `plt01` table obeys.
--
-- **`mem_` is what a member is entitled to; `fin_` is what they owe.** The TSD keeps them
-- apart on purpose and paragraph 1496 says why in one line: "membership state, billing state
-- and access state are related but never conflated." A frozen membership is not an unpaid one;
-- an unpaid invoice does not by itself revoke access; and whether somebody may train right now
-- is a question only `mem_entitlement_grants` answers. Three states, three tables, three
-- lifecycles. Collapsing any pair is the defect this module exists to avoid.
--
-- The prefix is `fin_` rather than `bil_` because `bil_` is MOD-015: Veyro billing the tenant
-- for its subscription. This is the tenant billing its own members. The two never join, they
-- are counted in different currencies to different parties, and one name for both would be an
-- invitation to add the join later.
--
-- Nine decisions are specific to this module.
--
--   * **A grant is the fulfilment authority and a reservation is atomic.** Paragraph 1506:
--     "MemberEntitlementGrant is the fulfillment authority. Reservation is atomic and
--     expiring." So a reservation is a row with an expiry, taken under a lock on the grant, and
--     the grant's remaining quantity is derived from an insert-only movement ledger rather than
--     stored in a column two concurrent bookings would race on. MOD-016's coupon ledger learned
--     this the hard way: counting and then inserting is a race, and the fix is the lock.
--
--   * **Every movement is a row, and a correction is another row.** `mem_entitlement_ledger`
--     has no UPDATE and no DELETE grant: a grant, a reservation, a consumption, a release, a
--     revocation and an expiry are each an insert, and the balance is their sum. That is
--     MOD-015's credit note and MOD-016's fulfilment reversal applied to access rights, and it
--     is what makes "may this member train now" answerable as of any past instant.
--
--   * **The lifecycle is effective-dated and insert-only.** COM-01-R07 asks for "full state
--     history and as-of reconstruction for disputes and audits", so `mem_lifecycle_changes`
--     records what changed, when it takes effect, who decided it and why -- and the current
--     state on `mem_memberships` is a cache of the latest effective change, not the only copy.
--     A dispute is argued from the history.
--
--   * **An invoice's fiscal state is separate from its payment state.** Paragraph 1607 is
--     explicit, and it names the Jordan case: "Jordan final tax invoice requires server serial
--     + JoFotara acknowledgement before FISCAL_COMPLETE." So `fin_invoices` carries two
--     independent status columns, and neither transition implies the other. An invoice can be
--     paid and not fiscalized, or fiscalized and unpaid.
--
--   * **A fiscal serial is allocated once, in order, per series.** COM-03-R07 and paragraph
--     1606: "fiscal series+serial uniqueness per legal entity." The serial comes from a
--     counter row taken under `FOR UPDATE`, because two invoices sharing a serial is a tax
--     offence rather than a bug, and a gap in the sequence is one a tax authority asks about.
--
--   * **No card data, and the locator columns are shaped so one will not fit.** Paragraph
--     1597: "sensitive card data never enters Veyro systems unless explicitly certified."
--     There is no PAN column, no expiry column and no CVV column -- the same shape MOD-012
--     uses for `vault_ref`, where the control is an *absence* and a later migration adding one
--     back is what the column-list pin exists to catch. **But an absence is only half of it**,
--     and the first version of this file claimed the whole: `payment_method_ref` was non-blank
--     text a caller supplies, so a reviewer stored a sixteen-digit number with an expiry in
--     it, in a table with that paragraph quoted ten lines above. This is MOD-012's own
--     `vault_ref` finding and MOD-010's "the restricted-field rule checks names, and a value
--     can carry anything", for the third time. `payment_method_ref`, `evidence_ref` and
--     `signature_evidence_ref` now have to look like a URI-shaped locator, which no card
--     number does.
--
--   * **Money is an integer count of minor units, and `app.billing.money` owns the
--     arithmetic.** Imported, never reimplemented: MOD-015 chose half-away-from-zero rounding
--     and largest-remainder allocation and wrote down why, and a second rounding rule in one
--     build is a pair of numbers that disagree on a receipt. MOD-016 shipped that second rule
--     once and a reviewer found it.
--
--   * **An unknown provider state fails closed and is persisted.** Paragraph 1609: "Fail
--     consequence-bearing writes closed on unknown provider/ledger state; persist PENDING
--     explicitly." So `unknown` is a real status a payment can hold, it is terminal until
--     something reconciles it, and nothing downstream treats it as either success or failure.
--
--   * **Nothing here takes money.** There is no provider, no outbound HTTP and no stored
--     payment method, because real financial expenditure is owner-reserved. What is built is
--     the half that must be correct whatever the provider turns out to be: the intent, the
--     idempotency, the reconciliation, the ledger and the fiscal sequence. A module that wrote
--     "captured" into a row while charging nobody is the fabricated-evidence shape this
--     codebase has been bitten by five times.

-- ---------------------------------------------------------------- contracts and agreements

-- COM-01-R02's contract terms, versioned. A published version is immutable by privilege: the
-- terms a member agreed to on the fourteenth have to still read the same a year later, which
-- is the whole reason a signature means anything. Re-wording is a new version; agreements
-- already signed keep pointing at the one they were signed against.
CREATE TABLE plt01.mem_contract_versions (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    contract_version_id uuid NOT NULL DEFAULT gen_random_uuid(),
    contract_key text NOT NULL,
    version integer NOT NULL,
    -- The terms themselves. Tenant-authored prose, so it is residue an erasure cannot reach
    -- and is declared as such -- a member's name in a bespoke clause is the realistic case.
    body text NOT NULL,
    locale text NOT NULL DEFAULT 'en',
    -- COM-01-R02's policy, as data rather than as prose, because the lifecycle arithmetic
    -- reads it. The prose above is what the member agreed; these are what the system enforces,
    -- and `check_contract` refuses a version whose two halves could not both be true.
    minimum_term_months integer NOT NULL DEFAULT 0,
    notice_days integer NOT NULL DEFAULT 0,
    renewal_mode text NOT NULL DEFAULT 'manual',
    cancellation_mode text NOT NULL DEFAULT 'end_of_term',
    -- How much freezing the contract allows, which COM-01-R04 needs and R05 prices.
    freeze_days_per_year integer NOT NULL DEFAULT 0,
    grace_days integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'draft',
    published_at timestamptz,
    published_by uuid,
    publish_correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, contract_version_id),
    UNIQUE (tenant_id, contract_key, version),
    CONSTRAINT mem_contract_versions_key_shape
        CHECK (contract_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT mem_contract_versions_version_positive CHECK (version >= 1),
    CONSTRAINT mem_contract_versions_body_not_blank CHECK (body ~ '[^[:space:]]'),
    CONSTRAINT mem_contract_versions_locale CHECK (locale ~ '^[a-z]{2}(-[A-Z]{2})?$'),
    CONSTRAINT mem_contract_versions_status CHECK (status IN ('draft', 'published', 'retired')),
    CONSTRAINT mem_contract_versions_renewal_mode
        CHECK (renewal_mode IN ('manual', 'automatic', 'none')),
    CONSTRAINT mem_contract_versions_cancellation_mode
        CHECK (cancellation_mode IN ('immediate', 'end_of_notice', 'end_of_term')),
    CONSTRAINT mem_contract_versions_term_sane
        CHECK (minimum_term_months BETWEEN 0 AND 120),
    CONSTRAINT mem_contract_versions_notice_sane CHECK (notice_days BETWEEN 0 AND 365),
    CONSTRAINT mem_contract_versions_freeze_sane
        CHECK (freeze_days_per_year BETWEEN 0 AND 365),
    CONSTRAINT mem_contract_versions_grace_sane CHECK (grace_days BETWEEN 0 AND 180),
    -- Publication names who and when, or nothing does: MOD-008 audits denials rather than
    -- allowed actions and `veyro_cp_app` holds nothing in `iam`, so this row is the only
    -- record there can be. Four modules have now shipped the version without it.
    CONSTRAINT mem_contract_versions_publication_attributed CHECK (
        (published_at IS NULL AND published_by IS NULL AND publish_correlation_id IS NULL)
        OR (published_at IS NOT NULL AND published_by IS NOT NULL
            AND publish_correlation_id IS NOT NULL)),
    CONSTRAINT mem_contract_versions_published_is_attributed
        CHECK (status <> 'published' OR published_at IS NOT NULL),
    -- **The author of a contract does not publish it.** This is the prose a member is held to
    -- and the policy numbers the lifecycle enforces, and it goes out under the tenant's name
    -- to everybody who signs on these terms -- which is MOD-013's separation of duties on
    -- template content, applied to the document with legal effect. Enforced here rather than
    -- in the service because the service's choice of SQL is not the writer this constraint
    -- exists for.
    CONSTRAINT mem_contract_versions_publisher_is_not_author
        CHECK (published_by IS NULL OR published_by <> created_by)
);
ALTER TABLE plt01.mem_contract_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_contract_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_contract_versions_tenant ON plt01.mem_contract_versions
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The membership-specific policy attached to a catalogue product. **MOD-016 owns what a thing
-- is and what it costs; this owns the contract terms it is sold under.** The TSD lists
-- MembershipProduct among COM-01's authoritative entities and `cat_products` already carries a
-- `membership` type, so the honest split is by question rather than by name: the catalogue
-- answers "what is for sale and at what price", and this answers "and on what terms". A second
-- product table would be two copies of the same thing able to disagree.
CREATE TABLE plt01.mem_membership_terms (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    membership_terms_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The catalogue product this is the terms for. A composite reference, so the product
    -- cannot belong to another tenant.
    product_id uuid NOT NULL,
    contract_key text NOT NULL,
    -- COM-01-R01's ten membership shapes. A shape decides which lifecycle edges exist and how
    -- the billing schedule is built, which is why it is a domain rather than free text.
    membership_kind text NOT NULL,
    billing_period text NOT NULL DEFAULT 'monthly',
    -- For an installment plan, how many; for prepaid, how long the prepayment covers.
    installment_count integer,
    prepaid_days integer,
    -- Off-peak memberships are entitled only inside a window, which the grant's scope carries;
    -- this is the declaration that there is one.
    is_off_peak boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'draft',
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, membership_terms_id),
    FOREIGN KEY (tenant_id, product_id) REFERENCES plt01.cat_products (tenant_id, product_id),
    -- One set of terms per product. Two would make "what did this member sign up to" ambiguous
    -- at the moment they have already signed.
    UNIQUE (tenant_id, product_id),
    CONSTRAINT mem_membership_terms_contract_key_shape
        CHECK (contract_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    -- COM-01-R01 in full. An eleventh shape is a product decision, not a migration.
    CONSTRAINT mem_membership_terms_kind CHECK (membership_kind IN (
        'fixed_term', 'recurring', 'installment', 'prepaid', 'off_peak', 'family',
        'student', 'corporate', 'class_credit', 'unlimited')),
    CONSTRAINT mem_membership_terms_billing_period CHECK (billing_period IN (
        'weekly', 'monthly', 'quarterly', 'annual', 'one_off')),
    CONSTRAINT mem_membership_terms_status
        CHECK (status IN ('draft', 'active', 'retired')),
    CONSTRAINT mem_membership_terms_version_positive CHECK (version >= 1),
    CONSTRAINT mem_membership_terms_installments_sane
        CHECK (installment_count IS NULL
               OR (installment_count >= 2 AND installment_count <= 120)),
    CONSTRAINT mem_membership_terms_prepaid_sane
        CHECK (prepaid_days IS NULL OR (prepaid_days >= 1 AND prepaid_days <= 3650)),
    -- **An installment plan has a count and nothing else does.** A count on a recurring
    -- membership is a field the schedule builder would read and nobody set deliberately,
    -- which is MOD-016's operand-matches-kind rule applied to a plan shape.
    CONSTRAINT mem_membership_terms_installments_match_kind
        CHECK ((membership_kind = 'installment') = (installment_count IS NOT NULL)),
    CONSTRAINT mem_membership_terms_prepaid_match_kind
        CHECK ((membership_kind = 'prepaid') = (prepaid_days IS NOT NULL)),
    CONSTRAINT mem_membership_terms_off_peak_matches_kind
        CHECK (membership_kind <> 'off_peak' OR is_off_peak)
);
ALTER TABLE plt01.mem_membership_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_membership_terms FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_membership_terms_tenant ON plt01.mem_membership_terms
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The signed agreement.** COM-01-R02: "contract version, signature, start/end, minimum
-- term, notice, renewal and cancellation policy." Insert-only in full except for its own
-- signature fields, because an agreement whose terms could be edited after signing is not an
-- agreement -- a change is a new agreement that supersedes this one, which is also how
-- COM-01-R04's upgrade and downgrade are represented.
CREATE TABLE plt01.mem_agreements (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    agreement_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The member. MOD-014's person, by composite reference, so an agreement cannot be signed
    -- against somebody else's tenant's member.
    person_id uuid NOT NULL,
    membership_terms_id uuid NOT NULL,
    -- The contract version signed, pinned. Not the key: a key would re-resolve to whatever is
    -- current, which is precisely what makes a signature meaningless.
    contract_version_id uuid NOT NULL,
    -- What was sold and what it cost, snapshotted from MOD-016's resolution. The resolution id
    -- is the receipt that explains the figure; the figures are copied so the agreement reads
    -- on its own.
    variant_id uuid NOT NULL,
    price_resolution_id uuid,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- COM-01-R02's dates. `starts_on` is the operative date; `minimum_term_ends_on` is
    -- derived at signing from the contract version and stored, because the version may be
    -- retired later and the member's commitment does not move with it.
    starts_on date NOT NULL,
    ends_on date,
    minimum_term_ends_on date,
    -- The signature. `signed_by_person` is the member or their guardian; the evidence is a
    -- locator for however it was captured, never the image itself.
    signature_kind text,
    signature_evidence_ref text,
    signed_at timestamptz,
    signed_by_person_id uuid,
    -- **Who recorded the signature**, which is not the same person as the one who signed and
    -- was not recorded at all in the first version: `sign_agreement` took an `actor_id` and a
    -- `correlation_id` and used neither, and `created_by` is the draft's author. MOD-008 audits
    -- denials and not allowed actions, and `veyro_cp_app` holds nothing in `iam`, so this row
    -- is the only record there can be -- the fifth time this build has shipped that shape.
    signed_by uuid,
    sign_correlation_id uuid,
    -- Which agreement this one replaces, for an upgrade, downgrade or transfer. Self-
    -- referencing, so the chain answers "what did this member have in March".
    supersedes_agreement_id uuid,
    status text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, agreement_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, membership_terms_id)
        REFERENCES plt01.mem_membership_terms (tenant_id, membership_terms_id),
    FOREIGN KEY (tenant_id, contract_version_id)
        REFERENCES plt01.mem_contract_versions (tenant_id, contract_version_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, price_resolution_id)
        REFERENCES plt01.cat_price_resolutions (tenant_id, resolution_id),
    FOREIGN KEY (tenant_id, signed_by_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, supersedes_agreement_id)
        REFERENCES plt01.mem_agreements (tenant_id, agreement_id),
    CONSTRAINT mem_agreements_status
        CHECK (status IN ('draft', 'signed', 'active', 'superseded', 'ended', 'void')),
    CONSTRAINT mem_agreements_amount_not_negative CHECK (amount_minor >= 0),
    CONSTRAINT mem_agreements_amount_sane CHECK (amount_minor <= 1000000000000),
    CONSTRAINT mem_agreements_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT mem_agreements_dates_ordered
        CHECK (ends_on IS NULL OR ends_on >= starts_on),
    CONSTRAINT mem_agreements_minimum_term_after_start
        CHECK (minimum_term_ends_on IS NULL OR minimum_term_ends_on >= starts_on),
    CONSTRAINT mem_agreements_not_self
        CHECK (supersedes_agreement_id IS NULL OR supersedes_agreement_id <> agreement_id),
    CONSTRAINT mem_agreements_signature_kind CHECK (signature_kind IS NULL
        OR signature_kind IN ('wet_ink', 'click_through', 'drawn', 'witnessed', 'imported')),
    -- A locator too, for the same reason: whatever captured the signature holds the image,
    -- and a column that would accept the image is one somebody eventually puts it in.
    CONSTRAINT mem_agreements_evidence_is_a_locator
        CHECK (signature_evidence_ref IS NULL
               OR signature_evidence_ref ~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$'),
    -- **A signature is a who, a when and a how, or it is none of them.** The four columns move
    -- together. Any subset is an agreement that reads as signed with nothing behind it.
    CONSTRAINT mem_agreements_signature_complete CHECK (
        (signed_at IS NULL AND signed_by_person_id IS NULL AND signature_kind IS NULL
         AND signature_evidence_ref IS NULL)
        OR (signed_at IS NOT NULL AND signed_by_person_id IS NOT NULL
            AND signature_kind IS NOT NULL AND signature_evidence_ref IS NOT NULL)),
    -- And nothing past `draft` exists without one. Split from the constraint above so each is
    -- violable on its own, which is the only way a mutation sweep can prove either --
    -- MOD-014's compound-CHECK finding, designed out rather than discovered.
    CONSTRAINT mem_agreements_signed_is_signed
        CHECK (status = 'draft' OR status = 'void' OR signed_at IS NOT NULL),
    CONSTRAINT mem_agreements_signature_attributed CHECK (
        (signed_at IS NULL AND signed_by IS NULL AND sign_correlation_id IS NULL)
        OR (signed_at IS NOT NULL AND signed_by IS NOT NULL
            AND sign_correlation_id IS NOT NULL))
);
CREATE INDEX mem_agreements_by_person
    ON plt01.mem_agreements (tenant_id, person_id, starts_on DESC);
ALTER TABLE plt01.mem_agreements ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_agreements FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_agreements_tenant ON plt01.mem_agreements
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- the membership lifecycle

-- **The live membership.** One row per agreement, carrying the current state -- and the state
-- here is a *cache of the latest effective lifecycle change*, not the only copy of it.
-- COM-01-R07 asks for "full state history and as-of reconstruction", so `mem_lifecycle_changes`
-- beside this is the authority and a dispute is argued from there. Keeping the current state
-- denormalized is what lets an access-control read answer in one indexed lookup; keeping the
-- history insert-only is what lets anybody prove the answer was right last March.
CREATE TABLE plt01.mem_memberships (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    membership_id uuid NOT NULL DEFAULT gen_random_uuid(),
    agreement_id uuid NOT NULL,
    person_id uuid NOT NULL,
    -- A human-facing number, because a member reads it out at a front desk and a uuid is not
    -- something anybody reads out. Unique per tenant.
    membership_number text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    -- The window this membership is operative over, and the current billing period inside it.
    starts_on date NOT NULL,
    ends_on date,
    current_period_start date,
    current_period_end date,
    -- Set when the status last changed and by which change, so the cache can be checked
    -- against the history rather than trusted.
    status_effective_on date NOT NULL,
    status_change_id uuid,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, membership_id),
    FOREIGN KEY (tenant_id, agreement_id)
        REFERENCES plt01.mem_agreements (tenant_id, agreement_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    -- One membership per agreement, and one number per tenant.
    UNIQUE (tenant_id, agreement_id),
    UNIQUE (tenant_id, membership_number),
    CONSTRAINT mem_memberships_number_shape
        CHECK (membership_number ~ '^[A-Z0-9][A-Z0-9-]{2,31}$'),
    -- COM-01-R04's lifecycle, as the states a membership can hold. `grace` is R05's grace
    -- period, which is a state and not merely a date, because access policy differs in it.
    CONSTRAINT mem_memberships_status CHECK (status IN (
        'pending', 'active', 'frozen', 'grace', 'suspended', 'cancelled', 'expired',
        'transferred')),
    CONSTRAINT mem_memberships_dates_ordered
        CHECK (ends_on IS NULL OR ends_on >= starts_on),
    CONSTRAINT mem_memberships_period_ordered
        CHECK (current_period_end IS NULL OR current_period_start IS NULL
               OR current_period_end >= current_period_start),
    CONSTRAINT mem_memberships_period_pair
        CHECK ((current_period_start IS NULL) = (current_period_end IS NULL)),
    CONSTRAINT mem_memberships_version_positive CHECK (version >= 1),
    -- Anything past `pending` was moved there by a recorded change. `pending` is the only
    -- state a membership can be in without one, because it is the state it is created in.
    CONSTRAINT mem_memberships_status_has_a_change
        CHECK (status = 'pending' OR status_change_id IS NOT NULL)
);
CREATE INDEX mem_memberships_by_person
    ON plt01.mem_memberships (tenant_id, person_id, status);
CREATE INDEX mem_memberships_by_status
    ON plt01.mem_memberships (tenant_id, status, current_period_end);
ALTER TABLE plt01.mem_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_memberships_tenant ON plt01.mem_memberships
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **COM-01-R07's history, and COM-01-R04's effective dating.** Insert-only in full: a
-- lifecycle change is what a dispute is argued from, so a change somebody could edit
-- afterwards is worth nothing. Every row names who decided, when they decided, when it takes
-- effect and why -- and `effective_on` is deliberately separate from `decided_at`, because a
-- cancellation decided today at the end of a notice period takes effect in thirty days and
-- both dates matter to the argument.
CREATE TABLE plt01.mem_lifecycle_changes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    change_id uuid NOT NULL DEFAULT gen_random_uuid(),
    membership_id uuid NOT NULL,
    change_kind text NOT NULL,
    from_status text NOT NULL,
    to_status text NOT NULL,
    effective_on date NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now(),
    decided_by uuid NOT NULL,
    -- Who asked for it, where that is not the person who decided. A member self-service
    -- request (COM-01-R06) is requested by the member and decided by whoever approved it.
    requested_by_person_id uuid,
    -- COM-01-R06's fee disclosure: what the member was told this would cost, recorded at the
    -- moment they were told rather than recomputed afterwards.
    disclosed_fee_minor bigint,
    disclosed_fee_currency char(3),
    -- The money consequence, if the change had one. A reference rather than an amount: the
    -- invoice is the authority and copying the figure here would be a second copy able to
    -- disagree with it.
    invoice_id uuid,
    reason text NOT NULL,
    -- The idempotency handle, so a retried command does not move a membership twice.
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, change_id),
    FOREIGN KEY (tenant_id, membership_id)
        REFERENCES plt01.mem_memberships (tenant_id, membership_id),
    FOREIGN KEY (tenant_id, requested_by_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    UNIQUE (tenant_id, idempotency_key),
    -- COM-01-R04's eleven acts. `reinstatement` is the edge MOD-004 deliberately refused for a
    -- tenant and COM-01 explicitly asks for here.
    CONSTRAINT mem_lifecycle_changes_kind CHECK (change_kind IN (
        'activation', 'freeze', 'resume', 'medical_hold', 'upgrade', 'downgrade',
        'transfer', 'renewal', 'cancellation', 'expiry', 'reinstatement', 'suspension',
        'grace_entry')),
    CONSTRAINT mem_lifecycle_changes_from_status CHECK (from_status IN (
        'pending', 'active', 'frozen', 'grace', 'suspended', 'cancelled', 'expired',
        'transferred')),
    CONSTRAINT mem_lifecycle_changes_to_status CHECK (to_status IN (
        'pending', 'active', 'frozen', 'grace', 'suspended', 'cancelled', 'expired',
        'transferred')),
    CONSTRAINT mem_lifecycle_changes_moves
        CHECK (from_status <> to_status OR change_kind IN ('renewal', 'upgrade', 'downgrade')),
    CONSTRAINT mem_lifecycle_changes_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    CONSTRAINT mem_lifecycle_changes_key_not_blank
        CHECK (idempotency_key ~ '[^[:space:]]'),
    -- A disclosed fee is an amount and a currency, or neither. MOD-016's
    -- `amount_has_currency`, and for the same reason: a figure with no currency is not a sum
    -- of money, and a currency with no figure is a restriction nobody applies.
    CONSTRAINT mem_lifecycle_changes_fee_has_currency
        CHECK ((disclosed_fee_minor IS NULL) = (disclosed_fee_currency IS NULL)),
    CONSTRAINT mem_lifecycle_changes_fee_not_negative
        CHECK (disclosed_fee_minor IS NULL OR disclosed_fee_minor >= 0),
    CONSTRAINT mem_lifecycle_changes_fee_sane
        CHECK (disclosed_fee_minor IS NULL OR disclosed_fee_minor <= 1000000000000),
    CONSTRAINT mem_lifecycle_changes_fee_currency_shape
        CHECK (disclosed_fee_currency IS NULL OR disclosed_fee_currency ~ '^[A-Z]{3}$')
);
CREATE INDEX mem_lifecycle_changes_history
    ON plt01.mem_lifecycle_changes (tenant_id, membership_id, effective_on DESC,
                                    decided_at DESC);
ALTER TABLE plt01.mem_lifecycle_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_lifecycle_changes FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_lifecycle_changes_tenant ON plt01.mem_lifecycle_changes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The membership's status cache points at the change that set it, and the change has to be
-- about this membership.** The comment on the column already said "a cache that could name a
-- change on another membership would be worse than no cache" -- and the first version's key
-- carried only `(tenant_id, status_change_id)`, so a reviewer pointed one membership's cache
-- at another's change. The membership id travels with the reference.
CREATE UNIQUE INDEX mem_lifecycle_changes_identity
    ON plt01.mem_lifecycle_changes (tenant_id, membership_id, change_id);
ALTER TABLE plt01.mem_memberships
    ADD CONSTRAINT mem_memberships_status_change_fkey
    FOREIGN KEY (tenant_id, membership_id, status_change_id)
    REFERENCES plt01.mem_lifecycle_changes (tenant_id, membership_id, change_id);

-- COM-01-R04's freeze, pause and medical hold, as windows rather than as a boolean. A
-- membership frozen twice in a year has two rows, and the contract's `freeze_days_per_year`
-- allowance is checked by summing them -- which is why the window is stored and not just the
-- current state. A `medical` hold is distinguished because contracts routinely exempt it from
-- the allowance, and because it carries a reference to evidence somebody else holds.
CREATE TABLE plt01.mem_freezes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    freeze_id uuid NOT NULL DEFAULT gen_random_uuid(),
    membership_id uuid NOT NULL,
    freeze_kind text NOT NULL,
    starts_on date NOT NULL,
    -- Open-ended while the freeze is live; set when it is resumed or when it lapses.
    ends_on date,
    -- **What the member asked for**, which is not the same fact as when the freeze actually
    -- ended and was conflated with it in the first version: a fixed-length freeze was written
    -- with `ends_on` already set, which made it indistinguishable from a resumed one, took it
    -- out of the one-live-freeze index, and let a second freeze be stacked on top. The plan is
    -- what the allowance arithmetic projects from; `ends_on` is what it counts.
    planned_ends_on date,
    -- Whether these days count against the contract's annual allowance. Derived from the kind
    -- by `freezes.counts_against_allowance` and stored, because the contract may change and
    -- the decision made at the time has to stand.
    counts_against_allowance boolean NOT NULL,
    -- COM-01-R05's expiry extension: a freeze ordinarily pushes the term out by its length,
    -- and whether it does is a contract decision recorded per freeze.
    extends_term boolean NOT NULL DEFAULT true,
    -- For a medical hold, where the note lives. A locator, never the note: a diagnosis is
    -- health data under MOD-008's classification and this module has no business holding one.
    evidence_ref text,
    reason text NOT NULL,
    requested_by_person_id uuid,
    decided_at timestamptz NOT NULL DEFAULT now(),
    decided_by uuid NOT NULL,
    resumed_at timestamptz,
    resumed_by uuid,
    resume_correlation_id uuid,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, freeze_id),
    FOREIGN KEY (tenant_id, membership_id)
        REFERENCES plt01.mem_memberships (tenant_id, membership_id),
    FOREIGN KEY (tenant_id, requested_by_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    CONSTRAINT mem_freezes_kind
        CHECK (freeze_kind IN ('freeze', 'pause', 'medical_hold')),
    CONSTRAINT mem_freezes_dates_ordered
        CHECK (ends_on IS NULL OR ends_on >= starts_on),
    CONSTRAINT mem_freezes_plan_ordered
        CHECK (planned_ends_on IS NULL OR planned_ends_on >= starts_on),
    CONSTRAINT mem_freezes_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    -- **A locator, enforced.** The comment on the column says "a diagnosis is health data
    -- under MOD-008's classification and this module has no business holding one", and the
    -- first version enforced only non-blankness -- so a reviewer stored a staged lymphoma
    -- diagnosis here, in a column with no UPDATE grant, in a build whose own rule is that
    -- health is unreadable by anybody. Same repair as `fin_payment_intents`, same precedent.
    CONSTRAINT mem_freezes_evidence_is_a_locator
        CHECK (evidence_ref IS NULL
               OR evidence_ref ~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$'),
    -- **A medical hold cites evidence.** It is the kind that ordinarily escapes the allowance
    -- and may carry a fee waiver, so a medical hold with nothing behind it is the one a member
    -- would claim and nobody could check.
    CONSTRAINT mem_freezes_medical_has_evidence
        CHECK (freeze_kind <> 'medical_hold' OR evidence_ref IS NOT NULL),
    -- A resume names who and when and under which correlation, or none of the three.
    CONSTRAINT mem_freezes_resume_attributed CHECK (
        (resumed_at IS NULL AND resumed_by IS NULL AND resume_correlation_id IS NULL)
        OR (resumed_at IS NOT NULL AND resumed_by IS NOT NULL
            AND resume_correlation_id IS NOT NULL)),
    -- And a resumed freeze has an end date. Split from the constraint above so each is
    -- isolatable.
    CONSTRAINT mem_freezes_resumed_is_closed
        CHECK (resumed_at IS NULL OR ends_on IS NOT NULL)
);
-- **One live freeze per membership.** Two overlapping freezes would make "is this membership
-- frozen" answerable two ways and the allowance arithmetic double-count. A partial index,
-- because the constraint is about the open ones only.
CREATE UNIQUE INDEX mem_freezes_one_live
    ON plt01.mem_freezes (tenant_id, membership_id)
    WHERE ends_on IS NULL;
CREATE INDEX mem_freezes_by_membership
    ON plt01.mem_freezes (tenant_id, membership_id, starts_on DESC);
ALTER TABLE plt01.mem_freezes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_freezes FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_freezes_tenant ON plt01.mem_freezes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- entitlements

-- COM-01-R03's entitlement types, as a per-tenant policy. **What an entitlement *means* is a
-- tenant decision and the set is open**, which is the opposite call from MOD-008's permissions
-- and MOD-010's event types: those are facts about what the software does, and two tenants
-- disagreeing would be unresolvable. "Six guest passes a month" is a product a gym sells, and
-- the gym next door sells a different one.
CREATE TABLE plt01.mem_entitlement_policies (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    policy_id uuid NOT NULL DEFAULT gen_random_uuid(),
    policy_key text NOT NULL,
    display_name text NOT NULL,
    -- COM-01-R03's nine kinds of right. The kind decides which scope columns on a grant mean
    -- anything, which is why it is a domain and not free text.
    entitlement_type text NOT NULL,
    -- Whether a grant of this type is counted or unlimited. A counted grant draws down through
    -- the ledger; an unlimited one is a yes/no over a window.
    is_counted boolean NOT NULL DEFAULT true,
    -- How long a reservation of this entitlement holds before it lapses. Paragraph 1506:
    -- "Reservation is atomic and expiring." A reservation that never expired would strand a
    -- member's own credit the first time a booking flow was abandoned.
    reservation_ttl_seconds integer NOT NULL DEFAULT 900,
    -- COM-01-R05's carryover: whether unconsumed quantity survives into the next period.
    carryover_mode text NOT NULL DEFAULT 'none',
    carryover_limit integer,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, policy_id),
    UNIQUE (tenant_id, policy_key),
    CONSTRAINT mem_entitlement_policies_key_shape
        CHECK (policy_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT mem_entitlement_policies_name_not_blank
        CHECK (display_name ~ '[^[:space:]]'),
    CONSTRAINT mem_entitlement_policies_type CHECK (entitlement_type IN (
        'location_access', 'schedule_access', 'zone_access', 'class_credit',
        'facility_access', 'service_credit', 'guest_pass', 'discount', 'digital_content')),
    CONSTRAINT mem_entitlement_policies_status
        CHECK (status IN ('active', 'retired')),
    CONSTRAINT mem_entitlement_policies_ttl_sane
        CHECK (reservation_ttl_seconds BETWEEN 30 AND 86400),
    CONSTRAINT mem_entitlement_policies_carryover_mode
        CHECK (carryover_mode IN ('none', 'capped', 'unlimited')),
    -- **A capped carryover has a cap and nothing else does.** MOD-016's operand rule: a limit
    -- on a mode that ignores it is a field somebody set and nothing reads, and a cap missing
    -- from the mode that needs it is an unlimited carryover wearing a cap's name.
    CONSTRAINT mem_entitlement_policies_cap_matches_mode
        CHECK ((carryover_mode = 'capped') = (carryover_limit IS NOT NULL)),
    CONSTRAINT mem_entitlement_policies_cap_positive
        CHECK (carryover_limit IS NULL OR (carryover_limit > 0 AND carryover_limit <= 100000)),
    -- An unlimited entitlement is not counted, and a counted one is not unlimited. The
    -- carryover of something uncounted is meaningless, so it must be `none`.
    CONSTRAINT mem_entitlement_policies_uncounted_has_no_carryover
        CHECK (is_counted OR carryover_mode = 'none')
);
ALTER TABLE plt01.mem_entitlement_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_entitlement_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_entitlement_policies_tenant ON plt01.mem_entitlement_policies
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The fulfilment authority.** Paragraph 1506 in four words: this table answers "may this
-- member use the service now?", and nothing else does. COM-04's ServiceCredit is the financial
-- liability view of the same purchase and is explicitly *not* the access decision (paragraph
-- 4053); reconciling the two is COM-04's job and a mismatch opens a case rather than changing
-- either.
--
-- **There is no `remaining` column**, and that is the single most important thing about this
-- table. A balance stored here is what two concurrent bookings race on, and a stored balance
-- that disagrees with the movements beside it is unresolvable. The balance is the sum of
-- `mem_entitlement_ledger`, taken under a lock on this row -- MOD-011's argument against a
-- metric that duplicates a table, applied to the number that decides whether somebody gets
-- through a turnstile.
CREATE TABLE plt01.mem_entitlement_grants (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    grant_id uuid NOT NULL DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL,
    policy_id uuid NOT NULL,
    -- Where this grant came from. Paragraph 4050's `source_type`/`source_id`: a membership, a
    -- bundle fulfilment, a goodwill gesture or a migration. No foreign key, because the four
    -- point at four different tables and a polymorphic reference the database cannot check is
    -- better declared than faked -- `source_kind` says which table to look in.
    source_kind text NOT NULL,
    source_id uuid,
    membership_id uuid,
    -- Counted or unlimited, copied from the policy at grant time: the policy may be retired
    -- and this grant's nature does not move with it.
    is_counted boolean NOT NULL,
    granted_quantity integer,
    -- The window. `valid_from` is when it becomes usable and `valid_to` when it lapses;
    -- COM-01-R05's expiry extension moves the latter and records why in the ledger.
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    -- COM-01-R03's scope. A grant may be narrowed to a brand, a location or a resource; all
    -- three NULL means the whole tenant, which is the ordinary case for an unlimited
    -- membership.
    brand_id uuid,
    location_id uuid,
    -- An off-peak membership's window, as minutes from midnight in the location's timezone.
    -- Two integers rather than a time range, because the comparison is done in the decision
    -- layer and a `timerange` would invite the database to do arithmetic it cannot explain.
    usable_from_minute integer,
    usable_to_minute integer,
    status text NOT NULL DEFAULT 'active',
    revoked_at timestamptz,
    revoked_by uuid,
    revoke_reason text,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, grant_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, policy_id)
        REFERENCES plt01.mem_entitlement_policies (tenant_id, policy_id),
    FOREIGN KEY (tenant_id, membership_id)
        REFERENCES plt01.mem_memberships (tenant_id, membership_id),
    FOREIGN KEY (tenant_id, brand_id) REFERENCES plt01.brands (tenant_id, brand_id),
    FOREIGN KEY (tenant_id, location_id)
        REFERENCES plt01.locations (tenant_id, location_id),
    CONSTRAINT mem_entitlement_grants_source_kind CHECK (source_kind IN (
        'membership', 'bundle_fulfilment', 'goodwill', 'migration', 'corporate')),
    CONSTRAINT mem_entitlement_grants_status
        CHECK (status IN ('active', 'exhausted', 'expired', 'revoked')),
    CONSTRAINT mem_entitlement_grants_window
        CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT mem_entitlement_grants_version_positive CHECK (version >= 1),
    -- **A counted grant has a quantity and an unlimited one does not.** The ledger's
    -- arithmetic is only defined for the first, and a quantity on the second is a number
    -- nothing draws down.
    CONSTRAINT mem_entitlement_grants_quantity_matches_counted
        CHECK (is_counted = (granted_quantity IS NOT NULL)),
    CONSTRAINT mem_entitlement_grants_quantity_positive
        CHECK (granted_quantity IS NULL
               OR (granted_quantity > 0 AND granted_quantity <= 100000)),
    -- A membership-sourced grant names the membership; nothing else does, so "which
    -- membership gave this member their classes" is answerable without a guess.
    CONSTRAINT mem_entitlement_grants_membership_matches_source
        CHECK ((source_kind = 'membership') = (membership_id IS NOT NULL)),
    -- The off-peak window is both ends or neither, and inside a day.
    CONSTRAINT mem_entitlement_grants_window_pair
        CHECK ((usable_from_minute IS NULL) = (usable_to_minute IS NULL)),
    CONSTRAINT mem_entitlement_grants_from_minute_sane
        CHECK (usable_from_minute IS NULL OR usable_from_minute BETWEEN 0 AND 1439),
    CONSTRAINT mem_entitlement_grants_to_minute_sane
        CHECK (usable_to_minute IS NULL OR usable_to_minute BETWEEN 1 AND 1440),
    CONSTRAINT mem_entitlement_grants_minutes_ordered
        CHECK (usable_to_minute IS NULL OR usable_from_minute IS NULL
               OR usable_to_minute > usable_from_minute),
    -- A revocation names who and why. The `coalesce` is load-bearing: a CHECK passes on NULL,
    -- which is how MOD-009's legal hold admitted the row it existed to refuse.
    CONSTRAINT mem_entitlement_grants_revocation_attributed CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)
        OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
            AND coalesce(revoke_reason, '') ~ '[^[:space:]]')),
    CONSTRAINT mem_entitlement_grants_revoked_is_attributed
        CHECK ((status = 'revoked') = (revoked_at IS NOT NULL))
);
CREATE INDEX mem_entitlement_grants_usable
    ON plt01.mem_entitlement_grants (tenant_id, person_id, policy_id, status, valid_from);
CREATE INDEX mem_entitlement_grants_by_membership
    ON plt01.mem_entitlement_grants (tenant_id, membership_id)
    WHERE membership_id IS NOT NULL;
ALTER TABLE plt01.mem_entitlement_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_entitlement_grants FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_entitlement_grants_tenant ON plt01.mem_entitlement_grants
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The reservation.** Paragraph 164: "atomic reserve/consume/release/revoke/expire
-- transitions, idempotency and optimistic version checks." A reservation is a held claim on a
-- counted grant: taken under `FOR UPDATE` on the grant, expiring on its own, and either
-- consumed when the service is delivered or released when it is not.
--
-- The two states that matter are `held` and everything after it. A `held` reservation reduces
-- the balance; a consumed, released or expired one does not, and the ledger carries the
-- matching movements so the arithmetic is one sum rather than a case analysis.
CREATE TABLE plt01.mem_entitlement_reservations (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    reservation_id uuid NOT NULL DEFAULT gen_random_uuid(),
    grant_id uuid NOT NULL,
    person_id uuid NOT NULL,
    quantity integer NOT NULL DEFAULT 1,
    -- What the reservation is for. OPS-02's booking is the realistic one and is not built, so
    -- this is an opaque locator -- the same shape MOD-016 uses for `order_reference`, and the
    -- same gap: nothing resolves it yet.
    purpose_kind text NOT NULL,
    purpose_ref text,
    status text NOT NULL DEFAULT 'held',
    held_at timestamptz NOT NULL DEFAULT now(),
    -- When it lapses if nothing settles it. Computed from the policy's TTL at reservation
    -- time, so a policy change does not retroactively expire or extend a live hold.
    expires_at timestamptz NOT NULL,
    settled_at timestamptz,
    settled_by uuid,
    settle_correlation_id uuid,
    -- Why it was released, where it was. A release is the direction that gives a member back
    -- something they paid for, so it says who did it and on what grounds.
    settle_reason text,
    idempotency_key text NOT NULL,
    held_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, reservation_id),
    FOREIGN KEY (tenant_id, grant_id)
        REFERENCES plt01.mem_entitlement_grants (tenant_id, grant_id),
    FOREIGN KEY (tenant_id, person_id) REFERENCES plt01.ppl_persons (tenant_id, person_id),
    -- **One reservation per handle**, which is what makes a retried booking free. Paragraph
    -- 1505 asks for "unique active entitlement reservation keys" and this is it.
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT mem_entitlement_reservations_status
        CHECK (status IN ('held', 'consumed', 'released', 'expired')),
    CONSTRAINT mem_entitlement_reservations_purpose_kind CHECK (purpose_kind IN (
        'booking', 'guest_entry', 'service_delivery', 'manual')),
    CONSTRAINT mem_entitlement_reservations_purpose_not_blank
        CHECK (purpose_ref IS NULL OR purpose_ref ~ '[^[:space:]]'),
    CONSTRAINT mem_entitlement_reservations_quantity_positive
        CHECK (quantity > 0 AND quantity <= 1000),
    CONSTRAINT mem_entitlement_reservations_key_not_blank
        CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT mem_entitlement_reservations_expires_after_hold
        CHECK (expires_at > held_at),
    -- A settlement names who and when and under which correlation, or none of the three.
    CONSTRAINT mem_entitlement_reservations_settlement_attributed CHECK (
        (settled_at IS NULL AND settled_by IS NULL AND settle_correlation_id IS NULL)
        OR (settled_at IS NOT NULL AND settled_by IS NOT NULL
            AND settle_correlation_id IS NOT NULL)),
    -- And anything past `held` is settled. Split so each half is violable alone.
    CONSTRAINT mem_entitlement_reservations_settled_is_settled
        CHECK ((status = 'held') = (settled_at IS NULL)),
    -- A release says why; a consumption does not need to, because delivering the service is
    -- its own explanation. The `coalesce` is the half a blank string walks past.
    CONSTRAINT mem_entitlement_reservations_release_explained
        CHECK (status <> 'released'
               OR coalesce(settle_reason, '') ~ '[^[:space:]]'),
    CONSTRAINT mem_entitlement_reservations_reason_not_blank
        CHECK (settle_reason IS NULL OR settle_reason ~ '[^[:space:]]')
);
-- The reservation's identity with its grant, so a ledger movement cannot cite a hold taken
-- against a different grant.
CREATE UNIQUE INDEX mem_entitlement_reservations_identity
    ON plt01.mem_entitlement_reservations (tenant_id, grant_id, reservation_id);
CREATE INDEX mem_entitlement_reservations_live
    ON plt01.mem_entitlement_reservations (tenant_id, grant_id, status, expires_at);
CREATE INDEX mem_entitlement_reservations_sweep
    ON plt01.mem_entitlement_reservations (tenant_id, expires_at)
    WHERE status = 'held';
ALTER TABLE plt01.mem_entitlement_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_entitlement_reservations FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_entitlement_reservations_tenant ON plt01.mem_entitlement_reservations
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The movement ledger, and the only authority on a balance.** Insert-only in full: no
-- UPDATE and no DELETE grant for either runtime role. Every transition paragraph 164 names is
-- a row here with a signed `delta`, and a grant's remaining quantity is their sum. That makes
-- three things true at once, and no stored balance makes any of them true:
--
--   * **"May this member train now" is answerable as of any past instant**, by summing the
--     rows up to it. COM-01-R07's as-of reconstruction, for the one question access control
--     asks.
--   * **A correction is a row, not an edit.** MOD-015's credit note and MOD-016's fulfilment
--     reversal, applied to access rights.
--   * **Two concurrent bookings cannot disagree**, because there is no column for them to
--     race on -- only a lock on the grant and an insert.
--
-- The signs are stated once and a constraint per kind enforces them, so each is violable on
-- its own: a grant, a carryover, a release and a lapsed reservation add; a reservation, a
-- revocation and a lapsed grant subtract; a consumption moves nothing, because the quantity
-- already left the balance when it was held.
CREATE TABLE plt01.mem_entitlement_ledger (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    movement_id uuid NOT NULL DEFAULT gen_random_uuid(),
    grant_id uuid NOT NULL,
    reservation_id uuid,
    movement_kind text NOT NULL,
    -- Signed, in whole units of the entitlement. Negative takes away.
    delta integer NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor_id uuid NOT NULL,
    reason text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, movement_id),
    FOREIGN KEY (tenant_id, grant_id)
        REFERENCES plt01.mem_entitlement_grants (tenant_id, grant_id),
    -- **A movement's reservation has to be a reservation against the same grant.** Two
    -- independent references let a reviewer credit grant B for a hold taken on grant A -- A
    -- short for ever and B ahead, with the ledger internally consistent on both rows. The
    -- grant id travels with the reference.
    FOREIGN KEY (tenant_id, grant_id, reservation_id)
        REFERENCES plt01.mem_entitlement_reservations
            (tenant_id, grant_id, reservation_id),
    -- **`reservation_expired` and `grant_expired` are two kinds, not one.** The first
    -- version had a single `expire`, which is two opposite movements wearing one name: a held
    -- reservation that lapses gives the quantity *back* to the balance, and a grant that
    -- lapses takes the whole remaining balance *away*. One kind meant one sign constraint,
    -- and whichever sign it enforced was wrong for half the rows -- a member either losing
    -- credit when a booking flow was abandoned, or keeping it after the grant expired. Caught
    -- while writing the sign constraints below, which is the argument for writing them.
    CONSTRAINT mem_entitlement_ledger_kind CHECK (movement_kind IN (
        'grant', 'reserve', 'consume', 'release', 'revoke', 'reservation_expired',
        'grant_expired', 'carryover', 'adjustment')),
    CONSTRAINT mem_entitlement_ledger_delta_sane
        CHECK (delta BETWEEN -100000 AND 100000),
    CONSTRAINT mem_entitlement_ledger_reason_not_blank CHECK (reason ~ '[^[:space:]]'),
    -- **The sign follows the kind**, each as its own constraint so each is isolatable. A
    -- `grant` that subtracted or a `reserve` that added would make the balance wrong in the
    -- direction nobody checks until a member is refused at a turnstile.
    CONSTRAINT mem_entitlement_ledger_grant_adds
        CHECK (movement_kind <> 'grant' OR delta > 0),
    CONSTRAINT mem_entitlement_ledger_carryover_adds
        CHECK (movement_kind <> 'carryover' OR delta > 0),
    CONSTRAINT mem_entitlement_ledger_release_adds
        CHECK (movement_kind <> 'release' OR delta > 0),
    CONSTRAINT mem_entitlement_ledger_reserve_subtracts
        CHECK (movement_kind <> 'reserve' OR delta < 0),
    CONSTRAINT mem_entitlement_ledger_revoke_subtracts
        CHECK (movement_kind <> 'revoke' OR delta < 0),
    CONSTRAINT mem_entitlement_ledger_grant_expired_subtracts
        CHECK (movement_kind <> 'grant_expired' OR delta < 0),
    CONSTRAINT mem_entitlement_ledger_reservation_expired_adds
        CHECK (movement_kind <> 'reservation_expired' OR delta > 0),
    -- A consumption moves nothing: the quantity left the balance when it was reserved. It is
    -- recorded because "when was this actually used" is a different question from "when was
    -- it held", and both get asked.
    CONSTRAINT mem_entitlement_ledger_consume_is_neutral
        CHECK (movement_kind <> 'consume' OR delta = 0),
    -- An adjustment is the one kind that may go either way, and it is the one kind that may
    -- not be zero -- a movement of nothing is a row with no meaning.
    CONSTRAINT mem_entitlement_ledger_adjustment_moves
        CHECK (movement_kind <> 'adjustment' OR delta <> 0),
    -- **The four reservation movements name their reservation, and the others do not.** A
    -- `consume` with no reservation is a consumption of nothing; a `grant` naming one is a
    -- reference nobody can interpret.
    CONSTRAINT mem_entitlement_ledger_reservation_matches_kind
        CHECK ((movement_kind IN ('reserve', 'consume', 'release', 'reservation_expired'))
               = (reservation_id IS NOT NULL))
);
CREATE INDEX mem_entitlement_ledger_balance
    ON plt01.mem_entitlement_ledger (tenant_id, grant_id, occurred_at);
-- **One opening movement per grant.** Without it a second `grant` row takes a ten-class pack
-- to nineteen, which a reviewer did. The service writes exactly one, at grant time, and this
-- is what makes that a fact rather than a habit.
CREATE UNIQUE INDEX mem_entitlement_ledger_one_opening
    ON plt01.mem_entitlement_ledger (tenant_id, grant_id)
    WHERE movement_kind = 'grant';
ALTER TABLE plt01.mem_entitlement_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.mem_entitlement_ledger FORCE ROW LEVEL SECURITY;
CREATE POLICY mem_entitlement_ledger_tenant ON plt01.mem_entitlement_ledger
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- ---------------------------------------------------------------- billing and payments
--
-- COM-03. **`fin_` is the tenant billing its own members**, which is a different thing from
-- MOD-015's `bil_` where Veyro bills the tenant for its subscription. The two are counted in
-- different currencies, owed by different parties and never joined.

-- COM-03-R01's billing account, and the thing that makes consolidated household and corporate
-- billing possible: the account is who *pays*, which is not always the member who *owes*. A
-- parent pays for three children; a company pays for forty employees. One account, many
-- memberships.
CREATE TABLE plt01.fin_billing_accounts (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    billing_account_id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The payer. A person for a household, and a person acting for a company until PPL-02's
    -- corporate accounts exist -- declared rather than faked.
    payer_person_id uuid NOT NULL,
    account_kind text NOT NULL DEFAULT 'individual',
    -- A human-facing reference, for the same reason a membership has a number.
    account_number text NOT NULL,
    currency char(3) NOT NULL,
    -- The legal entity that invoices from this account. MOD-004's hierarchy owns it, and the
    -- fiscal series below is per legal entity, which is what COM-03-R07 requires.
    legal_entity_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'active',
    -- COM-03-R04's access policy consequence: how far past due this account may go before
    -- dunning starts and before access is affected. Per account, because a corporate payer on
    -- thirty-day terms is not a lapsed member.
    payment_terms_days integer NOT NULL DEFAULT 0,
    closed_at timestamptz,
    closed_by uuid,
    close_reason text,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, billing_account_id),
    FOREIGN KEY (tenant_id, payer_person_id)
        REFERENCES plt01.ppl_persons (tenant_id, person_id),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    UNIQUE (tenant_id, account_number),
    CONSTRAINT fin_billing_accounts_kind
        CHECK (account_kind IN ('individual', 'household', 'corporate')),
    CONSTRAINT fin_billing_accounts_number_shape
        CHECK (account_number ~ '^[A-Z0-9][A-Z0-9-]{2,31}$'),
    CONSTRAINT fin_billing_accounts_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fin_billing_accounts_status
        CHECK (status IN ('active', 'suspended', 'closed')),
    CONSTRAINT fin_billing_accounts_terms_sane
        CHECK (payment_terms_days BETWEEN 0 AND 180),
    CONSTRAINT fin_billing_accounts_version_positive CHECK (version >= 1),
    CONSTRAINT fin_billing_accounts_closure_attributed CHECK (
        (closed_at IS NULL AND closed_by IS NULL AND close_reason IS NULL)
        OR (closed_at IS NOT NULL AND closed_by IS NOT NULL
            AND coalesce(close_reason, '') ~ '[^[:space:]]')),
    CONSTRAINT fin_billing_accounts_closed_is_attributed
        CHECK ((status = 'closed') = (closed_at IS NOT NULL))
);
ALTER TABLE plt01.fin_billing_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_billing_accounts FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_billing_accounts_tenant ON plt01.fin_billing_accounts
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- COM-03-R01's schedule: what this account will be invoiced, when, and how many times.
-- Installments and deposits are the same shape as a recurring charge with a count, which is
-- why there is one table rather than three.
CREATE TABLE plt01.fin_billing_schedules (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    schedule_id uuid NOT NULL DEFAULT gen_random_uuid(),
    billing_account_id uuid NOT NULL,
    -- What is being billed for. A membership, ordinarily; nullable because a deposit or a
    -- one-off charge has no membership behind it.
    membership_id uuid,
    schedule_kind text NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- The cadence, and how many are left. `remaining_count` is NULL for an open-ended
    -- recurring schedule and counts down for an installment plan.
    period text NOT NULL,
    next_due_on date,
    remaining_count integer,
    status text NOT NULL DEFAULT 'active',
    -- Paused when the membership is frozen, which is COM-01-R05's access consequence seen
    -- from the money side -- and the one place the two lifecycles touch, deliberately through
    -- a recorded act rather than a trigger.
    paused_at timestamptz,
    paused_by uuid,
    pause_reason text,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, schedule_id),
    FOREIGN KEY (tenant_id, billing_account_id)
        REFERENCES plt01.fin_billing_accounts (tenant_id, billing_account_id),
    FOREIGN KEY (tenant_id, membership_id)
        REFERENCES plt01.mem_memberships (tenant_id, membership_id),
    CONSTRAINT fin_billing_schedules_kind CHECK (schedule_kind IN (
        'recurring', 'installment', 'deposit', 'one_off')),
    CONSTRAINT fin_billing_schedules_period CHECK (period IN (
        'weekly', 'monthly', 'quarterly', 'annual', 'one_off')),
    CONSTRAINT fin_billing_schedules_status
        CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
    CONSTRAINT fin_billing_schedules_amount_positive
        CHECK (amount_minor > 0 AND amount_minor <= 1000000000000),
    CONSTRAINT fin_billing_schedules_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fin_billing_schedules_version_positive CHECK (version >= 1),
    CONSTRAINT fin_billing_schedules_remaining_sane
        CHECK (remaining_count IS NULL
               OR (remaining_count >= 0 AND remaining_count <= 1000)),
    -- **An installment plan counts down and an open-ended recurring one does not.** A count on
    -- the second is a number the scheduler would decrement to zero and silently stop billing.
    CONSTRAINT fin_billing_schedules_count_matches_kind
        CHECK ((schedule_kind = 'installment') = (remaining_count IS NOT NULL)),
    -- An active schedule knows when it next bills; a completed or cancelled one does not.
    CONSTRAINT fin_billing_schedules_active_has_a_due_date
        CHECK (status <> 'active' OR next_due_on IS NOT NULL),
    CONSTRAINT fin_billing_schedules_pause_attributed CHECK (
        (paused_at IS NULL AND paused_by IS NULL AND pause_reason IS NULL)
        OR (paused_at IS NOT NULL AND paused_by IS NOT NULL
            AND coalesce(pause_reason, '') ~ '[^[:space:]]')),
    CONSTRAINT fin_billing_schedules_paused_is_attributed
        CHECK ((status = 'paused') = (paused_at IS NOT NULL))
);
CREATE INDEX fin_billing_schedules_due
    ON plt01.fin_billing_schedules (tenant_id, status, next_due_on);
ALTER TABLE plt01.fin_billing_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_billing_schedules FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_billing_schedules_tenant ON plt01.fin_billing_schedules
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **COM-03-R07's fiscal series, and the counter the serial comes from.** "Fiscal series+serial
-- uniqueness per legal entity" (paragraph 1606). Two invoices sharing a serial is a tax
-- offence rather than a bug, and a *gap* in the sequence is something a tax authority asks
-- about -- so the serial is allocated from this row under `FOR UPDATE`, in order, with no
-- skipping. That is slower than a sequence and it is the only way the two properties hold
-- together: a PostgreSQL sequence is explicitly non-transactional and leaves gaps on rollback.
CREATE TABLE plt01.fin_fiscal_series (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    series_id uuid NOT NULL DEFAULT gen_random_uuid(),
    legal_entity_id uuid NOT NULL,
    series_code text NOT NULL,
    -- What this series numbers. A credit note series is separate from an invoice series in
    -- most regimes, and conflating them is not recoverable after the fact.
    document_kind text NOT NULL DEFAULT 'invoice',
    -- The last serial handed out. The next is this plus one, always, with no gaps.
    last_serial bigint NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, series_id),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    -- One series per code per legal entity, which is the uniqueness COM-03-R07 names.
    UNIQUE (tenant_id, legal_entity_id, series_code, document_kind),
    CONSTRAINT fin_fiscal_series_code_shape CHECK (series_code ~ '^[A-Z0-9][A-Z0-9-]{0,15}$'),
    CONSTRAINT fin_fiscal_series_document_kind
        CHECK (document_kind IN ('invoice', 'credit_note', 'receipt')),
    CONSTRAINT fin_fiscal_series_status CHECK (status IN ('active', 'closed')),
    -- A serial counter never goes backwards and never goes negative. It cannot be checked
    -- against `OLD` by a CHECK, so the monotonicity is a trigger -- the one place in this
    -- module that needs one, for MOD-009's reason: a CHECK cannot see what a row used to be,
    -- and rewinding this counter is how two invoices come to share a serial.
    CONSTRAINT fin_fiscal_series_serial_not_negative CHECK (last_serial >= 0)
);
-- **The series' own identity, as a key other tables can point at.** `fin_invoices` carries
-- the legal entity, the series, the serial, the number and the document kind as five
-- independent columns, and the service derives all five -- which made the correspondence a
-- property of the service's choice of SQL rather than of the database. A reviewer wrote an
-- invoice filed under entity B, numbered out of entity A's series, in a currency its account
-- does not use. COM-03-R07's uniqueness is per legal entity, so the entity and the kind have
-- to travel with the reference.
CREATE UNIQUE INDEX fin_fiscal_series_identity
    ON plt01.fin_fiscal_series (tenant_id, series_id, legal_entity_id, document_kind);

CREATE OR REPLACE FUNCTION plt01.fin_fiscal_series_no_rewind()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW.last_serial < OLD.last_serial THEN
        RAISE EXCEPTION 'a fiscal serial counter cannot be rewound (% -> %)',
            OLD.last_serial, NEW.last_serial;
    END IF;
    IF NEW.series_code <> OLD.series_code
       OR NEW.legal_entity_id <> OLD.legal_entity_id
       OR NEW.document_kind <> OLD.document_kind THEN
        RAISE EXCEPTION 'a fiscal series cannot be re-pointed once it has numbered anything';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER fin_fiscal_series_no_rewind
    BEFORE UPDATE ON plt01.fin_fiscal_series
    FOR EACH ROW EXECUTE FUNCTION plt01.fin_fiscal_series_no_rewind();
ALTER TABLE plt01.fin_fiscal_series ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_fiscal_series FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_fiscal_series_tenant ON plt01.fin_fiscal_series
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The invoice, with two independent statuses.** Paragraph 1607: "Provider payment state is
-- asynchronous; fiscal state is separate from payment state. Jordan final tax invoice requires
-- server serial + JoFotara acknowledgement before FISCAL_COMPLETE."
--
-- So `payment_status` and `fiscal_status` move independently and neither implies the other. An
-- invoice can be paid and not fiscalized -- the member's card cleared and the tax authority has
-- not acknowledged -- or fiscalized and unpaid, which is the ordinary state of a credit
-- customer. A single `status` column would have forced one of those to be unrepresentable, and
-- whichever it was would have been the one that happened on a Friday afternoon.
--
-- Insert-only on everything it says. The amounts, the lines, the serial and the tax are what
-- was issued; only the two statuses and their timestamps move. MOD-015's invoice has no draft
-- state for the same reason: a row exists only once issued, and a correction is a credit note.
CREATE TABLE plt01.fin_invoices (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    invoice_id uuid NOT NULL DEFAULT gen_random_uuid(),
    billing_account_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    -- The fiscal identity: series, serial and the printed number built from both. Allocated
    -- at issue, never after, and never reallocated.
    series_id uuid NOT NULL,
    serial bigint NOT NULL,
    document_number text NOT NULL,
    document_kind text NOT NULL DEFAULT 'invoice',
    -- What this invoice is for, where it came from a schedule.
    schedule_id uuid,
    membership_id uuid,
    -- The money. Net, tax and gross, each stored, with a constraint that they add up -- the
    -- same arithmetic-in-the-row discipline as MOD-016's resolution, and here it is the figure
    -- a tax authority reads.
    net_minor bigint NOT NULL,
    tax_minor bigint NOT NULL,
    gross_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    issued_on date NOT NULL,
    due_on date NOT NULL,
    payment_status text NOT NULL DEFAULT 'unpaid',
    paid_at timestamptz,
    fiscal_status text NOT NULL DEFAULT 'pending',
    -- The authority's own acknowledgement. Opaque, because what it contains is the
    -- authority's business and this build has no integration with one.
    fiscal_ack_ref text,
    fiscal_acked_at timestamptz,
    -- **Who moved the fiscal state**, which is deliberately not the issuer: the catalogue's
    -- own reason for a separate permission is that "the person who issues invoices is not
    -- necessarily the person who files them", and the first version recorded only the issuer.
    fiscalized_by uuid,
    fiscalized_at timestamptz,
    fiscalize_correlation_id uuid,
    -- **Why a document was declared outside the regime.** `not_required` is terminal, demands
    -- no acknowledgement and sidesteps the one control this table is proud of, so it is the
    -- transition that most needs a reason on the row. A reviewer took it in one call with
    -- nothing recorded.
    fiscal_exemption_reason text,
    -- What this credits, for a credit note. Stored positive like MOD-015's, and always read as
    -- a reduction, so a credit and the charge it reverses have the same magnitude.
    credits_invoice_id uuid,
    idempotency_key text NOT NULL,
    issued_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id),
    FOREIGN KEY (tenant_id, billing_account_id)
        REFERENCES plt01.fin_billing_accounts (tenant_id, billing_account_id),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    -- **The series, its legal entity and its document kind as one reference**, against
    -- `fin_fiscal_series_identity`. Three independent references would each be satisfied by a
    -- mismatched triple, which is exactly what a reviewer exploited.
    FOREIGN KEY (tenant_id, series_id, legal_entity_id, document_kind)
        REFERENCES plt01.fin_fiscal_series
            (tenant_id, series_id, legal_entity_id, document_kind),
    FOREIGN KEY (tenant_id, schedule_id)
        REFERENCES plt01.fin_billing_schedules (tenant_id, schedule_id),
    FOREIGN KEY (tenant_id, membership_id)
        REFERENCES plt01.mem_memberships (tenant_id, membership_id),
    FOREIGN KEY (tenant_id, credits_invoice_id)
        REFERENCES plt01.fin_invoices (tenant_id, invoice_id),
    -- **The uniqueness COM-03-R07 asks for**, enforced rather than described: one serial per
    -- series, and one printed number per legal entity.
    UNIQUE (tenant_id, series_id, serial),
    UNIQUE (tenant_id, legal_entity_id, document_number),
    UNIQUE (tenant_id, idempotency_key),
    -- **No domain on `document_kind` here**, for the reason above: the four-column reference
    -- to the fiscal series makes the kind a property of the series, and the series has the
    -- domain. An invoice carrying a kind outside the three cannot exist, because no series
    -- does.
    CONSTRAINT fin_invoices_number_shape
        CHECK (document_number ~ '^[A-Z0-9][A-Z0-9/-]{2,47}$'),
    CONSTRAINT fin_invoices_serial_positive CHECK (serial >= 1),
    CONSTRAINT fin_invoices_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fin_invoices_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT fin_invoices_dates_ordered CHECK (due_on >= issued_on),
    -- The arithmetic, in the row. Three constraints, each violable on its own.
    CONSTRAINT fin_invoices_net_not_negative CHECK (net_minor >= 0),
    CONSTRAINT fin_invoices_tax_not_negative CHECK (tax_minor >= 0),
    CONSTRAINT fin_invoices_adds_up CHECK (gross_minor = net_minor + tax_minor),
    CONSTRAINT fin_invoices_net_sane CHECK (net_minor <= 1000000000000),
    CONSTRAINT fin_invoices_tax_sane CHECK (tax_minor <= 1000000000000),
    -- **The two statuses, and nothing relating them.** That independence is the requirement.
    CONSTRAINT fin_invoices_payment_status CHECK (payment_status IN (
        'unpaid', 'part_paid', 'paid', 'overdue', 'written_off', 'credited')),
    CONSTRAINT fin_invoices_fiscal_status CHECK (fiscal_status IN (
        'pending', 'submitted', 'acknowledged', 'fiscal_complete', 'rejected',
        'not_required')),
    CONSTRAINT fin_invoices_paid_has_a_time
        CHECK ((payment_status = 'paid') = (paid_at IS NOT NULL)),
    -- **`fiscal_complete` needs the authority's acknowledgement**, which is paragraph 1607's
    -- Jordan rule as a constraint: a server serial (every row has one) *and* an ack. Nothing
    -- can read as fiscally final on the strength of a serial alone.
    CONSTRAINT fin_invoices_fiscal_complete_is_acked
        CHECK (fiscal_status <> 'fiscal_complete' OR fiscal_ack_ref IS NOT NULL),
    CONSTRAINT fin_invoices_fiscal_ack_attributed CHECK (
        (fiscal_ack_ref IS NULL AND fiscal_acked_at IS NULL)
        OR (coalesce(fiscal_ack_ref, '') ~ '[^[:space:]]'
            AND fiscal_acked_at IS NOT NULL)),
    CONSTRAINT fin_invoices_fiscal_move_attributed CHECK (
        (fiscalized_by IS NULL AND fiscalized_at IS NULL
         AND fiscalize_correlation_id IS NULL)
        OR (fiscalized_by IS NOT NULL AND fiscalized_at IS NOT NULL
            AND fiscalize_correlation_id IS NOT NULL)),
    CONSTRAINT fin_invoices_fiscal_state_has_an_actor
        CHECK (fiscal_status = 'pending' OR fiscalized_by IS NOT NULL),
    CONSTRAINT fin_invoices_exemption_reasoned
        CHECK ((fiscal_status = 'not_required')
               = (coalesce(fiscal_exemption_reason, '') ~ '[^[:space:]]')),
    -- A credit note credits something; an invoice does not.
    CONSTRAINT fin_invoices_credit_matches_kind
        CHECK ((document_kind = 'credit_note') = (credits_invoice_id IS NOT NULL)),
    CONSTRAINT fin_invoices_not_self
        CHECK (credits_invoice_id IS NULL OR credits_invoice_id <> invoice_id)
);
CREATE INDEX fin_invoices_by_account
    ON plt01.fin_invoices (tenant_id, billing_account_id, issued_on DESC);
CREATE INDEX fin_invoices_collectable
    ON plt01.fin_invoices (tenant_id, payment_status, due_on);
CREATE INDEX fin_invoices_fiscal_queue
    ON plt01.fin_invoices (tenant_id, fiscal_status, issued_on);
-- The invoice's own identity with its payer, so a dunning case cannot name another payer's.
CREATE UNIQUE INDEX fin_invoices_identity
    ON plt01.fin_invoices (tenant_id, invoice_id, billing_account_id);
ALTER TABLE plt01.fin_invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_invoices FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_invoices_tenant ON plt01.fin_invoices
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- An invoice's lines. Insert-only with the invoice: what was charged is what was charged, and
-- a correction is a credit note. The catalogue reference is a snapshot of what was sold, so
-- the line reads on its own after the product has been retired.
CREATE TABLE plt01.fin_invoice_lines (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    line_id uuid NOT NULL DEFAULT gen_random_uuid(),
    invoice_id uuid NOT NULL,
    line_number integer NOT NULL,
    -- What it was for, in words, because this is what the member reads on the invoice.
    description text NOT NULL,
    -- And what it was, as references, for everything else.
    variant_id uuid,
    price_resolution_id uuid,
    tax_category_id uuid,
    quantity integer NOT NULL DEFAULT 1,
    unit_net_minor bigint NOT NULL,
    net_minor bigint NOT NULL,
    -- The rate applied, in basis points, recorded per line. COM-03-R07's regional taxation:
    -- two lines on one invoice routinely carry different rates, and the rate that applied on
    -- the day has to survive a rate change.
    tax_rate_bp integer NOT NULL,
    tax_minor bigint NOT NULL,
    gross_minor bigint NOT NULL,
    PRIMARY KEY (tenant_id, line_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES plt01.fin_invoices (tenant_id, invoice_id),
    FOREIGN KEY (tenant_id, variant_id) REFERENCES plt01.cat_variants (tenant_id, variant_id),
    FOREIGN KEY (tenant_id, price_resolution_id)
        REFERENCES plt01.cat_price_resolutions (tenant_id, resolution_id),
    FOREIGN KEY (tenant_id, tax_category_id)
        REFERENCES plt01.cat_tax_categories (tenant_id, tax_category_id),
    UNIQUE (tenant_id, invoice_id, line_number),
    CONSTRAINT fin_invoice_lines_number_positive CHECK (line_number >= 1),
    CONSTRAINT fin_invoice_lines_description_not_blank
        CHECK (description ~ '[^[:space:]]'),
    CONSTRAINT fin_invoice_lines_quantity_positive
        CHECK (quantity > 0 AND quantity <= 1000000),
    CONSTRAINT fin_invoice_lines_unit_not_negative CHECK (unit_net_minor >= 0),
    CONSTRAINT fin_invoice_lines_unit_sane CHECK (unit_net_minor <= 1000000000000),
    -- **No `net_minor >= 0` here**, deliberately, and it was there until the mutation sweep
    -- showed it could not be isolated: `net_minor = unit_net_minor * quantity` with a positive
    -- quantity and a non-negative unit price makes a negative net impossible, so every row
    -- that violated it violated one of those too. One constraint that is the stronger
    -- statement beats two where the weaker is permanently unprovable -- the same judgement
    -- this repository made about MOD-016's subsumed eligibility-kind domain.
    CONSTRAINT fin_invoice_lines_tax_not_negative CHECK (tax_minor >= 0),
    CONSTRAINT fin_invoice_lines_rate_sane CHECK (tax_rate_bp BETWEEN 0 AND 10000),
    -- The line's own arithmetic, in the row, as two separate constraints so each can be
    -- violated alone.
    CONSTRAINT fin_invoice_lines_net_is_unit_times_quantity
        CHECK (net_minor = unit_net_minor * quantity),
    CONSTRAINT fin_invoice_lines_adds_up CHECK (gross_minor = net_minor + tax_minor)
);
ALTER TABLE plt01.fin_invoice_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_invoice_lines FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_invoice_lines_tenant ON plt01.fin_invoice_lines
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **COM-03-R02's payment intent: what a provider was asked to do.** The intent is created
-- before anything is attempted and it is the row that survives an unknown outcome -- paragraph
-- 1609: "persist PENDING explicitly". A provider that times out leaves an intent in `pending`
-- and nothing downstream may read that as either success or failure.
--
-- **There is no card data and no column one could go in.** No PAN, no expiry, no CVV, no
-- cardholder name. `payment_method_ref` is a token somebody else holds, by the same reasoning
-- as MOD-012's `vault_ref`: there is no vault in this build, so the honest shape is a table
-- that *cannot* store a secret rather than one that stores one carefully. The column-list pin
-- in the isolation suite exists because this control is an absence, and an absence is exactly
-- what a later migration adds back.
CREATE TABLE plt01.fin_payment_intents (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    intent_id uuid NOT NULL DEFAULT gen_random_uuid(),
    billing_account_id uuid NOT NULL,
    invoice_id uuid,
    method text NOT NULL,
    -- The provider this was routed to, and its own handle for the attempt. Opaque.
    provider_key text NOT NULL,
    provider_ref text,
    -- A token for a stored method, held by the provider. Never a number.
    payment_method_ref text,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    -- COM-03-R03's 3DS/SCA: whether the provider asked for a challenge and whether it was
    -- answered. Recorded, not performed -- nothing in this build speaks to a provider.
    requires_authentication boolean NOT NULL DEFAULT false,
    authenticated_at timestamptz,
    -- Why it failed, as a code rather than as prose. **A code, because a decision made by
    -- matching words in a provider's error text is a decision anybody can change by editing a
    -- string** -- MOD-016 shipped exactly that and a reviewer walked past it. The provider's
    -- own text goes in `failure_detail`, which nothing branches on.
    failure_code text,
    failure_detail text,
    settled_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, intent_id),
    FOREIGN KEY (tenant_id, billing_account_id)
        REFERENCES plt01.fin_billing_accounts (tenant_id, billing_account_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES plt01.fin_invoices (tenant_id, invoice_id),
    UNIQUE (tenant_id, idempotency_key),
    -- **One intent per provider reference per provider**, which is paragraph 1606's "unique
    -- provider reference per provider+tenant" and the thing that makes a replayed webhook
    -- free. A provider that delivers the same callback twice must not produce two payments.
    CONSTRAINT fin_payment_intents_method CHECK (method IN (
        'card', 'direct_debit', 'bank_transfer', 'cash', 'wallet', 'gift_card', 'other')),
    CONSTRAINT fin_payment_intents_provider_shape
        CHECK (provider_key ~ '^[a-z][a-z0-9_.-]{1,62}$'),
    CONSTRAINT fin_payment_intents_provider_ref_not_blank
        CHECK (provider_ref IS NULL OR provider_ref ~ '[^[:space:]]'),
    -- **A locator, enforced, not merely described.** The header above invokes MOD-012's
    -- `vault_ref` reasoning and the first version did not copy MOD-012's *constraint*, so
    -- `'4111111111111111|12/27|737|JANE SMITH'` was a valid "token reference" -- in a column
    -- with no UPDATE and no DELETE grant, which makes it permanent for every runtime role.
    -- A reviewer wrote one in through the HTTP route. The shape is the same one
    -- `int_credential_refs_vault_ref_is_a_locator` has carried since MOD-012's own review:
    -- a scheme, `://`, and no whitespace. A PAN does not match it.
    CONSTRAINT fin_payment_intents_method_ref_is_a_locator
        CHECK (payment_method_ref IS NULL
               OR payment_method_ref ~ '^[a-z][a-z0-9+.-]*://[^[:space:]]+$'),
    CONSTRAINT fin_payment_intents_amount_positive
        CHECK (amount_minor > 0 AND amount_minor <= 1000000000000),
    CONSTRAINT fin_payment_intents_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    -- `unknown` is a real state and it is the one paragraph 1609 requires. It is not a synonym
    -- for failed: a reconciliation decides which it was, and until then nothing may assume.
    CONSTRAINT fin_payment_intents_status CHECK (status IN (
        'pending', 'requires_authentication', 'succeeded', 'failed', 'cancelled',
        'unknown')),
    CONSTRAINT fin_payment_intents_attempts_sane CHECK (attempts BETWEEN 0 AND 100),
    CONSTRAINT fin_payment_intents_key_not_blank
        CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT fin_payment_intents_failure_code_shape
        CHECK (failure_code IS NULL OR failure_code ~ '^[a-z][a-z0-9_]{1,62}$'),
    CONSTRAINT fin_payment_intents_failure_detail_not_blank
        CHECK (failure_detail IS NULL OR failure_detail ~ '[^[:space:]]'),
    -- **A failure carries a code.** Without one, the retry policy and the dunning decision
    -- would have nothing to branch on but prose.
    CONSTRAINT fin_payment_intents_failure_has_a_code
        CHECK (status <> 'failed' OR failure_code IS NOT NULL),
    -- A settled intent has a settlement time, and `pending` and `unknown` are the two that
    -- do not -- `unknown` precisely because nothing has settled it.
    CONSTRAINT fin_payment_intents_settled_has_a_time
        CHECK ((status IN ('succeeded', 'failed', 'cancelled')) = (settled_at IS NOT NULL)),
    CONSTRAINT fin_payment_intents_authentication_matches
        CHECK (authenticated_at IS NULL OR requires_authentication)
);
CREATE UNIQUE INDEX fin_payment_intents_one_per_provider_ref
    ON plt01.fin_payment_intents (tenant_id, provider_key, provider_ref)
    WHERE provider_ref IS NOT NULL;
CREATE INDEX fin_payment_intents_unsettled
    ON plt01.fin_payment_intents (tenant_id, status, created_at)
    WHERE status IN ('pending', 'requires_authentication', 'unknown');
ALTER TABLE plt01.fin_payment_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_payment_intents FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_payment_intents_tenant ON plt01.fin_payment_intents
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **The payment: money that actually arrived.** Insert-only in full -- no UPDATE and no DELETE
-- grant for either runtime role -- because this is the row an accountant reconciles against and
-- a payment somebody could edit afterwards is not evidence of anything. A payment recorded in
-- error is reversed by a refund, which is the next table, on MOD-015's credit-note principle.
--
-- A payment exists only once an intent succeeded. There is no "pending payment": that is the
-- intent, and conflating them is how an unknown provider state becomes a figure in a revenue
-- report.
CREATE TABLE plt01.fin_payments (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    payment_id uuid NOT NULL DEFAULT gen_random_uuid(),
    billing_account_id uuid NOT NULL,
    intent_id uuid NOT NULL,
    invoice_id uuid,
    method text NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    received_at timestamptz NOT NULL,
    -- The provider's own settlement reference, for the reconciliation COM-03-R06 asks for.
    provider_ref text,
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, payment_id),
    FOREIGN KEY (tenant_id, billing_account_id)
        REFERENCES plt01.fin_billing_accounts (tenant_id, billing_account_id),
    FOREIGN KEY (tenant_id, intent_id)
        REFERENCES plt01.fin_payment_intents (tenant_id, intent_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES plt01.fin_invoices (tenant_id, invoice_id),
    -- **One payment per intent.** An intent that produced two payments is a double charge, and
    -- the commonest way to get one is a provider callback delivered twice. This index is what
    -- makes the replay free rather than expensive.
    UNIQUE (tenant_id, intent_id),
    CONSTRAINT fin_payments_method CHECK (method IN (
        'card', 'direct_debit', 'bank_transfer', 'cash', 'wallet', 'gift_card', 'other')),
    CONSTRAINT fin_payments_amount_positive
        CHECK (amount_minor > 0 AND amount_minor <= 1000000000000),
    CONSTRAINT fin_payments_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fin_payments_provider_ref_not_blank
        CHECK (provider_ref IS NULL OR provider_ref ~ '[^[:space:]]')
);
CREATE INDEX fin_payments_by_invoice
    ON plt01.fin_payments (tenant_id, invoice_id, received_at);
ALTER TABLE plt01.fin_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_payments FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_payments_tenant ON plt01.fin_payments
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **COM-03-R05's refund, and paragraph 1598's approval.** "Refunds, voids and write-offs
-- follow limits, approvals and ledger entries." So a refund cites the approval that permitted
-- it, and the approval is a separate act by a separate person -- MOD-016 learned at review that
-- a separation of duties collapsed into one insert is unverifiable in principle, and this
-- module has the two acts from the start.
--
-- Insert-only, and stored positive. It is always read as a reduction, so a refund and the
-- payment it reverses have the same magnitude and nothing has to remember a sign.
CREATE TABLE plt01.fin_refund_requests (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    request_id uuid NOT NULL DEFAULT gen_random_uuid(),
    payment_id uuid NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    reason text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    -- Derived from the requester's own session by the route. Nothing accepts this field.
    requested_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, request_id),
    FOREIGN KEY (tenant_id, payment_id)
        REFERENCES plt01.fin_payments (tenant_id, payment_id),
    CONSTRAINT fin_refund_requests_amount_positive
        CHECK (amount_minor > 0 AND amount_minor <= 1000000000000),
    CONSTRAINT fin_refund_requests_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fin_refund_requests_reason_not_blank CHECK (reason ~ '[^[:space:]]')
);
-- **The request's own terms, as a key the approval points at.** `fin_refunds` copied
-- `requested_by`, the payment, the amount and the currency and nothing related any of them
-- back -- so `approved_by <> requested_by` compared two columns of the same row, and a
-- reviewer satisfied it while being the actual requester, with an amount and a currency free
-- of both the request and the payment. Paragraph 1598's approval is the reason this table
-- exists; making it a database fact is the point of the key below.
CREATE UNIQUE INDEX fin_refund_requests_terms
    ON plt01.fin_refund_requests
       (tenant_id, request_id, requested_by, payment_id, amount_minor, currency);
ALTER TABLE plt01.fin_refund_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_refund_requests FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_refund_requests_tenant ON plt01.fin_refund_requests
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE TABLE plt01.fin_refunds (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    refund_id uuid NOT NULL DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL,
    payment_id uuid NOT NULL,
    billing_account_id uuid NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- The credit note this refund is documented by, where the regime needs one.
    credit_note_invoice_id uuid,
    status text NOT NULL DEFAULT 'pending',
    provider_ref text,
    failure_code text,
    settled_at timestamptz,
    approved_at timestamptz NOT NULL DEFAULT now(),
    approved_by uuid NOT NULL,
    -- Copied from the request, never from the body. This is what the constraint compares.
    requested_by uuid NOT NULL,
    approval_reason text NOT NULL,
    idempotency_key text NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, refund_id),
    -- **Everything the approval claims about the request is checked against the request.**
    -- The requester, the payment, the amount and the currency travel together, against
    -- `fin_refund_requests_terms`, so the separation of duties below compares one identity the
    -- approver's session gave with one the *requester's* session gave -- which is what makes
    -- it a separation rather than two columns of one row.
    FOREIGN KEY (tenant_id, request_id, requested_by, payment_id, amount_minor, currency)
        REFERENCES plt01.fin_refund_requests
            (tenant_id, request_id, requested_by, payment_id, amount_minor, currency),
    FOREIGN KEY (tenant_id, payment_id)
        REFERENCES plt01.fin_payments (tenant_id, payment_id),
    FOREIGN KEY (tenant_id, billing_account_id)
        REFERENCES plt01.fin_billing_accounts (tenant_id, billing_account_id),
    FOREIGN KEY (tenant_id, credit_note_invoice_id)
        REFERENCES plt01.fin_invoices (tenant_id, invoice_id),
    -- One decision per request, so a refused-then-reasked refund is a new request.
    UNIQUE (tenant_id, request_id),
    UNIQUE (tenant_id, idempotency_key),
    -- **No bound on the amount and none on the currency shape here.** Both were, and neither
    -- could be isolated once the six-column reference to the request went in: that key makes
    -- the amount and the currency properties *of the request*, which has its own bounds, so a
    -- refund row carrying a bad one cannot exist to be refused. The composite key did more
    -- than relate the two rows -- it made the copies redundant, which is the same judgement as
    -- the three arithmetic bounds deleted above.
    CONSTRAINT fin_refunds_status
        CHECK (status IN ('pending', 'succeeded', 'failed', 'unknown')),
    CONSTRAINT fin_refunds_reason_not_blank CHECK (approval_reason ~ '[^[:space:]]'),
    CONSTRAINT fin_refunds_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT fin_refunds_provider_ref_not_blank
        CHECK (provider_ref IS NULL OR provider_ref ~ '[^[:space:]]'),
    CONSTRAINT fin_refunds_failure_code_shape
        CHECK (failure_code IS NULL OR failure_code ~ '^[a-z][a-z0-9_]{1,62}$'),
    CONSTRAINT fin_refunds_failure_has_a_code
        CHECK (status <> 'failed' OR failure_code IS NOT NULL),
    CONSTRAINT fin_refunds_settled_has_a_time
        CHECK ((status IN ('succeeded', 'failed')) = (settled_at IS NOT NULL)),
    -- **The approver is not the requester**, with both sides derived: `requested_by` is copied
    -- from the request row, which recorded the requester's own session. This is the one act in
    -- the module that sends money back out, so paragraph 1598's approval is a constraint
    -- rather than a convention.
    CONSTRAINT fin_refunds_approver_is_not_requester CHECK (approved_by <> requested_by)
);
CREATE INDEX fin_refunds_by_payment ON plt01.fin_refunds (tenant_id, payment_id);
ALTER TABLE plt01.fin_refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_refunds FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_refunds_tenant ON plt01.fin_refunds
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- COM-03-R05's dispute and chargeback. The bank has decided something and Veyro is told; the
-- row records what was claimed, what was answered and how it ended. Insert-only on the claim,
-- with the outcome and its attribution the only things that move -- a dispute whose original
-- claim could be edited is one nobody can argue from.
CREATE TABLE plt01.fin_disputes (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    dispute_id uuid NOT NULL DEFAULT gen_random_uuid(),
    payment_id uuid NOT NULL,
    billing_account_id uuid NOT NULL,
    -- The bank's own case reference, which is how the two sides identify the same dispute.
    provider_case_ref text NOT NULL,
    dispute_kind text NOT NULL,
    reason_code text NOT NULL,
    amount_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    opened_on date NOT NULL,
    -- When Veyro must answer by. A real deadline set by the scheme, so it is required.
    -- Named `respond_due_on` and not `respond_by`: the reachability sweep matches any column
    -- ending in `_by` as a person, and a *date* called `respond_by` makes it demand an
    -- erasure declaration for something nobody can be erased from. A column name that lies to
    -- a sweep is worse than one that is merely ugly.
    respond_due_on date NOT NULL,
    status text NOT NULL DEFAULT 'open',
    -- What was submitted in response, as a locator -- the evidence itself lives wherever the
    -- provider portal keeps it.
    response_ref text,
    responded_at timestamptz,
    responded_by uuid,
    outcome text,
    closed_at timestamptz,
    idempotency_key text NOT NULL,
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, dispute_id),
    FOREIGN KEY (tenant_id, payment_id)
        REFERENCES plt01.fin_payments (tenant_id, payment_id),
    FOREIGN KEY (tenant_id, billing_account_id)
        REFERENCES plt01.fin_billing_accounts (tenant_id, billing_account_id),
    UNIQUE (tenant_id, provider_case_ref),
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT fin_disputes_kind
        CHECK (dispute_kind IN ('chargeback', 'inquiry', 'pre_arbitration')),
    CONSTRAINT fin_disputes_case_ref_not_blank
        CHECK (provider_case_ref ~ '[^[:space:]]'),
    CONSTRAINT fin_disputes_reason_code_shape
        CHECK (reason_code ~ '^[a-z0-9][a-z0-9_.-]{0,62}$'),
    CONSTRAINT fin_disputes_amount_positive
        CHECK (amount_minor > 0 AND amount_minor <= 1000000000000),
    CONSTRAINT fin_disputes_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fin_disputes_dates_ordered CHECK (respond_due_on >= opened_on),
    CONSTRAINT fin_disputes_status
        CHECK (status IN ('open', 'responded', 'won', 'lost', 'withdrawn')),
    -- There is no separate domain CHECK on `outcome`, deliberately. `outcome_matches_status`
    -- forces `outcome = status` and `closed_has_an_outcome` forces that status into the three
    -- closing values, all of which are valid outcomes -- so no input violates a domain
    -- constraint without violating one of those two first. It had no isolating case and could
    -- not have one; MOD-016's precedent is to delete the subsumed constraint rather than test
    -- it harder.
    CONSTRAINT fin_disputes_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT fin_disputes_response_not_blank
        CHECK (response_ref IS NULL OR response_ref ~ '[^[:space:]]'),
    -- A response names who and when and what was sent, or none of the three.
    CONSTRAINT fin_disputes_response_attributed CHECK (
        (responded_at IS NULL AND responded_by IS NULL AND response_ref IS NULL)
        OR (responded_at IS NOT NULL AND responded_by IS NOT NULL
            AND response_ref IS NOT NULL)),
    -- A closed dispute has an outcome and a closing time; an open one has neither. Two
    -- constraints, so each is violable alone.
    CONSTRAINT fin_disputes_closed_has_an_outcome
        CHECK ((status IN ('won', 'lost', 'withdrawn')) = (outcome IS NOT NULL)),
    CONSTRAINT fin_disputes_closed_has_a_time
        CHECK ((outcome IS NULL) = (closed_at IS NULL)),
    -- And the outcome agrees with the status, which is the half a separate `outcome` column
    -- would otherwise let drift: a dispute reading `won` with outcome `lost`.
    CONSTRAINT fin_disputes_outcome_matches_status
        CHECK (outcome IS NULL OR outcome = status)
);
CREATE INDEX fin_disputes_open
    ON plt01.fin_disputes (tenant_id, status, respond_due_on)
    WHERE status IN ('open', 'responded');
ALTER TABLE plt01.fin_disputes ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_disputes FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_disputes_tenant ON plt01.fin_disputes
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **COM-03-R04's dunning case.** "Retry schedule, grace period, member communication, task
-- escalation and access policy." One case per unpaid invoice, moving through stages on a
-- schedule, with the access consequence stated on the row rather than inferred.
--
-- **The access consequence is recorded and not applied here.** A dunning case may say that
-- access should be suspended; whether it *is* suspended is a membership lifecycle change with
-- its own recorded decision. That is paragraph 1496 again -- billing state and access state are
-- related and never conflated -- and it is why this column is a recommendation rather than a
-- trigger.
CREATE TABLE plt01.fin_dunning_cases (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    case_id uuid NOT NULL DEFAULT gen_random_uuid(),
    billing_account_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    stage integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'open',
    opened_on date NOT NULL,
    -- When the next step of the journey is due. NULL once the case is closed.
    next_action_on date,
    attempts integer NOT NULL DEFAULT 0,
    -- What this stage says should happen to access. `none` through to `suspend`, recorded so
    -- an operator reading the case knows what it is asking for.
    access_recommendation text NOT NULL DEFAULT 'none',
    -- The notification MOD-013 authored, where one was requested. A locator, so the two
    -- modules are related without either reaching into the other's tables.
    last_notification_ref text,
    -- COM-03-R04's escalation: who owns this case now.
    owner_ref text,
    resolution text,
    closed_at timestamptz,
    closed_by uuid,
    idempotency_key text NOT NULL,
    opened_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, case_id),
    -- **The account has to be the invoice's.** Two independent references let a reviewer open
    -- a recovery journey against one payer for another payer's invoice -- and the journey's
    -- `access_recommendation` then follows the wrong member.
    FOREIGN KEY (tenant_id, invoice_id, billing_account_id)
        REFERENCES plt01.fin_invoices (tenant_id, invoice_id, billing_account_id),
    UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT fin_dunning_cases_stage_sane CHECK (stage BETWEEN 1 AND 10),
    CONSTRAINT fin_dunning_cases_status
        CHECK (status IN ('open', 'paused', 'recovered', 'written_off', 'abandoned')),
    CONSTRAINT fin_dunning_cases_attempts_sane CHECK (attempts BETWEEN 0 AND 100),
    CONSTRAINT fin_dunning_cases_access_recommendation CHECK (access_recommendation IN (
        'none', 'warn', 'restrict', 'suspend')),
    CONSTRAINT fin_dunning_cases_key_not_blank CHECK (idempotency_key ~ '[^[:space:]]'),
    CONSTRAINT fin_dunning_cases_notification_not_blank
        CHECK (last_notification_ref IS NULL OR last_notification_ref ~ '[^[:space:]]'),
    CONSTRAINT fin_dunning_cases_owner_not_blank
        CHECK (owner_ref IS NULL OR owner_ref ~ '[^[:space:]]'),
    -- An open case has a next action; a closed one does not.
    CONSTRAINT fin_dunning_cases_open_has_a_next_action
        CHECK ((status = 'open') = (next_action_on IS NOT NULL)),
    -- A closed case says who closed it, when, and how it ended. The `coalesce` is the half a
    -- blank string walks past.
    CONSTRAINT fin_dunning_cases_closure_attributed CHECK (
        (closed_at IS NULL AND closed_by IS NULL AND resolution IS NULL)
        OR (closed_at IS NOT NULL AND closed_by IS NOT NULL
            AND coalesce(resolution, '') ~ '[^[:space:]]')),
    CONSTRAINT fin_dunning_cases_closed_is_attributed
        CHECK ((status IN ('recovered', 'written_off', 'abandoned'))
               = (closed_at IS NOT NULL))
);
-- **One open case per invoice.** Two would send the member two dunning journeys for one debt,
-- which is the complaint that reaches a regulator rather than a support queue.
CREATE UNIQUE INDEX fin_dunning_cases_one_open
    ON plt01.fin_dunning_cases (tenant_id, invoice_id)
    WHERE status IN ('open', 'paused');
CREATE INDEX fin_dunning_cases_due
    ON plt01.fin_dunning_cases (tenant_id, status, next_action_on);
ALTER TABLE plt01.fin_dunning_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_dunning_cases FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_dunning_cases_tenant ON plt01.fin_dunning_cases
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- **COM-03-R07's tax record: what was reported, per invoice, per jurisdiction.** Insert-only,
-- because this is the figure a tax return is built from and a tax record somebody could edit
-- after filing is the shape of an offence rather than a bug.
--
-- The rate is on the row rather than looked up, which is the same decision MOD-016 made for
-- its own reason: rates are jurisdictional and the sources state none, so a caller supplies
-- one and the record keeps what was applied on the day. MOD-015's `issue_invoice` set the
-- precedent and a rate table nobody could populate would be worse than this.
CREATE TABLE plt01.fin_tax_records (
    tenant_id uuid NOT NULL REFERENCES plt01_platform.tenants (tenant_id),
    tax_record_id uuid NOT NULL DEFAULT gen_random_uuid(),
    invoice_id uuid NOT NULL,
    legal_entity_id uuid NOT NULL,
    -- Where this is owed. A jurisdiction code the tenant chooses, because the set is open.
    jurisdiction text NOT NULL,
    tax_category_id uuid,
    tax_rate_bp integer NOT NULL,
    taxable_minor bigint NOT NULL,
    tax_minor bigint NOT NULL,
    currency char(3) NOT NULL,
    -- The period the return this belongs to covers, so an export can select by it.
    period_start date NOT NULL,
    period_end date NOT NULL,
    -- COM-03-R07's accounting export: set when this row has been included in one, so the
    -- same figure is not exported twice and a re-export is a deliberate act.
    exported_at timestamptz,
    exported_by uuid,
    export_ref text,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    recorded_by uuid NOT NULL,
    correlation_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, tax_record_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES plt01.fin_invoices (tenant_id, invoice_id),
    FOREIGN KEY (tenant_id, legal_entity_id)
        REFERENCES plt01.legal_entities (tenant_id, legal_entity_id),
    FOREIGN KEY (tenant_id, tax_category_id)
        REFERENCES plt01.cat_tax_categories (tenant_id, tax_category_id),
    -- One record per invoice per jurisdiction per rate. A second at the same rate would
    -- double-count the liability in a return.
    UNIQUE (tenant_id, invoice_id, jurisdiction, tax_rate_bp),
    CONSTRAINT fin_tax_records_jurisdiction_shape
        CHECK (jurisdiction ~ '^[A-Z]{2}(-[A-Z0-9]{1,8})?$'),
    CONSTRAINT fin_tax_records_rate_sane CHECK (tax_rate_bp BETWEEN 0 AND 10000),
    -- **No `taxable_minor >= 0` and no second bound on the tax**, for the reason above:
    -- `tax_minor >= 0` and `tax_minor <= taxable_minor` make a negative taxable amount
    -- impossible, and that pair with `taxable_minor <= 1000000000000` makes a tax above the
    -- bound impossible. Both were here and neither had an isolating case, which is what the
    -- sweep is for.
    CONSTRAINT fin_tax_records_taxable_sane CHECK (taxable_minor <= 1000000000000),
    CONSTRAINT fin_tax_records_tax_not_negative CHECK (tax_minor >= 0),
    -- **The tax is at most the taxable amount**, which no rate inside the allowed range can
    -- exceed. A row that breaks it is an arithmetic failure somebody would file.
    CONSTRAINT fin_tax_records_tax_bounded CHECK (tax_minor <= taxable_minor),
    CONSTRAINT fin_tax_records_currency_shape CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT fin_tax_records_period_ordered CHECK (period_end >= period_start),
    -- An export names who, when and under which reference, or none of the three.
    CONSTRAINT fin_tax_records_export_attributed CHECK (
        (exported_at IS NULL AND exported_by IS NULL AND export_ref IS NULL)
        OR (exported_at IS NOT NULL AND exported_by IS NOT NULL
            AND coalesce(export_ref, '') ~ '[^[:space:]]'))
);
CREATE INDEX fin_tax_records_for_return
    ON plt01.fin_tax_records (tenant_id, legal_entity_id, jurisdiction, period_start);
CREATE INDEX fin_tax_records_unexported
    ON plt01.fin_tax_records (tenant_id, period_start)
    WHERE exported_at IS NULL;
-- **An export marker is written once and never cleared.** The column comment says the marker
-- exists "so the same figure is not exported twice", and the UPDATE grant it needs to be
-- written at all is the grant that lets it be rewritten: clear it, and the row returns to the
-- unexported index and is exported again -- the liability counted twice in two returns, with
-- the row afterwards reading as a single clean export. Re-point it instead, and the question
-- "which return did this figure go into" has a new answer and no record of the old one.
--
-- A CHECK cannot see `OLD`, so this is the second place in the module that needs a trigger,
-- for exactly the reason `sec_legal_holds` needs one: the fact being protected is not the
-- row's current value but the value it used to have. A genuine re-export is a second
-- `fin_tax_records` row under a new reference, which is the same answer as everywhere else
-- here -- a correction is a row, not an edit.
CREATE OR REPLACE FUNCTION plt01.fin_tax_records_export_is_final()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.exported_at IS NOT NULL
       AND (NEW.exported_at IS DISTINCT FROM OLD.exported_at
            OR NEW.exported_by IS DISTINCT FROM OLD.exported_by
            OR NEW.export_ref IS DISTINCT FROM OLD.export_ref) THEN
        RAISE EXCEPTION
            'a tax record''s export marker is final (exported % under %)',
            OLD.exported_at, OLD.export_ref;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER fin_tax_records_export_is_final
    BEFORE UPDATE ON plt01.fin_tax_records
    FOR EACH ROW EXECUTE FUNCTION plt01.fin_tax_records_export_is_final();
ALTER TABLE plt01.fin_tax_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE plt01.fin_tax_records FORCE ROW LEVEL SECURITY;
CREATE POLICY fin_tax_records_tenant ON plt01.fin_tax_records
    FOR ALL TO veyro_cp_app, veyro_cp_worker
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

-- The lifecycle change's money consequence points at its invoice, declared after both tables
-- exist. A reference rather than a copied amount: the invoice is the authority, and a figure
-- duplicated onto the change would be a second copy able to disagree with it.
ALTER TABLE plt01.mem_lifecycle_changes
    ADD CONSTRAINT mem_lifecycle_changes_invoice_fkey
    FOREIGN KEY (tenant_id, invoice_id)
    REFERENCES plt01.fin_invoices (tenant_id, invoice_id);

-- ---------------------------------------------------------------- privileges
--
-- **Every insert-only claim in this file is a missing UPDATE grant, not a comment.** The
-- pattern this repository arrived at over nine modules: a control that rests on the service
-- choosing the right SQL is a control until somebody writes different SQL, and the column-list
-- comparison in the isolation suite is what stops a later migration widening one quietly.
--
-- Three tables carry no UPDATE grant at all, and each is a number somebody is accountable for:
-- the entitlement movement ledger (the balance that decides access), the payment (the money an
-- accountant reconciles), and the tax record (the figure a return is built from).

GRANT SELECT, INSERT ON plt01.mem_contract_versions TO veyro_cp_app, veyro_cp_worker;
-- A published contract's terms and its policy numbers do not move: the member agreed to those.
-- Only the lifecycle columns do, which is how a version is published and later retired.
GRANT UPDATE (status, published_at, published_by, publish_correlation_id)
    ON plt01.mem_contract_versions TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.mem_membership_terms TO veyro_cp_app, veyro_cp_worker;
-- The *kind* carries no UPDATE grant. Changing it re-routes the billing schedule and the
-- lifecycle edges for everything already sold on these terms -- a recurring membership that
-- becomes an installment plan is a contract nobody agreed to -- and it is MOD-016's reasoning
-- about `cat_products.product_type`, one layer up.
GRANT UPDATE (status, version, billing_period, installment_count, prepaid_days)
    ON plt01.mem_membership_terms TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.mem_agreements TO veyro_cp_app, veyro_cp_worker;
-- **The signed terms, the dates, the price and the contract version carry no UPDATE grant.**
-- An agreement whose amount or minimum term could be edited after signing is not an agreement,
-- and a change is a new row that supersedes this one -- which is also how COM-01-R04's upgrade,
-- downgrade and transfer are represented. The signature columns move once, from nothing to
-- signed, and `status` moves along the lifecycle.
GRANT UPDATE (status, signature_kind, signature_evidence_ref, signed_at,
              signed_by_person_id, signed_by, sign_correlation_id, ends_on)
    ON plt01.mem_agreements TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.mem_memberships TO veyro_cp_app, veyro_cp_worker;
-- The cache of the current state moves; the agreement, the person and the number do not. A
-- membership number that could be re-pointed at another person is a card on a turnstile
-- opening for the wrong member.
GRANT UPDATE (status, status_effective_on, status_change_id, ends_on,
              current_period_start, current_period_end, version)
    ON plt01.mem_memberships TO veyro_cp_app, veyro_cp_worker;

-- **The lifecycle history is insert-only in full.** COM-01-R07's "as-of reconstruction for
-- disputes and audits" is only true of a history nobody can rewrite, and this is the table a
-- dispute is argued from.
GRANT SELECT, INSERT ON plt01.mem_lifecycle_changes TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.mem_freezes TO veyro_cp_app, veyro_cp_worker;
-- A freeze's kind, its start, whether it counts against the allowance and whether it extends
-- the term are decided once. Only the close moves -- which is what resuming is.
GRANT UPDATE (ends_on, resumed_at, resumed_by, resume_correlation_id)
    ON plt01.mem_freezes TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.mem_entitlement_policies TO veyro_cp_app, veyro_cp_worker;
-- A policy's *type* and whether it is counted do not move: a counted entitlement that became
-- unlimited would unmask every past draw-down, and the ledger's arithmetic is only defined for
-- one of the two.
GRANT UPDATE (display_name, status, reservation_ttl_seconds, carryover_mode, carryover_limit)
    ON plt01.mem_entitlement_policies TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.mem_entitlement_grants TO veyro_cp_app, veyro_cp_worker;
-- **The granted quantity carries no UPDATE grant**, which is what makes the ledger the only
-- authority on a balance: a quantity that could be edited would let somebody change what a
-- member bought without a movement to show it. `valid_to` moves because COM-01-R05's expiry
-- extension is a real operation, and it records its reason in the ledger.
GRANT UPDATE (status, valid_to, revoked_at, revoked_by, revoke_reason, version)
    ON plt01.mem_entitlement_grants TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.mem_entitlement_reservations TO veyro_cp_app, veyro_cp_worker;
-- A reservation's quantity, grant, expiry and handle are fixed at the moment it is taken.
-- Only the settlement moves, once.
GRANT UPDATE (status, settled_at, settled_by, settle_correlation_id, settle_reason)
    ON plt01.mem_entitlement_reservations TO veyro_cp_app, veyro_cp_worker;

-- **The movement ledger has no UPDATE grant at all.** It is the balance that decides whether a
-- member gets through a turnstile and the record of every draw-down they have made; a row that
-- could be edited would make both unanswerable. A correction is an `adjustment` row with an
-- actor and a reason on it.
GRANT SELECT, INSERT ON plt01.mem_entitlement_ledger TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.fin_billing_accounts TO veyro_cp_app, veyro_cp_worker;
-- The payer, the currency, the legal entity and the account number do not move. Re-pointing an
-- account at another legal entity would change which fiscal series its future invoices are
-- numbered in, which is COM-03-R07's uniqueness defeated from the side nobody watches.
GRANT UPDATE (status, payment_terms_days, closed_at, closed_by, close_reason, version)
    ON plt01.fin_billing_accounts TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.fin_billing_schedules TO veyro_cp_app, veyro_cp_worker;
-- **The amount and the currency carry no UPDATE grant**: re-pricing a live schedule is a new
-- schedule, on the same terms as MOD-016's prices, so what a member was told they would pay
-- stays answerable. The cadence moves because it is what pausing and advancing do.
GRANT UPDATE (status, next_due_on, remaining_count, paused_at, paused_by, pause_reason,
              version)
    ON plt01.fin_billing_schedules TO veyro_cp_app, veyro_cp_worker;

-- The serial counter is the one thing on a fiscal series that moves, and a trigger stops it
-- moving backwards -- a CHECK cannot see `OLD`, and rewinding this counter is how two invoices
-- come to share a serial.
GRANT SELECT, INSERT ON plt01.fin_fiscal_series TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (last_serial, status) ON plt01.fin_fiscal_series
    TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.fin_invoices TO veyro_cp_app, veyro_cp_worker;
-- **Every figure, the serial, the number and the dates are immutable by privilege.** This is
-- the document a tax authority reads and a member disputes; a correction is a credit note. The
-- two statuses move independently, which is paragraph 1607's requirement, and the fiscal
-- acknowledgement moves once.
GRANT UPDATE (payment_status, paid_at, fiscal_status, fiscal_ack_ref, fiscal_acked_at,
              fiscalized_by, fiscalized_at, fiscalize_correlation_id,
              fiscal_exemption_reason)
    ON plt01.fin_invoices TO veyro_cp_app, veyro_cp_worker;

-- An invoice line is insert-only in full. What was charged is what was charged.
GRANT SELECT, INSERT ON plt01.fin_invoice_lines TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.fin_payment_intents TO veyro_cp_app, veyro_cp_worker;
-- The amount, the currency, the account, the method and the handle are fixed when the intent
-- is created -- an intent whose amount could be edited while a provider was deciding is a
-- different charge than the one authorized. The outcome columns move, and `provider_ref` moves
-- once because the provider hands it back after the attempt begins.
GRANT UPDATE (status, provider_ref, requires_authentication, authenticated_at,
              failure_code, failure_detail, settled_at, attempts)
    ON plt01.fin_payment_intents TO veyro_cp_app, veyro_cp_worker;

-- **A payment has no UPDATE grant at all.** It is money that arrived, and it is what an
-- accountant reconciles the bank statement against. A payment recorded in error is reversed by
-- a refund, which leaves both rows visible.
GRANT SELECT, INSERT ON plt01.fin_payments TO veyro_cp_app, veyro_cp_worker;

-- The refund request states what was asked, and nothing about it moves: it is the other half
-- of the separation of duties the approval compares against.
GRANT SELECT, INSERT ON plt01.fin_refund_requests TO veyro_cp_app, veyro_cp_worker;
GRANT SELECT, INSERT ON plt01.fin_refunds TO veyro_cp_app, veyro_cp_worker;
-- The amount, the approver, the requester and the reason are what was decided. Only the
-- provider outcome moves.
GRANT UPDATE (status, provider_ref, failure_code, settled_at, credit_note_invoice_id)
    ON plt01.fin_refunds TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.fin_disputes TO veyro_cp_app, veyro_cp_worker;
-- The claim is fixed: the bank made it. The response and the outcome move.
GRANT UPDATE (status, response_ref, responded_at, responded_by, outcome, closed_at)
    ON plt01.fin_disputes TO veyro_cp_app, veyro_cp_worker;

GRANT SELECT, INSERT ON plt01.fin_dunning_cases TO veyro_cp_app, veyro_cp_worker;
-- The invoice and the account do not move; the journey does.
GRANT UPDATE (stage, status, next_action_on, attempts, access_recommendation,
              last_notification_ref, owner_ref, resolution, closed_at, closed_by)
    ON plt01.fin_dunning_cases TO veyro_cp_app, veyro_cp_worker;

-- **A tax record has no UPDATE grant on anything it reports.** It is the figure a return is
-- built from. Only the export marker moves, and it is attributed.
GRANT SELECT, INSERT ON plt01.fin_tax_records TO veyro_cp_app, veyro_cp_worker;
GRANT UPDATE (exported_at, exported_by, export_ref) ON plt01.fin_tax_records
    TO veyro_cp_app, veyro_cp_worker;
