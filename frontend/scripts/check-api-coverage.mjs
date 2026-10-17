#!/usr/bin/env node
// Checks that the API explorer plan places every in-scope operation in exactly one
// section, and that every section points at an operation that exists in the map.
// Run from frontend/: node scripts/check-api-coverage.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { planSections } from "../src/js/api-map/plan.mjs";

const mapPath = fileURLToPath(new URL("../src/js/api-map/operations.json", import.meta.url));
const ops = JSON.parse(readFileSync(mapPath, "utf8"));
const keys = Object.keys(ops);
const failures = [];

const { sections } = planSections(ops);

const seen = new Map();
for (const section of sections) {
    for (const key of section.keys) {
        seen.set(key, (seen.get(key) || 0) + 1);
        if (!ops[key]) failures.push(`${section.id}: ${key} is not in operations.json`);
    }
    if (section.kind === "resource") {
        for (const action of [...section.cfg.rowActions, ...section.cfg.toolbar]) {
            const key = `${action.method} ${section.cfg.base}${action.suffix}`;
            if (!ops[key]) failures.push(`${section.id}: action ${key} is not in operations.json`);
        }
    }
    if (section.kind === "group" && section.items.length === 0) failures.push(`${section.id}: empty group`);
}

for (const key of keys) {
    const n = seen.get(key) || 0;
    if (n !== 1) failures.push(`${key} planned ${n} times (expected 1)`);
}

const byKind = {};
for (const s of sections) byKind[s.kind] = (byKind[s.kind] || 0) + 1;
console.log(`operations: ${keys.length}`);
console.log(`sections: ${sections.length} ${JSON.stringify(byKind)}`);
console.log(`planned operations: ${seen.size}`);

if (failures.length) {
    console.error(`FAIL: ${failures.length} problem(s)`);
    for (const f of failures.slice(0, 50)) console.error(`  - ${f}`);
    process.exit(1);
}
console.log("PASS: every operation is planned exactly once");
