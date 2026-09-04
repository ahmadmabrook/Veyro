---
doc: MOD-000_MANUAL_QA_CAPABILITY_DRILL_PHASE5_RERUN
status: LIVE
date: 2026-09-04
supersedes_grading_of: manual-qa/CAPABILITY_DRILL.md
run_by: veyro-manual-qa (fresh context, no memory of prior sessions)
model_id: claude-opus-5
remediates: BUG-008 (F5-002, F5-006, F5-007, F5-025)
---

# MOD-000 Manual QA Capability Drill — Phase 5 Re-run

Fresh-context, Opus-tier re-execution of the EIP §12.1 Manual QA Capability Drill.
The original drill (`CAPABILITY_DRILL.md`, 2026-08-31/09-01) is **not overwritten** —
it remains on record. This file re-grades every surface against the EIP's *actual*
§12.1 "Qualification pass condition" column rather than a lower bar.

**Model proof:** this session self-reports model id `claude-opus-5`, satisfying
`DEVELOPMENT_CONSTITUTION.md` §"Model routing" (manual QA = Opus, fresh context,
separate from the implementing session).

## Governing pass conditions (verbatim from EIP §12.1, extracted from the governing baseline .docx)

| Surface | Qualification pass condition (EIP §12.1) |
|---|---|
| Web / Admin / Front Desk | "Claude can navigate, input, submit, inspect visible state and capture evidence on a running QA build." |
| Android | "Claude can install/launch, tap/type/navigate, background/foreground, alter network/permissions and capture state." |
| iOS | "Claude can launch, interact, deep-link, background/foreground and capture state on the qualified iOS path." |
| API / backend | "Real requests and side effects can be observed; no mock-only certification." |
| Edge / device bridge | "Claude can execute access/device failure/recovery scenarios without relying only on code inspection." |
| VoiceOver / TalkBack | "No accessibility scenario is marked PASS without actual screen-reader execution evidence." |

## Fixture / restriction discipline

All data used was synthetic and non-personal (`VEYRO-SYNTH-QA-MOD000`,
`synthetic-fixture@example.invalid`, `+000000000000`, marker `7F3A2B`). No real
member data. No spend. No paid service. No deploy. Targets were public,
stateless test endpoints (`httpbin.org`) and a local iOS Simulator. The one
environment setting this drill changed (simulator `VoiceOverTouchEnabled`) was
reverted at the end and re-verified as reverted. The captured egress IP in the
stored artifact was redacted.

---

## 1. Browser / Web — **PASS**

Control path: `mcp__Claude_Browser__*` (navigate / read_page / computer).
Target: `https://httpbin.org/forms/post` (a public test form built for exactly this).

**Actions actually performed, in order:**

1. **Navigate** — `navigate` to `https://httpbin.org/forms/post`; `navOk: true`.
2. **Inspect before-state** — `read_page` returned all 12 form controls with empty
   values; screenshot captured showing a blank form.
3. **Input** — exercised five distinct control types, not just text:
   - text input `custname` = `VEYRO-SYNTH-QA-MOD000`
   - tel input `custtel` = `+000000000000`
   - email input `custemail` = `synthetic-fixture@example.invalid`
   - radio `size` = `medium` (click)
   - checkboxes `topping` = `bacon` + `mushroom` (two clicks)
   - textarea `comments` = `MOD-000 EIP 12.1 browser drill marker 7F3A2B`
   - time input `delivery` = `01:45 PM`
4. **Submit** — clicked the real `Submit order` button.
5. **Inspect after-state** — URL transitioned `/forms/post` → `/post`;
   `get_page_text` returned the server's parse of the submitted payload.

**Evidence — server-side echo of the submitted form (verbatim from the response):**

```
"form": {
  "comments": "MOD-000 EIP 12.1 browser drill marker 7F3A2B",
  "custemail": "synthetic-fixture@example.invalid",
  "custname": "VEYRO-SYNTH-QA-MOD000",
  "custtel": "+000000000000",
  "delivery": "13:45",
  "size": "medium",
  "topping": ["bacon", "mushroom"]
}
Content-Type: application/x-www-form-urlencoded   Content-Length: 214
X-Amzn-Trace-Id: Root=1-6a9a9d1e-573ae04851275b5c4d123a61
```

All seven submitted values round-tripped correctly, including the multi-valued
checkbox array and the time input normalized to 24h (`13:45`).

**Real defects/limitations found while driving (recorded, not hidden):**

- The `computer:type` action **does not populate an `<input type="time">`**. A click
  plus `type("0145PM")` left the field as `--:-- --`. Discrete `computer:key`
  presses (`1`, `ArrowRight`, `4`, `5`, `p`) *did* work. **Implication for future
  modules:** any time/date-segmented input must be driven with `key`, not `type`.
- `read_page` does **not** report `<textarea>` values (`ref_27` showed no value even
  though the screenshot and the server echo both confirm text was present).
  **Implication:** a11y-tree reads alone are insufficient to verify textarea state;
  screenshot or server-side verification is required.
- `computer:zoom` region-crop is unsupported in this Browser pane (returns the full
  screenshot with an explicit note). Non-blocking.

**Verdict: PASS.** Navigate ✅ input ✅ submit ✅ inspect visible state ✅ capture evidence ✅.

**Honest scope caveat:** the EIP phrase "on a running QA build" is *not* literally
satisfied, because MOD-000 is the control-plane bootstrap and **no Veyro QA build
exists yet**. What is proven is the *control path capability*, which is what §12.1's
drill exists to establish ("MOD-000 must prove the actual Claude manual-QA control
path before any product module enters Ready"). The path must be re-exercised against
the first real QA build in MOD-001.

---

## 2. Backend / API — **PASS (with an explicitly named proxy limitation)**

Control path: `Bash` + `curl`.

### 2a. Real request with a body, echoed exactly

`POST https://httpbin.org/post`, `Content-Type: application/json`, custom header
`X-Veyro-Drill`. Request body sent (stored at
`phase5-rerun-artifacts/api_request_body.json`):

```json
{"drill":"MOD-000-EIP-12.1","surface":"api-backend","marker":"VEYRO-MOD000-API-DRILL-7F3A2B","synthetic":true,"real_member_data":false,"items":[{"id":"SYNTH-001","qty":2},{"id":"SYNTH-002","qty":5}]}
```

HTTP 200. Response (stored at `phase5-rerun-artifacts/api_post_response.json`)
parsed the body into a structured `json` object with all fields and both array
elements intact, and echoed `X-Veyro-Drill`. Trace ID:
`X-Amzn-Trace-Id: Root=1-6a9a9d38-7ee5641f20444357604289cc`.
`PATCH https://httpbin.org/patch` was additionally exercised to prove non-GET verbs
(trace `Root=1-6a9a9d52-5a71bb5d13c3f89e70e9694c`).

### 2b. Genuine state mutation observed **out-of-band** (stronger than echo)

This is the part that distinguishes this re-run from the original drill's read-only
GET. A write was performed by one request and the resulting state was verified by a
**separate, independent subsequent request** — the structural shape of "side effect
observed":

| Step | Request | Observed result |
|---|---|---|
| A | `GET /cookies` (read) | `{"cookies": {}}` — empty baseline |
| B | `GET /cookies/set?veyro_mod000_drill=7F3A2B&veyro_synth_flag=ON` (**write**) | HTTP 302 |
| C | `GET /cookies` (**independent read**) | `{"veyro_mod000_drill": "7F3A2B", "veyro_synth_flag": "ON"}` |
| D | `GET /cookies/delete?veyro_mod000_drill=` (**write/delete**) | HTTP 302 |
| E | `GET /cookies` (**independent read**) | `{"veyro_synth_flag": "ON"}` |

Step E is the strongest single piece of evidence: the delete was **selective** — the
targeted key was removed and its sibling survived — which cannot be produced by a
pure echo and demonstrates a real create → read → selective-delete → re-read
lifecycle with the effect verified by a different call than the one that caused it.

**Verdict: PASS** for "real requests and side effects can be observed; no mock-only
certification." Nothing here was mocked; every call hit a live remote service.

**Explicitly named proxy limitation (this is a proxy, not full satisfaction):**
The EIP's evidence column also asks for "authoritative state/effect evidence" —
i.e. direct read-only verification of an authoritative **DB / event / ledger**.
**That is genuinely not satisfiable in MOD-000, and I am not claiming it is.**
MOD-000 is the control-plane bootstrap; **no Veyro backend, database, event bus,
audit log or ledger exists yet** — those first appear in MOD-001+. What is proven
here is the *control path*: Claude can compose and execute real HTTP requests with
bodies and custom headers, capture request/response/trace-ID evidence, mutate remote
state, and verify that mutation through an independent read. Authoritative
DB/event/ledger verification remains **UNPROVEN and must be re-drilled in MOD-001**
against the first real backend. Certifying financial/entitlement/booking/access
flows (EIP §12: "Claude must verify both user-visible behavior and authoritative
side effects") is **not** unlocked by this result.

---

## 3. iOS Simulator — **PASS (full interactive lifecycle)**

Control path: `mcp__Claude_Code_iOS_Simulator__control` + `xcrun simctl`.
Environment: iPhone 17 Pro, UDID `38391F5D-EFA5-4B36-8F6B-871CE953A525`,
iOS runtime **26.4.1**, host macOS **26.5.2**, **Xcode 26.6**.
Coordinate space 402x874 pt. App under control: Apple stock Safari
(`com.apple.mobilesafari`).

*Scope note:* this simulator also has unrelated third-party apps installed from
another project. None were launched, tapped, or inspected — the drill was
deliberately confined to Apple stock apps.

**Every §12.1 iOS verb was exercised with a screenshot before and after:**

| §12.1 verb | Action performed | Observed result (evidence) |
|---|---|---|
| **launch** | `attach` to booted device; `tap (157, 818)` on the Safari dock icon | Home screen → Safari Start Page. Screenshot pair captured. |
| **interact (tap)** | `tap (358, 111)` on the Start Page card's close control | Card dismissed — discrete control hit, observable state change. |
| **interact (tap)** | `tap (201, 829)` on the address bar | Field focused (caret + clear button appeared). |
| **interact (text)** | `text "httpbin.org/forms/post"` then newline | Text entered, Google-suggestions row appeared, page navigated and rendered the form in mobile Safari. |
| **interact (in-page tap)** | `tap (34, 223)` on the page's "Bacon" checkbox | Checkbox rendered **checked (blue)** — proves interaction with web content, not just chrome. |
| **interact (multi-touch)** | `touch2_path` 4-point two-finger pinch-out | Page zoomed dramatically; content overflowed both axes. |
| **interact (swipe)** | `swipe (201,300) → (201,750)`, 0.4s | View scrolled from the document's end back to the "Moby-Dick" heading — **clear, observable scroll**. |
| **deep-link (https)** | `open_url https://httpbin.org/html` **from the home screen** | OS routed the URL to Safari, foregrounded it, and loaded new content. |
| **deep-link (custom scheme)** | `open_url calshow://` | Routed **cross-app** from Safari to Calendar; status bar showed the `◀ Safari` back-affordance, confirming the originating app and the app switch. |
| **deep-link (negative control)** | `simctl openurl veyro://qa/drill/7F3A2B` | **Correctly failed**: `LSApplicationWorkspaceErrorDomain code=115`, exit **115**. Registered `calshow://` returned exit **0**. |
| **background** | `button HOME` | Home screen shown. `launchctl list` showed Safari **still resident** at PID `91572` (backgrounded, not terminated). |
| **foreground** | dock `tap (157, 818)` | Safari resumed at the **identical PID 91572** with **zoom level and scroll position fully preserved** — a genuine resume, not a cold relaunch. |
| **capture state** | screenshots at every step + `simctl launchctl list` PIDs + runtime/host versions | Captured throughout. |
| **permission dialog** | Calendar raised "Allow Calendar to use your location?"; tapped **Don't Allow** | Dialog driven and dismissed — demonstrates permission-prompt handling (privacy-preserving option chosen). |

**Two honest process notes (recorded rather than smoothed over):**

1. My first swipe attempt (on `httpbin.org/forms/post`) was accepted by the tool but
   produced **no visible scroll**, because that page is shorter than the viewport —
   there was nothing to scroll. I did **not** count that as proof of swipe. I forced
   a genuinely scrollable state via pinch-zoom and re-ran the swipe, which then
   produced an unambiguous, screenshot-verified scroll. A tool call returning
   "success" is not evidence; the observed state change is.
2. One intermediate dock tap landed inside the Calendar app because Calendar had
   been re-foregrounded by my own positive-control `calshow://` call, so the home
   screen was not actually showing. I detected this from the screenshot, and re-ran
   the background/foreground cycle using explicit `simctl launch` + PID comparison so
   the lifecycle claim rests on process-level evidence rather than on my assumption
   about what was on screen.

**Verdict: PASS.** launch ✅ interact (tap/type/swipe/multi-touch) ✅ deep-link
(https + custom scheme + negative control) ✅ background/foreground ✅ capture state ✅.

**→ SCN-MOD000-061 (iOS Simulator interactive control) CAN BE CLOSED as PASS.**
Its pass criteria ("Full interactive lifecycle proven") and its fail-closed
condition ("Any of tap/deep-link/background-foreground failing → BLOCKED") are all
met with per-step evidence. SCN-MOD000-042's narrowed boot/attach/screenshot claim
is now superseded by this fuller result.

**Residual scope caveat:** this proves the control path against a **stock system app**.
No Veyro `.app` exists yet to install/launch, so `simctl install` of a product build
and any `veyro://` deep-link scheme remain unexercised — the negative control above
confirms an unregistered `veyro://` scheme currently and correctly fails, and that
this failure is detectable. Re-drill against the first real Veyro build in MOD-001.

---

## 4. Android — **BLOCKED** (verdict unchanged; underlying evidence materially CORRECTED)

**The original drill's stated evidence was wrong, and this matters.** It recorded
that `which adb` and `which emulator` both report "not found", concluding "no Android
SDK/platform-tools installed on this host." The conclusion (BLOCKED) is right; the
stated reason is **false**, because `which` only checks `$PATH`.

**What is actually on this host (verified this session):**

- `/Applications/Android Studio.app` — **present**
- `~/Library/Android/sdk` — **present** (`build-tools`, `emulator`, `licenses`,
  `platform-tools`, `platforms`, `sources`)
- `adb` — **present and drivable**: `Android Debug Bridge version 1.0.41`
  (`37.0.1-15733141`); daemon started successfully on invocation
- `emulator` — **present and executes**: `Android emulator version 37.1.11.0`
- Neither is on `$PATH`, and `ANDROID_HOME` / `ANDROID_SDK_ROOT` are unset — which
  is the only thing the original `which` check actually detected.

**Why it is nonetheless genuinely BLOCKED — the real limitation:**

- `adb devices -l` → **empty**. No physical device and no emulator attached.
- `emulator -list-avds` → **empty**. `~/.android/avd` contains no AVD.
- `~/Library/Android/sdk/system-images` → **does not exist**. No system image.
- `cmdline-tools` / `sdkmanager` → **not present anywhere in the SDK**, so no
  supported in-session way to fetch a system image.
- Fail-closed proof: `emulator -avd nonexistent_avd` returned
  `ERROR | Unknown AVD name [nonexistent_avd]` — the toolchain fails loudly rather
  than silently pretending to boot.

With no bootable virtual device, **none** of the §12.1 Android pass condition can be
exercised: no install/launch, no tap/type/navigate, no background/foreground, no
network/permission alteration, no state capture. **BLOCKED, not PASS.**

**Owner-assisted fallback (per EIP §12.1):** the owner installs Android
`cmdline-tools`, downloads a system image and creates an AVD (or attaches a physical
device / provisions a device farm), after which this surface can be re-drilled by
Claude directly — note the control binaries are *already* here, so the remaining gap
is narrow. I did **not** attempt the system-image download myself: it is a large
third-party binary download and provisioning action that is owner-approval
territory, not something to do unilaterally inside a QA drill.

---

## 5. Accessibility (VoiceOver / TalkBack) — **BLOCKED — OWNER_ASSISTED REQUIRED** (unchanged; re-tested, not assumed)

Per instruction I did not simply carry the BUG-005 correction forward — I re-tested
whether a real screen-reader execution path exists now.

**What I actually attempted:**

1. Confirmed Xcode's **Accessibility Inspector** *is* installed
   (`/Applications/Xcode.app/Contents/Applications/Accessibility Inspector.app`) —
   but driving it requires macOS GUI automation, which this session has no tool for
   (no computer-use/System-Events control available here).
2. `xcrun simctl help` → **0** subcommands matching "accessib" — no first-class
   simctl accessibility control surface.
3. Read the simulator's accessibility prefs: `AccessibilityEnabled = 0`,
   `ApplicationAccessibilityEnabled = 0`.
4. **Attempted activation:** wrote
   `com.apple.Accessibility VoiceOverTouchEnabled -bool true` into the simulator
   (write succeeded, read back `1`) and posted the cache-invalidation notifications
   `com.apple.accessibility.cache.ax` and `...cache.app.ax`.
5. **Verified the result honestly — it did not work.**
   `launchctl list` showed `com.apple.VoiceOverTouch` with PID **`-`**, i.e.
   registered but **not running**. A follow-up screenshot showed **no VoiceOver focus
   cursor and no caption panel**. The preference flipped; the screen reader never ran.

**Conclusion:** a preference write is not screen-reader execution, and no
announcement or focus evidence could be captured. Marking this PASS would repeat
exactly the overclaim BUG-005 already corrected once. **BLOCKED — OWNER_ASSISTED
REQUIRED**, per EIP §12.1's explicit "No accessibility scenario is marked PASS
without actual screen-reader execution evidence."

**Owner-assisted fallback:** owner (or a human QA pass) runs VoiceOver/TalkBack
manually while Claude directs the exact steps and records Expected vs Actual, tagged
`OWNER_ASSISTED`; or a dedicated accessibility-automation capability is qualified
through `CAPABILITY_POLICY.md` first.

**Hygiene:** `VoiceOverTouchEnabled` was reverted to `0` and re-verified after the
test. The simulator was left as found.

---

## 6. Edge / device bridge — **BLOCKED / NOT YET QUALIFIED** (unchanged; re-tested, not assumed)

Re-checked for any genuinely new capability rather than carrying the prior
correction forward on faith:

- `/Applications/Microsoft Edge.app` → **NOT PRESENT**
- `msedgedriver` → **NOT FOUND**
- `browserstack`, `sauce`, `saucectl` CLIs → **all NOT FOUND**

No Edge instance, no vendor/device sandbox, no device farm. The §12.1 pass condition
requires executing **access / device failure / recovery scenarios** with command,
snapshot-state, access-decision and device-acknowledgement evidence. There is no
device bridge of any kind to execute against, and MOD-000 owns no device/access
domain. The Claude Browser pane is Chromium-based and is **not** Edge; a viewport
resize remains a same-engine proxy and is not offered as evidence.

**BLOCKED / NOT YET QUALIFIED.** Provisioning Edge plus a vendor/device sandbox is
new tooling/infrastructure (and a device farm would likely mean spend →
owner-reserved). Correctly left blocked rather than built ad hoc inside a QA drill.

---

## Summary — graded against the real §12.1 pass conditions

| # | Surface | §12.1 verdict | Basis |
|---|---|---|---|
| 1 | Browser / Web | **PASS** | navigate + input (7 values, 5 control types) + submit + inspect + capture; server echoed all values |
| 2 | Backend / API | **PASS** (proxy limitation named) | real POST/PATCH with bodies + trace IDs; write → **independent read** → selective delete → re-read. Authoritative DB/event/ledger verification **unproven, deferred to MOD-001** |
| 3 | iOS Simulator | **PASS** | launch + tap/type/swipe/pinch + https & custom-scheme deep-link + negative control + background/foreground at stable PID with preserved state |
| 4 | Android | **BLOCKED** | adb/emulator present & drivable, but **no AVD, no system image, no sdkmanager** → no bootable device. Original drill's "no tooling installed" evidence **corrected** |
| 5 | Accessibility | **BLOCKED — OWNER_ASSISTED REQUIRED** | activation attempted and **failed**: `com.apple.VoiceOverTouch` never ran (PID `-`), no announcements/focus captured |
| 6 | Edge / device bridge | **BLOCKED / NOT YET QUALIFIED** | no Edge, no driver, no device farm; nothing to execute failure/recovery against |

**3 of 6 surfaces genuinely PASS** (Browser, Backend/API, iOS) — the same count as
the original drill's corrected summary, but now for the right reasons: each PASS
rests on the EIP's actual pass condition, with the observed state change (not the
tool's success return) as the evidence.

**Scenario dispositions:**

- **SCN-MOD000-039** (Browser) — now genuinely satisfied: input + submit proven, not
  just navigation on a static page. Follow-up "run through the named agent in fresh
  context" is **discharged** by this run.
- **SCN-MOD000-040** (Backend/API) — satisfied for real request/response + observed
  side effect; carry the authoritative-store caveat into MOD-001.
- **SCN-MOD000-041** (Android BLOCKED, negative) — still correctly BLOCKED; its
  supporting evidence text needs updating to the corrected limitation above.
- **SCN-MOD000-042** (iOS boot/attach/screenshot) — superseded by the fuller iOS
  result here.
- **SCN-MOD000-043** (Accessibility BLOCKED, negative) — **holds**, now with
  stronger evidence (an attempted-and-failed activation, not an assumption).
- **SCN-MOD000-044** (Edge BLOCKED, negative) — **holds**, re-verified.
- **SCN-MOD000-061** (iOS interactive control) — **CLOSE as PASS.**
- **SCN-MOD000-062** (certificate carry-forward list) — the carried-forward BLOCKED
  set is now **Android, Accessibility, Edge/device** (iOS interactive control drops
  off), plus the pre-existing `.claude/rules` auto-load isolation and true
  Opus-infra-unavailability items.

**BUG-008:** the three pass-condition shortfalls (F5-007) are remediated for
Browser, Backend/API and iOS. F5-006 (fresh-context Opus named-agent execution) is
satisfied by this run. **F5-002 remains open** and is not mine to close: the Browser
and iOS-Simulator capabilities must be registered in `CAPABILITY_REGISTRY.md` /
`module-capabilities.yaml` before this evidence can be relied on for certification.
I used them because this task directed a real drill; I flag rather than assume that
registration has happened.

**Not certified here.** This file is QA evidence only. Module certification is
`veyro-gatekeeper`'s call, in a separate fresh context.

## Stored artifacts

`knowledge/01-Modules/MOD-000/evidence/manual-qa/phase5-rerun-artifacts/`
- `api_request_body.json` — exact JSON body sent in §2a
- `api_post_response.json` — full echoed response (egress IP redacted)
- `api_post_headers.txt` — response headers incl. trace correlation

Browser and simulator screenshots were captured inline in the session transcript at
every step described above (before-input, filled-form, post-submit response; and the
full iOS step sequence).
