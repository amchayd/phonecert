"""A report as text for the terminal (`phonecert scan` without --json). One function per section."""
from phonecert.checks import catalog

STATUS_ICON = {"pass": "✅", "fail": "❌", "warn": "⚠️ ", "unknown": "❔", "manual": "👁 ", "not_checked": "⏳"}


def _na(value, unit: str = "") -> str:
    return f"{value}{unit}" if value is not None else "n/a"


def print_summary(r: dict) -> None:
    if r.get("source") == "tests-only":
        return _tests_only(r)
    _trust(r.get("trust") or {})
    _device(r["device"], r.get("sim") or {})
    _battery(r["battery"])
    _storage(r["storage"])
    _system(r["system"])
    _parts(r["parts"])
    if "saved_to" in r:
        print(f"\n💾 Saved: {r['saved_to']}\n")


def _tests_only(r: dict) -> None:
    print(f"\n📱 {r['device'].get('name')} — tests-only report (no cable), {r['scanned_at']}")
    sm = catalog.summary(r.get("tests"))
    print(f"   Tests recorded: {sm['done']}/{sm['total']}" + (f" · failed: {', '.join(sm['failed'])}" if sm["failed"] else ""))


def _trust(t: dict) -> None:
    print(f"\n🛡  Trust: {t.get('verdict', '?').upper()}")
    for c in t.get("checks", []):
        print(f"   {STATUS_ICON.get(c['status'], '•')} {c['title']}: {c['detail']}")
        if c.get("action") and c["status"] != "pass":
            print(f"        → {c['action']}")


def _device(d: dict, sm: dict) -> None:
    print(f"\n📱 {d['model']} — \"{d['name']}\"  ({d['product_type']} · {d['model_number']} {d['region']})")
    print(f"   iOS {d['ios_version']} · Serial {d['serial']} · IMEI {d['imei']}")
    print(f"   Unit type: {d['unit_type']} · Activation: {d['activation_state']} · "
          f"Lock state: {'locked' if d.get('locked_now') else 'unlocked'} · {d.get('timezone')}")
    warn = " ⚠️ card in tray not recognised" if sm.get("card_not_recognised") else ""
    print(f"   SIM: {sm.get('summary')} · {sm.get('tray')} · baseband {sm.get('baseband_version')}{warn}")


def _battery(b: dict) -> None:
    if "error" in b:
        print(f"\n🔋 Battery: could not read ({b['error']})")
        return
    src = f" ({b['health_source']})" if b.get("health_source") else ""
    print(f"\n🔋 Battery health: {_na(b['health_pct'], '%')}{src}  → {b['grade']}")
    mah = (f"{b['current_max_capacity_mah']} / {b['design_capacity_mah']} mAh · "
           if b['design_capacity_mah'] else "")
    temp = f" · {b['temperature_c']} °C" if b['temperature_c'] is not None else ""
    print(f"   {mah}{_na(b['cycle_count'])} cycles · charge {_na(b.get('charge_pct'), '%')}{temp}")
    if b.get("battery_serial"):
        print(f"   Battery serial: {b['battery_serial']}")
    ch = b.get("charging") or {}
    if ch.get("status"):
        print(f"   Charging now: {ch['status']} — {'yes' if ch.get('is_charging') else 'no'}, {_na(ch.get('current_ma'))} mA, "
              f"adapter {_na(ch.get('adapter_watts'))} W ({_na(ch.get('adapter'))})")
    lt, sd = b.get("lifetime") or {}, b.get("last_shutdown") or {}
    if lt:
        print(f"   Lifetime: {_na(lt['min_temperature_c'])}–{_na(lt['max_temperature_c'])} °C (avg {_na(lt['avg_temperature_c'])}) · "
              f"peak capacity {_na(lt['max_full_charge_mah'])} mAh · gauge resets {_na(lt['gauge_resets'])}")
    res = b.get("resistance") or {}
    if res:
        tag = " ⚠️ high" if res["status"] == "high" else ""
        print(f"   Internal resistance: {res['mohm']} mΩ (battery's own figure; high above {res['high_above_mohm']}, provisional){tag}")
    if sd:
        tag = " ⚠️ unexpected" if sd.get("unexpected") else ""
        print(f"   Last shutdown: {sd['at']} at {_na(sd['charge_pct'], '%')} / {_na(sd['voltage_mv'])} mV{tag}")


def _storage(st: dict) -> None:
    if "error" in st:
        print(f"\n💽 Storage: could not read ({st['error']})")
        return
    purge = f" · purgeable {st['purgeable_gb']} GB" if st.get("purgeable_gb") else ""
    print(f"\n💽 Storage: {st['capacity_gb']} GB · used {st['used_gb']} GB ({st['used_pct']}%) "
          f"· free {st['free_gb']} GB{purge}")


def _system(system: dict) -> None:
    pl, jb, pr = system["panic_logs"], system["jailbreak"], system.get("profiles") or {}
    if "error" in pl:
        print(f"\n⚠️  Panic logs: could not read ({pl['error']})")
    else:
        last = f" · last {pl['last_panic']} ({pl['days_since_last_panic']} days ago)" if pl["last_panic"] else ""
        print(f"\n⚠️  Panic logs: {pl['panic_count']}{last}  → risk {pl['risk']}")
        ota = pl.get("ota_updates") or {}
        print(f"   Low-battery logs {pl.get('low_battery_logs')} · memory-pressure kills {pl.get('jetsam_events')} · "
              f"watchdog resets {pl.get('watchdog_resets')} · iOS updates {ota.get('count')} (last {ota.get('last')})")
    if "error" in pr:
        print(f"🛡  Profiles: could not read ({pr['error']})")
    else:
        names = f" — {', '.join(pr['profiles'])}" if pr.get("profiles") else ""
        print(f"🛡  Profiles / MDM: {pr.get('verdict')} ({pr.get('count')} installed){names}")
    if "error" in jb:
        print(f"🔓 Jailbreak: could not read ({jb['error']})")
    else:
        hints = jb["jailbreak_apps"] + jb["crash_hints"] + jb["sideloaded_apps"]
        detail = f" — {', '.join(hints[:5])}" if hints else ""
        print(f"🔓 Jailbreak: {jb['verdict']} ({jb['user_app_count']} user apps){detail}")


def _parts(pt: dict) -> None:
    if "error" in pt:
        print(f"\n🔩 Parts: could not read ({pt['error']})")
        return
    bt = pt["battery"]
    auth = "genuine ✓" if bt["auth_passed"] and bt["trusted"] else ("FAILED ✗" if bt["auth_passed"] is False else "n/a")
    print(f"\n🔩 Parts  (MLB {_na(pt['logic_board']['mlb_serial'])})")
    print(f"   Battery auth: {auth} · serial {_na(bt['serial'])}")
    print(f"   Display panel: {_na(pt['display']['panel_serial'])}")
    cams = " · ".join(f"{k} {c['serial'] or '—'}" for k, c in pt["cameras"].items())
    print(f"   Cameras: {cams or 'n/a'}")
    print(f"   Face ID: projector {_na(pt['face_id']['projector_serial'])} · self-test {_na(pt['face_id']['self_test_result'])}")
    print(f"   Taptic {_na(pt['taptic']['serial'])} · NAND {_na(pt['nand']['model'])} {_na(pt['nand']['serial'])}")
    age = pt["battery_age"]
    built = f"board built {age['board_built']}" if age["board_built"] else "board build date unknown"
    hours = (f"{age['operating_hours']} h operated / {age['phone_age_hours']} h ({age['ratio']:.0%})"
             if age["ratio"] is not None else f"operated {_na(age['operating_hours'])} h")
    print(f"   Battery age: {hours} · {built}  → {age['verdict']}")
    sn = pt.get("sensors") or {}
    if sn:
        miss = f" — missing: {', '.join(sn['missing'])}" if sn.get("missing") else ""
        print(f"   Hardware present: {sn['present']}/{sn['total']} drivers initialised{miss}")
    bdz = pt.get("build_dates") or {}
    built = " · ".join(f"{c['part']} {c['built'][:7]}" for c in bdz.get("components", []) if c.get("built"))
    print(f"   Build dates vs board {_na(bdz.get('board_built'))}: {bdz.get('verdict')}  ({built or 'no datable serials'})")
    for f in pt["flags"] + age["reasons"] + bdz.get("reasons", []):
        print(f"   ⚠️  {f}")
