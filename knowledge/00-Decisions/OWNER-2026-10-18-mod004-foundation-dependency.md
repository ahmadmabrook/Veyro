# Owner decision — MOD-004 prior-module dependency satisfied by FOUNDATION ONLY certificates (publication pending)

**Status: OWNER DECISION recorded on 2026-10-18 (publication pending). It is scoped strictly to the MOD-004 dependency edge on MOD-001 and MOD-002. It is not full product acceptance, not Module Ready, not a Scenario Review PASS and not code authorization.**

## Authority and exact binding

The verified owner answered YES to the decision headed `OWNER DECISION — FOUNDATION CERTIFICATE DEPENDENCY`, in the direct OpenClaw webchat. Inbound context verified requester id `gateway-owner`, display name Ahmad Mabrouk. Source: attached direct-webchat text `pasted-text-1792308187096.txt`, OpenClaw external-content identifier `b16bf3f5bd0183e7`. That identifier is a source identifier, not a chat-message ID.

Owner message ID: OPEN (not exposed; none is invented). The original text is preserved in the conversation.

## Decision

The existing `APPROVED — FOUNDATION ONLY` certificates for MOD-001 and MOD-002 satisfy the prior-module APPROVED dependency requirement of EIP §18 ¶1167 for MOD-004, provided authenticity, scope and continued validity are verified at the time of use.

Pinned EIP evidence is cited from ADR-0002 D12 and the MOD-004 Dependency readiness section. The EIP is not altered.

## Independently verified certificate evidence

Operator-verified with `gh` during the turn that produced this record:

| Module | Certificate | Activation SHA | Foundation CI (exact main push) |
|---|---|---|---|
| MOD-001 | `knowledge/03-Modules/MOD-001/APPROVAL.md` | `8e0f20d493b46a0867b1ddbb464db4ed0caa0972` | run 38883415070, success |
| MOD-002 | `knowledge/03-Modules/MOD-002/APPROVAL.md` | `f9804beb2576c2520d377a27c275f00a4685c47e` | run 38907796747, success |

## What this record does not do

- Scope is only the MOD-004 dependency edge. It does not upgrade either certificate to full product acceptance.
- It does not waive MOD-004 readiness, capability qualification, Scenario Review or security obligations.
- It does not authorize S1 before MOD-004 is READY.
- It does not modify governing product scope or acceptance records.
- It does not bypass review or CI.
- It does not reopen MOD-001 or MOD-002 and does not repair infrastructure.
- It claims no Active capability, no Ready state, no Scenario PASS and no code authorization.
- It grants no reserved action and no path coverage, so it carries no Covers or Actions authority.

## Publication and evidence

Publication or operational use requires independent exact-file review, local first-publication owner attestation, a normal non-force push and CI on the exact pushed head. None of these has been done; none is claimed here.
