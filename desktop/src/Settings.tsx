import { useEffect, useState } from "react";
import { api } from "./api";
import type { Settings } from "./types";
import { applyTheme, savedTheme, THEMES, type Theme } from "./theme";

type Name = keyof Settings["fields"];

/** IMEI provider keys and service ids. Stored in the project's .env file; a saved key is never shown again. */
export function SettingsScreen({ onSaved }: { onSaved: () => void }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  // Only what the user typed since the last save. An untouched key field stays out, so it is not overwritten.
  const [draft, setDraft] = useState<Partial<Record<Name, string>>>({});
  const [busy, setBusy] = useState<"save" | "check" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [theme, setTheme] = useState<Theme>(savedTheme());

  useEffect(() => { api.getSettings().then(setSettings).catch((e) => setErr(String(e))); }, []);

  function edit(name: Name, value: string) { setSaved(false); setDraft((d) => ({ ...d, [name]: value })); }

  async function save(changes: Partial<Record<Name, string>>) {
    setBusy("save"); setErr(null);
    try {
      setSettings(await api.saveSettings(changes as Record<string, string>));
      setDraft((d) => Object.fromEntries(Object.entries(d).filter(([k]) => !(k in changes))));
      setSaved(true);
      onSaved();
    } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  }
  async function check() {
    setBusy("check"); setErr(null);
    try { setSettings(await api.checkProvider()); } catch (e) { setErr(String(e)); }
    finally { setBusy(null); }
  }

  const dirty = Object.keys(draft).length > 0;
  const f = settings?.fields;
  const result = settings?.check;

  return (
    <section className="page" data-testid="settings">
      <header className="page-head">
        <h1>Settings</h1>
      </header>

      <section className="block">
        <header className="block-head"><h3>Appearance</h3></header>
        <div className="segmented" role="group" aria-label="Theme" data-testid="theme">
          {THEMES.map(([id, label]) => (
            <button key={id} className={theme === id ? "on" : ""} aria-pressed={theme === id}
                    onClick={() => { setTheme(id); applyTheme(id); }}>{label}</button>
          ))}
        </div>
      </section>

      <section className="block" style={{ marginTop: "1.6rem" }}>
        <header className="block-head"><h3>IMEI checks</h3></header>
        <p className="muted" style={{ marginBottom: ".8rem" }}>Scans are free. The paid checks (blacklist, carrier lock) need a key from one provider, and run only when you press Run check on the Trust page.</p>
      </section>
      {err && <div className="notice error">{err}</div>}
      {!settings && !err && <p className="muted">Loading…</p>}

      {settings && f && (
        <>
          <div className="verdict">
            <div className="verdict-title">{settings.provider ? `Provider in use: ${settings.provider}` : "No IMEI provider set up"}</div>
            <div className="muted">
              {settings.provider === "imei.info" ? `Services called per check: ${settings.services.join(", ")}.`
                : settings.provider ? "imei.info is used first when both keys are saved."
                : "Add a key below. Without one, the Trust page lists the blacklist and carrier lock as not checked."}
            </div>
          </div>

          <section className="block">
            <header className="block-head"><h3>imei.info</h3></header>
            <p className="muted small">Register at dash.imei.info, top up (5 USD minimum), and copy the API key from the dashboard.</p>
            <Secret label="API key" field={f.imeiinfo_key} value={draft.imeiinfo_key} onChange={(v) => edit("imeiinfo_key", v)}
                    onRemove={() => save({ imeiinfo_key: "" })} testid="imeiinfo-key" />
            <label className="field">
              <span>Service ids per check, comma separated (empty = {settings.default_services.join(", ")}: blacklist and lock status)</span>
              <input value={draft.imeiinfo_services ?? f.imeiinfo_services.value ?? ""} placeholder={settings.default_services.join(",")}
                     onChange={(e) => edit("imeiinfo_services", e.target.value)} data-testid="imeiinfo-services" />
            </label>
          </section>

          <section className="block" style={{ marginTop: "1.6rem" }}>
            <header className="block-head"><h3>sickw.com</h3></header>
            <p className="muted small">Alternative provider. One service (61) covers carrier, Find My and blacklist. Used only when no imei.info key is saved.</p>
            <Secret label="API key" field={f.sickw_key} value={draft.sickw_key} onChange={(v) => edit("sickw_key", v)}
                    onRemove={() => save({ sickw_key: "" })} testid="sickw-key" />
          </section>

          <div className="row-actions" style={{ marginTop: "1.2rem" }}>
            <button className="primary" disabled={!dirty || busy !== null} onClick={() => save(draft)} data-testid="save-settings">
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button disabled={!settings.provider || dirty || busy !== null} onClick={check} data-testid="check-provider">
              {busy === "check" ? "Checking…" : "Test the key"}
            </button>
          </div>
          {saved && !dirty && !result && <p className="muted small">Saved.</p>}
          {dirty && settings.provider && <p className="muted small">Save first, then test the key.</p>}
          {result && !dirty && (
            <p className={result.ok === false ? "notice error" : "notice"} data-testid="check-result">{result.detail}</p>
          )}
          <p className="muted small">Keys are kept in the file .env in the PhoneCert folder on this Mac, readable by your user only. Testing a key asks the provider for the account balance and costs nothing.</p>
        </>
      )}
    </section>
  );
}

function Secret({ label, field, value, onChange, onRemove, testid }:
  { label: string; field: Settings["fields"][Name]; value?: string; onChange: (v: string) => void; onRemove: () => void; testid: string }) {
  // A saved key is shown masked with its last characters, never in an input: to change it, remove it and enter the new one.
  if (field.set) {
    return (
      <div className="field">
        <span>{label}</span>
        <span className="field-row">
          <span className="secret mono" data-testid={`${testid}-saved`}>{"•".repeat(16)}{(field.hint ?? "").replace("…", "")}</span>
          {!field.from_environment && <button type="button" onClick={onRemove} data-testid={`${testid}-remove`}>Remove</button>}
        </span>
        {field.from_environment && <span className="small">Set as an environment variable on this Mac; it cannot be changed here.</span>}
      </div>
    );
  }
  return (
    <label className="field">
      <span>{label}</span>
      <input type="password" autoComplete="off" spellCheck={false} value={value ?? ""} placeholder="Paste the key"
             onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </label>
  );
}
