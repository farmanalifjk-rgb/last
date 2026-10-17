import test from "node:test";
import assert from "node:assert/strict";
import { escapeHtml, safeWebUrl } from "./html-safety.mjs";

test("escapes HTML text and quoted-attribute metacharacters", () => {
  assert.equal(escapeHtml(`<img src='x' onerror="alert(1)">`), "&lt;img src=&#39;x&#39; onerror=&quot;alert(1)&quot;&gt;");
  assert.equal(escapeHtml(null), "");
});

test("resolves relative web URLs against the configured API origin", () => {
  assert.equal(safeWebUrl("/media/products/item.png", "https://api.example.test"), "https://api.example.test/media/products/item.png");
  assert.equal(safeWebUrl("https://cdn.example.test/item.png"), "https://cdn.example.test/item.png");
});

test("rejects executable, non-web, and protocol-relative URLs", () => {
  for (const value of ["javascript:alert(1)", "data:image/svg+xml,<svg>", "file:///etc/passwd", "//cdn.example.test/item.png", "https:\\cdn.example.test\\item.png", "https://example.test/\nitem.png"]) {
    assert.equal(safeWebUrl(value, "https://api.example.test"), null, value);
  }
  assert.equal(safeWebUrl("   "), null);
  assert.equal(safeWebUrl(undefined), null);
});
