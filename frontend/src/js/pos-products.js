/*
 * Paginated loader for GET /api/pos/products/.
 *
 * Backend contract (backend/pos/views/canonical.py POSProductSearchView with
 * backend/pos/pagination.py CustomPagination):
 *   query:    ?page=<n>&page_size=<1..100>   (plus optional search / barcode / category_id)
 *   response: { count, page, page_size, total_pages, has_next, has_previous,
 *               next, previous, results: [...] }
 * Ordering is stable (name, id). A bare array is also accepted for safety.
 *
 * Kept free of DOM access so it can be exercised directly with Node
 * (see frontend/scripts/test-pos-products.mjs).
 */

export const POS_PRODUCT_PAGE_SIZE = 100; // CustomPagination.max_page_size
// Hard stop against a misbehaving server (e.g. has_next never false): 500 x 100 = 50,000 products.
export const POS_PRODUCT_MAX_PAGES = 500;

/**
 * Fetch every page of active products for the current tenant.
 *
 * @param {(path: string) => Promise<any>} fetchJson  apiJson-compatible getter
 * @returns {Promise<{products: object[], complete: boolean, count: number|null, error: Error|null}>}
 *   `complete` is false when a page failed; `products` then holds the pages
 *   loaded before the failure so the caller can decide what to show.
 */
export async function fetchAllProductPages(fetchJson, { pageSize = POS_PRODUCT_PAGE_SIZE, maxPages = POS_PRODUCT_MAX_PAGES } = {}) {
    const byId = new Map();
    let count = null;
    let page = 1;

    const add = (rows) => {
        for (const row of rows || []) {
            if (row && row.id !== undefined && row.id !== null && !byId.has(String(row.id))) {
                byId.set(String(row.id), row);
            }
        }
    };

    try {
        while (page <= maxPages) {
            const data = await fetchJson(`/api/pos/products/?page=${page}&page_size=${pageSize}`);

            if (Array.isArray(data)) {
                // Unpaginated response: everything is in this single payload.
                add(data);
                return { products: [...byId.values()], complete: true, count: byId.size, error: null };
            }

            if (!data || !Array.isArray(data.results)) {
                throw new Error("Unexpected product list response from the server.");
            }

            add(data.results);
            if (typeof data.count === "number") count = data.count;

            const totalPages = Number(data.total_pages);
            const hasNext = typeof data.has_next === "boolean"
                ? data.has_next
                : Number.isFinite(totalPages) ? page < totalPages : Boolean(data.next);

            if (!hasNext || data.results.length === 0) {
                return { products: [...byId.values()], complete: true, count, error: null };
            }
            page += 1;
        }
        return {
            products: [...byId.values()],
            complete: false,
            count,
            error: new Error(`Stopped after ${maxPages} pages of products.`),
        };
    } catch (error) {
        return { products: [...byId.values()], complete: false, count, error };
    }
}
