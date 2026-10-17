/**
 * Collect every page of a paginated list for an export, up to a row cap.
 *
 * `loadPage(page, pageSize)` returns the normalised list shape
 * ({ results, count, total_pages }). The cap keeps a browser export bounded;
 * `truncated` tells the caller to say so instead of silently exporting less.
 */
export async function collectAllPages(loadPage, { pageSize = 100, maxRows = 5000 } = {}) {
    const rows = [];
    let page = 1;
    let totalPages = 1;
    let count = 0;
    do {
        const data = await loadPage(page, pageSize);
        const results = Array.isArray(data?.results) ? data.results : [];
        rows.push(...results);
        count = Number(data?.count ?? rows.length) || rows.length;
        totalPages = Math.max(Number(data?.total_pages) || 1, 1);
        if (!results.length) break;
        page += 1;
    } while (page <= totalPages && rows.length < maxRows);
    const truncated = rows.length > maxRows || (rows.length >= maxRows && page <= totalPages);
    return { rows: rows.slice(0, maxRows), count, truncated };
}
