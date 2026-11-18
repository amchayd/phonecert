import { useState } from "react";
import { api } from "./api";
import type { Report } from "./types";

// Checks only a person can do; keys match webtests.MANUAL_TESTS in the Python core.
export const MANUAL: [string, string][] = [
  ["buttons", "Buttons and switches"], ["face_id", "Face ID unlock and attention"], ["true_tone", "True Tone toggle present"],
  ["cameras", "Cameras and flash"], ["earpiece", "Earpiece and top mic on a call"], ["cellular", "Call and data"],
  ["bluetooth", "Bluetooth pairs"], ["nfc", "Apple Pay / NFC tap sheet"], ["water_indicator", "Liquid indicator in SIM tray"],
  ["body", "Body and glass"],
];

export function ChecklistTab({ report, onReport }: { report: Report; onReport: (r: Report) => void }) {
  const path = report.saved_to ?? null;
  const [err, setErr] = useState<string | null>(null);
  const man = report.tests?.manual ?? {};
  const done = MANUAL.filter(([k]) => man[k]).length;
  const failed = MANUAL.filter(([k]) => man[k]?.status === "fail").length;

  async function mark(name: string, status: string) {
    if (!path) { setErr("This report has no file to save into. Open it from History and try again."); return; }
    setErr(null);
    // The CLI prints the report file as stored, which has no saved_to: keep the path or the next click has no report.
    try { onReport({ ...(await api.setManualTest(path, name, status)), saved_to: path }); } catch (e) { setErr(String(e)); }
  }

  return (
    <div className="tests" data-testid="checklist">
      <div className="verdict">
        <div className="verdict-title">{done} of {MANUAL.length} checked{failed ? `, ${failed} failed` : ""}</div>
        <div className="muted">Checks you do by hand with the phone in front of you. No cable or test page needed.</div>
      </div>
      {err && <div className="notice error">{err}</div>}
      <section className="block">
        <div className="results">
          {MANUAL.map(([k, label]) => (
            <div className="result" key={k}>
              <span className="result-label">{label}</span>
              <span className={`tag ${man[k]?.status ?? ""}`}>{man[k] ? man[k].status : "not checked"}</span>
              <span className="result-actions">
                <button className={man[k]?.status === "pass" ? "pass on" : "pass"} onClick={() => mark(k, "pass")}>Pass</button>
                <button className={man[k]?.status === "fail" ? "fail on" : "fail"} onClick={() => mark(k, "fail")}>Fail</button>
                <button onClick={() => mark(k, "skip")}>Skip</button>
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
