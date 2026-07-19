/** Application data — profile + master resumes + project masters for MCP (per logged-in user). */

import { beginScreenLoad, endScreenLoad, setScreenLoadProgress } from "./screen-loader.js";
import { $, escapeHtml, finishLoadingProgress, setLoadingProgress } from "./utils.js";

let masterItems = [];
let selectedSlug = "";
let selectedHasPdf = false;
let selectedPdfFilename = "resume.pdf";
let projectItems = [];
let selectedProjectSlug = "";
let selectedProjectHasPdf = false;
let selectedProjectPdfFilename = "project.pdf";
const MAX_PIPELINE_PROMPTS = 5;

function showLogin() {
  const content = $("applyContent");
  if (content) content.hidden = true;
  $("applyLoginPanel").hidden = false;
}

function showApp() {
  $("applyLoginPanel").hidden = true;
  const content = $("applyContent");
  if (content) content.hidden = false;
}

function showError(message) {
  const el = $("applyError");
  if (!el) return;
  el.hidden = !message;
  el.textContent = message || "";
}

function showToast(message) {
  const toast = $("applyToast");
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

function setTab(tab) {
  for (const btn of document.querySelectorAll(".apply-tab")) {
    btn.classList.toggle("apply-tab--active", btn.dataset.tab === tab);
  }
  const profile = $("applyProfilePanel");
  const masters = $("applyMastersPanel");
  const projects = $("applyProjectsPanel");
  const connect = $("applyConnectPanel");
  if (profile) profile.hidden = tab !== "profile";
  if (masters) masters.hidden = tab !== "masters";
  if (projects) projects.hidden = tab !== "projects";
  if (connect) connect.hidden = tab !== "connect";

  if (tab === "connect") {
    loadConnectPanel().catch((err) => showError(err.message || "Failed to load MCP connect info"));
  }

  // PDF iframes load while their panel is hidden (profile is the default tab).
  // Re-set src after show so the browser PDF viewer gets the real viewport size.
  if (tab === "masters" && selectedSlug) {
    updateMasterPdfPreview({
      slug: selectedSlug,
      hasPdf: selectedHasPdf,
      pdfFilename: selectedPdfFilename,
    });
  }
  if (tab === "projects" && selectedProjectSlug) {
    updateProjectPdfPreview({
      slug: selectedProjectSlug,
      hasPdf: selectedProjectHasPdf,
      pdfFilename: selectedProjectPdfFilename,
    });
  }
}

function fillProfileForm(profile) {
  $("profileFullName").value = profile.full_name || "";
  $("profileEmail").value = profile.email || "";
  $("profilePhone").value = profile.phone || "";
  $("profileLinkedin").value = profile.linkedin_url || "";
  $("profileLocation").value = profile.location || "";
  $("profileWorkAuth").value = profile.work_authorization || "";
  $("profileNotice").value = profile.notice_period || "";
  $("profileSummary").value = profile.summary || "";
  renderPipelineList(Array.isArray(profile.pipeline) ? profile.pipeline : []);
}

function pipelineFromForm({ includeEmpty = false } = {}) {
  const items = document.querySelectorAll(".apply-pipeline-item textarea");
  const values = Array.from(items).map((el) => el.value.trim());
  return includeEmpty ? values : values.filter(Boolean);
}

function renderPipelineList(prompts) {
  const list = $("applyPipelineList");
  const addBtn = $("applyPipelineAddBtn");
  if (!list) return;

  const items = prompts.slice(0, MAX_PIPELINE_PROMPTS);
  if (!items.length) {
    list.innerHTML = `<p class="apply-pipeline-empty">No pipeline prompts yet.</p>`;
  } else {
    list.innerHTML = items.map((text, index) => `
      <div class="apply-pipeline-item">
        <div class="apply-pipeline-item-header">
          <label for="applyPipeline${index}">Prompt ${index + 1}</label>
          <div class="apply-pipeline-item-actions">
            <div class="apply-pipeline-reorder">
              <button type="button" class="apply-pipeline-move" data-index="${index}" data-dir="-1" aria-label="Move prompt ${index + 1} up"${index === 0 ? " disabled" : ""}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="18 15 12 9 6 15"/></svg>
              </button>
              <button type="button" class="apply-pipeline-move" data-index="${index}" data-dir="1" aria-label="Move prompt ${index + 1} down"${index === items.length - 1 ? " disabled" : ""}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
            </div>
            <button type="button" class="link-btn apply-pipeline-remove" data-index="${index}" aria-label="Remove prompt ${index + 1}">Remove</button>
          </div>
        </div>
        <textarea id="applyPipeline${index}" class="apply-pipeline-textarea" rows="3" placeholder="Instructions for Claude before reframing">${escapeHtml(text)}</textarea>
      </div>
    `).join("");
  }

  if (addBtn) {
    addBtn.disabled = items.length >= MAX_PIPELINE_PROMPTS;
    addBtn.hidden = items.length >= MAX_PIPELINE_PROMPTS;
  }
}

function addPipelinePrompt() {
  const prompts = pipelineFromForm({ includeEmpty: true });
  if (prompts.length >= MAX_PIPELINE_PROMPTS) return;
  prompts.push("");
  renderPipelineList(prompts);
  const textareas = document.querySelectorAll(".apply-pipeline-item textarea");
  textareas[textareas.length - 1]?.focus();
}

function removePipelinePrompt(index) {
  const prompts = pipelineFromForm({ includeEmpty: true });
  prompts.splice(index, 1);
  renderPipelineList(prompts);
}

function movePipelinePrompt(index, delta) {
  const prompts = pipelineFromForm({ includeEmpty: true });
  const target = index + delta;
  if (target < 0 || target >= prompts.length) return;
  [prompts[index], prompts[target]] = [prompts[target], prompts[index]];
  renderPipelineList(prompts);
}

function profilePayload() {
  return {
    full_name: $("profileFullName").value.trim(),
    email: $("profileEmail").value.trim(),
    phone: $("profilePhone").value.trim(),
    linkedin_url: $("profileLinkedin").value.trim(),
    location: $("profileLocation").value.trim(),
    work_authorization: $("profileWorkAuth").value.trim(),
    notice_period: $("profileNotice").value.trim(),
    summary: $("profileSummary").value.trim(),
    pipeline: pipelineFromForm(),
  };
}

function masterPdfUrl(slug, { download = false } = {}) {
  const params = new URLSearchParams();
  if (download) params.set("download", "1");
  else params.set("ts", String(Date.now()));
  const query = params.toString();
  return `/api/mcp/master-resumes/${encodeURIComponent(slug)}/pdf${query ? `?${query}` : ""}`;
}

function updateMasterPdfPreview({ slug, hasPdf, pdfFilename }) {
  selectedHasPdf = Boolean(hasPdf);
  selectedPdfFilename = pdfFilename || "resume.pdf";

  const download = $("applyMasterDownloadPdf");
  const openPdf = $("applyMasterOpenPdf");
  if (download) {
    download.href = slug ? masterPdfUrl(slug, { download: true }) : "#";
    download.download = selectedPdfFilename;
    download.hidden = !selectedHasPdf;
  }
  if (openPdf) {
    openPdf.href = slug && selectedHasPdf ? masterPdfUrl(slug) : "#";
    openPdf.hidden = !selectedHasPdf;
  }

  const pdfFrame = $("applyMasterPdfFrame");
  const pdfMissing = $("applyMasterPdfMissing");
  const renderBtn = $("applyMasterRenderBtn");

  if (renderBtn) renderBtn.disabled = !slug;

  if (selectedHasPdf && slug && pdfFrame) {
    pdfFrame.hidden = false;
    pdfFrame.src = masterPdfUrl(slug);
    if (pdfMissing) pdfMissing.hidden = true;
  } else {
    if (pdfFrame) {
      pdfFrame.removeAttribute("src");
      pdfFrame.hidden = true;
    }
    if (pdfMissing) pdfMissing.hidden = false;
  }
}

function renderMasterList() {
  const list = $("applyMasterList");
  if (!list) return;

  if (!masterItems.length) {
    list.innerHTML = `<li class="apply-master-empty">No master resumes yet — create one.</li>`;
    return;
  }

  list.innerHTML = masterItems.map((item) => {
    const label = (item.label || item.slug).trim();
    const active = item.slug === selectedSlug ? " apply-master-item--active" : "";
    const pdfBadge = item.has_pdf
      ? '<span class="apply-master-item-badge apply-master-item-badge--pdf">PDF</span>'
      : "";
    return `<li><button type="button" class="apply-master-item${active}" data-slug="${escapeHtml(item.slug)}"><span class="apply-master-item-label">${escapeHtml(label)}${pdfBadge}</span><span class="apply-master-item-slug">${escapeHtml(item.slug)}</span></button></li>`;
  }).join("");
}

function clearMasterEditor() {
  selectedSlug = "";
  selectedHasPdf = false;
  selectedPdfFilename = "resume.pdf";
  $("applyMasterSlug").value = "";
  $("applyMasterLabel").value = "";
  $("applyMasterContent").value = "";
  $("applyMasterUpdated").textContent = "";
  updateMasterPdfPreview({ slug: "", hasPdf: false });
  const pdfMissing = $("applyMasterPdfMissing");
  if (pdfMissing) pdfMissing.hidden = false;
  renderMasterList();
}

async function loadMasterDetail(slug) {
  selectedSlug = slug;
  renderMasterList();
  setLoadingProgress(20);
  try {
    const detail = await api(`/api/mcp/master-resumes/${encodeURIComponent(slug)}`);
    $("applyMasterSlug").value = detail.slug || slug;
    $("applyMasterLabel").value = detail.label || "";
    $("applyMasterContent").value = detail.content || "";
    const updatedParts = [];
    if (detail.updated_at) updatedParts.push(`Updated ${detail.updated_at}`);
    if (detail.pdf_updated_at) updatedParts.push(`PDF ${detail.pdf_updated_at}`);
    $("applyMasterUpdated").textContent = updatedParts.join(" · ");
    updateMasterPdfPreview({
      slug: detail.slug || slug,
      hasPdf: detail.has_pdf,
      pdfFilename: detail.pdf_filename,
    });
  } finally {
    finishLoadingProgress();
  }
}

async function persistMaster() {
  const slug = $("applyMasterSlug").value.trim();
  const content = $("applyMasterContent").value;
  if (!slug) {
    throw new Error("Slug is required (e.g. go, java, fullstack)");
  }
  if (!content.trim()) {
    throw new Error("LaTeX content cannot be empty");
  }

  const saved = await api(`/api/mcp/master-resumes/${encodeURIComponent(slug)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      label: $("applyMasterLabel").value.trim(),
    }),
  });
  selectedSlug = saved.slug || slug;
  const mastersData = await api("/api/mcp/master-resumes");
  masterItems = mastersData.items || [];
  renderMasterList();
  $("applyMasterUpdated").textContent = saved.updated_at
    ? `Updated ${saved.updated_at}`
    : "";
  return saved;
}

async function refreshMasterDetail(slug = selectedSlug) {
  if (!slug) return null;
  const detail = await api(`/api/mcp/master-resumes/${encodeURIComponent(slug)}`);
  const updatedParts = [];
  if (detail.updated_at) updatedParts.push(`Updated ${detail.updated_at}`);
  if (detail.pdf_updated_at) updatedParts.push(`PDF ${detail.pdf_updated_at}`);
  $("applyMasterUpdated").textContent = updatedParts.join(" · ");
  updateMasterPdfPreview({
    slug: detail.slug || slug,
    hasPdf: detail.has_pdf,
    pdfFilename: detail.pdf_filename,
  });
  return detail;
}

async function rerenderMasterPdf() {
  const slug = $("applyMasterSlug").value.trim() || selectedSlug;
  if (!slug) {
    showError("Select or save a master resume before rendering PDF");
    return;
  }

  const btn = $("applyMasterRenderBtn");
  const saveBtn = $("applyMasterSaveBtn");
  btn.disabled = true;
  if (saveBtn) saveBtn.disabled = true;
  showError("");
  beginScreenLoad("Rendering PDF…");
  setScreenLoadProgress(15);
  const tick = window.setInterval(() => setScreenLoadProgress(88), 800);
  try {
    setScreenLoadProgress(20);
    await persistMaster();
    setScreenLoadProgress(35);
    const result = await api(
      `/api/mcp/master-resumes/${encodeURIComponent(selectedSlug)}/render`,
      { method: "POST" },
    );
    setScreenLoadProgress(92);
    if (!result.ok) {
      throw new Error(result.error || result.log || "Render failed");
    }
    showToast("PDF re-rendered");
    updateMasterPdfPreview({
      slug: selectedSlug,
      hasPdf: Boolean(result.pdf_stored),
      pdfFilename: result.pdf_filename,
    });
    setScreenLoadProgress(96);
    await refreshMasterDetail(selectedSlug);
  } catch (err) {
    showError(err.message || "Failed to re-render PDF");
  } finally {
    window.clearInterval(tick);
    endScreenLoad();
    btn.disabled = false;
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function loadData() {
  showError("");
  setLoadingProgress(15);
  try {
    const [profileData, mastersData, projectsData] = await Promise.all([
      api("/api/mcp/profile"),
      api("/api/mcp/master-resumes"),
      api("/api/mcp/project-masters"),
    ]);
    fillProfileForm(profileData.profile || {});
    masterItems = mastersData.items || [];
    projectItems = projectsData.items || [];
    renderMasterList();
    renderProjectList();
    if (masterItems.length && !selectedSlug) {
      await loadMasterDetail(masterItems[0].slug);
    }
    if (projectItems.length && !selectedProjectSlug) {
      await loadProjectDetail(projectItems[0].slug);
    }
  } finally {
    finishLoadingProgress();
  }
}

async function saveProfile(event) {
  event.preventDefault();
  showError("");
  const btn = $("applyProfileSaveBtn");
  btn.disabled = true;
  try {
    await api("/api/mcp/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profilePayload()),
    });
    showToast("Profile saved");
  } catch (err) {
    showError(err.message || "Failed to save profile");
  } finally {
    btn.disabled = false;
  }
}

async function saveMaster() {
  showError("");
  const btn = $("applyMasterSaveBtn");
  btn.disabled = true;
  try {
    await persistMaster();
    await refreshMasterDetail(selectedSlug);
    showToast(`Saved ${selectedSlug}`);
  } catch (err) {
    showError(err.message || "Failed to save master resume");
  } finally {
    btn.disabled = false;
  }
}

function startNewMaster() {
  clearMasterEditor();
  $("applyMasterSlug").focus();
}

function projectPdfUrl(slug, { download = false } = {}) {
  const params = new URLSearchParams();
  if (download) params.set("download", "1");
  else params.set("ts", String(Date.now()));
  const query = params.toString();
  return `/api/mcp/project-masters/${encodeURIComponent(slug)}/pdf${query ? `?${query}` : ""}`;
}

function updateProjectPdfPreview({ slug, hasPdf, pdfFilename }) {
  selectedProjectHasPdf = Boolean(hasPdf);
  selectedProjectPdfFilename = pdfFilename || "project.pdf";

  const download = $("applyProjectDownloadPdf");
  const openPdf = $("applyProjectOpenPdf");
  if (download) {
    download.href = slug ? projectPdfUrl(slug, { download: true }) : "#";
    download.download = selectedProjectPdfFilename;
    download.hidden = !selectedProjectHasPdf;
  }
  if (openPdf) {
    openPdf.href = slug && selectedProjectHasPdf ? projectPdfUrl(slug) : "#";
    openPdf.hidden = !selectedProjectHasPdf;
  }

  const pdfFrame = $("applyProjectPdfFrame");
  const pdfMissing = $("applyProjectPdfMissing");
  const renderBtn = $("applyProjectRenderBtn");

  if (renderBtn) renderBtn.disabled = !slug;

  if (selectedProjectHasPdf && slug && pdfFrame) {
    pdfFrame.hidden = false;
    pdfFrame.src = projectPdfUrl(slug);
    if (pdfMissing) pdfMissing.hidden = true;
  } else {
    if (pdfFrame) {
      pdfFrame.removeAttribute("src");
      pdfFrame.hidden = true;
    }
    if (pdfMissing) pdfMissing.hidden = false;
  }
}

function renderProjectList() {
  const list = $("applyProjectList");
  if (!list) return;

  if (!projectItems.length) {
    list.innerHTML = `<li class="apply-master-empty">No project masters yet — create one.</li>`;
    return;
  }

  list.innerHTML = projectItems.map((item) => {
    const label = (item.label || item.slug).trim();
    const active = item.slug === selectedProjectSlug ? " apply-master-item--active" : "";
    const pdfBadge = item.has_pdf
      ? '<span class="apply-master-item-badge apply-master-item-badge--pdf">PDF</span>'
      : "";
    return `<li><button type="button" class="apply-master-item${active}" data-slug="${escapeHtml(item.slug)}"><span class="apply-master-item-label">${escapeHtml(label)}${pdfBadge}</span><span class="apply-master-item-slug">${escapeHtml(item.slug)}</span></button></li>`;
  }).join("");
}

function clearProjectEditor() {
  selectedProjectSlug = "";
  selectedProjectHasPdf = false;
  selectedProjectPdfFilename = "project.pdf";
  $("applyProjectSlug").value = "";
  $("applyProjectLabel").value = "";
  $("applyProjectContent").value = "";
  $("applyProjectUpdated").textContent = "";
  updateProjectPdfPreview({ slug: "", hasPdf: false });
  const pdfMissing = $("applyProjectPdfMissing");
  if (pdfMissing) pdfMissing.hidden = false;
  renderProjectList();
}

async function loadProjectDetail(slug) {
  selectedProjectSlug = slug;
  renderProjectList();
  setLoadingProgress(20);
  try {
    const detail = await api(`/api/mcp/project-masters/${encodeURIComponent(slug)}`);
    $("applyProjectSlug").value = detail.slug || slug;
    $("applyProjectLabel").value = detail.label || "";
    $("applyProjectContent").value = detail.content || "";
    const updatedParts = [];
    if (detail.updated_at) updatedParts.push(`Updated ${detail.updated_at}`);
    if (detail.pdf_updated_at) updatedParts.push(`PDF ${detail.pdf_updated_at}`);
    $("applyProjectUpdated").textContent = updatedParts.join(" · ");
    updateProjectPdfPreview({
      slug: detail.slug || slug,
      hasPdf: detail.has_pdf,
      pdfFilename: detail.pdf_filename,
    });
  } finally {
    finishLoadingProgress();
  }
}

async function persistProject() {
  const slug = $("applyProjectSlug").value.trim();
  const content = $("applyProjectContent").value;
  if (!slug) {
    throw new Error("Slug is required (e.g. relocation-jobs)");
  }
  if (!content.trim()) {
    throw new Error("Project content cannot be empty");
  }

  const saved = await api(`/api/mcp/project-masters/${encodeURIComponent(slug)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      label: $("applyProjectLabel").value.trim(),
    }),
  });
  selectedProjectSlug = saved.slug || slug;
  const projectsData = await api("/api/mcp/project-masters");
  projectItems = projectsData.items || [];
  renderProjectList();
  $("applyProjectUpdated").textContent = saved.updated_at
    ? `Updated ${saved.updated_at}`
    : "";
  return saved;
}

async function refreshProjectDetail(slug = selectedProjectSlug) {
  if (!slug) return null;
  const detail = await api(`/api/mcp/project-masters/${encodeURIComponent(slug)}`);
  const updatedParts = [];
  if (detail.updated_at) updatedParts.push(`Updated ${detail.updated_at}`);
  if (detail.pdf_updated_at) updatedParts.push(`PDF ${detail.pdf_updated_at}`);
  $("applyProjectUpdated").textContent = updatedParts.join(" · ");
  updateProjectPdfPreview({
    slug: detail.slug || slug,
    hasPdf: detail.has_pdf,
    pdfFilename: detail.pdf_filename,
  });
  return detail;
}

async function rerenderProjectPdf() {
  const slug = $("applyProjectSlug").value.trim() || selectedProjectSlug;
  if (!slug) {
    showError("Select or save a project master before rendering PDF");
    return;
  }

  const btn = $("applyProjectRenderBtn");
  const saveBtn = $("applyProjectSaveBtn");
  btn.disabled = true;
  if (saveBtn) saveBtn.disabled = true;
  showError("");
  beginScreenLoad("Rendering PDF…");
  setScreenLoadProgress(15);
  const tick = window.setInterval(() => setScreenLoadProgress(88), 800);
  try {
    setScreenLoadProgress(20);
    await persistProject();
    setScreenLoadProgress(35);
    const result = await api(
      `/api/mcp/project-masters/${encodeURIComponent(selectedProjectSlug)}/render`,
      { method: "POST" },
    );
    setScreenLoadProgress(92);
    if (!result.ok) {
      throw new Error(result.error || result.log || "Render failed");
    }
    showToast("PDF re-rendered");
    updateProjectPdfPreview({
      slug: selectedProjectSlug,
      hasPdf: Boolean(result.pdf_stored),
      pdfFilename: result.pdf_filename,
    });
    setScreenLoadProgress(96);
    await refreshProjectDetail(selectedProjectSlug);
  } catch (err) {
    showError(err.message || "Failed to re-render PDF");
  } finally {
    window.clearInterval(tick);
    endScreenLoad();
    btn.disabled = false;
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function saveProject() {
  showError("");
  const btn = $("applyProjectSaveBtn");
  btn.disabled = true;
  try {
    await persistProject();
    await refreshProjectDetail(selectedProjectSlug);
    showToast(`Saved ${selectedProjectSlug}`);
  } catch (err) {
    showError(err.message || "Failed to save project master");
  } finally {
    btn.disabled = false;
  }
}

function startNewProject() {
  clearProjectEditor();
  $("applyProjectSlug").focus();
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
  $("applyLoginError").textContent = "";
  const username = $("applyLoginUsername").value.trim();
  const password = $("applyLoginPassword").value;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("applyLoginError").textContent = data.error || "Sign in failed";
      return;
    }
    $("applyLoginPassword").value = "";
    showApp();
    await loadData();
  } catch {
    $("applyLoginError").textContent = "Network error";
  }
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  clearMasterEditor();
  clearProjectEditor();
  masterItems = [];
  projectItems = [];
  showLogin();
}

async function loadConnectPanel() {
  const info = await api("/api/mcp/connect-info");
  const urlInput = $("applyMcpUrl");
  if (urlInput) urlInput.value = info.mcp_url || "";
  await refreshTokenList();
}

async function refreshTokenList() {
  const data = await api("/api/mcp/tokens");
  const list = $("applyTokenList");
  if (!list) return;
  const items = data.items || [];
  if (!items.length) {
    list.innerHTML = '<li class="apply-pipeline-empty">No API tokens yet.</li>';
    return;
  }
  list.innerHTML = items
    .map((item) => {
      const status = item.revoked ? "Revoked" : "Active";
      const revoke = item.revoked
        ? ""
        : `<button type="button" class="link-btn apply-token-revoke" data-id="${item.id}">Revoke</button>`;
      return `<li class="apply-token-item">
        <span class="apply-token-meta">${escapeHtml(item.label || "Untitled")} · ${escapeHtml(status)} · ${escapeHtml(item.created_at || "")}</span>
        ${revoke}
      </li>`;
    })
    .join("");
}

async function createApiToken() {
  const label = ($("applyTokenLabel")?.value || "").trim();
  const data = await api("/api/mcp/tokens", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  const once = $("applyTokenOnce");
  const value = $("applyTokenOnceValue");
  if (once && value) {
    value.textContent = data.token || "";
    once.hidden = false;
  }
  if ($("applyTokenLabel")) $("applyTokenLabel").value = "";
  await refreshTokenList();
  showToast("Token created — copy it now");
}

async function revokeApiToken(tokenId) {
  await api(`/api/mcp/tokens/${tokenId}`, { method: "DELETE" });
  showToast("Token revoked");
  await refreshTokenList();
}

async function copyText(value, okMessage) {
  if (!value) return;
  await navigator.clipboard.writeText(value);
  showToast(okMessage);
}

function bindEvents() {
  $("applyLoginForm")?.addEventListener("submit", submitLogin);
  $("applyLogoutBtn")?.addEventListener("click", logout);
  $("applyProfileForm")?.addEventListener("submit", saveProfile);
  $("applyPipelineAddBtn")?.addEventListener("click", addPipelinePrompt);
  $("applyPipelineList")?.addEventListener("click", (e) => {
    const removeBtn = e.target.closest(".apply-pipeline-remove");
    if (removeBtn) {
      removePipelinePrompt(Number(removeBtn.dataset.index));
      return;
    }
    const moveBtn = e.target.closest(".apply-pipeline-move");
    if (!moveBtn || moveBtn.disabled) return;
    movePipelinePrompt(Number(moveBtn.dataset.index), Number(moveBtn.dataset.dir));
  });
  $("applyMasterSaveBtn")?.addEventListener("click", saveMaster);
  $("applyMasterRenderBtn")?.addEventListener("click", rerenderMasterPdf);
  $("applyNewMasterBtn")?.addEventListener("click", startNewMaster);
  $("applyMasterList")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".apply-master-item");
    if (!btn) return;
    loadMasterDetail(btn.dataset.slug);
  });
  $("applyProjectSaveBtn")?.addEventListener("click", saveProject);
  $("applyProjectRenderBtn")?.addEventListener("click", rerenderProjectPdf);
  $("applyNewProjectBtn")?.addEventListener("click", startNewProject);
  $("applyProjectList")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".apply-master-item");
    if (!btn) return;
    loadProjectDetail(btn.dataset.slug);
  });

  for (const tabBtn of document.querySelectorAll(".apply-tab")) {
    tabBtn.addEventListener("click", () => setTab(tabBtn.dataset.tab));
  }

  $("applyMcpUrlCopyBtn")?.addEventListener("click", () => {
    copyText($("applyMcpUrl")?.value || "", "MCP URL copied");
  });
  $("applyTokenCreateBtn")?.addEventListener("click", () => {
    createApiToken().catch((err) => showError(err.message || "Failed to create token"));
  });
  $("applyTokenOnceCopyBtn")?.addEventListener("click", () => {
    copyText($("applyTokenOnceValue")?.textContent || "", "Token copied");
  });
  $("applyTokenList")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".apply-token-revoke");
    if (!btn) return;
    revokeApiToken(Number(btn.dataset.id)).catch((err) => showError(err.message || "Failed to revoke token"));
  });
}

async function init() {
  bindEvents();
  if (await refreshAuth()) {
    try {
      await loadData();
    } catch (err) {
      showError(err.message || "Failed to load application data");
    }
  }
}

init();
