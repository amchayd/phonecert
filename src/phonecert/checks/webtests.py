"""The test-page server: the Mac serves web-tests/ on the LAN and stores what the phone reports.

The phone opens the page in Safari (QR code, typed address + PIN, or the app's "Open in Safari"
button) and each test sends its result here; it lands in the report under tests.web.

  GET  /                      the page (with ?k=<token>), or the PIN form without it
  GET  /join?pin=…            PIN → redirect to the page with the token
  GET  /api/state             catalogue + results so far; also records "Wi-Fi reached the Mac"
  GET  /api/result?name=…     result, for when Safari's POST fails
  POST /api/result            result {"name", "status", "details"}
  GET  /api/blob?mb=…         random bytes for the Wi-Fi throughput test
  POST /api/load?phase=…      battery under load: start | load | stop | cancel

Everything except / and /join needs the session token. Over HTTPS (self-signed) Safari also allows
camera, microphone, motion and location. stdout carries one JSON event per line for the desktop app.
"""
import json
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from phonecert.checks import battery_load, catalog
from phonecert.checks.lan import lan_ip, self_signed_cert, wifi_ssid
from phonecert.device.safari import open_in_safari
from phonecert.report import store

WEB_DIR = Path(__file__).resolve().parents[3] / "web-tests"
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}

PIN_MAX_FAILURES = 5
MAX_BODY_BYTES = 1 << 20     # results are a few hundred bytes; refuse anything bigger than 1 MiB
TLS_HANDSHAKE_TIMEOUT_S = 20

JOIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>PhoneCert</title>
<style>body{margin:0;background:#151b24;color:#e6ebf1;font:18px/1.4 -apple-system,sans-serif;padding:2rem 1.2rem}
input{font:inherit;font-size:2rem;letter-spacing:.3em;width:100%;padding:.6rem;border-radius:12px;border:1px solid #2b3542;background:#1d2531;color:#fff;text-align:center}
button{font:inherit;font-weight:600;width:100%;margin-top:1rem;padding:.9rem;border-radius:12px;border:0;background:#4aa3cc;color:#0d1218}
p{color:#93a0b1}</style></head><body><h1>PhoneCert tests</h1>
<p>Type the 6-digit code shown in PhoneCert on the Mac.</p>
<form method="get" action="/join"><input name="pin" inputmode="numeric" pattern="[0-9]*" maxlength="6" autofocus autocomplete="one-time-code">
<button>Open the tests</button></form><!--EXTRA--></body></html>"""


def join_page(message: str = "") -> str:
    extra = f"<p style='color:#e05a54'>{message}</p>" if message else ""
    return JOIN_PAGE.replace("<!--EXTRA-->", extra)


def emit(event: str, **fields) -> None:
    """One NDJSON line on stdout; the desktop app reads these."""
    print(json.dumps({"event": event, **fields}), flush=True)


class HttpsUnavailable(RuntimeError):
    """HTTPS was asked for and no certificate could be made."""


class BadRequest(ValueError):
    """The phone sent something the server cannot use → 400 with this message."""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # keep-alive: Safari reports "Load failed" on POSTs when a 1.0 server closes the socket

    # Per-server state, set on a subclass by make_server():
    report_path: Path = None
    token: str = ""           # per-session secret carried in the URL (?k=…); the QR code includes it
    pin: str = ""             # 6-digit code for typing the address by hand in Safari (→ redirect with the token)
    pin_failures: int = 0     # locked after PIN_MAX_FAILURES wrong codes
    sampler: battery_load.LoadSampler = None
    lock = threading.Lock()   # one writer at a time on the report file

    # path → method name. Anything else under GET is a static file from web-tests/.
    GET_ROUTES = {"/api/state": "get_state", "/api/result": "get_result", "/api/blob": "get_blob"}
    POST_ROUTES = {"/api/result": "post_result", "/api/load": "post_load"}

    # ---- connection ----

    def setup(self):
        if hasattr(self.request, "do_handshake"):   # HTTPS: see make_server
            self.request.settimeout(TLS_HANDSHAKE_TIMEOUT_S)
            try:
                self.request.do_handshake()
            except OSError:          # warning page not accepted yet, port scan, timeout: just drop it
                self.tls_failed = True
            self.request.settimeout(None)
        super().setup()

    def handle(self):
        if getattr(self, "tls_failed", False):
            return
        try:
            super().handle()
        except Exception as e:  # noqa: BLE001 — surface it in the server log, keep serving
            emit("error", client=self.client_address[0], error=repr(e))

    def log_message(self, *args):   # quiet: events go through emit()
        pass

    # ---- request / response helpers ----

    @property
    def route(self) -> str:
        return urlsplit(self.path).path

    def param(self, name: str, default: str = "") -> str:
        return parse_qs(urlsplit(self.path).query).get(name, [default])[0]

    def body(self) -> bytes:
        """The request body, size-checked. Only called for requests that carry the session token."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as e:
            raise BadRequest("bad Content-Length") from e
        if not 0 <= length <= MAX_BODY_BYTES or self.headers.get("Transfer-Encoding"):
            self.close_connection = True          # the unread body would corrupt a kept-alive connection
            raise BadRequest("body too large or chunked")
        return self.rfile.read(length)

    def authorised(self) -> bool:
        return secrets.compare_digest(self.param("k"), self.token)

    def send(self, body: bytes, content_type: str, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str, status=HTTPStatus.OK):
        self.send(html.encode(), "text/html; charset=utf-8", status)

    def send_json(self, obj, status=HTTPStatus.OK):
        self.send(json.dumps(obj).encode(), "application/json", status)

    # ---- dispatch ----

    def do_GET(self):
        if not self.authorised():
            return self.get_without_token()
        self.dispatch(self.GET_ROUTES, fallback=self.get_static)

    def do_POST(self):
        if not self.authorised():
            self.close_connection = True          # never read a body from a client without the token
            return self.send_json({"error": "unauthorised"}, HTTPStatus.FORBIDDEN)
        try:
            self.request_body = self.body()
        except BadRequest as e:
            return self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
        self.dispatch(self.POST_ROUTES, fallback=lambda: self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND))

    def dispatch(self, routes: dict, fallback):
        handler = getattr(self, routes[self.route]) if self.route in routes else fallback
        try:
            handler()
        except BadRequest as e:
            self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)

    # ---- joining without the token ----

    def get_without_token(self):
        if self.route == "/":                # address typed by hand in Safari: ask for the code
            return self.send_html(join_page())
        if self.route == "/join":
            return self.get_join()
        self.send_json({"error": "unauthorised — open the address from the QR code"}, HTTPStatus.FORBIDDEN)

    def get_join(self):
        server_state = type(self)            # counters live on the per-server class, shared by all connections
        pin = self.param("pin").strip()
        with self.lock:                      # check and count in one step, so parallel guesses cannot exceed the limit
            locked = server_state.pin_failures >= PIN_MAX_FAILURES
            correct = not locked and bool(pin) and secrets.compare_digest(pin, self.pin)
            if not locked:
                server_state.pin_failures = 0 if correct else server_state.pin_failures + 1
        if locked:
            return self.send_html(join_page("Too many wrong codes. Stop and start the test page in PhoneCert."), HTTPStatus.FORBIDDEN)
        if not correct:
            return self.send_html(join_page("Wrong code."), HTTPStatus.FORBIDDEN)
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", f"/?k={self.token}")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- routes ----

    def get_state(self):
        emit("client", client=self.client_address[0], ua=self.headers.get("User-Agent", ""))
        with self.lock:   # the phone reached us → Wi-Fi works; record it once
            report = store.load(self.report_path)
            if "wifi" not in (report.get("tests") or {}).get("auto", {}):
                store.record_test(self.report_path, "auto", "wifi", "pass", details={"client": self.client_address[0]})
                report = store.load(self.report_path)
        self.send_json({"device": report.get("device", {}).get("model"), "tests": report.get("tests", {}),
                        "web_tests": catalog.WEB_TESTS, "secure_only": sorted(catalog.SECURE_ONLY),
                        "judged_by_you": sorted(catalog.JUDGED_BY_YOU)})

    def get_result(self):
        """GET fallback for results: ?name=…&status=…&details=<json>."""
        try:
            details = json.loads(self.param("details", "null"))
        except ValueError as e:
            raise BadRequest(str(e)) from e
        self.store_result(self.param("name"), self.param("status"), details, via="get")

    def post_result(self):
        try:
            data = json.loads(self.request_body or b"{}")
            name, status = data["name"], data["status"]
        except (ValueError, KeyError, TypeError) as e:
            raise BadRequest(str(e)) from e
        self.store_result(name, status, data.get("details"))

    def store_result(self, name: str, status: str, details, via: str | None = None):
        if name not in catalog.WEB_TESTS or status not in catalog.WEB_RESULT_STATUSES:
            raise BadRequest("unknown test or status")
        with self.lock:
            tests = store.record_test(self.report_path, "web", name, status, details=details)
        summary = catalog.summary(tests)
        emit("result", name=name, status=status, **({"via": via} if via else {}), summary=summary)
        self.send_json({"ok": True, "summary": summary})

    def get_blob(self):
        """Wi-Fi throughput: random bytes, so nothing on the way can compress them."""
        try:
            megabytes = max(1, min(int(self.param("mb", "4")), 32))
        except ValueError as e:
            raise BadRequest("mb must be a number") from e
        self.send(secrets.token_bytes(1024 * 1024) * megabytes, "application/octet-stream")

    def post_load(self):
        """Battery under load: start → sample over USB; load → the phone began working; stop → verdict."""
        phase = self.param("phase")
        if phase == "start":
            gauge = self.sampler.start()
            first = self.sampler.samples[0] or {}
            return self.send_json({"ok": True, "gauge": gauge, "charge_pct": first.get("charge_pct"),
                                   "too_full": battery_load.too_full_to_measure(first),
                                   "run_below_pct": battery_load.NEARLY_FULL_PCT})
        if phase == "cancel":                # the page decided not to run: stop sampling, record nothing
            self.sampler.stop()
            return self.send_json({"ok": True})
        if phase == "load":
            self.sampler.phase = "load"
            return self.send_json({"ok": True})
        if phase != "stop":
            raise BadRequest("phase must be start, load, stop or cancel")
        self.sampler.stop()
        verdict = battery_load.verdict(self.sampler.samples)
        status = verdict.pop("status")
        with self.lock:
            tests = store.record_test(self.report_path, "web", "battery_load", status,
                                      details={**verdict, "samples_raw": self.sampler.samples})
        emit("result", name="battery_load", status=status, summary=catalog.summary(tests))
        self.send_json({"ok": True, "status": status, **verdict})

    def get_static(self):
        web_root = WEB_DIR.resolve()
        file = (web_root / ("index.html" if self.route == "/" else self.route.lstrip("/"))).resolve()
        if not file.is_relative_to(web_root) or file.suffix not in STATIC_TYPES or not file.is_file():
            return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        self.send(file.read_bytes(), STATIC_TYPES[file.suffix])


def make_server(report_path: Path, port: int = 0, host: str = "0.0.0.0", token: str | None = None,
                https: bool = False, ip: str | None = None) -> ThreadingHTTPServer:
    """A server bound to one report. With https=True it is HTTPS or HttpsUnavailable, never a silent downgrade."""
    handler = type("BoundHandler", (Handler,), {
        "report_path": report_path, "token": token or secrets.token_urlsafe(16),
        "pin": f"{secrets.randbelow(1_000_000):06d}", "pin_failures": 0,
        "sampler": battery_load.LoadSampler()})
    server = ThreadingHTTPServer((host, port), handler)
    server.token, server.pin, server.scheme = handler.token, handler.pin, "http"
    if https:
        certificate = self_signed_cert(ip or lan_ip())
        if certificate is None:              # never fall back to plain HTTP behind the caller's back
            server.server_close()
            raise HttpsUnavailable("could not create the HTTPS certificate (is openssl installed?). "
                                   "Start without the secure page instead.")
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(certificate[0]), str(certificate[1]))
        # Handshake in the per-connection thread (Handler.setup), never in accept(): Safari parks a
        # half-open connection while it shows the certificate warning, and a handshake inside
        # accept() would freeze the server for every other connection until that one goes away.
        server.socket = ctx.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
        server.scheme = "https"
    return server


def serve(report_path: Path, port: int = 0, open_on_phone: bool = False, https: bool = False) -> None:
    """Blocking. Emits a "ready" event with the URL (incl. session token) first, then one event per result."""
    ip = lan_ip()
    server = make_server(report_path, port, https=https, ip=ip)
    address = f"{server.scheme}://{ip}:{server.server_port}"
    url = f"{address}/?k={server.token}"
    emit("ready", url=url, port=server.server_port, report=str(report_path), secure=server.scheme == "https",
         ip=ip, ssid=wifi_ssid(), short_url=address, pin=server.pin)
    if open_on_phone:
        threading.Thread(target=lambda: emit("open", **open_in_safari(url)), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
