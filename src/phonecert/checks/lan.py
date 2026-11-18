"""The Mac's side of the local network: its address, the Wi-Fi name, and a certificate for HTTPS."""
import re
import socket
import subprocess
from pathlib import Path

CERT_DIR = Path(__file__).resolve().parents[3] / "reports" / ".certs"


def lan_ip() -> str:
    """The Mac's address on the LAN (what the phone must reach)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # no packet is sent; picks the default route's interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def wifi_ssid() -> str | None:
    """The Mac's Wi-Fi network name, when macOS lets us see it.

    Since macOS 14 the SSID is "<redacted>" for processes without Location permission,
    so this often returns None; the app then asks the user to type it once.
    """
    try:
        iface = subprocess.run(["route", "-n", "get", "10.255.255.255"], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"interface:\s*(\S+)", iface)
        if not m:
            return None
        out = subprocess.run(["ipconfig", "getsummary", m[1]], capture_output=True, text=True, timeout=5).stdout
        m = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.M)
        ssid = m[1].strip() if m else None
        return None if not ssid or "redacted" in ssid else ssid
    except (OSError, subprocess.TimeoutExpired):
        return None


def self_signed_cert(ip: str) -> tuple[Path, Path] | None:
    """Create (once) a self-signed certificate for the Mac's LAN IP with the system openssl.

    Safari shows a warning the user accepts with two taps ("Show details → visit this website");
    nothing is installed on the phone. HTTPS is what unlocks camera / microphone / motion / GPS.
    """
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    crt, key = CERT_DIR / f"{ip}.crt", CERT_DIR / f"{ip}.key"
    if crt.exists() and key.exists():
        return crt, key
    cmd = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "825", "-nodes",
           "-keyout", str(key), "-out", str(crt), "-subj", f"/CN=PhoneCert {ip}",
           "-addext", f"subjectAltName=IP:{ip},DNS:localhost"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return crt, key
