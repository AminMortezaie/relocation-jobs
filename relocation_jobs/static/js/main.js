/** Application entry point. */

import { setOnUnauthorized } from "./state.js";
import { showLogin, refreshAuth, setLoginMode } from "./auth.js";
import { loadConfig, loadCountries, loadCities, loadJobs, showJobsLoading, setLoadingProgress, finishLoadingProgress } from "./data.js";
import { bindDialogEvents } from "./dialogs.js";
import { bindEvents } from "./events.js";
import { bindFilterBar, refreshFilterBar } from "./filters.js";
import { bindHeaderBar } from "./header.js";
import { resumeFetchIfRunning } from "./scrape.js";
import {
  loadCollapsedCompanies,
  loadShowNotForMeCompanies,
  loadShowRejectedCompanies,
  loadFilterPreferences,
  loadSortPreference,
} from "./storage.js";

async function init() {
  setOnUnauthorized(showLogin);

  loadCollapsedCompanies();
  loadShowNotForMeCompanies();
  loadShowRejectedCompanies();
  loadSortPreference();
  loadFilterPreferences();
  setLoginMode("login");

  bindEvents();
  bindDialogEvents();
  bindFilterBar();
  bindHeaderBar();

  const ok = await refreshAuth();
  if (!ok) return;

  showJobsLoading();
  setLoadingProgress(10);
  await Promise.all([loadConfig(), loadCountries()]);
  setLoadingProgress(40);
  refreshFilterBar();
  await Promise.all([loadCities(), loadJobs()]);
  finishLoadingProgress();
  await resumeFetchIfRunning();
}

init();
