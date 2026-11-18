import type { Trust, TrustCheck } from "./types";

const ICON: Record<string, string> = {
  pass: "✓", fail: "✕", warn: "!", unknown: "?", manual: "👁", not_checked: "…",
};
const KIND: Record<string, string> = {
  pass: "good", fail: "bad", warn: "warn", unknown: "", manual: "", not_checked: "",
};
function summary(trust: Trust) {
  const blockers = trust.checks.filter((c) => c.severity === "blocker");
  const failed = blockers.filter((c) => c.status === "fail").length;
  const pending = blockers.filter((c) => c.status === "unknown" || c.status === "not_checked").length;
  const passed = blockers.filter((c) => c.status === "pass").length;
  const warns = trust.checks.filter((c) => c.severity !== "blocker" && (c.status === "warn" || c.status === "fail")).length;
  const kind = failed ? "bad" : warns ? "warn" : pending ? "" : "good";
  const head = `${failed} of ${blockers.length} deal-breakers active, ${passed} passed${pending ? `, ${pending} pending` : ""}.`;
  const tail = warns ? ` ${warns} point${warns > 1 ? "s" : ""} worth a look.` : "";
  return { kind, text: head + tail };
}

function Check({ c, onRun, running }: { c: TrustCheck; onRun?: () => void; running?: boolean }) {
  return (
    <div className={`check ${KIND[c.status] ?? ""}`} data-testid={`check-${c.key}`}>
      <div className={`check-icon ${KIND[c.status] ?? ""}`}>{ICON[c.status] ?? "•"}</div>
      <div className="check-body">
        <div className="check-head">
          <span className="check-title">{c.title}</span>
          <span className="muted small">{c.severity === "blocker" ? "Deal-breaker" : c.severity === "warning" ? "Worth a look" : "Information"}</span>
        </div>
        <div>{c.detail}</div>
        {c.action && c.status !== "pass" && <div className="check-action">→ {c.action}</div>}
        {c.runnable && onRun && (
          <button className="primary run" disabled={running} onClick={onRun} data-testid={`run-${c.key}`}>
            {running ? "Running…" : `Run check${c.cost_usd != null ? ` (${c.cost_usd.toFixed(2)} USD${c.provider ? `, ${c.provider}` : ""})` : ""}`}
          </button>
        )}
      </div>
    </div>
  );
}

export function TrustTab({ trust, onRunImei, running, lookupError }:
  { trust: Trust; onRunImei?: () => void; running?: boolean; lookupError?: string | null }) {
  const v = summary(trust);
  const blockers = trust.checks.filter((c) => c.severity === "blocker");
  const others = trust.checks.filter((c) => c.severity !== "blocker");
  return (
    <div className="trust" data-testid="trust">
      <div className={`verdict ${v.kind}`} data-testid="trust-summary">
        <div className="verdict-title">{v.text}</div>
        <div className="muted">Read from the phone. The buying decision stays with you.</div>
      </div>
      {lookupError && <div className="notice error">IMEI lookup failed: {lookupError}</div>}
      <h3 className="group">Deal-breakers</h3>
      {blockers.map((c) => <Check key={c.key} c={c} onRun={onRunImei} running={running} />)}
      <h3 className="group">Worth checking</h3>
      {others.map((c) => <Check key={c.key} c={c} onRun={onRunImei} running={running} />)}
    </div>
  );
}
