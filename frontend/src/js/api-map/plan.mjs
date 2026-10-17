/**
 * Pure planner for the API explorer. No DOM and no imports, so scripts/check-api-coverage.mjs
 * can run it under Node against operations.json.
 *
 * planSections(ops) places every operation in exactly one section:
 *   resource   a list path C with item paths C{id}/ (or a POST on C):
 *              list, create, edit, delete, plus row actions on C{id}/x/ and toolbar actions on Cx/
 *   settings   a singleton object: GET C with PUT or PATCH C, no items
 *   group      every other operation, grouped per domain into one section:
 *              queries (GET), downloads (export GET), actions (POST/PUT/PATCH/DELETE),
 *              records (paths with placeholders), uploads (multipart)
 */
export const RAW_BODY = "__body__";

/** Bodies the schema does not describe, or where a hand-checked field list is needed. */
export const FIELD_HINTS = {
    "POST /api/draft-order/customer/": [
        { name: "draft_id", type: "integer", required: true, label: "Draft order ID" },
        { name: "customer_id", type: "integer", label: "Customer ID", help: "Leave empty to clear the customer." },
    ],
    "POST /api/catalog/batches/fefo-allocate/": [
        { name: "product_id", type: "integer", required: true, label: "Product ID" },
        { name: "quantity", type: "number", required: true, label: "Quantity" },
        { name: "kind", type: "string", label: "Kind", default: "sale" },
        { name: "order", type: "integer", label: "Order ID" },
        { name: "reference", type: "string", label: "Reference" },
    ],
    "POST /api/catalog/batches/{id}/recall/": [
        { name: "reason", type: "string", label: "Reason" },
    ],
    "POST /api/tax/preview-line/": [
        { name: "product_id", type: "integer", required: true, label: "Product ID" },
        { name: "customer_id", type: "integer", label: "Customer ID" },
        { name: "subtotal", type: "number", required: true, label: "Subtotal" },
    ],
};

const ACRONYMS = { api: "API", sms: "SMS", i18n: "i18n", fbr: "FBR", saas: "SaaS", rbac: "RBAC", pos: "POS", kpi: "KPI", kpis: "KPIs", csv: "CSV", pdf: "PDF", sku: "SKU", ai: "AI", fefo: "FEFO", gl: "GL", id: "ID", ids: "IDs", url: "URL", hr: "HR", sso: "SSO", ui: "UI", vat: "VAT", fiscal: "fiscal" };

export function humanize(text) {
    const words = String(text).replace(/[_-]+/g, " ").trim().split(/\s+/).filter(Boolean);
    return words.map((w, i) => {
        const lower = w.toLowerCase();
        if (ACRONYMS[lower]) return ACRONYMS[lower];
        return i === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower;
    }).join(" ");
}

export function singular(text) {
    const h = humanize(text);
    if (/ies$/i.test(h)) return `${h.slice(0, -3)}y`;
    if (/(ss|us|is)$/i.test(h)) return h;
    if (/s$/i.test(h)) return h.slice(0, -1);
    return h;
}

export const domainOf = (path) => path.split("/")[2] || "root";
const hasPlaceholder = (path) => /\{\w+\}/.test(path);
const placeholders = (path) => [...path.matchAll(/\{(\w+)\}/g)].map((m) => m[1]);
const keyOf = (op) => `${op.method} ${op.path}`;
const isDanger = (method, path) => method === "DELETE" || /\/(revoke|recall|cancel|regenerate|reset|clear|delete|remove|rebuild|optimize|unlock)/.test(path);

/** Request-body fields for an operation: hint, raw JSON when the schema has no fields, or the schema body. */
export function fieldsForOp(op) {
    const hint = bodyFieldsFor(op);
    return hint.fields;
}

function bodyFieldsFor(op) {
    const key = keyOf(op);
    if (FIELD_HINTS[key]) return { fields: FIELD_HINTS[key] };
    if (op.bodyGeneric) return { fields: [{ name: RAW_BODY, type: "json", label: "Request body (JSON)", placeholder: "{}", help: "The schema does not describe this body. Enter the JSON to send." }] };
    if (op.body && op.body.length) return { fields: op.body };
    return {};
}

/** Action descriptor used by resource row/toolbar actions and group actions. */
function actionDescriptor(op, base, kind) {
    const suffix = op.path.slice(base.length);
    const name = kind === "row" ? suffix.replace(/^\{id\}\//, "").replace(/\/$/, "") : suffix.replace(/\/$/, "");
    const hint = bodyFieldsFor(op);
    return {
        label: humanize(name),
        method: op.method,
        suffix,
        show: true,
        danger: isDanger(op.method, op.path),
        confirm: isDanger(op.method, op.path) ? `Run "${humanize(name)}" now? This may not be undone.` : undefined,
        ...(hint.fields ? { fields: hint.fields } : {}),
    };
}

export function planSections(ops) {
    const list = Object.values(ops);
    const byKey = new Map(list.map((o) => [keyOf(o), o]));
    const get = (method, path) => byKey.get(`${method} ${path}`);
    const claimed = new Map(); // key -> section id

    const claim = (op, sectionId) => {
        const key = keyOf(op);
        if (claimed.has(key)) throw new Error(`Operation planned twice: ${key} (${claimed.get(key)} and ${sectionId})`);
        claimed.set(key, sectionId);
        return key;
    };

    // Resources: a placeholder-free list path with item paths or a create.
    const resourceBases = [];
    for (const op of list) {
        if (op.method !== "GET" || hasPlaceholder(op.path) || !op.path.endsWith("/")) continue;
        const hasItem = !!get("GET", `${op.path}{id}/`) || list.some((o) => o.path === `${op.path}{id}/`);
        if (hasItem || get("POST", op.path)) resourceBases.push(op.path);
    }
    const resourceSet = new Set(resourceBases);

    const sections = [];
    const groups = new Map(); // domain -> { queries, downloads, actions, records, uploads }

    for (const base of resourceBases) {
        const id = `res:${base}`;
        const domain = domainOf(base);
        const keys = [];
        const create = get("POST", base);
        const readOp = get("GET", base);
        const item = {
            GET: get("GET", `${base}{id}/`), PUT: get("PUT", `${base}{id}/`),
            PATCH: get("PATCH", `${base}{id}/`), DELETE: get("DELETE", `${base}{id}/`),
        };
        const update = item.PATCH || item.PUT;
        const rowActions = [];
        const toolbar = [];
        keys.push(claim(readOp, id));
        if (create) keys.push(claim(create, id));
        for (const [m, op] of Object.entries(item)) if (op) keys.push(claim(op, id));
        for (const op of list) {
            if (claimed.has(keyOf(op))) continue;
            if (op.path.startsWith(`${base}{id}/`) && /^[\w-]+\/$/.test(op.path.slice(`${base}{id}/`.length))) {
                rowActions.push({ op, ...actionDescriptor(op, base, "row") });
                keys.push(claim(op, id));
            } else if (op.path.startsWith(base) && op.path !== base && /^[\w-]+\/$/.test(op.path.slice(base.length)) && !op.path.startsWith(`${base}{`) && !resourceSet.has(op.path)) {
                toolbar.push({ op, ...actionDescriptor(op, base, "toolbar") });
                keys.push(claim(op, id));
            }
        }
        const writeOp = create || update;
        const createHint = create ? bodyFieldsFor(create) : {};
        const updateHint = update ? bodyFieldsFor(update) : {};
        const tidy = (a) => { const { op, ...rest } = a; return rest; };
        sections.push({
            id, domain, kind: "resource", label: humanize(base.split("/").filter(Boolean).pop()),
            base, keys,
            cfg: {
                base,
                title: singular(base.split("/").filter(Boolean).pop()),
                plural: humanize(base.split("/").filter(Boolean).pop()).toLowerCase(),
                readOnly: !writeOp && !item.DELETE,
                createFields: createHint.fields,
                updateFields: updateHint.fields,
                rowActions: rowActions.map(tidy),
                toolbar: toolbar.map(tidy),
            },
        });
    }

    // Settings singletons: GET C with PUT or PATCH, no items, no create.
    for (const op of list) {
        if (op.method !== "GET" || hasPlaceholder(op.path) || claimed.has(keyOf(op))) continue;
        const writeOp = get("PUT", op.path) || get("PATCH", op.path);
        if (!writeOp || get("POST", op.path) || resourceSet.has(op.path)) continue;
        const id = `set:${op.path}`;
        const keys = [claim(op, id), claim(writeOp, id)];
        sections.push({ id, domain: domainOf(op.path), kind: "settings", label: humanize(op.path.split("/").filter(Boolean).pop()), base: op.path, keys, cfg: { path: op.path } });
    }

    // Everything else: grouped per domain.
    for (const op of list) {
        if (claimed.has(keyOf(op))) continue;
        const domain = domainOf(op.path);
        if (!groups.has(domain)) groups.set(domain, { queries: [], downloads: [], actions: [], records: [], uploads: [] });
        const g = groups.get(domain);
        const label = `${op.method} ${op.path}`;
        const entry = { key: keyOf(op), label: `${humanize(op.path.split("/").filter(Boolean).slice(2).join(" ") || op.path)} · ${op.method}`, op };
        if (op.multipart) g.uploads.push(entry);
        else if (op.method === "GET" && /\/export\b|\/export\/|\/download/.test(op.path) && !hasPlaceholder(op.path)) g.downloads.push(entry);
        else if (op.method === "GET" && !hasPlaceholder(op.path)) g.queries.push(entry);
        else if (hasPlaceholder(op.path)) g.records.push(entry);
        else g.actions.push(entry);
        claim(op, `grp:${domain}`);
    }
    for (const [domain, g] of groups) {
        for (const kind of ["queries", "downloads", "actions", "records", "uploads"]) {
            const items = g[kind];
            if (!items.length) continue;
            const id = `grp:${domain}:${kind}`;
            sections.push({ id, domain, kind: "group", groupKind: kind, label: { queries: "Queries", downloads: "Downloads", actions: "Actions", records: "Records", uploads: "Uploads" }[kind], keys: items.map((i) => i.key), items: items.map((i) => ({ key: i.key, label: i.label })) });
        }
    }

    // Every operation must be claimed exactly once.
    const missing = list.filter((o) => !claimed.has(keyOf(o))).map(keyOf);
    if (missing.length) throw new Error(`Operations not planned: ${missing.join(", ")}`);
    return { sections, claimed };
}
