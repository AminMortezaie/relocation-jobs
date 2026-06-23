/** Country-wide fetch controls for the admin panel. */

import {
  cancelFetchRequest,
  fetchAtsTypes,
  fetchConfig,
  fetchCountries,
  getFetchStatus,
  startFetchRequest,
} from "./api.js";
import { $, escapeHtml, formatActivityBadge, formatFetchDuration, parseFetchTimestamp, elapsedSecondsBetween, elapsedSecondsSince } from "./utils.js";

let pollTimer = null;
let fetchBusy = false;
let scrapeConfig = { default_concurrency: 16, max_concurrency: 64, scrape_enabled: true };

function toast(message) {
  const el = $("adminFetchToast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => el.classList.remove("show"), 3200);
}

function countryLabel(countryId) {
  const sel = $("adminFetchCountry");
  if (!sel) return countryId || "";
  const opt = [...sel.options].find((o) => o.value === countryId);
  return opt?.textContent?.trim() || countryId || "";
}

function atsLabel(atsId) {
  if (!atsId || atsId === "all") return "";
  const sel = $("adminFetchAts");
  if (!sel) return atsId;
  const opt = [...sel.options].find((o) => o.value === atsId);
  return opt?.textContent?.trim() || atsId;
}

function fetchScopeSubtitle(country, atsType, concurrency) {
  const parts = [countryLabel(country)];
  const ats = atsLabel(atsType);
  if (ats) parts.push(ats);
  if (concurrency) parts.push(`${concurrency} parallel workers`);
  return parts.join(" · ");
}

function setFetchBusy(busy) {
  fetchBusy = busy;
  const startBtn = $("adminFetchStartBtn");
  if (startBtn) startBtn.disabled = busy || scrapeConfig.scrape_enabled === false;
}

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

  const newJobs = Math.max(
    0,
    Number(fetchRun?.new_jobs ?? st?.new_jobs_total) || 0,
  );
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
  $("adminFetchCancelBtn").hidden = false;
  $("adminFetchCancelBtn").disabled = false;
  $("adminFetchCancelBtn").textContent = "Cancel";
}

function hidePanel() {
  const backdrop = $("adminFetchBackdrop");
  if (!backdrop) return;
  backdrop.classList.remove("open");
  backdrop.setAttribute("aria-hidden", "true");
  document.body.classList.remove("fetch-modal-open");
}

function finishPanel({ title, subtitle, cancelled = false, failed = false, fetchRun = null, fetchStatus = null }) {
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
    const n = st.concurrency || $("adminFetchConcurrency")?.value || scrapeConfig.default_concurrency;
    $("adminFetchTitle").textContent = st.ats_type
      ? `Fetching ${atsLabel(st.ats_type)} companies`
      : "Fetching companies";
    $("adminFetchSubtitle").textContent = fetchScopeSubtitle(st.country, st.ats_type, n);
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

  const newJobsTotal = Math.max(0, Number(st.new_jobs_total) || 0);
  const newJobsNote = newJobsTotal > 0
    ? `${newJobsTotal} new role${newJobsTotal === 1 ? "" : "s"} from this fetch`
    : "";
  const resultSubtitle = st.result_line
    ? st.result_line.replace(/^\[\d+\/\d+\]\s*/, "").replace(/^Done\s+/, "")
    : "Catalog updated";

  finishPanel({
    title: cancelled ? "Fetch cancelled" : (failed ? "Fetch finished with errors" : "Fetch complete"),
    subtitle: cancelled
      ? (newJobsNote ? `${newJobsNote} · completed companies were saved.` : "Completed companies were saved.")
      : (newJobsNote || resultSubtitle),
    cancelled,
    failed,
    fetchRun: st.last_fetch_run || null,
    fetchStatus: st,
  });
  return { done: true, st };
}

function pollFetchStatus() {
  if (pollTimer) clearInterval(pollTimer);

  async function tick() {
    const st = await getFetchStatus();
    // Ignore per-company fetches from the job panel — admin modal is country-scoped only.
    if (st.company && st.running) return;
    const result = applyFetchStatus(st);
    if (!result.done) return;

    clearInterval(pollTimer);
    pollTimer = null;
    setFetchBusy(false);

    const doneSt = result.st;
    const cancelled = doneSt.cancelled || doneSt.exit_code === 130;
    if (cancelled) toast("Fetch cancelled — progress saved");
    else if (doneSt.exit_code === 0) toast(doneSt.result_line || "Fetch complete");
    else toast(doneSt.result_line || "Fetch failed — see log");

    if (typeof window.adminReloadDashboard === "function") {
      await window.adminReloadDashboard();
    }
  }

  tick();
  pollTimer = setInterval(tick, 800);
}

async function startCountryFetch() {
  const country = $("adminFetchCountry")?.value;
  const atsType = $("adminFetchAts")?.value || "all";
  if (!country) {
    toast("Select a country.");
    return;
  }
  if (fetchBusy) {
    toast("A fetch is already running.");
    return;
  }
  if (scrapeConfig.scrape_enabled === false) {
    toast("Scraping is disabled on this host.");
    return;
  }

  setFetchBusy(true);
  showPanel({
    title: atsType !== "all" ? `Fetching ${atsLabel(atsType)} companies` : "Fetching companies",
    subtitle: fetchScopeSubtitle(country, atsType),
  });

  try {
    const concurrency = Math.max(
      1,
      Math.min(
        parseInt($("adminFetchConcurrency")?.value, 10) || scrapeConfig.default_concurrency,
        scrapeConfig.max_concurrency || 64,
      ),
    );
    localStorage.setItem("panel_concurrency", String(concurrency));
    if (atsType !== "all") {
      localStorage.setItem("panel_ats", atsType);
    }
    $("adminFetchSubtitle").textContent = fetchScopeSubtitle(country, atsType, concurrency);

    const data = await startFetchRequest({
      country,
      ats_type: atsType !== "all" ? atsType : undefined,
      skip_filled: Boolean($("adminFetchSkipFilled")?.checked),
      concurrency,
    });
    if (!data) {
      setFetchBusy(false);
      finishPanel({ title: "Fetch failed", subtitle: "Could not start fetch.", failed: true });
      return;
    }
    pollFetchStatus();
  } catch {
    toast("Network error");
    setFetchBusy(false);
    finishPanel({ title: "Fetch failed", subtitle: "Network error.", failed: true });
  }
}

async function cancelCountryFetch() {
  if (!fetchBusy) return;
  $("adminFetchCancelBtn").disabled = true;
  $("adminFetchCancelBtn").textContent = "Cancelling…";
  const res = await cancelFetchRequest();
  if (!res) {
    $("adminFetchCancelBtn").disabled = false;
    $("adminFetchCancelBtn").textContent = "Cancel";
  }
}

export async function initAdminFetch() {
  scrapeConfig = await fetchConfig();
  const [countries, atsTypes] = await Promise.all([fetchCountries(), fetchAtsTypes()]);
  const countrySel = $("adminFetchCountry");
  if (countrySel) {
    countrySel.innerHTML = countries
      .filter((c) => c.id !== "all")
      .map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.label)}</option>`)
      .join("");
    const saved = localStorage.getItem("panel_country");
    if (saved && saved !== "all") countrySel.value = saved;
  }

  const atsSel = $("adminFetchAts");
  if (atsSel) {
    atsSel.innerHTML = [
      `<option value="all">All ATS in country</option>`,
      `<option value="generic">Generic / unknown</option>`,
      ...atsTypes.map((t) =>
        `<option value="${escapeHtml(t.id)}">${escapeHtml(t.label)}</option>`
      ),
    ].join("");
    const savedAts = localStorage.getItem("panel_ats");
    if (savedAts) atsSel.value = savedAts;
  }

  const concurrencyInput = $("adminFetchConcurrency");
  if (concurrencyInput) {
    concurrencyInput.max = scrapeConfig.max_concurrency || 64;
    const saved = localStorage.getItem("panel_concurrency");
    concurrencyInput.value = saved || scrapeConfig.default_concurrency || 16;
  }

  const disabled = scrapeConfig.scrape_enabled === false;
  const hint = $("adminFetchDisabledHint");
  if (hint) hint.hidden = !disabled;
  if ($("adminFetchStartBtn")) $("adminFetchStartBtn").disabled = disabled;

  $("adminFetchStartBtn")?.addEventListener("click", startCountryFetch);
  $("adminFetchCancelBtn")?.addEventListener("click", cancelCountryFetch);
  $("adminFetchCloseBtn")?.addEventListener("click", hidePanel);
  $("adminFetchBackdrop")?.addEventListener("click", (e) => {
    if (e.target === $("adminFetchBackdrop") && !fetchBusy) hidePanel();
  });

  const st = await getFetchStatus();
  if (st.running && !st.company) {
    setFetchBusy(true);
    showPanel({
      title: st.ats_type ? `Fetching ${atsLabel(st.ats_type)} companies` : "Fetching companies",
      subtitle: fetchScopeSubtitle(st.country, st.ats_type),
    });
    pollFetchStatus();
  }
}

export function isAdminFetchBusy() {
  return fetchBusy;
}
