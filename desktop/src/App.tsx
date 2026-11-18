import { useEffect, useState } from "react";
import { api } from "./api";
import type { Device, Report, ReportSummary } from "./types";
import { ReportView, type Section, SECTIONS } from "./ReportView";
import { TestsTab } from "./TestsTab";
import { History } from "./History";
import { SettingsScreen } from "./Settings";
import { HowItWorks } from "./HowItWorks";
import "./App.css";

type View = "scan" | "report" | "history" | "settings" | "help";

export default function App() {
  const [view, setView] = useState<View>("scan");
  const [section, setSection] = useState<Section>("trust");
  const [report, setReport] = useState<Report | null>(null);
  const [scanning, setScanning] = useState<Device | null>(null);
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imeiRunning, setImeiRunning] = useState(false);
  const [imeiError, setImeiError] = useState<string | null>(null);

  // Device polling runs for the whole session so the sidebar pill is always current.
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const found = await api.devices();
        if (alive) setDevices(found);
      } catch {
        if (alive) setDevices([]);
      }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  async function startScan(device: Device) {
    setError(null);
    setImeiError(null);
    setScanning(device);
    try {
      const r = await api.scan();
      setReport(r);
      setSection("trust");
      setView("report");
    } catch (e) {
      setError(String(e));
    } finally {
      setScanning(null);
    }
  }

  async function openReport(summary: ReportSummary) {
    setError(null);
    setImeiError(null);
    try {
      const r = await api.readReport(summary.path);
      setReport({ ...r, saved_to: r.saved_to ?? summary.path });
      setSection("trust");
      setView("report");
    } catch (e) {
      setError(String(e));
    }
  }

  async function runImei() {
    if (!report?.saved_to) return;
    setImeiRunning(true);
    setImeiError(null);
    try {
      const updated = await api.imeiCheck(report.saved_to);
      setReport(updated);
      if (updated.imei_check?.error) setImeiError(updated.imei_check.error);
    } catch (e) {
      setImeiError(String(e));
    } finally {
      setImeiRunning(false);
    }
  }

  const connected = devices?.[0] ?? null;

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">PhoneCert</div>

        <nav className="nav">
          <button className={view === "scan" ? "on" : ""} onClick={() => setView("scan")}>Scan</button>
          <div className="nav-group">
            {SECTIONS.map((s) => (
              <button key={s.id} disabled={!report && s.id !== "tests"}
                      className={view === "report" && section === s.id ? "on" : ""}
                      onClick={() => { setSection(s.id); setView("report"); }}>
                {s.label}
                {s.id === "trust" && report?.trust && <span className={`dot ${trustKind(report.trust.verdict)}`} />}
              </button>
            ))}
          </div>
          <button className={view === "history" ? "on" : ""} onClick={() => setView("history")}>History</button>
          <button className={view === "settings" ? "on" : ""} onClick={() => setView("settings")}>Settings</button>
          <button className={view === "help" ? "on" : ""} onClick={() => setView("help")}>How it works</button>
        </nav>

        <div className={`pill ${connected ? "live" : ""}`} data-testid="device-pill">
          <span className="pill-dot" />
          {connected ? (
            <span><b>{connected.model}</b><br /><small>{connected.name}</small></span>
          ) : (
            <span>No iPhone connected</span>
          )}
        </div>
      </aside>

      <main className="main">
        {error && <div className="notice error" data-testid="error">{error}</div>}

        {view === "scan" && <ScanScreen devices={devices} scanning={scanning} onScan={startScan}
                                        onNoCable={() => { setSection("tests"); setView("report"); }} />}
        {view === "report" && report && (
          <ReportView report={report} section={section} onReport={setReport}
                      onRunImei={report.saved_to ? runImei : undefined} imeiRunning={imeiRunning} imeiError={imeiError} />
        )}
        {view === "report" && !report && section === "tests" && (
          <section className="page">
            <header className="page-head"><h1>Tests</h1></header>
            <TestsTab report={null} onReport={(r) => { setReport(r); }} />
          </section>
        )}
        {view === "help" && <HowItWorks />}
        {view === "settings" && <SettingsScreen onSaved={async () => {
          // A new key changes what Trust can offer: re-run it for the open scan so "Run check" shows up.
          if (!report?.saved_to || report.source === "tests-only") return;
          try { setReport(await api.refreshTrust(report.saved_to)); } catch { /* the open report stays as it is */ }
        }} />}
        {view === "history" && <History onOpen={openReport} onDeleted={(paths) => {
          // The open report was deleted: close it, and stop the test page that writes into it.
          if (report && (paths === "all" || (report.saved_to && paths.includes(report.saved_to)))) {
            setReport(null); api.stopTests().catch(() => {});
          }
        }} />}
      </main>
    </div>
  );
}

function trustKind(v: string) {
  return { blocked: "bad", warnings: "warn", clear: "good" }[v] ?? "";
}

const STEPS = ["Reading device identity", "Battery gauge", "Storage", "Crash logs", "Installed apps", "Parts and serials"];

function ScanScreen({ devices, scanning, onScan, onNoCable }:
  { devices: Device[] | null; scanning: Device | null; onScan: (d: Device) => void; onNoCable: () => void }) {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!scanning) { setStep(0); return; }
    const id = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 2800);
    return () => clearInterval(id);
  }, [scanning]);

  const device = scanning ?? devices?.[0] ?? null;
  const state = scanning ? "scanning" : device ? "ready" : "waiting";

  return (
    <section className="scan" data-testid="scan">
      <div className={`ring ${state}`}>
        <button className="ring-btn" disabled={state !== "ready"} onClick={() => device && onScan(device)}
                aria-label={state === "ready" ? `Scan ${device?.model}` : state}>
          {state === "scanning" ? "Scanning" : state === "ready" ? "Scan" : "Plug in"}
        </button>
      </div>

      {state === "waiting" && (
        <>
          <h1>Connect an iPhone</h1>
          <p className="lead">Plug it in over USB, unlock it, and tap “Trust This Computer” on the phone.</p>
          <p className="muted" style={{ marginTop: "1rem" }}>
            No cable at hand? <button className="link" onClick={onNoCable}>Run the Safari tests and the checklist over Wi-Fi</button>
          </p>
        </>
      )}
      {state === "ready" && device && (
        <>
          <h1>{device.model}</h1>
          <p className="lead">{device.name}, iOS {device.ios_version}. The scan reads the phone over USB and installs nothing.</p>
          {devices && devices.length > 1 && (
            <p className="muted">{devices.length} phones connected; the first one is scanned.</p>
          )}
        </>
      )}
      {state === "scanning" && device && (
        <>
          <h1>Scanning {device.model}</h1>
          <ol className="steps">
            {STEPS.map((s, i) => <li key={s} className={i < step ? "done" : i === step ? "now" : ""}>{s}</li>)}
          </ol>
          <p className="muted">Keep the phone unlocked. About twenty seconds.</p>
        </>
      )}
    </section>
  );
}
