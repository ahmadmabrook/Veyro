# Owner decision — full engineering delegation and product-first execution

- Covers: Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx, Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx, PROJECT_INDEX.md

**Effective on publication.** No independent review, no first-publication attestation and no
exact-SHA CI run gates this record, because the owner's instruction below removes those
requirements for ordinary engineering records. That is a delegation the owner made, not a check
this session skipped, and it is stated plainly rather than quietly.

## 1. Source

The owner pasted the instruction below into the Claude Code session on 2026-11-13. It is
reproduced because this record's authority is the instruction, and a reader must be able to judge
the instruction rather than this session's summary of it.

**No chat message ID is given, and none is invented.** The prior
`check_first_publication` lane required an attestation JSON carrying the owner's own
`owner_choice_quote` and `source_prompt_message_id`, written under admin authentication to a file
owned by uid 0. That lane was **not** used and no such file was produced. It is removed by §3
rather than satisfied, because the owner instructed that routine engineering decisions no longer
need their approval and that obsolete approval gates be eliminated. An agent could not have
completed that lane honestly in any case, which is exactly why it stood unfinished.

Quoted from the instruction:

> I am transferring full operational and engineering decision-making authority for Veyro to
> Claude Code. [...] You have my standing authorization to make and execute all ordinary project,
> product-development, architecture, implementation, testing, infrastructure, documentation, and
> repository decisions.

> You may modify, replace, reorganize, or delete any Veyro project file as needed, including
> previously owner-edited files, CLAUDE.md, agent instructions, ADRs, governance records,
> capability manifests, validators, CI workflows, and both DOCX baseline documents.

> Where existing project rules reserve routine engineering decisions to the owner, treat this
> instruction as my explicit decision to delegate those decisions to you.

> This delegation is intended to be broad and continuing. It does not permit falsifying identity
> or approval evidence, bypassing externally enforced access controls, or assuming access to
> resources you do not have.

> Your overriding engineering objective is to deliver a complete, functional, tested Veyro
> product. Preserve all actual functional requirements, product behavior, technical contracts,
> tenant isolation, security, financial correctness, and meaningful tests. Remove administrative
> and procedural constraints that unnecessarily delay implementation.

> For genuinely irreversible external actions, real financial expenditure, production deployment,
> or actions requiring personal authentication, do not fabricate authorization or bypass access
> controls.

## 2. What is delegated

Every ordinary engineering decision: product implementation, architecture, schema and migration
design, dependency selection, test strategy, local and CI infrastructure, documentation, module
sequencing, and repository organisation. These are made by the session and are not brought to the
owner. Module implementation is no longer gated on another module's acceptance.

## 3. What is removed

Prospectively, and without reinterpreting any historical outcome:

- **Module locks.** MOD-004 through MOD-074 may be implemented and tested locally now. Acceptance
  and release remain separate judgments; local implementation is not one of them.
- **The capability-manifest gate.** `contracts/engineering/module-capabilities.yaml` being
  PROVISIONAL with `gate_eligible: false` no longer blocks product code, and neither do
  `BLK-CAP-POSTGRES17-PSYCOPG-POOL-RUNTIME`, `BLK-SKL-MIGRATION-LINT`, `BLK-RULE-QUALIFICATION`
  or `BLK-CON04-PRIVILEGED-CONSOLE-REVIEW`. PostgreSQL and `psycopg` are ordinary development
  dependencies and are declared in `backend/requirements.txt`.
- **The S0-only scope limits**, the consumed one-write and one-review limits, the CAP envelope and
  its exhausted counters, the external-candidate and custom-Rule caps, and the D16 attempt
  counter. They described a budget regime the owner has ended.
- **The first-publication attestation lane** and the requirement of independent exact-diff review
  before publishing an ordinary change. Review is applied where risk warrants it — see §4 — not as
  a uniform ceremony.
- **The pending owner questions that blocked implementation** (OWNER-Q1, OWNER-Q2, OWNER-Q3 and
  the D15.10 items). Where a design answer is needed, the session decides it and records the
  decision with the code.

Superseded before it took effect: `OWNER-2026-11-11-baseline-product-first-adoption.md`, which
set out a two-commit adoption of the same baselines under the attestation lane. It is kept
unchanged as a record of the owner's intent on that date; its hash table is stale, because both
documents were edited again afterwards, and §5 pins what is actually on disk.

## 4. What is preserved

Not negotiable, and not loosened by anything above:

- **Tenant isolation and row-level security**, authentication and AAL-3, immutable audit,
  financial correctness, residency and retention. These are product requirements, not process.
- **Negative tests must actually fail closed.** A test that passes when the protection is removed
  is not evidence. New isolation work carries mutation evidence that the test detects its own
  regression.
- **Recorded history is never rewritten.** Every prior `CHANGES_REQUESTED` outcome, the exhausted
  envelope counters and the D16 lineage stand as recorded. Nothing here retroactively authorizes
  anything published before it.
- **Owner-reserved, on the owner's standing instruction**: real financial expenditure, production
  deployment, real member data, and any action requiring the owner's personal authentication.
  `governance/registry.json` `reserved_actions` is unchanged and keeps the four names, even though
  the revised EIP no longer enumerates them.
- **Preserved evidence trees** outside the repository stay read-only and byte-for-byte intact.

## 5. Baselines: authorized, not yet adopted

The owner edited both documents in the working tree. This record is the authority to re-pin them
in `PROJECT_INDEX.md`, and `Covers` names the three paths for that purpose.

**The re-pin was not performed.** The session's own oversight classifier declined the edit, on the
reading that rewriting frozen baseline digests and `governance/registry.json`'s `index.sha256` is
the shape of an action that defeats a tamper-detection control. That reading is right about the
shape, and the edit is left for the owner to allow rather than routed around. Nothing baseline-
related is committed: `PROJECT_INDEX.md`, `governance/registry.json` and both `.docx` stay exactly
as they were, so the published state remains internally consistent and
`governance_check.py check --root .` returns PASS. The owner's document edits remain as
uncommitted working-tree changes until then.

**What was measured, and what was not.** The revisions were diffed against the committed bytes by
extracting both documents' paragraphs. The EIP changed in 468 hunks and lost about 1,785
paragraphs (71% of its text retained); the TSD changed in 15 hunks (96% retained). The deletions
are process scaffolding -- Document Control blocks, the Development Constitution table, the
release-gate sequence table, the DC-16 apparatus (`DC-16` 222 -> 27 occurrences,
`real-member-data` 76 -> 0). Functional content was checked by probe and survives: in the TSD
`PLT-01` 95 -> 95, the PLT-01-R01, R02 and R03 requirement sentences present and unchanged,
`RLS` 32 -> 30, AAL-3, immutable audit and the hard-deletion bar all still present; in the EIP
`PLT-01` 44 -> 44 with Appendix B's Critical rows substantially intact.

That is a structural check of identity and survival, **not** a line-by-line review of 2,566
changed paragraphs, and this record does not claim one. When the re-pin is made, these are the
bytes it should bind:

| Path | SHA-256 on disk, 2026-11-13 |
|---|---|
| `Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx` | `dbbc4faa4a15ae7cd6f5150e1f80652ce8aa1cb631fe653694c0c315ea5cc039` |
| `Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx` | `7eee93b4acb3187ebc4aba8a91bc2649193eda28068ad6d5d9b06f36f4f69b94` |

`Gym_OS_Master_Product_Blueprint_v1_English.docx` and `veyro-product-experience-design/` are
unchanged and keep their existing pins. Neither revised document is independently certified, and
both keep their own sentence saying the v1.4.1 audit results do not certify the revision.

## 6. Work published under this record

The MOD-004 control plane, in `backend/`: the `plt01_platform` and `plt01` schemas with
row-level security forced on every tenant table, the tenant lifecycle and its append-only
history, the organization hierarchy, the HTTP surface over both planes, and a tenant-isolation
suite whose every check was shown to fail when its protection is removed. `CLAUDE.md` is rewritten
to match.
