// Shapes of the JSON produced by `phonecert scan --json`. Everything optional:
// each section may be {"error": "..."} when a device service refused.

export interface Device {
  udid: string;
  name: string;
  product_type: string;
  model: string;
  ios_version: string;
  connection: string;
}

export interface WithError {
  error?: string;
}

export interface Battery extends WithError {
  health_pct?: number | null;
  health_source?: string | null;
  grade?: string;
  design_capacity_mah?: number | null;
  current_max_capacity_mah?: number | null;
  cycle_count?: number | null;
  charge_pct?: number | null;
  temperature_c?: number | null;
  battery_serial?: string | null;
  operating_hours?: number | null;
  resistance?: { mohm?: number; high_above_mohm?: number; status?: "ok" | "high"; provisional?: boolean };
  lifetime?: {
    max_temperature_c?: number | null; min_temperature_c?: number | null; avg_temperature_c?: number | null;
    max_full_charge_mah?: number | null; min_full_charge_mah?: number | null; max_pack_voltage_mv?: number | null;
    gauge_resets?: number | null; operating_hours?: number | null;
  };
  last_shutdown?: {
    at?: string | null; charge_pct?: number | null; voltage_mv?: number | null;
    temperature_c?: number | null; unexpected?: boolean;
  };
}

export interface Storage extends WithError {
  capacity_gb?: number | null;
  used_gb?: number | null;
  free_gb?: number | null;
  purgeable_gb?: number | null;
  used_pct?: number | null;
}

export interface PanicLogs extends WithError {
  panic_count?: number;
  last_panic?: string | null;
  days_since_last_panic?: number | null;
  risk?: string;
  low_battery_logs?: number;
  jetsam_events?: number;
  watchdog_resets?: number;
  ota_updates?: { count: number; first?: string | null; last?: string | null };
}

export interface Profiles extends WithError {
  count?: number;
  profiles?: string[];
  mdm_enrolled?: boolean;
  verdict?: string;
}

export interface SimSlot {
  slot: number;
  present: boolean;
  embedded?: boolean | null;
  status?: string | null;
  carrier?: string | null;
  mcc?: string | null;
  mnc?: string | null;
}

export interface Sim {
  summary?: string;
  active_count?: number;
  slots?: SimSlot[];
  tray?: string | null;
  esim?: boolean;
  card_not_recognised?: boolean;
  telephony?: boolean | null;
  baseband_version?: string | null;
  activation?: string | null;
}

export interface Jailbreak extends WithError {
  verdict?: string;
  jailbreak_apps?: string[];
  sideloaded_apps?: string[];
  crash_hints?: string[];
  user_app_count?: number;
}

export interface Camera {
  expected?: boolean | null;
  serial?: string | null;
}

export interface BatteryAge {
  verdict: string;
  operating_hours?: number | null;
  board_built?: string | null;
  battery_built?: string | null;
  phone_age_hours?: number | null;
  ratio?: number | null;
  reasons: string[];
}

export interface Parts extends WithError {
  logic_board?: { serial?: string | null; mlb_serial?: string | null; model_number?: string | null;
                  regulatory_model?: string | null; wifi_module_vendor?: string | null };
  battery?: { serial?: string | null; manufacturer_data?: string | null; auth_passed?: boolean | null;
              trusted?: boolean | null; auth_status?: string | null };
  display?: { panel_id?: string | null; panel_serial?: string | null };
  cameras?: Record<string, Camera>;
  face_id?: { projector_serial?: string | null; self_test_result?: number | null };
  taptic?: { serial?: string | null; firmware?: string | null };
  nand?: { model?: string | null; serial?: string | null; firmware?: string | null };
  speaker?: { attached?: boolean | null; calibrated?: boolean | null };
  flags?: string[];
  battery_age?: BatteryAge;
  build_dates?: BuildDates;
  sensors?: Sensors;
}

export interface Sensors {
  checks: Record<string, { label: string; status: "present" | "found" | "missing" | string; detail?: string; count?: number }>;
  present: number;
  total: number;
  missing: string[];
}

export interface BuildDates {
  verdict: string;
  board_built?: string | null;
  components: { part: string; serial: string; built?: string | null; days_after_board?: number | null; verdict: string }[];
  dated_count: number;
  reasons: string[];
}

export interface TrustCheck {
  key: string;
  title: string;
  status: "pass" | "fail" | "warn" | "unknown" | "manual" | "not_checked" | string;
  severity: "blocker" | "warning" | "info" | string;
  detail: string;
  action?: string | null;
  runnable?: boolean;
  cost_usd?: number | null;
  provider?: string | null;
}

export interface Trust {
  verdict: "blocked" | "warnings" | "incomplete" | "clear" | string;
  blockers: string[];
  warnings: string[];
  unchecked: string[];
  checks: TrustCheck[];
}

export interface ImeiCheck {
  error?: string;
  provider?: string;
  service?: string;
  checked_at?: string;
  cached?: boolean;
  raw_price?: number | null;
  blacklist?: { status: string; detail?: string | null };
  carrier_lock?: { status: string; detail?: string | null; carrier?: string | null };
  find_my?: { status: string; detail?: string | null };
}

export interface TestResult { status: "pass" | "fail" | "skip" | string; details?: unknown; note?: string | null; at?: string }
export interface Tests { web?: Record<string, TestResult>; manual?: Record<string, TestResult>; auto?: Record<string, TestResult>; updated_at?: string }

export interface Report {
  scanned_at: string;
  source?: "tests-only" | string;
  tests?: Tests;
  trust?: Trust;
  imei_check?: ImeiCheck | null;
  saved_to?: string;
  device: {
    name?: string; product_type?: string; model?: string; model_number?: string; region?: string;
    color?: string; serial?: string; imei?: string; imei2?: string; ios_version?: string;
    activation_state?: string; unit_type?: string;
    locked_now?: boolean | null; wifi_mac?: string | null; bluetooth_mac?: string | null;
    timezone?: string | null; build_version?: string | null; hardware_model?: string | null;
  };
  battery: Battery;
  storage: Storage;
  sim?: Sim;
  system: { panic_logs: PanicLogs; jailbreak: Jailbreak; profiles?: Profiles };
  parts: Parts;
}

export interface ReportSummary {
  path: string;
  scanned_at: string;
  serial?: string | null;
  model?: string | null;
  name?: string | null;
  ios_version?: string | null;
  battery_health_pct?: number | null;
  battery_grade?: string | null;
  source?: string;
  tests_done?: number;
}

/** Saved reports come from every version of the scanner: early ones have only device + battery,
 *  later ones add storage, system, parts… Fill the sections a report lacks with empty ones so the
 *  views can read them without checking; they then show "—" / nothing for what was never scanned. */
export function normaliseReport(r: Report): Report {
  const raw = r as Partial<Report>;
  const system = (raw.system ?? {}) as Partial<Report["system"]>;
  return {
    ...r,
    device: raw.device ?? {},
    battery: raw.battery ?? ({} as Battery),
    storage: raw.storage ?? ({} as Storage),
    parts: raw.parts ?? ({} as Parts),
    system: { ...system, panic_logs: system.panic_logs ?? ({} as PanicLogs), jailbreak: system.jailbreak ?? ({} as Jailbreak) },
  };
}

/** `phonecert settings --json`. A saved key never comes back: only `set` and a four-character `hint`. */
export type SettingField = { set: boolean; from_environment: boolean; value?: string; hint?: string | null };
export type Settings = {
  fields: Record<"imeiinfo_key" | "imeiinfo_services" | "sickw_key", SettingField>;
  provider: string | null;
  services: number[];
  default_services: number[];
  check?: { ok: boolean | null; provider: string | null; detail: string; balance?: string | number | null };
};
