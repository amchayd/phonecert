// Renders every saved report in every sidebar section, server-side, and lists the ones that crash.
// Usage (from desktop/): node scripts/render-reports.mjs [reports dir]
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { createServer } from "vite";
import { createElement } from "react";
import { renderToString } from "react-dom/server";

const dir = resolve(process.argv[2] ?? "../reports");
const vite = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "error" });
let failed = 0, rendered = 0;
try {
  const { ReportView, SECTIONS } = await vite.ssrLoadModule("/src/ReportView.tsx");
  const files = readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "imei_cache.json").sort();
  for (const f of files) {
    const report = { ...JSON.parse(readFileSync(join(dir, f), "utf8")), saved_to: join(dir, f) };
    for (const { id } of SECTIONS) {
      try { renderToString(createElement(ReportView, { report, section: id, onReport() {} })); rendered++; }
      catch (e) { failed++; console.log(`FAIL ${f} [${id}]: ${String(e.message).split("\n")[0]}`); }
    }
  }
  console.log(`${rendered} renders ok, ${failed} failed, ${files.length} reports`);
} finally { await vite.close(); }
process.exit(failed ? 1 : 0);
