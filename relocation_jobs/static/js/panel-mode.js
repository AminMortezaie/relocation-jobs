/** Panel domain mode: relocation (/panel) vs remote (/remote). */

export function detectPanelMode(pathname = window.location.pathname) {
  const path = (pathname || "").replace(/\/+$/, "") || "/";
  return path === "/remote" || path.endsWith("/remote") ? "remote" : "relocation";
}

export const panelMode = detectPanelMode();

export function isRemotePanel() {
  return panelMode === "remote";
}

export function panelApiPrefix() {
  return isRemotePanel() ? "/api/remote" : "/api";
}

export function panelStorageKey(base) {
  return isRemotePanel() ? `remote_${base}` : `panel_${base}`;
}

export function applyPanelChrome() {
  const remote = isRemotePanel();
  document.body.dataset.panelMode = panelMode;

  document.querySelectorAll(".brand-tagline").forEach((el) => {
    el.textContent = remote ? "Remote roles worldwide" : "Visa-friendly roles abroad";
  });

  const loginHint = document.getElementById("loginHint");
  if (loginHint && !document.getElementById("loginSubmit")?.disabled) {
    const register = document.getElementById("loginTitle")?.textContent === "Create account";
    if (!register) {
      loginHint.textContent = remote
        ? "Track remote roles from aggregator boards."
        : "Track applications and relocation-friendly roles per country.";
    }
  }

  const countryLabel = document.querySelector('label[for="country"]');
  const countrySelect = document.getElementById("country");
  if (countryLabel) countryLabel.textContent = remote ? "Board" : "Country";
  if (countrySelect) countrySelect.setAttribute("aria-label", remote ? "Board" : "Country");

  const addCompanyBtn = document.getElementById("addCompanyBtn");
  if (addCompanyBtn) addCompanyBtn.hidden = remote;

  const visaRow = document.getElementById("visaOnly")?.closest("li");
  if (visaRow) visaRow.hidden = remote;

  const relocationNav = document.getElementById("panelNavRelocation");
  const remoteNav = document.getElementById("panelNavRemote");
  if (relocationNav) {
    relocationNav.classList.toggle("is-active", !remote);
    relocationNav.setAttribute("aria-current", remote ? "false" : "page");
  }
  if (remoteNav) {
    remoteNav.classList.toggle("is-active", remote);
    remoteNav.setAttribute("aria-current", remote ? "page" : "false");
  }
}
