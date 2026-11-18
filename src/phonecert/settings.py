"""App settings: the IMEI provider keys and service ids, kept in the repo's `.env` file (gitignored).

The desktop app's Settings screen and `phonecert settings` both go through here. A key is never
returned once saved: `read()` only says that it is set and shows its last four characters.
"""
import os
import re
from dataclasses import dataclass

from phonecert.checks import imei


@dataclass(frozen=True)
class Field:
    name: str        # what the app calls it
    env: str         # the line in .env / the environment variable
    secret: bool = False
    pattern: str = r"[^\r\n]*"   # what a value may look like


FIELDS = (
    Field("imeiinfo_key", "PHONECERT_IMEIINFO_KEY", secret=True, pattern=r"[\w.\-]*"),
    Field("imeiinfo_services", "PHONECERT_IMEIINFO_SERVICES", pattern=r"\d+(\s*,\s*\d+)*|"),
    Field("sickw_key", "PHONECERT_SICKW_KEY", secret=True, pattern=r"[\w.\-]*"),
)
BY_NAME = {f.name: f for f in FIELDS}


def _hint(secret: str) -> str | None:
    return f"…{secret[-4:]}" if len(secret) >= 8 else None


def read() -> dict:
    """What the Settings screen shows. Secrets are reduced to set / not set and a four-character hint."""
    fields = {}
    for f in FIELDS:
        value = imei.env(f.env) or ""
        fields[f.name] = {
            "set": bool(value),
            # A variable in the process environment wins over .env, so saving would not change it.
            "from_environment": bool(os.environ.get(f.env)),
            **({"hint": _hint(value)} if f.secret else {"value": value}),
        }
    provider = imei.provider_from_env()
    return {"fields": fields, "provider": provider.name if provider else None,
            "services": imei.default_services(provider) if provider else [],
            "default_services": list(imei.IMEIINFO_DEFAULT_SERVICES)}


def write(changes: dict) -> None:
    """Save {name: value}; an empty value removes the setting. Other lines of .env are left alone."""
    lines = {}
    for name, value in changes.items():
        field = BY_NAME.get(name)
        if field is None:
            raise ValueError(f"unknown setting: {name}")
        value = str(value).strip()
        if not re.fullmatch(field.pattern, value):
            raise ValueError(f"{name}: not a valid value")
        lines[field.env] = value
    if not lines:
        return
    path = imei.ENV_FILE
    out = []
    for line in (path.read_text().splitlines() if path.exists() else []):
        key = line.split("=", 1)[0].strip()
        out.append(f"{key}={lines.pop(key)}" if key in lines and "=" in line else line)
    out += [f"{key}={value}" for key, value in lines.items()]
    # Written next to the file and moved into place, readable by the owner only: it holds API keys.
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def check() -> dict:
    """Ask the provider whether the saved key works, without buying a lookup. → {"ok", "provider", "detail"}"""
    provider = imei.provider_from_env()
    if provider is None:
        return {"ok": False, "provider": None, "detail": "No provider key is saved."}
    if not hasattr(provider, "account"):
        return {"ok": None, "provider": provider.name,
                "detail": f"{provider.name} has no free way to test a key; the first lookup will tell."}
    try:
        account = provider.account()
    except imei.ImeiError as e:
        return {"ok": False, "provider": provider.name, "detail": str(e)}
    if "detail" in account and len(account) == 1:      # imei.info answers a bad key with {"detail": "Token is invalid."}
        return {"ok": False, "provider": provider.name, "detail": str(account["detail"])}
    balance = next((v for k, v in account.items() if "balance" in k.lower()), None)
    detail = "The key works." + (f" Balance: {balance} USD." if balance is not None else "")
    return {"ok": True, "provider": provider.name, "detail": detail, "balance": balance}
