---
doc: MOD-000_MANUAL_QA_CAPABILITY_DRILL
status: LIVE
date: 2026-08-31
---

# MOD-000 Manual QA Capability Drill

Real actions taken this chunk, not code inspection. All against synthetic/public targets, no real member data, no spend.

## Browser / Playwright — **PASS**

- Tool/control method: `mcp__Claude_Browser__*` (Claude Browser pane).
- Real action: navigated to `https://example.com`, read page text and accessibility tree.
- Evidence: `navOk: true`; `get_page_text` returned exact page content ("Example Domain..."); `read_page` returned structured a11y roles (`heading`, `generic`, `link` with href).
- Result: **PASS** — real, driveable control path confirmed.

## Backend / API — **PASS**

- Tool/control method: `Bash` + `curl`.
- Real action: `GET https://httpbin.org/get?veyro_mod000=1`.
- Evidence: HTTP 200, response JSON echoed the query param back (`"veyro_mod000": "1"`), captured in session output.
- Result: **PASS** — real HTTP execution + assertion path confirmed.

## Android Emulator / device tooling — **BLOCKED**

- Tool/control method attempted: `adb`, `emulator` (standard Android SDK platform tools).
- Real action: `which adb`, `which emulator`.
- Evidence: both report "not found" — no Android SDK/platform-tools installed on this host.
- Result: **BLOCKED** (not PASS, not guessed). Exact limitation: no Android tooling installed on this machine. **Owner-assisted fallback per EIP**: owner installs Android Studio/platform-tools (or points at a remote device farm) before this path can be qualified, or this surface stays deferred until MOD-001 actually needs Android.

## iOS Simulator / tooling — **PASS**

- Tool/control method: `mcp__Claude_Code_iOS_Simulator__control` + `xcrun simctl` (Bash).
- Real action: `xcrun simctl list devices available` (11+ simulators present, all Shutdown) -> booted iPhone SE 3rd gen (`xcrun simctl boot D676ECAD-...`) -> `control:attach` -> `control:screenshot`.
- Evidence: simulator transitioned Shutdown -> Booted (verified via `simctl list`); panel attached (`Simulator panel opened ... 375x667 points`); real screenshot captured (Apple boot logo, mid-boot).
- Result: **PASS** — real, driveable control path confirmed (boot, attach, screenshot all succeeded).

## Accessibility execution path — **CORRECTED: BLOCKED (was incorrectly PASS)**

**Correction (2026-09-01):** the original entry below counted an accessibility-*tree* read (`read_page`) as accessibility qualification. Per the EIP, that is not sufficient — the required evidence is actual screen-reader execution (VoiceOver on macOS/iOS, TalkBack on Android), not a structured-role dump that merely resembles what a screen reader consumes. This session has no demonstrated control path to actually drive VoiceOver or TalkBack (no dedicated automation tool available; VoiceOver requires macOS Accessibility permissions and either physical interaction or AppleScript/System-Events-level scripting that was not attempted or proven here; TalkBack has the same Android-tooling gap already recorded below).

- Tool/control method attempted: none capable of real screen-reader execution.
- What was actually done (demoted, not deleted): `mcp__Claude_Browser__read_page` accessibility-*tree* read of `example.com` — real, but not screen-reader execution.
- Result: **BLOCKED — OWNER_ASSISTED REQUIRED** per EIP §12.1. Exact limitation: no VoiceOver/TalkBack automation path available to Claude in this environment. Owner-assisted fallback: owner (or a human QA pass) runs VoiceOver/TalkBack manually against a real screen and reports results, or a dedicated accessibility-automation tool is qualified as a new capability before this path can be marked PASS.
- Accessibility-*tree* reads remain useful as a supplementary signal (e.g. for the browser surface) but are recorded as such, not as accessibility qualification.

## Edge / device simulation path — **CORRECTED: BLOCKED/NOT YET QUALIFIED (was incorrectly PASS)**

**Correction (2026-09-01):** the original entry below counted Claude Browser's viewport-*emulation* (resizing the pane's own Chromium-based viewport) as Edge/device qualification. That is not the required evidence — the EIP requires an actual Edge simulator and/or a representative device/vendor sandbox (e.g. a real Microsoft Edge instance, or a BrowserStack/Sauce Labs-style device farm) with command/state/telemetry evidence, not a same-engine viewport resize.

- Tool/control method attempted: none that qualifies (Claude Browser's pane is not Edge; no device/vendor sandbox connected).
- What was actually done (demoted, not deleted): `mcp__Claude_Browser__resize_window` mobile-preset viewport emulation on `example.com` — real, but not an Edge simulator or device sandbox.
- Result: **BLOCKED / NOT YET QUALIFIED**. Exact limitation: no Edge simulator or device/vendor sandbox is available in this environment. Setting one up (installing Edge, provisioning a device-farm account) would likely require new tooling and possibly spend/owner approval — that is itself out of scope for MOD-000 control-plane bootstrap and would edge toward product-implementation-adjacent infrastructure work, so it is correctly left BLOCKED rather than built ad hoc here.

## Summary (corrected)

| Surface | Result |
|---|---|
| Browser/Playwright | PASS |
| Backend/API | PASS |
| Android | **BLOCKED** — no tooling installed, owner-assisted fallback needed |
| iOS Simulator | PASS |
| Accessibility (real screen-reader execution) | **BLOCKED — OWNER_ASSISTED REQUIRED** (corrected from PASS) |
| Edge/device (real Edge/device sandbox) | **BLOCKED / NOT YET QUALIFIED** (corrected from PASS) |

Only 3 of 6 surfaces are genuinely PASS (Browser, Backend/API, iOS Simulator). The other 3 require either owner-assisted execution (Accessibility, Android) or new tooling/infrastructure decisions out of MOD-000's bootstrap scope (Edge/device). No surface above is marked PASS from tool-presence or code inspection alone — every PASS has a captured real action + real evidence, and every corrected BLOCKED reflects an honest re-read against the EIP's actual bar rather than a convenient proxy.
