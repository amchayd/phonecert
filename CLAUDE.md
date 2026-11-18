# PhoneCert — context for Claude Code

## What this is
Desktop diagnostic tool for **used iPhones**, built to support a used-iPhone
reselling side business. Goal: before buying/reselling, check battery health,
parts originality, authenticity, lock status and functional tests, then
produce a PDF certificate for buyers. Owner is a QA engineer
(Playwright/TypeScript background) — keep things testable.

Full roadmap with milestones and checkboxes: **PLAN.md** (keep it updated
when a task is done).

## Key decisions
- **CLI first** (`phonecert scan`); the desktop UI (M6, `desktop/`, Tauri 2 + React/TS) only
  shells out to `phonecert <cmd> --json` from Rust, so both share one core. UI was pulled
  before the PDF (M3) on the owner's request.
- **Nothing installed on the iPhone**: USB + unlock + "Trust This Computer".
- Python 3.10+, **pymobiledevice3 called via its CLI** (JSON output) in
  `src/phonecert/device/reader.py` — deliberately not its Python API,
  which changes between versions.
- Every scan saves a JSON in `reports/` including a `raw` section
  (lockdown + battery) — inspect it when adding new fields.

## Layout
```
src/phonecert/
  cli.py              # entry point: argument parsing + printing only; one cmd_<name>(args) per command
  scan.py             # scan(): read the device, run the analysers, assemble + save the report; build_trust(), devices()
  settings.py         # app settings = the IMEI provider lines of .env: read() (keys masked), write(), check() (free balance call)
  report/store.py     # the reports/ folder: load/save, save_scan, new_tests_only_report, record_test,
                      #   list_reports, delete_reports (→ macOS Trash; imei_cache.json is never touched)
  report/text.py      # print_summary(): a report as terminal text, one function per section
  device/reader.py    # pymobiledevice3 CLI wrapper (lockdown info/get, diagnostics battery, crash ls, apps list)
  device/safari.py    # open_in_safari(url): the one place using the pymobiledevice3 Python API
  device/models.py    # ProductType -> commercial name (iPhone17,1 = iPhone 16 Pro)
  battery/health.py   # health %, grade, nested-key search (_find)
  system/storage.py   # used/total from lockdown domain com.apple.disk_usage
  system/panics.py    # kernel panic count + risk from `crash ls` file names
  system/jailbreak.py # hints: known bundle ids, dev-signed apps, jailbreak daemons in crash names
  system/sim.py       # SIM status, tray, carrier bundle, eSIM, baseband (ICCID/IMSI stay in raw only)
  system/profiles.py  # configuration profiles / MDM from `profile list`
  system/trust.py     # buyer deal-breakers, one small function per check (Find My, blacklist, supervision, MDM…)
  checks/imei.py      # M4: IMEI lookup — imei.info (PHONECERT_IMEIINFO_KEY + _SERVICE) or sickw (PHONECERT_SICKW_KEY,
                      #     service 61); 7-day cache; MockProvider for dev (see .env.example)
  checks/catalog.py   # M5: which tests exist (WEB / AUTO / MANUAL, SECURE_ONLY, JUDGED_BY_YOU), summary(), auto_from_scan()
  checks/webtests.py  # M5: the test-page HTTP(S) server only — Handler with GET_ROUTES / POST_ROUTES, make_server, serve
  checks/battery_load.py # M5: gauge sampling (LoadSampler, read_gauge) + pure verdict() from internal resistance
  checks/lan.py       # M5: lan_ip, wifi_ssid, self_signed_cert
  parts/inventory.py  # M2: IORegistry class discovery + component serials/auth + flags
  parts/battery_age.py # M2: battery operating hours vs board build date → normal / clarify / unknown
  parts/build_dates.py # M2: every part serial (FFF Y WW…) vs board date → consistent / check / unknown
  parts/sensors.py    # M5: driver presence (accel/gyro/compass/baro/prox/ALS/U1/NFC/Wi-Fi/BT/port…) from the tree
scripts/m2_dump.sh    # research: dump everything readable into reports/research/<serial>/ (gitignored)
desktop/              # M6 Tauri app. src-tauri/src/lib.rs = 4 commands (devices, scan, reports, read_report)
  src/App.tsx         #   screens Connect → Scanning → Report (ReportView.tsx) → History (History.tsx); types.ts mirrors scan JSON
  src/ReportView.tsx  #   sections (sidebar): Trust (TrustTab.tsx) · Device · Battery · Parts · System · Tests (TestsTab.tsx:
                      #   scan + Safari results) · Checklist (ChecklistTab.tsx: the by-hand checks)
  src/Settings.tsx    #   Settings screen: provider keys + service ids → Rust get_settings / save_settings (values over stdin,
                      #   never as arguments) / check_provider; after a save App re-runs Trust for the open scan (refresh_trust)
  src/api.ts          #   Tauri invoke(); outside Tauri (plain `pnpm dev`) a shim serves public/dev/sample-report.json
web-tests/index.html  # M5: Safari test page (touch grid, multi-touch, colours, speaker, haptics) → POST /api/result
reports/              # scan JSON output (gitignored)
tests/                # pytest, pure functions on fixture dicts (no device needed)
```

## Run
```bash
source .venv/bin/activate      # created by ./setup.sh
phonecert scan
python -m pytest -q            # unit tests, no phone needed
phonecert devices | reports    # what the UI calls (add --json)
phonecert settings [--check]                  # show provider settings (keys masked); `--set` saves a JSON object from stdin
phonecert trust --report <path>               # re-run Trust for a saved scan with the current settings (free)
phonecert reports --delete <path> | --clear   # move saved scans to the macOS Trash (imei_cache.json is kept)
cd desktop && pnpm check:reports              # render every saved report in every section; lists crashes

cd desktop && pnpm install && pnpm tauri dev    # desktop app (needs Rust: `source ~/.cargo/env`)
cd desktop && pnpm dev                          # UI only in a browser (http://localhost:1420, demo data,
                                                #   add ?nodevice for the "plug in" state) — for design/Playwright
```
UI design: sidebar + one bold element (the scan ring); IBM Plex Sans, Plex Mono for serials only;
one accent (#2e8eb8 / #4aa3cc dark), status colours only on statuses; no middle-dot strings, no
all-caps labels. Screenshots for self-review via the Playwright MCP go to .playwright-mcp/ (gitignored).

## Learned so far (real devices)
- Battery keys differ by model/iOS: iPhone 16 Pro / iOS 27 nests them under
  `BatteryData` (DesignCapacity, NominalChargeCapacity…). `_find()` searches nested dicts.
- Health % = NominalChargeCapacity / DesignCapacity (matches iOS closely);
  fallback `MaximumCapacityPercent` if present.
- iOS 27 (16 Pro) exposes **no battery temperature** → optional field.
- Battery `Serial` is readable → basis for M2 replaced-battery detection.
- Model number prefix: M = new retail, F = Apple refurb, N = replacement, P = personalised.
- Grades: Excellent ≥100, Good 90–99, Average 80–89, Poor <80.
- pymobiledevice3 11.50: `lockdown get <domain>` and `apps list` print JSON; `crash ls`
  prints one path per line (panics = `panic-full-<date>-<time>...`; base/slog are companions).
  App Store apps have `SignerIdentity == "Apple iPhone OS Application Signing"`,
  TestFlight builds `"TestFlight Beta Distribution"` (both legit); dev-cert = sideloaded.
- `lockdown get com.apple.disk_usage` (whole domain) times out (>60 s): iOS computes
  per-category usage. Read `TotalDiskCapacity` / `TotalDataCapacity` / `TotalDataAvailable`
  one key at a time (~1 s each). iPhone 13 128 GB: 128000000000 / 120.3 GB / free.
  **Free space = `AmountDataAvailable`** (what Settings shows). `TotalDataAvailable` also counts
  purgeable iCloud-Photos caches (97 GB vs 0.9 GB on the test iPhone 13) — report it as "purgeable".
- `crash ls` top level: iPhone 13 339 entries, 16 Pro 128 entries, no panics on either;
  common names are JetsamEvent-*, ExcUserFault_*, SiriSearchFeedback-*, <process>-<date>.ips.
  /Retired, /DiagnosticLogs, /ForceResetTailspins subfolders listed empty.

Test devices: iPhone 13 (iPhone14,5, iOS 26.0, 75.3%, 1059 cycles) and
iPhone 16 Pro (iPhone17,1, iOS 27.0.1, 89.3%, 558 cycles).

## M2 findings (iPhone 13, iOS 26 — 10 Nov 2026)
- `diagnostics ioregistry --plane IOService` gives the tree (names/classes only, 1.3 MB, ~1 s);
  `--ioclass <Class>` gives one entry's properties (~1–2 s). `--name` is useless (returns whole tree).
  `diagnostics mg` (MobileGestalt) is dead since iOS 17.4.
- Readable parts: AppleAuthCPRelay (battery AuthPassed/isTrusted/authErrorDescription),
  AppleH13CamIn (BackCamera/BackSuperWideCamera/FrontCamera/FrontIRCamera *ModuleSerialNumString*,
  FrontIRStructuredLightProjectorSerialNumString, *ValidationStatus), ApplePearlSEPDriver
  (PearlSelfTestResult 0 = ok), AppleCLCD2 (Panel_ID, '+'-separated, first token = panel serial),
  AppleHapticsSupportLEAP (ModuleSerial), AppleANS3CGv2Controller (NAND Model/Serial Number),
  AppleMultitouchDevice (Multitouch ID), AppleCS35L27Amp (DeviceAttached), IOPlatformExpertDevice
  (serial/mlb/model/region as {"$hex": ...} strings; model-config lists wifi_module_vendor etc.).
- Class names embed the chip generation (H13 on iPhone 13) → discovered by regex in
  `parts/inventory.py`, not hard-coded. Full scan incl. parts: ~16 s.
- Not readable: Apple's "Parts and Service History" itself — still a manual step.
- Battery age: `LifetimeData/TotalOperatingTime` is in hours (iPhone 13: 40951 h ≈ age of the
  board, so original battery). Old-format serials encode dates: MLB `F3X 2 08…` = 2022 week 8,
  battery `FG9 2 033…` = 2022 day 33; the year digit is resolved with the model's release year
  (`models.RELEASE_YEAR`). iPhone 16 Pro: randomised serials and no LifetimeData on iOS 27 → unknown.
- Settings → Parts & Service on the iPhone 13 shows "Battery — Service" (health < 80 %), no repairs.
- Component serials (display Panel_ID first token, camera *ModuleSerialNumString, Taptic ModuleSerial
  before "+") follow FFF Y WW: iPhone 13 parts decode to Nov 2021 – Feb 2022, all before the
  board (2022-02-21). A part > 120 days after the board = fitted later (`build_dates.MAX_LAG_DAYS`).
  Not datable: Face ID projector (A2C1A3…), NAND (hex), randomised serials (16 Pro).
- Battery extras (iPhone 13 only, absent on iOS 27): `LifetimeData` Max/MinTemperature in 0.1 °C
  (514 → 51.4 °C, assumed), AverageTemperature in °C, MaximumFCC/MinimumFCC mAh, ResetCnt;
  `BatteryShutdownReason` = last shutdown (ShutDownTimestamp epoch, ShutDownUISoc %, voltage mV,
  temperature in 0.01 °C). UISoc ≥ 10 % at shutdown → flagged "unexpected".
- Crash dir also holds LowBatteryLog-*, JetsamEvent-* (memory kills), ResetCounter-* (watchdog),
  OTAUpdate-<date>-* (one per update attempt; last = last iOS update). Counted in panics.analyse().
- `profile list` → OrderedIdentifiers/ProfileManifest/ProfileMetadata (empty on both test phones).
- Lockdown `PasswordProtected` = the phone is *currently locked* (True in a dump taken while locked,
  False in every scan with the phone unlocked). It does not say whether a passcode exists.
- SIM: lockdown `SIMStatus` only describes slot 1. Slot 2 = keys suffixed "2" (ICCID2, IMSI2,
  SIM2IsEmbedded) + CarrierBundleInfoArray[].Slot "kTwo". The iPhone 13's only (physical) SIM is
  registered on slot 2, so slot 1 reads "NotInserted" while service works — never show that as "No SIM".
- Verified 10 Nov 2026: `lockdown get com.apple.fmip IsAssociated` → `true` when Find My is on
  (= Activation Lock after erase); `profile cloud-configuration` → `IsSupervised`, `ConfigurationSource`;
  `lockdown get com.apple.purplebuddy` → `SetupState` (set up vs Hello screen). No lockdown key for
  carrier/SIM lock exists (global keys queried via `lockdown get KEY` read a *domain* and return {}).
- Buyer deal-breakers (web research, Apple support HT213680 / 104999): Activation Lock, IMEI blacklist
  (stolen/lost/unpaid financing), supervision/MDM, carrier lock; then jailbreak, unknown parts,
  replacement/refurb unit. Apple's own Activation Lock web checker is gone; blacklist needs an IMEI API (M4).

## M5 notes (11 Nov 2026)
- Sensors live under AppleSPU with plain node names (accel, gyro, compass, pressure, prox, als, rose=U1,
  ttw). They share one class (AppleSPUHIDInterface) so `--ioclass` can't tell them apart → presence is
  taken from the tree (node + children = driver matched). Radios: AppleBCMWLANCore is an IOUserService
  (match by node name), bluetooth/AppleBluetoothModule, stockholm = NFC, hammerfest = secure element,
  AppleCBTL1614 = Lightning port controller. iPhone 13: 22/22 present.
- Safari tests: `phonecert serve --report <path> [--open]` prints `{"event":"ready","url":…}` (URL carries a
  per-session `?k=` token; every request without it gets 403 — the QR code includes it) then NDJSON
  events; Rust `start_tests` spawns it and keeps the Child in managed state (killed on stop / window close).
  Plain HTTP → no camera / mic / DeviceMotion in iOS Safari (secure context). navigator.vibrate doesn't
  exist on iOS → haptics is a prompt (mute switch). Opening the page from the Mac: `phonecert open <url> --json`
  (app button "Open in Safari on the phone" → Rust `open_on_phone`; `serve --open` does the same) starts Safari
  through the Web Inspector service and navigates its first tab — needs only Settings → Apps → Safari → Advanced →
  Web Inspector, cable, phone unlocked. Not `webinspector launch`: that is an automation window which closes when
  the command exits. This is the ONE place using the pymobiledevice3 Python API (`device/safari.py`), because
  the CLI can only do it interactively. 11 Nov 2026: reaches the iPhone 13, answered "Web Inspector is disabled";
  the success path is NOT yet verified on a device. QR code rendered in the app with `qrcode` (npm).
- Manual checklist: `phonecert tests --report <path> --name <key> --status pass|fail|skip [--note]`.
- **No cable**: `phonecert serve --new [--label …]` creates a tests-only report (`source: "tests-only"`,
  file `reports/nocable-<label>_<date>.json`) and serves it; the app's Scan screen offers the same via
  "Run the Safari tests … over Wi-Fi", the Tests section works without a report, and History lists it.
  A later cable scan is a separate report (merging is a future step).
- Test kinds in the report: `tests.auto` (computed: charging from the gauge, touch-controller error counters,
  wifi when the phone fetches /api/state), `tests.web` (page results), `tests.manual`.
- Page tests: touch grid (+ touch_rate from touchmove/s, pass ≥ 50 Hz), ghost_touch (10 s untouched),
  multitouch, display (6 colours + 2 greys + 2 gradients), speaker (tones + 100 Hz→10 kHz sweep),
  wifi_speed (3× 8 MB from /api/blob, pass ≥ 20 Mbit/s), battery_load (20 s rest + 80 s load on every core while the
  Mac polls the gauge via POST /api/load?phase=start|load|stop; measured internal resistance = least-squares
  slope of Voltage on InstantAmperage; verdict on the worse of measured and the gauge's own
  `BatteryData.WeightedRa`, fail > 150 mΩ (provisional, `battery_load.RESISTANCE_FAIL_MOHM`) or +8 °C; no cable,
  < 4 gauge refreshes or current spread < 300 mA → status "skip").
  iPhone 13 run (11 Nov 2026, charging, 46 %): gauge refreshes only every ~20 s (UpdateTime); measured 58 mΩ
  (62 mV over 1.1 A, 3 points) vs WeightedRa 153 — they disagree and neither is calibrated against a healthy
  battery yet. Next: same test on the 16 Pro for a reference.
- `--https`: self-signed cert per LAN IP in reports/.certs/ (openssl); Safari warning accepted with two taps,
  nothing installed. Unlocks camera / microphone / DeviceMotion (needs requestPermission) / geolocation
  tests (`SECURE_ONLY`). Verified on the iPhone 13 (11 Nov 2026): the accepted self-signed page IS a
  secure context — camera, microphone and motion tests pass. Geolocation answered "User denied Geolocation"
  with no prompt (Location Services / Safari Websites setting) → code 1 shows instructions, records nothing.
- HTTPS server: the TLS handshake runs in the per-connection thread (`Handler.setup`), not in accept().
  With the handshake in accept(), one half-open connection froze the whole server — Safari parks one
  while showing the certificate warning, so "Visit Website" then loaded nothing (11 Nov 2026, reproduced
  with a silent socket; regression test `test_https_server_survives_a_stalled_connection`).
- Battery resistance without a load test: every scan reads `BatteryData.WeightedRa` (the gauge's own internal
  resistance, mΩ) into `battery.resistance` — same value at any charge level, on or off the charger (iPhone 13:
  153 at 46 % and at 98 %). "high" above `health.RESISTANCE_HIGH_MOHM` = 150, provisional until a healthy phone
  gives a reference. The live load test cannot measure a nearly full battery on the charger (current moved only
  81–266 mA at 96–97 %), so the page refuses up front at ≥ 70 % and points to the scan figure.
- Skipped on purpose: storage write test (AFC can push but the CLI has no rm) and live syslog watch.

## M4 notes
- **imei.info** is the provider with a real sign-up (https://dash.imei.info/register/, 5 USD minimum).
  OpenAPI spec: https://dash.imei.info/swagger/?format=openapi. One-step check:
  `GET https://dash.imei.info/api-sync/check/{service}/?imei=…&API_KEY=…` →
  `{"id", "status": "Done|In_progress|Refunded|Rejected", "result": {…}, "token_request_price"}`;
  bad key → `{"detail": "Token is invalid."}` (verified). `/api/check/` is the async variant (poll
  `/api/search_history/{id}/`). Service ids/prices: `/api/service/services/?API_KEY=…` → `phonecert imei --services`.
  `result` field names are NOT verified yet — `normalise()` matches loosely; inspect `imei_check.raw`.
- **sickw.com**: `GET https://sickw.com/api.php?format=beta&key=…&imei=…&service=61` (0.10 USD, carrier+FMI+
  blacklist). No public registration page (only login / cart / support) — kept as alternative.
- Owner's rule: **scans are free**; paid lookups run only from the Trust tab's "Run check" button
  (or `phonecert scan --imei`). Button → Rust `imei_check(path)` → `phonecert imei --report <path> --json`
  (stores `imei_check`, re-runs Trust, rewrites the report, prints it). Trust checks carry
  `runnable` / `cost_usd` / `provider` so the UI knows when to show the button.
  imei.info has no combined Apple service → PHONECERT_IMEIINFO_SERVICES=27,8 (blacklist 0.20 + lock 0.20).
  Dev without balance: `PHONECERT_IMEI_MOCK=1`. `phonecert imei --balance` / `--services [search]`.
  Account (10 Nov 2026): key works, balance 0.00 → every call answers "Request is too expensive".
  Cache: reports/imei_cache.json (gitignored via reports/*.json).

## Status (10 Nov 2026)
- M0 ✅ done
- M1 ~95%. Full scan verified on both test phones (10 Nov 2026): iPhone 13
  (128 GB, 0 panics, 51 apps) and iPhone 16 Pro (256 GB, 0 panics, 236 apps, scan
  completes in well under a minute). Remaining:
  1. Validate numbers vs iMazing on a 3rd phone
  2. Panic `risk()` thresholds are a first guess — tune once a phone with panics shows up
- M2 ~60%: inventory + battery auth + flags work on the iPhone 13. Next: run on the
  16 Pro, then find a phone with a known replaced part to validate the flags; record
  Settings → General → About → Parts and Service History; cross-check 3uTools.

## Working style
- Answers direct and concise; no over-explaining.
- Iterate: small working steps, test on a real phone, then refine.
- Tested-on-device code only counts as done when the owner ran it on a phone.
