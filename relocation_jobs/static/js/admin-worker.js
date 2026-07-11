/** Fetch worker status + live progress modal for admin. */

import { cancelFetchRequest, getFetchStatus } from "./api.js";
import { $, escapeHtml, formatActivityBadge, formatFetchDuration, elapsedSecondsBetween, elapsedSecondsSince } from "./utils.js";

let pollTimer = null;
let fetchBusy = false;
let workerListenersBound = false;

function appendLog(text) {
  const log = $("adminFetchLog");
  if (!log) return;
  log.textContent = text || "";
  log.scrollTop = log.scrollHeight;
}

function updateActivity(st) {
  const wrap = $("adminFetchActivity");
  const step = $("adminFetchActivityStep");
  const detail = $("adminFetchActivityDetail");
  const list = $("adminFetchActivityLog");
  if (!wrap || !step) return;

  const activity = st.activity || {};
  const message = (activity.message || "").trim();
  if (st.running && message) {
    wrap.hidden = false;
    step.textContent = message;
    if (detail) {
      const d = (activity.detail || "").trim();
      detail.textContent = d;
      detail.hidden = !d;
    }
  }

  const entries = st.activity_log || [];
  if (list && entries.length) {
    wrap.hidden = false;
    list.innerHTML = entries
      .slice(-8)
      .map((entry) => {
        const msg = (entry.message || "").trim();
        const det = (entry.detail || "").trim();
        return `<li>${escapeHtml(msg)}${det ? `<span>${escapeHtml(det)}</span>` : ""}</li>`;
      })
      .join("");
  }
}

function hideFetchCompletion() {
  const el = $("adminFetchCompletion");
  if (el) el.hidden = true;
}

function updateFetchRunMeta(st, { running = false, fetchRun = null } = {}) {
  const wrap = $("adminFetchCompletion");
  const labelEl = $("adminFetchCompletionLabel");
  if (!wrap) return;

  const startedAt = fetchRun?.started_at || st?.started_at || "";
  if (!startedAt && !fetchRun) {
    hideFetchCompletion();
    return;
  }

  wrap.hidden = false;
  if (labelEl) labelEl.textContent = running ? "Current run" : "Last run";

  const startedEl = $("adminFetchCompletionStarted");
  const finishedEl = $("adminFetchCompletionFinished");
  const durationEl = $("adminFetchCompletionDuration");
  const newJobsEl = $("adminFetchCompletionNewJobs");

  if (startedEl) startedEl.textContent = formatActivityBadge(startedAt);

  const newJobs = Math.max(0, Number(fetchRun?.new_jobs ?? st?.new_jobs_total) || 0);
  if (newJobsEl) {
    newJobsEl.textContent = newJobs === 1 ? "1 role" : `${newJobs} roles`;
  }

  if (running) {
    if (finishedEl) finishedEl.textContent = "In progress…";
    const elapsed = elapsedSecondsSince(startedAt);
    if (durationEl) {
      durationEl.textContent = elapsed != null ? formatFetchDuration(elapsed) : "—";
    }
    return;
  }

  const finishedAt = fetchRun?.finished_at || st?.finished_at || "";
  if (finishedEl) {
    finishedEl.textContent = finishedAt ? formatActivityBadge(finishedAt) : "—";
  }
  const duration = fetchRun?.duration_seconds
    ?? elapsedSecondsBetween(startedAt, finishedAt)
    ?? null;
  if (durationEl) {
    durationEl.textContent = duration != null ? formatFetchDuration(duration) : "—";
  }
}

function updateProgress({ current = 0, total = 0, company = null, status = "", running = false, cancelled = false, newJobsTotal = 0 }) {
  const wrap = $("adminFetchProgressWrap");
  const label = $("adminFetchProgressLabel");
  const pctEl = $("adminFetchProgressPct");
  const bar = $("adminFetchProgressBar");
  const track = $("adminFetchProgressTrack");
  const companyEl = $("adminFetchCurrentCompany");
  if (!wrap || !label || !pctEl || !bar) return;

  wrap.hidden = false;
  const safeTotal = Math.max(0, total || 0);
  const safeCurrent = Math.max(0, current || 0);
  const pct = safeTotal > 0
    ? Math.min(running ? 99 : 100, Math.round((safeCurrent / safeTotal) * 100))
    : (running ? 0 : 100);
  const newJobs = Math.max(0, Number(newJobsTotal) || 0);
  const newJobsSuffix = newJobs > 0 ? ` · ${newJobs} new` : "";

  label.textContent = safeTotal > 0
    ? `${safeCurrent} / ${safeTotal} companies${newJobsSuffix}`
    : (running ? "Preparing…" : "Done");
  pctEl.textContent = `${pct}%`;
  bar.style.width = `${pct}%`;
  if (track) track.setAttribute("aria-valuenow", String(pct));

  if (companyEl) {
    if (company && status === "fetching") companyEl.textContent = `Fetching: ${company}`;
    else if (company && status === "done") companyEl.textContent = `Completed: ${company}`;
    else if (status === "saving") companyEl.textContent = "Saving to database…";
    else if (cancelled) companyEl.textContent = "Stopped — progress saved for completed companies.";
    else if (running) companyEl.textContent = safeTotal > 0 ? "Waiting for next company…" : "";
    else companyEl.textContent = "";
  }
}

function showPanel({ title, subtitle }) {
  const backdrop = $("adminFetchBackdrop");
  if (!backdrop) return;
  backdrop.classList.add("open");
  backdrop.setAttribute("aria-hidden", "false");
  document.body.classList.add("fetch-modal-open");
  $("adminFetchTitle").textContent = title || "Fetching companies";
  $("adminFetchSubtitle").textContent = subtitle || "Starting…";
  hideFetchCompletion();
  appendLog("Starting…\n");
  const log = $("adminFetchLog");
  if (log) log.hidden = true;
  const activity = $("adminFetchActivity");
  if (activity) activity.hidden = false;
  const cancelBtn = $("adminFetchCancelBtn");
  if (cancelBtn) {
    cancelBtn.hidden = false;
    cancelBtn.disabled = false;
    cancelBtn.textContent = "Cancel";
  }
}

function hidePanel() {
  const backdrop = $("adminFetchBackdrop");
  if (!backdrop) return;
  backdrop.classList.remove("open");
  backdrop.setAttribute("aria-hidden", "true");
  document.body.classList.remove("fetch-modal-open");
}

function finishPanel({ title, subtitle, cancelled = false, fetchRun = null, fetchStatus = null }) {
  $("adminFetchTitle").textContent = title;
  $("adminFetchSubtitle").textContent = subtitle;
  updateFetchRunMeta(fetchStatus, { running: false, fetchRun });
  const log = $("adminFetchLog");
  if (log) log.hidden = false;
  const cancelBtn = $("adminFetchCancelBtn");
  if (cancelBtn) cancelBtn.hidden = true;
}

function applyFetchStatus(st) {
  appendLog((st.log || []).join("\n") || "(waiting…)");
  updateActivity(st);
  if (st.running) {
    updateFetchRunMeta(st, { running: true });
  }

  const progress = st.progress || {};
  const current = progress.current || 0;
  const total = progress.total || 0;
  const company = progress.company || null;
  const progressStatus = progress.status || "";

  if (st.running) {
    $("adminFetchTitle").textContent = st.ats_type
      ? `Fetching ${st.ats_type} companies`
      : "Fetching companies";
    $("adminFetchSubtitle").textContent = st.country || "In progress";
    updateProgress({
      current,
      total,
      company,
      status: progressStatus,
      running: true,
      cancelled: st.cancel_requested,
      newJobsTotal: st.new_jobs_total,
    });
    if (st.cancel_requested) {
      $("adminFetchCancelBtn").disabled = true;
      $("adminFetchCancelBtn").textContent = "Cancelling…";
    }
    return { done: false };
  }

  const cancelled = st.cancelled || st.exit_code === 130;
  const failed = !cancelled && st.exit_code != null && st.exit_code !== 0;
  updateProgress({
    current: total > 0 ? total : current,
    total,
    company: null,
    running: false,
    cancelled,
    newJobsTotal: st.new_jobs_total,
  });

  finishPanel({
    title: cancelled ? "Fetch cancelled" : (failed ? "Fetch finished with errors" : "Fetch complete"),
    subtitle: st.result_line || "Catalog updated",
    cancelled,
    fetchRun: st.last_fetch_run || null,
    fetchStatus: st,
  });
  return { done: true, st };
}

function pollFetchStatus() {
  if (pollTimer) clearInterval(pollTimer);

  async function tick() {
    const st = await getFetchStatus();
    if (st.company && st.running) return;
    const result = applyFetchStatus(st);
    if (!result.done) return;

    clearInterval(pollTimer);
    pollTimer = null;
    fetchBusy = false;

    if (typeof window.adminReloadDashboard === "function") {
      await window.adminReloadDashboard();
    }
  }

  tick();
  pollTimer = setInterval(tick, 800);
}

async function cancelCountryFetch() {
  if (!fetchBusy) {
    const st = await getFetchStatus();
    if (!st?.running) return;
    fetchBusy = true;
  }
  $("adminFetchCancelBtn").disabled = true;
  $("adminFetchCancelBtn").textContent = "Cancelling…";
  const ok = await cancelFetchRequest();
  if (!ok) {
    $("adminFetchCancelBtn").disabled = false;
    $("adminFetchCancelBtn").textContent = "Cancel";
    return;
  }
  pollFetchStatus();
}

function formatRunSummary(run) {
  if (!run) return "—";
  const country = escapeHtml(run.country || "?");
  const newJobs = Number(run.new_jobs) || 0;
  const when = formatActivityBadge(run.finished_at || run.started_at || "");
  return `${country} · ${newJobs} new · ${when}`;
}

export function renderWorkerStatus(worker) {
  const mount = $("adminWorkerSection");
  if (!mount || !worker) return;

  const fetch = worker.fetch || {};
  const lastRun = worker.last_country_run;
  const running = Boolean(fetch.running);
  const statusLabel = running
    ? `Running — ${escapeHtml(fetch.country || "?")}${fetch.ats_type ? ` · ${escapeHtml(fetch.ats_type)}` : ""}`
    : "Idle";
  const scheduleOn = worker.schedule_enabled !== false;
  const interval = worker.schedule_interval_hours ?? 6;
  const concurrency = worker.schedule_concurrency ?? 4;
  const countries = (worker.schedule_countries || "").trim()
    || "all supported countries";
  const panelScrape = worker.panel_scrape_enabled;
  const panelCompanyFetch = worker.panel_company_fetch_enabled;

  mount.innerHTML = `
    <section class="admin-panel admin-fetch-panel">
      <h2 class="admin-panel-title">Fetch worker</h2>
      <p class="hint admin-fetch-hint">
        Country scrapes run on the <code>relocation-fetch-worker</code> container
        ${scheduleOn ? `every ${interval}h` : "when enabled"} (concurrency ${concurrency}).
        ${panelScrape
          ? "This host can also start manual country fetches."
          : "Manual country fetch is disabled on this panel host."}
        ${panelCompanyFetch
          ? " Single-company fetch is enabled."
          : " Single-company fetch is disabled."}
      </p>
      <div class="stats-grid admin-stats-grid admin-worker-grid">
        <div class="stat-card ${running ? "stat-card--accent" : ""}">
          <div class="value">${statusLabel}</div>
          <div class="label">Current fetch</div>
        </div>
        <div class="stat-card">
          <div class="value">${formatRunSummary(lastRun)}</div>
          <div class="label">Last country fetch</div>
        </div>
        <div class="stat-card stat-card--muted">
          <div class="value">${escapeHtml(countries)}</div>
          <div class="label">Scheduled countries</div>
        </div>
      </div>
      ${running ? `<p class="hint"><button type="button" class="link-btn" id="adminWorkerViewProgress">View live progress</button></p>` : ""}
    </section>
  `;

  $("adminWorkerViewProgress")?.addEventListener("click", () => {
    fetchBusy = true;
    showPanel({
      title: fetch.ats_type ? `Fetching ${fetch.ats_type} companies` : "Fetching companies",
      subtitle: fetch.country || "In progress",
    });
    pollFetchStatus();
  });
}

export async function initAdminWorker(worker) {
  renderWorkerStatus(worker);

  if (!workerListenersBound) {
    workerListenersBound = true;
    $("adminFetchCancelBtn")?.addEventListener("click", cancelCountryFetch);
    $("adminFetchCloseBtn")?.addEventListener("click", hidePanel);
    $("adminFetchBackdrop")?.addEventListener("click", (e) => {
      if (e.target === $("adminFetchBackdrop") && !fetchBusy) hidePanel();
    });
  }

  const fetch = worker?.fetch || {};
  if (fetch.running && !fetch.company) {
    fetchBusy = true;
    showPanel({
      title: fetch.ats_type ? `Fetching ${fetch.ats_type} companies` : "Fetching companies",
      subtitle: fetch.country || "In progress",
    });
    pollFetchStatus();
  } else {
    try {
      const st = await getFetchStatus();
      if (st.running && !st.company) {
        fetchBusy = true;
        showPanel({
          title: st.ats_type ? `Fetching ${st.ats_type} companies` : "Fetching companies",
          subtitle: st.country || "In progress",
        });
        pollFetchStatus();
      }
    } catch {
      /* ignore */
    }
  }
}
