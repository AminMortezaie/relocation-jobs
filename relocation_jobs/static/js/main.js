/** Application entry point. */

import { setOnUnauthorized, state } from "./state.js";
import { showLogin, refreshAuth, setLoginMode, setAdminNavVisible } from "./auth.js";
import { loadConfig, loadCountries, loadAtsTypes, loadBoardWithLocations, showJobsLoading, setLoadingProgress, finishLoadingProgress } from "./data.js";
import { beginScreenLoad } from "./screen-loader.js";
import { bindDialogEvents } from "./dialogs.js";
import { bindEvents, closePanelPopovers } from "./events.js";
import { bindFilterBar, refreshFilterBar } from "./filters.js";
import { bindHeaderBar } from "./header.js";
import { registerFetchActions } from "./fetch-actions.js";
import { publishFetchUi } from "./fetch-ui.js";
import { goToBoardPage } from "./board.js";
import { saveWaitingReferral, markJobSeen } from "./api.js";
import { toast } from "./utils.js";
import { resumeFetchIfRunning, syncFetchStateFromServer } from "./scrape.js";
import { applyPanelChrome } from "./panel-mode.js";
import {
  loadCollapsedCompanies,
  loadShowNotForMeCompanies,
  loadShowRejectedCompanies,
  loadFilterPreferences,
  loadSortPreference,
} from "./storage.js";

window.relocationJobs = window.relocationJobs || {};
window.relocationJobs.goToBoardPage = goToBoardPage;
window.relocationJobs.saveWaitingReferral = saveWaitingReferral;
window.relocationJobs.markJobSeen = markJobSeen;
window.relocationJobs.closePanelPopovers = closePanelPopovers;
window.relocationJobs.toast = toast;

async function init() {
  setOnUnauthorized(showLogin);
  applyPanelChrome();

  loadCollapsedCompanies();
  loadShowNotForMeCompanies();
  loadShowRejectedCompanies();
  loadSortPreference();
  loadFilterPreferences();
  setLoginMode("login");
  applyPanelChrome();

  bindEvents();
  bindDialogEvents();
  bindFilterBar();
  bindHeaderBar();
  registerFetchActions();
  publishFetchUi();

  const ok = await refreshAuth();
  if (!ok) return;

  beginScreenLoad("Loading panel…");
  showJobsLoading();
  setLoadingProgress(10);
  await Promise.all([loadConfig(), loadCountries(), loadAtsTypes()]);
  setAdminNavVisible(Boolean(state.authState.user?.is_admin));
  setLoadingProgress(40);
  refreshFilterBar();
  await loadBoardWithLocations();
  finishLoadingProgress();
  await resumeFetchIfRunning();
  await syncFetchStateFromServer();
}

init();
