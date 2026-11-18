"""Read raw data from a USB-connected iPhone via the pymobiledevice3 CLI.

Using the CLI (JSON output) keeps us independent of pymobiledevice3's
internal Python API, which changes between versions.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


class DeviceError(Exception):
    pass


def _pmd3() -> str:
    # Prefer the binary next to the running interpreter (inside .venv)
    local = Path(sys.executable).parent / "pymobiledevice3"
    if local.exists():
        return str(local)
    found = shutil.which("pymobiledevice3")
    if not found:
        raise DeviceError("pymobiledevice3 not found — run ./setup.sh")
    return found


def _exec(*args: str, timeout: int = 60) -> str:
    proc = subprocess.run([_pmd3(), *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise DeviceError(_error_message(proc.stderr or proc.stdout))
    return proc.stdout.strip()


def _error_message(output: str) -> str:
    """pymobiledevice3 logs '<date> <host> <module>[pid] ERROR <msg>' then an INFO hint; keep <msg>."""
    lines = [line for line in output.strip().splitlines() if line.strip()]
    errors = [line for line in lines if " ERROR " in line]
    line = errors[-1] if errors else (lines[-1] if lines else "unknown error")
    return line.split(" ERROR ", 1)[-1].strip()


def _run(*args: str, timeout: int = 60) -> dict:
    """Run a command that prints JSON and return the parsed object."""
    out = _exec(*args, timeout=timeout)
    start = out.find("{")
    if start == -1:
        raise DeviceError(f"unexpected output: {out[:200]}")
    return json.loads(out[start:])


def _run_lines(*args: str, timeout: int = 60) -> list[str]:
    """Run a command that prints one item per line and return the non-empty lines."""
    return [line.strip() for line in _exec(*args, timeout=timeout).splitlines() if line.strip()]


def list_devices() -> list[dict]:
    """Devices visible to usbmuxd (no pairing needed). Each has DeviceName, ProductType, ProductVersion, Identifier."""
    out = _exec("usbmux", "list", timeout=30)
    start = out.find("[")
    return json.loads(out[start:]) if start != -1 else []


def lockdown_info() -> dict:
    return _run("lockdown", "info")


def battery_info() -> dict:
    return _run("diagnostics", "battery", "single")


def _run_value(*args: str, timeout: int = 60):
    """Run a command that prints a single JSON value (scalar or object)."""
    return json.loads(_exec(*args, timeout=timeout))


DISK_KEYS = ("TotalDiskCapacity", "TotalDataCapacity", "TotalDataAvailable", "AmountDataAvailable")


def disk_usage() -> dict:
    """Storage figures in bytes from the lockdown domain com.apple.disk_usage.

    Read key by key (~1 s each): asking for the whole domain makes iOS compute
    per-category usage (photos, apps…) and that took >60 s on an iPhone 13.
    """
    return {k: _run_value("lockdown", "get", "com.apple.disk_usage", k, timeout=30) for k in DISK_KEYS}


def crash_files() -> list[str]:
    """Top-level entries of the device's CrashReporter directory (file names / folders)."""
    return _run_lines("crash", "ls", timeout=120)


def installed_apps(app_type: str = "User") -> dict:
    """Installed apps keyed by bundle id (installation_proxy). System apps are skipped by default."""
    return _run("apps", "list", "--type", app_type, timeout=120)


def find_my_associated():
    """True when the phone is linked to an iCloud account with Find My on → Activation Lock after erase."""
    return _run_value("lockdown", "get", "com.apple.fmip", "IsAssociated", timeout=30)


def cloud_configuration() -> dict:
    """Supervision / DEP state (`profile cloud-configuration`): IsSupervised, ConfigurationSource…"""
    return _run("profile", "cloud-configuration", timeout=60)


def setup_state() -> dict:
    """com.apple.purplebuddy: SetupState / RestoreState — whether the phone is set up or at the Hello screen."""
    return _run("lockdown", "get", "com.apple.purplebuddy", timeout=30)


def installed_profiles() -> dict:
    """Configuration profiles / MDM (`profile list`): OrderedIdentifiers, ProfileManifest, ProfileMetadata."""
    return _run("profile", "list", timeout=60)


def ioregistry_tree() -> dict:
    """Whole IOService plane as a tree of {name, className, children} — names/classes only, no properties."""
    return _run("diagnostics", "ioregistry", "--plane", "IOService", timeout=60)


def ioregistry_class(io_class: str) -> dict:
    """Properties of the first IORegistry entry of this class (~1-2 s each). {} if absent."""
    out = _exec("diagnostics", "ioregistry", "--ioclass", io_class, timeout=60)
    start = out.find("{")
    return json.loads(out[start:]) if start != -1 else {}
