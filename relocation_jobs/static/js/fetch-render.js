/** Fetch panel render helpers — update fetchPanelState for React. */

import { state, findCompany } from "./state.js";
import {
  formatActivityBadge,
  formatFetchDuration,
  elapsedSecondsBetween,
  elapsedSecondsSince,
} from "./utils.js";
import { fetchPanelState, publishFetchUi } from "./fetch-ui.js";

const JUNK_REVIEW_TITLE = /^(show\s+\d+\s+more|load\s+more|view\s+all(\s+jobs)?|see\s+all(\s+jobs)?)$/i;
const JUNK_REVIEW_URL = /\/jobs\/show_more\b/i;
const FETCH_REVIEW_LIST_PREVIEW = 10;

function isJunkReviewJob(title, url) {
  const t = (title || "").trim();
  const u = (url || "").trim();
  return JUNK_REVIEW_URL.test(u) || JUNK_REVIEW_TITLE.test(t);
}

export function normalizeReviewJobs(jobs) {
  const seen = new Set();
  const out = [];
  for (const job of jobs || []) {
    const url = String(job?.url || "").trim();
    if (!url || seen.has(url)) continue;
    const title = String(job?.title || "").trim();
    if (isJunkReviewJob(title, url)) continue;
    seen.add(url);
    out.push({
      title: title || url,
      url,
      filter_reason: String(job?.filter_reason || "").trim(),
    });
  }
  return out;
}

function reviewExpandMeta(filtered, expanded) {
  const showAll = expanded || filtered.length <= FETCH_REVIEW_LIST_PREVIEW;
  const visibleCount = showAll ? filtered.length : Math.min(FETCH_REVIEW_LIST_PREVIEW, filtered.length);
  const hiddenCount = Math.max(0, filtered.length - visibleCount);
  if (hiddenCount > 0) {
    return { expandHidden: false, expandLabel: `Show ${hiddenCount} more` };
  }
  if (showAll && filtered.length > FETCH_REVIEW_LIST_PREVIEW) {
    return { expandHidden: false, expandLabel: "Show less" };
  }
  return { expandHidden: true, expandLabel: "" };
}

export function clearFetchReviewContent() {
  fetchPanelState.review = {
    visible: false,
    hint: "",
    included: [],
    filtered: [],
    filteredExpanded: false,
    country: "",
    company: "",
    missingReview: false,
    addBtnVisible: false,
    expandHidden: true,
    expandLabel: "",
  };
  fetchPanelState.log.hidden = false;
  publishFetchUi();
}

export function hideFetchReviewFooter() {
  fetchPanelState.footer = {
    hidden: true,
    pending: false,
    resolved: false,
    resolvedStatus: null,
    prompt: "Did the fetch work correctly?",
    country: "",
    company: "",
    okDisabled: false,
    problemDisabled: false,
  };
  publishFetchUi();
}

export function clearFetchReview() {
  clearFetchReviewContent();
  hideFetchReviewFooter();
  resetFetchReviewFeedbackPrompt();
  state.fetchReviewFeedback = null;
}

export function setFetchReviewFeedbackDone(status) {
  fetchPanelState.footer.pending = false;
  fetchPanelState.footer.resolved = true;
  fetchPanelState.footer.resolvedStatus = status;
  publishFetchUi();
}

function resetFetchReviewFeedbackPrompt(prompt = "Did the fetch work correctly?") {
  fetchPanelState.footer.pending = false;
  fetchPanelState.footer.resolved = false;
  fetchPanelState.footer.resolvedStatus = null;
  fetchPanelState.footer.prompt = prompt;
  fetchPanelState.footer.okDisabled = false;
  fetchPanelState.footer.problemDisabled = false;
  publishFetchUi();
}

function applyStoredFetchReviewFeedback(country, company) {
  const saved = state.fetchReviewFeedback;
  if (saved?.country === country && saved?.company === company && saved?.status) {
    setFetchReviewFeedbackDone(saved.status);
    return true;
  }
  return false;
}

export function setFetchReviewFooterPending({ country, company, prompt = "Fetch in progress…" } = {}) {
  fetchPanelState.footer = {
    hidden: false,
    pending: true,
    resolved: false,
    resolvedStatus: null,
    prompt,
    country: country || "",
    company: company || "",
    okDisabled: false,
    problemDisabled: false,
  };
  publishFetchUi();
}

function updateFetchReviewFooter({ country, company, showFeedback = false, prompt } = {}) {
  if (!showFeedback) {
    hideFetchReviewFooter();
    return;
  }
  fetchPanelState.footer.hidden = false;
  fetchPanelState.footer.pending = false;
  fetchPanelState.footer.country = country || "";
  fetchPanelState.footer.company = company || "";
  if (!applyStoredFetchReviewFeedback(country, company)) {
    resetFetchReviewFeedbackPrompt(prompt);
  }
}

export function showFetchReviewFeedback({ country, company, failed = false } = {}) {
  if (!country || !company) {
    clearFetchReview();
    return;
  }
  fetchPanelState.review.visible = true;
  fetchPanelState.log.hidden = true;
  fetchPanelState.activity.hidden = true;
  fetchPanelState.review.addBtnVisible = false;
  updateFetchReviewFooter({
    country,
    company,
    showFeedback: true,
    prompt: failed
      ? "Fetch finished with errors. Did it load roles correctly?"
      : "Did the fetch work correctly?",
  });
  publishFetchUi();
}

export function renderFetchReview(review, { country, company, missingReview = false } = {}) {
  if (!country || !company) {
    clearFetchReview();
    return;
  }

  const included = normalizeReviewJobs(review?.included);
  const filtered = normalizeReviewJobs(review?.filtered);
  const expand = reviewExpandMeta(filtered, fetchPanelState.review.filteredExpanded);

  fetchPanelState.review.visible = true;
  fetchPanelState.log.hidden = true;
  fetchPanelState.activity.hidden = true;
  fetchPanelState.review.country = country;
  fetchPanelState.review.company = company;
  fetchPanelState.review.missingReview = missingReview;
  fetchPanelState.review.included = included;

  if (missingReview) {
    fetchPanelState.review.hint = "Role review is unavailable. Restart the panel server, then fetch again.";
    fetchPanelState.review.filtered = [];
    fetchPanelState.review.addBtnVisible = false;
    Object.assign(fetchPanelState.review, expand);
    updateFetchReviewFooter({ country, company, showFeedback: true });
    publishFetchUi();
    return;
  }

  if (!included.length && !filtered.length) {
    const co = findCompany(country, company);
    const ats = (co?.ats_type || "").trim();
    fetchPanelState.review.hint = ats && ats !== "generic"
      ? `No matching roles found using the ${ats} board. The page may be empty or your filters are strict.`
      : "No roles could be loaded. The ATS is likely misdetected (not generic) — use Edit URL or mark a fetch problem.";
    fetchPanelState.review.filtered = [];
    fetchPanelState.review.addBtnVisible = false;
    Object.assign(fetchPanelState.review, expand);
    updateFetchReviewFooter({ country, company, showFeedback: true });
    publishFetchUi();
    return;
  }

  fetchPanelState.review.hint = filtered.length
    ? "These roles were on the careers page but did not match your filters. Each line shows why. Select any to add manually."
    : "All roles on the careers page matched your filters.";
  fetchPanelState.review.filtered = filtered;
  fetchPanelState.review.addBtnVisible = filtered.length > 0;
  Object.assign(fetchPanelState.review, expand);
  updateFetchReviewFooter({ country, company, showFeedback: true });
  publishFetchUi();
}

export function toggleFetchReviewFilteredExpanded() {
  const filtered = fetchPanelState.review.filtered || [];
  if (!filtered.length) return;
  fetchPanelState.review.filteredExpanded = !fetchPanelState.review.filteredExpanded;
  Object.assign(fetchPanelState.review, reviewExpandMeta(filtered, fetchPanelState.review.filteredExpanded));
  publishFetchUi();
}

export function setFetchLogMode(singleCompany) {
  fetchPanelState.log.active = Boolean(singleCompany);
  publishFetchUi();
}

export function showFetchPanel({
  title,
  subtitle,
  singleCompany = false,
  country = null,
  company = null,
  reopen = false,
} = {}) {
  openFetchPanel();

  if (reopen) {
    state.fetchPanelSingle = Boolean(singleCompany);
    fetchPanelState.cancelHidden = false;
    fetchPanelState.cancelDisabled = false;
    fetchPanelState.cancelText = "Cancel";
    fetchPanelState.closeHidden = false;
    publishFetchUi();
    return;
  }

  state.fetchPanelSingle = Boolean(singleCompany);
  clearFetchReviewContent();
  hideFetchReviewFooter();
  state.fetchReviewFeedback = null;
  fetchPanelState.title = title || "Fetching companies";
  fetchPanelState.subtitle = subtitle || "Starting…";
  fetchPanelState.singleCompany = singleCompany;
  fetchPanelState.log.hidden = singleCompany;
  fetchPanelState.log.text = singleCompany ? "Waiting for scrape to start…\n" : "Starting…\n";
  fetchPanelState.activity.hidden = !singleCompany;
  fetchPanelState.activity.step = "Starting…";
  fetchPanelState.activity.detail = "";
  fetchPanelState.activity.items = [];
  fetchPanelState.cancelHidden = false;
  fetchPanelState.cancelDisabled = false;
  fetchPanelState.cancelText = "Cancel";
  fetchPanelState.cancelTitle = singleCompany
    ? "Stop this fetch immediately"
    : "Stop fetching remaining companies";
  fetchPanelState.closeHidden = false;
  setFetchLogMode(singleCompany);

  if (singleCompany) {
    fetchPanelState.progressWrapHidden = true;
    if (country && company) setFetchReviewFooterPending({ country, company });
  } else {
    fetchPanelState.progressWrapHidden = false;
    updateFetchProgress({ current: 0, total: 0, company: null, running: true });
  }
  publishFetchUi();
}

export function openFetchPanel() {
  fetchPanelState.open = true;
  publishFetchUi();
}

export function hideFetchPanel() {
  fetchPanelState.open = false;
  clearFetchReview();
  publishFetchUi();
}

export function updateFetchProgress({
  current = 0,
  total = 0,
  company = null,
  status = "",
  running = false,
  cancelled = false,
  newJobsTotal = 0,
}) {
  fetchPanelState.progressWrapHidden = false;
  const safeTotal = Math.max(0, total || 0);
  const safeCurrent = Math.max(0, current || 0);
  const displayCurrent = running && status === "fetching" && safeTotal > 1 && safeCurrent < safeTotal
    ? safeCurrent + 1
    : safeCurrent;
  const pct = safeTotal > 0
    ? (running && status !== "done"
      ? Math.min(99, Math.round((displayCurrent / safeTotal) * 100))
      : Math.min(100, Math.round((displayCurrent / safeTotal) * 100)))
    : (running ? 0 : (cancelled ? safeCurrent : 100));
  const newJobs = Math.max(0, Number(newJobsTotal) || 0);
  const newJobsSuffix = newJobs > 0 ? ` · ${newJobs} new` : "";
  let companyLine = "";
  if (company && status === "fetching") companyLine = `Fetching: ${company}`;
  else if (company && status === "done") companyLine = `Completed: ${company}`;
  else if (status === "saving") companyLine = "Saving to database…";
  else if (company) companyLine = company;
  else if (running) companyLine = safeTotal > 0 ? "Waiting for next company…" : "";
  else if (cancelled) companyLine = "Stopped — progress saved for completed companies.";

  fetchPanelState.progress = {
    current: safeCurrent,
    total: safeTotal,
    pct,
    label: safeTotal > 0
      ? `${safeCurrent} / ${safeTotal} companies${newJobsSuffix}`
      : (running ? "Preparing…" : (newJobs > 0 ? `${newJobs} new roles` : "Done")),
    companyLine,
  };
  publishFetchUi();
}

export function setFetchPanelRunning(running) {
  fetchPanelState.cancelHidden = !running;
  if (!running) {
    fetchPanelState.cancelDisabled = false;
    fetchPanelState.cancelText = "Cancel";
  }
  publishFetchUi();
}

export function hideFetchCompletion() {
  fetchPanelState.completion.hidden = true;
  publishFetchUi();
}

export function updateFetchRunMeta(st, { running = false, fetchRun = null } = {}) {
  const startedAt = fetchRun?.started_at || st?.started_at || "";
  if (!startedAt && !fetchRun) {
    hideFetchCompletion();
    return;
  }

  fetchPanelState.completion.hidden = false;
  fetchPanelState.completion.label = running ? "Current run" : "Last run";
  fetchPanelState.completion.started = formatActivityBadge(startedAt);
  const newJobs = Math.max(0, Number(fetchRun?.new_jobs ?? st?.new_jobs_total) || 0);
  fetchPanelState.completion.newJobs = newJobs === 1 ? "1 role" : `${newJobs} roles`;

  if (running) {
    fetchPanelState.completion.finished = "In progress…";
    const elapsed = elapsedSecondsSince(startedAt);
    fetchPanelState.completion.duration = elapsed != null ? formatFetchDuration(elapsed) : "—";
    publishFetchUi();
    return;
  }

  const finishedAt = fetchRun?.finished_at || st?.finished_at || "";
  fetchPanelState.completion.finished = finishedAt ? formatActivityBadge(finishedAt) : "—";
  const duration = fetchRun?.duration_seconds
    ?? elapsedSecondsBetween(startedAt, finishedAt)
    ?? null;
  fetchPanelState.completion.duration = duration != null ? formatFetchDuration(duration) : "—";
  publishFetchUi();
}

export function showFetchCompletion(run) {
  updateFetchRunMeta(null, { running: false, fetchRun: run });
}

export function finishFetchPanel({
  title,
  subtitle,
  cancelled = false,
  failed = false,
  singleCompany = false,
  fetchRun = null,
  fetchStatus = null,
}) {
  fetchPanelState.title = title || (cancelled ? "Fetch cancelled" : "Fetch complete");
  fetchPanelState.subtitle = failed && !cancelled ? (subtitle || "Check the log for details.") : (subtitle || "");
  updateFetchRunMeta(fetchStatus, { running: false, fetchRun });
  setFetchPanelRunning(false);
  state.fetchPanelSingle = false;
  setFetchLogMode(false);
  fetchPanelState.progressWrapHidden = singleCompany;
  if (cancelled) {
    fetchPanelState.progress.companyLine = "Stopped — progress saved for completed companies.";
  }
  publishFetchUi();
}

export function appendFetchLog(lines) {
  fetchPanelState.log.text = lines;
  publishFetchUi();
}

export function updateFetchActivity(st) {
  if (!st?.running) {
    fetchPanelState.activity.hidden = true;
    publishFetchUi();
    return;
  }

  const current = st.activity || {};
  const history = Array.isArray(st.activity_log) ? st.activity_log : [];
  const message = (current.message || "").trim() || "Working…";
  const detail = (current.detail || "").trim();
  const items = (history.length ? history : [{ message, detail }]).slice(-6).map((entry) => ({
    message: (entry.message || "").trim(),
    detail: (entry.detail || "").trim(),
  }));

  fetchPanelState.activity = {
    hidden: false,
    step: message,
    detail,
    items,
  };
  publishFetchUi();
}

export function showFetchNotice({ title, subtitle } = {}) {
  fetchPanelState.open = true;
  fetchPanelState.title = title || "Fetch";
  fetchPanelState.subtitle = subtitle || "";
  fetchPanelState.cancelHidden = true;
  fetchPanelState.cancelDisabled = false;
  fetchPanelState.cancelText = "Cancel";
  fetchPanelState.closeHidden = false;
  fetchPanelState.progressWrapHidden = true;
  fetchPanelState.activity.hidden = true;
  fetchPanelState.log.hidden = true;
  fetchPanelState.review.visible = false;
  fetchPanelState.footer.hidden = true;
  fetchPanelState.completion.hidden = true;
  publishFetchUi();
}

export function updateFetchHeaderUI() {
  publishFetchUi();
}

export function setFetchCancelPending(pending) {
  fetchPanelState.cancelDisabled = Boolean(pending);
  fetchPanelState.cancelText = pending ? "Cancelling…" : "Cancel";
  publishFetchUi();
}

export function patchRunningFetchPanel({
  title,
  subtitle,
  singleCompany,
  progressWrapHidden,
  activityHidden,
  logHidden,
  cancelRequested,
} = {}) {
  if (title != null) fetchPanelState.title = title;
  if (subtitle != null) fetchPanelState.subtitle = subtitle;
  if (singleCompany != null) fetchPanelState.singleCompany = singleCompany;
  if (progressWrapHidden != null) fetchPanelState.progressWrapHidden = progressWrapHidden;
  if (activityHidden != null) fetchPanelState.activity.hidden = activityHidden;
  if (logHidden != null) fetchPanelState.log.hidden = logHidden;
  if (cancelRequested) setFetchCancelPending(true);
  else publishFetchUi();
}
