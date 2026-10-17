// Checks for the POS product pagination loader (src/js/pos-products.js).
// Usage: node scripts/test-pos-products.mjs
import assert from "node:assert/strict";
import { withSrcLoader } from "./lib/load-src.mjs";

const { fetchAllProductPages, POS_PRODUCT_PAGE_SIZE } = await withSrcLoader((load) => load("/src/js/pos-products.js"));

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

/** Fake apiJson serving `total` products using the backend CustomPagination envelope. */
function paginatedServer(total, { failOnPage = null, duplicateAcrossPages = false } = {}) {
    const calls = [];
    const fetchJson = async (path) => {
        calls.push(path);
        const url = new URL(path, "http://pos.test");
        assert.equal(url.pathname, "/api/pos/products/");
        const page = Number(url.searchParams.get("page"));
        const size = Number(url.searchParams.get("page_size"));
        if (page === failOnPage) {
            const error = new Error("Request failed (500)");
            error.status = 500;
            throw error;
        }
        const totalPages = Math.max(1, Math.ceil(total / size));
        if (page > totalPages) {
            const error = new Error("Invalid page.");
            error.status = 404;
            throw error;
        }
        let start = (page - 1) * size;
        // Simulate a row shifting between requests (insert during paging): the
        // previous page's last row is repeated at the top of this page.
        if (duplicateAcrossPages && page > 1) start -= 1;
        const results = [];
        for (let i = start; i < Math.min(page * size, total); i += 1) {
            results.push({ id: i + 1, name: `Product ${String(i + 1).padStart(5, "0")}` });
        }
        return {
            count: total, page, page_size: size, total_pages: totalPages,
            has_next: page < totalPages, has_previous: page > 1,
            next: page < totalPages ? `http://pos.test/api/pos/products/?page=${page + 1}` : null,
            previous: null, results,
        };
    };
    return { fetchJson, calls };
}

await check("empty catalogue returns no products and one request", async () => {
    const server = paginatedServer(0);
    const result = await fetchAllProductPages(server.fetchJson);
    assert.equal(result.complete, true);
    assert.equal(result.error, null);
    assert.deepEqual(result.products, []);
    assert.equal(server.calls.length, 1);
});

await check("single page is loaded with the maximum page size", async () => {
    const server = paginatedServer(7);
    const result = await fetchAllProductPages(server.fetchJson);
    assert.equal(result.complete, true);
    assert.equal(result.products.length, 7);
    assert.equal(server.calls.length, 1);
    assert.match(server.calls[0], new RegExp(`page_size=${POS_PRODUCT_PAGE_SIZE}`));
});

await check("multiple pages load every product (previously only the first 10 were shown)", async () => {
    const server = paginatedServer(253);
    const result = await fetchAllProductPages(server.fetchJson);
    assert.equal(result.complete, true);
    assert.equal(result.count, 253);
    assert.equal(result.products.length, 253);
    assert.equal(server.calls.length, 3);
    assert.equal(result.products.at(-1).name, "Product 00253");
});

await check("rows repeated across pages are de-duplicated by id", async () => {
    const server = paginatedServer(250, { duplicateAcrossPages: true });
    const result = await fetchAllProductPages(server.fetchJson);
    const ids = result.products.map((p) => p.id);
    assert.equal(new Set(ids).size, ids.length);
    assert.equal(result.products.length, 250);
});

await check("API failure on the first page reports the error with no products", async () => {
    const server = paginatedServer(50, { failOnPage: 1 });
    const result = await fetchAllProductPages(server.fetchJson);
    assert.equal(result.complete, false);
    assert.equal(result.products.length, 0);
    assert.equal(result.error.status, 500);
});

await check("API failure mid-way keeps earlier pages and reports incomplete", async () => {
    const server = paginatedServer(350, { failOnPage: 3 });
    const result = await fetchAllProductPages(server.fetchJson);
    assert.equal(result.complete, false);
    assert.equal(result.products.length, 200);
    assert.equal(result.count, 350);
    assert.ok(result.error);
});

await check("network error (fetch rejected) is reported, not thrown", async () => {
    const result = await fetchAllProductPages(async () => {
        const error = new Error("Unable to reach the POS server.");
        error.isNetworkError = true;
        throw error;
    });
    assert.equal(result.complete, false);
    assert.equal(result.error.isNetworkError, true);
});

await check("unpaginated array response is accepted", async () => {
    const result = await fetchAllProductPages(async () => [{ id: 1 }, { id: 2 }, { id: 2 }]);
    assert.equal(result.complete, true);
    assert.equal(result.products.length, 2);
});

await check("malformed response is reported as an error", async () => {
    const result = await fetchAllProductPages(async () => ({ detail: "oops" }));
    assert.equal(result.complete, false);
    assert.match(result.error.message, /Unexpected product list/);
});

await check("a server that never ends paging is stopped by the page cap", async () => {
    let calls = 0;
    const result = await fetchAllProductPages(async () => {
        calls += 1;
        return { count: 1, results: [{ id: calls }], has_next: true };
    }, { maxPages: 5 });
    assert.equal(calls, 5);
    assert.equal(result.complete, false);
    assert.equal(result.products.length, 5);
});

console.log(failures ? `\n${failures} check(s) failed` : "\nall pos-products checks passed");
process.exit(failures ? 1 : 0);
