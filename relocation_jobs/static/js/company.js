/** Company workspace — per-position tailored CV + PDF preview. */

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
  if (hint) {
    hint.textContent = withCv
      ? `${withCv} of ${positions.length} roles have a tailored CV.`
      : "No tailored CVs yet — use Claude Desktop MCP after marking roles looking to apply.";
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

function clearDetail() {
  selectedKey = "";
  savedTexContent = "";
  texEditing = false;
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
    view.textContent = content || "No tailored LaTeX for this position yet.";
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
    `/api/mcp/applications/${encodeURIComponent(selectedKey)}/tex`,
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

async function loadPositionDetail(idempotencyKey, position, { quiet = false } = {}) {
  selectedKey = idempotencyKey;
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

  const hasUrl = Boolean(position.url);
  const applyLink = $("companyApplyLink");
  const applyHint = $("companyApplyHint");
  const applyHintText = $("companyApplyHintText");
  const applyUrl = $("companyApplyUrl");
  if (applyLink) {
    applyLink.href = position.url || "#";
    applyLink.hidden = !hasUrl;
  }
  if (applyHint && applyHintText && applyUrl) {
    applyHint.hidden = !hasUrl;
    if (hasUrl) {
      applyHintText.textContent = position.has_pdf
        ? "After downloading your PDF, apply at the original posting: "
        : "Apply at the original posting: ";
      applyUrl.href = position.url;
      applyUrl.textContent = position.url;
    }
  }

  const download = $("companyDownloadPdf");
  const openPdf = $("companyOpenPdf");
  const pdfUrl = `/api/mcp/applications/${encodeURIComponent(idempotencyKey)}/pdf?ts=${Date.now()}`;
  if (download) {
    download.href = `/api/mcp/applications/${encodeURIComponent(idempotencyKey)}/pdf?download=1`;
    download.download = position.pdf_filename || "resume.pdf";
    download.hidden = !position.has_pdf;
  }
  if (openPdf) {
    openPdf.href = position.has_pdf ? pdfUrl : "#";
    openPdf.hidden = !position.has_pdf;
  }

  const texView = $("companyTexView");
  const pdfFrame = $("companyPdfFrame");
  const pdfMissing = $("companyPdfMissing");

  if (position.has_tailored_tex) {
    if (!quiet) setLoadingProgress(35);
    try {
      const tex = await api(`/api/mcp/applications/${encodeURIComponent(idempotencyKey)}/tex`);
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
  }

  if (position.has_pdf && pdfFrame) {
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
    $("companySubtitle").textContent = "Tailored resumes and PDF preview";
    $("companyCountryLabel").textContent = (data.country || routeCountry).toUpperCase();

    if (routeSlug !== data.company_slug) {
      const canonical = companyWorkspacePath(data.country, companyName);
      window.history.replaceState(null, "", canonical);
    }

    renderPositionList();
    const preferred = positions.find((p) => p.has_pdf)
      || positions.find((p) => p.has_tailored_tex)
      || positions.find((p) => p.looking_to_apply || p.pinned)
      || positions[0];
    if (preferred?.idempotency_key) {
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
      `/api/mcp/applications/${encodeURIComponent(selectedKey)}/render`,
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
  $("companyRenderBtn")?.addEventListener("click", rerenderPdf);
  $("companyTexEditBtn")?.addEventListener("click", startTexEdit);
  $("companyTexSaveBtn")?.addEventListener("click", saveTex);
  $("companyTexCancelBtn")?.addEventListener("click", cancelTexEdit);
  $("companyPositionList")?.addEventListener("click", (event) => {
    const btn = event.target.closest(".company-position-item");
    if (!btn) return;
    selectPosition(btn.dataset.key);
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
