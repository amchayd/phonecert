import type { ReactNode } from "react";
import type { BatteryAge, Report } from "./types";
import { normaliseReport } from "./types";
import { TrustTab } from "./TrustTab";
import { TestsTab } from "./TestsTab";
import { ChecklistTab } from "./ChecklistTab";

export type Section = "trust" | "device" | "battery" | "parts" | "system" | "tests" | "checklist";
export const SECTIONS: { id: Section; label: string }[] = [
  { id: "trust", label: "Trust" }, { id: "device", label: "Device" }, { id: "battery", label: "Battery" },
  { id: "parts", label: "Parts" }, { id: "system", label: "System" }, { id: "tests", label: "Tests" },
  { id: "checklist", label: "Checklist" },
];

const na = (v: unknown, unit = "") => (v === null || v === undefined || v === "" ? "n/a" : `${v}${unit}`);

function Row({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  const shown = value === null || value === undefined || value === "" ? "n/a" : value;
  return (
    <div className="row">
      <span className="label">{label}</span>
      <span className={mono ? "value mono" : "value"}>{shown}</span>
    </div>
  );
}

function Section({ title, badge, badgeKind, error, children }:
  { title: string; badge?: string; badgeKind?: string; error?: string; children?: React.ReactNode }) {
  return (
    <section className="block">
      <header className="block-head">
        <h3>{title}</h3>
        {badge && <span className={`badge ${badgeKind ?? ""}`}>{badge}</span>}
      </header>
      {error ? <p className="muted">Could not read: {error}</p> : children}
    </section>
  );
}

function Stat({ label, value, kind }: { label: string; value: string; kind?: string }) {
  return (
    <div className={`stat ${kind ?? ""}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

const fmtH = (h: number) => `${Math.round(h).toLocaleString("en-US")} h`;
const fmtDate = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const ageText: Record<string, string> = {
  normal: "The battery has been in this phone since it was built.",
  clarify: "The battery is younger than the phone — ask the seller about a replacement.",
  unknown: "Not enough data on this model to date the battery.",
};

function BatteryAgeBlock({ age }: { age: BatteryAge }) {
  const pct = age.ratio != null ? Math.min(100, Math.round(age.ratio * 100)) : null;
  return (
    <div className="age" data-testid="battery-age">
      <div className="age-head">
        <span className="label">Age</span>
        <span className={`badge ${ageKind[age.verdict] ?? ""}`}>{age.verdict}</span>
      </div>
      {pct != null && (
        <>
          <div className="bar"><div className={ageKind[age.verdict]} style={{ width: `${pct}%` }} /></div>
          <div className="age-line">
            <span>Operated <b>{fmtH(age.operating_hours!)}</b> of {fmtH(age.phone_age_hours!)} since the board was built</span>
            <b>{pct}%</b>
          </div>
        </>
      )}
      <div className="age-line muted small">
        <span>
          {age.board_built ? `Board built ${fmtDate(age.board_built)}` : "Board build date unknown"}
          {age.battery_built ? `, battery built ${fmtDate(age.battery_built)}` : ""}
          {pct == null && age.operating_hours != null ? `, operated ${fmtH(age.operating_hours)}` : ""}
        </span>
      </div>
      <div className="muted small">{ageText[age.verdict]}</div>
    </div>
  );
}

const gradeKind: Record<string, string> = { Excellent: "good", Good: "good", Average: "warn", Poor: "bad" };
const riskKind: Record<string, string> = { none: "good", low: "warn", high: "bad" };
const jbKind: Record<string, string> = { none: "good", suspicious: "warn", likely: "bad" };
const ageKind: Record<string, string> = { normal: "good", clarify: "warn", unknown: "" };
const profKind: Record<string, string> = { clean: "good", profiles: "warn", mdm: "bad" };
const bdKind: Record<string, string> = { consistent: "good", check: "bad", unknown: "" };
const bdText: Record<string, string> = {
  consistent: "Every datable part was built before the board — factory original.",
  check: "A part was built after the board: it was fitted later.",
  unknown: "No part serial on this model encodes a build date.",
};
const fmtMonth = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { month: "short", year: "numeric" });
const fmtDateTime = (iso: string) => iso.replace("T", " ");

const CAMERA_PART: Record<string, string> = {
  back: "camera back", back_ultrawide: "camera ultrawide", back_tele: "camera tele",
  front: "camera front", front_ir: "camera front IR",
};

export function ReportView({ report: stored, section, onRunImei, imeiRunning, imeiError, onReport }:
  { report: Report; section: Section; onRunImei?: () => void; imeiRunning?: boolean; imeiError?: string | null;
    onReport: (r: Report) => void }) {
  const tab = section;
  const report = normaliseReport(stored);   // old scans lack whole sections
  const { device: d, battery: b, storage: s, system, parts: p } = report;
  const pl = system.panic_logs, jb = system.jailbreak, pr = system.profiles, sm = report.sim;
  const lt = b.lifetime, sd = b.last_shutdown;
  const age = p.battery_age;
  const bdz = p.build_dates;
  const flags = [...(p.flags ?? []), ...(age?.reasons ?? []), ...(bdz?.reasons ?? [])];
  const builtOf = (part: string) => bdz?.components.find((c) => c.part === part);
  const withDate = (serial: string | null | undefined, part: string) => {
    const c = builtOf(part);
    if (!serial) return null;
    if (!c?.built) return serial;
    return <>{serial} <span className={`built ${c.verdict === "newer" ? "bad" : ""}`}>built {fmtMonth(c.built)}</span></>;
  };
  const batteryAuth = p.battery?.auth_passed && p.battery?.trusted ? "Genuine"
    : p.battery?.auth_passed === false ? "Failed" : "n/a";

  const titles: Record<Section, string> = { trust: "Trust", device: "Device", battery: "Battery", parts: "Parts", system: "System", tests: "Tests", checklist: "Checklist" };
  return (
    <div className="page report" data-testid="report">
      <header className="page-head device-head">
        <div>
          <h1>{d.model ?? d.product_type ?? d.name ?? "Phone"}</h1>
          <p className="lead">
            {report.source === "tests-only"
              ? `Tests without the cable, started ${report.scanned_at.replace("T", " ").slice(0, 16)}. No scan data yet.`
              : `${d.name}, iOS ${d.ios_version}. Model ${d.model_number} ${d.region}, scanned ${report.scanned_at.replace("T", " ").slice(0, 16)}.`}
          </p>
        </div>
        <div className="head-stats">
          <Stat label="Battery" value={b.health_pct != null ? `${b.health_pct}%` : "—"} kind={gradeKind[b.grade ?? ""]} />
          <Stat label="Storage" value={s.capacity_gb != null ? `${s.capacity_gb} GB` : "—"} />
          <Stat label="Deal-breakers" value={report.trust ? `${report.trust.blockers.length} active` : "—"}
                kind={report.trust ? (report.trust.blockers.length ? "bad" : report.trust.unchecked.length ? "" : "good") : ""} />
        </div>
      </header>
      <h2 className="section-title">{titles[section]}</h2>

      {tab === "trust" && (report.trust
        ? <TrustTab trust={report.trust} onRunImei={report.saved_to ? onRunImei : undefined} running={imeiRunning} lookupError={imeiError} />
        : <p className="muted">No trust data in this report (older scan).</p>)}

      {tab === "tests" && <TestsTab report={report} onReport={onReport} />}
      {tab === "checklist" && <ChecklistTab report={report} onReport={onReport} />}

      {tab === "parts" && flags.length > 0 && (
        <div className="banner warn" data-testid="flags">
          <b>Check before buying</b>
          <ul>{flags.map((f) => <li key={f}>{f}</li>)}</ul>
        </div>
      )}

      <div className="sections">
        {tab === "device" && <Section title="Identity">
          <Row label="Serial" value={d.serial} mono />
          <Row label="IMEI" value={d.imei} mono />
          <Row label="Unit type" value={d.unit_type} />
          <Row label="Activation" value={d.activation_state} />
          <Row label="Lock state at scan" value={d.locked_now == null ? null : d.locked_now ? "locked" : "unlocked"} />
          <Row label="Time zone" value={d.timezone} />
          <Row label="iOS build" value={d.build_version} />
          <Row label="Wi-Fi MAC" value={d.wifi_mac} mono />
          <Row label="Bluetooth MAC" value={d.bluetooth_mac} mono />
          {sm && (
            <>
              <div className="subhead">SIM & carrier</div>
              <Row label="SIM" value={<>{sm.summary}{sm.card_not_recognised && <> <span className="badge warn">card not recognised</span></>}</>} />
              {sm.slots?.map((sl) => (
                <Row key={sl.slot} label={`Slot ${sl.slot}`}
                     value={sl.present
                       ? `${sl.embedded ? "eSIM" : "physical"}${sl.carrier ? `, ${sl.carrier}` : ""}${sl.mcc ? ` (${sl.mcc}/${sl.mnc})` : ""}`
                       : (sl.status ?? "empty")} />
              ))}
              <Row label="Tray" value={sm.tray} />
              <Row label="Baseband" value={sm.baseband_version} />
            </>
          )}
        </Section>}

        {tab === "battery" && <Section title="Health" badge={b.grade} badgeKind={gradeKind[b.grade ?? ""]} error={b.error}>
          <Row label="Health" value={b.health_pct != null ? `${b.health_pct}% (${b.health_source})` : null} />
          <Row label="Capacity" value={b.design_capacity_mah ? `${b.current_max_capacity_mah} / ${b.design_capacity_mah} mAh` : null} />
          <Row label="Cycles" value={b.cycle_count} />
          {b.resistance?.mohm != null && (
            <Row label="Internal resistance"
                 value={<>
                   {b.resistance.mohm} mΩ
                   {b.resistance.status === "high" && <> <span className="badge bad">high</span></>}
                   <small className="muted"> the battery's own figure, readable at any charge level; high above {b.resistance.high_above_mohm} (provisional)</small>
                 </>} />
          )}
          <Row label="Charge" value={na(b.charge_pct, "%")} />
          <Row label="Temperature" value={b.temperature_c != null ? `${b.temperature_c} °C` : null} />
          <Row label="Authentication" value={batteryAuth} />
          <Row label="Serial" value={b.battery_serial} mono />
          {lt && Object.keys(lt).length > 0 && (
            <>
              <div className="subhead">Lifetime</div>
              <Row label="Temperature range" value={lt.min_temperature_c != null ? `${lt.min_temperature_c} – ${lt.max_temperature_c} °C (avg ${na(lt.avg_temperature_c)})` : null} />
              <Row label="Peak full charge" value={lt.max_full_charge_mah != null ? `${lt.max_full_charge_mah} mAh (lowest ${na(lt.min_full_charge_mah)})` : null} />
              <Row label="Gauge resets" value={lt.gauge_resets} />
            </>
          )}
          {sd && sd.at && (
            <Row label="Last shutdown"
                 value={<>
                   {fmtDateTime(sd.at)} at {na(sd.charge_pct, "%")}, {na(sd.voltage_mv, " mV")}
                   {sd.unexpected && <> <span className="badge bad">unexpected</span></>}
                 </>} />
          )}
          {age && <BatteryAgeBlock age={age} />}
        </Section>}

        {tab === "device" && <Section title="Storage" error={s.error}>
          <Row label="Capacity" value={s.capacity_gb != null ? `${s.capacity_gb} GB` : null} />
          <Row label="Used" value={s.used_gb != null ? `${s.used_gb} GB (${s.used_pct}%)` : null} />
          <Row label="Free" value={s.free_gb != null ? `${s.free_gb} GB` : null} />
          {s.purgeable_gb ? <Row label="Purgeable (iCloud caches)" value={`${s.purgeable_gb} GB`} /> : null}
          {s.used_pct != null && <div className="bar"><div style={{ width: `${s.used_pct}%` }} /></div>}
        </Section>}

        {tab === "system" && <Section title="Stability" badge={pl.risk ? `panic risk ${pl.risk}` : undefined} badgeKind={riskKind[pl.risk ?? ""]}>
          {pl.error ? <p className="muted">Panic logs: {pl.error}</p> : (
            <>
              <Row label="Kernel panics" value={pl.panic_count} />
              <Row label="Last panic" value={pl.last_panic ? `${pl.last_panic} (${pl.days_since_last_panic} days ago)` : "none"} />
              <Row label="Low-battery logs" value={pl.low_battery_logs} />
              <Row label="Memory-pressure kills" value={pl.jetsam_events} />
              <Row label="Watchdog resets" value={pl.watchdog_resets} />
              <Row label="iOS updates" value={pl.ota_updates ? `${pl.ota_updates.count}${pl.ota_updates.last ? `, last ${pl.ota_updates.last}` : ""}` : null} />
            </>
          )}
          {pr && (pr.error ? <p className="muted">Profiles: {pr.error}</p> : (
            <>
              <Row label="Profiles / MDM" value={<span className={`badge ${profKind[pr.verdict ?? ""] ?? ""}`}>{pr.mdm_enrolled ? "MDM enrolled" : pr.verdict}</span>} />
              {pr.profiles?.map((n) => <div className="muted small" key={n}>{n}</div>)}
            </>
          ))}
          {jb.error ? <p className="muted">Jailbreak: {jb.error}</p> : (
            <>
              <Row label="Jailbreak" value={<span className={`badge ${jbKind[jb.verdict ?? ""]}`}>{jb.verdict}</span>} />
              <Row label="User apps" value={jb.user_app_count} />
              {[...(jb.jailbreak_apps ?? []), ...(jb.sideloaded_apps ?? []), ...(jb.crash_hints ?? [])].map((h) => (
                <div className="muted small" key={h}>{h}</div>
              ))}
            </>
          )}
        </Section>}

        {tab === "parts" && <Section title="Components" error={p.error}
                 badge={bdz ? `parts ${bdz.verdict}` : undefined} badgeKind={bdKind[bdz?.verdict ?? ""]}>
          <Row label="Logic board (MLB)" value={p.logic_board?.mlb_serial ? <>{p.logic_board.mlb_serial}{bdz?.board_built && <span className="built">built {fmtMonth(bdz.board_built)}</span>}</> : null} mono />
          <Row label="Display panel" value={withDate(p.display?.panel_serial, "display")} mono />
          {Object.entries(p.cameras ?? {}).map(([k, c]) => (
            <Row key={k} label={`Camera ${k.replace("_", " ")}`}
                 value={c.serial ? withDate(c.serial, CAMERA_PART[k] ?? k) : (c.expected ? "missing" : "n/a")} mono />
          ))}
          <Row label="Face ID projector" value={p.face_id?.projector_serial} mono />
          <Row label="Face ID self-test" value={p.face_id?.self_test_result === 0 ? "pass (0)" : p.face_id?.self_test_result} />
          <Row label="Taptic Engine" value={withDate(p.taptic?.serial, "taptic engine")} mono />
          <Row label="NAND" value={p.nand?.model ? `${p.nand.model}  ${p.nand.serial}` : null} mono />
          <Row label="Speaker amp" value={p.speaker?.attached ? (p.speaker.calibrated ? "attached, calibrated" : "attached") : p.speaker?.attached === false ? "not attached" : null} />
          {bdz && <div className="muted small" style={{ marginTop: ".6rem" }}>{bdText[bdz.verdict]} {bdz.dated_count > 0 && `(${bdz.dated_count} parts dated)`}</div>}
        </Section>}
        {tab === "parts" && p.sensors && (
          <Section title="Hardware present" badge={`${p.sensors.present} of ${p.sensors.total}`}
                   badgeKind={p.sensors.missing.length ? "bad" : "good"}>
            <p className="muted small" style={{ marginBottom: ".5rem" }}>
              Drivers iOS found and initialised at boot. Presence only; the interactive tests check performance.
            </p>
            <div className="chips">
              {Object.entries(p.sensors.checks).map(([k, c]) => (
                <span key={k} className={`chip ${c.status}`} title={c.detail ?? ""}>{c.label}</span>
              ))}
            </div>
          </Section>
        )}
      </div>
      {report.saved_to && <p className="muted small saved">Saved as {report.saved_to.split("/").pop()}</p>}
    </div>
  );
}
