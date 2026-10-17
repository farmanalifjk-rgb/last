// Static check: every sidebar link must resolve to a route that main.js renders.
// Usage: node scripts/check-routes.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const sidebar = readFileSync(join(root, "components", "Sidebar.js"), "utf8");
const main = readFileSync(join(root, "main.js"), "utf8");

const linked = new Set();
for (const match of sidebar.matchAll(/(?:route|data-route)\s*[:=]\s*["'`]#(\/[^"'`?]*)/g)) linked.add(match[1]);

const aliases = {};
const aliasBlock = main.match(/ROUTE_ALIASES = \{([\s\S]*?)\};/);
if (aliasBlock) for (const m of aliasBlock[1].matchAll(/"([^"]+)":\s*"([^"]+)"/g)) aliases[m[1]] = m[2];

const handled = new Set([...main.matchAll(/route === "([^"]+)"/g)].map((m) => m[1]));
// Insights page dispatches on two routes via a combined condition.
for (const m of main.matchAll(/route === "([^"]+)" \|\| route === "([^"]+)"/g)) { handled.add(m[1]); handled.add(m[2]); }

let failures = 0;
for (const route of [...linked].sort()) {
  const target = aliases[route] || route;
  const ok = handled.has(target) || target === "/"; // "/" is the dashboard fallback
  if (!ok) failures += 1;
  console.log(`${ok ? "ok  " : "FAIL"} ${route}${target !== route ? ` -> ${target}` : ""}`);
}
console.log(`\n${linked.size - failures}/${linked.size} sidebar routes resolve`);
process.exit(failures ? 1 : 0);
