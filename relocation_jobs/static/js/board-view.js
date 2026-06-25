/** Build the view model passed to the React board. */

import { state } from "./state.js";
import { $ } from "./utils.js";
import { getDisplayCompanies } from "./render.js";
import { boardTotalPages } from "./board.js";
import { publishBoardView } from "./board-sync.js";

function paginationView(loading = false) {
  const pageSize = state.boardMeta?.page_size ?? 25;
  const totalCompanies = state.boardMeta?.total_companies ?? null;
  return {
    page: state.boardPage ?? 1,
    pageSize,
    totalCompanies,
    totalPages: boardTotalPages(),
    loading,
  };
}

export function syncBoardView({ loading = false } = {}) {
  publishBoardView({
    loading,
    pagination: paginationView(loading),
    companies: loading ? [] : getDisplayCompanies(),
    ui: {
      collapsed: [...state.collapsedCompanies],
      showNotForMe: [...state.showNotForMeCompanies],
      showRejected: [...state.showRejectedCompanies],
      fetchingCompanyKey: state.fetchingCompanyKey,
      serverFetchRunning: state.serverFetchRunning,
      scrapeEnabled: state.scrapeConfig?.scrape_enabled !== false,
      positionRejectedOnly: Boolean($("positionRejectedOnly")?.checked),
      visaOnly: Boolean($("visaOnly")?.checked),
    },
  });
}
