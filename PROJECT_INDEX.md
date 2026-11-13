# Veyro Project Index

Selected working baselines for the clean execution epoch. The Blueprint and the design directory are bound to the bytes of 2026-10-15; the TSD and the EIP are bound to the owner's revisions of 2026-11-13. SHA-256 for the design directory is over sorted relative paths and file bytes, each length-prefixed (4-byte path length, 8-byte content length); `.DS_Store` is excluded.

| Source | SHA-256 |
| --- | --- |
| `Gym_OS_Master_Product_Blueprint_v1_English.docx` | `80f4b381df26919b358b3e64e209c67beba2ba9224c0f4df3951d3b179d426ef` |
| `Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx` | `7eee93b4acb3187ebc4aba8a91bc2649193eda28068ad6d5d9b06f36f4f69b94` |
| `Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx` | `dbbc4faa4a15ae7cd6f5150e1f80652ce8aa1cb631fe653694c0c315ea5cc039` |
| `veyro-product-experience-design/` | `193c2924be4e42d52888b2c50a4609c4514216cfb9648b3f4cb2578112987ffb` |

## Authority and certification

- Blueprint: product scope; TSD v1.4.2: architecture and invariants; UX bundle: applicable interaction contract; EIP v2.0: module execution and lean foundation timing. EIP internal references to v1.4.1/v1.4.0 and the LF-01 “review candidate” notice are legacy text; the selected current documents state owner-approved direction/content release, while independent/runtime certification of these revisions remains pending.
- These hashes identify owner-selected working baselines; they do **not** prove independent certification.
- The TSD and EIP rows were re-pinned on 2026-11-13 to the owner's own revisions of that date, under `knowledge/00-Decisions/OWNER-2026-11-13-full-engineering-delegation.md` §5, which names these two digests as the bytes a re-pin should bind. The revisions were checked structurally — document identity, and survival of the functional content by probe — **not** line by line across 2,566 changed paragraphs, and neither revised document is independently certified. The deletions are process scaffolding; the requirement text the implementation reads is unchanged. `governance/registry.json` `index.sha256` was updated in the same commit, because a pin whose witness disagrees with it is worse than no pin.
- `main` retains staged deletions and untracked files from retirement of the old epoch. Do not restore or import those files. No old runner process or loaded LaunchAgent was observed at bootstrap; two unloaded retired plist files were later found and moved out of `~/Library/LaunchAgents` to `~/.openclaw/retired-veyro-launchagents-2026-10-15/` so a future login cannot revive them.
- Future execution must verify all source hashes before writing to the repository and fail closed on mismatch.
