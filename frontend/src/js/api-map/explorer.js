/**
 * API explorer. Shows every in-scope backend operation from operations.json, grouped
 * by domain. Each section is built by planSections() in plan.mjs, so each operation
 * appears in exactly one section. Deep links: #/api-explorer?domain=&section=&op=
 */
import OPERATIONS from "./operations.json";
import { planSections, fieldsForOp, humanize } from "./plan.mjs";
import { resourceView, settingsView, queryView, actionView, uploadView } from "./views.js";
import { esc, hashParam, emptyStateCard } from "../../shared/ui.js";

const SELECT = "h-11 min-w-[14rem] rounded-xl border border-slate-200 bg-white px-4 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-violet-200";
const GROUP_KIND_LABEL = { queries: "Queries", downloads: "Downloads", actions: "Actions", records: "Records", uploads: "Uploads" };

let planCache = null;
const getPlan = () => planCache || (planCache = planSections(OPERATIONS));

function domainLabel(domain) {
    return humanize(domain);
}

/** Last readable path segment, used as a button label. */
function labelFor(path, method) {
    const segments = path.split("/").filter((s) => s && !/^\{.*\}$/.test(s));
    const tail = segments[segments.length - 1] || "";
    return tail ? humanize(tail) : `${method} request`;
}

/** Choose the file field for a multipart operation and return the other fields. */
function uploadFields(op, fields) {
    const body = fields || [];
    const file = body.find((f) => /file|image|upload|csv|document|media|attachment/i.test(f.name));
    return { fileField: file ? file.name : "file", rest: body.filter((f) => f !== file) };
}

/** Mount one operation from a group section. */
function mountOperation(view, key) {
    const op = OPERATIONS[key];
    if (!op) throw new Error(`Operation is not in the API map: ${key}`);
    const fields = fieldsForOp(op);
    const label = labelFor(op.path, op.method);
    const description = `${op.method} ${op.path}`;
    const hasSchemaBody = !!(fields && fields.length) || op.bodyGeneric;
    const kind = op.multipart ? "uploads"
        : op.method === "GET" && /\/export\b|\/export\/|\/download/.test(op.path) && !/\{/.test(op.path) ? "downloads"
            : op.method === "GET" && !/\{/.test(op.path) ? "queries"
                : /\{/.test(op.path) ? "records" : "actions";
    if (kind === "queries") return queryView(view, { path: op.path });
    if (kind === "downloads") return queryView(view, { path: op.path, download: true, label: label });
    if (kind === "uploads") {
        const { fileField, rest } = uploadFields(op, fields);
        return uploadView(view, { method: op.method, path: op.path, label, fileField, fields: rest, description, fileLabel: humanize(fileField) });
    }
    return actionView(view, {
        method: op.method, path: op.path, label, fields: hasSchemaBody ? fields : undefined, description,
    });
}

function groupSection(view, section) {
    const select = document.createElement("select");
    select.className = SELECT;
    select.setAttribute("aria-label", `${section.label} operation`);
    select.innerHTML = section.items.map((i) => `<option value="${esc(i.key)}">${esc(i.label)} — ${esc(i.key)}</option>`).join("");
    const body = document.createElement("div");
    body.className = "space-y-4";
    body.append(select);
    const target = document.createElement("div");
    body.append(target);
    view.replaceChildren(body);
    const show = (key) => {
        try {
            mountOperation(target, key);
            select.dataset.current = key;
            pushState({ op: key });
        } catch (error) {
            target.innerHTML = emptyStateCard("Could not open this operation", error.message);
        }
    };
    select.addEventListener("change", () => show(select.value));
    const requested = hashParam("op");
    const initial = section.items.find((i) => i.key === requested) ? requested : section.items[0].key;
    select.value = initial;
    show(initial);
}

function mountSection(view, section) {
    if (section.kind === "resource") return resourceView(view, section.cfg);
    if (section.kind === "settings") return settingsView(view, { path: section.cfg.path });
    return groupSection(view, section);
}

function pushState(extra = {}) {
    const params = new URLSearchParams();
    const domain = document.querySelector("[data-ex='domain']")?.value;
    const section = document.querySelector("[data-ex='section']")?.value;
    if (domain) params.set("domain", domain);
    if (section) params.set("section", section);
    Object.entries(extra).forEach(([k, v]) => { if (v) params.set(k, v); });
    history.replaceState(null, "", `#/api-explorer?${params.toString()}`);
}

export function mountApiExplorer(root) {
    const plan = getPlan();
    const domains = new Map();
    for (const section of plan.sections) {
        if (!domains.has(section.domain)) domains.set(section.domain, []);
        domains.get(section.domain).push(section);
    }
    const domainNames = [...domains.keys()].sort((a, b) => domainLabel(a).localeCompare(domainLabel(b)));
    const opCount = (sections) => new Set(sections.flatMap((s) => s.keys)).size;

    root.innerHTML = `
        <div class="mb-5 flex flex-wrap items-end gap-4">
            <label class="block text-sm font-medium text-slate-700">Domain
                <select data-ex="domain" class="mt-1.5 block ${SELECT}">
                    ${domainNames.map((d) => `<option value="${esc(d)}">${esc(domainLabel(d))} (${opCount(domains.get(d))})</option>`).join("")}
                </select>
            </label>
            <label class="block text-sm font-medium text-slate-700">Section
                <select data-ex="section" class="mt-1.5 block ${SELECT}"></select>
            </label>
            <p class="ml-auto text-sm text-slate-500" data-ex="summary"></p>
        </div>
        <div data-ex="view" class="rounded-2xl border border-slate-200 bg-white p-6"></div>`;

    const domainSelect = root.querySelector("[data-ex='domain']");
    const sectionSelect = root.querySelector("[data-ex='section']");
    const view = root.querySelector("[data-ex='view']");
    const summary = root.querySelector("[data-ex='summary']");

    const sectionLabel = (s) => {
        if (s.kind === "resource") return `${s.label} — list, create, edit`;
        if (s.kind === "settings") return `${s.label} — settings`;
        return `${GROUP_KIND_LABEL[s.groupKind]} (${s.items.length})`;
    };

    function fillSections(domain, requested) {
        const sections = domains.get(domain) || [];
        sectionSelect.innerHTML = sections.map((s) => `<option value="${esc(s.id)}">${esc(sectionLabel(s))}</option>`).join("");
        const chosen = sections.find((s) => s.id === requested) || sections[0];
        sectionSelect.value = chosen.id;
        summary.textContent = `${opCount(sections)} operations · ${sections.length} sections`;
        try {
            mountSection(view, chosen);
        } catch (error) {
            view.innerHTML = emptyStateCard("Could not open this section", error.message);
        }
        pushState();
    }

    domainSelect.addEventListener("change", () => fillSections(domainSelect.value, null));
    sectionSelect.addEventListener("change", () => {
        const section = (domains.get(domainSelect.value) || []).find((s) => s.id === sectionSelect.value);
        if (!section) return;
        try {
            mountSection(view, section);
        } catch (error) {
            view.innerHTML = emptyStateCard("Could not open this section", error.message);
        }
        pushState();
    });

    const initialDomain = domains.has(hashParam("domain")) ? hashParam("domain") : domainNames[0];
    domainSelect.value = initialDomain;
    fillSections(initialDomain, hashParam("section"));
}

