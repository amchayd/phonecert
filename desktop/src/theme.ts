// Appearance: "system" follows the Mac, "light" / "dark" pin one. The choice lives in this app's
// localStorage and is applied as data-theme on <html>, which App.css keys its colours on.
export type Theme = "system" | "light" | "dark";
export const THEMES: [Theme, string][] = [["system", "Match the Mac"], ["light", "Light"], ["dark", "Dark"]];
const KEY = "phonecert.theme";

export function savedTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch { return "system"; }
}

export function applyTheme(theme: Theme, remember = true): void {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  if (!remember) return;
  try { localStorage.setItem(KEY, theme); } catch { /* not remembered; still applied for this session */ }
}
