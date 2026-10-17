import test from "node:test";
import assert from "node:assert/strict";
import { fetchAllProductPages } from "./pos-products.mjs";

test("loads all canonical POS pages in order and removes duplicate IDs", async () => {
  const calls = [];
  const pages = new Map([
    [1, { page: 1, total_pages: 2, has_next: true, next: "?page=2", results: [{ id: 1 }, { id: 2 }] }],
    [2, { page: 2, total_pages: 2, has_next: false, next: null, results: [{ id: 2 }, { id: 3 }] }],
  ]);

  const products = await fetchAllProductPages(async (path) => {
    calls.push(path);
    const page = Number(new URL(path, "https://test.invalid").searchParams.get("page"));
    return pages.get(page);
  }, "/api/pos/products/", 2);

  assert.deepEqual(calls, [
    "/api/pos/products/?page=1&page_size=2",
    "/api/pos/products/?page=2&page_size=2",
  ]);
  assert.deepEqual(products.map((product) => product.id), [1, 2, 3]);
});

test("supports legacy unpaginated arrays", async () => {
  const products = await fetchAllProductPages(async () => [{ id: 4 }, { id: 5 }]);
  assert.deepEqual(products.map((product) => product.id), [4, 5]);
});

test("does not return partial products when a later page fails", async () => {
  await assert.rejects(
    fetchAllProductPages(async (path) => {
      const page = Number(new URL(path, "https://test.invalid").searchParams.get("page"));
      if (page === 1) {
        return { page: 1, total_pages: 2, has_next: true, results: [{ id: 1 }] };
      }
      throw new Error("page unavailable");
    }, "/api/pos/products/", 1),
    /page unavailable/,
  );
});

test("rejects malformed page metadata and rows without IDs", async () => {
  await assert.rejects(
    fetchAllProductPages(async () => ({ page: 2, total_pages: 2, has_next: false, results: [] })),
    /unexpected page number/,
  );
  await assert.rejects(
    fetchAllProductPages(async () => ({ page: 1, total_pages: 1, has_next: false, results: [{ name: "Missing ID" }] })),
    /without an ID/,
  );
});
