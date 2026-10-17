/**
 * Schema-driven form fields. A field spec comes from operations.json:
 *   { name, type, required, label, enum?, nullable?, maxLength?, default? }
 * where type is one of: string, integer, number, boolean, enum, date,
 * date-time, json. Overrides from a hub config can add select options, help
 * text, or a different input type (for example csv, textarea).
 */
import { esc, field, fieldGrid, toast } from "../../shared/ui.js";
import { listOp } from "./ops.js";
import { RAW_BODY, humanize } from "./plan.mjs";

export { humanize };

const HIDDEN_TYPES = new Set();

/** Merge schema specs with declared overrides. Keeps schema order, then appends extras. */
export function mergeSpecs(schemaFields = [], overrides = {}, extra = []) {
    const byName = new Map();
    for (const spec of schemaFields) byName.set(spec.name, { ...spec });
    for (const spec of extra) byName.set(spec.name, { ...(byName.get(spec.name) || {}), ...spec });
    const out = [];
    for (const [name, spec] of byName) {
        const o = overrides[name] || {};
        const merged = { ...spec, ...o, name };
        merged.label = merged.label || humanize(name);
        if (merged.type === "enum" && !merged.options) {
            merged.options = (merged.enum || []).map((v) => ({ value: v, label: humanize(String(v)) }));
        }
        if (HIDDEN_TYPES.has(merged.type)) continue;
        out.push(merged);
    }
    for (const [name, o] of Object.entries(overrides)) {
        if (!byName.has(name)) out.push({ name, label: o.label || humanize(name), type: o.type || "string", ...o });
    }
    return out;
}

/** Load option lists for reference fields declared as { refPath, refLabel }. */
export async function resolveRefs(specs) {
    await Promise.all(specs.map(async (spec) => {
        if (!spec.refPath) return;
        try {
            const data = await listOp(spec.refPath.split("?")[0], Object.fromEntries(new URLSearchParams(spec.refPath.split("?")[1] || "")));
            const label = spec.refLabel || "name";
            spec.options = [{ value: "", label: spec.required ? "Choose…" : "None" }, ...data.results.map((row) => ({
                value: row.id,
                label: `${row[label] ?? row.id}${row.sku ? ` (${row.sku})` : ""}`,
            }))];
            spec.type = "integer";
        } catch {
            spec.options = [];
        }
    }));
    return specs;
}

function valueText(spec, value) {
    if (value === null || value === undefined) return "";
    if (spec.type === "json" || typeof value === "object") return JSON.stringify(value, null, 2);
    if (spec.type === "csv" && Array.isArray(value)) return value.join(", ");
    return String(value);
}

/** HTML for one spec. Values come from `values` (object keyed by field name). */
export function fieldHtml(spec, values = {}) {
    const value = values[spec.name] !== undefined ? values[spec.name] : spec.default;
    const common = { name: spec.name, label: spec.label, required: !!spec.required, help: spec.help || "", full: !!spec.full, placeholder: spec.placeholder || "" };
    if (spec.type === "boolean") {
        return field({ ...common, type: "checkbox", value: !!value });
    }
    if (spec.type === "json") {
        return field({ ...common, type: "textarea", value: valueText(spec, value), full: true, placeholder: spec.placeholder || "{}", help: spec.help || "Enter valid JSON." });
    }
    if (spec.type === "textarea") {
        return field({ ...common, type: "textarea", value: valueText(spec, value), full: true });
    }
    if (spec.type === "csv") {
        return field({ ...common, value: valueText(spec, value), help: spec.help || "Separate values with commas." });
    }
    if (spec.options) {
        const options = spec.options.map((o) => ({ value: o.value, label: o.label }));
        if (!spec.required && !options.some((o) => o.value === "")) options.unshift({ value: "", label: "None" });
        return field({ ...common, type: "select", value: value ?? "", options });
    }
    const inputType = {
        integer: "number", number: "number", date: "date", "date-time": "datetime-local", password: "password",
    }[spec.type] || "text";
    const step = spec.type === "integer" ? "1" : spec.type === "number" ? "any" : undefined;
    return field({ ...common, type: inputType, value: valueText(spec, value), step });
}

export function fieldsHtml(specs, values = {}) {
    return fieldGrid(specs.map((spec) => fieldHtml(spec, values)));
}

/** Read the form back into a request body. Throws Error with a user-facing message. */
export function readBody(form, specs, { includeEmpty = false } = {}) {
    // A single raw JSON field stands for the whole request body (schema has no field list).
    if (specs.length === 1 && specs[0].name === RAW_BODY) {
        const raw = String(form.elements.namedItem(RAW_BODY)?.value ?? "").trim();
        if (!raw) return undefined;
        try { return JSON.parse(raw); } catch { throw new Error("Request body must be valid JSON."); }
    }
    const body = {};
    for (const spec of specs) {
        const el = form.elements.namedItem(spec.name);
        if (!el) continue;
        if (spec.type === "boolean") {
            body[spec.name] = !!el.checked;
            continue;
        }
        const raw = String(el.value ?? "").trim();
        if (raw === "") {
            if (spec.required) throw new Error(`${spec.label} is required.`);
            if (spec.nullable || includeEmpty) body[spec.name] = null;
            continue;
        }
        let value = raw;
        if (spec.type === "integer") {
            value = Number.parseInt(raw, 10);
            if (Number.isNaN(value)) throw new Error(`${spec.label} must be a whole number.`);
        } else if (spec.type === "number") {
            value = Number(raw);
            if (!Number.isFinite(value)) throw new Error(`${spec.label} must be a number.`);
        } else if (spec.type === "json") {
            try { value = JSON.parse(raw); } catch { throw new Error(`${spec.label} must be valid JSON.`); }
        } else if (spec.type === "csv") {
            value = raw.split(",").map((v) => v.trim()).filter(Boolean);
        }
        body[spec.name] = value;
    }
    return body;
}

/** Form values for a plain query-string object (used by report filters). */
export function queryFromForm(form, specs) {
    const query = {};
    for (const spec of specs) {
        const el = form.elements.namedItem(spec.name);
        const raw = el ? String(el.value ?? "").trim() : "";
        if (raw !== "") query[spec.name] = raw;
    }
    return query;
}

export function notifySaved(message = "Saved.") {
    toast(message, "success");
}
