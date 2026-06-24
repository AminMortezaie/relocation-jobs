/** Board load path: catalog from server, panel filters on the client. */

import { state } from "./state.js";
import { $ } from "./utils.js";
import { fetchBoard, fetchBoardUserStats } from "./api.js";
import { renderStats, releaseCompanyOrder } from "./render.js";
import {
  applyPanelFilters,
  computeViewStats,
  mergeBoardStats,
} from "./board-filter.js";
import { syncBoardView } from "./board-view.js";

function catalogScopeKey() {
  const country = $("country")?.value || "all";
  const ats = $("ats")?.value || "all";
  const location = $("location")?.value || "all";
  return `${country}|${ats}|${location}`;
}

function persistScopeSelection() {
  const country = $("country")?.value;
  if (country) localStorage.setItem("panel_country", country);
  if ($("ats")) localStorage.setItem("panel_ats", $("ats").value);
  if ($("location")) localStorage.setItem("panel_location", $("location").value);
}

export function showJobsLoading() {
  syncBoardView({ loading: true });
}

export function applyBoardView() {
  state.allCompanies = applyPanelFilters(state.boardCatalog);
  const viewStats = computeViewStats(state.allCompanies, state.boardMeta || {});
  state.boardStats = mergeBoardStats(viewStats, state.boardUserStats || {});
  renderStats(state.boardStats);
  syncBoardView();
}

async function loadBoardCatalog(options = {}) {
  persistScopeSelection();
  const data = await fetchBoard(options);
  state.boardCatalog = data.companies || [];
  state.boardMeta = data.meta || {};
  state.boardScopeKey = catalogScopeKey();
}

async function loadBoardUserStats() {
  state.boardUserStats = await fetchBoardUserStats();
}

export async function loadBoard(options = {}) {
  if (!options.silent) releaseCompanyOrder();

  const scopeChanged = state.boardScopeKey !== catalogScopeKey();
  const needsCatalog = options.force || scopeChanged || !state.boardCatalog.length;

  if (needsCatalog) {
    if (!options.silent) showJobsLoading();
    await Promise.all([loadBoardCatalog(options), loadBoardUserStats()]);
  } else if (options.refreshUserStats) {
    await loadBoardUserStats();
  }

  applyBoardView();
}

export async function refreshBoardUserStats() {
  await loadBoardUserStats();
  applyBoardView();
}

export { catalogScopeKey };
