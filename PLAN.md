# PhoneCert — Milestone Plan

Rhythm: ~5–8 h/week (evenings/weekends). Total ≈ 8–10 weeks to a usable v1.

---

## M0 — Setup & first connection (Week 1) ✅
**Goal:** the Mac talks to an iPhone.
- [x] Project scaffold, pyproject, setup.sh, `phonecert scan` CLI
- [x] Run `./setup.sh` on the Mac (venv + pymobiledevice3 + git init)
- [ ] Git repo + GitHub (private)
- [x] Plug an iPhone, run `phonecert scan` (iPhone 13, 10 Nov 2026)
- [ ] Have 2–3 test iPhones available (yours, spouse's, an old one)
**Done when:** device info prints in the terminal.

## M1 — Data reading CLI (Week 2)
**Goal:** `phonecert scan` outputs a JSON of the device.
- [x] Device module: model name, model number, region, serial, IMEI, iOS
- [x] Storage used / total (`lockdown get com.apple.disk_usage`)
- [x] Battery module: design/max capacity, cycles, charge, temperature (if exposed), battery serial, health %
- [x] Health grade: Excellent / Good (90–99) / Average (80–89) / Poor (<80)
- [x] System: jailbreak hints (installed apps + crash names), panic log count (`crash ls`)
- [x] Validate storage / panic / jailbreak output on a real phone (iPhone 13, 10 Nov 2026)
- [x] Same on the iPhone 16 Pro (iOS 27, 10 Nov 2026)
- [x] Save scan to `reports/<serial>_<date>.json` (incl. raw data)
**Done when:** numbers match iMazing on 3 phones.

## M2 — Parts & authenticity (Weeks 3–4) ⚠️ hardest
**Goal:** flag replaced or non-genuine parts.
- [x] Research what pymobiledevice3 exposes (`scripts/m2_dump.sh`, 10 Nov 2026 on iPhone 13)
- [x] Battery authentication (AppleAuthCPRelay: AuthPassed / isTrusted) — replaces "serial vs paired serial"
- [x] Component serials: display Panel_ID, 4 camera modules + Face ID projector, Taptic, NAND, MLB
- [x] Face ID self test, speaker amp attached/calibrated
- [ ] Run parts scan on the iPhone 16 Pro (iOS 27) — class names differ (AppleH16CamIn?)
- [ ] Understand camera validation statuses (iPhone 13 shows FCClValidationStatus "Invalid" — normal?)
- [ ] Refurb detection from model number (M = new, F = Apple refurb, N = replacement, P = personalised)
- [x] Battery age score: operating hours vs board build date (normal / clarify / unknown)
- [x] Component build dates vs board date (display, cameras, Taptic) → consistent / check
- [ ] Positive test: scan a phone with a known replaced screen or battery and confirm the flags fire
- [x] Manual step: read *Settings → About → Parts and Service History* (iPhone 13: no repairs, 10 Nov 2026)
- [ ] Compare results with 3uTools Verification Report
**Done when:** a phone with a known replaced part is flagged correctly.

## M3 — Grading & PDF report (Week 5)
**Goal:** a professional certificate for buyers.
- [ ] Scoring rules → grade A / B / C
- [ ] HTML template → PDF (Playwright `page.pdf()`)
- [ ] QR code + unique report ID
**Done when:** a 1-page PDF is generated from a scan.

## M4 — Lock & blacklist checks (Week 6)
**Goal:** never buy a locked or stolen phone.
- [x] On-device: Find My / Activation Lock (`com.apple.fmip IsAssociated`), supervision, MDM profiles,
      set-up state → Trust tab with verdict blocked / warnings / incomplete / clear (10 Nov 2026)
- [x] Choose an IMEI API provider: imei.info (real sign-up, from 0.02 USD) with sickw.com as alternative — 10 Nov 2026
- [x] Find My (device-side), carrier lock + blacklist (provider), trust checks wired
- [x] API key in `.env`, results cached 7 days (reports/imei_cache.json)
- [ ] Register at dash.imei.info, fund 5 USD, key → `.env`, `phonecert imei --services apple`, pick a service id,
      set PHONECERT_IMEIINFO_SERVICE, run `phonecert imei <IMEI>` once
- [ ] Inspect `imei_check.raw` from the first real answer and tighten `normalise()`
- [ ] Warranty / coverage (service 152, 0.03 USD) — later
**Done when:** status shows in JSON + PDF.

## M5 — Functional tests (Week 7)
**Goal:** test hardware without installing anything on the iPhone.
- [x] Passive presence check of 22 drivers (sensors, radios, NFC, port, audio) from the IORegistry tree (11 Nov 2026)
- [x] Web page in `web-tests/` served by `phonecert serve`, opened via QR code (or Safari Remote Automation with --open)
- [x] Tests: touch grid, multi-touch, solid colours, speaker tone (L/R), haptics prompt. Camera / mic / motion
      need HTTPS on iOS → manual checklist instead
- [x] Results POSTed to the local server → stored in the report (`tests.web`), app polls and shows them
- [x] Manual checklist (buttons, Face ID, cameras, charging, cellular, Wi-Fi/BT, mic, liquid indicator, body) in the app
- [x] More tests (11 Nov 2026): charging + touch-controller auto checks, ghost touch, touch sampling rate,
      speaker sweep, grey/gradient screens, Wi-Fi throughput, battery under load (USB sampling), HTTPS page
      with camera / mic / motion / GPS, checklist incl. True Tone, earpiece, NFC
- [x] Tests without the cable: tests-only report created on the spot (11 Nov 2026)
- [ ] Run the full flow on the iPhone 13 over Wi-Fi (verified so far in a desktop browser only)
- [ ] Merge a tests-only report into a later cable scan of the same phone
- [ ] Verify Safari treats the accepted self-signed HTTPS page as a secure context (camera test)
- [ ] Later: storage write-speed via AFC (needs a delete path), live syslog watch during tests port
**Done when:** a full test run takes < 5 minutes.

## M6 — Desktop app UI (Weeks 8–9)
**Goal:** one-click experience.
- [x] Pick UI: Tauri 2 + React/TypeScript, Rust shells out to the Python CLI (10 Nov 2026)
- [x] Screens: Connect → Scan → Report → History (Tests screen comes with M5)
- [ ] First run of `pnpm tauri dev` on the Mac with a phone plugged in
- [ ] Bundle the Python core as a sidecar so the .app works without the repo's .venv
- [ ] History of scanned phones (SQLite)
**Done when:** a non-technical person can run a full diagnostic.

## M7 — Pilot on real deals (Week 10)
**Goal:** prove it on the market.
- [ ] Check 10+ phones (buys or friends' phones)
- [ ] Log mismatches vs. 3uTools / Phonecheck → fix
- [ ] Attach PDF to resale listings, measure buyer reaction / price
**Done when:** you trust the tool to decide a purchase.

---

## Later (v2 ideas)
- Windows build
- Sell the tool / reports to other resellers
- iPad & Apple Watch support
