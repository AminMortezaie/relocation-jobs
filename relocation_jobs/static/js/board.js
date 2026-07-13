/** Board load path: paginated catalog from server, local UI filters only. */

import { state } from "./state.js";
import { $, beginTopLoadingProgress, finishLoadingProgress, setLoadingProgress } from "./utils.js";
import { fetchBoard, fetchBoardUserStats } from "./api.js";
import { releaseCompanyOrder } from "./render.js";
import { syncBoardView } from "./board-view.js";
import { beginScreenLoad, endScreenLoad, setScreenLoadProgress } from "./screen-loader.js";

function overlayLabel(options, page, requestChanged) {
  if (options.overlayLabel) return options.overlayLabel;
  if (requestChanged) return "Updating board…";
  if (page > 1) return "Loading page…";
  return "Loading board…";
}

function catalogScopeKey() {
  const country = $("country")?.value || "all";
  const ats = $("ats")?.value || "all";
  const location = $("location")?.value || "all";
  return `${country}|${ats}|${location}`;
}

function boardRequestKey() {
  const search = $("search")?.value.trim() || "";
  const filterIds = [
    "visaOnly",
    "hideApplied",
    "hideEmpty",
    "notAppliedOnly",
    "hidePositionApplied",
    "hidePositionRejected",
    "positionAppliedOnly",
    "positionRejectedOnly",
    "positionLookingToApplyOnly",
    "fetchOkOnly",
    "fetchProblemOnly",
  ];
  const flags = filterIds.map((id) => `${id}:${Boolean($(id)?.checked)}`).join("|");
  const sort = $("sortSelect")?.value === "name" ? "name" : "newest";
  return `${catalogScopeKey()}|${flags}|${search}|sort:${sort}`;
}

function boardPageSize() {
  return state.boardMeta?.page_size ?? 25;
}

export function boardTotalPages() {
  if (state.boardMeta?.total_pages != null) {
    return state.boardMeta.total_pages;
  }
  const total = state.boardMeta?.total_companies;
  if (total == null) return 1;
  return Math.max(1, Math.ceil(total / boardPageSize()));
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

export function applyBoardView({ enterAnimation = false } = {}) {
  state.allCompanies = state.boardCatalog;
  const jobsEl = document.getElementById("jobs");
  if (enterAnimation) {
    jobsEl?.classList.add("board-enter");
  } else {
    jobsEl?.classList.remove("board-enter");
  }
  syncBoardView();
  if (enterAnimation && jobsEl) {
    window.clearTimeout(state.boardEnterTimer);
    state.boardEnterTimer = window.setTimeout(() => {
      jobsEl.classList.remove("board-enter");
      state.boardEnterTimer = null;
    }, 400);
  }
}

async function loadBoardCatalog(options = {}) {
  persistScopeSelection();
  const page = options.page ?? state.boardPage ?? 1;
  const requestKey = boardRequestKey();
  const preserveMeta = !options.requestChanged && state.boardRequestKey === requestKey;
  const data = await fetchBoard({ ...options, page });
  const prevTotal = preserveMeta ? state.boardMeta?.total_companies : null;
  const prevPageSize = preserveMeta ? state.boardMeta?.page_size : null;
  const prevTotalPages = preserveMeta ? state.boardMeta?.total_pages : null;
  state.boardCatalog = data.companies || [];
  state.boardMeta = preserveMeta
    ? { ...state.boardMeta, ...(data.meta || {}) }
    : { ...(data.meta || {}) };
  if (data.meta?.total_companies == null && prevTotal != null) {
    state.boardMeta.total_companies = prevTotal;
  }
  if (data.meta?.page_size == null && prevPageSize != null) {
    state.boardMeta.page_size = prevPageSize;
  }
  if (data.meta?.total_pages == null && prevTotalPages != null) {
    state.boardMeta.total_pages = prevTotalPages;
  }
  state.boardUserStats = data.user_stats || {};
  state.boardPage = data.meta?.page ?? page;
  state.boardScopeKey = catalogScopeKey();
  state.boardRequestKey = requestKey;
}

async function loadBoardUserStats() {
  state.boardUserStats = await fetchBoardUserStats();
}

export async function loadBoard(options = {}) {
  const requestChanged = state.boardRequestKey !== boardRequestKey();
  let page = options.page ?? state.boardPage ?? 1;
  if (requestChanged || (options.force && options.page == null)) {
    page = 1;
  }

  const preserveContent = options.preserveContent === true;
  const useOverlay = options.noOverlay !== true;
  const useTopBar = !useOverlay;
  const enterAnimation = options.enterAnimation !== false && !preserveContent;
  if (useOverlay) {
    beginScreenLoad(overlayLabel(options, page, requestChanged));
  } else if (useTopBar) {
    beginTopLoadingProgress(12);
  }

  releaseCompanyOrder();
  if (preserveContent) {
    syncBoardView({ loading: true, preserveContent: true });
  } else {
    showJobsLoading();
  }

  try {
    if (useOverlay) setScreenLoadProgress(20);
    else if (useTopBar) setLoadingProgress(28);
    await loadBoardCatalog({ ...options, page, requestChanged });
    if (useOverlay) setScreenLoadProgress(72);
    else if (useTopBar) setLoadingProgress(82);

    const totalPages = boardTotalPages();
    if (state.boardPage > totalPages) {
      await loadBoardCatalog({ ...options, page: 1, requestChanged: false });
    }

    if (options.refreshUserStats) {
      if (useOverlay) setScreenLoadProgress(86);
      else if (useTopBar) setLoadingProgress(90);
      await loadBoardUserStats();
    }

    if (useOverlay) setScreenLoadProgress(94);
    else if (useTopBar) setLoadingProgress(96);
    applyBoardView({ enterAnimation });
  } finally {
    if (useOverlay) endScreenLoad();
    else if (useTopBar) finishLoadingProgress();
  }
}

export async function goToBoardPage(page) {
  if (state.boardRequestKey !== boardRequestKey()) {
    await loadBoard({ overlayLabel: "Updating board…" });
    return;
  }
  const totalPages = boardTotalPages();
  const next = Math.max(1, Math.min(Number(page) || 1, totalPages));
  if (next === state.boardPage && state.boardCatalog.length) return;
  await loadBoard({ page: next, overlayLabel: "Loading page…" });
  document.getElementById("board-toolbar")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export async function refreshBoardUserStats() {
  await loadBoardUserStats();
  applyBoardView();
}

export { catalogScopeKey, boardRequestKey };
