// Reproducible XSS checks for API-provided text rendered via innerHTML.
// Usage: node scripts/test-frontend-security.mjs
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { withSrcLoader } from "./lib/load-src.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
let failures = 0;
async function check(name, fn) {
    try {
        await fn();
        console.log(`ok   ${name}`);
    } catch (error) {
        failures += 1;
        console.log(`FAIL ${name}\n     ${error.message}`);
    }
}

// Hostile values an attacker could store as a product/customer/category name.
const HOSTILE = [
    `<img src=x onerror=alert(1)>`,
    `"><script>alert(1)</script>`,
    `' onmouseover='alert(1)`,
    `&quot;);alert(1);//`,
];
const HOSTILE_URLS = [
    "javascript:alert(1)",
    " JaVaScRiPt:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "//evil.example/x.png",
    "\\\\evil.example\\x.png",
];

/** Tokenise the real tags of an HTML string into {tag, attrs:[{name,value}]} (text content is skipped). */
function parseTags(html) {
    const tags = [];
    for (const match of html.matchAll(/<([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^\s"'>\/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*)\s*\/?>/g)) {
        const attrs = [];
        for (const attr of match[2].matchAll(/([^\s"'>\/=]+)(?:\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g)) {
            attrs.push({ name: attr[1].toLowerCase(), value: attr[3] ?? attr[4] ?? attr[5] ?? "" });
        }
        tags.push({ tag: match[1].toLowerCase(), attrs });
    }
    return tags;
}

const decode = (value) => value.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

/** Event-handler attributes rendered in `html`, as "name=value" strings. */
function handlers(html) {
    return parseTags(html).flatMap(({ attrs }) => attrs.filter((a) => a.name.startsWith("on")).map((a) => `${a.name}=${a.value}`));
}

/**
 * Fail when rendered HTML contains markup an attacker injected rather than
 * escaped text. `benignHtml` is the same component rendered with harmless data;
 * the hostile render may not introduce any handler the template doesn't have.
 */
function assertNoInjectedMarkup(html, label, benignHtml = "") {
    const allowed = new Set(handlers(benignHtml));
    for (const { tag, attrs } of parseTags(html)) {
        assert.notEqual(tag, "script", `${label}: raw <script> tag rendered`);
        for (const { name, value } of attrs) {
            if (name.startsWith("on")) {
                assert.ok(allowed.has(`${name}=${value}`), `${label}: injected handler ${name}="${value}"`);
            }
            if (name === "src" || name === "href") {
                const url = decode(value).replace(/[\u0000-\u0020]/g, "");
                assert.ok(!/^(javascript|data|vbscript):/i.test(url), `${label}: unsafe URL ${name}="${value}"`);
                assert.ok(!url.startsWith("//"), `${label}: protocol-relative URL ${name}="${value}"`);
            }
        }
    }
}

const modules = await withSrcLoader(async (load) => ({
    format: await load("/src/shared/format.js"),
    ProductRow: (await load("/src/js/inventory/components/ProductRow.js")).ProductRow,
    ProductModal: (await load("/src/js/inventory/components/ProductModal.js")).ProductModal,
    ProductDetailModal: (await load("/src/js/inventory/components/ProductDetailModal.js")).ProductDetailModal,
    EditProductModal: (await load("/src/js/inventory/components/EditProductModal.js")).EditProductModal,
    MovementDetailModal: (await load("/src/js/Movements/components/MovementDetailModal.js")).MovementDetailModal,
    AdjustmentDetailModal: (await load("/src/js/Adjustments/components/AdjustmentDetailModal.js")).AdjustmentDetailModal,
}));
const { escapeHtml, safeUrl } = modules.format;

await check("escapeHtml escapes all HTML-significant characters", () => {
    assert.equal(escapeHtml(`<a href="x" title='y'>&</a>`), "&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;");
    assert.equal(escapeHtml(null), "");
    assert.equal(escapeHtml(0), "0");
});

await check("safeUrl rejects script-capable and protocol-relative URLs", () => {
    for (const url of HOSTILE_URLS) assert.equal(safeUrl(url), "", url);
});

await check("safeUrl keeps http(s) and same-origin relative media URLs", () => {
    for (const url of ["https://cdn.example/p.png", "http://localhost:8000/media/p.png", "/media/products/p.png", "media/p.png"]) {
        assert.equal(safeUrl(url), url);
    }
    assert.equal(safeUrl(""), "");
    assert.equal(safeUrl(undefined), "");
});

const productFixture = (text, image) => ({
    id: 7, name: text, sku: text, barcode: text, category: text, unit: text, stock_quantity: 3, min_stock: 1,
    max_stock: 10, sales_price: "5.00", cost_price: "2.00", stock_status: text, stock: 3, image_url: image,
});
const renders = {
    ProductRow: (t, img) => modules.ProductRow(productFixture(t, img)),
    ProductModal: (t, img) => modules.ProductModal(productFixture(t, img)),
    EditProductModal: (t, img) => modules.EditProductModal(productFixture(t, img)),
    ProductDetailModal: (t, img) => modules.ProductDetailModal({
        product: productFixture(t, img), recent_movements: [{ movement_type: t, reference: t, quantity: -1 }],
    }),
    MovementDetailModal: (t) => modules.MovementDetailModal({ product: t, movement: t, quantity: 1, reference: t, note: t, created_at: "2026-01-01" }),
    AdjustmentDetailModal: (t) => modules.AdjustmentDetailModal({
        adjustment_number: t, note: t, created_at: "2026-01-01",
        items: [{ product_name: t, quantity_before: 1, quantity_after: 2, reason: t }],
    }),
};

for (const [component, render] of Object.entries(renders)) {
    const benign = render("Plain Coffee", "/media/products/coffee.png");
    for (const text of HOSTILE) {
        await check(`${component} escapes API text ${JSON.stringify(text)}`, () => {
            assertNoInjectedMarkup(render(text, HOSTILE_URLS[0]), component, benign);
        });
    }
    await check(`${component} drops unsafe image URLs`, () => {
        for (const url of HOSTILE_URLS) assertNoInjectedMarkup(render("Coffee", url), component, benign);
    });
}

await check("EditProductModal keeps a quote-bearing name inside its value attribute", () => {
    const html = modules.EditProductModal({ id: 1, name: `A" autofocus onfocus="alert(1)`, sales_price: 1, cost_price: 1 });
    assert.ok(html.includes('value="A&quot; autofocus onfocus=&quot;alert(1)"'));
});

// Static scan: inline event handlers must never embed non-numeric server data.
function walk(dir, out = []) {
    for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) walk(full, out);
        else if (full.endsWith(".js")) out.push(full);
    }
    return out;
}
const sources = [...walk(join(root, "src")), join(root, "receipt.js")].filter((f) => !f.includes(`${join("js", "api-map")}`));

await check("no inline handler interpolates non-numeric values", () => {
    const offenders = [];
    for (const file of sources) {
        const lines = readFileSync(file, "utf8").split("\n");
        lines.forEach((line, index) => {
            for (const match of line.matchAll(/\son[a-z]+\s*=\s*(["'])(.*?)\1/g)) {
                const body = match[2];
                const interpolations = [...body.matchAll(/\$\{([^}]*)\}/g)].map((m) => m[1].trim());
                const unsafe = interpolations.filter((expr) => !/^Number\(/.test(expr));
                if (unsafe.length) offenders.push(`${relative(root, file)}:${index + 1}: ${unsafe.join(", ")}`);
            }
        });
    }
    assert.deepEqual(offenders, [], `inline handlers with server values:\n     ${offenders.join("\n     ")}`);
});

await check("no handler serialises API objects with JSON.stringify", () => {
    const offenders = [];
    for (const file of sources) {
        readFileSync(file, "utf8").split("\n").forEach((line, index) => {
            if (/on[a-z]+\s*=\s*['"][^'"]*JSON\.stringify/.test(line)) offenders.push(`${relative(root, file)}:${index + 1}`);
        });
    }
    assert.deepEqual(offenders, []);
});

await check("loadErrorHtml escapes hostile backend error messages and labels", () => {
    for (const payload of HOSTILE) {
        for (const kind of ["permission", "server", "network", "validation", undefined]) {
            const html = modules.format.loadErrorHtml({ kind, message: payload }, payload);
            assertNoInjectedMarkup(html, `loadErrorHtml(${kind})`, modules.format.loadErrorHtml({ kind, message: "x" }, "x"));
        }
    }
    assert.match(modules.format.loadErrorHtml({ kind: "permission", message: "A platform-level permission is required." }, "users"),
        /You do not have permission to view users\./);
});

console.log(failures ? `\n${failures} check(s) failed` : "\nall frontend security checks passed");
process.exit(failures ? 1 : 0);
