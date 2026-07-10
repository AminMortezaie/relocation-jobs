/** Company workspace — per-position tailored CV / cover letter + PDF preview. */

import { companyWorkspacePath } from "./company-workspace.js";
import { beginScreenLoad, endScreenLoad, setScreenLoadProgress } from "./screen-loader.js";
import { $, escapeHtml, finishLoadingProgress, setLoadingProgress } from "./utils.js";

let routeCountry = "";
let routeSlug = "";
let companyName = "";
let positions = [];
let selectedKey = "";
let savedTexContent = "";
let texEditing = false;
let artifactMode = "cv";

function isCoverLetter() {
  return artifactMode === "cover-letter";
}

function artifactApiBase(idempotencyKey) {
  const root = `/api/mcp/applications/${encodeURIComponent(idempotencyKey)}`;
  return isCoverLetter() ? `${root}/cover-letter` : root;
}

function artifactHasTex(position) {
  return isCoverLetter()
    ? Boolean(position.has_cover_letter_tex)
    : Boolean(position.has_tailored_tex);
}

function artifactHasPdf(position) {
  return isCoverLetter()
    ? Boolean(position.has_cover_letter_pdf)
    : Boolean(position.has_pdf);
}

function artifactPdfFilename(position) {
  if (isCoverLetter()) {
    return position.cover_letter_pdf_filename || "cover_letter.pdf";
  }
  return position.pdf_filename || "resume.pdf";
}

function emptyTexMessage() {
  return isCoverLetter()
    ? "No cover letter LaTeX for this position yet."
    : "No tailored LaTeX for this position yet.";
}

function emptyPdfMessage() {
  return isCoverLetter()
    ? "No cover letter PDF yet — save cover letter tex via MCP, then re-render."
    : "No PDF yet — save tailored tex via MCP, then re-render.";
}

function syncArtifactTabs() {
  const cv = $("companyArtifactCv");
  const cover = $("companyArtifactCover");
  if (cv) {
    cv.classList.toggle("company-artifact-tab--active", !isCoverLetter());
    cv.setAttribute("aria-selected", isCoverLetter() ? "false" : "true");
  }
  if (cover) {
    cover.classList.toggle("company-artifact-tab--active", isCoverLetter());
    cover.setAttribute("aria-selected", isCoverLetter() ? "true" : "false");
  }
  const texLabel = $("companyTexLabel");
  const pdfLabel = $("companyPdfLabel");
  if (texLabel) {
    texLabel.textContent = isCoverLetter() ? "Cover letter LaTeX" : "CV LaTeX source";
  }
  if (pdfLabel) {
    pdfLabel.textContent = isCoverLetter() ? "Cover letter PDF" : "CV PDF preview";
  }
  const pdfMissing = $("companyPdfMissing");
  if (pdfMissing) pdfMissing.textContent = emptyPdfMessage();
}

function parseRoute() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts[0] !== "company" || parts.length < 3) {
    throw new Error("Invalid company workspace URL");
  }
  routeCountry = decodeURIComponent(parts[1]).trim().toLowerCase();
  routeSlug = decodeURIComponent(parts.slice(2).join("/")).trim();
}

function showLogin() {
  const content = $("companyContent");
  if (content) content.hidden = true;
  $("companyLoginPanel").hidden = false;
}

function showApp() {
  $("companyLoginPanel").hidden = true;
  const content = $("companyContent");
  if (content) content.hidden = false;
}

function showError(message) {
  const el = $("companyError");
  if (!el) return;
  el.hidden = !message;
  el.textContent = message || "";
}

function showToast(message) {
  const toast = $("companyToast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const res = await fetch(path, { credentials: "same-origin", ...options });
  if (res.status === 401) {
    showLogin();
    throw new Error("Authentication required");
  }
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/pdf")) {
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    return res;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function positionBadges(position) {
  const badges = [];
  if (position.has_pdf) badges.push('<span class="company-position-badge company-position-badge--pdf">PDF</span>');
  else if (position.has_tailored_tex) badges.push('<span class="company-position-badge company-position-badge--tex">CV</span>');
  if (position.has_cover_letter_pdf) {
    badges.push('<span class="company-position-badge company-position-badge--cl-pdf">CL PDF</span>');
  } else if (position.has_cover_letter_tex) {
    badges.push('<span class="company-position-badge company-position-badge--cl-tex">CL</span>');
  }
  if (position.looking_to_apply) badges.push('<span class="company-position-badge company-position-badge--queue">Queue</span>');
  if (position.pinned) badges.push('<span class="company-position-badge company-position-badge--pin">Pinned</span>');
  return badges.join("");
}

function renderPositionList() {
  const list = $("companyPositionList");
  const hint = $("companyPositionsHint");
  if (!list) return;

  if (!positions.length) {
    list.innerHTML = `<li class="company-position-empty">No open positions in catalog.</li>`;
    if (hint) hint.textContent = "Fetch jobs from the panel if this company should have roles.";
    return;
  }

  const withCv = positions.filter((p) => p.has_tailored_tex || p.has_pdf).length;
  const withCl = positions.filter((p) => p.has_cover_letter_tex || p.has_cover_letter_pdf).length;
  if (hint) {
    const parts = [];
    if (withCv) parts.push(`${withCv} tailored CV`);
    if (withCl) parts.push(`${withCl} cover letter`);
    hint.textContent = parts.length
      ? `${parts.join(" · ")} across ${positions.length} roles.`
      : "No tailored CVs or cover letters yet — use Claude Desktop MCP after marking roles looking to apply.";
  }

  list.innerHTML = positions.map((position) => {
    const active = position.idempotency_key === selectedKey ? " company-position-item--active" : "";
    const meta = [position.location, position.master_resume_slug].filter(Boolean).join(" · ");
    return `
      <li>
        <button
          type="button"
          class="company-position-item${active}"
          data-key="${escapeHtml(position.idempotency_key)}"
        >
          <span class="company-position-item-title">${escapeHtml(position.title || "Untitled role")}</span>
          <span class="company-position-item-meta">${escapeHtml(meta)}</span>
          <span class="company-position-item-badges">${positionBadges(position)}</span>
        </button>
      </li>`;
  }).join("");
}

let jdVisible = false;
let jdLoaded = false;
let jdCache = { key: "", hasDescription: false, text: "", html: "", needsFetch: false };
let jdEditing = false;

function setJobDescriptionContent({ hasDescription = false, text = "", html = "" } = {}) {
  const view = $("companyJdView");
  const empty = $("companyJdEmpty");
  const fetchBtn = $("companyJdFetchBtn");
  const editor = $("companyJdEditor");
  if (!view || !empty) return;
  const content = (text || "").trim();
  const markup = (html || "").trim();
  if (editor) editor.hidden = true;
  if (hasDescription && (markup || content)) {
    if (markup) {
      view.innerHTML = markup;
    } else {
      view.textContent = content;
    }
    view.hidden = false;
    empty.hidden = true;
    if (fetchBtn) fetchBtn.disabled = false;
    return;
  }
  view.innerHTML = "";
  view.hidden = true;
  empty.hidden = false;
  if (fetchBtn) {
    fetchBtn.disabled = false;
    fetchBtn.textContent = "Fetch job description";
  }
}

function setJobDescriptionEditMode({ content = jdCache.text || "" } = {}) {
  jdEditing = true;
  const view = $("companyJdView");
  const empty = $("companyJdEmpty");
  const editor = $("companyJdEditor");
  const editBtn = $("companyJdEditBtn");
  const saveBtn = $("companyJdSaveBtn");
  const cancelBtn = $("companyJdCancelBtn");
  const fetchBtn = $("companyJdFetchBtn");
  if (view) view.hidden = true;
  if (empty) empty.hidden = true;
  if (editor) {
    editor.hidden = false;
    editor.value = content;
    editor.focus();
  }
  if (editBtn) editBtn.hidden = true;
  if (saveBtn) saveBtn.hidden = false;
  if (cancelBtn) cancelBtn.hidden = false;
  if (fetchBtn) fetchBtn.hidden = true;
}

function setJobDescriptionViewMode() {
  jdEditing = false;
  const editBtn = $("companyJdEditBtn");
  const saveBtn = $("companyJdSaveBtn");
  const cancelBtn = $("companyJdCancelBtn");
  const fetchBtn = $("companyJdFetchBtn");
  if (editBtn) {
    editBtn.hidden = false;
    editBtn.textContent = jdCache.hasDescription ? "Edit" : "Paste description";
  }
  if (saveBtn) saveBtn.hidden = true;
  if (cancelBtn) cancelBtn.hidden = true;
  if (fetchBtn) fetchBtn.hidden = false;
  setJobDescriptionContent(jdCache);
}

function applyJobDescriptionPayload(jd) {
  const text = (jd.description_text || "").trim();
  const html = (jd.description_html || "").trim();
  const hasDescription = Boolean(jd.has_description) && Boolean(text || html);
  jdCache = {
    key: selectedKey,
    hasDescription,
    text,
    html,
    needsFetch: !hasDescription,
  };
  jdLoaded = true;
  setJobDescriptionViewMode();
  const position = positions.find((p) => p.idempotency_key === selectedKey);
  if (position) {
    position.has_description = jdCache.hasDescription;
    renderPositionList();
    updateJdToggleButton(position);
  }
}

function updateJdToggleButton(position) {
  const btn = $("companyJdToggleBtn");
  if (!btn) return;
  if (!position) {
    btn.hidden = true;
    return;
  }
  btn.hidden = false;
  if (jdVisible) {
    btn.textContent = "Hide job description";
    btn.setAttribute("aria-expanded", "true");
    return;
  }
  btn.textContent = "Show job description";
  btn.setAttribute("aria-expanded", "false");
}

function resetJobDescription() {
  jdVisible = false;
  jdLoaded = false;
  jdEditing = false;
  jdCache = { key: "", hasDescription: false, text: "", html: "", needsFetch: false };
  const panel = $("companyJdPanel");
  const btn = $("companyJdToggleBtn");
  const editBtn = $("companyJdEditBtn");
  const saveBtn = $("companyJdSaveBtn");
  const cancelBtn = $("companyJdCancelBtn");
  const fetchBtn = $("companyJdFetchBtn");
  const editor = $("companyJdEditor");
  if (panel) panel.hidden = true;
  setJobDescriptionContent();
  if (editBtn) editBtn.hidden = true;
  if (saveBtn) saveBtn.hidden = true;
  if (cancelBtn) cancelBtn.hidden = true;
  if (fetchBtn) {
    fetchBtn.hidden = false;
    fetchBtn.disabled = false;
    fetchBtn.textContent = "Fetch job description";
  }
  if (editor) {
    editor.hidden = true;
    editor.value = "";
  }
  if (btn) {
    btn.hidden = true;
    btn.disabled = false;
    btn.textContent = "Show job description";
    btn.setAttribute("aria-expanded", "false");
  }
}

async function toggleJobDescription() {
  const position = positions.find((p) => p.idempotency_key === selectedKey);
  if (!position || !selectedKey) return;

  const btn = $("companyJdToggleBtn");
  const panel = $("companyJdPanel");
  if (!btn || !panel) return;

  if (jdVisible) {
    jdVisible = false;
    panel.hidden = true;
    updateJdToggleButton(position);
    return;
  }

  if (jdLoaded && jdCache.key === selectedKey) {
    jdVisible = true;
    panel.hidden = false;
    if (jdEditing) {
      setJobDescriptionEditMode();
    } else {
      setJobDescriptionViewMode();
    }
    updateJdToggleButton(position);
    return;
  }

  btn.disabled = true;
  try {
    const jd = await api(
      `/api/mcp/positions/${encodeURIComponent(selectedKey)}/description`,
    );
    jdVisible = true;
    panel.hidden = false;
    applyJobDescriptionPayload(jd);
  } catch (err) {
    if (err.message?.includes("(500)")) {
      jdVisible = true;
      panel.hidden = false;
      jdCache = { key: selectedKey, hasDescription: false, text: "", html: "", needsFetch: true };
      jdLoaded = true;
      setJobDescriptionViewMode();
      $("companyJdMissing").textContent = (
        "Job description is not available yet. Use Fetch job description below."
      );
    } else {
      showError(err.message || "Failed to load job description");
    }
  } finally {
    btn.disabled = false;
  }
}

async function fetchJobDescription() {
  if (!selectedKey) return;
  const fetchBtn = $("companyJdFetchBtn");
  const panel = $("companyJdPanel");
  if (!fetchBtn || !panel) return;

  fetchBtn.disabled = true;
  fetchBtn.textContent = "Fetching…";
  showError("");
  try {
    const jd = await api(
      `/api/mcp/positions/${encodeURIComponent(selectedKey)}/fetch-description`,
      { method: "POST" },
    );
    jdVisible = true;
    panel.hidden = false;
    applyJobDescriptionPayload(jd);
    if (jd.has_description) {
      showToast("Job description fetched");
    } else {
      $("companyJdMissing").textContent = (
        "Could not fetch a job description from the posting URL. Try re-fetching the company from the job panel."
      );
    }
  } catch (err) {
    showError(err.message || "Failed to fetch job description");
  } finally {
    fetchBtn.disabled = false;
    fetchBtn.textContent = "Fetch job description";
  }
}

function startJobDescriptionEdit() {
  setJobDescriptionEditMode();
}

function cancelJobDescriptionEdit() {
  setJobDescriptionViewMode();
}

async function persistJobDescription() {
  if (!selectedKey) {
    throw new Error("Select a position first");
  }
  const descriptionText = $("companyJdEditor")?.value ?? "";
  if (!descriptionText.trim()) {
    throw new Error("Job description cannot be empty");
  }
  return api(
    `/api/mcp/positions/${encodeURIComponent(selectedKey)}/description`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description_text: descriptionText }),
    },
  );
}

async function saveJobDescription() {
  const editBtn = $("companyJdEditBtn");
  const saveBtn = $("companyJdSaveBtn");
  const fetchBtn = $("companyJdFetchBtn");
  if (!saveBtn) return;
  saveBtn.disabled = true;
  if (editBtn) editBtn.disabled = true;
  if (fetchBtn) fetchBtn.disabled = true;
  showError("");
  try {
    const jd = await persistJobDescription();
    jdVisible = true;
    applyJobDescriptionPayload(jd);
    showToast("Job description saved");
  } catch (err) {
    showError(err.message || "Failed to save job description");
  } finally {
    saveBtn.disabled = false;
    if (editBtn) editBtn.disabled = false;
    if (fetchBtn) fetchBtn.disabled = false;
  }
}

function clearDetail() {
  selectedKey = "";
  savedTexContent = "";
  texEditing = false;
  artifactMode = "cv";
  syncArtifactTabs();
  const body = $("companyDetailBody");
  const empty = $("companyDetailEmpty");
  if (body) body.hidden = true;
  if (empty) empty.hidden = false;
  $("companyPdfFrame")?.removeAttribute("src");
  $("companyOpenPdf")?.setAttribute("hidden", "");
  $("companyApplyLink")?.setAttribute("hidden", "");
  $("companyApplyHint")?.setAttribute("hidden", "");
  const pdfMissing = $("companyPdfMissing");
  if (pdfMissing) pdfMissing.hidden = true;
  resetJobDescription();
  renderPositionList();
}

function setTexViewMode({ editing = false, content = savedTexContent } = {}) {
  texEditing = editing;
  savedTexContent = content;
  const view = $("companyTexView");
  const editor = $("companyTexEditor");
  const editBtn = $("companyTexEditBtn");
  const saveBtn = $("companyTexSaveBtn");
  const cancelBtn = $("companyTexCancelBtn");
  const hasTex = Boolean(content.trim());

  if (view) {
    view.textContent = content || emptyTexMessage();
    view.hidden = editing;
  }
  if (editor) {
    editor.value = content;
    editor.hidden = !editing;
  }
  if (editBtn) editBtn.hidden = !hasTex || editing;
  if (saveBtn) saveBtn.hidden = !editing;
  if (cancelBtn) cancelBtn.hidden = !editing;
}

function startTexEdit() {
  if (!savedTexContent.trim()) return;
  setTexViewMode({ editing: true });
  $("companyTexEditor")?.focus();
}

function cancelTexEdit() {
  setTexViewMode({ editing: false });
}

async function persistTex() {
  if (!selectedKey) {
    throw new Error("Select a position first");
  }
  const content = $("companyTexEditor")?.value ?? savedTexContent;
  if (!content.trim()) {
    throw new Error("LaTeX content cannot be empty");
  }
  const saved = await api(
    `${artifactApiBase(selectedKey)}/tex`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
  setTexViewMode({ editing: false, content });
  return saved;
}

async function saveTex() {
  const btn = $("companyTexSaveBtn");
  const editBtn = $("companyTexEditBtn");
  btn.disabled = true;
  if (editBtn) editBtn.disabled = true;
  showError("");
  try {
    await persistTex();
    showToast("LaTeX saved");
  } catch (err) {
    showError(err.message || "Failed to save LaTeX");
  } finally {
    btn.disabled = false;
    if (editBtn) editBtn.disabled = false;
  }
}

function positionCardVariant(position) {
  if (position.not_for_me) return "not_for_me";
  if (position.rejected) return "rejected";
  return "open";
}

function normalizePositionForCard(position) {
  // The tracking state (applied/looking/seen/rejected dates + history, referral,
  // pin) now comes through from the backend on `position`, so spread it as-is
  // for parity with the job board. Only override fields the company applications
  // endpoint doesn't supply or that are workspace-specific.
  return {
    ...position,
    country: routeCountry || "",
    company: companyName || "",
    visa_sponsorship: false,
    fetched: position.tailored_tex_updated_at || position.pdf_updated_at || position.cover_letter_tex_updated_at || position.cover_letter_pdf_updated_at || "",
    last_seen: "",
    job_city: position.location || "",
    not_for_me: false,
    not_for_me_date: "",
    not_for_me_reason: "",
  };
}

function renderPositionCard(position) {
  const container = $("companyPositionCardContainer");
  if (!container) return;
  let card = container.querySelector("position-card");
  if (!card) {
    card = document.createElement("position-card");
    container.appendChild(card);
  }
  const normalized = normalizePositionForCard(position);
  card.job = normalized;
  card.variant = positionCardVariant(normalized);
}

async function loadPositionDetail(idempotencyKey, position, { quiet = false } = {}) {
  selectedKey = idempotencyKey;
  texEditing = false;
  syncArtifactTabs();
  resetJobDescription();
  renderPositionList();
  const empty = $("companyDetailEmpty");
  const body = $("companyDetailBody");
  if (empty) empty.hidden = true;
  if (body) body.hidden = false;

  $("companyPositionTitle").textContent = position.title || "Untitled role";
  const metaParts = [
    position.location,
    position.master_resume_slug ? `master: ${position.master_resume_slug}` : "",
    position.applied ? "Applied" : "",
    position.looking_to_apply ? "Looking to apply" : "",
  ].filter(Boolean);
  $("companyPositionMeta").textContent = metaParts.join(" · ");
  updateJdToggleButton(position);
  renderPositionCard(position);

  const hasUrl = Boolean(position.url);
  const applyLink = $("companyApplyLink");
  const applyHint = $("companyApplyHint");
  const applyHintText = $("companyApplyHintText");
  const applyUrl = $("companyApplyUrl");
  const hasPdf = artifactHasPdf(position);
  if (applyLink) {
    applyLink.href = position.url || "#";
    applyLink.hidden = !hasUrl;
  }
  if (applyHint && applyHintText && applyUrl) {
    applyHint.hidden = !hasUrl;
    if (hasUrl) {
      applyHintText.textContent = hasPdf
        ? "After downloading your PDF, apply at the original posting: "
        : "Apply at the original posting: ";
      applyUrl.href = position.url;
      applyUrl.textContent = position.url;
    }
  }

  const download = $("companyDownloadPdf");
  const openPdf = $("companyOpenPdf");
  const base = artifactApiBase(idempotencyKey);
  const pdfUrl = `${base}/pdf?ts=${Date.now()}`;
  if (download) {
    download.href = `${base}/pdf?download=1`;
    download.download = artifactPdfFilename(position);
    download.hidden = !hasPdf;
  }
  if (openPdf) {
    openPdf.href = hasPdf ? pdfUrl : "#";
    openPdf.hidden = !hasPdf;
  }

  const texView = $("companyTexView");
  const pdfFrame = $("companyPdfFrame");
  const pdfMissing = $("companyPdfMissing");
  if (pdfMissing) pdfMissing.textContent = emptyPdfMessage();

  if (artifactHasTex(position)) {
    if (!quiet) setLoadingProgress(35);
    try {
      const tex = await api(`${base}/tex`);
      setTexViewMode({ editing: false, content: tex.content || "" });
    } catch (err) {
      setTexViewMode({ editing: false, content: "" });
      if (texView) texView.textContent = "";
      showError(err.message || "Failed to load LaTeX");
    } finally {
      if (!quiet) finishLoadingProgress();
    }
  } else {
    setTexViewMode({ editing: false, content: "" });
    if (!quiet) finishLoadingProgress();
  }

  if (hasPdf && pdfFrame) {
    pdfFrame.hidden = false;
    pdfFrame.src = pdfUrl;
    if (pdfMissing) pdfMissing.hidden = true;
  } else {
    if (pdfFrame) {
      pdfFrame.removeAttribute("src");
      pdfFrame.hidden = true;
    }
    if (pdfMissing) pdfMissing.hidden = false;
  }
}

async function switchArtifactMode(mode) {
  if (mode !== "cv" && mode !== "cover-letter") return;
  if (mode === artifactMode) return;
  if (texEditing) {
    const proceed = window.confirm("Discard unsaved LaTeX edits and switch document?");
    if (!proceed) return;
    texEditing = false;
  }
  artifactMode = mode;
  syncArtifactTabs();
  const position = positions.find((p) => p.idempotency_key === selectedKey);
  if (position) {
    showError("");
    await loadPositionDetail(selectedKey, position, { quiet: true });
  }
}

async function selectPosition(idempotencyKey) {
  const position = positions.find((p) => p.idempotency_key === idempotencyKey);
  if (!position) return;
  showError("");
  await loadPositionDetail(idempotencyKey, position);
}

async function loadWorkspace() {
  showError("");
  setLoadingProgress(20);
  try {
    const data = await api(
      `/api/mcp/companies/${encodeURIComponent(routeCountry)}/${encodeURIComponent(routeSlug)}/applications`,
    );
    companyName = data.company || "";
    positions = data.positions || [];
    document.title = `${companyName} — Relocation Jobs`;
    $("companyTitle").textContent = companyName;
    $("companySubtitle").textContent = "Tailored resumes, cover letters, and PDF preview";
    $("companyCountryLabel").textContent = (data.country || routeCountry).toUpperCase();

    if (routeSlug !== data.company_slug) {
      const canonical = companyWorkspacePath(data.country, companyName);
      window.history.replaceState(null, "", canonical);
    }

    renderPositionList();
    const preferred = positions.find((p) => p.has_pdf)
      || positions.find((p) => p.has_tailored_tex)
      || positions.find((p) => p.has_cover_letter_pdf)
      || positions.find((p) => p.has_cover_letter_tex)
      || positions.find((p) => p.looking_to_apply || p.pinned)
      || positions[0];
    if (preferred?.idempotency_key) {
      artifactMode = preferred.has_pdf || preferred.has_tailored_tex
        ? "cv"
        : (preferred.has_cover_letter_pdf || preferred.has_cover_letter_tex ? "cover-letter" : "cv");
      await loadPositionDetail(preferred.idempotency_key, preferred);
    } else {
      clearDetail();
    }
  } catch (err) {
    showError(err.message || "Failed to load company workspace");
    clearDetail();
  } finally {
    finishLoadingProgress();
  }
}

async function refreshPositionsAfterRender() {
  const data = await api(
    `/api/mcp/companies/${encodeURIComponent(routeCountry)}/${encodeURIComponent(routeSlug)}/applications`,
  );
  positions = data.positions || [];
  renderPositionList();
  const position = positions.find((p) => p.idempotency_key === selectedKey);
  if (position) {
    await loadPositionDetail(selectedKey, position, { quiet: true });
  }
}

async function rerenderPdf() {
  if (!selectedKey) return;
  const btn = $("companyRenderBtn");
  const saveBtn = $("companyTexSaveBtn");
  const editBtn = $("companyTexEditBtn");
  btn.disabled = true;
  if (saveBtn) saveBtn.disabled = true;
  if (editBtn) editBtn.disabled = true;
  showError("");
  beginScreenLoad("Rendering PDF…");
  setScreenLoadProgress(15);
  const tick = window.setInterval(() => setScreenLoadProgress(88), 800);
  try {
    if (texEditing) {
      setScreenLoadProgress(20);
      await persistTex();
    }
    setScreenLoadProgress(25);
    const result = await api(
      `${artifactApiBase(selectedKey)}/render`,
      { method: "POST" },
    );
    setScreenLoadProgress(92);
    if (!result.ok) {
      throw new Error(result.error || result.log || "Render failed");
    }
    showToast("PDF re-rendered");
    setScreenLoadProgress(96);
    await refreshPositionsAfterRender();
  } catch (err) {
    showError(err.message || "Failed to re-render PDF");
  } finally {
    window.clearInterval(tick);
    endScreenLoad();
    btn.disabled = false;
    if (saveBtn) saveBtn.disabled = false;
    if (editBtn) editBtn.disabled = false;
  }
}

async function refreshAuth() {
  const res = await fetch("/api/auth/status", { credentials: "same-origin" });
  const data = await res.json();
  if (!data.authenticated) {
    showLogin();
    return false;
  }
  showApp();
  return true;
}

async function submitLogin(event) {
  event.preventDefault();
  $("companyLoginError").textContent = "";
  const username = $("companyLoginUsername").value.trim();
  const password = $("companyLoginPassword").value;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("companyLoginError").textContent = data.error || "Sign in failed";
      return;
    }
    $("companyLoginPassword").value = "";
    showApp();
    await loadWorkspace();
  } catch {
    $("companyLoginError").textContent = "Network error";
  }
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  clearDetail();
  positions = [];
  showLogin();
}

function bindEvents() {
  $("companyLoginForm")?.addEventListener("submit", submitLogin);
  $("companyLogoutBtn")?.addEventListener("click", logout);
  $("companyJdToggleBtn")?.addEventListener("click", toggleJobDescription);
  $("companyJdFetchBtn")?.addEventListener("click", fetchJobDescription);
  $("companyJdEditBtn")?.addEventListener("click", startJobDescriptionEdit);
  $("companyJdSaveBtn")?.addEventListener("click", saveJobDescription);
  $("companyJdCancelBtn")?.addEventListener("click", cancelJobDescriptionEdit);
  $("companyRenderBtn")?.addEventListener("click", rerenderPdf);
  $("companyTexEditBtn")?.addEventListener("click", startTexEdit);
  $("companyTexSaveBtn")?.addEventListener("click", saveTex);
  $("companyTexCancelBtn")?.addEventListener("click", cancelTexEdit);
  $("companyArtifactCv")?.addEventListener("click", () => switchArtifactMode("cv"));
  $("companyArtifactCover")?.addEventListener("click", () => switchArtifactMode("cover-letter"));
  $("companyPositionList")?.addEventListener("click", (event) => {
    const btn = event.target.closest(".company-position-item");
    if (!btn) return;
    selectPosition(btn.dataset.key);
  });
  $("companyDetailBody")?.addEventListener("position-state-changed", async (event) => {
    const { detail } = event;
    if (detail.type === "auth-required") {
      showLogin();
      return;
    }
    if (detail.type === "error") {
      showError(detail.message || "Position state update failed");
      return;
    }
    if (detail.message) {
      showToast(detail.message);
    }
    await refreshPositionsAfterRender();
  });
}

async function init() {
  bindEvents();
  try {
    parseRoute();
  } catch (err) {
    showError(err.message);
    return;
  }
  if (await refreshAuth()) {
    await loadWorkspace();
  }
}

init();
