/*
 * Pure helpers for the FBR / Fiscal screens (no DOM, unit-tested in
 * scripts/test-fbr-logic.mjs).
 *
 * Honesty rules encoded here:
 *  - only a genuine (non-simulated) acceptance is shown as "Accepted by FBR"
 *    and only then is an FBR invoice number displayed;
 *  - a simulator acceptance is always labelled "Simulated — not official";
 *  - an unknown outcome is never offered a retry (reconcile first) — the
 *    backend's allowed_actions decides which buttons exist at all.
 */

export const FBR_STATUS = {
    accepted: { label: "Accepted by FBR", tone: "green" },
    simulated: { label: "Simulated — not official", tone: "violet" },
    pending: { label: "Pending", tone: "amber" },
    unknown: { label: "Outcome unknown — reconcile", tone: "amber" },
    rejected: { label: "Rejected by FBR", tone: "red" },
    failed: { label: "Failed — not fiscalized", tone: "red" },
    not_submitted: { label: "Not submitted", tone: "slate" },
};

/** Presentation status of a submission row (simulated acceptance kept apart). */
export function submissionStatus(submission) {
    if (!submission) return "not_submitted";
    if (submission.status === "accepted" && submission.is_simulated) return "simulated";
    return FBR_STATUS[submission.status] ? submission.status : "unknown";
}

export function statusInfo(status) {
    return FBR_STATUS[status] || { label: String(status || "Unknown").replace(/_/g, " "), tone: "slate" };
}

/** FBR invoice number to display, or "" unless genuinely accepted. */
export function officialFbrNumber(row) {
    if (!row) return "";
    const status = row.fbr ? row.fbr.status : submissionStatus(row);
    const number = row.fbr ? row.fbr.fbr_invoice_number : row.fbr_invoice_number;
    return status === "accepted" && number ? String(number) : "";
}

/** Which tabs the cached permissions allow (backend RBAC still decides). */
export function allowedTabs(can) {
    const tabs = [];
    if (can("fiscal.manage")) tabs.push({ id: "configuration", label: "Configuration" }, { id: "profiles", label: "Product profiles" });
    if (can("fiscal.create") || can("fiscal.manage")) tabs.push({ id: "sequences", label: "Invoice sequences" });
    if (can("fiscal.view") || can("fiscal.manage")) tabs.push({ id: "invoices", label: "Fiscal invoices" }, { id: "submissions", label: "Submissions" });
    return tabs;
}

/** Zero-padded preview of the next invoice number of a sequence. */
export function nextInvoiceNumber(sequence) {
    const padding = Math.min(Math.max(Number(sequence?.padding) || 1, 1), 12);
    return `${sequence?.prefix || ""}${String(Number(sequence?.next_number) || 1).padStart(padding, "0")}`;
}

const NUMBER_FIELDS = ["pos_registration_number", "timeout_seconds", "max_retries"];
const NULLABLE_FK_FIELDS = ["seller_province", "default_transaction_type"];

/**
 * Build the configuration PATCH/POST body from form values.
 * The security token is write-only: a blank field keeps the stored token.
 */
export function configurationPayload(values, { creating = false } = {}) {
    const body = { ...values };
    for (const key of NUMBER_FIELDS) {
        if (!(key in body)) continue;
        const raw = String(body[key] ?? "").trim();
        body[key] = raw === "" ? (key === "pos_registration_number" ? null : undefined) : Number(raw);
        if (body[key] === undefined) delete body[key];
    }
    for (const key of NULLABLE_FK_FIELDS) {
        if (key in body && String(body[key] ?? "") === "") body[key] = null;
    }
    if (!String(body.security_token ?? "").trim()) delete body.security_token;
    if (!creating) delete body.environment;
    return body;
}

const RATE_FIELDS = [
    "sales_tax_rate", "extra_tax_rate", "further_tax_rate", "fed_payable_rate", "cvt_rate",
    "st_withheld_rate", "withholding_income_tax_rate", "withholding_income_tax_rate_2", "retail_price",
];

/** Product fiscal profile body: blank rates become "0", blank optional FKs null. */
export function profilePayload(values, { creating = false } = {}) {
    const body = { ...values };
    for (const key of RATE_FIELDS) {
        if (key in body && String(body[key] ?? "").trim() === "") body[key] = "0";
    }
    for (const key of ["transaction_type", "sro_schedule"]) {
        if (key in body && String(body[key] ?? "") === "") body[key] = null;
    }
    if (!creating) delete body.product;
    return body;
}

/** Sequence body: numbering fields are dropped once invoices exist (backend locks them). */
export function sequencePayload(values, sequence = null) {
    const body = { name: values.name, is_active: Boolean(values.is_active) };
    if (!sequence || !Number(sequence.invoices_issued)) {
        body.prefix = values.prefix;
        body.document_type = values.document_type || "invoice";
        body.padding = Number(values.padding);
        body.next_number = Number(values.next_number);
    }
    return body;
}

/**
 * Interpret the result of POST /submissions/<id>/retry/.
 * The endpoint answers 2xx for accepted, 422 for rejected and 502 otherwise —
 * the non-2xx bodies are the submission itself (no "error" key), so they are
 * an outcome to report, not a transport failure.
 */
export function retryOutcome(result, error) {
    const submission = result || (error?.data && typeof error.data === "object" && error.data.id ? error.data : null);
    if (!submission) {
        return { ok: false, tone: "error", message: error?.message || "The retry could not be started." };
    }
    const status = submissionStatus(submission);
    const detail = submission.error_message ? ` ${String(submission.error_message).slice(0, 200)}` : "";
    if (status === "accepted") return { ok: true, tone: "success", message: `Accepted by FBR: ${submission.fbr_invoice_number}.` };
    if (status === "simulated") return { ok: true, tone: "info", message: "Simulator accepted the retry — this is NOT an official FBR acceptance." };
    return { ok: true, tone: status === "pending" ? "info" : "error", message: `Retry finished: ${statusInfo(status).label}.${detail}` };
}

/** Field errors of the backend validation envelope as "field: message" lines. */
export function fieldErrorLines(error) {
    const fields = error?.fields && typeof error.fields === "object" ? error.fields : {};
    return Object.entries(fields).map(([name, messages]) => {
        const text = Array.isArray(messages) ? messages.join(" ") : String(messages);
        return `${name.replace(/_/g, " ")}: ${text}`;
    });
}
