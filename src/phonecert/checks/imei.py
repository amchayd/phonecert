"""IMEI lookups against a paid provider (M4): GSMA blacklist, carrier lock, Find My.

Provider A: imei.info (has a real sign-up: https://dash.imei.info/register/, 5 USD minimum)
  GET https://dash.imei.info/api-sync/check/{service}/?imei=…&API_KEY=…
  → {"status": "Done"|"In_progress"|"Refunded"|"Rejected", "result": {...}, "token_request_price": "0.02", …}
  Bad key → {"detail": "Token is invalid."}. Service ids come from /api/service/services/?API_KEY=…
  (`phonecert imei --services`). Set PHONECERT_IMEIINFO_SERVICE once you picked one.
Provider B: sickw.com (no public sign-up page) — GET https://sickw.com/api.php?format=beta&key=…&imei=…&service=…
  → {"status": "success", "imei": "…", "result": {...}}   or   {"status": "error", "result": "Error A01: …"}
Service 61 "iPHONE CARRIER & FMI & BLACKLIST" (0.10 USD) covers all three in one call.
The result's field names are not documented publicly, so `normalise()` matches keys loosely
and the raw answer is kept in the report. Verified so far: the error shape only (no key yet).

Key: env PHONECERT_SICKW_KEY or a `.env` line at the repo root. Results are cached per
IMEI+service in reports/imei_cache.json so a re-scan never pays twice.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / ".env"
CACHE_FILE = ROOT / "reports" / "imei_cache.json"
CACHE_TTL = timedelta(days=7)

SICKW_URL = "https://sickw.com/api.php"
SERVICE_FULL = 61        # iPHONE CARRIER & FMI & BLACKLIST — 0.10 USD
SERVICE_BLACKLIST = 54   # WW BLACKLIST STATUS — 0.04 USD


class ImeiError(Exception):
    pass


def env(name: str) -> str | None:
    """Environment variable, else the same name from the repo's .env file."""
    val = os.environ.get(name)
    if val:
        return val.strip()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def api_key() -> str | None:   # kept for backwards compatibility
    return env("PHONECERT_SICKW_KEY")


IMEIINFO_URL = "https://dash.imei.info"
MAX_SERVICE_PAGES = 50
IMEIINFO_DEFAULT_SERVICES = (27, 8)   # BLACKLIST: Simple Check 0.20 + APPLE: Lock Status Check 0.20


class ImeiInfoProvider:
    name = "imei.info"

    def __init__(self, key: str, timeout: int = 60):
        self.key, self.timeout = key, timeout

    def _get(self, path: str, **params) -> dict:
        qs = urllib.parse.urlencode({**params, "API_KEY": self.key})
        req = urllib.request.Request(f"{IMEIINFO_URL}{path}?{qs}", headers={"User-Agent": "phonecert"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            raise ImeiError(f"imei.info HTTP {e.code}: {body}") from e
        except (OSError, ValueError) as e:
            raise ImeiError(f"imei.info request failed: {e}") from e

    def lookup(self, imei: str, service: int) -> dict:
        payload = self._get(f"/api-sync/check/{service}/", imei=imei)
        if "detail" in payload and "status" not in payload:
            raise ImeiError(str(payload["detail"]))
        if payload.get("status") != "Done":
            raise ImeiError(f"imei.info status {payload.get('status')}: {payload.get('result') or payload}")
        return {"status": "success", "imei": imei, "result": payload.get("result"),
                "price": payload.get("token_request_price"), "request_id": payload.get("id")}

    def account(self) -> dict:
        """Account details incl. balance (GET /api/account/account/)."""
        return self._get("/api/account/account/")

    def services(self, search: str | None = None) -> list[dict]:
        """Available services (id, name, price) — paginated; follows `next` links."""
        out, path, params = [], "/api/service/services/", ({"search": search} if search else {})
        for _ in range(MAX_SERVICE_PAGES):
            payload = self._get(path, **params)
            items = payload if isinstance(payload, list) else payload.get("results", [])   # list = unpaginated
            for it in items:
                out.append({"id": it.get("id"), "name": it.get("name"), "price": it.get("price") or it.get("token_price"),
                            "brand": it.get("brand"), "slug": it.get("slug")})
            nxt = payload.get("next") if isinstance(payload, dict) else None
            if not nxt:
                break
            # Never fetch the link itself: only its paging parameters are reused, against our own base URL.
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(str(nxt)).query))
            paging = {k: v for k, v in query.items() if k in ("page", "offset", "limit", "search")}
            if not paging or paging == params:
                break
            params = paging
        return out


class SickwProvider:
    name = "sickw"

    def __init__(self, key: str, timeout: int = 30):
        self.key, self.timeout = key, timeout

    def lookup(self, imei: str, service: int) -> dict:
        qs = urllib.parse.urlencode({"format": "beta", "key": self.key, "imei": imei, "service": service})
        req = urllib.request.Request(f"{SICKW_URL}?{qs}", headers={"User-Agent": "phonecert"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except (OSError, ValueError) as e:
            raise ImeiError(f"sickw request failed: {e}") from e
        if payload.get("status") != "success":
            raise ImeiError(str(payload.get("result") or payload))
        return payload


class MockProvider:
    """Canned answer for development and tests — never costs anything."""
    name = "mock"

    def __init__(self, result: dict | None = None):
        self.result = result or {"Model": "iPhone 13", "Blacklist Status": "Clean", "Carrier": "Unlocked",
                                 "Sim-Lock Status": "Unlocked", "Find My iPhone": "OFF"}

    def lookup(self, imei: str, service: int) -> dict:
        return {"status": "success", "imei": imei, "result": self.result}


def _flatten(obj, prefix="") -> dict:
    """{'a': {'b': 1}} → {'a.b': 1}; HTML strings become 'key: value' lines when possible."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, str) and "<br" in obj.lower():
        for line in re.split(r"<br\s*/?>", obj, flags=re.I):
            line = re.sub(r"<[^>]+>", "", line).strip()
            if ":" in line:
                k, v = line.split(":", 1)
                out[f"{prefix}{k.strip()}"] = v.strip()
    else:
        out[prefix.rstrip(".")] = obj
    return out


def _pick(flat: dict, *needles: str):
    for k, v in flat.items():
        kl = k.lower()
        if all(n in kl for n in needles):
            return str(v)
    return None


# A negation and the rest of its clause: "not blacklisted", "no sim restrictions", "never reported lost or stolen".
_NEGATED = re.compile(r"\b(?:not|no|never)\b[^.,;:()<>/|]*")


def normalise(payload: dict) -> dict:
    """Loose mapping of a provider result onto blacklist / carrier lock / Find My statuses."""
    flat = _flatten(payload.get("result"))
    bl = _pick(flat, "blacklist") or _pick(flat, "gsma")
    lock = _pick(flat, "lock") or _pick(flat, "carrier")
    fmi = _pick(flat, "find my") or _pick(flat, "fmi") or _pick(flat, "icloud")

    def status(text, good: str, bad: str):
        """good/bad are regexes. A bad word wins unless it is negated ("not blacklisted", "no lock"),
        so an answer holding both ("Blacklisted, not paid") never reads as a pass."""
        if text is None:
            return "unknown"
        t = text.lower()
        if re.search(bad, _NEGATED.sub(" ", t)):
            return "fail"
        if re.search(good, t):
            return "pass"
        return "unknown"

    bl_status = status(bl, r"\bclean\b|\bnot\b|\bnever\b|^no\b", r"blacklist|lost|stolen|barred|blocked")
    if re.search(r"\b(not|no longer) clean|unclean", (bl or "").lower()):
        bl_status = "fail"
    lock_status = status(lock, r"unlock|no sim|\bnone\b|\boff\b|\bfalse\b", r"\block")
    fmi_status = status(fmi, r"\boff\b|\bclean\b|disabled|\bfalse\b", r"\bon\b|lost|enabled|\btrue\b")

    return {
        "blacklist": {"status": bl_status, "detail": bl},
        "carrier_lock": {"status": lock_status, "detail": lock, "carrier": _pick(flat, "carrier")},
        "find_my": {"status": fmi_status, "detail": fmi},
        "fields": flat,
    }


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def check_imei(imei: str, provider, service: int = SERVICE_FULL, force: bool = False,
               cache_file: Path = CACHE_FILE) -> dict:
    imei = re.sub(r"\D", "", imei or "")
    if len(imei) not in (14, 15):
        raise ImeiError(f"not an IMEI: {imei!r}")
    cache = {} if cache_file is None else _load_cache_from(cache_file)
    key = f"{provider.name}:{service}:{imei}"
    hit = cache.get(key)
    if hit and not force and datetime.fromisoformat(hit["checked_at"]) > datetime.now() - CACHE_TTL:
        return {**hit, "cached": True}

    payload = provider.lookup(imei, service)
    result = {"imei": imei, "provider": provider.name, "service": service,
              "checked_at": datetime.now().isoformat(timespec="seconds"),
              **normalise(payload), "raw": payload.get("result"), "raw_price": payload.get("price")}
    if cache_file is not None:
        cache[key] = result
        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=1, default=str))
    return {**result, "cached": False}


def _load_cache_from(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


# Prices seen on 10 Nov 2026 (USD) — only for the button label; the provider bills the real amount.
KNOWN_PRICES = {"imei.info": {0: 0.02, 2: 0.36, 8: 0.20, 9: 0.05, 12: 0.10, 27: 0.20, 28: 0.42},
                "sickw": {54: 0.04, 61: 0.10}, "mock": {}}


def estimated_cost(provider, services: list[int]) -> float | None:
    table = KNOWN_PRICES.get(getattr(provider, "name", ""), {})
    if not services or any(sv not in table for sv in services):
        return None
    return round(sum(table[sv] for sv in services), 2)


def provider_from_env(mock: bool = False):
    """MockProvider when asked (or PHONECERT_IMEI_MOCK=1); else imei.info, else sickw, else None."""
    if mock or env("PHONECERT_IMEI_MOCK") == "1":
        return MockProvider()
    if env("PHONECERT_IMEIINFO_KEY"):
        return ImeiInfoProvider(env("PHONECERT_IMEIINFO_KEY"))
    if env("PHONECERT_SICKW_KEY"):
        return SickwProvider(env("PHONECERT_SICKW_KEY"))
    return None


def default_services(provider) -> list[int]:
    """Service ids to call per scan: sickw [61]; imei.info from PHONECERT_IMEIINFO_SERVICES ("27,8"); mock [61]."""
    if isinstance(provider, ImeiInfoProvider):
        val = env("PHONECERT_IMEIINFO_SERVICES") or env("PHONECERT_IMEIINFO_SERVICE") or ""
        return [int(x) for x in re.findall(r"\d+", val)] or list(IMEIINFO_DEFAULT_SERVICES)
    return [SERVICE_FULL]


def default_service(provider) -> int | None:   # single-service convenience
    ids = default_services(provider)
    return ids[0] if ids else None


def _merge_status(a: dict, b: dict) -> dict:
    """First definite answer wins; 'unknown' is overwritten by anything better."""
    return b if a.get("status") == "unknown" and b.get("status") != "unknown" else a


def check_imei_multi(imei: str, provider, services: list[int], force: bool = False,
                     cache_file: Path = CACHE_FILE) -> dict:
    """Run several services and merge them into one blacklist / carrier_lock / find_my answer."""
    if not services:
        raise ImeiError("no service ids configured")
    results = [check_imei(imei, provider, service=sv, force=force, cache_file=cache_file) for sv in services]
    merged = {"imei": results[0]["imei"], "provider": provider.name,
              "service": ",".join(str(sv) for sv in services), "services": services,
              "checked_at": max(r["checked_at"] for r in results),
              "cached": all(r["cached"] for r in results),
              "blacklist": {"status": "unknown"}, "carrier_lock": {"status": "unknown"}, "find_my": {"status": "unknown"},
              "fields": {}, "raw": {}, "raw_price": None}
    total = 0.0
    for r in results:
        for k in ("blacklist", "carrier_lock", "find_my"):
            merged[k] = _merge_status(merged[k], r[k])
        merged["fields"].update({f"{r['service']}.{k}": v for k, v in r.get("fields", {}).items()})
        merged["raw"][str(r["service"])] = r.get("raw")
        try:
            total += float(r.get("raw_price") or 0)
        except (TypeError, ValueError):
            pass
    merged["raw_price"] = round(total, 3) if total else None
    return merged
