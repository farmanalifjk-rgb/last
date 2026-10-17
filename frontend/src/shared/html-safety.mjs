const SAFE_WEB_PROTOCOLS = new Set(["http:", "https:"]);

/** Escape untrusted text for HTML text and quoted attribute contexts. */
export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Resolve an API-provided URL only when it uses HTTP(S).
 * Relative URLs resolve against the API origin so `/media/...` works when the
 * API and frontend have different origins. Protocol-relative URLs are rejected
 * to prevent silently switching origins.
 */
export function safeWebUrl(value, baseUrl = globalThis.location?.origin || "https://pos.invalid") {
  if (value === null || value === undefined) return null;
  const raw = String(value).trim();
  if (!raw || /[\u0000-\u001f\u007f]/.test(raw) || raw.includes("\\")) return null;
  const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(raw);
  const isHttp = /^https?:\/\//i.test(raw);
  if (raw.startsWith("//") || (hasScheme && !isHttp)) {
    return null;
  }

  try {
    const url = new URL(raw, baseUrl);
    return SAFE_WEB_PROTOCOLS.has(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
