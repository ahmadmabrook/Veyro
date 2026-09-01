GYM OS
Master Product Blueprint
Version 1.0
The complete product, experience, SaaS, data, AI, security, operations and delivery blueprint for an intelligent multi-tenant gym operating system.
Product scopeComplete long-term vision
Delivery modelPhased releases with dependency gates
Primary surfacesAdmin Web, Coach App, Member App, Front Desk, Kiosk
Core architectureMulti-tenant SaaS + Gym Operating System
Prepared for product strategy, UX, architecture and execution planningAugust 2026

# Document Control
Field
Value
Document
Gym OS Master Product Blueprint
Version
1.0
Date
August 2026
Status
Master vision and planning baseline
Scope
Complete long-term product scope; phased delivery scope
Primary audience
Product, design, engineering, data, AI, security, operations, GTM and partners
Primary markets
MENA/GCC-first, globally extensible

## Scope Commitment
Master scope rule
All important product, SaaS, enterprise, operational, financial, security, compliance, data, AI, support, migration, white-label, hardware, regional and internal-control capabilities in this blueprint remain part of the approved long-term product vision. A capability may be deferred to a later release, but it is not removed from the master scope without a deliberate governance decision.

## How to Read This Blueprint
“Must” indicates a mandatory product or platform requirement in the complete vision.
A phase indicates sequencing and dependency, not whether the capability matters.
Targets in the non-functional section are initial engineering design objectives and must be validated through capacity, security and market discovery.
Legal, medical, tax, labor, biometric and privacy requirements must be reviewed for every launch jurisdiction.
UX specifications define intended behavior and quality; detailed wireframes and interaction prototypes follow this blueprint.
## Assumptions and Product Boundaries
Gym OS is a multi-tenant SaaS platform, not a single-gym custom application.
The platform serves single-location gyms, growing multi-location operators, franchises and corporate programs.
Virtuagym provides a useful breadth benchmark; Gym OS must create an original product with simpler UX, transparent business practices, deeper CRM/AI/platform capabilities and MENA/GCC-native operations.
Gym OS supports coaching and wellness operations but does not claim to diagnose or treat medical conditions.
The platform may integrate with regulated providers; provider obligations remain explicit and independently governed.

# Contents
Section
Title
1
Executive Blueprint
2
Vision, Strategy & Product Principles
3
Users, Jobs & Experience Architecture
4
Complete Domain Capability Blueprint
5
Detailed Application & UX Blueprint
6
Critical End-to-End Flows
7
Identity, Roles, Permissions & Biometrics
8
Data, Events, Automation, AI & Technical Architecture
9
SaaS Commercial & Operating Model
10
Security, Reliability & Non-functional Requirements
11
Roadmap, Dependencies & Release Gates
12
Metrics, Risks, Governance & Definition of Done
A
Requirement Traceability Register
B
Domain Event Catalog
C
Glossary & Completeness Checklist


CHAPTER 1
# Executive Blueprint
What Gym OS is, why it wins and what must remain true.
Product definition
Gym OS is the AI-native, multi-tenant operating system for gyms: one platform to acquire customers, sell memberships and services, operate locations, coach members, engage communities, retain revenue, understand performance and scale across brands, regions and partners.

## Strategic Thesis
The opportunity is not to copy a broad gym-management suite. It is to combine comparable functional completeness with a simpler role-specific experience, a unified data model, transparent commercial practices, deep CRM and automation, safe AI execution, developer-grade extensibility and native MENA/GCC operations. Gym OS should feel like one coherent operating system rather than a collection of acquired or loosely connected modules.
## Value System
Pillar
Scope
Acquire
CRM, campaigns, referrals, trials, sales pipeline and conversion intelligence.
Sell
Memberships, packages, POS, ecommerce, pricing, payments and revenue recovery.
Operate
Scheduling, access, front desk, staff, facilities, equipment and incidents.
Coach
Programming, workouts, nutrition, assessments, progress and contextual communication.
Engage
Member app, self-service, community, challenges, rewards and omnichannel messaging.
Retain
Churn signals, failed-payment recovery, no-show reduction and proactive outreach.
Understand
Operational analytics, forecasting, benchmarking and AI copilots.
Scale
Multi-tenant SaaS, multi-brand/franchise, APIs, marketplace and regional deployment.

## Core Differentiation
Role-native UX: Admin is a command center, Coach is a daily client workspace and Member is a personalized action surface.
Member 360 and one event timeline across CRM, membership, access, commerce, coaching, nutrition, communication and support.
Actionable intelligence: detect -> explain -> recommend -> approve -> execute -> measure.
Best-in-class nutrition UX: coach plan creation in about one minute and member logging in one to two taps.
Member-aware POS and commerce that understand membership, entitlements, credits, inventory, wallet and commission.
Transparent SaaS packaging, migration, onboarding and cancellation rather than surprise add-ons or contractual friction.
MENA/GCC-native Arabic RTL, WhatsApp-first workflows, regional payments/tax, family structures and local operations.
Platform rather than closed suite: APIs, webhooks, sandbox, marketplace, hardware abstraction and governed partners.
Security, privacy, biometric consent, offline resilience and enterprise control are designed in, not added later.
## Non-negotiable Product Outcomes
Audience
Required outcome
Gym staff
Operate daily work from role-specific attention queues and complete routine tasks without training-heavy navigation.
Coaches
Prepare, deliver, review and adapt coaching from one mobile workflow.
Members
Enter, book, train, eat, pay, progress and self-serve with minimal friction and clear control.
Owners
Understand business performance, causes and actions without exporting spreadsheets.
Gym OS team
Provision, support, secure, bill and evolve thousands of tenants with controlled unit economics.


CHAPTER 2
# Vision, Strategy & Product Principles
The decisions that keep a broad ecosystem coherent.
## Vision Statement
Build the trusted operating system that allows any gym - from an independent club to a regional franchise - to run its business, coach its members and grow from one intelligent platform.
## Positioning
Category
The AI Operating System for Modern Gyms

Dimension
Gym OS position
Core promise
Run the gym, coach members and grow the business from one source of truth.
UX promise
Role-specific, action-first and progressively disclosed; frequent tasks in three actions or fewer where safe.
Intelligence promise
Answers include causes, confidence and governed next actions - not charts or text alone.
Business promise
Transparent packaging, reliable migration, predictable support and customer-owned data.
Regional promise
Arabic/RTL, WhatsApp, local payments/tax and MENA/GCC operating realities are first-class.

## Product Principles
1. One member, one identity, one timeline and one source of truth across every surface.
2. The system detects, prioritizes and recommends; users should not hunt through modules for work.
3. Frequent tasks should complete in three primary actions or fewer whenever risk permits.
4. Progressive disclosure: simple by default, powerful on demand.
5. Management by exception: surface deviations, risks and approvals instead of activity noise.
6. Self-service first, with staff override and a complete audit trail.
7. Tenant isolation, least privilege and privacy by design from the first line of code.
8. AI assists and executes only within permissions, confidence thresholds and approval policies.
9. Offline-safe critical paths for access, check-in and front-desk commerce.
10. Arabic/RTL, accessibility and localization are architecture concerns, not translation tasks.
11. Every important state change emits a durable domain event.
12. Complete product scope is preserved, while release scope remains ruthlessly phased.
## Business Model Principles
Core workflows should not be artificially fragmented into surprise add-ons.
Plans differ primarily by scale, governance, brand, data/AI usage and enterprise controls.
Cost-intensive services such as AI, messages, storage and branded app operations may be metered transparently.
Contracts, renewal, notice, cancellation and data export must be understandable before purchase.
Migration, implementation and support are productized capabilities with measurable quality.
Enterprise exceptions become reusable configuration or extensions, not private forks.
## Scope Governance
Layer
Meaning
Decision rule
Master Product Scope
All capabilities required for the complete ecosystem and SaaS business.
Remove only by explicit governance decision.
Release Scope
Capabilities committed to a specific delivery wave.
Controlled by dependencies, outcome and risk gates.
Tenant Configuration
What a plan/tenant enables or customizes.
No code fork; validated configuration and entitlement.
Experiment
Controlled test of a hypothesis or interaction.
Guardrails, exposure events and stop criteria required.


CHAPTER 3
# Users, Jobs & Experience Architecture
One platform, multiple role-native surfaces.
## Primary Personas and Jobs
Persona
Primary job to be done
Gym Owner / Founder
Needs revenue, growth, retention, cash visibility and trusted controls across the business.
Regional / Franchise Leader
Compares locations, enforces standards, manages exceptions and allocates resources.
Club Manager
Runs daily operations, people, schedules, incidents, targets and approvals.
Reception / Front Desk
Needs fast check-in, member resolution, booking, payment and sales workflows.
Sales Representative
Needs prioritized leads, omnichannel history, next actions, offers and conversion tracking.
Coach / Personal Trainer
Needs today view, client context, programs, sessions, progress and exception alerts.
Nutritionist
Needs safe client context, rapid plan creation, adherence insight and contextual changes.
Member
Wants effortless access, bookings, training, nutrition, progress, payments and support.
Parent / Household Manager
Manages dependents, permissions, shared payment and family bookings.
Corporate Benefits Admin
Manages eligibility, enrollment, utilization, invoices and reporting.
Finance / Accountant
Needs invoices, tax, immutable ledger, reconciliation, exports and controls.
Inventory / Operations Manager
Controls catalog, stock, suppliers, transfers, wastage, assets and maintenance.
Tenant IT / Security Admin
Configures SSO, SCIM, policies, integrations, devices and audit access.
Gym OS Support / Customer Success
Diagnoses tenants safely, drives adoption, supports incidents and prevents churn.
Developer / Integration Partner
Needs stable APIs, sandbox, scopes, webhooks, logs, documentation and certification.

## Product Surfaces
Surface
Purpose
Admin Web
Command center for growth, operations, finance, people, analytics, configuration and enterprise controls.
Coach App
Mobile-first daily workflow for clients, sessions, training, nutrition, progress and messaging.
Member App
Personalized home, access, bookings, training, nutrition, progress, commerce and self-service.
Front Desk Mode
High-speed check-in, member lookup, problem resolution, sales, booking and cash-shift operations.
Kiosk
Unattended check-in, waiver, trial/day-pass purchase, guest registration and basic self-service.
Corporate Portal
Eligibility, employee enrollment, benefit utilization, invoices and aggregate reporting.
Internal SaaS Console
Tenant lifecycle, subscriptions, support, diagnostics, feature flags, incidents, cost and system health.
Developer Portal
API keys, OAuth applications, scopes, sandbox, webhooks, logs, documentation and marketplace submission.
Device / Edge Runtime
Turnstiles, scanners, biometric terminals, kiosks, POS devices and offline synchronization.

## Experience Architecture
Layer
Responsibility
Experience Layer
Role-specific web, mobile, kiosk, front-desk and partner experiences.
Domain Services
Gym business capabilities with explicit ownership, invariants and APIs.
Workflow & Intelligence
Automation, approvals, tasks, search, analytics and AI agents.
Commerce & Financial Control
Catalog, pricing, orders, payments, invoices, ledger, wallet and reconciliation.
Identity, Tenancy & Policy
Tenant isolation, authentication, authorization, consent, entitlements and audit.
Data & Integration
Operational data, events, warehouse, APIs, webhooks, integrations and hardware abstraction.
Platform Reliability
Queues, jobs, storage, observability, security, offline support, backup and disaster recovery.

## Cross-surface Continuity
A lead becomes a member without losing attribution, conversation or trial history.
A membership sale immediately updates payment, ledger, entitlements, access, app and timeline.
A coach change appears in the member experience with the exact assigned plan version.
A member meal question opens for the coach with the meal, target and plan context attached.
A front-desk resolution updates the same source of truth used by billing, access and self-service.
AI, search, analytics and automation respect the same permission and data ownership model as the UI.

CHAPTER 4
# Complete Domain Capability Blueprint
57 governed domains covering the product and the SaaS business.
Domain rule
Each domain has an accountable owner, authoritative data, invariants, permission policy, event contract, quality tests, metrics and operational runbook. Domain boundaries are product and governance boundaries, not merely code folders.

## Core SaaS Platform & Identity
### PLT-01  Tenant, Organization, Brand & Location Management
Provide the isolation and organizational hierarchy on which every product and SaaS capability depends.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Internal SaaS Console; Admin Web; APIs
Dependencies
Platform foundation
Core entities
Tenant, Organization, LegalEntity, Brand, Region, Location, Department, CostCenter, TenantConfiguration
Key events
tenant.provisioned, tenant.activated, tenant.suspended, organization.updated, location.opened, brand.created

#### Required capabilities
1. Provision, activate, suspend, archive and delete tenants through a controlled lifecycle.
2. Model organization, legal entity, brand, region, location, department and cost-center hierarchies.
3. Enforce tenant-aware identifiers, storage paths, search indexes, events, caches, logs and background jobs.
4. Support tenant templates, cloning, defaults, regional settings and configuration inheritance.
5. Provide data residency, deployment-region and encryption-key assignment policies.
6. Allow multi-brand ownership with separate branding, catalogs, pricing, domains, applications and policies.
7. Maintain tenant lifecycle history and prevent hard deletion before legal, billing and retention gates pass.
Critical controls
Required outcomes
No cross-tenant query, cache, file, event or search result is permitted.
New tenant can be ready with secure defaults in minutes.
Destructive lifecycle actions require approvals, retention checks and an immutable audit record.
A chain can manage multiple brands and regions without duplicated data or custom code.

### PLT-02  Configuration, Feature Flags & Experimentation
Allow safe variation by tenant, plan, brand, location, role, cohort and release channel without custom forks.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Internal SaaS Console; Admin Web; Mobile Apps
Dependencies
PLT-01
Core entities
ConfigurationDefinition, ConfigurationValue, FeatureFlag, TargetingRule, Experiment, Variant, Exposure
Key events
configuration.changed, feature_flag.evaluated, experiment.exposed, experiment.completed

#### Required capabilities
1. Typed configuration registry with defaults, validation, ownership, versioning and inheritance.
2. Feature flags targeted by environment, tenant, plan, brand, location, user, role and percentage rollout.
3. Kill switches for risky integrations, AI actions, payments, hardware and communications.
4. Experiment assignment, exposure events, metrics, guardrails and statistical decision records.
5. Configuration preview, impact analysis, approval and rollback.
6. Remote configuration for mobile applications, kiosks and managed devices.
Critical controls
Required outcomes
Financial, security and access-control flags require owner approval and change windows.
Release risk is reduced through controlled rollout and rapid rollback.
Every evaluation remains tenant-safe and every change is reversible.
Enterprise differences are configuration, not code forks.

### PLT-03  SaaS Plans, Subscription Billing, Metering & Entitlements
Commercialize Gym OS itself with transparent plans, usage controls, invoicing and revenue protection.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Internal SaaS Console; Tenant Billing Portal; Finance
Dependencies
PLT-01, PLT-02
Core entities
SaaSPlan, SaaSPrice, SaaSSubscription, SaaSInvoice, UsageMeter, UsageRecord, EntitlementGrant, Quota
Key events
saas.subscription.started, saas.subscription.changed, saas.usage.recorded, saas.quota.reached, saas.payment.failed

#### Required capabilities
1. Plan catalog with editions, add-ons, trial policies, contract terms, currencies and regions.
2. Monthly, annual and contractual subscriptions with upgrades, downgrades, proration and scheduled changes.
3. Entitlements for locations, active members, staff, white-label apps, AI, storage, messages, API and integrations.
4. Usage metering, aggregation, late-event handling, corrections, quotas, overages and fair-use rules.
5. Trial conversion, dunning, grace periods, suspension, reactivation and offboarding coordination.
6. SaaS invoices, tax, credit notes, payment methods, partner/reseller attribution and revenue share.
7. Tenant cost and gross-margin view across cloud, AI, messaging, storage, support and third parties.
Critical controls
Required outcomes
Metering records are idempotent, attributable and auditable.
Pricing aligns revenue with customer value and controllable cost.
A plan change may never silently remove operationally critical tenant data.
Tenants understand limits before reaching them and receive safe upgrade paths.

### PLT-04  Internal Administration, Support & Customer Success
Operate thousands of tenants safely with diagnostics, support controls, adoption insight and lifecycle tooling.
Attribute
Definition
Delivery phase
Pilot
Primary surfaces
Internal SaaS Console
Dependencies
PLT-01, PLT-02, PLT-03, SEC-01
Core entities
TenantHealth, SupportSession, SupportTicket, SuccessPlan, ImplementationProject, Renewal, Risk, TenantDiagnostic
Key events
tenant.health.changed, support.session.started, support.ticket.escalated, renewal.risk.detected

#### Required capabilities
1. Global tenant search and 360 view covering plan, usage, health, incidents, integrations, adoption and contacts.
2. Permission-safe support impersonation with reason, approval, time limit, visible banner and full audit.
3. Tenant diagnostics for jobs, webhooks, devices, payments, messaging, storage, mobile versions and configuration.
4. Customer health score using activation, adoption, support, usage, billing, sentiment and risk signals.
5. Implementation, success-plan, renewal, expansion, risk and executive-review workspaces.
6. Support tickets, SLAs, escalation, knowledge links, incident linkage and post-resolution feedback.
7. Bulk tenant communication, maintenance notices, release notes and deprecation notices.
Critical controls
Required outcomes
Support staff never receive standing access to customer data.
Lower support cost per tenant and faster resolution.
Sensitive actions require explicit tenant consent or documented emergency procedure.
Customer success acts before adoption or renewal risk becomes churn.

### IAM-01  Identity, Authentication, Passkeys & Device Sessions
Provide secure, low-friction authentication for members, staff, tenant administrators, partners and internal users.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
All Apps; Admin Web; Developer Portal
Dependencies
PLT-01
Core entities
Identity, Credential, Passkey, MFAFactor, Session, Device, FederationConnection, RecoveryMethod
Key events
identity.created, authentication.succeeded, authentication.failed, session.revoked, passkey.registered, risk.challenge.required

#### Required capabilities
1. Identity model that can link one person to multiple tenant roles without identity duplication.
2. Email/phone login, OTP, password, passkeys and platform biometric unlock through operating-system APIs.
3. MFA, step-up authentication, recovery codes, trusted devices and risk-based challenges.
4. Enterprise federation through OIDC/SAML and lifecycle provisioning through SCIM.
5. Session inventory, device binding, remote revocation, token rotation and suspicious-login detection.
6. Separate authentication assurance levels for routine, financial, privileged and biometric-sensitive actions.
7. Account linking, duplicate detection, merge review and identity recovery without losing tenant data.
Critical controls
Required outcomes
Biometric templates from Apple Face ID/Touch ID never leave the user device.
Fast daily access with reduced password dependence.
Recovery and support procedures cannot bypass tenant authorization without exceptional audit.
Enterprise identity requirements are supported without separate products.

### IAM-02  Biometric Identity & Physical Access Methods
Support optional biometric gym entry and alternative access methods with consent, liveness and privacy controls.
Attribute
Definition
Delivery phase
V2 Platform
Primary surfaces
Member App; Front Desk; Access Device; Admin Web
Dependencies
IAM-01, OPS-03, SEC-01, ECO-03
Core entities
BiometricEnrollment, BiometricTemplateRef, AccessCredential, WalletPass, LivenessCheck, ConsentRecord
Key events
biometric.enrolled, biometric.revoked, liveness.failed, access_credential.issued, wallet_pass.updated

#### Required capabilities
1. Member-controlled enrollment for facial entry with explicit informed consent and clear alternatives.
2. Vendor-neutral biometric templates, encrypted storage, retention policy, revocation and deletion workflow.
3. Liveness detection, match thresholds, anti-spoofing, retry limits and manual fallback.
4. QR, NFC, Apple Wallet, Google Wallet, physical card and temporary credential support.
5. Separate enrollment and policies for member access, staff attendance and high-security zones.
6. Identity Center showing methods, devices, consent, recent access and the ability to revoke.
7. Edge decision support for low-latency entry with secure synchronization and central policy validation.
Critical controls
Required outcomes
Biometric access is opt-in and never the only access method.
Hands-free, fast and secure entry for consenting members.
Raw enrollment imagery is minimized and deleted according to documented policy.
Privacy expectations and regional biometric laws remain enforceable.

### IAM-03  Authorization, Roles, Permissions, Approvals & Audit
Ensure every read, write, search result, AI action and support operation follows explicit policy and traceability.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
All Surfaces
Dependencies
PLT-01, IAM-01
Core entities
Role, Permission, Policy, Scope, Assignment, ApprovalRequest, AuditEvent, AccessReview
Key events
role.assigned, permission.denied, approval.requested, approval.completed, audit_event.recorded

#### Required capabilities
1. Tenant-scoped RBAC with custom roles, permission bundles and location/brand scope.
2. Attribute- and relationship-based policies for assigned clients, sensitive notes, minors and health data.
3. Field-level masking for financial, biometric, health, identity and contact attributes.
4. Delegation, temporary access, break-glass access and separation-of-duties policies.
5. Approval policies by amount, risk, role, location and action type.
6. Immutable audit for authentication, data access, configuration, finance, access, AI and support.
7. Permission simulator and access review/certification for enterprise administrators.
Critical controls
Required outcomes
Default deny and least privilege are mandatory.
Sensitive data and actions remain appropriately separated.
Audit records are write-once, integrity-protected and retention-controlled.
Enterprise customers can prove and review access governance.

## People, CRM & Growth
### PPL-01  People, Profiles & Member 360
Create the canonical person and relationship model that unifies lead, member, staff, coach, dependent and contact history.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Admin Web; Coach App; Member App; Front Desk
Dependencies
PLT-01, IAM-01, IAM-03, DAT-01
Core entities
Person, TenantProfile, MemberProfile, StaffProfile, Relationship, ContactPoint, TimelineEntry, Tag, CustomField
Key events
person.created, profile.updated, member.lifecycle.changed, person.merged, relationship.created

#### Required capabilities
1. Canonical person record with tenant-specific profiles and role relationships.
2. Member 360 covering lifecycle, membership, entitlements, attendance, bookings, coaching, nutrition, progress, finance, messages, consent and support.
3. Unified chronological timeline built from domain events with permission-aware visibility.
4. Duplicate detection and merge workflow using identity, contact and contextual signals.
5. Tags, segments, custom fields and data-quality indicators governed by schema and permissions.
6. Relationship graph for coach-client, guardian-dependent, company-employee, referrer-referred and household.
7. Privacy controls for preferred name, contact channels, sensitive notes, progress media and minors.
Critical controls
Required outcomes
Each data attribute has one authoritative owner and defined visibility.
Every team sees the right context without duplicate records.
Merges are reviewable, reversible where feasible and fully audited.
Member service becomes faster and more personal across channels.

### PPL-02  Households, Dependents, Guests & Eligibility
Support real-world membership relationships including families, minors, guardians, corporate eligibility and temporary visitors.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Member App; Admin Web; Front Desk; Corporate Portal
Dependencies
PPL-01, IAM-03, COM-01, OPS-03
Core entities
Household, HouseholdMember, GuardianGrant, Dependent, Eligibility, GuestPass, TrialVisit, Sponsor
Key events
household.created, dependent.added, eligibility.verified, guest_pass.issued, trial.converted

#### Required capabilities
1. Household account with shared payment methods, wallet rules, family plan and consolidated statements.
2. Guardian permissions, consent, pickup rules and booking controls for minors and dependents.
3. Corporate eligibility verification by roster, code, domain, API or identity provider.
4. Guest, trial and day-pass profiles with sponsor, access window, waiver, lead conversion and abuse limits.
5. Relationship-specific communication, privacy and financial permissions.
6. Dependent aging and eligibility-change workflows without losing history.
Critical controls
Required outcomes
Guardianship and consent must be validated before exposing minor data.
Family and youth programs operate without manual workarounds.
Temporary access expires automatically and cannot silently become permanent.
Guests and corporate users enter through controlled, measurable funnels.

### GRO-01  CRM, Leads, Sales Pipeline & Trials
Turn acquisition into a measurable, prioritized and omnichannel sales workflow embedded in the core product.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Admin Web; Front Desk; Mobile Staff
Dependencies
PPL-01, ENG-01, OPS-01, COM-02
Core entities
Lead, Opportunity, Pipeline, Stage, SalesActivity, Trial, Offer, LossReason, Attribution
Key events
lead.created, lead.assigned, trial.booked, trial.attended, offer.sent, opportunity.won, opportunity.lost

#### Required capabilities
1. Lead capture from forms, ads, referrals, walk-ins, imports, APIs, partners and corporate lists.
2. Configurable pipelines and stages with required fields, probability, ownership and service-level timers.
3. Lead scoring using source, intent, engagement, demographics, response and historical conversion.
4. Unified calls, WhatsApp, SMS, email, notes, tasks and appointment history.
5. Trial, tour and assessment booking with reminders, attendance and conversion follow-up.
6. Offers, quotes, proposal expiry, objection/loss reason and membership conversion.
7. Duplicate prevention and lead-to-member merge preserving attribution and history.
8. Sales dashboards for response time, stage aging, conversion, source ROI and representative performance.
Critical controls
Required outcomes
Marketing consent and channel opt-in are evaluated before outreach.
Faster first response and higher trial-to-membership conversion.
Automated scoring informs prioritization but never hides leads from authorized review.
Every membership sale retains source and campaign attribution.

### GRO-02  Marketing, Referrals, Offers & Growth Journeys
Coordinate permission-aware acquisition, activation, referral, upsell and win-back journeys across channels.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Admin Web; Member App; Communication Channels
Dependencies
GRO-01, ENG-02, AUT-01, COM-02, SEC-02
Core entities
Audience, Segment, Campaign, Journey, Referral, ReferralReward, Offer, AttributionWindow, ConsentSuppression
Key events
campaign.launched, message.delivered, referral.created, referral.qualified, offer.redeemed, journey.completed

#### Required capabilities
1. Audience builder using lifecycle, membership, attendance, spending, coaching, engagement, location and risk.
2. Campaign orchestration across email, push, SMS, WhatsApp and in-app placements.
3. Referral links, codes and QR with sponsor tracking, fraud checks, qualification and rewards.
4. Lifecycle journeys for onboarding, first visit, inactivity, expiration, birthday, milestone and win-back.
5. Offer eligibility, frequency caps, suppression, holdout groups and attribution windows.
6. Landing pages and lead forms governed by brand and localization settings.
7. Incrementality and conversion reporting instead of message-open metrics alone.
Critical controls
Required outcomes
Channel preferences, quiet hours and regulatory consent are mandatory.
Lower acquisition cost and measurable member-led growth.
Referral and promotion abuse is detected before reward settlement.
Campaigns optimize business outcomes, not notification volume.

## Membership, Finance & Commerce
### COM-01  Memberships, Contracts, Entitlements & Lifecycle
Model the commercial agreement and the operational rights a member receives throughout its lifecycle.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Admin Web; Member App; Front Desk; Access Control
Dependencies
PPL-01, COM-02, COM-03, IAM-03
Core entities
MembershipProduct, MembershipAgreement, Membership, Entitlement, EntitlementPolicy, Freeze, LifecycleChange, ContractVersion
Key events
membership.created, membership.activated, membership.frozen, membership.changed, membership.renewed, membership.cancelled, entitlement.changed

#### Required capabilities
1. Fixed-term, recurring, installment, prepaid, off-peak, family, student, corporate, class-credit and unlimited memberships.
2. Contract version, signature, start/end, minimum term, notice, renewal and cancellation policy.
3. Entitlements for locations, schedules, zones, classes, facilities, services, guest passes, discounts and digital content.
4. Freeze, pause, medical hold, upgrade, downgrade, transfer, renewal, cancellation and reinstatement with effective dating.
5. Proration, credit carryover, expiry extension, grace period and access consequences.
6. Member self-service request policies with eligibility checks, fee disclosure and approval where required.
7. Full state history and “as-of” reconstruction for disputes and audits.
Critical controls
Required outcomes
Membership state, billing state and access state are related but never conflated.
Complex plans operate consistently across sales, access, booking and billing.
Lifecycle calculations are deterministic, effective-dated and auditable.
Members understand consequences before confirming changes.

### COM-02  Catalog, Pricing, Promotions & Packages
Provide a single commercial catalog for memberships, services, credits, retail goods, digital products and bundles.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Admin Web; POS; Member App; CRM
Dependencies
PLT-01, IAM-03
Core entities
Product, ProductVariant, Bundle, PriceBook, Price, Promotion, Coupon, EligibilityRule, TaxCategory
Key events
product.published, price.changed, promotion.activated, coupon.redeemed, bundle.fulfilled

#### Required capabilities
1. Product types for membership, service, session credit, class credit, retail SKU, subscription add-on, event and gift card.
2. Price books by brand, location, channel, currency, tax regime, customer segment and effective date.
3. Bundles linking commercial sale to operational fulfillment and entitlements.
4. Coupons, automatic promotions, corporate rates, member tiers, staff discounts and manual discount policy.
5. Eligibility, stacking, usage limits, minimum spend, blackout dates and approval thresholds.
6. Localized names, media, descriptions, terms, availability and merchandising order.
7. Versioned price changes that do not rewrite historical transactions.
Critical controls
Required outcomes
Pricing resolution is deterministic and returns an explanation.
One catalog drives every sales channel consistently.
Manual price overrides and high discounts require explicit permission and audit.
Pricing changes safely without corrupting history or entitlements.

### COM-03  Member Billing, Payments, Tax & Revenue Recovery
Collect and recover member revenue across recurring, installment, one-time and in-person scenarios.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Admin Web; Member App; POS; Finance
Dependencies
COM-01, COM-02, IAM-03, ECO-02
Core entities
BillingAccount, BillingSchedule, Invoice, InvoiceLine, PaymentIntent, Payment, Refund, Dispute, DunningCase, TaxRecord
Key events
invoice.issued, payment.succeeded, payment.failed, dunning.started, refund.completed, chargeback.opened

#### Required capabilities
1. Billing schedules, recurring invoices, installments, deposits, due dates and consolidated household/corporate billing.
2. Payment orchestration for cards, direct debit, bank transfer, cash, wallet, gift card and local gateways.
3. Tokenized stored payment methods, 3DS/SCA handling, retries and payment-method updates.
4. Dunning journeys with retry schedule, grace period, member communication, task escalation and access policy.
5. Invoices, receipts, tax calculation, credit notes, refunds, disputes and chargebacks.
6. Provider abstraction, idempotent commands, webhook verification and payment-status reconciliation.
7. Regional taxation, invoice numbering, fiscalization hooks and accounting export.
Critical controls
Required outcomes
Payment data uses tokenization; sensitive card data never enters Gym OS systems unless explicitly certified.
Higher successful collection and transparent member billing.
Refunds, voids and write-offs follow limits, approvals and ledger entries.
Payment-provider changes do not force product redesign.

### COM-04  Financial Ledger, Wallet, Credits & Reconciliation
Create an immutable financial source of truth for money, credits, liabilities and provider settlement.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Finance; POS; Member App; Admin Web
Dependencies
COM-03, IAM-03
Core entities
LedgerAccount, LedgerEntry, Posting, Wallet, WalletTransaction, ServiceCredit, Settlement, ReconciliationCase, FinancialPeriod
Key events
ledger.posted, wallet.credited, wallet.debited, credit.consumed, settlement.imported, reconciliation.mismatch.detected

#### Required capabilities
1. Double-entry or equivalent immutable posting model for sales, payments, refunds, fees, wallet and credits.
2. Member wallet with cash value, promotional value, referral credit, refund credit and expiry policy.
3. Separate non-monetary service credits such as PT sessions, classes, guest passes and assessments.
4. Provider settlement import and automated matching to payments, fees, refunds and chargebacks.
5. Cash drawer, bank deposit and payout reconciliation with discrepancy workflows.
6. Financial periods, lock controls, correction entries and export to accounting systems.
7. Statements and balances reconstructed from entries rather than mutable totals.
Critical controls
Required outcomes
Posted financial entries are never edited or deleted; corrections use compensating entries.
Finance can explain every balance and reconcile every provider.
Promotional, refundable and cash-equivalent balances remain distinct.
Wallet and credits operate safely across channels and locations.

### COM-05  Point of Sale, Ecommerce & Order Fulfillment
Unify in-club and digital commerce while preserving member context, inventory, entitlements and financial control.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Front Desk; Member App; Coach App; Admin Web
Dependencies
COM-02, COM-03, COM-04, COM-06, PPL-01
Core entities
Cart, Order, OrderLine, Tender, POSRegister, CashShift, Return, Receipt, Fulfillment
Key events
cart.created, order.completed, cash_shift.opened, return.completed, receipt.sent, fulfillment.completed

#### Required capabilities
1. Fast member-aware checkout: identify member, tap/scan product, pay and complete.
2. Guest checkout with optional lead/member conversion and receipt capture.
3. Barcode scanning, favorites, category tiles, search, recent items and configurable quick actions.
4. Cash, card, wallet, saved method, gift card and split-tender payments.
5. Sell memberships, upgrades, PT packages, classes, nutrition, events, merchandise and digital products from one cart.
6. Automatic member pricing, included-benefit detection, tax, discount policy and approval.
7. Returns, partial refunds, exchanges, store credit, voids and reason codes.
8. Orders from member app/web shop with pickup, digital fulfillment or future delivery.
9. Cash shift opening, paid-in/out, drawer count, expected/actual difference and manager close.
Critical controls
Required outcomes
Price overrides, discounts, refunds and cash adjustments follow permission limits.
Most daily sales finish in three to four interactions.
Order completion is idempotent and fulfillment cannot silently duplicate.
One order model supports physical, service and digital products.

### COM-06  Inventory, Purchasing, Suppliers & Stock Control
Control stock, cost, expiry, purchasing and movement across locations and sales channels.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Admin Web; POS; Warehouse Mobile
Dependencies
COM-02, IAM-03
Core entities
SKU, InventoryItem, StockPosition, Lot, Supplier, PurchaseOrder, GoodsReceipt, StockTransfer, StockCount
Key events
stock.received, stock.reserved, stock.adjusted, stock.transferred, stock.low, lot.expiring

#### Required capabilities
1. SKU, barcode, variant, unit, lot, expiry, supplier, cost, selling price and tax category.
2. On-hand, available, reserved, in-transit, damaged and quarantined quantities by location.
3. Purchase requisition, approval, purchase order, receiving, variance and supplier invoice matching.
4. Inter-location transfer, cycle count, stock adjustment, wastage and reason-coded shrinkage.
5. Reorder points, suggested purchasing, sales velocity and expiry-risk alerts.
6. Cost history, margin, landed cost and valuation export.
7. Inventory reservations linked to orders and fulfillment.
Critical controls
Required outcomes
Inventory adjustments require reason, actor and approval above threshold.
Fewer stockouts, lower waste and reliable gross margin.
Expired or quarantined stock cannot be sold.
Multi-location inventory is visible and transferable in real time.

## Gym Operations
### OPS-01  Scheduling, Resources & Capacity
Provide one scheduling engine for classes, PT, consultations, assessments, facilities, rooms, courts and equipment.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Admin Web; Coach App; Member App
Dependencies
PLT-01, PPL-01, IAM-03, COM-01
Core entities
Resource, Availability, ScheduleTemplate, ScheduledInstance, RecurrenceRule, CapacityPolicy, Substitution
Key events
schedule.published, session.created, session.changed, resource.conflict.detected, instructor.substituted

#### Required capabilities
1. Resource model for staff, room, zone, court, equipment, service and composite requirements.
2. One-time and recurring schedules with templates, exceptions, seasonality and time-zone correctness.
3. Availability, working hours, breaks, time off, substitutions and cross-location travel buffers.
4. Capacity, setup/cleanup time, age/skill restrictions, equipment requirements and entitlement checks.
5. Conflict detection and resolution for people, space, equipment and policies.
6. Schedule publishing, draft changes, member impact preview and notification plan.
7. Instructor substitution, cancellation, relocation and attendance handoff.
Critical controls
Required outcomes
All schedule changes are effective-dated and impact-assessed before publication.
One calendar coordinates every bookable service and resource.
Resource conflicts cannot be overridden without permission and reason.
Staff and members receive reliable, localized schedules.

### OPS-02  Booking, Waitlist & No-show Intelligence
Make booking simple for members while maximizing utilization and enforcing fair operational policies.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Member App; Admin Web; Front Desk; Coach App
Dependencies
OPS-01, COM-01, ENG-02, COM-04
Core entities
Booking, WaitlistEntry, BookingPolicy, Cancellation, NoShowRecord, Appeal, AttendanceIntent
Key events
booking.created, booking.cancelled, waitlist.joined, waitlist.promoted, no_show.recorded, booking.checked_in

#### Required capabilities
1. Book, reschedule, cancel and recurring booking across eligible services and resources.
2. Booking windows, cancellation windows, lead time, capacity, quotas, priority and membership eligibility.
3. Waitlist position, automatic promotion, timed confirmation, fallback and member preferences.
4. No-show and late-cancel policy with fee, credit loss, warning, strike and appeal.
5. Predictive no-show score used for reminders and controlled overbooking, never opaque denial.
6. Calendar synchronization, reminders, check-in linkage and attendance completion.
7. Group, household, guest and corporate booking with permission and eligibility rules.
Critical controls
Required outcomes
Booking decisions return an understandable eligibility or denial explanation.
Higher class utilization and fewer empty reserved spots.
Predictive scoring may influence communication and capacity strategy but not discriminate unlawfully.
Members receive fast, fair and transparent booking behavior.

### OPS-03  Check-in, Access Control & Entitlement Decisions
Make physical access fast and reliable while enforcing membership, location, time, zone and risk policies.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Access Device; Front Desk; Admin Web; Member App
Dependencies
COM-01, IAM-01, ECO-03, REL-01
Core entities
AccessPoint, AccessZone, AccessPolicy, AccessDecision, AccessEvent, CredentialBinding, Occupancy
Key events
access.requested, access.granted, access.denied, access.overridden, occupancy.changed, device.offline

#### Required capabilities
1. Real-time decision pipeline: identify person, resolve credential, evaluate entitlement and policy, then actuate device.
2. QR, NFC, wallet pass, card, PIN, staff-assisted and optional biometric credentials.
3. Rules for location, zone, hours, membership state, capacity, outstanding balance, freeze, age and safety flags.
4. Configurable grace and exception policies with staff override, reason and approval.
5. Offline entitlement cache, signed policy snapshots, duplicate-entry protection and eventual synchronization.
6. Live occupancy, entry/exit events, anti-passback and emergency unlock integration.
7. Privacy-safe welcome/failure display and immediate fallback path.
Critical controls
Required outcomes
Offline access uses time-limited signed data and risk-bounded policy.
Fast entry with auditable policy enforcement.
Access denial never reveals sensitive financial or health information publicly.
The club continues operating during temporary connectivity loss.

### OPS-04  Front Desk, Kiosk, Guest & Visitor Operations
Provide a dedicated operational experience for high-volume arrival, resolution, sales and visitor workflows.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Front Desk; Kiosk; Admin Web
Dependencies
PPL-01, PPL-02, OPS-02, OPS-03, COM-05
Core entities
FrontDeskSession, Arrival, Visitor, WalkIn, KioskSession, ResolutionCase, Handoff
Key events
arrival.detected, visitor.registered, waiver.signed, front_desk.case.resolved, handoff.created

#### Required capabilities
1. Live arrivals with identity, membership/access status, alerts and next best action.
2. Fast global member search by name, phone, ID, QR, card or recent visit.
3. Resolve expired/frozen membership, failed payment, booking, waiver, guest or credential issue in context.
4. Walk-in, trial, day pass and guest registration with waiver, identity, payment and lead creation.
5. Reception mode combining check-in, bookings, POS, member actions and operational alerts.
6. Kiosk mode for unattended check-in, renewal, day pass, waiver and guest registration.
7. Queue and handoff support for escalations to sales, manager, coach or finance.
Critical controls
Required outcomes
Kiosk data is minimized, automatically cleared and protected from shoulder surfing.
Reception handles the majority of issues without navigating the full admin system.
Staff overrides are permissioned, reason-coded and time-bounded.
Guest traffic becomes measurable sales opportunity rather than anonymous footfall.

### OPS-05  Staff, Shifts, Attendance, Payroll & Commissions
Manage the workforce, labor obligations, performance and compensation required to operate gyms consistently.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Admin Web; Coach App; Staff Kiosk
Dependencies
PPL-01, IAM-03, OPS-01, COM-04
Core entities
Staff, Employment, Qualification, Shift, TimeEntry, Leave, CompensationRule, Commission, PayrollRun
Key events
staff.onboarded, shift.started, time_entry.corrected, session.verified, commission.earned, payroll.approved

#### Required capabilities
1. Staff profile, employment/contract relationship, location assignment, qualifications and document expiry.
2. Shift planning, availability, clock-in/out, break, overtime, leave and substitution.
3. Optional biometric attendance separated from member-access enrollment and policy.
4. Coach session completion, class delivery, sales, lead handling, tasks, NPS and retention metrics.
5. Compensation rules for base, hourly, per-session, class, tiered commission, bonus and deduction.
6. Payroll preview, exception review, approval, lock and export to payroll/accounting.
7. Separation between performance coaching and protected HR information.
Critical controls
Required outcomes
Payroll-affecting corrections require reason, approval and locked-period controls.
Accurate compensation with fewer disputes and spreadsheets.
Local labor requirements are configurable and reviewed regionally.
Managers understand capacity and performance without exposing protected HR data.

### OPS-06  Facilities, Equipment, Assets & Maintenance
Keep physical clubs safe, available and cost-efficient through asset, issue and maintenance workflows.
Attribute
Definition
Delivery phase
V2 Platform
Primary surfaces
Admin Web; Member App; Staff Mobile; Partner Portal
Dependencies
PLT-01, AUT-02, ENG-02, OPS-01
Core entities
Asset, Facility, AssetLabel, Inspection, MaintenancePlan, Issue, WorkOrder, Downtime, ServiceProvider
Key events
asset.registered, issue.reported, asset.isolated, work_order.created, maintenance.completed, facility.closed

#### Required capabilities
1. Asset register for equipment, rooms, zones, lockers, access devices, kiosks and POS hardware.
2. QR/NFC asset labels for member/staff issue reporting and technician context.
3. Preventive maintenance schedules, inspection checklists, warranties, service contracts and compliance dates.
4. Issue triage, severity, safety isolation, work order, parts, downtime and resolution evidence.
5. Facility closure or capacity impact synchronized to booking, access and communication.
6. Asset utilization, downtime, maintenance cost and replacement forecasting.
7. Supplier/technician portal or limited-access workflow for assigned work.
Critical controls
Required outcomes
Safety-critical assets can be immediately isolated from use and booking.
Lower downtime and safer member experience.
Maintenance evidence and compliance records follow retention policy.
Capital replacement decisions use real cost and utilization data.

## Coaching, Nutrition, Progress & Safety
### COA-01  Coach Workspace & Client Management
Give coaches a focused mobile operating system for daily work instead of a reduced copy of the admin product.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Coach App; Admin Web
Dependencies
PPL-01, OPS-01, OPS-02, IAM-03, ENG-01
Core entities
CoachAssignment, CoachClient, CoachTask, CoachingSession, SessionNote, ClientAlert, PaymentRequest
Key events
coach.assigned, session.started, session.completed, client.attention.required, coach_note.created

#### Required capabilities
1. Today view with upcoming sessions, preparation context, tasks, changes and clients needing attention.
2. Assigned client roster, search, lifecycle status, goals, restrictions, program and recent activity.
3. Client 360 subset scoped to coaching relationship and sensitive-data permissions.
4. Session preparation, attendance, notes, exercises, measurements, follow-up and credit consumption.
5. Coach tasks generated from plan end, inactivity, pain report, missed targets, check-in or member request.
6. Contextual messaging tied to client, workout, meal, assessment or session.
7. Mobile sales of approved coaching products or secure payment-request handoff to the member.
8. Offline read access to today schedule and safe queued notes where policy allows.
Critical controls
Required outcomes
Coaches only see clients and sensitive fields authorized by relationship and policy.
Coaches spend less time on administration and more on client outcomes.
Session credit consumption requires attendance evidence and dispute workflow.
Managers can see delivery quality without micromanaging every action.

### COA-02  Training Programs, Workouts & Exercise Logging
Support high-quality programming, assignment, execution and progression for coached and self-directed training.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Coach App; Member App; Admin Web
Dependencies
COA-01, PPL-01, COA-05, DAT-01
Core entities
Exercise, ExerciseVariant, ProgramTemplate, Program, TrainingBlock, Workout, ExercisePrescription, WorkoutLog, SetLog, PersonalRecord
Key events
program.assigned, workout.started, set.logged, workout.completed, personal_record.achieved, program.adjusted

#### Required capabilities
1. Exercise library with movement pattern, equipment, muscle, level, media, coaching cues and contraindications.
2. Program templates, blocks, mesocycles, weeks, sessions, supersets, circuits and conditional alternatives.
3. Prescription for sets, reps, load, duration, distance, tempo, rest, RPE/RIR and target zones.
4. Member-specific substitutions based on equipment, time, limitation, preference and location.
5. Fast member logging with previous result, smart defaults, timers, wearable input and minimal taps.
6. Coach review, comments, technique media, PR detection, progression and adherence.
7. Program versioning, assignment dates, completion history and safe plan transitions.
8. AI-assisted generation and adaptation with explicit constraints, evidence and coach approval.
Critical controls
Required outcomes
Health limitations and contraindications must be evaluated before assignment or AI generation.
Coaches create high-quality plans quickly and members log with minimal friction.
AI changes remain drafts until an authorized coach approves them, except low-risk member substitutions allowed by policy.
Progression and adherence are measurable from structured data.

### COA-03  Nutrition Planning, Meals, Logging & Adherence
Deliver the best coach-to-member nutrition experience through rapid plan creation, flexible adherence and contextual guidance.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Coach App; Member App; Admin Web
Dependencies
COA-01, PPL-01, COA-04, COA-05, DAT-01
Core entities
NutritionPlan, NutritionTarget, MealSlot, MealPlanDay, Meal, Recipe, Food, Serving, MealAlternative, FoodLog, NutritionCheckIn, GroceryList
Key events
nutrition_plan.assigned, meal.logged, meal.swapped, nutrition_checkin.submitted, adherence.changed, coach_review.required

#### Required capabilities
1. Three plan modes: flexible targets, structured meals and hybrid plan with coach-configurable tracking level.
2. Auto-load member age, measurements, goals, activity, training schedule and approved health context; request only missing data.
3. Preferences for allergies, dietary pattern, halal, dislikes, cuisine, budget, cooking time, meal count and schedule.
4. AI/template/scratch plan creation with calorie/macro targets, confidence, rationale and coach review.
5. Meal builder with recipe search, favorites, recent items, local/MENA foods, portions, daily target feedback and one-click target repair.
6. Generate or duplicate days, rotate meals, create meal slots and maintain alternatives within calorie/protein tolerance.
7. Preview exactly as member, set start/duration/check-in, meal-swap permissions and exception thresholds, then assign.
8. Member today view answering “what should I eat now?” with one-tap Eat & Log.
9. Smart swap, portion change, skip, log-something-else, barcode, favorites, recent and photo-based estimate with uncertainty.
10. Automatic grocery list, restaurant alternatives, contextual coach question and weekly check-in.
11. Coach exception inbox for low adherence, repeated missed protein, weight stall, swap request, hunger or energy issue.
12. Food/recipe library governance, locale-specific serving units, nutrition-source provenance and edit history.
Critical controls
Required outcomes
Nutrition guidance is not diagnosis or medical treatment; high-risk cases require qualified review.
Coach assigns an excellent plan in roughly one minute from a template or AI draft.
Allergen rules are hard constraints and cannot be overridden silently by AI or meal swaps.
Member follows and logs planned meals in one to two taps.
Photo estimates and food data display uncertainty and source where relevant.
Flexible adherence improves without forcing obsessive tracking.

### COA-04  Assessments, Measurements, Progress & Outcomes
Turn coaching, attendance and health-safe measurements into understandable progress and actionable review.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Coach App; Member App; Admin Web
Dependencies
PPL-01, IAM-03, SEC-01
Core entities
AssessmentTemplate, Assessment, MeasurementDefinition, Measurement, ProgressMedia, Goal, Milestone, OutcomeSummary
Key events
assessment.completed, measurement.recorded, goal.created, milestone.achieved, progress_review.required

#### Required capabilities
1. Configurable assessment templates for goals, movement, fitness, strength, endurance, habits and wellbeing.
2. Measurements for weight, circumference, body composition, performance, mobility and custom metrics with unit normalization.
3. Progress photos and media with consent, privacy, comparison controls and retention.
4. Goals with baseline, target, deadline, milestones, status and coach/member ownership.
5. Device/body-scanner imports with source, calibration and confidence metadata.
6. Member-friendly progress narrative alongside charts, consistency, attendance and program adherence.
7. Stall, anomaly and safety alerts that route to qualified review rather than autonomous change.
Critical controls
Required outcomes
Measurement source, unit and timestamp are immutable provenance.
Members can see meaningful progress beyond scale weight.
Sensitive images and health-like data use explicit access and retention policy.
Coaches review objective trends with source quality and context.

### COA-05  Health, Safety, Consent & Incident Management
Protect members, staff and the business through screening, restrictions, emergency context and accountable incident workflows.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Member App; Coach App; Admin Web; Front Desk
Dependencies
PPL-01, IAM-03, SEC-01, AUT-02
Core entities
HealthQuestionnaire, Waiver, Consent, Limitation, Allergy, EmergencyContact, Incident, Witness, CorrectiveAction, LegalHold
Key events
screening.submitted, consent.signed, limitation.updated, incident.reported, incident.escalated, corrective_action.closed

#### Required capabilities
1. PAR-Q-style screening, health questionnaire, waiver, informed consent and versioned signatures.
2. Injury, limitation, allergy, contraindication and emergency contact with fine-grained visibility.
3. Member-declared pain or symptom flow that pauses unsafe activity and routes to coach/qualified review.
4. Incident reporting for injury, equipment, safeguarding, harassment, security, medical or operational event.
5. Triage, immediate action, witnesses, evidence, notification, escalation, corrective action and closure.
6. Emergency mode with minimal necessary member context and controlled break-glass access.
7. Safety rules integrated into workout, nutrition, booking, access, facility and communication decisions.
8. Policy versioning, jurisdiction mapping, retention and legal hold.
Critical controls
Required outcomes
Gym OS must not present itself as a medical diagnosis or treatment system.
Unsafe assignments and preventable incidents are reduced.
Only minimum necessary health context is exposed to each role.
The organization can prove consent, response and corrective action.
Emergency access is exceptional, time-limited and reviewed.


## Engagement, Communication & Automation
### ENG-01  Unified Inbox, Messaging & Contextual Communication
Unify member, lead, coach and operational communication without losing channel history or business context.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Admin Web; Coach App; Member App; Front Desk
Dependencies
PPL-01, GRO-01, IAM-03, ECO-02
Core entities
Conversation, Thread, Message, ChannelIdentity, Inbox, Assignment, Template, DeliveryStatus
Key events
message.received, message.sent, message.failed, conversation.assigned, conversation.sla_breached

#### Required capabilities
1. Unified conversation timeline for in-app chat, WhatsApp, SMS, email, call notes and staff notes.
2. Threads anchored to member, lead, booking, workout, meal, invoice, incident or support case.
3. Shared team inbox with routing, assignment, status, collision prevention, SLA and handoff.
4. Channel templates, approved WhatsApp templates, localized variables and preview.
5. Member-to-coach messaging with availability, response expectations, media and moderation controls.
6. Consent, opt-out, quiet hours, communication preferences and legal retention by channel.
7. Delivery, read, failure, reply and escalation status with provider reconciliation.
8. AI-assisted drafts and summaries that never send without authorized policy.
Critical controls
Required outcomes
Channel consent and recipient identity are checked at send time.
Staff communicate from one contextual workspace.
Sensitive health or financial content is restricted from unsuitable channels.
Members do not repeat their history to each department.

### ENG-02  Notification Platform, Templates & Preferences
Deliver timely, localized and non-spammy transactional and engagement notifications across channels.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
All Apps; Internal SaaS Console
Dependencies
PLT-01, PLT-02, IAM-01, ECO-02
Core entities
Notification, NotificationTemplate, Preference, ChannelPolicy, DeliveryAttempt, Suppression, Digest
Key events
notification.requested, notification.sent, notification.delivered, notification.failed, preference.changed

#### Required capabilities
1. Event-triggered email, push, SMS, WhatsApp and in-app notifications through one orchestration API.
2. Template versioning, localization, brand styling, variables, preview and approval.
3. Transactional, operational, coaching and marketing categories with different consent rules.
4. User preferences, quiet hours, frequency caps, digesting, priority and channel fallback.
5. Scheduling, deduplication, idempotency, retry, provider failover and dead-letter handling.
6. Delivery analytics, complaint/bounce suppression and cost by tenant/channel.
7. Critical alerts that bypass selected preferences only under documented policy.
Critical controls
Required outcomes
Marketing and transactional purposes are separated.
Members receive fewer, more relevant messages.
The same logical notification cannot be delivered repeatedly because of retries.
Delivery reliability and communication cost are measurable.

### ENG-03  Community, Challenges, Achievements & Rewards
Increase motivation and belonging through purposeful social and reward mechanics without building an uncontrolled social network.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Member App; Admin Web; Corporate Portal
Dependencies
DAT-01, COM-04, SEC-02, PPL-01
Core entities
Challenge, Participant, Leaderboard, Achievement, RewardRule, PointsAccount, RewardRedemption, CommunityPost, ModerationCase
Key events
challenge.joined, challenge.progressed, achievement.earned, reward.issued, reward.redeemed, content.reported

#### Required capabilities
1. Challenges based on attendance, workout completion, distance, consistency, team goals or custom verified events.
2. Private, club, location, corporate and invitation-only participation scopes.
3. Leaderboards with privacy aliases, fair ranking, eligibility and anti-cheat review.
4. Achievements, streaks and milestones based on trusted event sources.
5. Reward rules for attendance, consistency, referrals, renewals, purchases, challenges and coaching milestones.
6. Reward catalog supporting points, wallet credit, guest pass, product, class or privilege.
7. Lightweight posts, announcements, reactions and comments with reporting, blocking and moderation.
8. Fraud, duplicate-event and incentive-abuse controls before reward settlement.
Critical controls
Required outcomes
Participation is optional and privacy defaults are conservative.
Higher consistency and community engagement.
Health-sensitive metrics are never publicly ranked without explicit design review and consent.
Rewards connect measurable behavior to business value.

### ENG-04  Member Self-Service, Digital Card & Service Requests
Let members safely resolve routine needs without contacting reception while retaining policy, approval and audit.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Member App; Member Web
Dependencies
COM-01, COM-03, OPS-02, OPS-03, IAM-01
Core entities
DigitalCard, WalletPass, SelfServiceRequest, RequestPolicy, MemberDocument, DataSubjectRequest
Key events
wallet_pass.issued, self_service.requested, self_service.approved, payment_method.updated, data_export.requested

#### Required capabilities
1. Digital membership card, QR/NFC credential and wallet pass with live status.
2. Renew, upgrade, downgrade, freeze, resume, cancel or request transfer with transparent effects and fees.
3. Manage payment methods, settle balances, view invoices/receipts/statements and download documents.
4. Buy packages, services, products, guest passes and gift cards.
5. Manage bookings, waitlist, household, dependents, consents, preferences, devices and access methods.
6. Service-request center with status, SLA, required documents, communication and resolution.
7. Export personal data, correct profile information and request account/data deletion where applicable.
Critical controls
Required outcomes
High-impact changes show terms, financial impact and effective date before confirmation.
Lower reception workload and faster member resolution.
Risky actions require step-up authentication and may require approval.
Members retain clear control over identity, billing and privacy.

### AUT-01  Automation & Workflow Orchestration
Turn domain events into reliable, explainable and permission-safe multi-step business workflows.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Admin Web; Internal SaaS Console
Dependencies
DAT-01, IAM-03, ENG-02, AUT-02
Core entities
WorkflowDefinition, WorkflowVersion, Trigger, Condition, Action, WorkflowRun, StepRun, DeadLetter
Key events
workflow.published, workflow.started, workflow.step.failed, workflow.completed, workflow.replayed

#### Required capabilities
1. Visual or structured builder using trigger, conditions, branches, waits, actions and stop criteria.
2. Triggers from events, schedules, thresholds, inbound messages, webhooks and manual commands.
3. Actions for notifications, tasks, tags, offers, booking, membership request, webhook, API and AI draft.
4. Tenant-safe execution context, service identity, permission checks and secret references.
5. Idempotency, retries, timeout, compensation, dead-letter queue and manual replay.
6. Versioning, draft/publish, test mode, simulation, impact estimate and rollback.
7. Execution timeline, reason, inputs, outputs, cost, errors and business outcome.
8. Frequency caps and contact governance inherited from notification/communication policy.
Critical controls
Required outcomes
Workflows cannot exceed the privileges of their owner/service identity.
Repeatable operations scale without hidden manual work.
Financial, access and health actions require purpose-built guarded actions, not generic mutation.
Every automated outcome is explainable and recoverable.

### AUT-02  Tasks, Cases, Approvals, SLAs & Escalations
Provide accountable human work management for exceptions, decisions, follow-ups and regulated actions.
Attribute
Definition
Delivery phase
V1 General Availability
Primary surfaces
Admin Web; Coach App; Internal SaaS Console
Dependencies
IAM-03, PPL-01, ENG-02
Core entities
Task, TaskTemplate, Case, ApprovalPolicy, ApprovalRequest, ApprovalDecision, SLA, Escalation
Key events
task.created, task.overdue, case.opened, approval.requested, approval.rejected, sla.breached

#### Required capabilities
1. Tasks linked to member, lead, tenant, invoice, incident, device, booking, asset or workflow.
2. Assignee, team queue, priority, due date, checklist, evidence, dependency and status.
3. Case container for multi-step problems with communication, timeline, documents and resolution reason.
4. Approval policies for refunds, discounts, price overrides, payroll, access exceptions, data export and deletion.
5. Sequential, parallel, quorum and amount-based approvals with delegation and expiry.
6. SLA clocks, business hours, pause reasons, breach warning and escalation routes.
7. Workload, aging, bottleneck, outcome and compliance reporting.
Critical controls
Required outcomes
Approvers cannot approve their own restricted actions unless explicit emergency policy applies.
Exceptions have clear ownership and do not disappear in messages.
SLA calculation is time-zone and business-calendar aware.
High-risk actions are controlled without blocking routine work.

## Analytics, AI, Corporate & Franchise
### INT-01  Operational Analytics, BI, Forecasting & Benchmarking
Explain what happened, why it happened, what is likely next and what action should be considered.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Admin Web; Coach App; Internal SaaS Console
Dependencies
DAT-01, DAT-02, IAM-03
Core entities
MetricDefinition, Dimension, Fact, Dashboard, Report, Forecast, Target, BenchmarkCohort, Anomaly
Key events
metric.updated, anomaly.detected, forecast.generated, target.missed, report.delivered

#### Required capabilities
1. Role-specific scorecards for owner, region, club, sales, finance, coaching, operations and customer success.
2. Metric semantic layer with definition, owner, grain, source, freshness and tenant-safe access.
3. Revenue, collections, membership, retention, attendance, booking, PT, nutrition, POS, inventory, staff and NPS analytics.
4. Drill from KPI to cohort, location, segment and permission-aware underlying records.
5. Variance explanations, anomaly detection, forecasts, targets and scenario comparisons.
6. Benchmarking across a chain and optional privacy-preserving industry cohorts.
7. Scheduled reports, exports, alerts and embedded analytics.
8. Data quality, freshness and completeness indicators displayed with decisions.
Critical controls
Required outcomes
Metric definitions are governed and cannot differ silently across dashboards.
Leaders act on explanations and exceptions, not exported spreadsheets.
Small cohorts and sensitive attributes are protected from re-identification.
Forecasts show uncertainty and improve through measured feedback.

### INT-02  AI Platform, Copilots, Agents & Governance
Make the entire Gym OS AI-native while keeping data isolation, safety, cost and human accountability explicit.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
All Product Surfaces; Internal SaaS Console
Dependencies
IAM-03, DAT-01, DAT-02, AUT-02, SEC-01
Core entities
AIUseCase, PromptVersion, ModelRoute, AIConversation, AIMessage, ToolDefinition, ToolRun, Evaluation, SafetyPolicy, AIBudget
Key events
ai.requested, ai.response.generated, ai.tool.proposed, ai.tool.approved, ai.tool.executed, ai.safety.blocked

#### Required capabilities
1. Admin Copilot for business questions, explanations, prioritized actions, draft campaigns and guarded execution.
2. Sales Copilot for lead prioritization, conversation summary, next action, objection help and follow-up draft.
3. Coach Copilot for attention list, program/nutrition draft, adaptation, review summary and client message.
4. Member Assistant for navigation, booking, plan explanation and low-risk allowed substitutions.
5. Retrieval layer with tenant, role, purpose and record-level authorization at query and response time.
6. Tool/action registry with schemas, permission checks, risk tiers, approvals, idempotency and compensating actions.
7. Prompt/model/version registry, evaluation sets, routing, fallback, latency and budget controls.
8. AI audit recording context references, model, prompt version, outputs, confidence, citations, actions and approver.
9. Safety boundaries for health, nutrition, finance, biometric, employment and legal-sensitive use cases.
10. Tenant-level opt-in, data-use controls, regional model policy, cost budget and feature disablement.
Critical controls
Required outcomes
AI never receives broader data access than the requesting user and purpose.
Users obtain answers and actions without navigating the system structure.
Irreversible or high-impact actions require explicit human approval.
AI value, quality, latency, safety and cost are measured per use case and tenant.
Health and nutrition outputs include scope limits and qualified escalation paths.


### INT-03  Global Search, Command Bar & Knowledge Navigation
Provide a secure, fast entry point to records, actions, help and AI-assisted commands across the platform.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Admin Web; Coach App; Internal SaaS Console
Dependencies
IAM-03, DAT-01, INT-02
Core entities
SearchDocument, SearchIndex, SavedSearch, Command, CommandAction, KnowledgeArticle
Key events
search.executed, search.zero_result, command.previewed, command.executed

#### Required capabilities
1. Keyboard-first global command bar on Admin Web and role-appropriate search on mobile.
2. Search members, leads, staff, bookings, invoices, products, orders, tasks, incidents, assets and settings.
3. Permission-aware indexing, query filtering, result masking and post-filter validation.
4. Recent, pinned, suggested and context-sensitive actions such as create, refund, book, message or navigate.
5. Natural-language commands converted to previewable structured actions.
6. Help and knowledge results matched to page, role, tenant configuration and product version.
7. Search analytics for zero-result, latency, permission denial and task-completion improvement.
Critical controls
Required outcomes
Search can never be used to bypass field or record permissions.
Experienced users complete cross-module work dramatically faster.
Commands show target, effect and required approval before execution.
New users discover capabilities without learning the entire navigation tree.

### B2B-01  Corporate Memberships & Employer Portal
Support business-to-business membership programs from eligibility and enrollment through utilization, billing and renewal.
Attribute
Definition
Delivery phase
Enterprise
Primary surfaces
Corporate Portal; Admin Web; Member App
Dependencies
PPL-02, COM-01, COM-03, IAM-01, DAT-02
Core entities
CorporateAccount, CorporateContract, BenefitPlan, EligibilityRoster, EmployeeEnrollment, EmployerInvoice, CorporateReport
Key events
corporate.contract.started, eligibility.added, employee.enrolled, employee.eligibility.ended, corporate.invoice.issued

#### Required capabilities
1. Corporate account, contract, eligible population, benefit package, subsidy and employee contribution.
2. Eligibility via roster upload, HRIS/API, email domain, code or enterprise identity.
3. Employee invitation, self-enrollment, dependent rules, location access and plan selection.
4. Joiner, mover and leaver synchronization with grace and conversion to personal membership.
5. Consolidated invoice, employee copay, adjustments, credits and reconciliation.
6. Privacy-preserving aggregate utilization, engagement, attendance and program-outcome reporting.
7. Corporate challenges, events, communications and support contacts.
Critical controls
Required outcomes
Employers receive only contractually permitted aggregate data.
Enterprise contracts are operable without manual spreadsheets.
Individual health, coaching and sensitive activity remains private unless explicitly authorized.
Corporate customers can prove utilization and value while protecting employees.

### B2B-02  Franchise, Multi-brand & Chain Command Center
Give large operators centralized governance and comparable insight while preserving local execution.
Attribute
Definition
Delivery phase
Enterprise
Primary surfaces
Admin Web; Franchise Portal; Internal SaaS Console
Dependencies
PLT-01, PLT-02, INT-01, COM-04, IAM-03
Core entities
FranchiseNetwork, Franchisee, GovernanceTemplate, Override, HomeClub, IntercompanyAllocation, RoyaltyStatement
Key events
governance.published, location.exception.detected, member.home_club.changed, royalty.statement.created

#### Required capabilities
1. Hierarchy for holding company, brand, franchisee, region, location and department.
2. Central standards with inherited/local overrides for catalog, pricing, membership, brand, access and operations.
3. Cross-location member access, home club, revenue attribution, transfer and data ownership policy.
4. Comparable scorecards and exception queues for revenue, churn, conversion, NPS, staffing, maintenance and compliance.
5. Franchise royalty, marketing fund, shared services, intercompany allocation and settlement exports.
6. Location opening/closing playbooks, readiness gates and configuration templates.
7. Benchmarking with normalized metrics and permissions by hierarchy scope.
Critical controls
Required outcomes
Local overrides are explicit, bounded and reviewable.
Head office sees the chain as one operating system.
Cross-location analytics use governed definitions and ownership rules.
Local managers retain autonomy within approved guardrails.

## Developer Ecosystem, Hardware & White-label
### ECO-01  Developer Platform, APIs, Webhooks & Sandbox
Make Gym OS an extensible platform with secure, stable and observable integration contracts.
Attribute
Definition
Delivery phase
V2 Platform
Primary surfaces
Developer Portal; Admin Web; Internal SaaS Console
Dependencies
IAM-01, IAM-03, DAT-01, REL-01
Core entities
DeveloperApp, OAuthGrant, APIKey, Scope, WebhookSubscription, WebhookDelivery, SandboxTenant, SDKVersion
Key events
developer_app.created, oauth.granted, api.rate_limited, webhook.delivered, webhook.failed, api.version.deprecated

#### Required capabilities
1. Versioned public APIs with consistent resources, pagination, filtering, errors and idempotency.
2. OAuth 2/OIDC applications, tenant authorization, granular scopes, API keys and service accounts.
3. Webhook subscriptions, event filtering, signing, retries, ordering guidance, replay and delivery logs.
4. Sandbox tenant, test data, simulated providers and safe webhook endpoint testing.
5. Developer portal with documentation, examples, SDKs, changelog, status and support.
6. Rate limits, quotas, usage analytics, error diagnostics and credential rotation.
7. API versioning, compatibility, deprecation, migration guides and contract tests.
8. Partner certification and security review for sensitive scopes.
Critical controls
Required outcomes
API authorization is tenant-bound and scope-limited.
Partners integrate without private documentation or manual credential exchange.
Backward compatibility and deprecation windows are contractual product commitments.
Integrations are observable and supportable by tenant and partner.

### ECO-02  Integration Framework, Marketplace & Partner Ecosystem
Connect payments, messaging, accounting, wearables, access, HR, analytics and regional providers through governed adapters.
Attribute
Definition
Delivery phase
V2 Platform
Primary surfaces
Admin Web; Developer Portal; Internal SaaS Console
Dependencies
ECO-01, PLT-03, SEC-01, REL-01
Core entities
IntegrationDefinition, IntegrationInstall, Connection, CredentialRef, SyncCursor, ConnectorRun, MarketplaceListing, PartnerAccount
Key events
integration.installed, integration.connected, integration.sync.failed, credential.expiring, marketplace.listing.approved

#### Required capabilities
1. Integration catalog with capabilities, regions, prerequisites, permissions, pricing and support owner.
2. Standard connector lifecycle: install, authorize, configure, validate, activate, monitor, rotate and uninstall.
3. Provider abstraction for payments, WhatsApp/SMS/email, accounting, access hardware, identity and storage.
4. Credential vault, tenant-specific secrets, least scopes and automated rotation reminders.
5. Sync state, cursor, retries, conflict policy, dead-letter, reconciliation and diagnostics.
6. Marketplace listing, review, certification, trial, billing, revenue share, ratings and support route.
7. Vendor dependency register with SLA, outage fallback, cost and exit plan.
Critical controls
Required outcomes
Third parties receive only required data and permissions.
Regional and vertical capability expands without bloating the core product.
Critical integrations require fallback, reconciliation and documented exit strategy.
Partners become a distribution and innovation channel.

### ECO-03  Hardware Abstraction, Edge Runtime & Device Fleet
Operate turnstiles, biometric terminals, scanners, kiosks, POS devices and connected equipment without vendor lock-in.
Attribute
Definition
Delivery phase
V2 Platform
Primary surfaces
Internal SaaS Console; Admin Web; Edge Runtime
Dependencies
PLT-01, IAM-01, REL-01, SEC-01
Core entities
Device, DeviceType, DeviceCapability, DeviceCertificate, Firmware, EdgePolicySnapshot, DeviceCommand, DeviceTelemetry
Key events
device.enrolled, device.online, device.offline, device.command.completed, firmware.updated, edge.sync.conflict

#### Required capabilities
1. Canonical device capabilities for credential read, access actuation, biometric match, scan, print, payment and telemetry.
2. Vendor adapters behind stable commands, events, health and configuration contracts.
3. Device enrollment, tenant/location assignment, certificate, firmware, configuration and remote revoke.
4. Edge runtime with signed policy/data cache, local queue, secure time, retry and conflict handling.
5. Fleet dashboard for online status, latency, errors, storage, version, peripherals and last sync.
6. Remote commands, staged rollout, maintenance mode, diagnostics bundle and replacement workflow.
7. Mobile device management integration for dedicated tablets and kiosks.
Critical controls
Required outcomes
Devices authenticate with rotating certificates; default credentials are forbidden.
Hardware vendors can change without rewriting gym workflows.
Remote commands are scoped, signed, audited and bounded by device safety.
Fleet failures are detected before they block club operation.

### WHT-01  White-label, App Builder, CMS & Mobile Release Operations
Let each brand deliver a differentiated member experience without forking the product or losing release control.
Attribute
Definition
Delivery phase
V2 Platform
Primary surfaces
Admin Web; Member App; Internal SaaS Console
Dependencies
PLT-02, PLT-03, ENG-02, GOV-01
Core entities
BrandTheme, AppConfiguration, ContentItem, ContentVersion, ContentTarget, BrandedApp, Build, StoreRelease
Key events
content.published, app_configuration.changed, build.completed, store_release.approved, mobile_version.deprecated

#### Required capabilities
1. Brand tokens for logo, icon, color, typography, imagery, tone, domains, sender identities and legal links.
2. Configurable navigation, home modules, feature visibility, campaigns, banners, content blocks and service shortcuts.
3. CMS for announcements, onboarding, help, exercises, recipes, programs, challenges, promotions and legal content.
4. Content workflow with draft, review, localization, scheduling, targeting, versioning and rollback.
5. Branded app ownership model, store account setup, signing, certificates, privacy labels and asset validation.
6. Automated build pipeline, version matrix, staged rollout, minimum supported version and forced/optional update.
7. Preview environment showing exact member experience by brand, location, language, plan and feature flags.
8. Release fleet dashboard for app review, store status, certificates, crashes and adoption.
Critical controls
Required outcomes
Tenant customization is configuration and content, never unreviewed executable code.
Brands achieve differentiation without slowing the core roadmap.
Store credentials and signing materials are isolated, encrypted and rotated.
Hundreds of branded apps remain supportable and updateable.

### WHT-02  Localization, RTL, Accessibility & Regional Policy
Make Gym OS usable, compliant and operationally correct across languages, abilities, currencies, cultures and jurisdictions.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
All Surfaces
Dependencies
PLT-01, PLT-02, GOV-01
Core entities
Locale, TranslationKey, TranslationVersion, RegionalPolicyPack, AccessibilityIssue, CurrencyConfiguration, TaxLocale
Key events
translation.published, regional_policy.updated, accessibility.issue.detected, locale.changed

#### Required capabilities
1. First-class Arabic and English with full RTL/LTR layouts, mixed content and bidirectional testing.
2. Locale-aware date, time, week start, number, currency, tax, name, address and phone formatting.
3. Translation workflow, glossary, context, screenshot review, pluralization, fallback and tenant overrides.
4. Accessibility for screen readers, dynamic type, keyboard, focus order, contrast, reduced motion, captions and touch targets.
5. Regional payment, tax, invoicing, data residency, consent, biometrics, labor, contracts and communication policy packs.
6. Cuisine, food, serving units, names and search behavior localized for nutrition.
7. Time-zone, daylight-saving and cross-region schedule correctness.
8. Localization and accessibility QA gates in design, development and release.
Critical controls
Required outcomes
No critical workflow is considered complete until tested in Arabic RTL and English LTR.
MENA/GCC users receive a native rather than translated experience.
Accessibility conformance is measurable and release-blocking for critical defects.
Regional expansion uses policy packs instead of product forks.

## Data, Security & Reliability
### DAT-01  Domain Events, Event Bus & Operational Timeline
Capture every important business state change as a durable, governed and replayable event.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Platform; Developer Portal; Internal SaaS Console
Dependencies
PLT-01, SEC-01, REL-01
Core entities
DomainEvent, EventSchema, OutboxRecord, Subscription, ConsumerCheckpoint, DeadLetterEvent, ReplayJob
Key events
event.published, event.delivery.failed, event.replayed, event_schema.changed

#### Required capabilities
1. Canonical event envelope with tenant, aggregate, actor, correlation, causation, schema, timestamp and source.
2. Transactional outbox or equivalent guarantee between state change and event publication.
3. Schema registry, compatibility rules, ownership, classification and deprecation.
4. At-least-once delivery with idempotent consumers, retry, dead-letter and replay.
5. Event routing to timeline, automation, notification, analytics, integrations, fraud and AI.
6. Retention, compaction, PII minimization, encryption and regional routing.
7. Operational explorer for correlation tracing and controlled replay.
8. Business event catalog accessible to product, engineering, analytics and partners.
Critical controls
Required outcomes
Events contain only data needed by approved consumers and preserve tenant boundaries.
Analytics, automation and integrations react consistently to the same truth.
Schema changes follow compatibility and consumer migration policy.
Complex workflows are traceable across services and channels.

### DAT-02  Data Platform, Warehouse, Governance & Data Products
Turn operational data into trusted analytics, AI context and governed customer data products without burdening transactions.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Analytics; AI Platform; Internal SaaS Console; Enterprise Export
Dependencies
DAT-01, IAM-03, SEC-01
Core entities
DataSource, DataAsset, DataProduct, Dataset, Metric, QualityRule, LineageEdge, DataClassification, DataShare
Key events
data.ingested, data_quality.failed, data_product.published, dataset.accessed, data_export.completed

#### Required capabilities
1. Ingestion from domain events, databases, provider settlements, devices and external integrations.
2. Warehouse/lakehouse layers for raw, cleaned, conformed and business-ready data.
3. Semantic model for shared facts, dimensions, metrics, cohorts and effective-dated history.
4. Data catalog, ownership, classification, lineage, quality, freshness and usage.
5. Tenant and row/column security, privacy transformations, pseudonymization and aggregation.
6. Data products for member health score, churn risk, revenue, capacity, inventory, coach performance and SaaS usage.
7. Reverse ETL or safe activation of derived insight back into operational workflows.
8. Export, clean room, partner sharing and residency controls for enterprise use.
Critical controls
Required outcomes
Derived data inherits the strictest relevant classification and tenant policy.
Operational reporting no longer threatens transaction performance.
Metric and model inputs expose freshness and quality state.
AI and analytics share trusted, governed data products.

### SEC-01  Security, Privacy, Compliance & Consent
Protect tenant, member, staff and platform data through a security and privacy program embedded in architecture and operations.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
All Systems
Dependencies
PLT-01, IAM-01, IAM-03
Core entities
SecurityControl, ThreatModel, Vulnerability, Secret, EncryptionKey, ConsentRecord, RetentionPolicy, DataSubjectRequest, SecurityIncident
Key events
consent.granted, consent.withdrawn, security.alert.detected, vulnerability.opened, data_subject_request.completed

#### Required capabilities
1. Security architecture, threat modeling, secure defaults, least privilege and zero-trust service identity.
2. Encryption in transit and at rest, key management, rotation, secret vault and certificate lifecycle.
3. Secure SDLC with code review, SAST/DAST, dependency, container, IaC and secret scanning.
4. Vulnerability management, penetration tests, bug response, risk acceptance and remediation SLAs.
5. Data classification for identity, contact, financial, health, biometric, media, employment, operational and analytics data.
6. Consent registry for terms, privacy, marketing, waiver, health, biometrics, media and data sharing with version history.
7. Data subject requests for access, correction, portability, restriction and deletion with identity and legal checks.
8. Retention schedule, archive, deletion, legal hold, backup expiry and subprocessor governance.
9. Security monitoring, incident response, evidence, notification assessment and postmortem.
10. Enterprise package: DPA, security whitepaper, subprocessor list, SLA, controls evidence and questionnaire response.
Critical controls
Required outcomes
Privacy and security review is mandatory for biometric, health, AI and new data-sharing capabilities.
Security becomes a sales enabler and operational discipline.
Production access is just-in-time, purpose-bound and audited.
Users retain meaningful control over sensitive data.

### SEC-02  Fraud, Abuse, Trust & Content Moderation
Detect and respond to financial, access, promotion, identity, staff and community abuse without harming legitimate users.
Attribute
Definition
Delivery phase
V1.5 Growth
Primary surfaces
Admin Web; Internal SaaS Console; Member App
Dependencies
DAT-01, AUT-02, IAM-03, SEC-01
Core entities
FraudSignal, RiskAssessment, TrustCase, Restriction, ModerationReport, ModerationDecision, Appeal
Key events
fraud.signal.detected, trust.case.opened, account.restricted, content.reported, moderation.decided, appeal.resolved

#### Required capabilities
1. Rules and anomaly detection for QR sharing, access passback, guest abuse, duplicate identities and biometric spoofing.
2. Payment, wallet, refund, discount, promotion, referral and chargeback abuse signals.
3. Staff fraud indicators for unauthorized overrides, cash variance, stock adjustment and suspicious member changes.
4. Risk score, evidence, case creation, action recommendation and human review.
5. Progressive responses: warn, challenge, hold, restrict, require approval, suspend and investigate.
6. Community reporting, blocking, moderation queues, policy reasons, appeals and repeat-offender handling.
7. Model/rule monitoring for false positives, bias, drift and business impact.
Critical controls
Required outcomes
Automated detection does not impose severe irreversible penalties without review.
Revenue, access and community integrity improve with explainable controls.
Risk data is restricted, retained appropriately and not exposed to unrelated staff.
Legitimate members have clear appeal and recovery paths.

### REL-01  Reliability, Offline Operation, Business Continuity & Incident Management
Keep critical club and SaaS operations available, recoverable and communicable under component, provider, network or regional failure.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Platform; Internal SaaS Console; Status Page; Edge Devices
Dependencies
PLT-01, DAT-01, SEC-01
Core entities
SLO, ErrorBudget, OfflinePolicy, SyncQueue, Backup, RestoreTest, DRPlan, Incident, StatusUpdate, Postmortem
Key events
slo.breached, offline_mode.entered, sync.reconciled, backup.completed, restore.tested, incident.declared, incident.resolved

#### Required capabilities
1. Service-level indicators, objectives and error budgets for login, access, booking, POS, payments, messaging and core APIs.
2. Resilient patterns: timeout, retry with jitter, circuit breaker, bulkhead, queue, idempotency and graceful degradation.
3. Offline modes for check-in, access and selected front-desk/POS operations with bounded risk and reconciliation.
4. Backup, point-in-time recovery, restore testing, replication and tenant-level recovery procedures.
5. Documented RPO/RTO by data and workflow criticality.
6. Disaster recovery for zone, region, database, object storage, queue and identity dependencies.
7. Incident command, severity, ownership, timeline, runbook, status page, customer communication and postmortem.
8. Provider continuity plans for payments, messaging, access hardware, biometric and cloud services.
9. Chaos, failover, restore and business-continuity drills on a defined cadence.
Critical controls
Required outcomes
Critical workflows define explicit degraded behavior rather than fail unpredictably.
Gyms continue core operation during common outages.
Backups are not considered valid until restore drills pass.
Incidents are detected, contained, communicated and learned from.

### REL-02  Observability, Performance, Capacity & FinOps
Make platform health, tenant impact, performance and unit economics visible and actionable.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Internal SaaS Console; Engineering Operations
Dependencies
PLT-01, SEC-01
Core entities
Telemetry, Trace, MetricSeries, SyntheticCheck, PerformanceBudget, CapacityModel, CostAllocation, BudgetAlert
Key events
synthetic_check.failed, performance_budget.exceeded, capacity.threshold.reached, cost.anomaly.detected

#### Required capabilities
1. Structured logs, metrics and distributed traces with tenant-safe correlation and redaction.
2. Golden signals and business signals for each critical workflow and dependency.
3. Synthetic monitoring for login, member search, booking, payment, POS, check-in, webhook and messaging paths.
4. Performance budgets for web, mobile, APIs, search, edge access and report generation.
5. Capacity models, load tests, scaling policy, hot-tenant protection and noisy-neighbor controls.
6. Cost allocation by tenant, domain, environment, AI model, message, storage, integration and support.
7. Budgets, anomaly alerts, unit economics, margin by plan and cost optimization backlog.
8. Operational dashboards and alert routing with ownership, runbook and escalation.
Critical controls
Required outcomes
Observability data is redacted and access-controlled; logs are not a shadow database.
Teams diagnose tenant-impacting failures quickly.
Alerts must be actionable, owned and tied to user/business impact.
Gross margin remains visible as usage and AI scale.

## Lifecycle, Quality & Governance
### LIF-01  Onboarding, Implementation & Go-live Readiness
Move a customer from signed contract to confident daily operation through a measurable implementation journey.
Attribute
Definition
Delivery phase
Pilot
Primary surfaces
Admin Web; Internal SaaS Console; Learning Portal
Dependencies
PLT-01, PLT-04, LIF-02, GOV-04
Core entities
ImplementationProject, ImplementationTask, ReadinessCheck, TrainingPath, GoLivePlan, HypercareCase
Key events
implementation.started, readiness.changed, go_live.approved, tenant.went_live, hypercare.completed

#### Required capabilities
1. Guided setup for organization, brands, locations, legal entities, regional settings and administrators.
2. Configure plans, catalog, pricing, tax, payment, access, schedule, staff, roles, documents, communications and apps.
3. Implementation project with checklist, owner, dependency, due date, evidence, risks and readiness score.
4. Data migration waves, validation, reconciliation, sign-off and cutover plan.
5. Hardware installation, network test, device enrollment, offline validation and operational rehearsal.
6. Role-based training, sandbox practice, knowledge paths and certification.
7. Go-live gate covering data, finance, access, bookings, support, rollback and communication.
8. Hypercare period, issue triage, adoption review and transition to customer success.
Critical controls
Required outcomes
No tenant goes live without validated rollback and business-continuity plan.
Time-to-value decreases and implementation risk becomes visible.
Readiness gates are evidence-based, not subjective status labels.
Staff reach operational confidence before member launch.

### LIF-02  Migration, Import, Validation & Cutover
Make switching from spreadsheets or competitors safe, repeatable and commercially compelling.
Attribute
Definition
Delivery phase
Pilot
Primary surfaces
Admin Web; Internal SaaS Console
Dependencies
PLT-01, PPL-01, COM-01, COM-04, SEC-01
Core entities
MigrationProject, SourceSystem, ImportFile, Mapping, Transformation, ImportRun, ImportError, ReconciliationReport, CutoverRun
Key events
migration.dry_run.completed, migration.error.detected, migration.import.completed, migration.reconciled, cutover.completed

#### Required capabilities
1. Source-specific importers for CSV/Excel and prioritized competitors, plus generic API/file framework.
2. Mapping workspace for fields, codes, locations, plans, products, statuses, currencies and identities.
3. Transformations, normalization, deduplication, defaults and exception queues.
4. Dry run with counts, financial totals, orphan records, conflicts, invalid data and remediation guidance.
5. Migration of members, leads, memberships, balances, credits, invoices, payments, bookings, attendance, programs, notes and documents according to scope.
6. Incremental/delta imports, freeze window, cutover runbook and post-cutover reconciliation.
7. Import lineage, source identifiers, evidence, sign-off and controlled rollback.
8. Privacy-safe staging, time-limited source files and secure deletion.
Critical controls
Required outcomes
Financial and entitlement totals require explicit reconciliation and customer sign-off.
Migration becomes a productized competitive advantage.
Source files are encrypted, access-limited and deleted by policy.
Customers switch with traceable data quality and minimal operational downtime.

### LIF-03  Offboarding, Data Portability, Archival & Deletion
End customer and user relationships responsibly with complete financial, legal, security and data controls.
Attribute
Definition
Delivery phase
Enterprise
Primary surfaces
Internal SaaS Console; Tenant Admin; Member App
Dependencies
PLT-03, SEC-01, DAT-02, ECO-02
Core entities
OffboardingCase, DataExportPackage, ArchiveRecord, DeletionJob, LegalHold, CredentialRevocation, DeletionEvidence
Key events
tenant.offboarding.started, data_export.ready, tenant.archived, credentials.revoked, data.deleted

#### Required capabilities
1. Tenant lifecycle from active to past due, suspended, cancelled, read-only, archived and deleted.
2. Final billing, settlement, refunds, outstanding obligations, device return and credential revocation.
3. Structured export for members, contracts, payments, invoices, attendance, bookings, training, nutrition, messages and audit according to rights.
4. Export manifest, schema, checksums, encryption, expiry and delivery audit.
5. Retention by data class, legal hold, archive tier, restoration authorization and deletion schedule.
6. Integration uninstall, webhook shutdown, secret destruction, domain release and app-store transition.
7. Member-level account deletion/export coordinated across tenant and platform obligations.
8. Deletion evidence and tombstones preventing unintended recreation or orphaned references.
Critical controls
Required outcomes
Deletion occurs only after retention, legal hold and billing obligations are evaluated.
Customers trust that they own and can retrieve their data.
Exports are permissioned, encrypted, time-limited and auditable.
Departed tenants do not leave active credentials, costs or hidden risk.

### GOV-01  Quality Engineering, CI/CD, Release & Schema Management
Deliver frequent change safely across backend, web, mobile, data, integrations and edge devices.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Engineering; Internal SaaS Console
Dependencies
PLT-02, REL-01, SEC-01
Core entities
TestSuite, TestRun, BuildArtifact, Deployment, Release, DatabaseMigration, MobileVersion, ChangeNotice
Key events
build.completed, quality_gate.failed, deployment.started, deployment.rolled_back, release.published, schema.migrated

#### Required capabilities
1. Test pyramid covering unit, component, integration, contract, end-to-end, mobile UI and exploratory testing.
2. Critical workflow suites for authentication, tenant isolation, membership, booking, payment, ledger, POS, access and migration.
3. Load, performance, security, accessibility, localization, offline and failure testing.
4. CI gates for lint, test, vulnerability, schema compatibility, migration safety and artifact signing.
5. Progressive delivery, canary, feature flags, automated rollback and release evidence.
6. Backward-compatible database changes, expand-contract pattern, zero-downtime migration and rollback strategy.
7. Mobile version support policy, store rollout, crash monitoring and remote configuration.
8. Release train, changelog, maintenance, beta/GA/deprecation lifecycle and customer communication.
Critical controls
Required outcomes
Tenant isolation, finance and access tests are release-blocking.
Release velocity increases without sacrificing trust.
Every production artifact is reproducible, signed and traceable to source and tests.
Schema and mobile evolution do not break active tenants.

### GOV-02  Product, Architecture, Data & AI Governance
Keep a large product coherent through ownership, decisions, standards and measurable lifecycle control.
Attribute
Definition
Delivery phase
Foundation
Primary surfaces
Internal Product Operations
Dependencies
PLT-01
Core entities
DomainOwnership, ArchitectureDecision, ProductLifecycleRecord, DesignToken, GovernanceReview, RequirementTrace, AIGovernanceReview
Key events
decision.accepted, domain.owner.changed, product_feature.deprecated, governance.review.completed

#### Required capabilities
1. Domain ownership with product, design, engineering, data and operations accountable leaders.
2. Architecture decision records, service boundaries, invariants, dependency rules and review forum.
3. Product lifecycle from discovery to beta, GA, deprecation and removal with evidence gates.
4. Design system governance for components, interaction patterns, accessibility, RTL and white-label tokens.
5. Data governance council for ownership, metrics, quality, classification, lineage and access.
6. AI governance for use-case approval, risk tier, evaluation, model change, human oversight and incident response.
7. Requirement traceability from strategy through domain, flow, screen, event, test and metric.
8. Portfolio prioritization using value, urgency, dependency, risk, revenue, cost and learning.
Critical controls
Required outcomes
No domain has ambiguous ownership or multiple sources of truth.
The platform grows without becoming an incoherent feature collection.
High-risk AI, data and architecture changes require documented review.
Decisions and tradeoffs remain understandable years later.

### GOV-03  Legal, Procurement, Vendor, Partner & Compliance Operations
Make Gym OS ready for enterprise buying, regulated operations and responsible third-party dependence.
Attribute
Definition
Delivery phase
Enterprise
Primary surfaces
Internal SaaS Console; Legal/Compliance Workspace
Dependencies
SEC-01, REL-01, PLT-04
Core entities
LegalDocument, Contract, Obligation, Vendor, VendorAssessment, Subprocessor, PartnerAgreement, ComplianceControl, Evidence
Key events
legal_document.published, contract.renewal_due, vendor.risk.changed, partner.certified, control.test.failed

#### Required capabilities
1. Terms, privacy notice, DPA, SLA, acceptable-use, biometric, AI, marketplace and partner policies with versioning.
2. Contract repository, obligations, renewal, notice periods, security addenda and approval workflow.
3. Enterprise procurement pack, security questionnaires, architecture diagrams and evidence library.
4. Vendor inventory, risk tier, due diligence, DPA, subprocessor, SLA, cost, performance and exit plan.
5. Partner/reseller onboarding, certification, territory, deal registration, commission, conduct and termination.
6. Compliance control mapping, evidence collection, audit calendar, remediation and continuous monitoring.
7. Insurance, business continuity, intellectual property and open-source license governance.
Critical controls
Required outcomes
Material vendors and subprocessors cannot be adopted without risk and privacy review.
Enterprise deals pass procurement with less bespoke effort.
Customer commitments map to owned controls and measurable evidence.
Third-party risk and obligations are visible before incidents or renewal.

### GOV-04  GTM Operations, Knowledge, Training, Feedback & Product Education
Connect sales, implementation, support, education and product learning into a repeatable customer lifecycle.
Attribute
Definition
Delivery phase
Pilot
Primary surfaces
Internal SaaS Console; Learning Portal; In-product Help
Dependencies
PLT-04, LIF-01, WHT-01
Core entities
GTMLead, DemoTenant, KnowledgeArticle, LearningPath, Certification, FeedbackItem, Opportunity, AdoptionCampaign
Key events
demo.created, learning.completed, feedback.received, opportunity.validated, release_communication.sent

#### Required capabilities
1. Internal sales pipeline for Gym OS leads, demos, trials, proposals, procurement, contracts and handoff.
2. Demo tenants, scenario data, role-based demo scripts and resettable environments.
3. Knowledge base, contextual help, guided tours, release notes and troubleshooting trees.
4. Admin Academy, Coach Academy, implementation training and partner certification.
5. Feedback intake from support, NPS, interviews, in-product prompts, sales and partners with deduplication.
6. Opportunity repository linking problem evidence, affected segment, value, risk and decision.
7. Adoption campaigns and capability education targeted by tenant configuration and behavior.
8. Release and deprecation communication by impacted tenant, role and integration.
Critical controls
Required outcomes
Demo and learning data is synthetic and isolated from production.
Customers learn faster and adopt more of the platform.
Feedback prioritization preserves evidence and does not become a vote count.
Product decisions use a continuous, traceable evidence stream.


CHAPTER 5
# Detailed Application & UX Blueprint
Information architecture, interaction rules and the highest-value experiences.
## Global UX Standards
Frequent tasks should take three primary actions or fewer when security and policy permit.
Reuse known context; never ask a user to re-enter data already owned by the system.
Show the next best action and exceptions before charts, menus or raw records.
Every denial or error explains what happened, why and how to recover.
Use progressive disclosure for advanced controls, policy and enterprise detail.
Preserve context across handoffs; member, meal, workout, invoice or incident stays attached.
Offline and sync state is visible, understandable and recoverable.
Arabic RTL and accessibility are tested in every state, not only the happy path.
## Admin Web Information Architecture
Area
Key screens and outcomes
Home / Command Center
Today KPIs; attention queue; revenue, collections, sales, attendance and risk; quick actions; AI summary.
CRM & Sales
Lead inbox, pipeline, trial calendar, offers, activities, attribution, sales performance and automations.
Members
Member directory, Member 360, lifecycle, relationships, notes, documents, access, privacy and timeline.
Memberships
Plans, contracts, entitlements, lifecycle requests, freezes, renewals, cancellations and exceptions.
Schedule & Bookings
Calendar, resources, classes, PT, waitlist, no-show, substitutions, capacity and policies.
Front Desk
Live arrivals, member search, access resolution, guest/trial, quick booking, payment and POS.
Commerce / POS
Catalog, orders, registers, cash shifts, receipts, returns, ecommerce and sales analysis.
Billing & Finance
Invoices, payments, dunning, refunds, disputes, ledger, wallet, reconciliation, tax and exports.
Inventory & Procurement
Stock, suppliers, purchase orders, receiving, transfers, counts, expiry, margin and replenishment.
Team & Staff
People, roles, shifts, time, qualifications, payroll, commissions, tasks and performance.
Coaching
Coach assignments, clients, sessions, programs, exercise library, assessments and delivery quality.
Nutrition
Nutrition templates, food/recipe library, plan oversight, adherence exceptions and qualified review.
Engagement
Unified inbox, campaigns, referrals, community, challenges, rewards, content and notifications.
Operations
Facilities, equipment, maintenance, incidents, health/safety, guests, devices and occupancy.
Automations & Work
Workflows, tasks, cases, approvals, SLAs, execution history and failure recovery.
Analytics & AI
Scorecards, reports, forecasts, benchmarks, anomalies, copilots, evaluations and AI audit.
Corporate & Franchise
Employer programs, eligibility, consolidated billing, franchise governance and cross-location comparison.
Developer & Integrations
API apps, webhooks, marketplace, connection status, devices, logs, credentials and sandbox.
Settings & Governance
Organization, brands, locations, roles, regional policy, features, app builder, documents and audit.

Admin home behavior
The first screen should answer: What happened? What needs attention? Why? What is the recommended action? Can I complete it here? Examples include failed payments, expiring memberships, uncontacted hot leads, high-risk members, schedule conflicts, stockouts and device failures.

## Coach App Information Architecture
Area
Key screens and outcomes
Today
Sessions, preparation cards, changes, tasks and clients needing attention.
Clients
Assigned roster, search, filters, alerts and quick status.
Client Overview
Goals, membership/coaching status, recent activity, restrictions, program, nutrition and progress.
Sessions
Prepare, start, verify attendance, record notes, complete, consume credit and follow up.
Training
Program builder, templates, exercise library, assignment, review and adaptation.
Nutrition
Create by AI/template/scratch, targets, meal builder, preview, assign, check-ins and exceptions.
Assessments & Progress
Assessments, measurements, photos, goals, PRs, trends and progress review.
Inbox
Client conversations, contextual threads, requests and handoffs.
Create
Quick creation of program, workout, meal plan, assessment, note, task or message.
Sell / Request Payment
Approved PT, assessment or nutrition packages and secure member payment requests.
Profile & Availability
Schedule, availability, qualifications, device security, preferences and support.

Coach home behavior
The coach sees today, client preparation and exceptions - not gym revenue or a miniature admin menu. “Needs attention” should contain only actionable deviations such as missed workouts, pain reports, expiring programs, check-in problems or member requests.

## Member App Information Architecture
Area
Key screens and outcomes
Personalized Home
Today workout, next meal, next booking, membership status, progress, coach message and quick actions.
Access / Digital Card
QR/NFC/wallet card, live access status, permitted locations and fallback.
Train
Current program, workout execution, previous results, one-tap sets, timers, substitutions and history.
Nutrition
Today plan, calories/protein as configured, Eat & Log, swap, portion, alternatives, grocery and check-in.
Book
Classes, PT, consultations, facilities, favorites, waitlist, calendar and policies.
Progress
Goals, measurements, strength, consistency, attendance, photos, milestones and coach review.
Shop
Membership upgrades, PT, classes, nutrition, products, events, gift cards and order history.
Community & Rewards
Challenges, achievements, points, rewards, referrals, posts and privacy controls.
Membership & Payments
Plan, entitlements, renewal, freeze, requests, invoices, payment methods, wallet and receipts.
Inbox & Support
Coach, club and support conversations with contextual requests and status.
Household
Dependents, guardians, family plan, shared payment and bookings.
Profile, Security & Privacy
Identity, passkeys, Face ID, devices, access methods, consents, preferences, data export/delete.

Member home behavior
Home is personalized and action-first: today workout, next meal, next booking, access/membership issue, progress and coach message. The member should rarely need to understand the internal module structure.

## Front Desk Mode
Area
Key screens and outcomes
Live Check-in
Arrival stream, status, alerts, occupancy and rapid resolution.
Member Lookup
Name, phone, ID, QR, card, recent visits and contextual actions.
Quick Member Actions
Renew, pay balance, freeze, book, issue credential, sign waiver and update contact.
POS
Member-aware cart, scan, tender, receipt, return and payment request.
Bookings
Today schedule, check-in, walk-in, waitlist, reschedule and no-show.
Guests & Trials
Register, verify sponsor, waiver, payment, access and CRM conversion.
Cash Shift
Open, paid-in/out, expected/actual, discrepancy and manager close.
Incidents & Handoffs
Report, triage, escalate and hand off to manager, finance, sales or coach.

## Internal SaaS Console
Area
Key screens and outcomes
Tenant 360
Lifecycle, plan, contacts, usage, costs, health, incidents, integrations and history.
Subscriptions & Finance
Plans, invoices, payments, dunning, entitlements, credits, partner share and margin.
Support & Diagnostics
Tickets, safe support session, jobs, webhooks, configuration, devices and provider state.
Customer Success
Health, adoption, risks, success plans, renewals, expansion and reviews.
Release & Feature Control
Flags, experiments, releases, mobile fleet, app builds, deprecations and notices.
Incident Command
Alerts, impacted tenants, severity, timeline, status updates, runbooks and postmortems.
Security & Compliance
Access, consent, vulnerabilities, evidence, vendors, DSARs, legal holds and audit.
Integrations & Device Fleet
Connector health, credentials, sync, webhooks, devices, versions and remote commands.
Data & AI Operations
Data quality, pipelines, models, prompts, evaluations, safety, budgets and AI incidents.
Cost & Capacity
Cloud, AI, messages, storage, support, unit economics, anomalies and forecasts.

## Nutrition UX - Coach Experience
Step
Required experience
1. Enter context
Client -> Nutrition. Known goals, measurements, activity, training and approved health context load automatically.
2. Choose start
Generate with AI, use template or start from scratch. AI is the default convenience, not automatic publication.
3. Collect missing data
Allergies, dietary pattern, halal, dislikes, cuisine, budget, cooking time, schedule and meal count.
4. Select mode and targets
Flexible targets, structured meals or hybrid. Configure simple, standard or advanced tracking.
5. Build the plan
Daily meal cards, recipes, portions, local food search, remaining targets and Fix with AI.
6. Scale the week
Duplicate day, apply to selected days, generate variations, meal slots and macro-aware alternatives.
7. Preview and assign
Preview exactly as member; set dates, check-in, swaps, free logging and exception thresholds; assign.
8. Manage by exception
Review only low adherence, repeated target misses, stall, hunger/energy issue, swap request or safety signal.

## Nutrition UX - Member Experience
Area
Required experience
Today
Show simple target, next meal and meal cards. Answer “what should I eat now?” before showing a database.
Eat & Log
One tap logs the coach-authored meal; no ingredient-by-ingredient reconstruction.
Swap
Offer approved alternatives inside calorie/protein tolerance and hard allergen constraints.
Log something else
Photo, barcode, search, favorites or recent; clearly label estimates and allow correction.
Plan support
Automatic grocery list, restaurant alternatives, contextual question to coach and weekly check-in.

## POS UX
Primary checkout
Identify member -> tap/scan product -> pay -> done. The cart must automatically understand membership benefits, member pricing, wallet, service credits, stock and tax.

UX requirement
Behavior
Member-first context
Scan QR/search once; show membership, balance, wallet, credits and relevant alerts without exposing unnecessary data.
Fast catalog
Large category tiles, favorites, recent, search and barcode; no ERP-like navigation.
Service fulfillment
Membership or PT sale activates agreement, credits, coach assignment, commission, receipt and access automatically.
Tender
Cash, card, wallet, saved method, gift card and split payment with clear remaining balance.
Recovery
Offline/failed-provider state is explicit; do not double-charge or duplicate the order on retry.

## Biometric UX
Use case
UX and security rule
Face ID / Touch ID in apps
Use operating-system biometric APIs for app unlock and step-up confirmation; Gym OS never receives the device biometric template.
Sensitive action
Show exact action/amount/target, then request biometric/passkey confirmation and record successful assurance level.
Gym facial entry
Separate optional enrollment with informed consent, liveness, alternatives, retention and revocation.
Recognition failure
Use neutral language, allow retry, then offer QR/NFC/front-desk fallback immediately.
Identity Center
Member sees devices, sessions, app biometrics, access methods, consent, recent access and revoke controls.


CHAPTER 6
# Critical End-to-End Flows
The workflows that must remain coherent across domains and surfaces.
## FL-01  Provision a New SaaS Tenant
Actors: Sales/Finance; SaaS Operations; Tenant Owner
#### Happy path
1. Create contract/subscription and select plan, region, currency and isolation tier.
2. Provision tenant, organization, default brand, encryption context and admin identity.
3. Apply regional policy pack, defaults, entitlements, quotas and implementation template.
4. Verify isolation, authentication, notifications, storage, audit and support visibility.
5. Invite tenant owner and start onboarding project.
Critical rules
Key events
Success outcome
Provisioning must be idempotent and resumable. | No production tenant without verified isolation tests.
saas.subscription.started, tenant.provisioned, implementation.started
Tenant owner signs in to a secure, correctly entitled and regionally configured environment.

## FL-02  Onboard, Migrate and Go Live
Actors: Implementation Manager; Gym Admin; Data Specialist; Operations
#### Happy path
1. Complete discovery, target configuration and migration scope.
2. Configure organization, plans, payments, access, schedules, staff, apps and policies.
3. Run migration dry runs, resolve exceptions and reconcile counts/financials.
4. Train roles, enroll devices and rehearse critical workflows/offline operation.
5. Pass readiness gate, execute delta migration and cutover.
6. Run hypercare, reconcile and transition to customer success.
Critical rules
Key events
Success outcome
Financial and entitlement reconciliation requires customer sign-off. | Rollback and continuity plans are mandatory.
migration.reconciled, go_live.approved, tenant.went_live
Business opens on Gym OS with validated data, trained staff and recoverable operations.

## FL-03  Lead to Trial to Active Member
Actors: Lead; Sales; Reception; System
#### Happy path
1. Capture lead with source, consent and deduplication.
2. Score, assign and create next action under response SLA.
3. Book trial/tour/assessment and send reminders.
4. Check in, record outcome and generate approved offer.
5. Complete membership sale, identity/profile merge, payment and contract signature.
6. Activate entitlements, access and onboarding journey while preserving attribution.
Critical rules
Key events
Success outcome
Consent governs outreach channel. | Lead history and attribution survive conversion.
lead.created, trial.attended, opportunity.won, membership.activated
An active member has one identity, paid/valid membership, access and a complete acquisition history.

## FL-04  Sell and Activate a Membership
Actors: Sales/Reception; Member; Finance
#### Happy path
1. Identify or create person and confirm eligibility.
2. Select plan; resolve price, promotion, tax and included entitlements.
3. Present terms, dates, renewal, cancellation and payment schedule.
4. Capture signature/consent and authorize payment.
5. Post invoice/payment/ledger and create membership.
6. Activate entitlements, access credentials, app onboarding and receipt.
Critical rules
Key events
Success outcome
Payment and membership activation are coordinated but independently auditable. | No historical price is overwritten.
order.completed, invoice.issued, payment.succeeded, membership.activated
Member understands the agreement and can immediately use entitled services.

## FL-05  Recurring Billing and Payment Failure Recovery
Actors: Billing Engine; Member; Finance/Reception
#### Happy path
1. Generate invoice from billing schedule and tax rules.
2. Attempt tokenized payment idempotently.
3. On success, post ledger and issue receipt.
4. On failure, classify reason and start policy-specific dunning.
5. Notify member, request payment method update, retry and create staff task when needed.
6. Apply grace/access policy, then recover, suspend or route exception.
Critical rules
Key events
Success outcome
Retries never duplicate charge. | Access impact is transparent and independently configured.
invoice.issued, payment.failed, dunning.started, payment.succeeded
Revenue is recovered with minimal friction and clear member communication.

## FL-06  Freeze, Resume, Upgrade, Downgrade or Cancel Membership
Actors: Member; Manager; Billing/Membership Engines
#### Happy path
1. Member or staff selects lifecycle action and desired effective date.
2. System evaluates eligibility, notice, fees, credits, billing and access effects.
3. Show complete preview and required documents/approval.
4. Authenticate and submit request; approve if policy requires.
5. Apply effective-dated membership, billing, entitlement and access changes.
6. Notify member and preserve prior state/history.
Critical rules
Key events
Success outcome
The preview is deterministic and can be reproduced later. | Cancellation UX must not be intentionally obstructive.
self_service.requested, approval.completed, membership.changed, entitlement.changed
The action completes transparently without manual recalculation or lost history.

## FL-07  Book, Waitlist and Attend a Class
Actors: Member; Instructor; Scheduling System
#### Happy path
1. Member searches eligible sessions with real-time availability.
2. System evaluates entitlement, policy, conflicts and capacity.
3. Create confirmed booking or waitlist entry.
4. Send reminders and promote waitlist with timed confirmation when a spot opens.
5. Member checks in; instructor verifies attendance.
6. Complete attendance or apply late-cancel/no-show policy with appeal path.
Critical rules
Key events
Success outcome
Every denial provides a clear reason and resolution. | No-show prediction cannot silently deny booking.
booking.created, waitlist.promoted, booking.checked_in, no_show.recorded
Capacity is well used and the member experiences fair, predictable booking.

## FL-08  Gym Entry - Online and Offline
Actors: Member; Access Device; Reception
#### Happy path
1. Read QR/NFC/card/credential and resolve member.
2. Evaluate signed local policy/cache or online entitlement service.
3. Check membership, zone, time, capacity, duplicate entry and configured financial rules.
4. Grant/deny and actuate gate with privacy-safe message.
5. Queue event locally if offline and synchronize later.
6. Offer QR/manual fallback and staff resolution on failure.
Critical rules
Key events
Success outcome
Offline grants are risk-bounded and expire. | Public screens never show sensitive balance or health reason.
access.requested, access.granted, access.denied, sync.reconciled
Entry is fast, reliable and auditable even during temporary network loss.

## FL-09  Enroll and Use Facial Gym Entry
Actors: Member; Front Desk; Biometric Vendor/Edge
#### Happy path
1. Member reviews purpose, storage, retention, alternatives and consent.
2. Authenticate, capture guided enrollment and pass liveness/quality checks.
3. Create encrypted vendor-neutral reference and activate method.
4. At entry, perform liveness and match, then evaluate normal access policy.
5. Grant entry or offer immediate alternative; log only necessary result.
6. Member can revoke; system removes templates according to policy.
Critical rules
Key events
Success outcome
Face entry is opt-in and not the sole method. | A face match never bypasses membership/access policy.
biometric.enrolled, liveness.failed, access.granted, biometric.revoked
Consenting members receive hands-free entry with privacy and fallback control.

## FL-10  Issue and Redeem a Guest Pass
Actors: Member/Host; Guest; Reception
#### Happy path
1. Host requests pass under membership/abuse policy.
2. Guest receives link, verifies identity/contact and signs waiver.
3. System creates temporary credential, time/location window and CRM lead if consented.
4. Guest checks in via credential and policy.
5. Record attendance and trigger follow-up/conversion journey.
6. Credential expires automatically.
Critical rules
Key events
Success outcome
Guest data and marketing consent are separate. | Repeated abuse blocks reward/access until review.
guest_pass.issued, waiver.signed, access.granted, trial.converted
Guests enter safely and become measurable acquisition opportunities.

## FL-11  Front Desk Resolve an Access or Account Issue
Actors: Reception; Member; Manager/Finance
#### Happy path
1. Scan/search member and open contextual issue card.
2. System explains denial/alert and available permitted actions.
3. Reception completes routine resolution: pay, renew, sign, update or reissue.
4. If permission threshold is exceeded, create approval/handoff without losing context.
5. Re-evaluate access and complete check-in.
6. Record reason, action and outcome in timeline.
Critical rules
Key events
Success outcome
Reception sees only data necessary to resolve the issue. | Overrides are reason-coded and auditable.
access.denied, front_desk.case.resolved, access.granted
Most problems resolve in one workspace without manager or module hopping.

## FL-12  Retail POS Sale
Actors: Reception/POS Clerk; Member/Guest
#### Happy path
1. Identify member or choose guest checkout.
2. Scan/tap items; apply member price, tax, promotion and stock reservation.
3. Review cart and choose cash/card/wallet/gift/split tender.
4. Authorize payment and complete order idempotently.
5. Post ledger, decrement stock and issue receipt.
6. Update member purchase history and analytics.
Critical rules
Key events
Success outcome
The same retry cannot create duplicate order/payment. | Out-of-stock/quarantined items cannot complete.
order.completed, payment.succeeded, stock.adjusted, receipt.sent
Checkout completes quickly with correct inventory and financial records.

## FL-13  Sell PT or Nutrition Package and Fulfill Credits
Actors: Coach/Reception; Member; Finance
#### Happy path
1. Select member and approved service package.
2. Show price, validity, coach assignment, commission and terms.
3. Collect payment directly or send secure payment request to member.
4. On successful payment, issue service credits and assign relationship if needed.
5. Book first session/consultation and send receipt.
6. Track credit consumption, expiry and commission.
Critical rules
Key events
Success outcome
Coach sales are limited to approved products and permissions. | Credits issue only after configured payment condition.
payment_request.sent, payment.succeeded, credit.issued, commission.earned
The member buys and starts the service without reception handoffs.

## FL-14  Return, Refund or Void a Sale
Actors: Staff; Manager; Finance
#### Happy path
1. Open original receipt/order and select eligible line/amount.
2. System calculates stock, tax, credit, entitlement and commission impact.
3. Capture reason, evidence and preferred refund method.
4. Request approval if threshold/policy requires.
5. Post compensating ledger entries and execute provider refund/credit.
6. Return stock if valid, revoke unused credits/entitlements and notify member.
Critical rules
Key events
Success outcome
Posted entries are never deleted. | Consumed service credits require dispute/exception policy.
approval.requested, refund.completed, ledger.posted, stock.adjusted
The financial, inventory and entitlement effects remain synchronized and explainable.

## FL-15  Replenish Inventory
Actors: Inventory Manager; Supplier; Finance
#### Happy path
1. Low-stock/forecast signal creates suggestion or requisition.
2. Review quantity, supplier, cost, expiry risk and budget.
3. Approve and issue purchase order.
4. Receive goods, scan lot/expiry and record variance/damage.
5. Update stock/cost and match supplier invoice.
6. Resolve variance and close purchase order.
Critical rules
Key events
Success outcome
Receiving and invoice approval may require separation of duties. | Expired/quarantined stock is not available for sale.
stock.low, purchase_order.approved, stock.received, reconciliation.mismatch.detected
Stock is available at the right location with correct cost and audit.

## FL-16  Plan Staff, Deliver Work and Run Payroll
Actors: Manager; Staff/Coach; Payroll/Finance
#### Happy path
1. Publish shifts from availability, demand, qualifications and labor rules.
2. Staff clocks in/out, records breaks and completes scheduled work.
3. System captures delivered sessions/classes, sales and eligible commission.
4. Exceptions such as missed clock, overtime or disputed session enter review.
5. Preview payroll, approve, lock and export.
6. Post cost/commission data for analytics.
Critical rules
Key events
Success outcome
Locked payroll periods change only through controlled correction. | Protected HR data is separated from operational performance.
shift.started, session.completed, commission.earned, payroll.approved
Compensation is accurate, traceable and tied to verified delivery.

## FL-17  Coach Assigns a Training Program
Actors: Coach; Member; AI Assistant
#### Happy path
1. Open client training context, goals, history, equipment and restrictions.
2. Start from template, AI draft or scratch.
3. Build blocks/workouts, prescriptions, alternatives and progression.
4. Validate constraints, schedule, volume and health warnings.
5. Preview member experience, set dates and assign.
6. Member receives explanation and first workout; coach monitors adherence.
Critical rules
Key events
Success outcome
AI output is draft until approved. | Hard contraindications cannot be overridden silently.
program.assigned, notification.sent, workout.started
A safe, personalized plan reaches the member quickly with a clear start path.

## FL-18  Member Completes and Logs a Workout
Actors: Member; Coach
#### Happy path
1. Open Today and start assigned workout.
2. See exercise, video/cues, target and previous result.
3. Log sets rapidly with defaults, timer and optional wearable input.
4. Request allowed substitution for equipment, time or low-risk limitation.
5. Complete workout, add feedback/pain and review summary.
6. System updates adherence/PRs and routes exceptions to coach.
Critical rules
Key events
Success outcome
Pain/safety signal interrupts unsafe continuation and offers escalation. | Offline logs synchronize idempotently.
workout.started, set.logged, workout.completed, client.attention.required
Logging takes minimal effort and produces reliable progression data.

## FL-19  Coach Creates and Assigns a Nutrition Plan
Actors: Coach/Nutritionist; Member; AI Assistant
#### Happy path
1. Open client Nutrition and choose AI, template or scratch.
2. Reuse known goals/measurements/activity and collect only missing preferences/allergies.
3. Select flexible, structured or hybrid mode and target tracking level.
4. Generate/build meals; review targets, allergens, cuisine, budget and alternatives.
5. Generate rest of week, preview as member and configure swaps/check-in/exceptions.
6. Assign with dates and notify member.
Critical rules
Key events
Success outcome
Allergens are hard constraints. | Medical/high-risk nutrition requires qualified scope and review.
nutrition_plan.assigned, notification.sent, nutrition_checkin.scheduled
A reviewed, locally relevant and flexible plan is assigned in roughly one minute from a strong starting point.

## FL-20  Member Follows, Logs and Swaps a Meal
Actors: Member; Coach/Nutritionist
#### Happy path
1. Home shows next meal and simple daily targets.
2. If eaten as planned, tap Eat & Log once.
3. If not suitable, choose smart swap, portion change, skip or log something else.
4. System offers alternatives within configured tolerance and allergen rules.
5. Photo/barcode/search logging shows estimate/source and allows correction.
6. Adherence updates; only meaningful exception reaches coach.
Critical rules
Key events
Success outcome
The member is not forced to rebuild coach-authored meals ingredient by ingredient. | Photo estimates communicate uncertainty.
meal.logged, meal.swapped, adherence.changed, coach_review.required
Planned eating is trackable in one to two taps and remains flexible.

## FL-21  Weekly Coaching/Nutrition Check-in and Adjustment
Actors: Member; Coach/Nutritionist; AI Assistant
#### Happy path
1. Prompt member for weight/measure, hunger, energy, difficulty, symptoms and notes.
2. Combine check-in with adherence, attendance, workouts and trend context.
3. Generate concise review and flag risk/stall/anomaly.
4. Coach reviews recommendation and opens plan adjustment.
5. Preview change, obtain approval/consent if needed and publish version.
6. Explain change to member and schedule next check-in.
Critical rules
Key events
Success outcome
Automated recommendation does not replace qualified judgment. | Version history preserves what changed and why.
nutrition_checkin.submitted, progress_review.required, program.adjusted
Plans adapt based on evidence without requiring daily coach micromanagement.

## FL-22  Report and Resolve a Health/Safety Incident
Actors: Member/Staff; Manager; Safety/Legal
#### Happy path
1. Capture incident type, time, location, people and immediate action.
2. Triage severity and trigger emergency or safety isolation if required.
3. Collect witnesses/evidence under privacy controls.
4. Notify required roles, create tasks and preserve legal hold if applicable.
5. Investigate root cause and corrective actions.
6. Close with evidence, communication and trend reporting.
Critical rules
Key events
Success outcome
Emergency response takes priority over data completeness. | Sensitive incident access is need-to-know.
incident.reported, asset.isolated, incident.escalated, corrective_action.closed
The organization responds quickly, protects privacy and proves corrective action.

## FL-23  Unified Member Conversation and Handoff
Actors: Member; Reception/Sales/Coach
#### Happy path
1. Message arrives from app, WhatsApp, SMS or email and resolves identity/context.
2. Route to correct shared inbox by purpose, location, language and SLA.
3. Agent sees permitted Member 360 context and prior messages.
4. Respond using approved template or assisted draft.
5. If another team is needed, hand off thread with task and context.
6. Resolve and capture outcome/feedback.
Critical rules
Key events
Success outcome
Consent and channel suitability are checked at send time. | Handoff does not duplicate messages or reset SLA silently.
message.received, conversation.assigned, handoff.created, conversation.resolved
The member receives one coherent service experience across departments.

## FL-24  Build and Run a Retention Automation
Actors: Manager; Automation Engine; Coach/Sales
#### Happy path
1. Select trigger such as no visit for ten days or churn score threshold.
2. Add eligibility, exclusions, consent and contact frequency rules.
3. Configure notification, wait, condition, task and escalation steps.
4. Simulate on historical/current cohort and review projected volume/cost.
5. Approve, publish and monitor runs/outcomes.
6. Handle failures or pause with kill switch.
Critical rules
Key events
Success outcome
Automation inherits permissions and communication policy. | Outcome is measured against a holdout where appropriate.
workflow.published, workflow.started, task.created, workflow.completed
At-risk members receive timely outreach and staff see only actionable exceptions.

## FL-25  Admin Copilot Explains Performance and Launches an Action
Actors: Owner/Manager; AI Platform; Approver
#### Happy path
1. User asks a business question in natural language.
2. System retrieves permissioned metrics, definitions, freshness and relevant drivers.
3. AI returns explanation, uncertainty and drill-down references.
4. User requests action such as create retention campaign.
5. AI produces structured draft, target cohort, cost, exclusions and expected effect.
6. User/approver reviews and executes through guarded tool; audit records result.
Critical rules
Key events
Success outcome
AI does not invent unavailable metrics or bypass permission. | High-impact actions require preview and approval.
ai.requested, ai.response.generated, ai.tool.proposed, ai.tool.executed
The manager moves from question to governed action without manual report assembly.

## FL-26  Corporate Employee Enrollment
Actors: Employer Admin; Employee; Gym Admin
#### Happy path
1. Employer provides/synchronizes eligible roster.
2. Employee verifies identity and eligibility.
3. Select eligible benefit/plan and dependents if allowed.
4. Accept terms, privacy and any employee contribution.
5. Create membership, entitlements, billing split and access.
6. Employer sees aggregate enrollment/utilization only.
Critical rules
Key events
Success outcome
Employer cannot access individual coaching/health data. | Eligibility changes are effective-dated and recoverable.
eligibility.verified, employee.enrolled, membership.activated
Employees self-enroll quickly while privacy and billing responsibilities remain clear.

## FL-27  Franchise Leader Reviews and Resolves a Location Exception
Actors: Regional Leader; Club Manager
#### Happy path
1. Command center detects KPI or compliance exception.
2. Drill into normalized drivers and affected cohort/location.
3. Compare against peer branches and configuration differences.
4. Create corrective plan/task with owner, due date and target.
5. Local manager executes within approved autonomy.
6. Track outcome and close or escalate.
Critical rules
Key events
Success outcome
Metrics use identical definitions and local context. | Cross-location view follows hierarchy permissions.
location.exception.detected, task.created, corrective_action.closed
Head office governs outcomes without micromanaging local work.

## FL-28  Install and Operate an Integration
Actors: Tenant Admin; Partner; Gym OS Platform
#### Happy path
1. Select integration and review capabilities, permissions, price and region.
2. Authorize tenant and provider with least scopes.
3. Configure mapping and validate connection in test mode.
4. Activate sync/webhooks and monitor first run.
5. Handle retries, conflicts, reconciliation and credential rotation.
6. Uninstall safely with export/cleanup if needed.
Critical rules
Key events
Success outcome
Partner receives only authorized tenant data. | Uninstall revokes credentials and stops data flow.
integration.installed, integration.connected, integration.sync.failed, integration.uninstalled
Integration is self-service, observable and safely removable.

## FL-29  Developer Creates an API App and Webhook
Actors: Developer; Tenant Admin
#### Happy path
1. Register app in developer portal and choose environment.
2. Request scopes and configure redirect/webhook endpoints.
3. Tenant admin reviews and grants access.
4. Develop against sandbox with test data and logs.
5. Promote to production, rotate credentials and monitor usage.
6. Handle version/deprecation notices and contract tests.
Critical rules
Key events
Success outcome
Scopes are granular and tenant-bound. | Webhooks are signed, replayable and idempotently consumed.
developer_app.created, oauth.granted, webhook.delivered
A partner can integrate without private support-led setup.

## FL-30  Member Data Export or Deletion Request
Actors: Member; Privacy Team; Tenant Admin
#### Happy path
1. Member submits request after step-up authentication.
2. Verify identity, jurisdiction, scope, legal holds and tenant/platform responsibilities.
3. Collect data from governed sources and validate completeness.
4. For export, package encrypted files with manifest and expiry.
5. For deletion, apply retention exceptions, anonymize/delete and revoke credentials.
6. Notify requester and retain evidence of fulfillment.
Critical rules
Key events
Success outcome
Deletion does not erase legally required financial/audit evidence. | Export links are encrypted and time-limited.
data_subject_request.created, data_export.ready, data.deleted
Privacy rights are fulfilled securely, consistently and on time.

## FL-31  Operate a Branded Mobile App Release
Actors: Tenant Brand Admin; Gym OS Release Team
#### Happy path
1. Configure brand tokens, navigation, content and legal metadata.
2. Validate assets, store accounts, signing and privacy labels.
3. Preview all supported languages, devices and feature states.
4. Build, test, sign and submit through controlled pipeline.
5. Track review, stage rollout and monitor crash/adoption.
6. Roll back feature/configuration or issue hotfix when needed.
Critical rules
Key events
Success outcome
Tenant customization cannot inject unreviewed code. | Signing assets are isolated and audited.
build.completed, store_release.approved, mobile_version.deprecated
Many branded apps release predictably without fragmenting the codebase.

## FL-32  Detect, Communicate and Recover from an Incident
Actors: SRE/Incident Commander; Support; Tenant Admin
#### Happy path
1. Monitoring detects symptom and maps impacted workflows/tenants.
2. Declare severity, assign roles and open timeline/runbook.
3. Contain through failover, kill switch, degradation or provider fallback.
4. Publish status and targeted tenant communication.
5. Restore service, reconcile delayed/failed work and verify business state.
6. Close incident, issue postmortem and track corrective actions.
Critical rules
Key events
Success outcome
Customer communication reflects known facts, not speculation. | Recovery includes data/business reconciliation, not uptime alone.
incident.declared, status_update.published, incident.resolved, postmortem.published
Impact is minimized, customers are informed and recurrence risk is reduced.

## FL-33  Tenant Offboarding and Data Handover
Actors: Tenant Owner; Finance/CS; Security/Data
#### Happy path
1. Confirm cancellation, notice, final obligations and timeline.
2. Freeze configuration changes and prepare final reconciliation/export.
3. Deliver structured encrypted export and obtain acknowledgement.
4. Set read-only/archive state, revoke users/integrations/devices and settle billing.
5. Apply retention/legal hold and schedule deletion.
6. Produce deletion/offboarding evidence and release domains/app assets.
Critical rules
Key events
Success outcome
Data and credentials are not deleted before obligations and export complete. | Continued costs and access terminate visibly.
tenant.offboarding.started, data_export.ready, credentials.revoked, tenant.archived
The customer exits cleanly with owned data and no hidden residual access.

## FL-34  Support Investigates a Tenant Issue Safely
Actors: Support Agent; Tenant Admin; Engineering
#### Happy path
1. Open ticket and collect tenant-safe diagnostics automatically.
2. Review logs, jobs, configuration, device/integration status without impersonation.
3. If user-context reproduction is necessary, request consent and time-limited support session.
4. Reproduce, resolve or escalate with correlation evidence.
5. End session, revoke temporary access and document actions.
6. Send resolution, collect feedback and link systemic follow-up.
Critical rules
Key events
Success outcome
Support has no standing production data access. | Sensitive actions need explicit approval and audit.
support.session.started, support.ticket.escalated, support.session.ended
Issues resolve quickly without sacrificing customer privacy or control.


CHAPTER 7
# Identity, Roles, Permissions & Biometrics
A unified identity layer for digital and physical trust.
## Identity Model
A global authentication identity may link to multiple tenant profiles and roles; tenant data never merges automatically.
Person, member, staff and lead are business profiles/relationships rather than separate login systems.
Authentication proves who is acting; authorization determines what that identity may do in a tenant and context.
Physical credentials identify a person or temporary visitor; access policy independently grants or denies entry.
## Role Catalog
Role
Purpose and scope
Platform Super Admin
Internal only; tenant lifecycle, platform operations and emergency control. No standing access to customer content.
Support Agent
Tickets and diagnostics; temporary consented support sessions; no unrestricted finance, health or biometric access.
Customer Success Manager
Tenant health, adoption, success plans, renewals and expansion; aggregate operational context.
Organization Owner
Full tenant business authority, subscription, enterprise settings and delegated administration.
Regional / Franchise Manager
Scoped multi-location oversight, standards, comparison, approvals and exception management.
Club Manager
Location operations, staff, finance thresholds, memberships, incidents, schedules and performance.
Receptionist
Check-in, member lookup, routine account resolution, booking, guest registration and permitted POS.
Sales Representative
Leads, trials, offers, approved products, activities and conversion; limited member/financial context.
Coach / Personal Trainer
Assigned clients, sessions, training, progress, permitted health context and contextual messages.
Nutritionist
Assigned clients, nutrition plans, relevant assessments, check-ins and qualified health context.
Finance / Accountant
Invoices, payments, ledger, reconciliation, tax, periods and exports; no coaching details.
Inventory / Operations Manager
Catalog/SKUs, suppliers, purchasing, stock, assets, facilities and maintenance.
Staff Member / Instructor
Own shifts, assigned sessions/classes, attendance, tasks and limited member context.
Corporate Benefits Admin
Corporate eligibility, enrollment and aggregate utilization/billing only.
Member
Own profile, household permissions, access, bookings, plans, payments, health consents and data rights.
Guardian / Household Manager
Authorized dependent actions, bookings, payments and consents according to relationship.
Developer / Integration Partner
Only tenant-authorized API scopes, sandbox, webhooks and partner operations.

## Permission Matrix - Baseline
Legend: V=view; M=manage; A=approve/admin; S=scoped to relationship/location/tenant grant; -=none. Final permissions are policy-based and field-sensitive.
Role
People & CRM
Membership
Billing & Ledger
POS & Inventory
Schedule & Access
Coaching & Health
Communications
Analytics
Settings & Roles
SaaS / Platform
Platform Super Admin
S
S
S
S
S
-
S
A
A
A
Support Agent
S
S
S
S
S
S
S
S
-
M
Customer Success Manager
S
V
V
V
V
-
M
M
-
M
Organization Owner
A
A
A
A
A
A
A
A
A
V
Regional / Franchise Manager
M
M
A
M
M
M
M
M
M
-
Club Manager
M
M
A
A
A
M
M
M
M
-
Receptionist
S
S
S
S
S
-
S
V
-
-
Sales Representative
M
V
S
S
S
-
M
S
-
-
Coach / Personal Trainer
S
V
-
S
S
M
S
S
-
-
Nutritionist
S
V
-
-
S
M
S
S
-
-
Finance / Accountant
V
V
A
V
V
-
V
M
S
-
Inventory / Operations Manager
V
V
V
A
M
-
S
M
S
-
Staff Member / Instructor
S
-
-
-
S
S
S
S
-
-
Corporate Benefits Admin
S
S
S
-
-
-
S
S
-
-
Member
S
S
S
S
S
S
S
S
-
-
Guardian / Household Manager
S
S
S
S
S
S
S
S
-
-
Developer / Integration Partner
S
S
S
S
S
S
S
S
-
S

## Authentication Assurance
Level
Use
AAL-1 Routine
Normal authenticated session for low-risk viewing and routine actions.
AAL-2 Elevated
MFA/passkey or recent biometric for payment method, sensitive profile, export or membership change.
AAL-3 Privileged
Strong MFA, managed device and approval for roles, large refunds, payroll, security or tenant lifecycle.
Emergency / Break-glass
Time-limited, reasoned, heavily audited access with immediate review.

## Biometric Boundaries
Face ID/Touch ID authenticates locally through the operating system; Gym OS stores only the resulting assurance, never the device biometric.
Gym facial recognition is a separate high-risk capability requiring opt-in consent, liveness, encrypted templates, retention and alternatives.
Staff attendance biometrics are separate from member access and must follow employment law and local policy.
Biometric match never grants business entitlement by itself.

CHAPTER 8
# Data, Events, Automation, AI & Technical Architecture
A trustworthy architecture for one source of truth and intelligent execution.
## Canonical Aggregate Model
Domain aggregate
Root
Ownership
Invariant
Tenant / Organization
Tenant
Owns organizational hierarchy, region, configuration, plan and isolation context.
Every persisted and emitted object belongs to exactly one tenant or an explicit platform scope.
Identity
Identity
Owns credentials, passkeys, sessions, devices and federation links.
Authentication identity is separate from tenant business profiles.
Person / Member 360
Person
Owns canonical person and tenant relationships; timeline is a projection.
Duplicate merge never loses source provenance or financial/health history.
Lead / Opportunity
Opportunity
Owns sales stage, owner, activities, offer and outcome.
Conversion preserves attribution and links to the canonical person/member.
Catalog / Price
Product
Owns sellable definition; prices/promotions are effective-dated policies.
Historical orders reference resolved immutable commercial terms.
Membership
Membership
Owns agreement, lifecycle and granted entitlements.
Membership, billing and access states are distinct and coordinated through events.
Billing Account / Invoice
BillingAccount
Owns schedules, invoices, balances, payment intents and dunning.
Invoices are versioned financial documents; paid status derives from allocated payments/credits.
Ledger / Wallet
Ledger
Owns immutable postings, balances, wallet and service-credit movement.
Balances are computed from postings; corrections are compensating entries.
Order
Order
Owns cart-to-completion commercial transaction and fulfillment references.
Completion is idempotent and each line has explicit fulfillment state.
Inventory
InventoryItem
Owns stock positions, lots, reservations and movements by location.
Available quantity cannot include quarantined, expired or reserved stock.
Schedule / Resource
ScheduledInstance
Owns occurrence, resources, capacity and published state.
Published conflicts require explicit authorized resolution.
Booking
Booking
Owns reservation, waitlist, cancellation and attendance intent.
Booking state changes evaluate entitlement and policy at the relevant time.
Access Decision
AccessDecision
Owns evaluated policy result and associated access event.
A credential identifies; only policy and entitlement authorize access.
Staff / Employment
Employment
Owns assignment, qualification, shift, time and compensation context.
Protected employment data has separate visibility from operational data.
Coaching Program
Program
Owns versioned training prescription and assignment.
Completed logs remain linked to the exact program/workout version executed.
Nutrition Plan
NutritionPlan
Owns targets, meal structure, alternatives, assignment and versions.
Allergen constraints and plan history survive edits and swaps.
Assessment / Goal
Assessment
Owns assessment result, measurement provenance, goal and milestone.
Measurement value, unit, source and observed time are immutable provenance.
Consent / Incident
ConsentRecord / Incident
Owns legal/safety evidence, version, response and corrective actions.
Withdrawal does not rewrite the fact that a prior version was signed at a past time.
Conversation
Conversation
Owns cross-channel thread, messages, assignment and status.
Messages retain channel delivery evidence and permission-aware context links.
Workflow / Case
WorkflowRun / Case
Owns automated execution or accountable human exception work.
Every step/action records actor/service identity, inputs, result and recovery state.
Integration / Device
IntegrationInstall / Device
Owns tenant authorization, configuration, health, credentials and sync.
Revocation stops access/data flow and can be proven.
Content / Brand App
ContentItem / BrandedApp
Owns localized content, targeting, app configuration and release state.
Published versions are immutable; rollback points to a prior approved version.

## Logical Technical Architecture
Layer
Responsibilities
Clients and Edge
Admin Web, Coach/Member mobile apps, front desk, kiosk, partner clients and managed edge/device runtime.
API Gateway and BFFs
Authentication, tenant resolution, rate limiting, API versioning, request policy and surface-specific composition.
Domain Application Layer
Explicit modules/services for the domain catalog in this blueprint; commands own state changes and queries return permission-filtered views.
Workflow and Intelligence
Automation engine, task/approval service, search/command, analytics APIs, AI orchestration and guarded tools.
Events and Asynchronous Work
Transactional outbox, event bus, queues, schedulers, retries, dead-letter handling and replay.
Data Stores
Relational OLTP, immutable financial/audit stores, object/media storage, cache, search index, event archive and analytical warehouse.
Integration Plane
Provider adapters, webhooks, public APIs, connector workers, secure credential vault and marketplace governance.
Platform Control Plane
Tenant provisioning, configuration, flags, SaaS billing, app/device fleet, support, observability, security and incident control.

## Architecture Decisions
Start with a well-enforced modular architecture and explicit domain contracts; extract independently deployable services when scale, risk, team ownership or availability justifies it.
Use an event-driven integration model, but do not use events as an excuse for unclear ownership or eventual consistency in member-facing critical decisions.
Default tenant isolation uses enforced tenant context at every layer; enterprise tiers may add dedicated databases, keys, regions or deployments.
Keep operational transactions separate from analytics workloads; feed the warehouse through governed events and change capture.
Financial ledger, audit and consent evidence are append-oriented and integrity protected.
Mobile and edge clients use bounded offline data and explicit synchronization protocols, not arbitrary local replicas.
Provider integrations sit behind canonical capabilities so payment, messaging and hardware vendors can change.
AI has no direct database access and acts only through authorized retrieval and guarded tools.
## Storage and Data Separation
Class
Primary content
Transactional relational
Members, memberships, bookings, catalog, orders, workflow state and configuration.
Immutable financial/audit
Ledger postings, audit evidence, consent signatures and high-risk decisions.
Object/media
Contracts, receipts, progress media, exercise/recipe content, exports and diagnostic bundles.
Search
Permission-filterable projections for global search and knowledge navigation.
Cache/edge
Time-limited sessions, reference data, signed access snapshots and performance accelerators.
Event archive
Governed event stream for replay, timelines and downstream recovery.
Warehouse/lakehouse
Historical facts, conformed dimensions, metrics, forecasts, evaluations and data products.

## Event and Automation Contract
State changes publish durable domain events through a transactional guarantee.
Consumers are idempotent and own retry, dead-letter and replay behavior.
Automation executes with a service identity and cannot exceed configured permissions.
Financial, access, health, employment and deletion actions use guarded domain commands, not generic updates.
Every execution exposes correlation, reason, version, inputs, outputs, cost and recovery state.
## AI Reference Architecture
Component
Required behavior
Use-case registry
Owner, users, purpose, data classes, risk tier, tools, approvals, metrics and kill switch.
Permissioned retrieval
Tenant, role, relationship, record and field checks before retrieval and before response.
Model routing
Choose model by quality, latency, region, privacy, cost and fallback policy.
Grounding and evidence
Answers link to governed metrics/records and expose freshness, uncertainty or missing data.
Guarded tools
Typed action schema, permission check, preview, risk policy, idempotency, approval and audit.
Evaluation
Offline test sets plus online task success, acceptance, safety, latency, cost and business impact.
Operations
Prompt/model versioning, budgets, drift, incidents, red-team findings and rollback.


CHAPTER 9
# SaaS Commercial & Operating Model
How Gym OS is packaged, provisioned, supported and scaled as a business.
## Packaging Framework
Plan
Target customer
Packaging intent
Starter
Independent gym
Core members, memberships, billing, schedule, check-in, front desk, basic coach/member experiences and support.
Growth
Growing multi-location operator
CRM, marketing, advanced self-service, POS/inventory, automations, retention and multi-location analytics.
Pro
Established brand
Advanced coaching/nutrition, AI, white-label configuration, API, integrations, advanced data and priority support.
Enterprise
Chain, franchise or corporate program
SSO/SCIM, custom roles, dedicated controls, data residency, corporate/franchise portals, SLA and procurement package.

Exact limits and prices are commercial decisions validated against cost and willingness to pay. The blueprint requires transparent public packaging, pre-purchase clarity and no intentional cancellation friction.
## Metered Cost Drivers
Driver
Possible unit
Control
Active members/locations
Monthly active member or location tier
Plan allowance and overage/upgrade path
AI
Tool run, model unit or budget
Model routing, quotas, tenant budget and value metric
Messaging
SMS/WhatsApp/email delivery
Pass-through cost, templates, caps and channel fallback
Storage/media
GB-month and egress
Retention, compression, archive and quota
API/webhooks
Calls, events or partner tier
Rate limits, plan allowance and marketplace model
White-label operations
App/brand/build fleet
Setup, annual operation and supported-version policy

## Tenant Lifecycle
Trial -> Contracted -> Provisioning -> Implementation -> Live -> Growth/Renewal -> Past Due -> Suspended -> Cancelled -> Read-only/Archived -> Deleted
Each state has explicit product access, billing, data, support, export and deletion behavior.
Suspension protects revenue/security without destroying customer data.
Offboarding exports, revokes credentials, settles obligations and applies retention before deletion.
## Operating Model
Function
Mandatory capability
Sales
Demo tenants, trials, proposals, procurement tracking, partner attribution and clean implementation handoff.
Implementation
Configuration, migration, training, device readiness, go-live gates, rollback and hypercare.
Customer Success
Health score, adoption, success plans, business reviews, renewal, expansion and churn prevention.
Support
Knowledge, diagnostics, safe support sessions, SLAs, incident linkage and feedback.
Finance/FinOps
SaaS billing, collection, tax, margin, tenant cost, partner share and reconciliation.
Security/Compliance
Controls, evidence, vendor risk, privacy requests, audits, incidents and enterprise assurance.
Product/Engineering
Domain ownership, roadmap, experimentation, quality, releases, deprecation and cost-aware architecture.

CHAPTER 10
# Security, Reliability & Non-functional Requirements
The quality envelope that makes the product trustworthy and commercially viable.
## Non-functional Requirement Baseline
Area
Initial requirement / target
Tenant isolation
100% of application, job, event, file, search, cache, telemetry and AI paths carry validated tenant context; automated isolation tests block release.
Availability
Initial design targets: access decision 99.99%; core billing/booking 99.95%; admin/member/coach experiences 99.9%, measured independently and excluding documented external-provider failures.
Latency
Target p95: common mobile API under 350 ms, admin API under 500 ms, search under 750 ms, online access decision under 700 ms, edge/offline access under 250 ms, excluding network/provider latency where stated.
Mobile experience
Warm launch target under 1.5 s on supported reference devices; critical daily flows remain usable on constrained networks; crashes and hangs stay below agreed error budgets.
Scale envelope
Architecture and load tests should support the commercial forecast with at least 3x peak headroom; reference planning envelope includes thousands of tenants, tens of thousands of locations and tens of millions of people without redesign.
Recovery
Tier-1 financial/access data uses near-zero-loss replication where feasible; initial target RPO <= 5 minutes and RTO <= 60 minutes for critical regional failure, with stricter provider-specific goals where justified.
Offline operation
Access and selected front-desk functions continue using signed time-limited data; every offline command has conflict, duplicate and reconciliation behavior.
Security
Strong encryption, managed secrets, MFA for privileged users, secure SDLC, regular penetration testing, vulnerability SLAs and current industry control frameworks appropriate to risk.
Privacy
Purpose limitation, data minimization, consent versioning, retention, deletion/export, regional policy and privacy review for sensitive features.
Accessibility
Target the current widely adopted AA accessibility level across web and mobile; critical defects block release and assistive-technology tests are automated plus manual.
Localization
Every critical flow ships in Arabic RTL and English LTR with locale-aware formatting, mixed-direction testing and regional policy validation.
Data quality
Critical data products publish owner, lineage, freshness, completeness and quality state; bad data does not silently feed decisions or AI.
Auditability
All privileged, financial, access, consent, biometric, AI and support actions record actor, tenant, purpose, before/after or reference, time, device and outcome.
API quality
Versioned contracts, documented error model, idempotency for mutations, signed webhooks, rate limits, sandbox and compatibility tests.
Observability
Critical paths expose logs, metrics, traces, business outcomes and tenant impact; alerts link to owner and runbook.
AI quality and safety
Each use case has offline/online evaluations for accuracy, groundedness, safety, latency, cost and task success; high-risk actions require human approval.
Cost efficiency
Cloud, AI, messaging, storage, integration and support costs are attributable by tenant and compared to plan revenue/gross margin.
Maintainability
Every domain has owner, contract, decision record, test suite, runbook and deprecation policy; no hidden cross-domain database writes.

## Data Classification and Handling
Class
Examples
Handling baseline
Public
Published marketing and public help.
Integrity and brand controls.
Internal
Operational configuration and non-sensitive staff content.
Tenant access control and normal retention.
Confidential
Member contact, contracts, business metrics and support.
Encryption, least privilege, audit and controlled export.
Restricted
Financial, health, biometric, employment, progress media and identity credentials.
Field controls, strong assurance, purpose limitation, short retention where possible and enhanced monitoring.

## Continuity Tiers
Tier
Examples
Expected behavior
Tier 1 - Club critical
Access, check-in, core POS, payment/ledger integrity.
Offline/degraded mode, highest SLO, rapid failover and reconciliation.
Tier 2 - Business critical
Membership, booking, billing, staff schedule, communications.
High availability, queued work and documented recovery.
Tier 3 - Insight/engagement
Analytics, AI, community, campaigns and advanced reports.
Graceful degradation; no corruption of critical operations.


CHAPTER 11
# Roadmap, Dependencies & Release Gates
Preserve the complete vision while shipping in a controlled sequence.
## Foundation
Build the trustworthy platform substrate.
Tenant/org hierarchy and isolation
Identity, passkeys, roles, policies and audit
Core Person/Member 360 model
Catalog, event platform and notifications
Security, observability, CI/CD, localization/RTL and design system
SaaS plans, entitlements and internal control-plane foundations
Exit gate
Gate: isolation, authentication, audit, event, release and recovery tests pass.

## Pilot
Validate the end-to-end gym core with design partners.
Admin Home, CRM, members and basic analytics
Memberships, contracts, entitlements, billing, payments and ledger
Scheduling, booking, front desk, QR/NFC check-in and access adapters
Coach Today, clients, sessions, basic training and assessments
Member Home, access card, booking, membership/payment self-service
Migration, implementation, support diagnostics and go-live controls
Exit gate
Gate: design partners operate daily, financial/access reconciliation passes and critical task success meets target.

## V1 General Availability
Ship a commercially complete core for modern gyms.
Complete membership lifecycle and dunning
POS, receipts, cash shifts, service credits and core inventory
Waitlists, no-show policy, guest/trial and kiosk basics
Training program builder and member workout logging
Health/safety, consent, incidents and contextual communication
Member self-service, household basics and digital wallet/card
Exit gate
Gate: commercial onboarding, billing, support and reliability playbooks are repeatable.

## V1.5 Growth
Increase engagement, retention and operational leverage.
Best-in-class nutrition planning and member logging
Automations, tasks, approvals, churn/no-show intelligence
Advanced analytics, forecasting and exception dashboards
Community, challenges, referrals and rewards
Staff, commissions, payroll preview and advanced inventory/procurement
Initial copilots in read/draft mode with evaluations
Exit gate
Gate: retention/efficiency impact is measured and AI quality/cost controls pass.

## V2 Platform
Become an extensible, intelligent and white-label platform.
Developer portal, public APIs, webhooks, sandbox and marketplace foundation
Advanced AI tools/agents with guarded execution
White-label app builder, CMS and scalable mobile release fleet
Biometric entry, liveness and device/edge fleet
Data products, benchmarking, advanced fraud and regional connectors
Facilities/equipment and connected-device integrations
Exit gate
Gate: partner contracts, hardware security, AI governance and white-label operations scale safely.

## Enterprise
Meet complex chain, corporate and procurement requirements.
SSO/SAML/OIDC, SCIM, access reviews and custom roles
Corporate portal, eligibility, aggregate reporting and billing
Franchise command center, standards, royalties and intercompany controls
Dedicated isolation/data residency options and enterprise SLA
Advanced audit, compliance evidence, legal/procurement and offboarding
Regional deployment and business-continuity options
Exit gate
Gate: enterprise security/procurement review and operational support model pass.

## Future Expansion
Extend into adjacent wellness, commerce and ecosystem models.
Service marketplace for coaching, nutrition, recovery and wellness
Partner marketplace economics and embedded billing
Connected equipment, smart lockers, body scanners and wearables at scale
Embedded finance, financing and insurance partnerships where appropriate
Privacy-preserving industry benchmarks and research data products
Exit gate
Gate: each expansion has a validated business model, risk assessment and strategic fit.

## Primary Dependency Chains
Value stream
Dependency chain
Member lifecycle
PLT-01 -> IAM-01/IAM-03 -> PPL-01 -> GRO-01 -> COM-02 -> COM-01 -> COM-03/COM-04 -> OPS-03
Booking and access
COM-01 -> OPS-01 -> OPS-02 -> OPS-03 -> ENG-02 -> DAT-01
Commerce
COM-02 -> COM-05 -> COM-03 -> COM-04 -> COM-06 -> INT-01
Coaching
PPL-01 -> COA-05 -> COA-04 -> COA-01 -> COA-02/COA-03 -> INT-01
Automation and AI
DAT-01 -> IAM-03 -> AUT-02 -> AUT-01 -> DAT-02 -> INT-02 -> INT-03
White-label scale
PLT-02 -> WHT-02 -> WHT-01 -> GOV-01 -> PLT-04
Open ecosystem
IAM-01/IAM-03 -> DAT-01 -> ECO-01 -> ECO-02 -> PLT-03
Hardware and biometrics
ECO-03 -> REL-01 -> SEC-01 -> OPS-03 -> IAM-02
Enterprise
PLT-01 -> IAM-03 -> DAT-02 -> B2B-01/B2B-02 -> GOV-03 -> LIF-03

## Release Prioritization Metadata
Field
Required values / use
Priority
Critical, High, Medium, Future.
Phase
Foundation, Pilot, V1, V1.5, V2, Enterprise, Future.
Dependency
Upstream domain, data, policy, integration, hardware or operational prerequisite.
Owner
Product, design, engineering, data, AI, security and operational DRI.
Risk
Customer, financial, safety, security, privacy, regulatory, migration and operational.
Evidence
Discovery evidence, prototype, technical spike, design partner result and measured outcome.


CHAPTER 12
# Metrics, Risks, Governance & Definition of Done
How the organization decides, measures and maintains quality.
## Outcome Metric Framework
Area
Metrics
Gym business growth
Lead response time, trial attendance, lead-to-member conversion, acquisition source ROI, new memberships and expansion sales.
Revenue and collections
Membership/PT/POS revenue, recurring collection rate, failed-payment recovery, ARPU, gross margin, wallet liability and cash variance.
Retention
Member churn, renewal, attendance decline recovery, cohort retention, NPS, complaint recovery and win-back.
Operations
Check-in success/latency, class utilization, waitlist fill, no-show, front-desk resolution, device uptime and incident closure.
Coaching outcomes
Program assignment time, workout adherence, session completion, client attention SLA, goal progress and coach retention.
Nutrition experience
Plan creation time, one-tap logging share, meal-swap success, weekly check-in completion, adherence and exception resolution.
Product UX
Task success, time on task, taps/actions, error recovery, search success, accessibility completion and support contact rate.
SaaS health
Activation, time-to-value, product-qualified usage, logo churn, gross/net revenue retention, expansion, support cost and tenant health.
Reliability
SLO attainment, error budget, incident frequency/duration, recovery, sync conflicts, webhook delivery and restore-test success.
Security and privacy
MFA/passkey adoption, vulnerability age, privileged-access review, consent completeness, DSAR SLA and security incidents.
AI
Grounded answer rate, task success, human acceptance, safety blocks, tool error, latency, cost and measurable business lift.

## Risk Register
Risk
Why it matters
Primary mitigation
Scope overload
The vision contains many products and enterprise layers.
Preserve master scope, enforce dependency-gated releases and outcome-based cut lines.
Weak domain boundaries
Membership, billing, access and orders can become tightly coupled.
Explicit aggregate ownership, contracts, events and architecture reviews.
Migration failure
Bad legacy data can damage trust on day one.
Productized dry run, reconciliation, sign-off, delta migration and rollback.
Financial inconsistency
Payments, invoices, wallet and refunds may diverge.
Immutable ledger, idempotency, settlement reconciliation and controlled corrections.
Hardware fragmentation
Access, biometric and POS vendors vary widely.
Capability-based abstraction, certification, edge runtime and exit plans.
Offline conflicts
Check-in and POS may continue during network loss.
Bounded offline scope, signed snapshots, idempotent commands and reconciliation UI.
Biometric privacy and spoofing
Face entry introduces sensitive data and attack surface.
Opt-in, alternatives, liveness, minimal retention, vendor-neutral templates and regional review.
AI unsafe or ungrounded output
Health, finance and operational actions can cause harm.
Permissioned retrieval, use-case evaluations, risk tiers, guarded tools and human approval.
AI and messaging cost
Usage may exceed plan economics.
Metering, budgets, routing, quotas, margin dashboards and packaging.
White-label release burden
Many apps can create certificate, review and support complexity.
Configuration-first apps, automated fleet pipeline, supported-version policy and store governance.
Localization as afterthought
RTL, tax, time and regional behavior can break critical workflows.
Arabic/English release gates and regional policy packs from foundation.
Data quality and metric disputes
Different teams may calculate the same KPI differently.
Semantic layer, metric ownership, lineage, quality indicators and governance.
Enterprise customization
Large clients may request forks and one-off behavior.
Configuration, policy packs, extension APIs and explicit product-fit review.
Support scaling
Complex product and integrations can drive high support cost.
Diagnostics, knowledge, safe support sessions, health scores and certification.
Vendor dependency
Payments, messaging, cloud and devices can fail or change terms.
Abstraction, multiple providers where justified, SLA monitoring and exit strategy.
Security breach or cross-tenant exposure
The highest trust-destroying platform risk.
Default deny, isolation tests, encryption, access reviews, monitoring, incident drills and dedicated tiers.
Regulatory variation
Biometric, tax, labor, privacy and invoicing rules vary by country.
Regional legal review, policy packs, configurable controls and phased market entry.
Product adoption
Broad capability can overwhelm small gyms and staff.
Role-specific experiences, progressive disclosure, templates, onboarding and task-based guidance.

## Governance Cadence
Forum
Scope
Output
Weekly domain review
Delivery, incidents, decisions, dependencies and metrics.
Owned actions and updated risks.
Monthly product council
Portfolio evidence, release scope, experiments and customer learning.
Prioritization and scope decisions.
Architecture/data/AI review
High-impact contracts, models, privacy, performance and platform changes.
Decision record, conditions and follow-up.
Quarterly business review
SaaS KPIs, unit economics, quality, risk, customer outcomes and roadmap.
Strategic adjustments and investment.
Post-incident review
Material reliability, security, AI, privacy or customer-impacting incident.
Root cause, corrective actions and verified closure.

## Definition of Done
☑ Problem, target user, expected outcome and non-goals are documented.
☑ Domain owner, source of truth, invariants, permissions and dependency contracts are approved.
☑ English LTR and Arabic RTL designs cover loading, empty, success, error, offline and permission-denied states.
☑ Accessibility checks and assistive-technology behavior pass.
☑ Security, privacy, consent, retention and threat-model review are complete for the risk tier.
☑ Domain events, analytics instrumentation, metrics and data-quality expectations are defined.
☑ Unit, integration, contract, end-to-end, localization, accessibility, performance and failure tests meet the plan.
☑ Observability, alerts, dashboards, runbook and support diagnostics are ready.
☑ Migration/backfill, backward compatibility, rollout, feature flag, rollback and deprecation are addressed.
☑ Help content, release communication, role training and customer-success readiness are complete.
☑ AI features pass use-case evaluation, safety, cost and human-approval criteria.
☑ Post-launch owner, review date, success metric and kill/iterate decision are assigned.

CHAPTER A
# Requirement Traceability Register
A complete capability inventory derived from the domain blueprint.
Each row is a mandatory requirement in the master product vision. Phase indicates delivery sequencing. Priority is derived from the phase and may be refined during planning without removing the requirement.
Requirement ID
Domain
Requirement
Priority
Phase
Surfaces
PLT-01-R01
Tenant, Organization, Brand & Location Management
Provision, activate, suspend, archive and delete tenants through a controlled lifecycle.
Critical
Foundation
Internal SaaS Console, Admin Web, APIs
PLT-01-R02
Tenant, Organization, Brand & Location Management
Model organization, legal entity, brand, region, location, department and cost-center hierarchies.
Critical
Foundation
Internal SaaS Console, Admin Web, APIs
PLT-01-R03
Tenant, Organization, Brand & Location Management
Enforce tenant-aware identifiers, storage paths, search indexes, events, caches, logs and background jobs.
Critical
Foundation
Internal SaaS Console, Admin Web, APIs
PLT-01-R04
Tenant, Organization, Brand & Location Management
Support tenant templates, cloning, defaults, regional settings and configuration inheritance.
Critical
Foundation
Internal SaaS Console, Admin Web, APIs
PLT-01-R05
Tenant, Organization, Brand & Location Management
Provide data residency, deployment-region and encryption-key assignment policies.
Critical
Foundation
Internal SaaS Console, Admin Web, APIs
PLT-01-R06
Tenant, Organization, Brand & Location Management
Allow multi-brand ownership with separate branding, catalogs, pricing, domains, applications and policies.
Critical
Foundation
Internal SaaS Console, Admin Web, APIs
PLT-01-R07
Tenant, Organization, Brand & Location Management
Maintain tenant lifecycle history and prevent hard deletion before legal, billing and retention gates pass.
Critical
Foundation
Internal SaaS Console, Admin Web, APIs
PLT-02-R01
Configuration, Feature Flags & Experimentation
Typed configuration registry with defaults, validation, ownership, versioning and inheritance.
Critical
Foundation
Internal SaaS Console, Admin Web, Mobile Apps
PLT-02-R02
Configuration, Feature Flags & Experimentation
Feature flags targeted by environment, tenant, plan, brand, location, user, role and percentage rollout.
Critical
Foundation
Internal SaaS Console, Admin Web, Mobile Apps
PLT-02-R03
Configuration, Feature Flags & Experimentation
Kill switches for risky integrations, AI actions, payments, hardware and communications.
Critical
Foundation
Internal SaaS Console, Admin Web, Mobile Apps
PLT-02-R04
Configuration, Feature Flags & Experimentation
Experiment assignment, exposure events, metrics, guardrails and statistical decision records.
Critical
Foundation
Internal SaaS Console, Admin Web, Mobile Apps
PLT-02-R05
Configuration, Feature Flags & Experimentation
Configuration preview, impact analysis, approval and rollback.
Critical
Foundation
Internal SaaS Console, Admin Web, Mobile Apps
PLT-02-R06
Configuration, Feature Flags & Experimentation
Remote configuration for mobile applications, kiosks and managed devices.
Critical
Foundation
Internal SaaS Console, Admin Web, Mobile Apps
PLT-03-R01
SaaS Plans, Subscription Billing, Metering & Entitlements
Plan catalog with editions, add-ons, trial policies, contract terms, currencies and regions.
Critical
Foundation
Internal SaaS Console, Tenant Billing Portal, Finance
PLT-03-R02
SaaS Plans, Subscription Billing, Metering & Entitlements
Monthly, annual and contractual subscriptions with upgrades, downgrades, proration and scheduled changes.
Critical
Foundation
Internal SaaS Console, Tenant Billing Portal, Finance
PLT-03-R03
SaaS Plans, Subscription Billing, Metering & Entitlements
Entitlements for locations, active members, staff, white-label apps, AI, storage, messages, API and integrations.
Critical
Foundation
Internal SaaS Console, Tenant Billing Portal, Finance
PLT-03-R04
SaaS Plans, Subscription Billing, Metering & Entitlements
Usage metering, aggregation, late-event handling, corrections, quotas, overages and fair-use rules.
Critical
Foundation
Internal SaaS Console, Tenant Billing Portal, Finance
PLT-03-R05
SaaS Plans, Subscription Billing, Metering & Entitlements
Trial conversion, dunning, grace periods, suspension, reactivation and offboarding coordination.
Critical
Foundation
Internal SaaS Console, Tenant Billing Portal, Finance
PLT-03-R06
SaaS Plans, Subscription Billing, Metering & Entitlements
SaaS invoices, tax, credit notes, payment methods, partner/reseller attribution and revenue share.
Critical
Foundation
Internal SaaS Console, Tenant Billing Portal, Finance
PLT-03-R07
SaaS Plans, Subscription Billing, Metering & Entitlements
Tenant cost and gross-margin view across cloud, AI, messaging, storage, support and third parties.
Critical
Foundation
Internal SaaS Console, Tenant Billing Portal, Finance
PLT-04-R01
Internal Administration, Support & Customer Success
Global tenant search and 360 view covering plan, usage, health, incidents, integrations, adoption and contacts.
Critical
Pilot
Internal SaaS Console
PLT-04-R02
Internal Administration, Support & Customer Success
Permission-safe support impersonation with reason, approval, time limit, visible banner and full audit.
Critical
Pilot
Internal SaaS Console
PLT-04-R03
Internal Administration, Support & Customer Success
Tenant diagnostics for jobs, webhooks, devices, payments, messaging, storage, mobile versions and configuration.
Critical
Pilot
Internal SaaS Console
PLT-04-R04
Internal Administration, Support & Customer Success
Customer health score using activation, adoption, support, usage, billing, sentiment and risk signals.
Critical
Pilot
Internal SaaS Console
PLT-04-R05
Internal Administration, Support & Customer Success
Implementation, success-plan, renewal, expansion, risk and executive-review workspaces.
Critical
Pilot
Internal SaaS Console
PLT-04-R06
Internal Administration, Support & Customer Success
Support tickets, SLAs, escalation, knowledge links, incident linkage and post-resolution feedback.
Critical
Pilot
Internal SaaS Console
PLT-04-R07
Internal Administration, Support & Customer Success
Bulk tenant communication, maintenance notices, release notes and deprecation notices.
Critical
Pilot
Internal SaaS Console
IAM-01-R01
Identity, Authentication, Passkeys & Device Sessions
Identity model that can link one person to multiple tenant roles without identity duplication.
Critical
Foundation
All Apps, Admin Web, Developer Portal
IAM-01-R02
Identity, Authentication, Passkeys & Device Sessions
Email/phone login, OTP, password, passkeys and platform biometric unlock through operating-system APIs.
Critical
Foundation
All Apps, Admin Web, Developer Portal
IAM-01-R03
Identity, Authentication, Passkeys & Device Sessions
MFA, step-up authentication, recovery codes, trusted devices and risk-based challenges.
Critical
Foundation
All Apps, Admin Web, Developer Portal
IAM-01-R04
Identity, Authentication, Passkeys & Device Sessions
Enterprise federation through OIDC/SAML and lifecycle provisioning through SCIM.
Critical
Foundation
All Apps, Admin Web, Developer Portal
IAM-01-R05
Identity, Authentication, Passkeys & Device Sessions
Session inventory, device binding, remote revocation, token rotation and suspicious-login detection.
Critical
Foundation
All Apps, Admin Web, Developer Portal
IAM-01-R06
Identity, Authentication, Passkeys & Device Sessions
Separate authentication assurance levels for routine, financial, privileged and biometric-sensitive actions.
Critical
Foundation
All Apps, Admin Web, Developer Portal
IAM-01-R07
Identity, Authentication, Passkeys & Device Sessions
Account linking, duplicate detection, merge review and identity recovery without losing tenant data.
Critical
Foundation
All Apps, Admin Web, Developer Portal
IAM-02-R01
Biometric Identity & Physical Access Methods
Member-controlled enrollment for facial entry with explicit informed consent and clear alternatives.
High
V2 Platform
Member App, Front Desk, Access Device, Admin Web
IAM-02-R02
Biometric Identity & Physical Access Methods
Vendor-neutral biometric templates, encrypted storage, retention policy, revocation and deletion workflow.
High
V2 Platform
Member App, Front Desk, Access Device, Admin Web
IAM-02-R03
Biometric Identity & Physical Access Methods
Liveness detection, match thresholds, anti-spoofing, retry limits and manual fallback.
High
V2 Platform
Member App, Front Desk, Access Device, Admin Web
IAM-02-R04
Biometric Identity & Physical Access Methods
QR, NFC, Apple Wallet, Google Wallet, physical card and temporary credential support.
High
V2 Platform
Member App, Front Desk, Access Device, Admin Web
IAM-02-R05
Biometric Identity & Physical Access Methods
Separate enrollment and policies for member access, staff attendance and high-security zones.
High
V2 Platform
Member App, Front Desk, Access Device, Admin Web
IAM-02-R06
Biometric Identity & Physical Access Methods
Identity Center showing methods, devices, consent, recent access and the ability to revoke.
High
V2 Platform
Member App, Front Desk, Access Device, Admin Web
IAM-02-R07
Biometric Identity & Physical Access Methods
Edge decision support for low-latency entry with secure synchronization and central policy validation.
High
V2 Platform
Member App, Front Desk, Access Device, Admin Web
IAM-03-R01
Authorization, Roles, Permissions, Approvals & Audit
Tenant-scoped RBAC with custom roles, permission bundles and location/brand scope.
Critical
Foundation
All Surfaces
IAM-03-R02
Authorization, Roles, Permissions, Approvals & Audit
Attribute- and relationship-based policies for assigned clients, sensitive notes, minors and health data.
Critical
Foundation
All Surfaces
IAM-03-R03
Authorization, Roles, Permissions, Approvals & Audit
Field-level masking for financial, biometric, health, identity and contact attributes.
Critical
Foundation
All Surfaces
IAM-03-R04
Authorization, Roles, Permissions, Approvals & Audit
Delegation, temporary access, break-glass access and separation-of-duties policies.
Critical
Foundation
All Surfaces
IAM-03-R05
Authorization, Roles, Permissions, Approvals & Audit
Approval policies by amount, risk, role, location and action type.
Critical
Foundation
All Surfaces
IAM-03-R06
Authorization, Roles, Permissions, Approvals & Audit
Immutable audit for authentication, data access, configuration, finance, access, AI and support.
Critical
Foundation
All Surfaces
IAM-03-R07
Authorization, Roles, Permissions, Approvals & Audit
Permission simulator and access review/certification for enterprise administrators.
Critical
Foundation
All Surfaces
PPL-01-R01
People, Profiles & Member 360
Canonical person record with tenant-specific profiles and role relationships.
Critical
Foundation
Admin Web, Coach App, Member App, Front Desk
PPL-01-R02
People, Profiles & Member 360
Member 360 covering lifecycle, membership, entitlements, attendance, bookings, coaching, nutrition, progress, finance, messages, consent and support.
Critical
Foundation
Admin Web, Coach App, Member App, Front Desk
PPL-01-R03
People, Profiles & Member 360
Unified chronological timeline built from domain events with permission-aware visibility.
Critical
Foundation
Admin Web, Coach App, Member App, Front Desk
PPL-01-R04
People, Profiles & Member 360
Duplicate detection and merge workflow using identity, contact and contextual signals.
Critical
Foundation
Admin Web, Coach App, Member App, Front Desk
PPL-01-R05
People, Profiles & Member 360
Tags, segments, custom fields and data-quality indicators governed by schema and permissions.
Critical
Foundation
Admin Web, Coach App, Member App, Front Desk
PPL-01-R06
People, Profiles & Member 360
Relationship graph for coach-client, guardian-dependent, company-employee, referrer-referred and household.
Critical
Foundation
Admin Web, Coach App, Member App, Front Desk
PPL-01-R07
People, Profiles & Member 360
Privacy controls for preferred name, contact channels, sensitive notes, progress media and minors.
Critical
Foundation
Admin Web, Coach App, Member App, Front Desk
PPL-02-R01
Households, Dependents, Guests & Eligibility
Household account with shared payment methods, wallet rules, family plan and consolidated statements.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Corporate Portal
PPL-02-R02
Households, Dependents, Guests & Eligibility
Guardian permissions, consent, pickup rules and booking controls for minors and dependents.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Corporate Portal
PPL-02-R03
Households, Dependents, Guests & Eligibility
Corporate eligibility verification by roster, code, domain, API or identity provider.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Corporate Portal
PPL-02-R04
Households, Dependents, Guests & Eligibility
Guest, trial and day-pass profiles with sponsor, access window, waiver, lead conversion and abuse limits.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Corporate Portal
PPL-02-R05
Households, Dependents, Guests & Eligibility
Relationship-specific communication, privacy and financial permissions.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Corporate Portal
PPL-02-R06
Households, Dependents, Guests & Eligibility
Dependent aging and eligibility-change workflows without losing history.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Corporate Portal
GRO-01-R01
CRM, Leads, Sales Pipeline & Trials
Lead capture from forms, ads, referrals, walk-ins, imports, APIs, partners and corporate lists.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-01-R02
CRM, Leads, Sales Pipeline & Trials
Configurable pipelines and stages with required fields, probability, ownership and service-level timers.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-01-R03
CRM, Leads, Sales Pipeline & Trials
Lead scoring using source, intent, engagement, demographics, response and historical conversion.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-01-R04
CRM, Leads, Sales Pipeline & Trials
Unified calls, WhatsApp, SMS, email, notes, tasks and appointment history.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-01-R05
CRM, Leads, Sales Pipeline & Trials
Trial, tour and assessment booking with reminders, attendance and conversion follow-up.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-01-R06
CRM, Leads, Sales Pipeline & Trials
Offers, quotes, proposal expiry, objection/loss reason and membership conversion.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-01-R07
CRM, Leads, Sales Pipeline & Trials
Duplicate prevention and lead-to-member merge preserving attribution and history.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-01-R08
CRM, Leads, Sales Pipeline & Trials
Sales dashboards for response time, stage aging, conversion, source ROI and representative performance.
Critical
V1 General Availability
Admin Web, Front Desk, Mobile Staff
GRO-02-R01
Marketing, Referrals, Offers & Growth Journeys
Audience builder using lifecycle, membership, attendance, spending, coaching, engagement, location and risk.
High
V1.5 Growth
Admin Web, Member App, Communication Channels
GRO-02-R02
Marketing, Referrals, Offers & Growth Journeys
Campaign orchestration across email, push, SMS, WhatsApp and in-app placements.
High
V1.5 Growth
Admin Web, Member App, Communication Channels
GRO-02-R03
Marketing, Referrals, Offers & Growth Journeys
Referral links, codes and QR with sponsor tracking, fraud checks, qualification and rewards.
High
V1.5 Growth
Admin Web, Member App, Communication Channels
GRO-02-R04
Marketing, Referrals, Offers & Growth Journeys
Lifecycle journeys for onboarding, first visit, inactivity, expiration, birthday, milestone and win-back.
High
V1.5 Growth
Admin Web, Member App, Communication Channels
GRO-02-R05
Marketing, Referrals, Offers & Growth Journeys
Offer eligibility, frequency caps, suppression, holdout groups and attribution windows.
High
V1.5 Growth
Admin Web, Member App, Communication Channels
GRO-02-R06
Marketing, Referrals, Offers & Growth Journeys
Landing pages and lead forms governed by brand and localization settings.
High
V1.5 Growth
Admin Web, Member App, Communication Channels
GRO-02-R07
Marketing, Referrals, Offers & Growth Journeys
Incrementality and conversion reporting instead of message-open metrics alone.
High
V1.5 Growth
Admin Web, Member App, Communication Channels
COM-01-R01
Memberships, Contracts, Entitlements & Lifecycle
Fixed-term, recurring, installment, prepaid, off-peak, family, student, corporate, class-credit and unlimited memberships.
Critical
V1 General Availability
Admin Web, Member App, Front Desk, Access Control
COM-01-R02
Memberships, Contracts, Entitlements & Lifecycle
Contract version, signature, start/end, minimum term, notice, renewal and cancellation policy.
Critical
V1 General Availability
Admin Web, Member App, Front Desk, Access Control
COM-01-R03
Memberships, Contracts, Entitlements & Lifecycle
Entitlements for locations, schedules, zones, classes, facilities, services, guest passes, discounts and digital content.
Critical
V1 General Availability
Admin Web, Member App, Front Desk, Access Control
COM-01-R04
Memberships, Contracts, Entitlements & Lifecycle
Freeze, pause, medical hold, upgrade, downgrade, transfer, renewal, cancellation and reinstatement with effective dating.
Critical
V1 General Availability
Admin Web, Member App, Front Desk, Access Control
COM-01-R05
Memberships, Contracts, Entitlements & Lifecycle
Proration, credit carryover, expiry extension, grace period and access consequences.
Critical
V1 General Availability
Admin Web, Member App, Front Desk, Access Control
COM-01-R06
Memberships, Contracts, Entitlements & Lifecycle
Member self-service request policies with eligibility checks, fee disclosure and approval where required.
Critical
V1 General Availability
Admin Web, Member App, Front Desk, Access Control
COM-01-R07
Memberships, Contracts, Entitlements & Lifecycle
Full state history and “as-of” reconstruction for disputes and audits.
Critical
V1 General Availability
Admin Web, Member App, Front Desk, Access Control
COM-02-R01
Catalog, Pricing, Promotions & Packages
Product types for membership, service, session credit, class credit, retail SKU, subscription add-on, event and gift card.
Critical
V1 General Availability
Admin Web, POS, Member App, CRM
COM-02-R02
Catalog, Pricing, Promotions & Packages
Price books by brand, location, channel, currency, tax regime, customer segment and effective date.
Critical
V1 General Availability
Admin Web, POS, Member App, CRM
COM-02-R03
Catalog, Pricing, Promotions & Packages
Bundles linking commercial sale to operational fulfillment and entitlements.
Critical
V1 General Availability
Admin Web, POS, Member App, CRM
COM-02-R04
Catalog, Pricing, Promotions & Packages
Coupons, automatic promotions, corporate rates, member tiers, staff discounts and manual discount policy.
Critical
V1 General Availability
Admin Web, POS, Member App, CRM
COM-02-R05
Catalog, Pricing, Promotions & Packages
Eligibility, stacking, usage limits, minimum spend, blackout dates and approval thresholds.
Critical
V1 General Availability
Admin Web, POS, Member App, CRM
COM-02-R06
Catalog, Pricing, Promotions & Packages
Localized names, media, descriptions, terms, availability and merchandising order.
Critical
V1 General Availability
Admin Web, POS, Member App, CRM
COM-02-R07
Catalog, Pricing, Promotions & Packages
Versioned price changes that do not rewrite historical transactions.
Critical
V1 General Availability
Admin Web, POS, Member App, CRM
COM-03-R01
Member Billing, Payments, Tax & Revenue Recovery
Billing schedules, recurring invoices, installments, deposits, due dates and consolidated household/corporate billing.
Critical
V1 General Availability
Admin Web, Member App, POS, Finance
COM-03-R02
Member Billing, Payments, Tax & Revenue Recovery
Payment orchestration for cards, direct debit, bank transfer, cash, wallet, gift card and local gateways.
Critical
V1 General Availability
Admin Web, Member App, POS, Finance
COM-03-R03
Member Billing, Payments, Tax & Revenue Recovery
Tokenized stored payment methods, 3DS/SCA handling, retries and payment-method updates.
Critical
V1 General Availability
Admin Web, Member App, POS, Finance
COM-03-R04
Member Billing, Payments, Tax & Revenue Recovery
Dunning journeys with retry schedule, grace period, member communication, task escalation and access policy.
Critical
V1 General Availability
Admin Web, Member App, POS, Finance
COM-03-R05
Member Billing, Payments, Tax & Revenue Recovery
Invoices, receipts, tax calculation, credit notes, refunds, disputes and chargebacks.
Critical
V1 General Availability
Admin Web, Member App, POS, Finance
COM-03-R06
Member Billing, Payments, Tax & Revenue Recovery
Provider abstraction, idempotent commands, webhook verification and payment-status reconciliation.
Critical
V1 General Availability
Admin Web, Member App, POS, Finance
COM-03-R07
Member Billing, Payments, Tax & Revenue Recovery
Regional taxation, invoice numbering, fiscalization hooks and accounting export.
Critical
V1 General Availability
Admin Web, Member App, POS, Finance
COM-04-R01
Financial Ledger, Wallet, Credits & Reconciliation
Double-entry or equivalent immutable posting model for sales, payments, refunds, fees, wallet and credits.
Critical
V1 General Availability
Finance, POS, Member App, Admin Web
COM-04-R02
Financial Ledger, Wallet, Credits & Reconciliation
Member wallet with cash value, promotional value, referral credit, refund credit and expiry policy.
Critical
V1 General Availability
Finance, POS, Member App, Admin Web
COM-04-R03
Financial Ledger, Wallet, Credits & Reconciliation
Separate non-monetary service credits such as PT sessions, classes, guest passes and assessments.
Critical
V1 General Availability
Finance, POS, Member App, Admin Web
COM-04-R04
Financial Ledger, Wallet, Credits & Reconciliation
Provider settlement import and automated matching to payments, fees, refunds and chargebacks.
Critical
V1 General Availability
Finance, POS, Member App, Admin Web
COM-04-R05
Financial Ledger, Wallet, Credits & Reconciliation
Cash drawer, bank deposit and payout reconciliation with discrepancy workflows.
Critical
V1 General Availability
Finance, POS, Member App, Admin Web
COM-04-R06
Financial Ledger, Wallet, Credits & Reconciliation
Financial periods, lock controls, correction entries and export to accounting systems.
Critical
V1 General Availability
Finance, POS, Member App, Admin Web
COM-04-R07
Financial Ledger, Wallet, Credits & Reconciliation
Statements and balances reconstructed from entries rather than mutable totals.
Critical
V1 General Availability
Finance, POS, Member App, Admin Web
COM-05-R01
Point of Sale, Ecommerce & Order Fulfillment
Fast member-aware checkout: identify member, tap/scan product, pay and complete.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R02
Point of Sale, Ecommerce & Order Fulfillment
Guest checkout with optional lead/member conversion and receipt capture.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R03
Point of Sale, Ecommerce & Order Fulfillment
Barcode scanning, favorites, category tiles, search, recent items and configurable quick actions.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R04
Point of Sale, Ecommerce & Order Fulfillment
Cash, card, wallet, saved method, gift card and split-tender payments.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R05
Point of Sale, Ecommerce & Order Fulfillment
Sell memberships, upgrades, PT packages, classes, nutrition, events, merchandise and digital products from one cart.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R06
Point of Sale, Ecommerce & Order Fulfillment
Automatic member pricing, included-benefit detection, tax, discount policy and approval.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R07
Point of Sale, Ecommerce & Order Fulfillment
Returns, partial refunds, exchanges, store credit, voids and reason codes.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R08
Point of Sale, Ecommerce & Order Fulfillment
Orders from member app/web shop with pickup, digital fulfillment or future delivery.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-05-R09
Point of Sale, Ecommerce & Order Fulfillment
Cash shift opening, paid-in/out, drawer count, expected/actual difference and manager close.
Critical
V1 General Availability
Front Desk, Member App, Coach App, Admin Web
COM-06-R01
Inventory, Purchasing, Suppliers & Stock Control
SKU, barcode, variant, unit, lot, expiry, supplier, cost, selling price and tax category.
High
V1.5 Growth
Admin Web, POS, Warehouse Mobile
COM-06-R02
Inventory, Purchasing, Suppliers & Stock Control
On-hand, available, reserved, in-transit, damaged and quarantined quantities by location.
High
V1.5 Growth
Admin Web, POS, Warehouse Mobile
COM-06-R03
Inventory, Purchasing, Suppliers & Stock Control
Purchase requisition, approval, purchase order, receiving, variance and supplier invoice matching.
High
V1.5 Growth
Admin Web, POS, Warehouse Mobile
COM-06-R04
Inventory, Purchasing, Suppliers & Stock Control
Inter-location transfer, cycle count, stock adjustment, wastage and reason-coded shrinkage.
High
V1.5 Growth
Admin Web, POS, Warehouse Mobile
COM-06-R05
Inventory, Purchasing, Suppliers & Stock Control
Reorder points, suggested purchasing, sales velocity and expiry-risk alerts.
High
V1.5 Growth
Admin Web, POS, Warehouse Mobile
COM-06-R06
Inventory, Purchasing, Suppliers & Stock Control
Cost history, margin, landed cost and valuation export.
High
V1.5 Growth
Admin Web, POS, Warehouse Mobile
COM-06-R07
Inventory, Purchasing, Suppliers & Stock Control
Inventory reservations linked to orders and fulfillment.
High
V1.5 Growth
Admin Web, POS, Warehouse Mobile
OPS-01-R01
Scheduling, Resources & Capacity
Resource model for staff, room, zone, court, equipment, service and composite requirements.
Critical
V1 General Availability
Admin Web, Coach App, Member App
OPS-01-R02
Scheduling, Resources & Capacity
One-time and recurring schedules with templates, exceptions, seasonality and time-zone correctness.
Critical
V1 General Availability
Admin Web, Coach App, Member App
OPS-01-R03
Scheduling, Resources & Capacity
Availability, working hours, breaks, time off, substitutions and cross-location travel buffers.
Critical
V1 General Availability
Admin Web, Coach App, Member App
OPS-01-R04
Scheduling, Resources & Capacity
Capacity, setup/cleanup time, age/skill restrictions, equipment requirements and entitlement checks.
Critical
V1 General Availability
Admin Web, Coach App, Member App
OPS-01-R05
Scheduling, Resources & Capacity
Conflict detection and resolution for people, space, equipment and policies.
Critical
V1 General Availability
Admin Web, Coach App, Member App
OPS-01-R06
Scheduling, Resources & Capacity
Schedule publishing, draft changes, member impact preview and notification plan.
Critical
V1 General Availability
Admin Web, Coach App, Member App
OPS-01-R07
Scheduling, Resources & Capacity
Instructor substitution, cancellation, relocation and attendance handoff.
Critical
V1 General Availability
Admin Web, Coach App, Member App
OPS-02-R01
Booking, Waitlist & No-show Intelligence
Book, reschedule, cancel and recurring booking across eligible services and resources.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Coach App
OPS-02-R02
Booking, Waitlist & No-show Intelligence
Booking windows, cancellation windows, lead time, capacity, quotas, priority and membership eligibility.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Coach App
OPS-02-R03
Booking, Waitlist & No-show Intelligence
Waitlist position, automatic promotion, timed confirmation, fallback and member preferences.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Coach App
OPS-02-R04
Booking, Waitlist & No-show Intelligence
No-show and late-cancel policy with fee, credit loss, warning, strike and appeal.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Coach App
OPS-02-R05
Booking, Waitlist & No-show Intelligence
Predictive no-show score used for reminders and controlled overbooking, never opaque denial.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Coach App
OPS-02-R06
Booking, Waitlist & No-show Intelligence
Calendar synchronization, reminders, check-in linkage and attendance completion.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Coach App
OPS-02-R07
Booking, Waitlist & No-show Intelligence
Group, household, guest and corporate booking with permission and eligibility rules.
Critical
V1 General Availability
Member App, Admin Web, Front Desk, Coach App
OPS-03-R01
Check-in, Access Control & Entitlement Decisions
Real-time decision pipeline: identify person, resolve credential, evaluate entitlement and policy, then actuate device.
Critical
V1 General Availability
Access Device, Front Desk, Admin Web, Member App
OPS-03-R02
Check-in, Access Control & Entitlement Decisions
QR, NFC, wallet pass, card, PIN, staff-assisted and optional biometric credentials.
Critical
V1 General Availability
Access Device, Front Desk, Admin Web, Member App
OPS-03-R03
Check-in, Access Control & Entitlement Decisions
Rules for location, zone, hours, membership state, capacity, outstanding balance, freeze, age and safety flags.
Critical
V1 General Availability
Access Device, Front Desk, Admin Web, Member App
OPS-03-R04
Check-in, Access Control & Entitlement Decisions
Configurable grace and exception policies with staff override, reason and approval.
Critical
V1 General Availability
Access Device, Front Desk, Admin Web, Member App
OPS-03-R05
Check-in, Access Control & Entitlement Decisions
Offline entitlement cache, signed policy snapshots, duplicate-entry protection and eventual synchronization.
Critical
V1 General Availability
Access Device, Front Desk, Admin Web, Member App
OPS-03-R06
Check-in, Access Control & Entitlement Decisions
Live occupancy, entry/exit events, anti-passback and emergency unlock integration.
Critical
V1 General Availability
Access Device, Front Desk, Admin Web, Member App
OPS-03-R07
Check-in, Access Control & Entitlement Decisions
Privacy-safe welcome/failure display and immediate fallback path.
Critical
V1 General Availability
Access Device, Front Desk, Admin Web, Member App
OPS-04-R01
Front Desk, Kiosk, Guest & Visitor Operations
Live arrivals with identity, membership/access status, alerts and next best action.
Critical
V1 General Availability
Front Desk, Kiosk, Admin Web
OPS-04-R02
Front Desk, Kiosk, Guest & Visitor Operations
Fast global member search by name, phone, ID, QR, card or recent visit.
Critical
V1 General Availability
Front Desk, Kiosk, Admin Web
OPS-04-R03
Front Desk, Kiosk, Guest & Visitor Operations
Resolve expired/frozen membership, failed payment, booking, waiver, guest or credential issue in context.
Critical
V1 General Availability
Front Desk, Kiosk, Admin Web
OPS-04-R04
Front Desk, Kiosk, Guest & Visitor Operations
Walk-in, trial, day pass and guest registration with waiver, identity, payment and lead creation.
Critical
V1 General Availability
Front Desk, Kiosk, Admin Web
OPS-04-R05
Front Desk, Kiosk, Guest & Visitor Operations
Reception mode combining check-in, bookings, POS, member actions and operational alerts.
Critical
V1 General Availability
Front Desk, Kiosk, Admin Web
OPS-04-R06
Front Desk, Kiosk, Guest & Visitor Operations
Kiosk mode for unattended check-in, renewal, day pass, waiver and guest registration.
Critical
V1 General Availability
Front Desk, Kiosk, Admin Web
OPS-04-R07
Front Desk, Kiosk, Guest & Visitor Operations
Queue and handoff support for escalations to sales, manager, coach or finance.
Critical
V1 General Availability
Front Desk, Kiosk, Admin Web
OPS-05-R01
Staff, Shifts, Attendance, Payroll & Commissions
Staff profile, employment/contract relationship, location assignment, qualifications and document expiry.
High
V1.5 Growth
Admin Web, Coach App, Staff Kiosk
OPS-05-R02
Staff, Shifts, Attendance, Payroll & Commissions
Shift planning, availability, clock-in/out, break, overtime, leave and substitution.
High
V1.5 Growth
Admin Web, Coach App, Staff Kiosk
OPS-05-R03
Staff, Shifts, Attendance, Payroll & Commissions
Optional biometric attendance separated from member-access enrollment and policy.
High
V1.5 Growth
Admin Web, Coach App, Staff Kiosk
OPS-05-R04
Staff, Shifts, Attendance, Payroll & Commissions
Coach session completion, class delivery, sales, lead handling, tasks, NPS and retention metrics.
High
V1.5 Growth
Admin Web, Coach App, Staff Kiosk
OPS-05-R05
Staff, Shifts, Attendance, Payroll & Commissions
Compensation rules for base, hourly, per-session, class, tiered commission, bonus and deduction.
High
V1.5 Growth
Admin Web, Coach App, Staff Kiosk
OPS-05-R06
Staff, Shifts, Attendance, Payroll & Commissions
Payroll preview, exception review, approval, lock and export to payroll/accounting.
High
V1.5 Growth
Admin Web, Coach App, Staff Kiosk
OPS-05-R07
Staff, Shifts, Attendance, Payroll & Commissions
Separation between performance coaching and protected HR information.
High
V1.5 Growth
Admin Web, Coach App, Staff Kiosk
OPS-06-R01
Facilities, Equipment, Assets & Maintenance
Asset register for equipment, rooms, zones, lockers, access devices, kiosks and POS hardware.
High
V2 Platform
Admin Web, Member App, Staff Mobile, Partner Portal
OPS-06-R02
Facilities, Equipment, Assets & Maintenance
QR/NFC asset labels for member/staff issue reporting and technician context.
High
V2 Platform
Admin Web, Member App, Staff Mobile, Partner Portal
OPS-06-R03
Facilities, Equipment, Assets & Maintenance
Preventive maintenance schedules, inspection checklists, warranties, service contracts and compliance dates.
High
V2 Platform
Admin Web, Member App, Staff Mobile, Partner Portal
OPS-06-R04
Facilities, Equipment, Assets & Maintenance
Issue triage, severity, safety isolation, work order, parts, downtime and resolution evidence.
High
V2 Platform
Admin Web, Member App, Staff Mobile, Partner Portal
OPS-06-R05
Facilities, Equipment, Assets & Maintenance
Facility closure or capacity impact synchronized to booking, access and communication.
High
V2 Platform
Admin Web, Member App, Staff Mobile, Partner Portal
OPS-06-R06
Facilities, Equipment, Assets & Maintenance
Asset utilization, downtime, maintenance cost and replacement forecasting.
High
V2 Platform
Admin Web, Member App, Staff Mobile, Partner Portal
OPS-06-R07
Facilities, Equipment, Assets & Maintenance
Supplier/technician portal or limited-access workflow for assigned work.
High
V2 Platform
Admin Web, Member App, Staff Mobile, Partner Portal
COA-01-R01
Coach Workspace & Client Management
Today view with upcoming sessions, preparation context, tasks, changes and clients needing attention.
Critical
V1 General Availability
Coach App, Admin Web
COA-01-R02
Coach Workspace & Client Management
Assigned client roster, search, lifecycle status, goals, restrictions, program and recent activity.
Critical
V1 General Availability
Coach App, Admin Web
COA-01-R03
Coach Workspace & Client Management
Client 360 subset scoped to coaching relationship and sensitive-data permissions.
Critical
V1 General Availability
Coach App, Admin Web
COA-01-R04
Coach Workspace & Client Management
Session preparation, attendance, notes, exercises, measurements, follow-up and credit consumption.
Critical
V1 General Availability
Coach App, Admin Web
COA-01-R05
Coach Workspace & Client Management
Coach tasks generated from plan end, inactivity, pain report, missed targets, check-in or member request.
Critical
V1 General Availability
Coach App, Admin Web
COA-01-R06
Coach Workspace & Client Management
Contextual messaging tied to client, workout, meal, assessment or session.
Critical
V1 General Availability
Coach App, Admin Web
COA-01-R07
Coach Workspace & Client Management
Mobile sales of approved coaching products or secure payment-request handoff to the member.
Critical
V1 General Availability
Coach App, Admin Web
COA-01-R08
Coach Workspace & Client Management
Offline read access to today schedule and safe queued notes where policy allows.
Critical
V1 General Availability
Coach App, Admin Web
COA-02-R01
Training Programs, Workouts & Exercise Logging
Exercise library with movement pattern, equipment, muscle, level, media, coaching cues and contraindications.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-02-R02
Training Programs, Workouts & Exercise Logging
Program templates, blocks, mesocycles, weeks, sessions, supersets, circuits and conditional alternatives.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-02-R03
Training Programs, Workouts & Exercise Logging
Prescription for sets, reps, load, duration, distance, tempo, rest, RPE/RIR and target zones.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-02-R04
Training Programs, Workouts & Exercise Logging
Member-specific substitutions based on equipment, time, limitation, preference and location.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-02-R05
Training Programs, Workouts & Exercise Logging
Fast member logging with previous result, smart defaults, timers, wearable input and minimal taps.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-02-R06
Training Programs, Workouts & Exercise Logging
Coach review, comments, technique media, PR detection, progression and adherence.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-02-R07
Training Programs, Workouts & Exercise Logging
Program versioning, assignment dates, completion history and safe plan transitions.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-02-R08
Training Programs, Workouts & Exercise Logging
AI-assisted generation and adaptation with explicit constraints, evidence and coach approval.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-03-R01
Nutrition Planning, Meals, Logging & Adherence
Three plan modes: flexible targets, structured meals and hybrid plan with coach-configurable tracking level.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R02
Nutrition Planning, Meals, Logging & Adherence
Auto-load member age, measurements, goals, activity, training schedule and approved health context; request only missing data.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R03
Nutrition Planning, Meals, Logging & Adherence
Preferences for allergies, dietary pattern, halal, dislikes, cuisine, budget, cooking time, meal count and schedule.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R04
Nutrition Planning, Meals, Logging & Adherence
AI/template/scratch plan creation with calorie/macro targets, confidence, rationale and coach review.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R05
Nutrition Planning, Meals, Logging & Adherence
Meal builder with recipe search, favorites, recent items, local/MENA foods, portions, daily target feedback and one-click target repair.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R06
Nutrition Planning, Meals, Logging & Adherence
Generate or duplicate days, rotate meals, create meal slots and maintain alternatives within calorie/protein tolerance.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R07
Nutrition Planning, Meals, Logging & Adherence
Preview exactly as member, set start/duration/check-in, meal-swap permissions and exception thresholds, then assign.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R08
Nutrition Planning, Meals, Logging & Adherence
Member today view answering “what should I eat now?” with one-tap Eat & Log.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R09
Nutrition Planning, Meals, Logging & Adherence
Smart swap, portion change, skip, log-something-else, barcode, favorites, recent and photo-based estimate with uncertainty.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R10
Nutrition Planning, Meals, Logging & Adherence
Automatic grocery list, restaurant alternatives, contextual coach question and weekly check-in.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R11
Nutrition Planning, Meals, Logging & Adherence
Coach exception inbox for low adherence, repeated missed protein, weight stall, swap request, hunger or energy issue.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-03-R12
Nutrition Planning, Meals, Logging & Adherence
Food/recipe library governance, locale-specific serving units, nutrition-source provenance and edit history.
High
V1.5 Growth
Coach App, Member App, Admin Web
COA-04-R01
Assessments, Measurements, Progress & Outcomes
Configurable assessment templates for goals, movement, fitness, strength, endurance, habits and wellbeing.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-04-R02
Assessments, Measurements, Progress & Outcomes
Measurements for weight, circumference, body composition, performance, mobility and custom metrics with unit normalization.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-04-R03
Assessments, Measurements, Progress & Outcomes
Progress photos and media with consent, privacy, comparison controls and retention.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-04-R04
Assessments, Measurements, Progress & Outcomes
Goals with baseline, target, deadline, milestones, status and coach/member ownership.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-04-R05
Assessments, Measurements, Progress & Outcomes
Device/body-scanner imports with source, calibration and confidence metadata.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-04-R06
Assessments, Measurements, Progress & Outcomes
Member-friendly progress narrative alongside charts, consistency, attendance and program adherence.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-04-R07
Assessments, Measurements, Progress & Outcomes
Stall, anomaly and safety alerts that route to qualified review rather than autonomous change.
Critical
V1 General Availability
Coach App, Member App, Admin Web
COA-05-R01
Health, Safety, Consent & Incident Management
PAR-Q-style screening, health questionnaire, waiver, informed consent and versioned signatures.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
COA-05-R02
Health, Safety, Consent & Incident Management
Injury, limitation, allergy, contraindication and emergency contact with fine-grained visibility.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
COA-05-R03
Health, Safety, Consent & Incident Management
Member-declared pain or symptom flow that pauses unsafe activity and routes to coach/qualified review.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
COA-05-R04
Health, Safety, Consent & Incident Management
Incident reporting for injury, equipment, safeguarding, harassment, security, medical or operational event.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
COA-05-R05
Health, Safety, Consent & Incident Management
Triage, immediate action, witnesses, evidence, notification, escalation, corrective action and closure.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
COA-05-R06
Health, Safety, Consent & Incident Management
Emergency mode with minimal necessary member context and controlled break-glass access.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
COA-05-R07
Health, Safety, Consent & Incident Management
Safety rules integrated into workout, nutrition, booking, access, facility and communication decisions.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
COA-05-R08
Health, Safety, Consent & Incident Management
Policy versioning, jurisdiction mapping, retention and legal hold.
Critical
V1 General Availability
Member App, Coach App, Admin Web, Front Desk
ENG-01-R01
Unified Inbox, Messaging & Contextual Communication
Unified conversation timeline for in-app chat, WhatsApp, SMS, email, call notes and staff notes.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-01-R02
Unified Inbox, Messaging & Contextual Communication
Threads anchored to member, lead, booking, workout, meal, invoice, incident or support case.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-01-R03
Unified Inbox, Messaging & Contextual Communication
Shared team inbox with routing, assignment, status, collision prevention, SLA and handoff.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-01-R04
Unified Inbox, Messaging & Contextual Communication
Channel templates, approved WhatsApp templates, localized variables and preview.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-01-R05
Unified Inbox, Messaging & Contextual Communication
Member-to-coach messaging with availability, response expectations, media and moderation controls.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-01-R06
Unified Inbox, Messaging & Contextual Communication
Consent, opt-out, quiet hours, communication preferences and legal retention by channel.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-01-R07
Unified Inbox, Messaging & Contextual Communication
Delivery, read, failure, reply and escalation status with provider reconciliation.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-01-R08
Unified Inbox, Messaging & Contextual Communication
AI-assisted drafts and summaries that never send without authorized policy.
Critical
V1 General Availability
Admin Web, Coach App, Member App, Front Desk
ENG-02-R01
Notification Platform, Templates & Preferences
Event-triggered email, push, SMS, WhatsApp and in-app notifications through one orchestration API.
Critical
Foundation
All Apps, Internal SaaS Console
ENG-02-R02
Notification Platform, Templates & Preferences
Template versioning, localization, brand styling, variables, preview and approval.
Critical
Foundation
All Apps, Internal SaaS Console
ENG-02-R03
Notification Platform, Templates & Preferences
Transactional, operational, coaching and marketing categories with different consent rules.
Critical
Foundation
All Apps, Internal SaaS Console
ENG-02-R04
Notification Platform, Templates & Preferences
User preferences, quiet hours, frequency caps, digesting, priority and channel fallback.
Critical
Foundation
All Apps, Internal SaaS Console
ENG-02-R05
Notification Platform, Templates & Preferences
Scheduling, deduplication, idempotency, retry, provider failover and dead-letter handling.
Critical
Foundation
All Apps, Internal SaaS Console
ENG-02-R06
Notification Platform, Templates & Preferences
Delivery analytics, complaint/bounce suppression and cost by tenant/channel.
Critical
Foundation
All Apps, Internal SaaS Console
ENG-02-R07
Notification Platform, Templates & Preferences
Critical alerts that bypass selected preferences only under documented policy.
Critical
Foundation
All Apps, Internal SaaS Console
ENG-03-R01
Community, Challenges, Achievements & Rewards
Challenges based on attendance, workout completion, distance, consistency, team goals or custom verified events.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-03-R02
Community, Challenges, Achievements & Rewards
Private, club, location, corporate and invitation-only participation scopes.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-03-R03
Community, Challenges, Achievements & Rewards
Leaderboards with privacy aliases, fair ranking, eligibility and anti-cheat review.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-03-R04
Community, Challenges, Achievements & Rewards
Achievements, streaks and milestones based on trusted event sources.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-03-R05
Community, Challenges, Achievements & Rewards
Reward rules for attendance, consistency, referrals, renewals, purchases, challenges and coaching milestones.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-03-R06
Community, Challenges, Achievements & Rewards
Reward catalog supporting points, wallet credit, guest pass, product, class or privilege.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-03-R07
Community, Challenges, Achievements & Rewards
Lightweight posts, announcements, reactions and comments with reporting, blocking and moderation.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-03-R08
Community, Challenges, Achievements & Rewards
Fraud, duplicate-event and incentive-abuse controls before reward settlement.
High
V1.5 Growth
Member App, Admin Web, Corporate Portal
ENG-04-R01
Member Self-Service, Digital Card & Service Requests
Digital membership card, QR/NFC credential and wallet pass with live status.
Critical
V1 General Availability
Member App, Member Web
ENG-04-R02
Member Self-Service, Digital Card & Service Requests
Renew, upgrade, downgrade, freeze, resume, cancel or request transfer with transparent effects and fees.
Critical
V1 General Availability
Member App, Member Web
ENG-04-R03
Member Self-Service, Digital Card & Service Requests
Manage payment methods, settle balances, view invoices/receipts/statements and download documents.
Critical
V1 General Availability
Member App, Member Web
ENG-04-R04
Member Self-Service, Digital Card & Service Requests
Buy packages, services, products, guest passes and gift cards.
Critical
V1 General Availability
Member App, Member Web
ENG-04-R05
Member Self-Service, Digital Card & Service Requests
Manage bookings, waitlist, household, dependents, consents, preferences, devices and access methods.
Critical
V1 General Availability
Member App, Member Web
ENG-04-R06
Member Self-Service, Digital Card & Service Requests
Service-request center with status, SLA, required documents, communication and resolution.
Critical
V1 General Availability
Member App, Member Web
ENG-04-R07
Member Self-Service, Digital Card & Service Requests
Export personal data, correct profile information and request account/data deletion where applicable.
Critical
V1 General Availability
Member App, Member Web
AUT-01-R01
Automation & Workflow Orchestration
Visual or structured builder using trigger, conditions, branches, waits, actions and stop criteria.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-01-R02
Automation & Workflow Orchestration
Triggers from events, schedules, thresholds, inbound messages, webhooks and manual commands.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-01-R03
Automation & Workflow Orchestration
Actions for notifications, tasks, tags, offers, booking, membership request, webhook, API and AI draft.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-01-R04
Automation & Workflow Orchestration
Tenant-safe execution context, service identity, permission checks and secret references.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-01-R05
Automation & Workflow Orchestration
Idempotency, retries, timeout, compensation, dead-letter queue and manual replay.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-01-R06
Automation & Workflow Orchestration
Versioning, draft/publish, test mode, simulation, impact estimate and rollback.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-01-R07
Automation & Workflow Orchestration
Execution timeline, reason, inputs, outputs, cost, errors and business outcome.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-01-R08
Automation & Workflow Orchestration
Frequency caps and contact governance inherited from notification/communication policy.
High
V1.5 Growth
Admin Web, Internal SaaS Console
AUT-02-R01
Tasks, Cases, Approvals, SLAs & Escalations
Tasks linked to member, lead, tenant, invoice, incident, device, booking, asset or workflow.
Critical
V1 General Availability
Admin Web, Coach App, Internal SaaS Console
AUT-02-R02
Tasks, Cases, Approvals, SLAs & Escalations
Assignee, team queue, priority, due date, checklist, evidence, dependency and status.
Critical
V1 General Availability
Admin Web, Coach App, Internal SaaS Console
AUT-02-R03
Tasks, Cases, Approvals, SLAs & Escalations
Case container for multi-step problems with communication, timeline, documents and resolution reason.
Critical
V1 General Availability
Admin Web, Coach App, Internal SaaS Console
AUT-02-R04
Tasks, Cases, Approvals, SLAs & Escalations
Approval policies for refunds, discounts, price overrides, payroll, access exceptions, data export and deletion.
Critical
V1 General Availability
Admin Web, Coach App, Internal SaaS Console
AUT-02-R05
Tasks, Cases, Approvals, SLAs & Escalations
Sequential, parallel, quorum and amount-based approvals with delegation and expiry.
Critical
V1 General Availability
Admin Web, Coach App, Internal SaaS Console
AUT-02-R06
Tasks, Cases, Approvals, SLAs & Escalations
SLA clocks, business hours, pause reasons, breach warning and escalation routes.
Critical
V1 General Availability
Admin Web, Coach App, Internal SaaS Console
AUT-02-R07
Tasks, Cases, Approvals, SLAs & Escalations
Workload, aging, bottleneck, outcome and compliance reporting.
Critical
V1 General Availability
Admin Web, Coach App, Internal SaaS Console
INT-01-R01
Operational Analytics, BI, Forecasting & Benchmarking
Role-specific scorecards for owner, region, club, sales, finance, coaching, operations and customer success.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-01-R02
Operational Analytics, BI, Forecasting & Benchmarking
Metric semantic layer with definition, owner, grain, source, freshness and tenant-safe access.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-01-R03
Operational Analytics, BI, Forecasting & Benchmarking
Revenue, collections, membership, retention, attendance, booking, PT, nutrition, POS, inventory, staff and NPS analytics.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-01-R04
Operational Analytics, BI, Forecasting & Benchmarking
Drill from KPI to cohort, location, segment and permission-aware underlying records.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-01-R05
Operational Analytics, BI, Forecasting & Benchmarking
Variance explanations, anomaly detection, forecasts, targets and scenario comparisons.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-01-R06
Operational Analytics, BI, Forecasting & Benchmarking
Benchmarking across a chain and optional privacy-preserving industry cohorts.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-01-R07
Operational Analytics, BI, Forecasting & Benchmarking
Scheduled reports, exports, alerts and embedded analytics.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-01-R08
Operational Analytics, BI, Forecasting & Benchmarking
Data quality, freshness and completeness indicators displayed with decisions.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-02-R01
AI Platform, Copilots, Agents & Governance
Admin Copilot for business questions, explanations, prioritized actions, draft campaigns and guarded execution.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R02
AI Platform, Copilots, Agents & Governance
Sales Copilot for lead prioritization, conversation summary, next action, objection help and follow-up draft.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R03
AI Platform, Copilots, Agents & Governance
Coach Copilot for attention list, program/nutrition draft, adaptation, review summary and client message.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R04
AI Platform, Copilots, Agents & Governance
Member Assistant for navigation, booking, plan explanation and low-risk allowed substitutions.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R05
AI Platform, Copilots, Agents & Governance
Retrieval layer with tenant, role, purpose and record-level authorization at query and response time.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R06
AI Platform, Copilots, Agents & Governance
Tool/action registry with schemas, permission checks, risk tiers, approvals, idempotency and compensating actions.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R07
AI Platform, Copilots, Agents & Governance
Prompt/model/version registry, evaluation sets, routing, fallback, latency and budget controls.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R08
AI Platform, Copilots, Agents & Governance
AI audit recording context references, model, prompt version, outputs, confidence, citations, actions and approver.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R09
AI Platform, Copilots, Agents & Governance
Safety boundaries for health, nutrition, finance, biometric, employment and legal-sensitive use cases.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-02-R10
AI Platform, Copilots, Agents & Governance
Tenant-level opt-in, data-use controls, regional model policy, cost budget and feature disablement.
High
V1.5 Growth
All Product Surfaces, Internal SaaS Console
INT-03-R01
Global Search, Command Bar & Knowledge Navigation
Keyboard-first global command bar on Admin Web and role-appropriate search on mobile.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-03-R02
Global Search, Command Bar & Knowledge Navigation
Search members, leads, staff, bookings, invoices, products, orders, tasks, incidents, assets and settings.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-03-R03
Global Search, Command Bar & Knowledge Navigation
Permission-aware indexing, query filtering, result masking and post-filter validation.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-03-R04
Global Search, Command Bar & Knowledge Navigation
Recent, pinned, suggested and context-sensitive actions such as create, refund, book, message or navigate.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-03-R05
Global Search, Command Bar & Knowledge Navigation
Natural-language commands converted to previewable structured actions.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-03-R06
Global Search, Command Bar & Knowledge Navigation
Help and knowledge results matched to page, role, tenant configuration and product version.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
INT-03-R07
Global Search, Command Bar & Knowledge Navigation
Search analytics for zero-result, latency, permission denial and task-completion improvement.
High
V1.5 Growth
Admin Web, Coach App, Internal SaaS Console
B2B-01-R01
Corporate Memberships & Employer Portal
Corporate account, contract, eligible population, benefit package, subsidy and employee contribution.
High
Enterprise
Corporate Portal, Admin Web, Member App
B2B-01-R02
Corporate Memberships & Employer Portal
Eligibility via roster upload, HRIS/API, email domain, code or enterprise identity.
High
Enterprise
Corporate Portal, Admin Web, Member App
B2B-01-R03
Corporate Memberships & Employer Portal
Employee invitation, self-enrollment, dependent rules, location access and plan selection.
High
Enterprise
Corporate Portal, Admin Web, Member App
B2B-01-R04
Corporate Memberships & Employer Portal
Joiner, mover and leaver synchronization with grace and conversion to personal membership.
High
Enterprise
Corporate Portal, Admin Web, Member App
B2B-01-R05
Corporate Memberships & Employer Portal
Consolidated invoice, employee copay, adjustments, credits and reconciliation.
High
Enterprise
Corporate Portal, Admin Web, Member App
B2B-01-R06
Corporate Memberships & Employer Portal
Privacy-preserving aggregate utilization, engagement, attendance and program-outcome reporting.
High
Enterprise
Corporate Portal, Admin Web, Member App
B2B-01-R07
Corporate Memberships & Employer Portal
Corporate challenges, events, communications and support contacts.
High
Enterprise
Corporate Portal, Admin Web, Member App
B2B-02-R01
Franchise, Multi-brand & Chain Command Center
Hierarchy for holding company, brand, franchisee, region, location and department.
High
Enterprise
Admin Web, Franchise Portal, Internal SaaS Console
B2B-02-R02
Franchise, Multi-brand & Chain Command Center
Central standards with inherited/local overrides for catalog, pricing, membership, brand, access and operations.
High
Enterprise
Admin Web, Franchise Portal, Internal SaaS Console
B2B-02-R03
Franchise, Multi-brand & Chain Command Center
Cross-location member access, home club, revenue attribution, transfer and data ownership policy.
High
Enterprise
Admin Web, Franchise Portal, Internal SaaS Console
B2B-02-R04
Franchise, Multi-brand & Chain Command Center
Comparable scorecards and exception queues for revenue, churn, conversion, NPS, staffing, maintenance and compliance.
High
Enterprise
Admin Web, Franchise Portal, Internal SaaS Console
B2B-02-R05
Franchise, Multi-brand & Chain Command Center
Franchise royalty, marketing fund, shared services, intercompany allocation and settlement exports.
High
Enterprise
Admin Web, Franchise Portal, Internal SaaS Console
B2B-02-R06
Franchise, Multi-brand & Chain Command Center
Location opening/closing playbooks, readiness gates and configuration templates.
High
Enterprise
Admin Web, Franchise Portal, Internal SaaS Console
B2B-02-R07
Franchise, Multi-brand & Chain Command Center
Benchmarking with normalized metrics and permissions by hierarchy scope.
High
Enterprise
Admin Web, Franchise Portal, Internal SaaS Console
ECO-01-R01
Developer Platform, APIs, Webhooks & Sandbox
Versioned public APIs with consistent resources, pagination, filtering, errors and idempotency.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-01-R02
Developer Platform, APIs, Webhooks & Sandbox
OAuth 2/OIDC applications, tenant authorization, granular scopes, API keys and service accounts.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-01-R03
Developer Platform, APIs, Webhooks & Sandbox
Webhook subscriptions, event filtering, signing, retries, ordering guidance, replay and delivery logs.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-01-R04
Developer Platform, APIs, Webhooks & Sandbox
Sandbox tenant, test data, simulated providers and safe webhook endpoint testing.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-01-R05
Developer Platform, APIs, Webhooks & Sandbox
Developer portal with documentation, examples, SDKs, changelog, status and support.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-01-R06
Developer Platform, APIs, Webhooks & Sandbox
Rate limits, quotas, usage analytics, error diagnostics and credential rotation.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-01-R07
Developer Platform, APIs, Webhooks & Sandbox
API versioning, compatibility, deprecation, migration guides and contract tests.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-01-R08
Developer Platform, APIs, Webhooks & Sandbox
Partner certification and security review for sensitive scopes.
High
V2 Platform
Developer Portal, Admin Web, Internal SaaS Console
ECO-02-R01
Integration Framework, Marketplace & Partner Ecosystem
Integration catalog with capabilities, regions, prerequisites, permissions, pricing and support owner.
High
V2 Platform
Admin Web, Developer Portal, Internal SaaS Console
ECO-02-R02
Integration Framework, Marketplace & Partner Ecosystem
Standard connector lifecycle: install, authorize, configure, validate, activate, monitor, rotate and uninstall.
High
V2 Platform
Admin Web, Developer Portal, Internal SaaS Console
ECO-02-R03
Integration Framework, Marketplace & Partner Ecosystem
Provider abstraction for payments, WhatsApp/SMS/email, accounting, access hardware, identity and storage.
High
V2 Platform
Admin Web, Developer Portal, Internal SaaS Console
ECO-02-R04
Integration Framework, Marketplace & Partner Ecosystem
Credential vault, tenant-specific secrets, least scopes and automated rotation reminders.
High
V2 Platform
Admin Web, Developer Portal, Internal SaaS Console
ECO-02-R05
Integration Framework, Marketplace & Partner Ecosystem
Sync state, cursor, retries, conflict policy, dead-letter, reconciliation and diagnostics.
High
V2 Platform
Admin Web, Developer Portal, Internal SaaS Console
ECO-02-R06
Integration Framework, Marketplace & Partner Ecosystem
Marketplace listing, review, certification, trial, billing, revenue share, ratings and support route.
High
V2 Platform
Admin Web, Developer Portal, Internal SaaS Console
ECO-02-R07
Integration Framework, Marketplace & Partner Ecosystem
Vendor dependency register with SLA, outage fallback, cost and exit plan.
High
V2 Platform
Admin Web, Developer Portal, Internal SaaS Console
ECO-03-R01
Hardware Abstraction, Edge Runtime & Device Fleet
Canonical device capabilities for credential read, access actuation, biometric match, scan, print, payment and telemetry.
High
V2 Platform
Internal SaaS Console, Admin Web, Edge Runtime
ECO-03-R02
Hardware Abstraction, Edge Runtime & Device Fleet
Vendor adapters behind stable commands, events, health and configuration contracts.
High
V2 Platform
Internal SaaS Console, Admin Web, Edge Runtime
ECO-03-R03
Hardware Abstraction, Edge Runtime & Device Fleet
Device enrollment, tenant/location assignment, certificate, firmware, configuration and remote revoke.
High
V2 Platform
Internal SaaS Console, Admin Web, Edge Runtime
ECO-03-R04
Hardware Abstraction, Edge Runtime & Device Fleet
Edge runtime with signed policy/data cache, local queue, secure time, retry and conflict handling.
High
V2 Platform
Internal SaaS Console, Admin Web, Edge Runtime
ECO-03-R05
Hardware Abstraction, Edge Runtime & Device Fleet
Fleet dashboard for online status, latency, errors, storage, version, peripherals and last sync.
High
V2 Platform
Internal SaaS Console, Admin Web, Edge Runtime
ECO-03-R06
Hardware Abstraction, Edge Runtime & Device Fleet
Remote commands, staged rollout, maintenance mode, diagnostics bundle and replacement workflow.
High
V2 Platform
Internal SaaS Console, Admin Web, Edge Runtime
ECO-03-R07
Hardware Abstraction, Edge Runtime & Device Fleet
Mobile device management integration for dedicated tablets and kiosks.
High
V2 Platform
Internal SaaS Console, Admin Web, Edge Runtime
WHT-01-R01
White-label, App Builder, CMS & Mobile Release Operations
Brand tokens for logo, icon, color, typography, imagery, tone, domains, sender identities and legal links.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-01-R02
White-label, App Builder, CMS & Mobile Release Operations
Configurable navigation, home modules, feature visibility, campaigns, banners, content blocks and service shortcuts.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-01-R03
White-label, App Builder, CMS & Mobile Release Operations
CMS for announcements, onboarding, help, exercises, recipes, programs, challenges, promotions and legal content.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-01-R04
White-label, App Builder, CMS & Mobile Release Operations
Content workflow with draft, review, localization, scheduling, targeting, versioning and rollback.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-01-R05
White-label, App Builder, CMS & Mobile Release Operations
Branded app ownership model, store account setup, signing, certificates, privacy labels and asset validation.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-01-R06
White-label, App Builder, CMS & Mobile Release Operations
Automated build pipeline, version matrix, staged rollout, minimum supported version and forced/optional update.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-01-R07
White-label, App Builder, CMS & Mobile Release Operations
Preview environment showing exact member experience by brand, location, language, plan and feature flags.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-01-R08
White-label, App Builder, CMS & Mobile Release Operations
Release fleet dashboard for app review, store status, certificates, crashes and adoption.
High
V2 Platform
Admin Web, Member App, Internal SaaS Console
WHT-02-R01
Localization, RTL, Accessibility & Regional Policy
First-class Arabic and English with full RTL/LTR layouts, mixed content and bidirectional testing.
Critical
Foundation
All Surfaces
WHT-02-R02
Localization, RTL, Accessibility & Regional Policy
Locale-aware date, time, week start, number, currency, tax, name, address and phone formatting.
Critical
Foundation
All Surfaces
WHT-02-R03
Localization, RTL, Accessibility & Regional Policy
Translation workflow, glossary, context, screenshot review, pluralization, fallback and tenant overrides.
Critical
Foundation
All Surfaces
WHT-02-R04
Localization, RTL, Accessibility & Regional Policy
Accessibility for screen readers, dynamic type, keyboard, focus order, contrast, reduced motion, captions and touch targets.
Critical
Foundation
All Surfaces
WHT-02-R05
Localization, RTL, Accessibility & Regional Policy
Regional payment, tax, invoicing, data residency, consent, biometrics, labor, contracts and communication policy packs.
Critical
Foundation
All Surfaces
WHT-02-R06
Localization, RTL, Accessibility & Regional Policy
Cuisine, food, serving units, names and search behavior localized for nutrition.
Critical
Foundation
All Surfaces
WHT-02-R07
Localization, RTL, Accessibility & Regional Policy
Time-zone, daylight-saving and cross-region schedule correctness.
Critical
Foundation
All Surfaces
WHT-02-R08
Localization, RTL, Accessibility & Regional Policy
Localization and accessibility QA gates in design, development and release.
Critical
Foundation
All Surfaces
DAT-01-R01
Domain Events, Event Bus & Operational Timeline
Canonical event envelope with tenant, aggregate, actor, correlation, causation, schema, timestamp and source.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-01-R02
Domain Events, Event Bus & Operational Timeline
Transactional outbox or equivalent guarantee between state change and event publication.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-01-R03
Domain Events, Event Bus & Operational Timeline
Schema registry, compatibility rules, ownership, classification and deprecation.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-01-R04
Domain Events, Event Bus & Operational Timeline
At-least-once delivery with idempotent consumers, retry, dead-letter and replay.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-01-R05
Domain Events, Event Bus & Operational Timeline
Event routing to timeline, automation, notification, analytics, integrations, fraud and AI.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-01-R06
Domain Events, Event Bus & Operational Timeline
Retention, compaction, PII minimization, encryption and regional routing.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-01-R07
Domain Events, Event Bus & Operational Timeline
Operational explorer for correlation tracing and controlled replay.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-01-R08
Domain Events, Event Bus & Operational Timeline
Business event catalog accessible to product, engineering, analytics and partners.
Critical
Foundation
Platform, Developer Portal, Internal SaaS Console
DAT-02-R01
Data Platform, Warehouse, Governance & Data Products
Ingestion from domain events, databases, provider settlements, devices and external integrations.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
DAT-02-R02
Data Platform, Warehouse, Governance & Data Products
Warehouse/lakehouse layers for raw, cleaned, conformed and business-ready data.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
DAT-02-R03
Data Platform, Warehouse, Governance & Data Products
Semantic model for shared facts, dimensions, metrics, cohorts and effective-dated history.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
DAT-02-R04
Data Platform, Warehouse, Governance & Data Products
Data catalog, ownership, classification, lineage, quality, freshness and usage.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
DAT-02-R05
Data Platform, Warehouse, Governance & Data Products
Tenant and row/column security, privacy transformations, pseudonymization and aggregation.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
DAT-02-R06
Data Platform, Warehouse, Governance & Data Products
Data products for member health score, churn risk, revenue, capacity, inventory, coach performance and SaaS usage.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
DAT-02-R07
Data Platform, Warehouse, Governance & Data Products
Reverse ETL or safe activation of derived insight back into operational workflows.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
DAT-02-R08
Data Platform, Warehouse, Governance & Data Products
Export, clean room, partner sharing and residency controls for enterprise use.
High
V1.5 Growth
Analytics, AI Platform, Internal SaaS Console, Enterprise Export
SEC-01-R01
Security, Privacy, Compliance & Consent
Security architecture, threat modeling, secure defaults, least privilege and zero-trust service identity.
Critical
Foundation
All Systems
SEC-01-R02
Security, Privacy, Compliance & Consent
Encryption in transit and at rest, key management, rotation, secret vault and certificate lifecycle.
Critical
Foundation
All Systems
SEC-01-R03
Security, Privacy, Compliance & Consent
Secure SDLC with code review, SAST/DAST, dependency, container, IaC and secret scanning.
Critical
Foundation
All Systems
SEC-01-R04
Security, Privacy, Compliance & Consent
Vulnerability management, penetration tests, bug response, risk acceptance and remediation SLAs.
Critical
Foundation
All Systems
SEC-01-R05
Security, Privacy, Compliance & Consent
Data classification for identity, contact, financial, health, biometric, media, employment, operational and analytics data.
Critical
Foundation
All Systems
SEC-01-R06
Security, Privacy, Compliance & Consent
Consent registry for terms, privacy, marketing, waiver, health, biometrics, media and data sharing with version history.
Critical
Foundation
All Systems
SEC-01-R07
Security, Privacy, Compliance & Consent
Data subject requests for access, correction, portability, restriction and deletion with identity and legal checks.
Critical
Foundation
All Systems
SEC-01-R08
Security, Privacy, Compliance & Consent
Retention schedule, archive, deletion, legal hold, backup expiry and subprocessor governance.
Critical
Foundation
All Systems
SEC-01-R09
Security, Privacy, Compliance & Consent
Security monitoring, incident response, evidence, notification assessment and postmortem.
Critical
Foundation
All Systems
SEC-01-R10
Security, Privacy, Compliance & Consent
Enterprise package: DPA, security whitepaper, subprocessor list, SLA, controls evidence and questionnaire response.
Critical
Foundation
All Systems
SEC-02-R01
Fraud, Abuse, Trust & Content Moderation
Rules and anomaly detection for QR sharing, access passback, guest abuse, duplicate identities and biometric spoofing.
High
V1.5 Growth
Admin Web, Internal SaaS Console, Member App
SEC-02-R02
Fraud, Abuse, Trust & Content Moderation
Payment, wallet, refund, discount, promotion, referral and chargeback abuse signals.
High
V1.5 Growth
Admin Web, Internal SaaS Console, Member App
SEC-02-R03
Fraud, Abuse, Trust & Content Moderation
Staff fraud indicators for unauthorized overrides, cash variance, stock adjustment and suspicious member changes.
High
V1.5 Growth
Admin Web, Internal SaaS Console, Member App
SEC-02-R04
Fraud, Abuse, Trust & Content Moderation
Risk score, evidence, case creation, action recommendation and human review.
High
V1.5 Growth
Admin Web, Internal SaaS Console, Member App
SEC-02-R05
Fraud, Abuse, Trust & Content Moderation
Progressive responses: warn, challenge, hold, restrict, require approval, suspend and investigate.
High
V1.5 Growth
Admin Web, Internal SaaS Console, Member App
SEC-02-R06
Fraud, Abuse, Trust & Content Moderation
Community reporting, blocking, moderation queues, policy reasons, appeals and repeat-offender handling.
High
V1.5 Growth
Admin Web, Internal SaaS Console, Member App
SEC-02-R07
Fraud, Abuse, Trust & Content Moderation
Model/rule monitoring for false positives, bias, drift and business impact.
High
V1.5 Growth
Admin Web, Internal SaaS Console, Member App
REL-01-R01
Reliability, Offline Operation, Business Continuity & Incident Management
Service-level indicators, objectives and error budgets for login, access, booking, POS, payments, messaging and core APIs.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R02
Reliability, Offline Operation, Business Continuity & Incident Management
Resilient patterns: timeout, retry with jitter, circuit breaker, bulkhead, queue, idempotency and graceful degradation.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R03
Reliability, Offline Operation, Business Continuity & Incident Management
Offline modes for check-in, access and selected front-desk/POS operations with bounded risk and reconciliation.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R04
Reliability, Offline Operation, Business Continuity & Incident Management
Backup, point-in-time recovery, restore testing, replication and tenant-level recovery procedures.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R05
Reliability, Offline Operation, Business Continuity & Incident Management
Documented RPO/RTO by data and workflow criticality.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R06
Reliability, Offline Operation, Business Continuity & Incident Management
Disaster recovery for zone, region, database, object storage, queue and identity dependencies.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R07
Reliability, Offline Operation, Business Continuity & Incident Management
Incident command, severity, ownership, timeline, runbook, status page, customer communication and postmortem.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R08
Reliability, Offline Operation, Business Continuity & Incident Management
Provider continuity plans for payments, messaging, access hardware, biometric and cloud services.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-01-R09
Reliability, Offline Operation, Business Continuity & Incident Management
Chaos, failover, restore and business-continuity drills on a defined cadence.
Critical
Foundation
Platform, Internal SaaS Console, Status Page, Edge Devices
REL-02-R01
Observability, Performance, Capacity & FinOps
Structured logs, metrics and distributed traces with tenant-safe correlation and redaction.
Critical
Foundation
Internal SaaS Console, Engineering Operations
REL-02-R02
Observability, Performance, Capacity & FinOps
Golden signals and business signals for each critical workflow and dependency.
Critical
Foundation
Internal SaaS Console, Engineering Operations
REL-02-R03
Observability, Performance, Capacity & FinOps
Synthetic monitoring for login, member search, booking, payment, POS, check-in, webhook and messaging paths.
Critical
Foundation
Internal SaaS Console, Engineering Operations
REL-02-R04
Observability, Performance, Capacity & FinOps
Performance budgets for web, mobile, APIs, search, edge access and report generation.
Critical
Foundation
Internal SaaS Console, Engineering Operations
REL-02-R05
Observability, Performance, Capacity & FinOps
Capacity models, load tests, scaling policy, hot-tenant protection and noisy-neighbor controls.
Critical
Foundation
Internal SaaS Console, Engineering Operations
REL-02-R06
Observability, Performance, Capacity & FinOps
Cost allocation by tenant, domain, environment, AI model, message, storage, integration and support.
Critical
Foundation
Internal SaaS Console, Engineering Operations
REL-02-R07
Observability, Performance, Capacity & FinOps
Budgets, anomaly alerts, unit economics, margin by plan and cost optimization backlog.
Critical
Foundation
Internal SaaS Console, Engineering Operations
REL-02-R08
Observability, Performance, Capacity & FinOps
Operational dashboards and alert routing with ownership, runbook and escalation.
Critical
Foundation
Internal SaaS Console, Engineering Operations
LIF-01-R01
Onboarding, Implementation & Go-live Readiness
Guided setup for organization, brands, locations, legal entities, regional settings and administrators.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-01-R02
Onboarding, Implementation & Go-live Readiness
Configure plans, catalog, pricing, tax, payment, access, schedule, staff, roles, documents, communications and apps.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-01-R03
Onboarding, Implementation & Go-live Readiness
Implementation project with checklist, owner, dependency, due date, evidence, risks and readiness score.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-01-R04
Onboarding, Implementation & Go-live Readiness
Data migration waves, validation, reconciliation, sign-off and cutover plan.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-01-R05
Onboarding, Implementation & Go-live Readiness
Hardware installation, network test, device enrollment, offline validation and operational rehearsal.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-01-R06
Onboarding, Implementation & Go-live Readiness
Role-based training, sandbox practice, knowledge paths and certification.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-01-R07
Onboarding, Implementation & Go-live Readiness
Go-live gate covering data, finance, access, bookings, support, rollback and communication.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-01-R08
Onboarding, Implementation & Go-live Readiness
Hypercare period, issue triage, adoption review and transition to customer success.
Critical
Pilot
Admin Web, Internal SaaS Console, Learning Portal
LIF-02-R01
Migration, Import, Validation & Cutover
Source-specific importers for CSV/Excel and prioritized competitors, plus generic API/file framework.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-02-R02
Migration, Import, Validation & Cutover
Mapping workspace for fields, codes, locations, plans, products, statuses, currencies and identities.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-02-R03
Migration, Import, Validation & Cutover
Transformations, normalization, deduplication, defaults and exception queues.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-02-R04
Migration, Import, Validation & Cutover
Dry run with counts, financial totals, orphan records, conflicts, invalid data and remediation guidance.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-02-R05
Migration, Import, Validation & Cutover
Migration of members, leads, memberships, balances, credits, invoices, payments, bookings, attendance, programs, notes and documents according to scope.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-02-R06
Migration, Import, Validation & Cutover
Incremental/delta imports, freeze window, cutover runbook and post-cutover reconciliation.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-02-R07
Migration, Import, Validation & Cutover
Import lineage, source identifiers, evidence, sign-off and controlled rollback.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-02-R08
Migration, Import, Validation & Cutover
Privacy-safe staging, time-limited source files and secure deletion.
Critical
Pilot
Admin Web, Internal SaaS Console
LIF-03-R01
Offboarding, Data Portability, Archival & Deletion
Tenant lifecycle from active to past due, suspended, cancelled, read-only, archived and deleted.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
LIF-03-R02
Offboarding, Data Portability, Archival & Deletion
Final billing, settlement, refunds, outstanding obligations, device return and credential revocation.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
LIF-03-R03
Offboarding, Data Portability, Archival & Deletion
Structured export for members, contracts, payments, invoices, attendance, bookings, training, nutrition, messages and audit according to rights.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
LIF-03-R04
Offboarding, Data Portability, Archival & Deletion
Export manifest, schema, checksums, encryption, expiry and delivery audit.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
LIF-03-R05
Offboarding, Data Portability, Archival & Deletion
Retention by data class, legal hold, archive tier, restoration authorization and deletion schedule.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
LIF-03-R06
Offboarding, Data Portability, Archival & Deletion
Integration uninstall, webhook shutdown, secret destruction, domain release and app-store transition.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
LIF-03-R07
Offboarding, Data Portability, Archival & Deletion
Member-level account deletion/export coordinated across tenant and platform obligations.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
LIF-03-R08
Offboarding, Data Portability, Archival & Deletion
Deletion evidence and tombstones preventing unintended recreation or orphaned references.
High
Enterprise
Internal SaaS Console, Tenant Admin, Member App
GOV-01-R01
Quality Engineering, CI/CD, Release & Schema Management
Test pyramid covering unit, component, integration, contract, end-to-end, mobile UI and exploratory testing.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-01-R02
Quality Engineering, CI/CD, Release & Schema Management
Critical workflow suites for authentication, tenant isolation, membership, booking, payment, ledger, POS, access and migration.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-01-R03
Quality Engineering, CI/CD, Release & Schema Management
Load, performance, security, accessibility, localization, offline and failure testing.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-01-R04
Quality Engineering, CI/CD, Release & Schema Management
CI gates for lint, test, vulnerability, schema compatibility, migration safety and artifact signing.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-01-R05
Quality Engineering, CI/CD, Release & Schema Management
Progressive delivery, canary, feature flags, automated rollback and release evidence.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-01-R06
Quality Engineering, CI/CD, Release & Schema Management
Backward-compatible database changes, expand-contract pattern, zero-downtime migration and rollback strategy.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-01-R07
Quality Engineering, CI/CD, Release & Schema Management
Mobile version support policy, store rollout, crash monitoring and remote configuration.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-01-R08
Quality Engineering, CI/CD, Release & Schema Management
Release train, changelog, maintenance, beta/GA/deprecation lifecycle and customer communication.
Critical
Foundation
Engineering, Internal SaaS Console
GOV-02-R01
Product, Architecture, Data & AI Governance
Domain ownership with product, design, engineering, data and operations accountable leaders.
Critical
Foundation
Internal Product Operations
GOV-02-R02
Product, Architecture, Data & AI Governance
Architecture decision records, service boundaries, invariants, dependency rules and review forum.
Critical
Foundation
Internal Product Operations
GOV-02-R03
Product, Architecture, Data & AI Governance
Product lifecycle from discovery to beta, GA, deprecation and removal with evidence gates.
Critical
Foundation
Internal Product Operations
GOV-02-R04
Product, Architecture, Data & AI Governance
Design system governance for components, interaction patterns, accessibility, RTL and white-label tokens.
Critical
Foundation
Internal Product Operations
GOV-02-R05
Product, Architecture, Data & AI Governance
Data governance council for ownership, metrics, quality, classification, lineage and access.
Critical
Foundation
Internal Product Operations
GOV-02-R06
Product, Architecture, Data & AI Governance
AI governance for use-case approval, risk tier, evaluation, model change, human oversight and incident response.
Critical
Foundation
Internal Product Operations
GOV-02-R07
Product, Architecture, Data & AI Governance
Requirement traceability from strategy through domain, flow, screen, event, test and metric.
Critical
Foundation
Internal Product Operations
GOV-02-R08
Product, Architecture, Data & AI Governance
Portfolio prioritization using value, urgency, dependency, risk, revenue, cost and learning.
Critical
Foundation
Internal Product Operations
GOV-03-R01
Legal, Procurement, Vendor, Partner & Compliance Operations
Terms, privacy notice, DPA, SLA, acceptable-use, biometric, AI, marketplace and partner policies with versioning.
High
Enterprise
Internal SaaS Console, Legal/Compliance Workspace
GOV-03-R02
Legal, Procurement, Vendor, Partner & Compliance Operations
Contract repository, obligations, renewal, notice periods, security addenda and approval workflow.
High
Enterprise
Internal SaaS Console, Legal/Compliance Workspace
GOV-03-R03
Legal, Procurement, Vendor, Partner & Compliance Operations
Enterprise procurement pack, security questionnaires, architecture diagrams and evidence library.
High
Enterprise
Internal SaaS Console, Legal/Compliance Workspace
GOV-03-R04
Legal, Procurement, Vendor, Partner & Compliance Operations
Vendor inventory, risk tier, due diligence, DPA, subprocessor, SLA, cost, performance and exit plan.
High
Enterprise
Internal SaaS Console, Legal/Compliance Workspace
GOV-03-R05
Legal, Procurement, Vendor, Partner & Compliance Operations
Partner/reseller onboarding, certification, territory, deal registration, commission, conduct and termination.
High
Enterprise
Internal SaaS Console, Legal/Compliance Workspace
GOV-03-R06
Legal, Procurement, Vendor, Partner & Compliance Operations
Compliance control mapping, evidence collection, audit calendar, remediation and continuous monitoring.
High
Enterprise
Internal SaaS Console, Legal/Compliance Workspace
GOV-03-R07
Legal, Procurement, Vendor, Partner & Compliance Operations
Insurance, business continuity, intellectual property and open-source license governance.
High
Enterprise
Internal SaaS Console, Legal/Compliance Workspace
GOV-04-R01
GTM Operations, Knowledge, Training, Feedback & Product Education
Internal sales pipeline for Gym OS leads, demos, trials, proposals, procurement, contracts and handoff.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help
GOV-04-R02
GTM Operations, Knowledge, Training, Feedback & Product Education
Demo tenants, scenario data, role-based demo scripts and resettable environments.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help
GOV-04-R03
GTM Operations, Knowledge, Training, Feedback & Product Education
Knowledge base, contextual help, guided tours, release notes and troubleshooting trees.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help
GOV-04-R04
GTM Operations, Knowledge, Training, Feedback & Product Education
Admin Academy, Coach Academy, implementation training and partner certification.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help
GOV-04-R05
GTM Operations, Knowledge, Training, Feedback & Product Education
Feedback intake from support, NPS, interviews, in-product prompts, sales and partners with deduplication.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help
GOV-04-R06
GTM Operations, Knowledge, Training, Feedback & Product Education
Opportunity repository linking problem evidence, affected segment, value, risk and decision.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help
GOV-04-R07
GTM Operations, Knowledge, Training, Feedback & Product Education
Adoption campaigns and capability education targeted by tenant configuration and behavior.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help
GOV-04-R08
GTM Operations, Knowledge, Training, Feedback & Product Education
Release and deprecation communication by impacted tenant, role and integration.
Critical
Pilot
Internal SaaS Console, Learning Portal, In-product Help


CHAPTER B
# Domain Event Catalog
The initial business event vocabulary for timelines, automation, analytics and integrations.
Domain
Name
Initial events
Phase
PLT-01
Tenant, Organization, Brand & Location Management
tenant.provisioned, tenant.activated, tenant.suspended, organization.updated, location.opened, brand.created
Foundation
PLT-02
Configuration, Feature Flags & Experimentation
configuration.changed, feature_flag.evaluated, experiment.exposed, experiment.completed
Foundation
PLT-03
SaaS Plans, Subscription Billing, Metering & Entitlements
saas.subscription.started, saas.subscription.changed, saas.usage.recorded, saas.quota.reached, saas.payment.failed
Foundation
PLT-04
Internal Administration, Support & Customer Success
tenant.health.changed, support.session.started, support.ticket.escalated, renewal.risk.detected
Pilot
IAM-01
Identity, Authentication, Passkeys & Device Sessions
identity.created, authentication.succeeded, authentication.failed, session.revoked, passkey.registered, risk.challenge.required
Foundation
IAM-02
Biometric Identity & Physical Access Methods
biometric.enrolled, biometric.revoked, liveness.failed, access_credential.issued, wallet_pass.updated
V2 Platform
IAM-03
Authorization, Roles, Permissions, Approvals & Audit
role.assigned, permission.denied, approval.requested, approval.completed, audit_event.recorded
Foundation
PPL-01
People, Profiles & Member 360
person.created, profile.updated, member.lifecycle.changed, person.merged, relationship.created
Foundation
PPL-02
Households, Dependents, Guests & Eligibility
household.created, dependent.added, eligibility.verified, guest_pass.issued, trial.converted
V1 General Availability
GRO-01
CRM, Leads, Sales Pipeline & Trials
lead.created, lead.assigned, trial.booked, trial.attended, offer.sent, opportunity.won, opportunity.lost
V1 General Availability
GRO-02
Marketing, Referrals, Offers & Growth Journeys
campaign.launched, message.delivered, referral.created, referral.qualified, offer.redeemed, journey.completed
V1.5 Growth
COM-01
Memberships, Contracts, Entitlements & Lifecycle
membership.created, membership.activated, membership.frozen, membership.changed, membership.renewed, membership.cancelled, entitlement.changed
V1 General Availability
COM-02
Catalog, Pricing, Promotions & Packages
product.published, price.changed, promotion.activated, coupon.redeemed, bundle.fulfilled
V1 General Availability
COM-03
Member Billing, Payments, Tax & Revenue Recovery
invoice.issued, payment.succeeded, payment.failed, dunning.started, refund.completed, chargeback.opened
V1 General Availability
COM-04
Financial Ledger, Wallet, Credits & Reconciliation
ledger.posted, wallet.credited, wallet.debited, credit.consumed, settlement.imported, reconciliation.mismatch.detected
V1 General Availability
COM-05
Point of Sale, Ecommerce & Order Fulfillment
cart.created, order.completed, cash_shift.opened, return.completed, receipt.sent, fulfillment.completed
V1 General Availability
COM-06
Inventory, Purchasing, Suppliers & Stock Control
stock.received, stock.reserved, stock.adjusted, stock.transferred, stock.low, lot.expiring
V1.5 Growth
OPS-01
Scheduling, Resources & Capacity
schedule.published, session.created, session.changed, resource.conflict.detected, instructor.substituted
V1 General Availability
OPS-02
Booking, Waitlist & No-show Intelligence
booking.created, booking.cancelled, waitlist.joined, waitlist.promoted, no_show.recorded, booking.checked_in
V1 General Availability
OPS-03
Check-in, Access Control & Entitlement Decisions
access.requested, access.granted, access.denied, access.overridden, occupancy.changed, device.offline
V1 General Availability
OPS-04
Front Desk, Kiosk, Guest & Visitor Operations
arrival.detected, visitor.registered, waiver.signed, front_desk.case.resolved, handoff.created
V1 General Availability
OPS-05
Staff, Shifts, Attendance, Payroll & Commissions
staff.onboarded, shift.started, time_entry.corrected, session.verified, commission.earned, payroll.approved
V1.5 Growth
OPS-06
Facilities, Equipment, Assets & Maintenance
asset.registered, issue.reported, asset.isolated, work_order.created, maintenance.completed, facility.closed
V2 Platform
COA-01
Coach Workspace & Client Management
coach.assigned, session.started, session.completed, client.attention.required, coach_note.created
V1 General Availability
COA-02
Training Programs, Workouts & Exercise Logging
program.assigned, workout.started, set.logged, workout.completed, personal_record.achieved, program.adjusted
V1 General Availability
COA-03
Nutrition Planning, Meals, Logging & Adherence
nutrition_plan.assigned, meal.logged, meal.swapped, nutrition_checkin.submitted, adherence.changed, coach_review.required
V1.5 Growth
COA-04
Assessments, Measurements, Progress & Outcomes
assessment.completed, measurement.recorded, goal.created, milestone.achieved, progress_review.required
V1 General Availability
COA-05
Health, Safety, Consent & Incident Management
screening.submitted, consent.signed, limitation.updated, incident.reported, incident.escalated, corrective_action.closed
V1 General Availability
ENG-01
Unified Inbox, Messaging & Contextual Communication
message.received, message.sent, message.failed, conversation.assigned, conversation.sla_breached
V1 General Availability
ENG-02
Notification Platform, Templates & Preferences
notification.requested, notification.sent, notification.delivered, notification.failed, preference.changed
Foundation
ENG-03
Community, Challenges, Achievements & Rewards
challenge.joined, challenge.progressed, achievement.earned, reward.issued, reward.redeemed, content.reported
V1.5 Growth
ENG-04
Member Self-Service, Digital Card & Service Requests
wallet_pass.issued, self_service.requested, self_service.approved, payment_method.updated, data_export.requested
V1 General Availability
AUT-01
Automation & Workflow Orchestration
workflow.published, workflow.started, workflow.step.failed, workflow.completed, workflow.replayed
V1.5 Growth
AUT-02
Tasks, Cases, Approvals, SLAs & Escalations
task.created, task.overdue, case.opened, approval.requested, approval.rejected, sla.breached
V1 General Availability
INT-01
Operational Analytics, BI, Forecasting & Benchmarking
metric.updated, anomaly.detected, forecast.generated, target.missed, report.delivered
V1.5 Growth
INT-02
AI Platform, Copilots, Agents & Governance
ai.requested, ai.response.generated, ai.tool.proposed, ai.tool.approved, ai.tool.executed, ai.safety.blocked
V1.5 Growth
INT-03
Global Search, Command Bar & Knowledge Navigation
search.executed, search.zero_result, command.previewed, command.executed
V1.5 Growth
B2B-01
Corporate Memberships & Employer Portal
corporate.contract.started, eligibility.added, employee.enrolled, employee.eligibility.ended, corporate.invoice.issued
Enterprise
B2B-02
Franchise, Multi-brand & Chain Command Center
governance.published, location.exception.detected, member.home_club.changed, royalty.statement.created
Enterprise
ECO-01
Developer Platform, APIs, Webhooks & Sandbox
developer_app.created, oauth.granted, api.rate_limited, webhook.delivered, webhook.failed, api.version.deprecated
V2 Platform
ECO-02
Integration Framework, Marketplace & Partner Ecosystem
integration.installed, integration.connected, integration.sync.failed, credential.expiring, marketplace.listing.approved
V2 Platform
ECO-03
Hardware Abstraction, Edge Runtime & Device Fleet
device.enrolled, device.online, device.offline, device.command.completed, firmware.updated, edge.sync.conflict
V2 Platform
WHT-01
White-label, App Builder, CMS & Mobile Release Operations
content.published, app_configuration.changed, build.completed, store_release.approved, mobile_version.deprecated
V2 Platform
WHT-02
Localization, RTL, Accessibility & Regional Policy
translation.published, regional_policy.updated, accessibility.issue.detected, locale.changed
Foundation
DAT-01
Domain Events, Event Bus & Operational Timeline
event.published, event.delivery.failed, event.replayed, event_schema.changed
Foundation
DAT-02
Data Platform, Warehouse, Governance & Data Products
data.ingested, data_quality.failed, data_product.published, dataset.accessed, data_export.completed
V1.5 Growth
SEC-01
Security, Privacy, Compliance & Consent
consent.granted, consent.withdrawn, security.alert.detected, vulnerability.opened, data_subject_request.completed
Foundation
SEC-02
Fraud, Abuse, Trust & Content Moderation
fraud.signal.detected, trust.case.opened, account.restricted, content.reported, moderation.decided, appeal.resolved
V1.5 Growth
REL-01
Reliability, Offline Operation, Business Continuity & Incident Management
slo.breached, offline_mode.entered, sync.reconciled, backup.completed, restore.tested, incident.declared, incident.resolved
Foundation
REL-02
Observability, Performance, Capacity & FinOps
synthetic_check.failed, performance_budget.exceeded, capacity.threshold.reached, cost.anomaly.detected
Foundation
LIF-01
Onboarding, Implementation & Go-live Readiness
implementation.started, readiness.changed, go_live.approved, tenant.went_live, hypercare.completed
Pilot
LIF-02
Migration, Import, Validation & Cutover
migration.dry_run.completed, migration.error.detected, migration.import.completed, migration.reconciled, cutover.completed
Pilot
LIF-03
Offboarding, Data Portability, Archival & Deletion
tenant.offboarding.started, data_export.ready, tenant.archived, credentials.revoked, data.deleted
Enterprise
GOV-01
Quality Engineering, CI/CD, Release & Schema Management
build.completed, quality_gate.failed, deployment.started, deployment.rolled_back, release.published, schema.migrated
Foundation
GOV-02
Product, Architecture, Data & AI Governance
decision.accepted, domain.owner.changed, product_feature.deprecated, governance.review.completed
Foundation
GOV-03
Legal, Procurement, Vendor, Partner & Compliance Operations
legal_document.published, contract.renewal_due, vendor.risk.changed, partner.certified, control.test.failed
Enterprise
GOV-04
GTM Operations, Knowledge, Training, Feedback & Product Education
demo.created, learning.completed, feedback.received, opportunity.validated, release_communication.sent
Pilot

## Event Envelope Minimum
event_id, event_type, schema_version, occurred_at and published_at.
tenant_id plus organization/brand/location context when applicable.
aggregate_type, aggregate_id and aggregate_version.
actor type/id, authentication assurance and delegated/service identity.
correlation_id, causation_id, command/request reference and idempotency key where relevant.
data classification, purpose, region and retention metadata.

CHAPTER C
# Glossary & Completeness Checklist
Shared language and the final master-scope verification.
## Glossary
Term
Definition
Tenant
A customer organization whose data, configuration, users, billing and operations are isolated.
Organization
The top business hierarchy inside a tenant.
Brand
A customer-facing identity with its own app, content, catalog and policies.
Location
A physical or virtual operating site.
Member 360
Permission-aware consolidated view of a member lifecycle and interactions.
Entitlement
An operational right granted by membership, purchase, role or policy.
Service Credit
A non-cash right to consume a PT session, class, assessment or similar service.
Ledger
Immutable financial record from which balances are derived.
Domain Event
Durable fact that an important business state change occurred.
Workflow
Versioned multi-step automation triggered by an event, time or command.
Case
Accountable human work container for an exception or problem.
BFF
Backend-for-Frontend API composition tailored to a specific client surface.
Edge Runtime
Managed local software operating near access/POS devices with offline capability.
Data Product
Governed dataset or model with owner, quality, contract and consumers.
AI Tool
Permissioned structured action an AI assistant may propose or execute under policy.
White-label
Configurable branded experience without a separate product codebase.
RPO / RTO
Maximum acceptable data loss window / service recovery time target.
SLO
Measurable reliability objective for a service or workflow.

## Master Scope Completeness Checklist
☑ Multi-tenant isolation, organization hierarchy, provisioning and tenant lifecycle.
☑ SaaS plans, billing, metering, entitlements, quotas, tax, dunning and margin.
☑ Identity, passkeys, MFA, SSO/SCIM, devices, roles, policies, approvals and audit.
☑ Biometric app authentication and optional privacy-controlled physical facial access.
☑ CRM, sales, marketing, referrals, trials, attribution and growth journeys.
☑ Member 360, households, dependents, guests and corporate eligibility.
☑ Membership lifecycle, contracts, entitlements, pricing and promotions.
☑ Member billing, payments, invoices, immutable ledger, wallet and reconciliation.
☑ POS, ecommerce, orders, receipts, refunds, inventory, purchasing and suppliers.
☑ Scheduling, booking, waitlist, no-show, front desk, kiosk and guest operations.
☑ Check-in, access control, offline decisions, devices and occupancy.
☑ Staff, shifts, attendance, tasks, payroll, commissions and performance.
☑ Training, programs, workouts, assessments, progress and coach workflows.
☑ Nutrition planning, one-tap logging, swaps, groceries, check-ins and exception management.
☑ Health, safety, consent, waivers, restrictions, incidents and emergency context.
☑ Unified communication, notifications, community, challenges and rewards.
☑ Automations, tasks, cases, approvals, SLAs and escalations.
☑ Analytics, forecasting, benchmarking, search, copilots and governed AI agents.
☑ Corporate portal, franchise command center and multi-brand governance.
☑ Developer platform, APIs, webhooks, sandbox, marketplace and partner certification.
☑ Hardware abstraction, edge runtime, device fleet and vendor exit plans.
☑ White-label app builder, CMS, mobile fleet and release operations.
☑ Arabic RTL, accessibility, regional payments/tax/policy and data residency.
☑ Events, warehouse, data products, governance, privacy and security.
☑ Reliability, observability, offline operation, backup, DR, incidents and FinOps.
☑ Onboarding, migration, training, support, customer success, offboarding and export.
☑ Quality engineering, CI/CD, schema evolution, governance, legal, procurement and GTM operations.
Blueprint completion statement
No major product, SaaS, enterprise or operational domain identified in the approved Gym OS vision is intentionally omitted from Version 1.0 of this master blueprint. Future discoveries should be added through the same domain, dependency, risk and governance model.
