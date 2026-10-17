/**
 * Money with the business currency.
 *
 * Company.currency is free text (max 20 chars, model default "Rs"): it may hold
 * an ISO code ("PKR", "USD") or a symbol/abbreviation ("Rs", "$"). ISO codes are
 * shown with their narrow symbol (PKR -> "Rs", USD -> "$", AED -> "AED"); free
 * text is shown as entered after stripping markup characters. Without a
 * configured currency the label falls back to "Rs" (the model default).
 *
 * Source of the currency, in order: the company profile (owners/admins), then
 * the session payload tenant.currency (every member, including cashiers).
 */
import { formatMoney } from "./format.js";
import { cachedCompany } from "../services/company.js";
import { getCachedTenant } from "../services/auth.js";

export const FALLBACK_CURRENCY_LABEL = "Rs";

export function configuredCurrency() {
    // Formatting money must never throw: without readable storage (private
    // mode, tests) fall back to the default label.
    try {
        const fromCompany = cachedCompany()?.currency;
        if (fromCompany && String(fromCompany).trim()) return String(fromCompany).trim();
        const fromSession = getCachedTenant()?.currency;
        if (fromSession && String(fromSession).trim()) return String(fromSession).trim();
    } catch {
        // fall through to the fallback
    }
    return "";
}

export function currencyLabel(raw = configuredCurrency()) {
    const value = String(raw ?? "").trim();
    if (!value) return FALLBACK_CURRENCY_LABEL;
    if (/^[A-Za-z]{3}$/.test(value)) {
        const code = value.toUpperCase();
        try {
            const part = new Intl.NumberFormat("en-PK", { style: "currency", currency: code, currencyDisplay: "narrowSymbol" })
                .formatToParts(0)
                .find((p) => p.type === "currency");
            return part?.value || code;
        } catch {
            return code;
        }
    }
    // Free text: keep letters, currency symbols, dots and spaces only, so the
    // label is safe in HTML and cannot break layouts.
    const cleaned = value.replace(/[^\p{L}\p{Sc}. ]/gu, "").trim().slice(0, 8);
    return cleaned || FALLBACK_CURRENCY_LABEL;
}

/** "Rs 1,250.00" — plain text, HTML-safe by construction. */
export function formatCurrency(amount, raw) {
    return `${currencyLabel(raw)} ${formatMoney(amount)}`;
}

/** Re-label static markup rendered before the profile/session was known. */
export function applyCurrencyLabels(root = document) {
    const label = currencyLabel();
    root.querySelectorAll?.("[data-currency-label]").forEach((el) => {
        el.textContent = label;
    });
}
