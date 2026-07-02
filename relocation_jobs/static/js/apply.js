/** Application data — profile + master resumes for MCP (per logged-in user). */

import { $, escapeHtml, setLoadingProgress, finishLoadingProgress } from "./utils.js";

let masterItems = [];
let selectedSlug = "";
const MAX_PIPELINE_PROMPTS = 5;

function showLogin() {
  $("applyContent")?.classList.add("hidden");
  $("applyLoginPanel").hidden = false;
}

function showApp() {
  $("applyLoginPanel").hidden = true;
  $("applyContent")?.classList.remove("hidden");
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
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    showLogin();
    throw new Error("Authentication required");
  }
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function setTab(tab) {
  for (const btn of document.querySelectorAll(".apply-tab")) {
    btn.classList.toggle("apply-tab--active", btn.dataset.tab === tab);
  }
  $("applyProfilePanel")?.classList.toggle("hidden", tab !== "profile");
  $("applyMastersPanel")?.classList.toggle("hidden", tab !== "masters");
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
    return `<li><button type="button" class="apply-master-item${active}" data-slug="${escapeHtml(item.slug)}">${escapeHtml(label)}<span class="apply-master-item-slug">${escapeHtml(item.slug)}</span></button></li>`;
  }).join("");
}

function clearMasterEditor() {
  selectedSlug = "";
  $("applyMasterSlug").value = "";
  $("applyMasterLabel").value = "";
  $("applyMasterContent").value = "";
  $("applyMasterUpdated").textContent = "";
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
    $("applyMasterUpdated").textContent = detail.updated_at
      ? `Updated ${detail.updated_at}`
      : "";
  } finally {
    finishLoadingProgress();
  }
}

async function loadData() {
  showError("");
  setLoadingProgress(15);
  try {
    const [profileData, mastersData] = await Promise.all([
      api("/api/mcp/profile"),
      api("/api/mcp/master-resumes"),
    ]);
    fillProfileForm(profileData.profile || {});
    masterItems = mastersData.items || [];
    renderMasterList();
    if (masterItems.length && !selectedSlug) {
      await loadMasterDetail(masterItems[0].slug);
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
  const slug = $("applyMasterSlug").value.trim();
  const content = $("applyMasterContent").value;
  if (!slug) {
    showError("Slug is required (e.g. go, java, fullstack)");
    return;
  }
  if (!content.trim()) {
    showError("LaTeX content cannot be empty");
    return;
  }

  const btn = $("applyMasterSaveBtn");
  btn.disabled = true;
  try {
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
    showToast(`Saved ${selectedSlug}`);
  } catch (err) {
    showError(err.message || "Failed to save master resume");
  } finally {
    btn.disabled = false;
  }
}

function startNewMaster() {
  selectedSlug = "";
  $("applyMasterSlug").value = "";
  $("applyMasterLabel").value = "";
  $("applyMasterContent").value = "";
  $("applyMasterUpdated").textContent = "";
  renderMasterList();
  $("applyMasterSlug").focus();
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
  showLogin();
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
  $("applyNewMasterBtn")?.addEventListener("click", startNewMaster);
  $("applyMasterList")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".apply-master-item");
    if (!btn) return;
    loadMasterDetail(btn.dataset.slug);
  });

  for (const tabBtn of document.querySelectorAll(".apply-tab")) {
    tabBtn.addEventListener("click", () => setTab(tabBtn.dataset.tab));
  }
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
