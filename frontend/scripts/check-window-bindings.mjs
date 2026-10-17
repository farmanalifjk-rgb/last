// Guard against `window.name = identifier;` bindings whose identifier is not
// defined or imported in the same module. main.js imports every page module
// eagerly, so one such ReferenceError at import time blanks the whole app
// (found in Inventory.js and Adjustment.js during the production audit).
// Usage: node scripts/check-window-bindings.mjs
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const walk = (dir, out = []) => {
    for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) walk(full, out);
        else if (full.endsWith(".js")) out.push(full);
    }
    return out;
};

const problems = [];
for (const file of walk(join(root, "src"))) {
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(/^\s*window\.(\w+)\s*=\s*([A-Za-z_$][\w$]*)\s*;/gm)) {
        const id = match[2];
        const declared = new RegExp(
            `(function\\s*\\*?\\s*${id}\\b|(const|let|var|class)\\s+${id}\\b|import[^;]*\\b${id}\\b[^;]*from)`,
            "s",
        ).test(source);
        if (!declared) problems.push(`${relative(root, file)}: window.${match[1]} = ${id} (not defined in this module)`);
    }
}

// Inline handlers (onclick="fn()" in template markup) run in the global scope:
// fn must be assigned to window somewhere, or the button silently throws a
// ReferenceError (the Adjustments export menu, phase 5).
const sources = walk(join(root, "src")).map((file) => [file, readFileSync(file, "utf8")]);
const bound = new Set(sources.flatMap(([, source]) => [...source.matchAll(/window\.(\w+)\s*=/g)].map((m) => m[1])));
const builtins = new Set(["event", "history", "location", "alert", "confirm", "print", "document", "window", "console", "setTimeout", "if", "return"]);
for (const [file, source] of sources) {
    for (const attr of source.matchAll(/\bon(?:click|change|input|submit|keyup|keydown|blur|focus)\s*=\s*"([^"]*)"/g)) {
        for (const call of attr[1].matchAll(/(?:^|;)\s*(?:event\.\w+\(\)\s*;\s*)?([A-Za-z_$][\w$]*)\s*\(/g)) {
            const name = call[1];
            if (!builtins.has(name) && !bound.has(name)) {
                problems.push(`${relative(root, file)}: inline handler calls ${name}() but window.${name} is never assigned`);
            }
        }
    }
}

if (problems.length) {
    console.error(problems.join("\n"));
    console.error(`\n${problems.length} undefined window binding(s)`);
    process.exit(1);
}
console.log("window bindings: all identifiers are defined in their modules; inline handlers resolve");
