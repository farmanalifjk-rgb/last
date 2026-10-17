const POS_PRODUCT_PAGE_SIZE = 100;

function pagePath(path, page, pageSize) {
  const url = new URL(path, "https://pos.invalid");
  url.searchParams.set("page", String(page));
  url.searchParams.set("page_size", String(pageSize));
  return `${url.pathname}${url.search}`;
}

/**
 * Load the canonical POS product endpoint's page-number envelope.
 * The API currently returns {count, page, page_size, total_pages, has_next,
 * has_previous, next, previous, results}; bare arrays are retained for older
 * deployments. Duplicate IDs are ignored while preserving API order.
 */
export async function fetchAllProductPages(fetchPage, path = "/api/pos/products/", pageSize = POS_PRODUCT_PAGE_SIZE) {
  const limit = Math.max(1, Math.min(POS_PRODUCT_PAGE_SIZE, Number(pageSize) || POS_PRODUCT_PAGE_SIZE));
  const products = [];
  const seenIds = new Set();
  let requestedPage = 1;
  let totalPages = null;

  const appendUnique = (rows) => {
    for (const product of rows) {
      if (!product || product.id === null || product.id === undefined) {
        throw new TypeError("POS product response contains an item without an ID.");
      }
      const id = String(product.id);
      if (seenIds.has(id)) continue;
      seenIds.add(id);
      products.push(product);
    }
  };

  while (totalPages === null || requestedPage <= totalPages) {
    const payload = await fetchPage(pagePath(path, requestedPage, limit));

    if (Array.isArray(payload)) {
      if (requestedPage !== 1) {
        throw new TypeError("POS product pagination changed to an unpaged response mid-load.");
      }
      appendUnique(payload);
      return products;
    }

    if (!payload || !Array.isArray(payload.results)) {
      throw new TypeError("POS product endpoint returned an invalid list response.");
    }

    const currentPage = Number(payload.page ?? requestedPage);
    if (!Number.isInteger(currentPage) || currentPage !== requestedPage) {
      throw new TypeError("POS product endpoint returned an unexpected page number.");
    }

    if (payload.total_pages !== undefined && payload.total_pages !== null) {
      const reportedTotal = Number(payload.total_pages);
      if (!Number.isInteger(reportedTotal) || reportedTotal < 0 || currentPage > Math.max(reportedTotal, 1)) {
        throw new TypeError("POS product endpoint returned invalid pagination metadata.");
      }
      totalPages = reportedTotal;
    }

    appendUnique(payload.results);

    const hasNext = payload.has_next === true || (payload.has_next === undefined && payload.next != null);
    if (!hasNext) return products;

    if (totalPages !== null && requestedPage >= totalPages) {
      throw new TypeError("POS product endpoint has_next conflicts with total_pages.");
    }
    requestedPage += 1;
  }

  return products;
}
