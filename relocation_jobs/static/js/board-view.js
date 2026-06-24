/** Build the view model passed to the React board. */

import { state } from "./state.js";
import { $ } from "./utils.js";
import { getDisplayCompanies } from "./render.js";
import { publishBoardView } from "./board-sync.js";

export function syncBoardView({ loading = false } = {}) {
  publishBoardView({
    loading,
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
