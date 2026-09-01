// VEYRO SCREEN REGISTRY — SINGLE SOURCE OF TRUTH
// Extracted from Veyro Screen Registry.dc.html. Every document that reports a
// Veyro screen count imports this file. There is no second copy to drift from.
// 8 fields: [id, module, name, phase, status, roles, ar, note]
// phase: V1 | V1.5 | V2 | ENT   status: DONE | GAP | NO-UI | V1.5 | V2 | ENT
// ar: BUILT | CONTRACT | NEEDS | N/A
// Surface and domain are derived from the id prefix — never stored.

export const R = [
// ── ADMIN ──────────────────────────────────────────────
['ADM-CC-01','Command','Command Center · Owner, all locations','V1','DONE','Owner,RM','BUILT','HF Command Center c1'],
['ADM-CC-02','Command','Command Center · Club Manager, branch scope','V1','DONE','CM','CONTRACT','HF Command Center c2'],
['ADM-CC-03','Command','Command Center · critical exception','V1','DONE','All admin','CONTRACT','HF Command Center c3'],
['ADM-CC-04','Command','Command Center · quiet day','V1','DONE','All admin','CONTRACT','HF Command Center c4'],
['ADM-CC-05','Command','Command Center · degraded data','V1','DONE','All admin','CONTRACT','HF Command Center c5'],
['ADM-CC-06','Command','Attention item detail · side sheet','V1','GAP','All admin','CONTRACT','Resolution workspace for one exception'],
['ADM-CC-07','Command','Resolved history · today','V1','GAP','All admin','CONTRACT','Audit of what was actioned and by whom'],
['ADM-CRM-01','CRM','Lead pipeline','V1','DONE','Sales,CM','NEEDS','HF CRM and Console c1'],
['ADM-CRM-02','CRM','Lead list · table view','V1','GAP','Sales,CM','CONTRACT','Filterable table alternative to the board'],
['ADM-CRM-03','CRM','Lead profile · full','V1','GAP','Sales,CM','NEEDS','Activity, source, ownership, next action'],
['ADM-CRM-04','CRM','Add lead · form','V1','GAP','Sales,Recep','NEEDS','First form screen in the product'],
['ADM-CRM-05','CRM','Trial in progress · day N of 7','V1','GAP','Sales,CM','CONTRACT','Trial clock, usage, conversion prompt'],
['ADM-CRM-06','CRM','Convert trial to member','V1','GAP','Sales,CM','NEEDS','Plan pick, terms, first payment'],
['ADM-CRM-07','CRM','Lost lead · reason capture','V1','GAP','Sales','CONTRACT','Structured reason, feeds retention analytics'],
['ADM-MEM-01','Members','Member 360 · attention','V1','DONE','CM,Recep','BUILT','HF Member 360 c1'],
['ADM-MEM-02','Members','Member 360 · healthy','V1','DONE','CM','CONTRACT','HF Member 360 c2'],
['ADM-MEM-03','Members','Member 360 · receptionist view','V1','DONE','Recep','CONTRACT','HF Member 360 c3'],
['ADM-MEM-04','Members','Member 360 · frozen + loading','V1','DONE','CM','CONTRACT','HF Member 360 c4'],
['ADM-MEM-05','Members','Members list · filter, bulk, saved views','V1','DONE','CM,Recep','NEEDS','V1 Admin Members c1 · 34px rows, saved views, bulk bar'],
['ADM-MEM-06','Members','Member · billing tab','V1','GAP','CM,Acct','NEEDS','Invoices, methods, schedule, arrears'],
['ADM-MEM-07','Members','Member · attendance tab','V1','GAP','CM','CONTRACT','Visit history, patterns, gaps'],
['ADM-MEM-08','Members','Member · documents tab','V1','GAP','CM','CONTRACT','Contracts, waivers, ID, expiry tracking'],
['ADM-MEM-09','Members','Member · notes and communication','V1','GAP','CM,Recep','NEEDS','Staff notes, WhatsApp thread, consent state'],
['ADM-MEM-10','Members','Add member · manual','V1','GAP','Recep,Sales','NEEDS','Walk-in join without a lead record'],
['ADM-MEM-11','Members','Merge duplicate members','V1','GAP','CM','CONTRACT','Field-by-field resolution, destructive'],
['ADM-MSH-01','Membership','Membership sale · plan selection','V1','DONE','Sales,Recep','NEEDS','V1 Admin Members c2 · pro-rata + recurring both shown'],
['ADM-MSH-02','Membership','Membership · renew','V1','GAP','CM,Recep','CONTRACT','Same or changed plan, price change disclosure'],
['ADM-MSH-03','Membership','Membership · freeze','V1','GAP','CM','NEEDS','Reason, dates, allowance, billing and access impact'],
['ADM-MSH-04','Membership','Membership · resume early','V1','GAP','CM','CONTRACT','Proration, revised end date'],
['ADM-MSH-05','Membership','Membership · upgrade','V1','DONE','Sales,CM','NEEDS','V1 Admin Members c3 · proration maths before commit'],
['ADM-MSH-06','Membership','Membership · downgrade','V1','GAP','CM','CONTRACT','Entitlement loss stated explicitly'],
['ADM-MSH-07','Membership','Membership · cancel','V1','DONE','CM','NEEDS','V1 Admin Members c4 · tier 3, freeze offered first'],
['ADM-MSH-08','Membership','Membership · transfer','V1.5','V1.5','CM','N/A','Deferred — needs legal position per market'],
['ADM-MSH-09','Membership','Plans and pricing configuration','V1','GAP','Owner','CONTRACT','Plan catalogue, entitlements, price changes'],
['ADM-PAY-01','Payments','Payments ledger','V1','DONE','Acct,CM','NEEDS','HF Remaining Modules c2'],
['ADM-PAY-02','Payments','Refund · tier 3+4 confirmation','V1','DONE','CM,Acct','CONTRACT','HF Remaining Modules c3'],
['ADM-PAY-03','Payments','Invoice detail','V1','DONE','Acct,CM','NEEDS','V1 Admin Billing c1 · immutable, JoFotara state'],
['ADM-PAY-04','Payments','Take payment · modal','V1','GAP','Recep,CM','NEEDS','Method, amount, allocation to invoices'],
['ADM-PAY-05','Payments','Failed payment · recovery workspace','V1','DONE','Acct,CM','CONTRACT','V1 Admin Billing c2 · batch of 6, message preview'],
['ADM-PAY-06','Payments','Dunning configuration','V1','GAP','Owner,Acct','CONTRACT','Retry schedule, grace, message templates'],
['ADM-PAY-07','Payments','Wallet and credits','V1','GAP','Acct,Recep','CONTRACT','Balance, top-up, spend history, expiry'],
['ADM-PAY-08','Payments','Partial refund','V1','GAP','CM,Acct','CONTRACT','Amount split, reason, same tier-3+4 gate'],
['ADM-PAY-09','Payments','Cash reconciliation · shift close','V1','GAP','Recep,CM','NEEDS','Counted vs expected, variance, sign-off'],
['ADM-PAY-10','Payments','Payment dispute','V1','GAP','Acct','CONTRACT','Evidence deadline, submission, outcome'],
['ADM-POS-01','POS admin','Products and pricing','V1','GAP','Owner,Inv','CONTRACT','Catalogue, price, tax class, availability per club'],
['ADM-POS-02','POS admin','Inventory and stock','V1','GAP','Inv,CM','CONTRACT','Levels per club, low-stock, adjustments'],
['ADM-POS-03','POS admin','Discounts and promotions','V1','GAP','Owner','CONTRACT','Rules, approval thresholds, expiry'],
['ADM-SCH-01','Scheduling','Class schedule · week grid','V1','DONE','CM','NEEDS','HF Remaining Modules c1'],
['ADM-SCH-02','Scheduling','Class detail and roster','V1','DONE','CM,Coach','NEEDS','V1 Admin Billing c3 · roster, waitlist, cancel path'],
['ADM-SCH-03','Scheduling','Create or edit class','V1','GAP','CM','NEEDS','Recurrence, capacity, room, coach, waitlist policy'],
['ADM-SCH-04','Scheduling','Coach availability','V1','GAP','CM,Coach','CONTRACT','Working hours, exceptions, conflict detection'],
['ADM-SCH-05','Scheduling','PT session scheduling','V1','GAP','CM,Coach','CONTRACT','Coach, member, credit consumption'],
['ADM-SCH-06','Scheduling','Rooms and resources','V1','GAP','CM','CONTRACT','Capacity, double-booking prevention'],
['ADM-SCH-07','Scheduling','Cancel class · notify members','V1','GAP','CM','NEEDS','Message preview, credit or transfer offer'],
['ADM-ACC-01','Access','Access control dashboard','V1','GAP','CM','CONTRACT','Device health, live entries, denials'],
['ADM-ACC-02','Access','Access denial log','V1','GAP','CM,Recep','CONTRACT','Reason, member, resolution'],
['ADM-ACC-03','Access','Member access credentials','V1','GAP','CM','CONTRACT','Card, app, biometric enrolment state'],
['ADM-STF-01','Staff','Staff list','V1','GAP','Owner,CM','CONTRACT','Role, club, status'],
['ADM-STF-02','Staff','Staff profile and permissions','V1','GAP','Owner','NEEDS','Role assignment, club scope, sensitive grants'],
['ADM-STF-03','Staff','Invite staff member','V1','GAP','Owner,CM','CONTRACT','Email, role, scope, expiry'],
['ADM-STF-04','Staff','Roles and permission matrix','V1','GAP','Owner','CONTRACT','The nine roles, editable per tenant'],
['ADM-STF-05','Staff','Commissions','V1.5','V1.5','Owner,Acct','N/A','Deferred — rules vary too widely for V1'],
['ADM-COM-01','Comms','WhatsApp conversation','V1','DONE','Recep,CM','NEEDS','V1 Admin Billing c4 · consent state, 24h window'],
['ADM-COM-02','Comms','Message templates','V1','GAP','Owner,CM','CONTRACT','Approved templates, variables, language pair'],
['ADM-COM-03','Comms','Broadcast · segment and send','V1','GAP','CM','NEEDS','Audience, consent filter, preview, schedule'],
['ADM-COM-04','Comms','Notification settings','V1','GAP','All admin','CONTRACT','Per-event, per-channel, per-role'],
['ADM-TSK-01','Tasks','Task list','V1','GAP','All admin','CONTRACT','Assigned, due, source, bulk complete'],
['ADM-AUT-01','Automation','Automation list','V1','GAP','Owner,CM','CONTRACT','Active rules, run counts, recovered value'],
['ADM-AUT-02','Automation','Automation builder','V1','DONE','Owner,CM','CONTRACT','HF Remaining Modules c5'],
['ADM-AUT-03','Automation','Automation run history','V1','GAP','Owner,CM','CONTRACT','Per-run outcome, failures, retry'],
['ADM-RPT-01','Reports','Reports index','V1','GAP','Owner,CM,Acct','CONTRACT','Available reports by permission'],
['ADM-RPT-02','Reports','Revenue report','V1','GAP','Owner,Acct','NEEDS','Period, club, plan, method breakdown, export'],
['ADM-RPT-03','Reports','Membership report','V1','GAP','Owner,CM','CONTRACT','Joins, leaves, net, cohort retention'],
['ADM-RPT-04','Reports','Attendance report','V1','GAP','CM','CONTRACT','Peak hours, class fill, capacity planning'],
['ADM-RPT-05','Reports','Export · sensitive data gate','V1','GAP','Owner,Acct','CONTRACT','Reason, scope, audit entry, tier-4'],
['ADM-SET-01','Settings','Organization settings','V1','GAP','Owner','CONTRACT','Legal entity, tax number, branding entry'],
['ADM-SET-02','Settings','Location settings','V1','GAP','Owner,CM','CONTRACT','Hours, capacity, address, contact'],
['ADM-SET-03','Settings','Tax and invoicing · JoFotara','V1','DONE','Owner,Acct','NEEDS','V1 Admin Billing c5 · Jordan adapter in a global frame'],
['ADM-SET-04','Settings','Payment providers · CliQ, cards','V1','GAP','Owner','CONTRACT','Connection, test, and the fallback POS-02 offline queue depends on'],
['ADM-SET-05','Settings','Integrations index','V1','GAP','Owner','CONTRACT','Connected, health, disconnect'],
['ADM-SET-06','Settings','White-label branding','V1','GAP','Owner','CONTRACT','Accent, logo, preview, guardrail feedback'],
['ADM-SET-07','Settings','Localization','V1','GAP','Owner','CONTRACT','Language, numerals, date format, currency'],
['ADM-SET-08','Settings','Security and audit log','V1','GAP','Owner','CONTRACT','Sessions, MFA policy, audit trail'],
['ADM-AI-01','AI','AI insight detail · evidence','V1','GAP','Owner,CM','CONTRACT','Full derivation behind a Command Center claim'],
['ADM-AI-02','AI','Ask Veyro · conversational','V1.5','V1.5','Owner,CM','N/A','Deferred — command palette covers V1 queries'],
['ADM-SRCH-01','Search','Command palette · open state','V1','GAP','All admin','NEEDS','Entities, screens, actions, AI query, permission-aware'],
['ADM-AUTH-01','Auth','Admin sign-in','V1','GAP','All','CONTRACT','Email, password, MFA challenge'],
['ADM-AUTH-02','Auth','Sensitive action re-auth','V1','GAP','All admin','CONTRACT','Step-up before tier-4 actions'],
// ── FRONT DESK ─────────────────────────────────────────
['FD-01','Front Desk','Live check-in · peak','V1','DONE','Recep','BUILT','HF Front Desk and POS c1'],
['FD-02','Front Desk','Member lookup · no scan','V1','GAP','Recep','CONTRACT','Name, phone, partial match, photo confirm'],
['FD-03','Front Desk','Access denial · resolution','V1','GAP','Recep','NEEDS','Reason, override authority, manual entry'],
['FD-04','Front Desk','Guest and day pass','V1','GAP','Recep','NEEDS','Details, waiver, payment, temporary credential'],
['FD-05','Front Desk','Walk-in trial signup','V1','GAP','Recep,Sales','NEEDS','Minimal capture, becomes a lead record'],
['FD-06','Front Desk','Class check-in · roster','V1','GAP','Recep','CONTRACT','Booked list, walk-up, waitlist promotion'],
['FD-07','Front Desk','Shift open and close','V1','GAP','Recep','CONTRACT','Float, count, variance, handover'],
['FD-08','Front Desk','Scanner and device state','V1','GAP','Recep','CONTRACT','Disconnected, unrecognised card, fallback'],
['FD-09','Front Desk','Front desk offline · whole surface','V1','GAP','Recep','NEEDS','FOUND IN COMPLETION · cached check-in, queued sales'],
['POS-01','POS','Sale · cart and payment','V1','DONE','Recep','BUILT','HF Front Desk and POS c2'],
['POS-02','POS','Payment · card terminal states','V1','DONE','Recep','NEEDS','V1 Front Desk c1 · six-state machine'],
['POS-03','POS','Split payment','V1','DONE','Recep','NEEDS','V1 Front Desk c2 · running remainder, nothing settles early'],
['POS-04','POS','Membership sale at the desk','V1','GAP','Recep,Sales','NEEDS','Plan, terms, first payment, welcome'],
['POS-05','POS','PT package sale','V1','GAP','Sales,Recep','CONTRACT','Package size, coach, expiry, price'],
['POS-06','POS','Refund at the desk','V1','GAP','Recep,CM','CONTRACT','Manager approval, method, receipt'],
['POS-07','POS','Receipt · print, WhatsApp, email','V1','GAP','Recep','NEEDS','Bilingual receipt, tax fields, JoFotara reference'],
// ── COACH ──────────────────────────────────────────────
['CCH-01','Coach','Today','V1','DONE','Coach','BUILT','HF Coach c1'],
['CCH-02','Coach','Live session · set logger','V1','DONE','Coach','BUILT','HF Coach c2'],
['CCH-03','Coach','Nutrition plan generation','V1','DONE','Coach,Nutr','CONTRACT','HF Coach c3'],
['CCH-04','Coach','Client list','V1','GAP','Coach','CONTRACT','Roster, attention sort, credits remaining'],
['CCH-05','Coach','Client profile','V1','DONE','Coach','NEEDS','V1 Front Desk c3 · programme, last session, limitations'],
['CCH-06','Coach','Session detail · pre-session','V1','GAP','Coach','CONTRACT','Plan for today, last session, flags'],
['CCH-07','Coach','Session complete · summary','V1','GAP','Coach','CONTRACT','Verification, note, credit decrement, next booking'],
['CCH-08','Coach','Programme builder','V1','DONE','Coach','NEEDS','V1 Front Desk c4 · 12 weeks as a pattern, not a sheet'],
['CCH-09','Coach','Exercise picker','V1','GAP','Coach','CONTRACT','Search, muscle group, equipment, substitution'],
['CCH-10','Coach','Workout assignment','V1','GAP','Coach','CONTRACT','To client, schedule, notify'],
['CCH-11','Coach','Client progress and measurements','V1','GAP','Coach','CONTRACT','Weight, measurements, photos, PBs'],
['CCH-12','Coach','Assessment and goals','V1','GAP','Coach','NEEDS','Intake, limitations, goal setting'],
['CCH-13','Coach','Nutrition plan editing','V1','GAP','Coach,Nutr','CONTRACT','Meal swap, macro adjust, day copy'],
['CCH-14','Coach','Nutrition check-in review','V1','GAP','Coach,Nutr','CONTRACT','Adherence, weight trend, plan adjust'],
['CCH-15','Coach','Client messaging','V1','GAP','Coach','NEEDS','Thread, quick replies, media'],
['CCH-16','Coach','Coach schedule','V1','GAP','Coach','CONTRACT','Week view, availability, PT and classes'],
['CCH-17','Coach','Unverified sessions queue','V1','GAP','Coach','CONTRACT','The 22, batch verify, dispute'],
['CCH-18','Coach','Coach profile and settings','V1','GAP','Coach','CONTRACT','Availability defaults, notifications, language'],
['CCH-19','Coach','Sign-in and biometric unlock','V1','GAP','Coach','CONTRACT','Shared-device consideration'],
// ── MEMBER ─────────────────────────────────────────────
['MBR-01','Member','Home','V1','DONE','Member','BUILT','HF Member App c1'],
['MBR-02','Member','Meal swap sheet','V1','DONE','Member','BUILT','HF Member App c2'],
['MBR-03','Member','Class booking list','V1','DONE','Member','CONTRACT','HF Remaining Modules c4'],
['MBR-04','Member','Onboarding · first run','V1','GAP','Member','NEEDS','Goals, preferences, notification consent'],
['MBR-05','Member','Sign-in and account creation','V1','GAP','Member','NEEDS','Phone or email, OTP, link to membership'],
['MBR-06','Member','Workout detail · before starting','V1','GAP','Member','CONTRACT','Exercises, sets, estimated time'],
['MBR-07','Member','Member set logger','V1','DONE','Member','NEEDS','V1 Member c1 · self-guided, dark, offline'],
['MBR-08','Member','Workout complete','V1','GAP','Member','CONTRACT','Summary, PBs, next session'],
['MBR-09','Member','Workout history','V1','GAP','Member','CONTRACT','Past sessions, volume trend'],
['MBR-10','Member','Nutrition · full day','V1','GAP','Member','CONTRACT','All meals, macros, water, notes'],
['MBR-11','Member','Meal detail','V1','GAP','Member','CONTRACT','Ingredients, portions, prep, alternatives'],
['MBR-12','Member','Food search and manual log','V1','GAP','Member','NEEDS','Search, portion, recent, favourites'],
['MBR-13','Member','Barcode scan','V1','GAP','Member','CONTRACT','Camera, match, portion confirm, not-found'],
['MBR-14','Member','Photo meal log','V1','GAP','Member','CONTRACT','Capture, AI estimate, coach review flag'],
['MBR-15','Member','Grocery list','V1','GAP','Member','CONTRACT','Week aggregate, by aisle, check off'],
['MBR-16','Member','Weekly check-in','V1','GAP','Member','NEEDS','Weight, photos, adherence, note to coach'],
['MBR-17','Member','Booking confirmation','V1','GAP','Member','CONTRACT','Time, room, coach, add to calendar, cancel policy'],
['MBR-18','Member','My bookings','V1','GAP','Member','CONTRACT','Upcoming, waitlisted, past, cancel'],
['MBR-19','Member','Waitlist state','V1','GAP','Member','CONTRACT','Position, odds, auto-book consent'],
['MBR-20','Member','Cancel booking','V1','GAP','Member','CONTRACT','Policy window, fee if late, confirm'],
['MBR-21','Member','Book PT with coach','V1','GAP','Member','CONTRACT','Coach availability, credit use, confirm'],
['MBR-22','Member','Progress','V1','GAP','Member','CONTRACT','Weight, measurements, photos, strength'],
['MBR-23','Member','Membership details','V1','DONE','Member','NEEDS','V1 Member c2 · cancel present and plainly worded'],
['MBR-24','Member','Request freeze','V1','GAP','Member','NEEDS','Dates, reason, allowance, what changes'],
['MBR-25','Member','Payment history and receipts','V1','GAP','Member','NEEDS','Invoices, receipts, download, tax fields'],
['MBR-26','Member','Pay outstanding balance','V1','DONE','Member','NEEDS','V1 Member c3 · CliQ first, desk is a real option'],
['MBR-27','Member','Payment methods','V1','GAP','Member','CONTRACT','Add, update, remove, default'],
['MBR-28','Member','Wallet','V1','GAP','Member','CONTRACT','Balance, top-up, history, expiry'],
['MBR-29','Member','QR access pass','V1','GAP','Member','CONTRACT','Rotating code, offline availability, brightness'],
['MBR-30','Member','Coach chat','V1','GAP','Member','NEEDS','Thread, response expectation, media'],
['MBR-31','Member','Notifications','V1','GAP','Member','CONTRACT','List, deep-link targets, mark read'],
['MBR-32','Member','Profile and preferences','V1','GAP','Member','CONTRACT','Details, goals, dietary, language'],
['MBR-33','Member','Security and devices','V1','GAP','Member','CONTRACT','Password, biometric unlock, sessions'],
['MBR-34','Member','Privacy and consent','V1','GAP','Member','NEEDS','Marketing, health data, coach visibility, export'],
['MBR-38','Member','Member app offline','V1','GAP','Member','NEEDS','FOUND IN COMPLETION · basement is the normal case'],
['MBR-35','Member','Shop','V1.5','V1.5','Member','N/A','Deferred — retail is desk-first in V1'],
['MBR-36','Member','Guest passes','V1.5','V1.5','Member','N/A','Deferred to V1.5 with referrals'],
['MBR-37','Member','Achievements','V2','V2','Member','N/A','Deferred — gamification is a V2 decision'],
// ── CONSOLE ────────────────────────────────────────────
['CON-01','Console','Tenant list · live incident','V1','DONE','Support','N/A','HF CRM and Console c2'],
['CON-02','Console','Tenant onboarding checklist','V1','DONE','Support','N/A','HF Remaining Modules c6'],
['CON-03','Console','Tenant detail','V1','GAP','Support','N/A','Config, health, subscription, contacts'],
['CON-04','Console','Tenant provisioning','V1','GAP','Support','N/A','New tenant, plan, region, initial admin'],
['CON-05','Console','Member import · mapping and errors','V1','GAP','Support','N/A','The 27 quarantined rows, resolution UI'],
['CON-06','Console','SaaS subscription and entitlements','V1','GAP','Support','N/A','Plan, seats, clubs, feature entitlement'],
['CON-07','Console','Usage and metering','V1','GAP','Support','N/A','Against plan limits, overage'],
['CON-08','Console','Incident detail','V1','GAP','Support','N/A','Timeline, affected tenants, comms, resolution'],
['CON-09','Console','Safe impersonation · start and audit','V1','DONE','Support','N/A','V1 Console c1 · tier 4, start + persistent session bar'],
['CON-10','Console','Feature flags and rollout','V1','GAP','Support','N/A','Per-tenant, percentage, kill switch'],
['CON-11','Console','System health','V1','GAP','Support','N/A','Services, integrations, queues'],
['CON-12','Console','Audit log','V1','GAP','Support','N/A','Cross-tenant, filterable, exportable'],
['CON-13','Console','Tenant billing and dunning','V1','GAP','Support','N/A','SaaS invoices, failed subscription payments'],
['CON-14','Console','Partner management','ENT','ENT','Support','N/A','Deferred — no partner programme in V1'],
['CON-15','Console','App release management','V1.5','V1.5','Support','N/A','Deferred — manual store releases in V1'],
['CON-16','Console','Console sign-in','V1','GAP','Support','N/A','FOUND IN COMPLETION · staff SSO, mandatory MFA'],
['CON-17','Console','Support ticket context','V1','GAP','Support','N/A','FOUND IN COMPLETION · upstream of impersonation'],
// ── BACKEND-ONLY ───────────────────────────────────────
['SYS-01','System','Payment webhook processing','V1','NO-UI','—','N/A','Surfaces only as payment state on existing screens'],
['SYS-02','System','JoFotara submission queue','V1','NO-UI','—','N/A','Surfaces as invoice state and the CC exception'],
['SYS-03','System','Access controller sync','V1','NO-UI','—','N/A','Surfaces as device health on ADM-ACC-01'],
['SYS-04','System','Nutrition policy evaluation','V1','NO-UI','—','N/A','Routing engine; outcomes appear on CCH-03'],
['SYS-05','System','Churn scoring','V1','NO-UI','—','N/A','Surfaces as attention items, never as a raw score'],
['SYS-06','System','Data retention and deletion jobs','V1','NO-UI','—','N/A','Policy configured in ADM-SET-08'],
['SYS-07','System','Notification delivery and retry','V1','NO-UI','—','N/A','Configured in ADM-COM-04'],
['SYS-08','System','Search indexing','V1','NO-UI','—','N/A','Surfaces as ADM-SRCH-01 results']
];

// A screen already DONE before the completion phase keeps its original file
// reference; re-drawing it later does not "move" it. Counts derive from here.
export const DRAWN = {};
const ALREADY_DONE = new Set(R.filter(r => r[4] === 'DONE').map(r => r[0]));
const mark = (file, ids) => ids.split(/\s+/).filter(Boolean).forEach(id => {
  if (!ALREADY_DONE.has(id)) DRAWN[id] = file;
});

mark('Batch F · Command and CRM', 'ADM-CC-06 ADM-CC-07 ADM-CRM-02 ADM-CRM-03 ADM-CRM-04 ADM-CRM-05 ADM-CRM-06 ADM-CRM-07');
mark('Batch G · Member Record and Lifecycle', 'ADM-MEM-06 ADM-MEM-07 ADM-MEM-08 ADM-MEM-09 ADM-MEM-10 ADM-MEM-11 ADM-MSH-02 ADM-MSH-03 ADM-MSH-04 ADM-MSH-06 ADM-MSH-09');
mark('Batch H · Payments and Retail', 'ADM-PAY-04 ADM-PAY-06 ADM-PAY-07 ADM-PAY-08 ADM-PAY-09 ADM-PAY-10 ADM-POS-01 ADM-POS-02 ADM-POS-03');
mark('Batch I · Scheduling and Access', 'ADM-SCH-03 ADM-SCH-04 ADM-SCH-05 ADM-SCH-06 ADM-SCH-07 ADM-ACC-01 ADM-ACC-02 ADM-ACC-03');
mark('Batch J · Staff and Communication', 'ADM-STF-01 ADM-STF-02 ADM-STF-03 ADM-STF-04 ADM-COM-02 ADM-COM-03 ADM-COM-04 ADM-TSK-01');
mark('Batch K · Automation Reports and AI', 'ADM-AUT-01 ADM-AUT-03 ADM-RPT-01 ADM-RPT-02 ADM-RPT-03 ADM-RPT-04 ADM-RPT-05 ADM-AI-01');
mark('Batch L · Settings Search and Auth', 'ADM-SET-01 ADM-SET-02 ADM-SET-04 ADM-SET-05 ADM-SET-06 ADM-SET-07 ADM-SET-08 ADM-SRCH-01 ADM-AUTH-01 ADM-AUTH-02');
mark('Batch M · Front Desk and POS', 'FD-02 FD-03 FD-04 FD-05 FD-06 FD-07 FD-08 FD-09 POS-04 POS-05 POS-06 POS-07');
mark('Batch N · Coach', 'CCH-04 CCH-05 CCH-06 CCH-07 CCH-08 CCH-09 CCH-10 CCH-11 CCH-12 CCH-13 CCH-14 CCH-15 CCH-16 CCH-17 CCH-18 CCH-19');
mark('Batch O · Member Training and Nutrition', 'MBR-04 MBR-05 MBR-06 MBR-07 MBR-08 MBR-09 MBR-10 MBR-11 MBR-12 MBR-13 MBR-14 MBR-15 MBR-16 MBR-22');
mark('Batch P · Member Booking and Account', 'MBR-17 MBR-18 MBR-19 MBR-20 MBR-21 MBR-24 MBR-25 MBR-27 MBR-28 MBR-29 MBR-30 MBR-31 MBR-32 MBR-33 MBR-34 MBR-38');
mark('Batch Q · Console', 'CON-03 CON-04 CON-05 CON-06 CON-07 CON-08 CON-10 CON-11 CON-12 CON-13 CON-16 CON-17');

export const SURFACE_OF = id => {
  const p = id.split('-')[0];
  if (p === 'ADM') return 'Veyro Admin';
  if (p === 'FD' || p === 'POS') return 'Front Desk & POS';
  if (p === 'CCH') return 'Veyro Coach';
  if (p === 'MBR') return 'Veyro Member';
  if (p === 'CON') return 'Internal Console';
  return 'Backend / no UI';
};

export const SURFACES = ['Veyro Admin', 'Front Desk & POS', 'Veyro Coach', 'Veyro Member', 'Internal Console', 'Backend / no UI'];

// One resolved row per screen: status folded with the DRAWN overlay.
export function resolve() {
  return R.map(r => {
    const drawnIn = DRAWN[r[0]];
    const status = drawnIn ? 'DONE' : r[4];
    const isDefer = ['V1.5', 'V2', 'ENT', 'FUTURE'].includes(status);
    return {
      id: r[0], module: r[1], name: r[2], phase: r[3], status,
      roles: r[5], ar: r[6], note: drawnIn || r[7],
      surface: SURFACE_OF(r[0]),
      isV1: r[3] === 'V1' && !isDefer,
      isDone: status === 'DONE',
      isGap: status === 'GAP',
      isNoUi: status === 'NO-UI',
      isDefer,
      movedThisPhase: !!drawnIn
    };
  });
}
