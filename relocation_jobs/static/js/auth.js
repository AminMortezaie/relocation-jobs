/** Login, registration, and session UI. */

import { state } from "./state.js";
import { $ } from "./utils.js";
import { loadConfig, loadCountries, loadAtsTypes, loadBoardWithLocations, showJobsLoading, setLoadingProgress, finishLoadingProgress } from "./data.js";
import { beginScreenLoad } from "./screen-loader.js";
import { refreshFilterBar } from "./filters.js";
import { updateFetchHeaderUI } from "./render.js";

export function showLogin(message = "") {
  $("mainContent").classList.add("hidden");
  $("loginPanel").hidden = false;
  $("loginError").textContent = message;
  $("loginUsername").focus();
}

export function setAdminNavVisible(visible) {
  const adminLink = $("adminLink");
  const adminPanelBtn = $("adminPanelBtn");
  state.fetchControlsEnabled = Boolean(visible) && state.scrapeConfig?.scrape_enabled !== false;
  if (adminLink) adminLink.hidden = !visible;
  if (adminPanelBtn) adminPanelBtn.hidden = !visible;
  updateFetchHeaderUI();
}

export function showApp() {
  $("loginPanel").hidden = true;
  $("mainContent").classList.remove("hidden");
  const user = state.authState.user;
  if (user) {
    const initial = (user.username || "?").charAt(0).toUpperCase();
    $("userAvatar").textContent = initial;
    $("userName").textContent = user.username;
    $("userMenuBtn").title = user.username;
    setAdminNavVisible(Boolean(user.is_admin));
  } else {
    $("userAvatar").textContent = "?";
    $("userName").textContent = "Account";
    $("userMenuBtn").title = "Account";
    setAdminNavVisible(false);
  }
}

export function setLoginMode(mode) {
  state.loginMode = mode;
  const register = mode === "register";
  $("loginTitle").textContent = register ? "Create account" : "Sign in";
  $("loginSubmit").textContent = register ? "Create account" : "Sign in";
  $("loginPassword").autocomplete = register ? "new-password" : "current-password";
  $("toggleRegister").textContent = register ? "Back to sign in" : "Create account";
  $("loginHint").textContent = register
    ? "Password must be at least 8 characters."
    : "Track applications and relocation-friendly roles per country.";
}

export async function refreshAuth() {
  const res = await fetch("/api/auth/status", { credentials: "same-origin" });
  state.authState = await res.json();
  $("toggleRegister").hidden = !state.authState.allow_register;
  if (state.authState.authenticated) {
    showApp();
    return true;
  }
  showLogin();
  return false;
}

export async function submitAuth(e) {
  e.preventDefault();
  const username = $("loginUsername").value.trim();
  const password = $("loginPassword").value;
  const endpoint = state.loginMode === "register" ? "/api/auth/register" : "/api/auth/login";
  $("loginSubmit").disabled = true;
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("loginError").textContent = data.error || "Authentication failed";
      return;
    }
    state.authState = data;
    $("loginPassword").value = "";
    $("loginError").textContent = "";
    showApp();
    beginScreenLoad("Loading panel…");
    showJobsLoading();
    setLoadingProgress(10);
    await Promise.all([loadConfig(), loadCountries(), loadAtsTypes()]);
    setAdminNavVisible(Boolean(state.authState.user?.is_admin));
    setLoadingProgress(40);
    refreshFilterBar();
    await loadBoardWithLocations();
    finishLoadingProgress();
  } catch {
    $("loginError").textContent = "Network error";
  } finally {
    $("loginSubmit").disabled = false;
  }
}

export async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  state.authState = { authenticated: false };
  showLogin();
}
