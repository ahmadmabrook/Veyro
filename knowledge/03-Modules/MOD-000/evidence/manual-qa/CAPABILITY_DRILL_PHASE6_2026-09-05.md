---
doc: CAPABILITY_DRILL_PHASE6_2026-09-05
status: EXECUTED (2026-09-05) — Phase 6, real fresh-context Opus veyro-manual-qa run
date: 2026-09-05
model_attestation: PASS (non-self-report) — see below
---

# Phase 6 — Actual Claude Manual QA (MOD-000)

## Run identity

| Field | Value |
|---|---|
| Role | `veyro-manual-qa`, fresh context, no memory of prior sessions |
| Model, technically attested (not self-report) | `claude-opus-5` — `knowledge/05-QA/tools/mr_verify.py` run against the real subagent transcript (`agent-a2e3b32ad4c5bfe0a.jsonl`), **203 turns, 100% consistent, PASS**. Raw output: `phase6-artifacts/mr_verify_output.json`. This closes the run's own FINDING-P6-05 (self-report only at drill time — the parent session ran the real attestation after the drill completed, once the subagent's own transcript file existed on disk). |
| Required tier | Opus (DC-17: manual QA judgment calls = Opus) — satisfied and technically verified |
| Repo HEAD at drill time | `b4ca8314c048c9580faf47a4f839d070cc5ea1ca`, `git status` clean before and after |
| Host | macOS 26.5.2 (25F84), Xcode simulator runtime iOS 26.4 |

## Scope determination

7 scenarios require actual interactive manual QA per `SCENARIO_CATALOG.md`'s D-2 (§12.1 Manual QA Capability Drill) matrix and their own `Manual-QA requirement: Yes` / `Model: Opus` fields: **SCN-MOD000-039, 040, 041, 042, 043, 044, 061.**

**Scoping judgment made and flagged for the parent to sanity-check, not silently resolved:** the catalog's D-9 banner asserts every Required-category scenario needs eventual Claude manual execution. This drill did **not** treat that as putting all ~95 scenarios in Phase 6's scope — the other Required-category scenarios are control-plane governance checks (hash verification, deny-pattern drills, audits) already executed in Phases 1-5 with their own durable records. Re-running those is not "manual QA of a running surface," which is what Phase 6 specifically unlocks. If a stricter reading is intended, that is an open scope question, not resolved here.

**7 required / 7 executed fresh this run / 0 cited-without-re-execution / 0 skipped.**

## Manual-QA matrix

| Scenario | Surface | Disposition | Method / tool | Bug linkage | Certification impact |
|---|---|---|---|---|---|
| SCN-MOD000-039 | Browser / Web | **PASS** | CAP-005 `mcp__Claude_Browser__*` | — | Satisfied |
| SCN-MOD000-040 | Backend / API | **PASS** (proxy limitation named, not overclaimed) | CAP-004 Bash + `curl` | — | Satisfied for control path; authoritative-store verification deferred to MOD-001 (no real backend/DB/ledger exists yet) |
| SCN-MOD000-041 | Android | **BLOCKED** (correct result — negative/capability-absence scenario) | `adb`/`emulator` direct invocation | — | Carried forward per SCN-062 |
| SCN-MOD000-042 | iOS lifecycle | **PASS** | CAP-006 + `xcrun simctl` | — | Satisfied |
| SCN-MOD000-043 | Accessibility | **BLOCKED — OWNER_ASSISTED REQUIRED** (correct result) | CAP-006 + `simctl spawn launchctl`/`kickstart` + `log stream` | BUG-005 (verdict holds); **BUG-011 filed** (evidence file correction) | Carried forward; underlying evidence corrected |
| SCN-MOD000-044 | Edge / device bridge | **BLOCKED / NOT YET QUALIFIED** (correct result) | Host tooling probe (`command -v`, `/Applications` scan) | — | Carried forward |
| SCN-MOD000-061 | iOS interactive control | **PASS** | CAP-006 | — | Re-confirmed independently; prior 2026-09-04 PASS holds |

**0 FAIL. 0 P0. 0 P1.** Nothing from Phase 6 blocks Phase 7.

## Per-surface detail

### 1. Browser (SCN-039) — PASS

Navigated `https://httpbin.org/forms/post`; before-state screenshot; `read_page` enumerated 13 controls. Filled 7 values across 5 control types with synthetic-only data (`VEYRO-SYNTH-QA-MOD000-PHASE6`, `+000000000000`, `synthetic-fixture@example.invalid`, radio `large`, checkboxes `cheese`+`onion`, time `02:30 PM`, textarea marker `P6-9C4E`). Clicked real Submit. URL transitioned `/forms/post` → `/post`; server echoed every value including both checkbox array elements. Raw response: `phase6-artifacts/api_post_response.json` is the API-drill's version; the browser-drill echo was captured in the subagent's own transcript (not separately saved as a file — the response body is quoted verbatim in the run's report, reproduced below for the record):

```
"form": { "comments": "MOD-000 Phase 6 manual QA browser drill marker P6-9C4E",
  "custemail": "synthetic-fixture@example.invalid", "custname": "VEYRO-SYNTH-QA-MOD000-PHASE6",
  "custtel": "+000000000000", "delivery": "14:30", "size": "large",
  "topping": ["cheese", "onion"] }
```

Deliberately different fixture values from the 2026-09-04 run (large/cheese+onion/14:30 vs medium/bacon+mushroom/13:45) — provably a fresh execution, not a transcription of the prior run.

**Negative controls:** `https://httpbin.org/status/418` rendered the teapot error body; navigation to a deliberately nonexistent host returned an explicit tool error — failure reported, not fabricated or silently swallowed.

### 2. Backend / API (SCN-040) — PASS, proxy limitation explicitly named

`POST https://httpbin.org/post` with JSON body + custom header `X-Veyro-Drill: MOD000-PHASE6-9C4E` → HTTP 200, 0.71s. Raw request/response/headers: `phase6-artifacts/api_post_request.json`, `api_post_response.json`, `api_post_headers.txt`.

**Side-effect verification (the part proving this isn't a pure echo):** `phase6-artifacts/api_cookies_sequence.txt` — baseline `GET /cookies` empty → `GET /cookies/set?...` sets 2 keys → **independent** `GET /cookies` re-read confirms both present → `GET /cookies/delete?...` removes one → **independent** re-read confirms exactly one survived. Selective survival across an independent read is not reproducible by a stateless echo.

**5 distinct negative paths, all loud, none swallowed:** 503 status; 404 unknown path; unreachable host → `curl` exit 28 (DNS timeout); malformed JSON → server-reported `json: null` with raw body preserved; `GET /post` → 405.

**Proxy limitation, explicitly not claimed satisfied:** no Veyro backend/database/event bus/ledger exists before MOD-001. What is proven is the control path (request/response, header propagation, stateful side-effects, negative-path handling against a real HTTP server) — not authoritative Veyro data-store behavior. Must be re-drilled against the real MOD-001 backend.

### 3. iOS Simulator (SCN-042, SCN-061) — PASS

Device iPhone 17 Pro `38391F5D-EFA5-4B36-8F6B-871CE953A525`, 402×874pt. Confined to stock Safari/Calendar per CAP-006's scope caveat — unrelated third-party apps present on the simulator were never touched.

| §12.1 verb | Action | Evidence |
|---|---|---|
| launch (cold) | `terminate` → `launch` | New PID 49447 (was 91572); form state cleared, proving a genuine cold start, not a resume |
| launch (negative) | launch nonexistent bundle id | `FBSOpenApplicationServiceErrorDomain code=4`, exit 4 |
| multi-touch | 4-point two-finger pinch-in | Visible zoom-out, layout reflow |
| tap (in-page) | tap "Onion" checkbox | Rendered checked (blue) |
| text entry | tap field + type | Field focused (blue outline + caret), text visible, keyboard accessory bar present |
| swipe/scroll | drag (200,700)→(200,250) | Unambiguous scroll between form fields |
| deep-link (https) | `open_url https://httpbin.org/forms/post` | Safari navigated, form rendered |
| deep-link (custom) | `calshow://` | Cross-app switch to Calendar app, confirmed via "◀ Safari" back-affordance |
| deep-link (negative) | `veyro://qa/phase6/9C4E` | `LSApplicationWorkspaceErrorDomain code=115`, exit 115 — distinct from the valid exit-0 case |
| background/foreground | HOME then dock tap | **Identical PID 91572** on the earlier-session Safari instance; typed text + focus + zoom state all preserved — genuine resume, not a fresh relaunch mistaken for one |
| permission dialog | Calendar notifications prompt | Driven, chose "Don't Allow" |

**Honest process note preserved from the run:** the first "launch" observed was actually a resume of a process resident since 2026-09-04 (same PID). This was not counted as launch evidence on its own — a deliberate terminate→launch cycle was added, producing a new PID and cleared state, which is what actually demonstrates the launch verb.

**Residual caveat, unchanged from Phase 5:** proven against stock system apps only. No Veyro `.app` build exists yet, so `simctl install` of a real product build and a real `veyro://` scheme remain unexercised — re-drill in MOD-001.

### 4. Android (SCN-041) — BLOCKED, correctly not a fabricated PASS

Re-verified live, not carried forward from a prior claim: `adb` (1.0.41, build 37.0.1-15733141) and `emulator` (37.1.11.0) binaries **are present** and drivable, but not on `PATH`; `ANDROID_HOME`/`ANDROID_SDK_ROOT` unset. `adb devices -l` → empty. `emulator -list-avds` → empty. `~/.android/avd` → empty. `~/Library/Android/sdk/system-images` → does not exist. `sdkmanager` → not found anywhere in the SDK tree.

**Fail-closed proof:** `emulator -avd veyro_synth_nonexistent_avd` → `ERROR | Unknown AVD name` — the tooling itself fails loudly on a bad input, confirming the invocation path is real, not silently no-op'd.

With no bootable AVD or attached device, none of the §12.1 Android pass condition is exercisable. **BLOCKED.** No system image was downloaded — that is a large third-party binary provisioning action, owner territory per DC-16, not a unilateral QA-drill action.

**Owner-assisted fallback, named explicitly:** owner installs `cmdline-tools`, downloads a system image, and creates an AVD (or attaches a physical device / provisions a device farm — the latter likely incurs spend, also owner-reserved). The control binaries being already present narrows what remains.

### 5. Accessibility (SCN-043) — BLOCKED / OWNER_ASSISTED REQUIRED, verdict unchanged, evidence corrected (see BUG-011)

**What this run proved that the 2026-09-04 run did not attempt:** the iOS screen reader genuinely starts and speaks on this simulator when driven correctly. Writing the `VoiceOverTouchEnabled` preference alone does **not** start it (prior finding confirmed correct — PID stays `-`). But `xcrun simctl spawn <udid> launchctl start com.apple.VoiceOverTouch` (and `kickstart -k system/...`) **does**: PID progression 50019 → 50040 → 50376. System-observable confirmation: `VOTIsRunningKey=1`, `AccessibilityEnabled=1`, `ApplicationAccessibilityEnabled=1`. The VoiceOver focus cursor rendered and moved across real UI (modal title → web form label group → "Customer name:" label → page heading). Real speech audio was emitted, evidenced directly from the simulator's own log (`phase6-artifacts/voiceover_full_log.txt`, extract in `VOICEOVER_EVIDENCE_EXTRACT.txt`): `[com.apple.Accessibility:VOTAudio] Trying to speak...`, a CoreAudio AudioQueue at 22050 Hz mono with a `SPEECH` session user, and `VOTWebPageMovement` events confirming active VoiceOver web navigation.

**Why this still correctly stays BLOCKED, not PASS — two specific gaps, neither closed this run:**

1. **No announcement text is capturable.** `ScreenReaderOutput` exposes only `SCROVirtualBrailleDisplay` objects, never an utterance string. All 4 caption-panel preference keys were tried, accepted, and read back as `1`, but no caption panel renders and no audio-capture path exists. What any given element actually announces cannot be verified.
2. **VoiceOver gestures cannot be driven programmatically.** An injected swipe-right is delivered to the app as a raw touch, not interpreted as VoiceOver's "next item" gesture — proven directly: the swipe toggled the page's checkbox instead of advancing screen-reader focus. The accessibility tree cannot be walked by screen-reader semantics from this harness.

Per EIP §12.1 ("no accessibility scenario is marked PASS without actual screen-reader execution evidence" — output capture and gesture-driven navigation both count as part of that evidence, not just process liveness), **BLOCKED — OWNER_ASSISTED REQUIRED** is the correct disposition. Marking PASS on "the process started and spoke something" without being able to verify *what* it said or navigate by its own semantics would repeat the exact class of overclaim BUG-005 already caught once.

**Hygiene, verified:** VoiceOver stopped (PID back to `-`); `VoiceOverTouchEnabled`/`AccessibilityEnabled`/`ApplicationAccessibilityEnabled` reverted to `0`; all 4 caption-panel keys deleted; confirmed by re-read and by a screenshot showing the focus cursor gone. Simulator left as found.

### 6. Edge / device bridge (SCN-044) — BLOCKED / NOT YET QUALIFIED, correct

Exhaustive re-probe using `command -v` (not `which`, which returns exit 0 unconditionally in zsh and would produce a false-positive reading): all 4 Edge channels (stable/Beta/Dev/Canary) absent from `/Applications`; `msedgedriver`, `chromedriver`, `geckodriver`, `browserstack`, `browserstack-local`, `sauce`, `saucectl`, `perfecto`, `appium`, `lambdatest` all absent, no matching global npm packages. Nothing exists to execute access/device-failure/recovery scenarios against. The Claude Browser pane is Chromium-based, not Edge, and viewport resizing is explicitly not accepted as Edge/device evidence per the governing instruction. Provisioning Edge plus a vendor sandbox is new infrastructure; a device farm likely incurs spend — both owner-reserved.

## Restriction compliance

Synthetic fixtures only throughout (`VEYRO-SYNTH-QA-MOD000-PHASE6`, `VEYRO-SYNTH-IOS-P6`, `synthetic-fixture@example.invalid`, `+000000000000`, marker `P6-9C4E`) — no real member data. No spend, no paid service, no billed TestSprite command, no Production action. Targets: public stateless test endpoints (httpbin.org) and a local simulator only. CAP-005/CAP-006 scope caveats respected (no authenticated sessions, no credentials entered, stock Apple apps only, no destructive `simctl` operations). Egress IP redacted from stored artifacts. Every environment setting changed was reverted and independently re-verified. Repo `git status` clean before and after the drill.

## Findings

- **FINDING-P6-01 → filed as BUG-011.** `CAPABILITY_DRILL_PHASE5_RERUN.md` §5's accessibility reasoning was materially incomplete (said the screen reader "never ran"; it does run when driven via `launchctl`/`kickstart`, just can't be made to announce-capturably or gesture-navigate). Verdict unchanged, reasoning corrected — see BUG-011 and the Phase 5 file's own correction.
- **FINDING-P6-02 (P3, confirmed persistent, not new).** `computer:type` still silently fails on `<input type="time">` — already recorded in the Phase 5 file; independently reproduced again this run.
- **FINDING-P6-03 (P3, new harness observation, non-blocking).** iOS Simulator Safari address-bar taps failed to focus across 3 attempts; a subsequent `text` call reported "Typed N characters" with no field focused and no state change — another instance of a tool's own success return not being reliable evidence on its own. Non-blocking (deep-link navigation is the supported, working path); recorded for MOD-001 mobile-web QA awareness.
- **FINDING-P6-04 → catalog correction applied.** `SCENARIO_CATALOG.md`'s D-2 matrix still said iOS interaction was "BLOCKED/NOT YET QUALIFIED" after SCN-061 closed PASS on 2026-09-04. Fixed.
- **FINDING-P6-05 → closed.** Model tier was self-reported at drill time (the parent transcript's sidechain rows for this run had not flushed yet when the drill itself needed to self-describe its tier). Closed after the drill completed: `mr_verify.py` run against the real, complete subagent transcript, PASS, 203 turns, 100% consistent `claude-opus-5`. See "Run identity" above.

## Certification impact

3 of 6 §12.1 surfaces genuinely PASS this run (Browser, Backend/API, iOS) — Browser and Backend/API newly executed this chunk; iOS re-confirmed. The carry-forward BLOCKED set for the eventual Module Approval Certificate under SCN-MOD000-062 is unchanged: **Android, Accessibility, Edge/device** — plus the pre-existing `.claude/rules` auto-load isolation and true-Opus-infrastructure-unavailability items already tracked. This drill is QA evidence only; it does not certify the module (that is the Gatekeeper's role, not run this chunk).
