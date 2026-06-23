/** Admin dashboard — catalog ops, users, fetch history, system config. */

import { initAdminFetch } from "./admin-scrape.js";
import { $, escapeHtml, escapeAttr, setLoadingProgress, finishLoadingProgress } from "./utils.js";

function skeletonRows(n = 4) {
  return Array(n).fill(0).map(() =>
    `<div class="skeleton-block skeleton-admin-row"></div>`
  ).join("");
}

function skeletonStatCards(n = 4) {
  return Array(n).fill(0).map(() =>
    `<div class="skeleton-block skeleton-admin-stat"></div>`
  ).join("");
}

function showAdminSkeletons() {
  const overview = $("adminOverview");
  const catalog = $("adminCatalog");
  const users = $("adminUsers");
  const runs = $("adminFetchRuns");
  const config = $("adminConfig");
  if (overview) overview.innerHTML = `<div class="skeleton-admin-stats">${skeletonStatCards(6)}</div>`;
  if (catalog) catalog.innerHTML = `<div class="skeleton-admin-table">${skeletonRows(5)}</div>`;
  if (users)   users.innerHTML   = `<div class="skeleton-admin-table">${skeletonRows(3)}</div>`;
  if (runs)    runs.innerHTML    = `<div class="skeleton-admin-table">${skeletonRows(6)}</div>`;
  if (config)  config.innerHTML  = `<div class="skeleton-admin-table">${skeletonRows(4)}</div>`;
}

function formatTs(value) {
  const v = String(value ?? "").trim();
  if (!v) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;

  const cleaned = v.replace(/\.\d+(?=[Z+-]|$)/, "");
  const parsed = new Date(cleaned.includes("T") ? cleaned : `${cleaned}T00:00:00`);
  if (!Number.isNaN(parsed.getTime())) {
    const pad = (n) => String(n).padStart(2, "0");
    const date = `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`;
    if (!/[T ]\d{2}:\d{2}/.test(v)) return date;
    return parsed.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  const match = v.match(/^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))/);
  if (match) return `${match[1]} ${match[2]}`;
  return v.split(/[T+]/)[0] || v;
}

function statCard(value, label, { accent = false, muted = false } = {}) {
  const classes = [
    "stat-card",
    accent ? "stat-card--accent" : "",
    muted ? "stat-card--muted" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return `<div class="${classes}"><div class="value">${value}</div><div class="label">${escapeHtml(label)}</div></div>`;
}

function adminCell(value, label) {
  return `<td data-label="${escapeAttr(label)}">${value}</td>`;
}

async function apiGet(path) {
  const res = await fetch(path, { credentials: "same-origin" });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    showLogin();
    throw new Error("Authentication required");
  }
  if (res.status === 403) {
    showDenied();
    throw new Error("Admin access required");
  }
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function showLogin(message = "") {
  $("adminContent").classList.add("hidden");
  $("adminDenied").hidden = true;
  $("adminLoginPanel").hidden = false;
  $("adminLoginError").textContent = message;
}

function showDenied() {
  $("adminContent").classList.add("hidden");
  $("adminLoginPanel").hidden = true;
  $("adminDenied").hidden = false;
}

function showAdmin() {
  $("adminLoginPanel").hidden = true;
  $("adminDenied").hidden = true;
  $("adminContent").classList.remove("hidden");
}

function renderOverview(data) {
  const catalog = data.catalog || {};
  const tracking = data.tracking || {};
  const fetch = data.fetch || {};
  const fetchLabel = fetch.running
    ? `Running (${escapeHtml(fetch.country || "?")}${fetch.ats_type ? ` · ${escapeHtml(fetch.ats_type)}` : ""}${fetch.company ? ` · ${escapeHtml(fetch.company)}` : ""})`
    : "Idle";

  $("adminOverview").innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">Overview</h2>
      <div class="stats-grid admin-stats-grid">
        ${statCard(data.users ?? 0, "Users", { accent: true })}
        ${statCard(catalog.companies ?? 0, "Companies")}
        ${statCard(catalog.jobs ?? 0, "Open roles")}
        ${statCard(catalog.fetch_problems ?? 0, "Fetch issues")}
        ${statCard(tracking.applied_positions ?? 0, "Applied (all users)")}
        ${statCard(tracking.tracking_rows ?? 0, "Tracking rows")}
        ${statCard(fetchLabel, "Scrape", { muted: true })}
      </div>
    </section>
  `;
}

function renderCatalog(data) {
  if (!data.has_data) {
    $("adminCatalog").innerHTML = `
      <section class="admin-panel">
        <h2 class="admin-panel-title">Catalog</h2>
        <p class="hint">No catalog data in the database yet.</p>
      </section>
    `;
    $("adminFetchProblems").innerHTML = "";
    return;
  }

  const countryRows = (data.countries || [])
    .map(
      (row) => `
      <tr>
        ${adminCell(escapeHtml(row.label), "Country")}
        ${adminCell(row.companies, "Companies")}
        ${adminCell(row.jobs, "Jobs")}
        ${adminCell(row.visa_jobs, "Visa")}
        ${adminCell(row.fetch_problems, "Fetch issues")}
        ${adminCell(row.missing_locations, "No locations")}
      </tr>
    `
    )
    .join("");

  const metaRows = (data.country_meta || [])
    .map(
      (row) => `
      <tr>
        ${adminCell(escapeHtml(row.label), "Country")}
        ${adminCell(escapeHtml(formatTs(row.last_fetch)), "Last fetch")}
        ${adminCell(row.last_fetch_new_jobs, "New jobs")}
        ${adminCell(row.total, "Total co.")}
      </tr>
    `
    )
    .join("");

  const atsRows = (data.by_ats || [])
    .slice(0, 12)
    .map(
      (row) => `
      <tr>
        ${adminCell(`<code>${escapeHtml(row.ats_type)}</code>`, "ATS")}
        ${adminCell(row.companies, "Companies")}
      </tr>
    `
    )
    .join("");

  $("adminCatalog").innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">Catalog by country</h2>
      <div class="admin-table-wrap">
        <table class="admin-table admin-table--responsive">
          <thead>
            <tr>
              <th>Country</th><th>Companies</th><th>Jobs</th><th>Visa</th><th>Fetch issues</th><th>No locations</th>
            </tr>
          </thead>
          <tbody>${countryRows || '<tr><td colspan="6">No data</td></tr>'}</tbody>
        </table>
      </div>
      <div class="admin-split">
        <div>
          <h3 class="admin-subheading">Last fetch meta</h3>
          <div class="admin-table-wrap">
            <table class="admin-table admin-table--responsive">
              <thead><tr><th>Country</th><th>Last fetch</th><th>New jobs</th><th>Total co.</th></tr></thead>
              <tbody>${metaRows || '<tr><td colspan="4">No meta</td></tr>'}</tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 class="admin-subheading">ATS breakdown</h3>
          <div class="admin-table-wrap">
            <table class="admin-table admin-table--responsive">
              <thead><tr><th>ATS</th><th>Companies</th></tr></thead>
              <tbody>${atsRows || '<tr><td colspan="2">No ATS data</td></tr>'}</tbody>
            </table>
          </div>
        </div>
      </div>
      <p class="hint admin-footnote">
        Empty companies: ${data.totals?.empty_companies ?? 0} ·
        Visa roles: ${data.totals?.visa_jobs ?? 0} ·
        Stored roles: ${data.totals?.stored_jobs ?? data.totals?.jobs ?? 0}
      </p>
    </section>
  `;

  const problems = data.fetch_problem_companies || [];
  $("adminFetchProblems").innerHTML = problems.length
    ? `
    <section class="admin-panel">
      <h2 class="admin-panel-title">Fetch problems (${problems.length})</h2>
      <div class="admin-table-wrap">
        <table class="admin-table admin-table--responsive">
          <thead>
            <tr><th>Country</th><th>Company</th><th>ATS</th><th>Since</th><th>Careers URL</th></tr>
          </thead>
          <tbody>
            ${problems
              .map(
                (row) => `
              <tr>
                ${adminCell(escapeHtml(row.country), "Country")}
                ${adminCell(escapeHtml(row.name), "Company")}
                ${adminCell(`<code>${escapeHtml(row.ats_type || "—")}</code>`, "ATS")}
                ${adminCell(escapeHtml(row.fetch_problem_date || "—"), "Since")}
                ${adminCell(`<span class="admin-url">${escapeHtml(row.careers_url || "—")}</span>`, "Careers URL")}
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </section>
  `
    : "";
}

function renderUsers(data) {
  const rows = (data.users || [])
    .map(
      (user) => `
      <tr>
        ${adminCell(`${escapeHtml(user.username)}${user.is_admin ? ' <span class="admin-badge">admin</span>' : ""}`, "Username")}
        ${adminCell(formatTs(user.created_at), "Created")}
        ${adminCell(user.tracking_rows, "Tracking")}
        ${adminCell(user.applied_positions, "Applied")}
        ${adminCell(user.rejected_positions, "Rejected")}
        ${adminCell(user.not_for_me_positions, "Hidden")}
        ${adminCell(user.fetch_runs, "Fetches")}
      </tr>
    `
    )
    .join("");

  $("adminUsers").innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">Users</h2>
      <div class="admin-table-wrap">
        <table class="admin-table admin-table--responsive">
          <thead>
            <tr>
              <th>Username</th><th>Created</th><th>Tracking</th><th>Applied</th><th>Rejected</th><th>Hidden</th><th>Fetches</th>
            </tr>
          </thead>
          <tbody>${rows || '<tr><td colspan="7">No users</td></tr>'}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderFetchRuns(data) {
  const rows = (data.runs || [])
    .map((run) => {
      const target =
        run.scope === "company"
          ? `${run.country} · ${run.company_name || "?"}`
          : run.country;
      const status = run.cancelled
        ? "cancelled"
        : run.exit_code === 0
          ? "ok"
          : run.exit_code == null
            ? "—"
            : `exit ${run.exit_code}`;
      return `
        <tr>
          ${adminCell(formatTs(run.started_at), "Started")}
          ${adminCell(escapeHtml(run.username || "?"), "User")}
          ${adminCell(escapeHtml(target), "Target")}
          ${adminCell(run.new_jobs ?? 0, "New")}
          ${adminCell(run.duration_seconds != null ? `${Math.round(run.duration_seconds)}s` : "—", "Duration")}
          ${adminCell(escapeHtml(status), "Status")}
          ${adminCell(`<span class="admin-url">${escapeHtml(run.result_line || "—")}</span>`, "Result")}
        </tr>
      `;
    })
    .join("");

  $("adminFetchRuns").innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">Fetch runs (all users)</h2>
      <div class="admin-table-wrap">
        <table class="admin-table admin-table--responsive">
          <thead>
            <tr><th>Started</th><th>User</th><th>Target</th><th>New</th><th>Duration</th><th>Status</th><th>Result</th></tr>
          </thead>
          <tbody>${rows || '<tr><td colspan="7">No fetch runs yet</td></tr>'}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderConfig(data) {
  const keywordList = (items) =>
    items.map((item) => `<code>${escapeHtml(item)}</code>`).join(", ");

  const customCities = Object.entries(data.custom_cities || {})
    .map(([country, cities]) => `${escapeHtml(country)}: ${(cities || []).length}`)
    .join(" · ");

  $("adminConfig").innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">System config</h2>
      <dl class="admin-dl">
        <dt>Database</dt><dd>${escapeHtml(data.database)}</dd>
        <dt>Data dir</dt><dd><code>${escapeHtml(data.data_dir)}</code></dd>
        <dt>Scrape enabled</dt><dd>${data.scrape_enabled ? "yes" : "no"}</dd>
        <dt>Registration</dt><dd>${data.allow_register ? "open" : "closed"}</dd>
        <dt>HTTPX</dt><dd>${data.httpx_available ? "available" : "missing"}</dd>
        <dt>Concurrency</dt><dd>default ${data.default_concurrency}, max ${data.max_concurrency}</dd>
        <dt>Archives</dt><dd>${(data.archives || []).map((a) => `<code>${escapeHtml(a)}</code>`).join(" ") || "—"}</dd>
        <dt>Known ATS overrides</dt><dd>${data.known_ats_count} companies</dd>
        <dt>Custom cities</dt><dd>${customCities || "none"}</dd>
      </dl>
      <details class="admin-details">
        <summary>Include keywords (${(data.include_keywords || []).length})</summary>
        <p class="admin-keywords">${keywordList(data.include_keywords || [])}</p>
      </details>
      <details class="admin-details">
        <summary>Exclude keywords (${(data.exclude_keywords || []).length})</summary>
        <p class="admin-keywords">${keywordList(data.exclude_keywords || [])}</p>
      </details>
      <details class="admin-details">
        <summary>Known ATS companies</summary>
        <p class="admin-keywords">${keywordList(data.known_ats_companies || [])}</p>
      </details>
    </section>
  `;
}

async function loadDashboard() {
  $("adminError").hidden = true;
  showAdminSkeletons();
  setLoadingProgress(15);
  const data = await apiGet("/api/admin/dashboard?limit=50");
  setLoadingProgress(80);
  renderOverview(data.overview);
  renderCatalog(data.catalog);
  renderUsers(data.users);
  renderFetchRuns(data.runs);
  renderConfig(data.config);
  finishLoadingProgress();
}

window.adminReloadDashboard = loadDashboard;

async function refreshAuth() {
  const res = await fetch("/api/auth/status", { credentials: "same-origin" });
  const data = await res.json();
  if (!data.authenticated) {
    showLogin();
    return false;
  }
  if (!data.user?.is_admin) {
    showDenied();
    return false;
  }
  showAdmin();
  return true;
}

async function submitLogin(event) {
  event.preventDefault();
  $("adminLoginError").textContent = "";
  const username = $("adminLoginUsername").value.trim();
  const password = $("adminLoginPassword").value;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("adminLoginError").textContent = data.error || "Sign in failed";
      return;
    }
    if (!data.user?.is_admin) {
      showDenied();
      return;
    }
    $("adminLoginPassword").value = "";
    showAdmin();
    await initAdminFetch();
    await loadDashboard();
  } catch {
    $("adminLoginError").textContent = "Network error";
  }
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  showLogin();
}

async function init() {
  $("adminLoginForm").addEventListener("submit", submitLogin);
  $("adminLogoutBtn").addEventListener("click", logout);
  $("adminRefreshBtn").addEventListener("click", async () => {
    try {
      await loadDashboard();
    } catch (err) {
      $("adminError").hidden = false;
      $("adminError").textContent = err.message || "Failed to refresh";
    }
  });

  if (await refreshAuth()) {
    try {
      await initAdminFetch();
      await loadDashboard();
    } catch (err) {
      $("adminError").hidden = false;
      $("adminError").textContent = err.message || "Failed to load admin data";
    }
  }
}

init();
