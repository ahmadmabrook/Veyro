# Veyro Project Index

Selected working baselines for the clean execution epoch, bound to the current bytes on 2026-10-15. SHA-256 for the design directory is over sorted relative paths and file bytes, each length-prefixed (4-byte path length, 8-byte content length); `.DS_Store` is excluded.

| Source | SHA-256 |
| --- | --- |
| `Gym_OS_Master_Product_Blueprint_v1_English.docx` | `80f4b381df26919b358b3e64e209c67beba2ba9224c0f4df3951d3b179d426ef` |
| `Veyro_Technical_System_Design_v1.4.2_Foundation_Clarification.docx` | `e0bef7cf2c42885fa35825343ff9b18bbf8fe4996ea72ac38a594752a8c69d33` |
| `Veyro_Engineering_Implementation_Plan_v2.0_Lean_Foundation.docx` | `b82e56f88a3b5cc5ba486fe8d10b2d04e8153ce227729e9ba6a92debe15d894f` |
| `veyro-product-experience-design/` | `193c2924be4e42d52888b2c50a4609c4514216cfb9648b3f4cb2578112987ffb` |

## Authority and certification

- Blueprint: product scope; TSD v1.4.2: architecture and invariants; UX bundle: applicable interaction contract; EIP v2.0: module execution and lean foundation timing. EIP internal references to v1.4.1/v1.4.0 and the LF-01 “review candidate” notice are legacy text; the selected current documents state owner-approved direction/content release, while independent/runtime certification of these revisions remains pending.
- These hashes identify owner-selected working baselines; they do **not** prove independent certification.
- `main` retains staged deletions and untracked files from retirement of the old epoch. Do not restore or import those files. No old runner process or loaded LaunchAgent was observed at bootstrap; two unloaded retired plist files were later found and moved out of `~/Library/LaunchAgents` to `~/.openclaw/retired-veyro-launchagents-2026-10-15/` so a future login cannot revive them.
- Future execution must verify all source hashes before writing to the repository and fail closed on mismatch.
