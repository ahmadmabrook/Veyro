# M1-C-03 R2b-O — Per-screen ownership derivability determination

Status: COMPLETE

- Operation: MOD-001 / M1-C-03, step R2b-O (operation id `45122966-d29f-4c3e-9805-c38a148f4975`)
- Role: veyro-lead (architecture, fresh context). Runtime model id: `claude-opus-5-5`
- Date: 2026-10-13
- Scope: one bounded determination. No code change, no review, no scenario disposition, no MCP use.
- Input context: commit `a3be8bb` (ADR-014 D2 generator) emits 170/170 `OWNER_UNRESOLVED`.

## Question

Can per-screen `owner_domain` (TSD domain code), owning implementation module and wave be
derived deterministically from source artifacts, without invention, for the 170 V1 screens?

## Verdict: NOT_DERIVABLE (for owner_domain, owning module and wave)

Surface is fully derivable (170/170). Owner_domain, owning module and wave resolve for
**0/170** screens from source alone. A single owner decision (table T1 below) is the minimum
needed to unblock gate 5.

## Evidence (precedence order)

### 1. UX bundle (`veyro-product-experience-design/project/`)

- `veyro-registry-data.js:4` says each row has 8 fields `[id, module, name, phase, status, roles, ar, note]`.
  There is no domain field. Line 7 says surface and domain are derived from the id prefix and never stored.
- `veyro-registry-data.js:225-233` `SURFACE_OF` covers surface only: ADM is Admin, FD/POS are Front Desk & POS,
  CCH is Coach, MBR is Member, CON is Console, and anything else is Backend. **This gives surface for 170/170 screens.**
- `Veyro Screen Registry.dc.html:126-142` `DOMAIN_OF` is the only prefix→domain table in the bundle.
  It returns **English UX labels** ('Command Center', 'CRM', 'Members', 'Membership lifecycle',
  'Billing & payments', 'POS & retail', 'Scheduling', 'Access control', 'Staff & permissions',
  'Communication', 'Tasks', 'Automation', 'Analytics & reports', 'Configuration', 'AI', 'Search',
  'Auth & security', 'Front desk ops', 'Coaching & training', 'Member experience', 'SaaS Console').
  It never returns a TSD domain code, and nothing in the bundle maps these labels to TSD codes.
  `veyro-screen.js` has no domain mapping: `grep -i domain` finds 0 hits.
- The registry `phase` field (`veyro-registry-data.js:4`, col 4) is `V1` for all 170 in-scope rows.
  That field is a product phase, not an EIP wave, so it cannot tell Pilot apart from V1 GA.
- Scope check: the registry has 186 rows. 8 are `SYS-*` NO-UI rows (`:194-201`). 8 are deferred:
  ADM-MSH-08, ADM-STF-05, ADM-AI-02, MBR-35, MBR-36, MBR-37, CON-14, CON-15. That leaves **170**, which matches the manifest.

### 2. TSD (`knowledge/00-System/TSD_MIRROR.md`)

- The domain code catalog with names and phases is in Appendix C (`:16615`), rows `:16625-16974`. Examples:
  GRO-01 "CRM, Leads, Sales" (`:16679`), COM-01 Memberships (`:16691`), OPS-04 Front Desk (`:16756`),
  COA-03 Nutrition **V1.5 Growth** (`:16786`), AUT-01 Automation **V1.5 Growth** (`:16830`),
  INT-02 AI **V1.5** (`:16848`), INT-03 Global Search **V1.5** (`:16854`), OPS-05 Staff **V1.5** (`:16762`).
- Aggregate ownership is in §9 (`:2036-2108`). §10 (`:2186`) covers the 57 domains.
- **No TSD line names any canonical Screen ID.** A grep for
  `ADM-*-NN|FD-NN|CCH-NN|MBR-NN|CON-NN` finds 0 hits. TSD also never uses the UX domain labels as keys.

### 3. EIP Appendix F (`knowledge/00-System/EIP_MIRROR.md:17995-19566`)

- The rule (`:18011-18015`) requires mapping to be "generated from source metadata and module/domain ownership".
  The per-module rule (e.g. `:18036-18054`) requires the screen's *source owner_domain* to fall in the
  module's TSD scope, with multi-domain screens resolved to the module owning the primary mutation/route contract.
  The UX source carries no TSD owner_domain, so this rule has no input.
- **Duplicate domain/surface rows across waves** (module | wave | domains). Each pair has identical domains, and the surfaces overlap:
  MOD-017 Pilot / MOD-034 V1 (COM-01, COM-03) `:18328`/`:18694`; MOD-018/035 (COM-04) `:18350`/`:18716`;
  MOD-019/036 (OPS-01) `:18372`/`:18738`; MOD-020/037 (OPS-02) `:18394`/`:18760`;
  MOD-022/038 (OPS-03) `:18439`/`:18783`; MOD-023/044 (COA-01) `:18461`/`:18917`;
  MOD-024/045 (COA-02) `:18482`/`:18938`; MOD-025/046 (COA-04) `:18504`/`:18960`;
  MOD-027/043 (GRO-01, ENG-01) `:18548`/`:18894`; MOD-028/048 (ENG-04) `:18571`/`:19004`;
  MOD-032 Pilot / MOD-057 V1.5 (INT-01) `:18658`/`:19190`; MOD-040 V1 / MOD-051 V1.5 (COM-06) `:18828`/`:19060`;
  MOD-012 Foundation / MOD-063 V2 (ECO-02) `:18218`/`:19316`; MOD-021 Pilot / MOD-064 V2 (ECO-03) `:18417`/`:19339`.
  Neither Appendix F nor the module list (`:3082-3506`, e.g. MOD-017 "Commercial Core" vs MOD-034
  "Commercial Core GA") gives a screen-level rule for choosing Pilot or GA. The gate modules MOD-033 (`:18680`)
  and MOD-049 only say "exact IDs are unioned from owning modules", which is circular.
- **Surface gaps in Appendix F rows:** MOD-041 (COM-05 POS) lists no "POS" surface (`:18849`).
  MOD-058 (INT-02 AI) lists only Internal SaaS Console (`:19212`), but ADM-AI-01 is Admin.
  IAM-03 (authorization) has no UI-bearing module row.

### 4. EIP Appendix B (`EIP_MIRROR.md:11840`) and Blueprint

- These map Blueprint requirements to modules, not screens. A grep for Screen IDs finds 0 hits in
  `EIP_MIRROR.md` and in `veyro-product-experience-design/project/blueprint.md`.

## Resolution counts

| Field | Source-derivable | Rule / source |
|---|---|---|
| surface | 170/170 | `SURFACE_OF`, `veyro-registry-data.js:225-233` |
| UX domain label (not a TSD code) | 170/170 | `DOMAIN_OF`, `Veyro Screen Registry.dc.html:126-142` |
| owner_domain (TSD code) | **0/170** | no label→code or id→code mapping exists in any baseline |
| owning module | **0/170** | depends on owner_domain |
| wave | **0/170** | registry phase is uniformly V1; Pilot/GA duplicates have no tie-break |

## Residue: all 170 screens, grouped by prefix

The UX label groups split as follows.

**Group A: name match to one TSD domain, and one Appendix F module that lists the surface. 31 screens.**
These are the easiest for the owner to ratify:
- ADM-MEM ×11 → PPL-01 → MOD-014
- ADM-SET ×8 → PLT-02 → MOD-005
- ADM-AUTH ×2 → IAM-01 → MOD-007
- ADM-TSK ×1 → AUT-02 → MOD-026
- FD ×9 → OPS-04 → MOD-042 (Front Desk listed)

Strictly, even these are label→code inferences and are not stated in source.

**Group B: name match to one TSD domain, but the domain sits in a Pilot/V1 GA duplicate pair. 35 screens.**
- ADM-CRM ×7 → GRO-01 → MOD-027 or MOD-043
- ADM-MSH ×8 → COM-01 → MOD-017 or MOD-034
- ADM-PAY ×10 → COM-03 → MOD-017 or MOD-034
- ADM-SCH ×7 → OPS-01 → MOD-019 or MOD-036
- ADM-ACC ×3 → OPS-03 → MOD-022 or MOD-038

**Group C: label is ambiguous across domains, or the domain/module wave conflicts with the registry's V1. 104 screens.**
- ADM-CC ×7: INT-01, AUT-02 or PLT? No "Command Center" domain exists.
- ADM-COM ×4: ENG-01 or ENG-02.
- ADM-RPT ×5: INT-01, but MOD-032 is Pilot and MOD-057 is V1.5.
- ADM-AUT ×3: AUT-01 is V1.5 in both TSD and EIP, but the registry says V1.
- ADM-AI ×1: INT-02 is V1.5, and the only module (MOD-058) has no Admin surface.
- ADM-SRCH ×1: INT-03 is V1.5 (MOD-059).
- ADM-STF ×4: OPS-05 is V1.5 (MOD-052), or IAM-03, which has no UI module.
- ADM-POS ×3 and POS ×7: COM-05 (MOD-041 has no POS surface) or COM-06 (MOD-040).
- CCH ×19: spans COA-01, 02, 03, 04, OPS-01, ENG-01 and IAM-01. No single domain applies.
- MBR ×35: spans ENG-04, OPS-02, OPS-03, COM-01, 03, 04, COA-02, 03, 04, COA-05/SEC-01, IAM-01 and ENG-02.
- CON ×15: spans PLT-01, PLT-03, PLT-04, LIF-02, LIF-01, PLT-02, REL-02, DAT-01/GOV-01 and IAM-01.

Total: 31 + 35 + 104 = 170.

Nutrition is a specific wave conflict. CCH-03, CCH-13, CCH-14, MBR-02 and MBR-10…MBR-15 (10 screens) are V1 in
the registry, but COA-03 is V1.5 Growth (TSD `:16786`) and its only module, MOD-053, is V1.5 (EIP `:19103`).
The same conflict applies to ADM-AUT, ADM-AI, ADM-SRCH and ADM-STF.

## Single minimum owner decision

**Decision OD-R2BO: approve an ownership table T1 as a new source artifact.**

T1 is keyed by screen-ID prefix group, with per-screen rows only for CCH, MBR and CON. It carries:
- `owner_domain` (TSD code)
- `owning_module`
- `wave`
- one global duplicate-wave rule

Recommended home: `contracts/ui/screen-ownership.yaml`, cited by ADR-014. The generator then joins it
deterministically and fails closed on any unmapped ID.

T1 needs these owner choices:

1. **Duplicate-wave rule (one line).** Proposed: the owning module is the **earliest-wave module** whose
   Appendix F row lists the domain and surface (Pilot for MOD-017/018/019/020/022/023/024/025/027/028).
   The GA twin (MOD-034…048) is recorded as a secondary traceability link. The alternative is "GA module owns".
2. **V1.5-domain conflict.** Choose one:
   (a) the screen keeps V1, is owned by the nearest V1-wave module, and the V1.5 domain is secondary; or
   (b) the screen is reclassified to V1.5. That changes the 170 count, so it is a scope change.
   This applies to the 10 nutrition screens plus ADM-AUT ×3, ADM-AI-01, ADM-SRCH-01 and ADM-STF ×4.
3. **Smallest concrete table to approve.** These are proposals, not derivations. The basis for each is a TSD Appendix C name line.

| Prefix group | n | owner_domain (TSD App C line) | owning module (rule 1 applied) |
|---|---|---|---|
| ADM-MEM | 11 | PPL-01 (:16667) | MOD-014 |
| ADM-SET | 8 | PLT-02 (:16631) | MOD-005 |
| ADM-AUTH | 2 | IAM-01 (:16648) | MOD-007 |
| ADM-TSK | 1 | AUT-02 (:16836) | MOD-026 |
| FD | 9 | OPS-04 (:16756) | MOD-042 |
| ADM-CRM | 7 | GRO-01 (:16679) | MOD-027 |
| ADM-MSH | 8 | COM-01 (:16691) | MOD-017 |
| ADM-PAY | 10 | COM-03 (:16714) | MOD-017 |
| ADM-SCH | 7 | OPS-01 (:16738) | MOD-019 |
| ADM-ACC | 3 | OPS-03 (:16750) | MOD-022 |
| ADM-COM | 4 | ENG-01 (:16805) | MOD-027 |
| ADM-CC | 7 | INT-01 (:16842) — owner choice | MOD-032 |
| ADM-RPT | 5 | INT-01 (:16842) | MOD-032 |
| ADM-POS, POS | 3+7 | COM-05 (:16726) | MOD-041 (needs POS surface added to its row) |
| ADM-AUT / ADM-AI / ADM-SRCH / ADM-STF | 3/1/1/4 | AUT-01 / INT-02 / INT-03 / OPS-05 | per decision 2 |
| CCH-01..19 | 19 | per screen: sessions/today → COA-01; programme/workout → COA-02; assessment/progress → COA-04; nutrition → COA-03; messaging → ENG-01; schedule → OPS-01; sign-in → IAM-01 | per rule 1 |
| MBR-01..34, 38 | 35 | per screen: workout → COA-02; nutrition → COA-03; progress → COA-04; booking → OPS-02; QR access → OPS-03; membership/freeze → COM-01; payments → COM-03; wallet → COM-04; chat → ENG-01; notifications → ENG-02; consent → COA-05; sign-in/security → IAM-01; home/onboarding/profile/offline → ENG-04 | per rule 1 |
| CON-01..13, 16, 17 | 15 | per screen: tenant list/detail → PLT-04; provisioning → PLT-01; onboarding → LIF-01; import → LIF-02; subscription/metering/tenant billing → PLT-03; flags → PLT-02; health/incident → REL-02; impersonation/support → PLT-04; audit log → GOV-01 (MOD-001); sign-in → IAM-01 | per rule 1 |

Until OD-R2BO is approved, the generator must keep emitting `OWNER_UNRESOLVED`. That is the correct
fail-closed behavior and matches EIP `:18011-18015`, which forbids invented values. A Sonnet implementer
can code the join as soon as T1 exists. No further architecture judgment is needed beyond rules 1 and 2.
