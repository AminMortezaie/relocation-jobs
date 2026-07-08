/** Admin dashboard — catalog ops, users, fetch history, system config. */

import { initAdminWorker } from "./admin-worker.js";
import { buildAdminStatsHtml } from "./stats-dashboard.js";
import { $, escapeHtml, escapeAttr, setLoadingProgress, finishLoadingProgress, formatActivityBadge } from "./utils.js";

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
  const worker = $("adminWorkerSection");
  const panelStats = $("adminPanelStats");
  const catalog = $("adminCatalog");
  const users = $("adminUsers");
  const newJobs = $("adminNewJobs");
  const runs = $("adminFetchRuns");
  const config = $("adminConfig");
  if (worker) worker.innerHTML = `<div class="skeleton-admin-stats">${skeletonStatCards(3)}</div>`;
  if (panelStats) panelStats.innerHTML = `<div class="skeleton-admin-stats">${skeletonStatCards(4)}</div>`;
  if (catalog) catalog.innerHTML = `<div class="skeleton-admin-table">${skeletonRows(5)}</div>`;
  if (users) users.innerHTML = `<div class="skeleton-admin-table">${skeletonRows(3)}</div>`;
  if (newJobs) newJobs.innerHTML = `<div class="skeleton-admin-table">${skeletonRows(4)}</div>`;
  if (runs) runs.innerHTML = `<div class="skeleton-admin-table">${skeletonRows(4)}</div>`;
  if (config) config.innerHTML = `<div class="skeleton-admin-table">${skeletonRows(3)}</div>`;
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

function renderPanelStats(stats, userCount) {
  const mount = $("adminPanelStats");
  if (!mount) return;
  mount.innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">Your pipeline</h2>
      <p class="hint">Actionable roles for your account across the full catalog. Stored roles in Postgres may be higher.</p>
      <p class="hint admin-pipeline-meta">${userCount ?? 1} user${userCount === 1 ? "" : "s"} · open roles exclude applied, rejected, and not-for-me</p>
      ${buildAdminStatsHtml(stats, { escapeHtml, formatActivityBadge })}
    </section>
  `;
}

function lastFetchByCountry(countryMeta) {
  const map = {};
  for (const row of countryMeta || []) {
    if (row.country) map[row.country] = row.last_fetch || "";
  }
  return map;
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

  const lastFetch = lastFetchByCountry(data.country_meta);

  const countryRows = (data.countries || [])
    .map(
      (row) => `
      <tr>
        ${adminCell(escapeHtml(row.label), "Country")}
        ${adminCell(row.companies, "Companies")}
        ${adminCell(row.jobs, "Stored roles")}
        ${adminCell(row.visa_jobs, "Visa")}
        ${adminCell(escapeHtml(formatTs(lastFetch[row.country] || "")), "Last fetch")}
        ${adminCell(row.missing_locations, "No locations")}
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
      <p class="hint">Raw Postgres counts — not filtered by your tracking state.</p>
      <div class="admin-table-wrap">
        <table class="admin-table admin-table--responsive">
          <thead>
            <tr>
              <th>Country</th><th>Companies</th><th>Stored roles</th><th>Visa</th><th>Last fetch</th><th>No locations</th>
            </tr>
          </thead>
          <tbody>${countryRows || '<tr><td colspan="6">No data</td></tr>'}</tbody>
        </table>
      </div>
      <div class="admin-split">
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
        ${adminCell(user.applied_positions, "Applied")}
        ${adminCell(user.rejected_positions, "Rejected")}
        ${adminCell(user.not_for_me_positions, "Not for me")}
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
              <th>Username</th><th>Created</th><th>Applied</th><th>Rejected</th><th>Not for me</th><th>Fetches</th>
            </tr>
          </thead>
          <tbody>${rows || '<tr><td colspan="6">No users</td></tr>'}</tbody>
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
        </tr>
      `;
    })
    .join("");

  $("adminFetchRuns").innerHTML = `
    <section class="admin-panel">
      <details class="admin-details">
        <summary>Recent fetch runs (${(data.runs || []).length})</summary>
        <div class="admin-table-wrap">
          <table class="admin-table admin-table--responsive">
            <thead>
              <tr><th>Started</th><th>User</th><th>Target</th><th>New</th><th>Duration</th><th>Status</th></tr>
            </thead>
            <tbody>${rows || '<tr><td colspan="6">No fetch runs yet</td></tr>'}</tbody>
          </table>
        </div>
      </details>
    </section>
  `;
}

function renderNewJobs(data) {
  const jobs = data.jobs || [];
  if (!jobs.length) {
    $("adminNewJobs").innerHTML = `
      <section class="admin-panel">
        <h2 class="admin-panel-title">Today's new positions</h2>
        <p class="hint">No positions fetched today.</p>
      </section>
    `;
    return;
  }
  const rows = jobs
    .map((job) => {
      const title = escapeHtml(job.title || "Untitled");
      const company = escapeHtml(job.company_name || "?");
      const country = escapeHtml(job.country || "?");
      const fetched = formatTs(job.fetched);
      const visa = job.visa_sponsorship
        ? '<span class="badge visa">Visa</span>'
        : "";
      return `
        <tr>
          ${adminCell(title, "Title")}
          ${adminCell(company, "Company")}
          ${adminCell(country, "Country")}
          ${adminCell(fetched, "Fetched")}
          ${adminCell(visa, "Visa")}
        </tr>
      `;
    })
    .join("");

  $("adminNewJobs").innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">Today's new positions</h2>
      <p class="hint">${jobs.length} position${jobs.length === 1 ? "" : "s"} fetched today.</p>
      <details class="admin-details" open>
        <summary>New positions (${jobs.length})</summary>
        <div class="admin-table-wrap" style="margin-top:0.55rem">
          <table class="admin-table admin-table--responsive">
            <thead>
              <tr><th>Title</th><th>Company</th><th>Country</th><th>Fetched</th><th>Visa</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </details>
    </section>
  `;
}

function renderConfig(data) {
  const redisLabel = data.countries_store === "redis" && data.redis_ping
    ? "redis (connected)"
    : escapeHtml(data.countries_store || "—");

  $("adminConfig").innerHTML = `
    <section class="admin-panel">
      <h2 class="admin-panel-title">System</h2>
      <dl class="admin-dl">
        <dt>Database</dt><dd>${escapeHtml(data.database)}</dd>
        <dt>Countries store</dt><dd>${redisLabel}</dd>
        <dt>Scrape on this host</dt><dd>${data.scrape_enabled ? "enabled" : "disabled (worker only)"}</dd>
        <dt>Registration</dt><dd>${data.allow_register ? "open" : "closed"}</dd>
        <dt>Concurrency</dt><dd>default ${data.default_concurrency}, max ${data.max_concurrency}</dd>
      </dl>
    </section>
  `;
}

async function loadDashboard() {
  $("adminError").hidden = true;
  showAdminSkeletons();
  setLoadingProgress(15);
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const data = await apiGet(`/api/admin/dashboard?limit=15&timezone=${encodeURIComponent(tz)}`);
  setLoadingProgress(80);
  renderCatalog(data.catalog);
  renderUsers(data.users);
  renderNewJobs(await apiGet("/api/admin/recent-jobs?limit=30"));
  renderFetchRuns(data.runs);
  renderConfig(data.config);
  await initAdminWorker(data.worker);
  finishLoadingProgress();
  void loadPanelStats(data.user_count, tz);
}

async function loadPanelStats(userCount, timezone) {
  const mount = $("adminPanelStats");
  if (!mount) return;
  try {
    const stats = await apiGet(
      `/api/admin/panel-stats?timezone=${encodeURIComponent(timezone)}`,
    );
    renderPanelStats(stats, userCount);
  } catch (err) {
    mount.innerHTML = `
      <section class="admin-panel">
        <h2 class="admin-panel-title">Your pipeline</h2>
        <p class="hint admin-error">${escapeHtml(err.message || "Could not load pipeline stats")}</p>
      </section>
    `;
  }
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
      await loadDashboard();
    } catch (err) {
      $("adminError").hidden = false;
      $("adminError").textContent = err.message || "Failed to load admin data";
    }
  }
}

init();
