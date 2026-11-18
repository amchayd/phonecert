import { useEffect, useState } from "react";
import { api } from "./api";
import type { ReportSummary } from "./types";

/** Saved scans: open one, delete one, or clear them all. Deleting moves files to the macOS Trash. */
export function History({ onOpen, onDeleted }: { onOpen: (r: ReportSummary) => void; onDeleted: (paths: string[] | "all") => void }) {
  const [items, setItems] = useState<ReportSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // Deleting takes two clicks: the first arms the button ("Delete?"), the second does it.
  const [armed, setArmed] = useState<string | null>(null);   // a report path, or "all"
  useEffect(() => { api.reports().then(setItems).catch(() => setItems([])); }, []);
  useEffect(() => {
    if (!armed) return;
    const id = setTimeout(() => setArmed(null), 4000);        // disarm if the second click never comes
    return () => clearTimeout(id);
  }, [armed]);

  async function remove(target: string) {
    if (armed !== target) { setArmed(target); return; }
    setArmed(null); setErr(null);
    try {
      const res = target === "all" ? await api.clearReports() : await api.deleteReport(target);
      setItems(res.reports);
      onDeleted(target === "all" ? "all" : [target]);
    } catch (e) { setErr(String(e)); }
  }

  return (
    <section className="page" data-testid="history">
      <header className="page-head">
        <h1>History</h1>
        <p className="lead">Every scan is saved on this Mac. Open one to review it or run the paid checks later. Deleted scans go to the Trash.</p>
      </header>
      {err && <div className="notice error">{err}</div>}
      {items === null && <p className="muted">Loading…</p>}
      {items?.length === 0 && <p className="muted">No scans yet. Plug in a phone and scan it.</p>}
      {items && items.length > 0 && (
        <>
          <div className="row-actions">
            <button className={armed === "all" ? "danger on" : "danger"} data-testid="clear-all" onClick={() => remove("all")}>
              {armed === "all" ? `Click again to delete all ${items.length} scans` : "Clear all"}
            </button>
          </div>
          <table className="list">
            <thead><tr><th>When</th><th>Phone</th><th>Serial</th><th>Battery</th><th></th></tr></thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.path} onClick={() => onOpen(r)}>
                  <td>{r.scanned_at?.replace("T", " ").slice(0, 16)}</td>
                  <td>{r.model ?? (r.source === "tests-only" ? "Tests only, no cable" : "Unknown")}<br /><small className="muted">{r.name}</small></td>
                  <td className="mono">{r.serial ?? "—"}</td>
                  <td>{r.battery_health_pct != null ? `${r.battery_health_pct}%` : "—"}
                    {r.battery_grade && <small className="muted"> {r.battery_grade}</small>}
                    {r.tests_done ? <small className="muted">, {r.tests_done} tests</small> : null}</td>
                  <td className="row-buttons">
                    <button>Open</button>
                    <button className={armed === r.path ? "danger on" : "danger"} data-testid="delete-scan"
                            onClick={(e) => { e.stopPropagation(); remove(r.path); }}>
                      {armed === r.path ? "Delete?" : "Delete"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
