import { invoke } from "@tauri-apps/api/core";
import type { Device, Report, ReportSummary, Settings } from "./types";

// Outside Tauri (plain `pnpm dev` in a browser) the commands do not exist. A small shim serves
// a scrubbed sample report so the UI can be designed and tested with Playwright without a phone.
const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

const DEMO_DEVICE: Device = { udid: "demo", name: "Demo iPhone", product_type: "iPhone14,5", model: "iPhone 13", ios_version: "26.0", connection: "USB" };

const DEMO_SETTINGS: Settings = {
  fields: {
    imeiinfo_key: { set: true, from_environment: false, hint: "…demo" },
    imeiinfo_services: { set: true, from_environment: false, value: "27,8" },
    sickw_key: { set: false, from_environment: false, hint: null },
  },
  provider: "imei.info", services: [27, 8], default_services: [27, 8],
};

async function sample(): Promise<Report> {
  const r = await fetch("/dev/sample-report.json");
  return r.json();
}

const shim = {
  devices: async () => (new URLSearchParams(location.search).get("nodevice") ? [] : [DEMO_DEVICE]),
  scan: async () => { await new Promise((r) => setTimeout(r, 1500)); return sample(); },
  reports: async (): Promise<ReportSummary[]> => {
    const r = await sample();
    return [{ path: "reports/demo.json", scanned_at: r.scanned_at, serial: r.device.serial, model: r.device.model,
              name: r.device.name, ios_version: r.device.ios_version, battery_health_pct: r.battery.health_pct, battery_grade: r.battery.grade }];
  },
  readReport: async (_path: string) => sample(),
  imeiCheck: async (_path: string) => { const r = await sample(); return { ...r, imei_check: { error: "demo mode: no provider" } }; },
  startTests: async (_path: string | null, _open: boolean, https: boolean, _label?: string) =>
    ({ url: `${https ? "https" : "http"}://192.168.1.20:8765/?k=demo`, port: 8765, secure: https, report: "reports/demo.json", ip: "192.168.1.20", ssid: null, short_url: "http://192.168.1.20:8765", pin: "482913" }),
  stopTests: async () => {},
  deleteReport: async (_path: string) => ({ deleted: 1, reports: [] as ReportSummary[] }),
  clearReports: async () => ({ deleted: 1, reports: [] as ReportSummary[] }),
  openOnPhone: async () => ({ ok: false, detail: "demo mode: no phone" }),
  refreshTrust: async (_path: string) => sample(),
  getSettings: async () => DEMO_SETTINGS,
  saveSettings: async (_changes: Record<string, string>) => DEMO_SETTINGS,
  checkProvider: async (): Promise<Settings> => ({ ...DEMO_SETTINGS, check: { ok: false, provider: null, detail: "demo mode: no provider" } }),
  setManualTest: async (_path: string, name: string, status: string, note?: string) => {
    const r = await sample();
    const tests = { web: {}, manual: { [name]: { status, note, at: new Date().toISOString() } } };
    return { ...r, tests };
  },
};

const real = {
  devices: () => invoke<Device[]>("devices"),
  scan: () => invoke<Report>("scan"),
  reports: () => invoke<ReportSummary[]>("reports"),
  readReport: (path: string) => invoke<Report>("read_report", { path }),
  imeiCheck: (path: string) => invoke<Report>("imei_check", { path }),
  startTests: (path: string | null, open: boolean, https: boolean, label?: string) =>
    invoke<{ url: string; port: number; secure?: boolean; report: string; ip?: string; ssid?: string | null; short_url?: string; pin?: string }>("start_tests", { path, open, https, label: label ?? null }),
  stopTests: () => invoke<void>("stop_tests"),
  deleteReport: (path: string) => invoke<{ deleted: number; reports: ReportSummary[] }>("delete_report", { path }),
  clearReports: () => invoke<{ deleted: number; reports: ReportSummary[] }>("clear_reports"),
  openOnPhone: () => invoke<{ ok: boolean; detail: string }>("open_on_phone"),
  refreshTrust: (path: string) => invoke<Report>("refresh_trust", { path }),
  getSettings: () => invoke<Settings>("get_settings"),
  saveSettings: (changes: Record<string, string>) => invoke<Settings>("save_settings", { changes }),
  checkProvider: () => invoke<Settings>("check_provider"),
  setManualTest: (path: string, name: string, status: string, note?: string) =>
    invoke<Report>("set_manual_test", { path, name, status, note: note ?? null }),
};

export const api = inTauri ? real : shim;
