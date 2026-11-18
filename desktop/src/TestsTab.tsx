import { useEffect, useState } from "react";
import { MANUAL } from "./ChecklistTab";
import QRCode from "qrcode";
import { api } from "./api";
import type { Report } from "./types";

// Mirrors MANUAL_TESTS / WEB_TESTS in src/phonecert/checks/webtests.py (labels only).
const AUTO: [string, string][] = [
  ["charging", "Charging over the cable"], ["touch_controller", "Touch controller error counters"], ["wifi", "Wi-Fi reached the Mac"],
];
// Same split as the phone page (webtests.JUDGED_BY_YOU): the page decides these itself…
const WEB_AUTO: [string, string][] = [
  ["touch", "Touch grid"], ["touch_rate", "Touch sampling rate"], ["ghost_touch", "Ghost touches"],
  ["multitouch", "Multi-touch"], ["wifi_speed", "Wi-Fi throughput"], ["battery_load", "Battery under load"],
  ["motion", "Motion sensors"], ["location", "GPS fix"],
];
// …and for these the tester looks, listens or feels, then taps pass or fail on the phone.
const WEB_MANUAL: [string, string][] = [
  ["display", "Display screens"], ["speaker", "Speakers and sweep"], ["vibration", "Haptics"],
  ["camera", "Cameras in the browser"], ["microphone", "Microphone"],
];

// The running server session, kept outside the component: the section remounts when the
// no-cable flow swaps in the newly created report, and the QR code must survive that.
let session: { url: string; qr: string; secure: boolean; ssid: string | null; shortUrl: string; pin: string } | null = null;

function savedWifiName(): string {
  try { return localStorage.getItem("phonecert.wifiName") ?? ""; } catch { return ""; }
}

export function TestsTab({ report, onReport }: { report: Report | null; onReport: (r: Report) => void }) {
  const path = report?.saved_to ?? null;
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState<string | null>(session?.url ?? null);
  const [secure, setSecure] = useState(session?.secure ?? false);
  const [ssid, setSsid] = useState<string | null>(session?.ssid ?? null);
  const [shortUrl, setShortUrl] = useState(session?.shortUrl ?? "");
  const [pin, setPin] = useState(session?.pin ?? "");
  const [wifiName, setWifiName] = useState(savedWifiName());
  function rememberWifi(v: string) {
    setWifiName(v);
    try { localStorage.setItem("phonecert.wifiName", v); } catch { /* private mode: not remembered */ }
  }
  const [qr, setQr] = useState<string | null>(session?.qr ?? null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // While the server runs, re-read the report every 2 s so phone results appear here.
  useEffect(() => {
    if (!url || !path) return;
    const id = setInterval(async () => {
      try { onReport({ ...(await api.readReport(path)), saved_to: path }); } catch { /* keep last */ }
    }, 2000);
    return () => clearInterval(id);
  }, [url, path, onReport]);


  async function start(open: boolean, https = false) {
    setBusy(true); setErr(null);
    try {
      const r = await api.startTests(path, open, https, path ? undefined : label);
      const dataUrl = await QRCode.toDataURL(r.url, { margin: 1, width: 220 });
      session = { url: r.url, qr: dataUrl, secure: !!r.secure, ssid: r.ssid ?? null, shortUrl: r.short_url ?? "", pin: r.pin ?? "" };
      setUrl(r.url); setSecure(!!r.secure); setQr(dataUrl); setSsid(r.ssid ?? null); setShortUrl(r.short_url ?? ""); setPin(r.pin ?? "");
      if (!path && r.report) {
        // No cable: the server created a tests-only report; make it the current one so results show up.
        const created = await api.readReport(r.report);
        onReport({ ...created, saved_to: created.saved_to ?? r.report });
      }
    } catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  }
  const [opening, setOpening] = useState(false);
  const [opened, setOpened] = useState<{ ok: boolean; detail: string } | null>(null);
  async function openOnPhone() {
    if (!url) return;
    setOpening(true); setOpened(null);
    try { setOpened(await api.openOnPhone()); } catch (e) { setOpened({ ok: false, detail: String(e) }); }
    finally { setOpening(false); }
  }
  async function stop() {
    await api.stopTests().catch(() => {});
    session = null;
    setUrl(null); setQr(null);
  }
  const web = report?.tests?.web ?? {};
  const man = report?.tests?.manual ?? {};
  const auto = report?.tests?.auto ?? {};
  const total = AUTO.length + WEB_AUTO.length + WEB_MANUAL.length + MANUAL.length;
  const done = Object.keys(web).length + Object.keys(man).length + Object.keys(auto).length;
  const failed = [...Object.values(web), ...Object.values(man), ...Object.values(auto)].filter((t) => t.status === "fail").length;

  const noCable = !report || report.source === "tests-only";

  return (
    <div className="tests" data-testid="tests">
      {!report ? (
        <div className="verdict">
          <div className="verdict-title">Test a phone without the cable</div>
          <div className="muted">The Safari tests and the checklist only need Wi-Fi. Results go into a report of their own; a scan with the cable can be done later.</div>
          <label className="field">
            <span>Name for this phone</span>
            <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="iPhone 13 blue, seller Max" />
          </label>
        </div>
      ) : (
        <div className="verdict">
          <div className="verdict-title">{done} of {total} tests recorded{failed ? `, ${failed} failed` : ""}</div>
          <div className="muted">
            {noCable ? "Tests-only report: no scan data. Plug the cable later and scan to get battery, parts and trust."
                     : "Some results come from the scan itself, the rest from Safari on the phone. The checks you do by hand are in the Checklist section."}
          </div>
        </div>
      )}

      {err && <div className="notice error">{err}</div>}

      {!noCable && (
        <section className="block">
          <header className="block-head"><h3>From the scan, automatically</h3></header>
          <div className="results">
            {AUTO.map(([k, label]) => <Result key={k} label={label} r={auto[k]} />)}
          </div>
        </section>
      )}

      <section className="block">
        <header className="block-head"><h3>On the phone, in Safari</h3></header>
        {!url ? (
          <div>
            <div className="row-actions">
              <button className="primary" disabled={busy} onClick={() => start(false, true)}>Start tests</button>
            </div>
            <p className="muted small">
              Runs every test. Safari shows a certificate warning once: tap Show details, then visit this website. Nothing is installed.
              {" "}If the warning cannot be accepted, <button className="link" disabled={busy} onClick={() => start(false)}>start without the secure page</button>
              {" "}(no camera, microphone, motion or GPS tests).
            </p>
          </div>
        ) : (
          <div className="qr-box">
            {qr && <img src={qr} alt="QR code of the test page address" width={220} height={220} />}
            <div>
              <p className="wifi-line">
                Join the Wi-Fi <b>{ssid ?? (wifiName || "this Mac is on")}</b> on the phone, then scan the code with the camera and open it in Safari.
              </p>
              {!ssid && (
                <label className="field" style={{ marginTop: 0, marginBottom: ".6rem" }}>
                  <span>Wi-Fi network name, as shown in the Mac menu bar (macOS hides it from apps; typed once, remembered)</span>
                  <input value={wifiName} onChange={(e) => rememberWifi(e.target.value)} placeholder="e.g. FRITZ!Box 7590" />
                </label>
              )}
              {secure && <p className="muted small">Safari will warn about the certificate once. Tap Show details, then visit this website. Nothing is installed.</p>}
              <div className="join">
                <div className="join-step"><span className="muted small">Or in Safari, type</span><span className="mono">{shortUrl.replace(/^https?:\/\//, "")}</span></div>
                <div className="join-step"><span className="muted small">then enter the code</span><span className="pin">{pin}</span></div>
              </div>
              <p className="mono small muted">{url}</p>
              <div className="row-actions">
                <button className="primary" disabled={opening} onClick={openOnPhone}>{opening ? "Opening…" : "Open in Safari on the phone"}</button>
                <button onClick={stop}>Stop</button>
              </div>
              {opened
                ? <p className={opened.ok ? "muted small" : "notice error"}>{opened.ok ? "Opened in Safari on the phone." : opened.detail}</p>
                : <p className="muted small">The button needs the cable, the phone unlocked, and Settings → Apps → Safari → Advanced → Web Inspector switched on. It replaces the page in Safari's current tab.</p>}
            </div>
          </div>
        )}
        <div className="subhead">Automatic: the phone measures and decides</div>
        <div className="results">
          {WEB_AUTO.map(([k, label]) => <Result key={k} label={label} r={web[k]} />)}
        </div>
        <div className="subhead">Manual: you judge on the phone, then tap pass or fail</div>
        <div className="results">
          {WEB_MANUAL.map(([k, label]) => <Result key={k} label={label} r={web[k]} />)}
        </div>
      </section>
    </div>
  );
}

function Result({ label, r }: { label: string; r?: { status: string; details?: unknown } }) {
  const d = r?.details && typeof r.details === "object" ? (r.details as Record<string, unknown>) : null;
  const detail = d ? (typeof d.summary === "string" ? d.summary
    : Object.entries(d).filter(([k]) => k !== "samples_raw").map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(", ")) : "";
  return (
    <div className="result">
      <span className="result-label">{label}{detail && <small className="muted"> {detail}</small>}</span>
      <span className={`tag ${r?.status ?? ""}`}>{r ? r.status : "not run"}</span>
    </div>
  );
}
