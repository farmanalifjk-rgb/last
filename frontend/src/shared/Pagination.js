export class Pagination {
  /**
   * @param {Object} options
   * @param {string} [options.prevButtonId="prev-page"]   - id of the "previous" button
   * @param {string} [options.nextButtonId="next-page"]   - id of the "next" button
   * @param {string} [options.containerId="pagination-numbers"] - id of the "Page X of Y" container
   * @param {number} [options.pageSize=20]                - number of items per page (used to compute totalPages)
   * @param {Function} [options.onPageChange]              - callback invoked with the new page number whenever the page changes
   */
  constructor({
    prevButtonId = "prev-page",
    nextButtonId = "next-page",
    containerId = "pagination-numbers",
    pageSize = 20,
    onPageChange = () => {},
  } = {}) {
    this.prevButtonId = prevButtonId;
    this.nextButtonId = nextButtonId;
    this.containerId = containerId;
    this.pageSize = pageSize;
    this.onPageChange = onPageChange;

    this.state = {
      page: 1,
      totalPages: 1,
      hasNext: false,
      hasPrevious: false,
    };

    
    
  }

  initialize() {

    this._setupEventListeners();

    this._render();

}

  // ==========================================================================
  // PUBLIC API
  // ==========================================================================

  /** Returns the current page number. */
  getPage() {
    return this.state.page;
  }

  /** Returns the full pagination state ({ page, totalPages, hasNext, hasPrevious }). */
  getState() {
    return { ...this.state };
  }

  /**
   * Updates pagination state from a typical DRF-style paginated response:
   *   { count, next, previous }
   * Recomputes totalPages using pageSize, then re-renders the UI.
   */
  updateFromResponse(data = {}) {

    this.totalCount = data.count;

    this.state.page = data.page;

    this.state.totalPages = data.total_pages;

    this.state.hasNext = data.has_next;

    this.state.hasPrevious = data.has_previous;

    this._render();

}

  /**
   * Manually set pagination state (useful if you're not using a DRF-style response).
   */
  setState({ page, totalPages, hasNext, hasPrevious } = {}) {
    if (page !== undefined) this.state.page = page;
    if (totalPages !== undefined) this.state.totalPages = totalPages;
    if (hasNext !== undefined) this.state.hasNext = hasNext;
    if (hasPrevious !== undefined) this.state.hasPrevious = hasPrevious;

    this._render();
  }

  /** Resets back to page 1 (e.g. after a new search or filter change). Does NOT trigger onPageChange. */
  reset() {
    this.state.page = 1;
    this._render();
  }

  /** Advances to the next page (if available) and fires onPageChange. */
  next() {
    if (!this.state.hasNext) return;
    this.state.page++;
    this._render();
    this.onPageChange(this.state.page);
  }

  /** Goes back to the previous page (if available) and fires onPageChange. */
  prev() {
    if (!this.state.hasPrevious) return;
    this.state.page--;
    this._render();
    this.onPageChange(this.state.page);
  }

  // ==========================================================================
  // INTERNAL
  // ==========================================================================

  _setupEventListeners() {
    const nextBtn = document.getElementById(this.nextButtonId);
    const prevBtn = document.getElementById(this.prevButtonId);

    nextBtn?.addEventListener("click", () => this.next());
    prevBtn?.addEventListener("click", () => this.prev());
  }

  _render() {
    const prevBtn = document.getElementById(this.prevButtonId);
    const nextBtn = document.getElementById(this.nextButtonId);
    const container = document.getElementById(this.containerId);

    if (prevBtn) prevBtn.disabled = !this.state.hasPrevious;
    if (nextBtn) nextBtn.disabled = !this.state.hasNext;

    if (container) {
      container.innerHTML = `<span class="px-3 py-1 bg-gray-50 rounded-lg border border-gray-200">Page ${this.state.page} of ${this.state.totalPages}</span>`;
    }

    const info =
    document.getElementById("pagination-info");

if(info){

    const start =
        ((this.state.page-1)*this.pageSize)+1;

    const end =
        Math.min(
            this.state.page*this.pageSize,
            this.totalCount
        );

    info.textContent =
        `Showing ${start}-${end} of ${this.totalCount}`;

}
  }
}

export default Pagination;