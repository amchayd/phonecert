"""PhoneCert command line. This file only parses arguments and prints; the work is in the modules it calls.

Every command has one function `cmd_<name>(args)`. The desktop app runs the same commands with --json.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from phonecert import scan as scanner
from phonecert import settings
from phonecert.checks import catalog, webtests
from phonecert.checks import imei as imei_check
from phonecert.device.reader import DeviceError
from phonecert.device.safari import open_in_safari
from phonecert.report import store
from phonecert.report.text import print_summary


def fail(message: str):
    sys.exit(f"❌ {message}")


def print_json(obj, pretty: bool = True) -> None:
    print(json.dumps(obj, indent=2 if pretty else None, default=str))


def print_report(report: dict, as_json: bool) -> None:
    print_json(report) if as_json else print_summary(report)


# ---- scan / devices ----

def cmd_scan(args) -> None:
    try:
        report = scanner.scan(save=not args.no_save, imei_mock=args.imei_mock, imei_lookup=args.imei)
    except DeviceError as e:
        fail(f"{e}\n   Is the iPhone plugged in, unlocked and 'Trusted'?")
    print_report(report, args.json)


def cmd_devices(args) -> None:
    try:
        found = scanner.devices()
    except DeviceError as e:
        fail(e)
    if args.json:
        return print_json(found, pretty=False)
    for x in found:
        print(f"📱 {x['model']} — \"{x['name']}\" · iOS {x['ios_version']} · {x['connection']}")
    if not found:
        print("No iPhone detected.")


# ---- saved reports ----

def cmd_reports(args) -> None:
    if args.delete or args.clear:
        try:
            moved = store.delete_reports(None if args.clear else args.delete)
        except (ValueError, OSError) as e:
            fail(e)
        if args.json:
            return print_json({"deleted": moved, "reports": store.list_reports()}, pretty=False)
        return print(f"🗑  {moved} scan(s) moved to the Trash")
    found = store.list_reports()
    if args.json:
        return print_json(found, pretty=False)
    for x in found:
        if x["source"] == "tests-only":
            print(f"{x['scanned_at']}  {x['name'] or 'phone':16s} tests only, no cable   {x['tests_done']} tests")
        else:
            print(f"{x['scanned_at']}  {x['model'] or '?':16s} {x['serial']}  battery {x['battery_health_pct']}%  {x['tests_done']} tests")


# ---- hardware tests ----

def cmd_serve(args) -> None:
    if args.new:
        report = store.new_tests_only_report(args.label)
    elif args.report:
        report = Path(args.report)
    else:
        fail("Give --report <path>, or --new to test a phone without the cable.")
    try:
        webtests.serve(report, port=args.port, open_on_phone=args.open, https=args.https)
    except webtests.HttpsUnavailable as e:
        fail(e)


def cmd_open(args) -> None:
    result = open_in_safari(args.url)
    if args.json:
        return print_json(result, pretty=False)
    print(("✅ " if result["ok"] else "❌ ") + result["detail"])


def cmd_tests(args) -> None:
    path = Path(args.report)
    tests = store.record_test(path, "manual", args.name, args.status, note=args.note)
    if args.json:
        return print_json({**store.load(path), "saved_to": str(path)})
    sm = catalog.summary(tests)
    print(f"{args.name}: {args.status} — {sm['done']}/{sm['total']} tests recorded")


# ---- paid IMEI lookup ----

def _service_ids(text: str | None) -> list[int] | None:
    return [int(x) for x in re.findall(r"\d+", text)] if text else None


def cmd_imei(args) -> None:
    provider = imei_check.provider_from_env(mock=args.mock)
    if provider is None:
        fail("No provider key. Put PHONECERT_IMEIINFO_KEY=… (or PHONECERT_SICKW_KEY=…) in .env — see .env.example — or use --mock.")
    try:
        if args.balance:
            return _imei_balance(provider)
        if args.services is not None:
            return _imei_services(provider, args)
        if args.report:
            return _imei_update_report(args)
        _imei_single(provider, args)
    except imei_check.ImeiError as e:
        fail(e)


def _imei_balance(provider) -> None:
    if not hasattr(provider, "account"):
        fail(f"{provider.name} has no account endpoint.")
    print_json(provider.account())


def _imei_services(provider, args) -> None:
    if not hasattr(provider, "services"):
        fail(f"{provider.name} has no service listing; see its website.")
    items = provider.services(args.services or None)
    if args.json:
        return print_json(items)
    for it in items:
        print(f"{str(it['id']):>6}  {str(it['price']):>8}  {it['name']}")
    print(f"\n{len(items)} services. Put the chosen id in .env as PHONECERT_IMEIINFO_SERVICE=<id>.")


def _imei_update_report(args) -> None:
    """Run the lookup for a saved scan, store it, re-run Trust and print the updated report."""
    path = Path(args.report)
    report = store.load(path)
    target = args.imei or report["device"].get("imei")
    if not target:
        fail("Report has no IMEI.")
    report["imei_check"] = scanner.run_imei_lookup(target, _service_ids(args.service), force=args.force)
    report["trust"] = scanner.build_trust(report, report["imei_check"])
    store.save(path, report)
    report["saved_to"] = str(path)
    if not args.json and "error" in report["imei_check"]:
        fail(report["imei_check"]["error"])
    print_report(report, args.json)


def _imei_single(provider, args) -> None:
    if not args.imei:
        fail("Give an IMEI, or --services to list services.")
    services = _service_ids(args.service) or imei_check.default_services(provider)
    if not services:
        fail("No service id: pass --service <id[,id]> or set PHONECERT_IMEIINFO_SERVICES in .env (list with --services).")
    r = imei_check.check_imei_multi(args.imei, provider, services, force=args.force)
    if args.json:
        return print_json(r)
    icon = {"pass": "✅", "fail": "❌", "unknown": "❔"}
    price = f" · {r['raw_price']} USD" if r.get("raw_price") else ""
    print(f"IMEI {r['imei']} · {r['provider']} service {r['service']} · {r['checked_at']}{' (cached)' if r['cached'] else ''}{price}")
    for k in ("blacklist", "carrier_lock", "find_my"):
        print(f"  {icon[r[k]['status']]} {k.replace('_', ' ')}: {r[k].get('detail') or 'no field recognised'}")
    print("  raw fields:", json.dumps(r["fields"], ensure_ascii=False)[:400])


def cmd_trust(args) -> None:
    """Re-run Trust for a saved scan with the settings as they are now (free; keeps a lookup already paid for)."""
    path = Path(args.report)
    report = store.load(path)
    if report.get("source") == "tests-only":
        fail("A tests-only report has no scan to judge.")
    report["trust"] = scanner.build_trust(report, report.get("imei_check"))
    store.save(path, report)
    report["saved_to"] = str(path)
    print_report(report, args.json)


# ---- settings ----

def cmd_settings(args) -> None:
    """Show the settings; --set saves a JSON object read from stdin (a key never travels as an argument)."""
    check = None
    try:
        if args.set:
            settings.write(json.load(sys.stdin))
        if args.check:
            check = settings.check()
    except ValueError as e:
        fail(e)
    view = settings.read()
    if check:
        view["check"] = check
    if args.json:
        return print_json(view, pretty=False)
    for name, f in view["fields"].items():
        shown = f.get("value") or f.get("hint") or ("set" if f["set"] else "not set")
        print(f"{name:20s} {shown if f['set'] else 'not set'}{'  (from the environment)' if f['from_environment'] else ''}")
    print(f"Provider in use: {view['provider'] or 'none'}")
    if check:
        print(("✅ " if check["ok"] else "❌ " if check["ok"] is False else "❔ ") + check["detail"])


# ---- arguments ----

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="phonecert")
    sub = p.add_subparsers(dest="cmd", required=True)

    def command(name: str, handler, help: str) -> argparse.ArgumentParser:
        parser = sub.add_parser(name, help=help)
        parser.set_defaults(run=handler)
        return parser

    s = command("scan", cmd_scan, "Scan the connected iPhone")
    s.add_argument("--json", action="store_true", help="Print raw JSON")
    s.add_argument("--no-save", action="store_true")
    s.add_argument("--imei", action="store_true", help="Also run the paid IMEI lookup during the scan")
    s.add_argument("--imei-mock", action="store_true", help="Use a canned IMEI answer (development)")

    i = command("imei", cmd_imei, "IMEI blacklist / carrier lock / Find My lookup (paid provider)")
    i.add_argument("imei", nargs="?", help="IMEI to check (omit with --services)")
    i.add_argument("--json", action="store_true")
    i.add_argument("--mock", action="store_true", help="Canned answer, no cost")
    i.add_argument("--force", action="store_true", help="Ignore the 7-day cache")
    i.add_argument("--service", help="Service id(s), e.g. 27 or 27,8 (default: sickw 61 / PHONECERT_IMEIINFO_SERVICES)")
    i.add_argument("--services", nargs="?", const="", metavar="SEARCH",
                   help="List the provider's services (optionally filtered), with ids and prices")
    i.add_argument("--balance", action="store_true", help="Show the provider account / balance")
    i.add_argument("--report", metavar="PATH", help="Update this saved scan: store the result, re-run Trust, print the report")

    sv = command("serve", cmd_serve, "Serve the Safari hardware tests for a saved scan (blocking)")
    sv.add_argument("--report", metavar="PATH", help="Saved scan to attach results to")
    sv.add_argument("--new", action="store_true", help="No cable: create a tests-only report first")
    sv.add_argument("--label", default=None, help="Name for the --new report, e.g. 'iPhone 13 blue, seller Max'")
    sv.add_argument("--port", type=int, default=0, help="0 = pick a free port")
    sv.add_argument("--open", action="store_true", help="Also open the page in Safari on the cabled phone (Web Inspector switch)")
    sv.add_argument("--https", action="store_true", help="Self-signed HTTPS (unlocks camera / mic / motion / GPS tests)")

    op = command("open", cmd_open, "Open a URL in Safari on the cabled phone (needs Safari's Web Inspector switch)")
    op.add_argument("url")
    op.add_argument("--json", action="store_true")

    ts = command("tests", cmd_tests, "Record a manual checklist result in a saved scan")
    ts.add_argument("--report", required=True, metavar="PATH")
    ts.add_argument("--name", required=True, choices=sorted(catalog.MANUAL_TESTS))
    ts.add_argument("--status", required=True, choices=["pass", "fail", "skip"])
    ts.add_argument("--note", default=None)
    ts.add_argument("--json", action="store_true")

    d = command("devices", cmd_devices, "List connected iPhones")
    d.add_argument("--json", action="store_true")

    h = command("reports", cmd_reports, "List saved scans")
    h.add_argument("--json", action="store_true")
    h.add_argument("--delete", metavar="PATH", action="append", help="Move this saved scan to the Trash (repeatable)")
    h.add_argument("--clear", action="store_true", help="Move every saved scan to the Trash")

    tr = command("trust", cmd_trust, "Re-run the Trust verdict of a saved scan with the current settings (free)")
    tr.add_argument("--report", required=True, metavar="PATH")
    tr.add_argument("--json", action="store_true")

    st = command("settings", cmd_settings, "Show or change the IMEI provider settings (stored in .env)")
    st.add_argument("--json", action="store_true")
    st.add_argument("--set", action="store_true", help='Save a JSON object from stdin, e.g. {"imeiinfo_services": "27,8"}; "" removes a setting')
    st.add_argument("--check", action="store_true", help="Ask the provider whether the saved key works (free)")
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
