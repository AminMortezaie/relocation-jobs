/** DOM event listeners for the jobs panel. */

import { state, companyKey } from "./state.js";
import { $, toast, atsScoreTone, isNarrowViewport, debounce, SEARCH_DEBOUNCE_MS } from "./utils.js";
import {
  removeCompany,
  setNotForMe,
  restoreJob,
  toggleApplied,
  toggleRejected,
  reapplyJob,
  saveAtsScore,
  markJobSeen,
  toggleSeen,
  toggleLookingToApply,
  toggleCompanyAwaitingResponse,
} from "./api.js";
import { pinJob } from "./api.js";
import { loadJobs, loadCities, ensureLocationsLoaded } from "./data.js";
import { loadBoard } from "./board.js";
import {
  renderCompanies,
  toggleCompanyCollapse,
  toggleShowNotForMe,
  toggleShowRejected,
  hideFetchPanel,
  notForMeReasonMeta,
  updateFetchHeaderUI,
} from "./render.js";
import { saveShowRejectedCompanies } from "./storage.js";
import { fetchOneCompany, ensureFetchPolling } from "./scrape.js";
import { fetchPanelState } from "./fetch-ui.js";
import { openEditCareersDialog, openEditCompanyNameDialog, openEditCityDialog } from "./dialogs.js";
import { saveCollapsedCompanies } from "./storage.js";
import { logout, submitAuth, setLoginMode } from "./auth.js";
import { closeAllHeaderPopovers } from "./header.js";

let atsScrollListener = null;
let hideReasonScrollListener = null;

function ensureAtsWrapId(wrap) {
  if (!wrap.dataset.atsWrapId) {
    wrap.dataset.atsWrapId = `ats-wrap-${crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  }
  return wrap.dataset.atsWrapId;
}

function getAtsPopover(wrap) {
  if (!wrap) return null;
  const wrapId = wrap.dataset.atsWrapId;
  if (wrapId) {
    const floating = document.body.querySelector(
      `.ats-score-popover[data-ats-wrap-id="${wrapId}"]`,
    );
    if (floating) return floating;
  }
  return wrap.querySelector(".ats-score-popover");
}

function resolveAtsWrap(el) {
  const wrap = el?.closest?.(".ats-score-wrap");
  if (wrap) return wrap;
  const popover = el?.closest?.(".ats-score-popover");
  const wrapId = popover?.dataset?.atsWrapId;
  if (!wrapId) return null;
  return document.querySelector(`.ats-score-wrap[data-ats-wrap-id="${wrapId}"]`);
}

function mountAtsPopover(wrap) {
  const popover = wrap.querySelector(".ats-score-popover");
  if (!popover || popover.parentElement === document.body) return popover;

  ensureAtsWrapId(wrap);
  popover.dataset.atsWrapId = wrap.dataset.atsWrapId;

  const placeholder = document.createComment("ats-score-popover-anchor");
  popover.parentNode.insertBefore(placeholder, popover);
  wrap._atsPopoverPlaceholder = placeholder;
  document.body.appendChild(popover);
  return popover;
}

function unmountAtsPopover(wrap) {
  const popover = getAtsPopover(wrap);
  const placeholder = wrap?._atsPopoverPlaceholder;
  if (!popover || popover.parentElement !== document.body) return;
  if (placeholder?.parentNode) {
    placeholder.parentNode.insertBefore(popover, placeholder);
    placeholder.remove();
  } else {
    wrap?.appendChild(popover);
  }
  delete wrap?._atsPopoverPlaceholder;
}

function resetAtsPopover(wrap) {
  const popover = getAtsPopover(wrap);
  if (!popover) return;
  popover.classList.remove("is-floating", "is-sheet");
  popover.style.top = "";
  popover.style.left = "";
}

function showAtsBackdrop() {
  const backdrop = $("atsScoreBackdrop");
  if (backdrop) {
    backdrop.hidden = false;
    backdrop.setAttribute("aria-hidden", "false");
  }
}

function hideAtsBackdrop() {
  const backdrop = $("atsScoreBackdrop");
  if (backdrop) {
    backdrop.hidden = true;
    backdrop.setAttribute("aria-hidden", "true");
  }
}

function positionAtsPopover(wrap) {
  const popover = mountAtsPopover(wrap);
  const trigger = wrap.querySelector(".ats-score-trigger");
  if (!popover || !trigger) return;

  popover.classList.add("is-floating");
  popover.hidden = false;

  if (isNarrowViewport()) {
    popover.classList.add("is-sheet");
    popover.style.top = "";
    popover.style.left = "";
    return;
  }

  popover.classList.remove("is-sheet");

  requestAnimationFrame(() => {
    const tr = trigger.getBoundingClientRect();
    const pr = popover.getBoundingClientRect();
    const gap = 10;
    const margin = 12;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top = tr.top - pr.height - gap;
    if (top < margin) top = tr.bottom + gap;
    if (top + pr.height > vh - margin) {
      top = Math.max(margin, vh - pr.height - margin);
    }

    let left = tr.right - pr.width;
    if (left + pr.width > vw - margin) left = vw - pr.width - margin;
    left = Math.max(margin, left);

    popover.style.top = `${Math.round(top)}px`;
    popover.style.left = `${Math.round(left)}px`;
  });
}

function hideReferralBackdrop() {
  const backdrop = $("referralBackdrop");
  if (backdrop) {
    backdrop.hidden = true;
    backdrop.setAttribute("aria-hidden", "true");
  }
}

function closeReferralPopovers() {
  document.dispatchEvent(new CustomEvent("referral-popover-close"));
  hideReferralBackdrop();
}

export function closePanelPopovers() {
  closeReferralPopovers();
  closeHideReasonPopovers();
  closeAtsPopovers();
}

function ensureHideReasonWrapId(wrap) {
  if (!wrap.dataset.hideWrapId) {
    wrap.dataset.hideWrapId = `hide-wrap-${crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  }
  return wrap.dataset.hideWrapId;
}

function getHideReasonPopover(wrap) {
  if (!wrap) return null;
  const wrapId = wrap.dataset.hideWrapId;
  if (wrapId) {
    const floating = document.body.querySelector(
      `.hide-reason-popover[data-hide-wrap-id="${wrapId}"]`,
    );
    if (floating) return floating;
  }
  return wrap.querySelector(".hide-reason-popover");
}

function resolveHideReasonWrap(el) {
  const wrap = el?.closest?.(".hide-reason-wrap");
  if (wrap) return wrap;
  const popover = el?.closest?.(".hide-reason-popover");
  const wrapId = popover?.dataset?.hideWrapId;
  if (!wrapId) return null;
  return document.querySelector(`.hide-reason-wrap[data-hide-wrap-id="${wrapId}"]`);
}

function mountHideReasonPopover(wrap) {
  const popover = wrap.querySelector(".hide-reason-popover");
  if (!popover || popover.parentElement === document.body) return popover;

  ensureHideReasonWrapId(wrap);
  popover.dataset.hideWrapId = wrap.dataset.hideWrapId;

  const placeholder = document.createComment("hide-reason-popover-anchor");
  popover.parentNode.insertBefore(placeholder, popover);
  wrap._hideReasonPopoverPlaceholder = placeholder;
  document.body.appendChild(popover);
  return popover;
}

function unmountHideReasonPopover(wrap) {
  const popover = getHideReasonPopover(wrap);
  const placeholder = wrap?._hideReasonPopoverPlaceholder;
  if (!popover || popover.parentElement !== document.body) return;
  if (placeholder?.parentNode) {
    placeholder.parentNode.insertBefore(popover, placeholder);
    placeholder.remove();
  } else {
    wrap?.appendChild(popover);
  }
  delete wrap?._hideReasonPopoverPlaceholder;
}

function resetHideReasonPopover(wrap) {
  const popover = getHideReasonPopover(wrap);
  if (!popover) return;
  popover.classList.remove("is-floating", "is-sheet");
  popover.style.top = "";
  popover.style.left = "";
  popover.style.minWidth = "";
}

function closeHideReasonPopovers(exceptWrap = null) {
  document.querySelectorAll(".hide-reason-wrap").forEach((wrap) => {
    if (wrap === exceptWrap) return;
    const popover = getHideReasonPopover(wrap);
    const trigger = wrap.querySelector(".hide-reason-trigger");
    if (popover) popover.hidden = true;
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    resetHideReasonPopover(wrap);
    unmountHideReasonPopover(wrap);
  });
  const exceptWrapId = exceptWrap?.dataset?.hideWrapId;
  document.body.querySelectorAll(".hide-reason-popover").forEach((popover) => {
    if (exceptWrapId && popover.dataset.hideWrapId === exceptWrapId) return;
    popover.hidden = true;
    popover.classList.remove("is-floating", "is-sheet");
    popover.style.top = "";
    popover.style.left = "";
    popover.style.minWidth = "";
  });
  if (hideReasonScrollListener) {
    window.removeEventListener("scroll", hideReasonScrollListener, true);
    hideReasonScrollListener = null;
  }
}

function positionHideReasonPopover(wrap) {
  const popover = mountHideReasonPopover(wrap);
  const trigger = wrap.querySelector(".hide-reason-trigger");
  if (!popover || !trigger) return;

  popover.classList.add("is-floating");
  popover.hidden = false;

  if (isNarrowViewport()) {
    popover.classList.add("is-sheet");
    popover.style.top = "";
    popover.style.left = "";
    popover.style.minWidth = "";
    return;
  }

  popover.classList.remove("is-sheet");

  requestAnimationFrame(() => {
    const tr = trigger.getBoundingClientRect();
    const pr = popover.getBoundingClientRect();
    const gap = 8;
    const margin = 12;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top = tr.bottom + gap;
    if (top + pr.height > vh - margin) top = tr.top - pr.height - gap;
    top = Math.max(margin, Math.min(top, vh - pr.height - margin));

    let left = tr.left;
    if (left + pr.width > vw - margin) left = vw - pr.width - margin;
    left = Math.max(margin, left);

    popover.style.top = `${Math.round(top)}px`;
    popover.style.left = `${Math.round(left)}px`;
    popover.style.minWidth = `${Math.round(tr.width)}px`;
  });
}

function toggleHideReasonPopover(wrap) {
  const popover = getHideReasonPopover(wrap) || wrap.querySelector(".hide-reason-popover");
  const trigger = wrap.querySelector(".hide-reason-trigger");
  if (!popover || !trigger) return;
  const open = popover.hidden;
  closeHideReasonPopovers(open ? wrap : null);
  closeReferralPopovers();
  closeAtsPopovers();
  trigger.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    positionHideReasonPopover(wrap);
    hideReasonScrollListener = () => closeHideReasonPopovers();
    window.addEventListener("scroll", hideReasonScrollListener, true);
  } else {
    popover.hidden = true;
    resetHideReasonPopover(wrap);
    unmountHideReasonPopover(wrap);
  }
}

function clickTargetElement(target) {
  return target instanceof Element ? target : target?.parentElement ?? null;
}

function markSeenFromPositionCard(card) {
  if (!card) return;
  const companyCard = card.closest(".company-card");
  let country = card.dataset.country || companyCard?.dataset.country || "";
  let company = card.dataset.company || companyCard?.dataset.company || "";
  const { url, idempotencyKey } = card.dataset;
  if (!country || country === "all" || !company || !url) return;
  void markJobSeen(country, company, url, idempotencyKey || "");
}

function bindHideReasonPopoverEvents() {
  document.addEventListener("click", async (e) => {
    const hideReasonTrigger = e.target.closest(".hide-reason-trigger");
    if (hideReasonTrigger) {
      e.stopPropagation();
      const wrap = hideReasonTrigger.closest(".hide-reason-wrap");
      if (wrap) toggleHideReasonPopover(wrap);
      return;
    }

    const hideReasonOption = e.target.closest(".hide-reason-option");
    if (hideReasonOption) {
      e.stopPropagation();
      const wrap = resolveHideReasonWrap(hideReasonOption);
      const card = wrap?.closest(".position-card");
      if (!card || hideReasonOption.disabled) return;
      await submitHideReasonFromCard(card, hideReasonOption.dataset.reason);
      return;
    }

    if (e.target.closest(".hide-reason-popover")) {
      e.stopPropagation();
    }
  });
}

async function submitHideReasonFromCard(card, reason) {
  const wrap = card.querySelector(".hide-reason-wrap");
  const currentReason = wrap?.dataset.currentReason || "";
  if (currentReason && currentReason === reason) {
    closeHideReasonPopovers();
    return true;
  }

  const { country, company, url } = card.dataset;
  const option = getHideReasonPopover(wrap)?.querySelector(
    `.hide-reason-option[data-reason="${reason}"]`,
  );
  if (option) option.disabled = true;
  if (wrap?.querySelector(".hide-reason-trigger")) {
    wrap.querySelector(".hide-reason-trigger").disabled = true;
  }

  const ok = await setNotForMe(country, company, url, true, reason);
  if (option) option.disabled = false;
  if (wrap?.querySelector(".hide-reason-trigger")) {
    wrap.querySelector(".hide-reason-trigger").disabled = false;
  }
  if (!ok) return false;

  closeHideReasonPopovers();
  const { label } = notForMeReasonMeta(reason);
  toast(currentReason ? `Category changed · ${label}` : `Hidden · ${label}`);
  return true;
}

function closeAtsPopovers(exceptWrap = null) {
  document.querySelectorAll(".ats-score-wrap").forEach((wrap) => {
    if (wrap === exceptWrap) return;
    const popover = getAtsPopover(wrap);
    const trigger = wrap.querySelector(".ats-score-trigger");
    if (popover) popover.hidden = true;
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    resetAtsPopover(wrap);
    unmountAtsPopover(wrap);
  });
  const exceptWrapId = exceptWrap?.dataset?.atsWrapId;
  document.body.querySelectorAll(".ats-score-popover").forEach((popover) => {
    if (exceptWrapId && popover.dataset.atsWrapId === exceptWrapId) return;
    popover.hidden = true;
    popover.classList.remove("is-floating", "is-sheet");
    popover.style.top = "";
    popover.style.left = "";
  });
  hideAtsBackdrop();
  if (atsScrollListener) {
    window.removeEventListener("scroll", atsScrollListener, true);
    atsScrollListener = null;
  }
}

function updateAtsScorePreview(wrap, score, options = {}) {
  const value = Math.max(0, Math.min(100, Number(score) || 0));
  const popover = getAtsPopover(wrap);
  if (!popover) return value;
  const preview = popover.querySelector(".ats-score-preview");
  const ring = popover.querySelector(".ats-score-ring-preview");
  const previewWrap = popover.querySelector(".ats-score-preview-wrap");
  const slider = popover.querySelector(".ats-score-slider");
  const number = popover.querySelector(".ats-score-number");
  if (preview) preview.textContent = String(value);
  if (ring) ring.style.setProperty("--ats-pct", String(value));
  if (previewWrap) {
    previewWrap.classList.remove("ats-high", "ats-mid", "ats-low");
    previewWrap.classList.add(atsScoreTone(value));
  }
  if (!options.skipSlider && slider && Number(slider.value) !== value) {
    slider.value = String(value);
  }
  if (!options.skipNumber && number && document.activeElement !== number) {
    number.value = String(value);
  }
  popover.querySelectorAll(".ats-quick-chip").forEach((chip) => {
    chip.classList.toggle("is-active", Number(chip.dataset.score) === value);
  });
  return value;
}

function readAtsScoreValue(wrap) {
  const popover = getAtsPopover(wrap);
  const number = popover?.querySelector(".ats-score-number");
  const slider = popover?.querySelector(".ats-score-slider");
  const raw = (number?.value ?? "").trim();
  if (raw !== "") {
    const parsed = Number(raw);
    if (!Number.isInteger(parsed) || parsed < 0 || parsed > 100) {
      return null;
    }
    return parsed;
  }
  return updateAtsScorePreview(wrap, slider?.value ?? 0);
}

function toggleAtsPopover(wrap) {
  const popover = getAtsPopover(wrap) || wrap.querySelector(".ats-score-popover");
  const trigger = wrap.querySelector(".ats-score-trigger");
  if (!popover || !trigger) return;
  const open = popover.hidden;
  closeReferralPopovers();
  closeHideReasonPopovers();
  closeAtsPopovers(open ? wrap : null);
  trigger.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    showAtsBackdrop();
    positionAtsPopover(wrap);
    atsScrollListener = () => closeAtsPopovers();
    window.addEventListener("scroll", atsScrollListener, true);
    const mounted = getAtsPopover(wrap);
    const slider = mounted?.querySelector(".ats-score-slider");
    const number = mounted?.querySelector(".ats-score-number");
    const initialScore = number?.value ?? slider?.value ?? 70;
    if (slider) updateAtsScorePreview(wrap, initialScore);
    slider?.focus();
  }
}

async function submitAtsScoreFromCard(card, atsScore) {
  const { country, company, url } = card.dataset;
  const wrap = card.querySelector(".ats-score-wrap");
  const popover = getAtsPopover(wrap);
  const saveBtn = popover?.querySelector(".ats-score-save-btn");
  const clearBtn = popover?.querySelector(".ats-score-clear-btn");
  if (saveBtn) saveBtn.disabled = true;
  if (clearBtn) clearBtn.disabled = true;
  const result = await saveAtsScore(country, company, url, atsScore);
  if (saveBtn) saveBtn.disabled = false;
  if (clearBtn) clearBtn.disabled = false;
  if (!result) return false;
  closeAtsPopovers();
  toast(atsScore == null ? "ATS score removed" : `ATS score · ${atsScore}`);
  return true;
}

function bindAtsPopoverEvents() {
  document.addEventListener("input", (e) => {
    const slider = e.target.closest(".ats-score-slider");
    if (slider) {
      const wrap = resolveAtsWrap(slider);
      if (wrap) updateAtsScorePreview(wrap, slider.value);
      return;
    }

    const number = e.target.closest(".ats-score-number");
    if (!number) return;
    const wrap = resolveAtsWrap(number);
    if (!wrap) return;
    const raw = number.value.trim();
    if (raw === "") return;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return;
    updateAtsScorePreview(wrap, parsed, { skipNumber: true });
  });

  document.addEventListener("change", (e) => {
    const number = e.target.closest(".ats-score-number");
    if (!number) return;
    const wrap = resolveAtsWrap(number);
    if (wrap) updateAtsScorePreview(wrap, number.value);
  });

  document.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const number = e.target.closest(".ats-score-number");
    if (!number) return;
    e.preventDefault();
    const card = resolveAtsWrap(number)?.closest(".position-card");
    const wrap = resolveAtsWrap(number);
    if (!card || !wrap) return;
    const score = readAtsScoreValue(wrap);
    if (score == null) {
      toast("ATS score must be a whole number 0–100");
      number.focus();
      return;
    }
    await submitAtsScoreFromCard(card, score);
  });

  document.addEventListener("click", async (e) => {
    const atsTrigger = e.target.closest(".ats-score-trigger");
    if (atsTrigger) {
      e.stopPropagation();
      const wrap = atsTrigger.closest(".ats-score-wrap");
      if (wrap) toggleAtsPopover(wrap);
      return;
    }

    const atsCloseBtn = e.target.closest(".ats-score-close");
    if (atsCloseBtn) {
      e.stopPropagation();
      closeAtsPopovers();
      return;
    }

    const atsQuickChip = e.target.closest(".ats-quick-chip");
    if (atsQuickChip) {
      e.stopPropagation();
      const wrap = resolveAtsWrap(atsQuickChip);
      if (wrap) updateAtsScorePreview(wrap, atsQuickChip.dataset.score);
      return;
    }

    const atsSaveBtn = e.target.closest(".ats-score-save-btn");
    if (atsSaveBtn) {
      e.stopPropagation();
      const wrap = resolveAtsWrap(atsSaveBtn);
      const card = wrap?.closest(".position-card");
      if (!card || !wrap) return;
      const score = readAtsScoreValue(wrap);
      if (score == null) {
        toast("ATS score must be a whole number 0–100");
        getAtsPopover(wrap)?.querySelector(".ats-score-number")?.focus();
        return;
      }
      await submitAtsScoreFromCard(card, score);
      return;
    }

    const atsClearBtn = e.target.closest(".ats-score-clear-btn");
    if (atsClearBtn) {
      e.stopPropagation();
      const wrap = resolveAtsWrap(atsClearBtn);
      const card = wrap?.closest(".position-card");
      if (!card) return;
      await submitAtsScoreFromCard(card, null);
      return;
    }

    if (e.target.closest(".ats-score-popover")) {
      e.stopPropagation();
    }
  });
}

function bindJobsListEvents() {
  $("jobs").addEventListener("click", async (e) => {
    const collapseBtn = e.target.closest(".collapse-company-btn");
    if (collapseBtn) {
      const card = collapseBtn.closest(".company-card");
      if (!card) return;
      toggleCompanyCollapse(companyKey(card.dataset.country, card.dataset.company));
      return;
    }

    const showNotForMeBtn = e.target.closest(".show-not-for-me-btn");
    if (showNotForMeBtn) {
      toggleShowNotForMe(showNotForMeBtn.dataset.companyKey);
      return;
    }

    const showRejectedBtn = e.target.closest(".show-rejected-btn");
    if (showRejectedBtn) {
      toggleShowRejected(showRejectedBtn.dataset.companyKey);
      return;
    }

    const awaitingResponseBtn = e.target.closest(".awaiting-response-btn");
    if (awaitingResponseBtn) {
      const card = awaitingResponseBtn.closest(".company-card");
      if (!card) return;
      const { country, company } = card.dataset;
      const awaiting = awaitingResponseBtn.dataset.awaiting !== "1";
      awaitingResponseBtn.disabled = true;
      const result = await toggleCompanyAwaitingResponse(country, company, awaiting);
      awaitingResponseBtn.disabled = false;
      if (!result) return;
      return;
    }

    const jobTitleLink = clickTargetElement(e.target)?.closest(".job-title");
    if (jobTitleLink) {
      const card = jobTitleLink.closest(".position-card");
      if (card) markSeenFromPositionCard(card);
      return;
    }

    const appliedBtn = e.target.closest(".applied-btn");
    if (appliedBtn) {
      const card = appliedBtn.closest(".position-card");
      if (!card) return;
      const { country, company, url, idempotencyKey } = card.dataset;
      const applied = appliedBtn.dataset.applied !== "1";
      appliedBtn.disabled = true;
      const result = await toggleApplied(country, company, url, applied, idempotencyKey);
      appliedBtn.disabled = false;
      if (!result) return;
      return;
    }

    if (e.target.closest(".referral-wrap, .referral-popover")) {
      return;
    }

    closeAtsPopovers();
    closeReferralPopovers();
    closeHideReasonPopovers();

    const rejectedBtn = e.target.closest(".rejected-btn");
    if (rejectedBtn) {
      const card = rejectedBtn.closest(".position-card");
      if (!card) return;
      const { country, company, url, idempotencyKey } = card.dataset;
      const rejected = rejectedBtn.dataset.rejected !== "1";
      rejectedBtn.disabled = true;
      const result = await toggleRejected(country, company, url, rejected, idempotencyKey);
      rejectedBtn.disabled = false;
      if (!result) return;
      if (rejected) {
        state.showRejectedCompanies.add(companyKey(country, company));
        saveShowRejectedCompanies();
      }
      return;
    }

    const lookingToApplyBtn = e.target.closest(".looking-to-apply-btn");
    if (lookingToApplyBtn) {
      const card = lookingToApplyBtn.closest(".position-card");
      if (!card) return;
      const { country, company, url, idempotencyKey } = card.dataset;
      const lookingToApply = lookingToApplyBtn.dataset.looking !== "1";
      lookingToApplyBtn.disabled = true;
      const result = await toggleLookingToApply(country, company, url, lookingToApply, idempotencyKey);
      lookingToApplyBtn.disabled = false;
      if (!result) return;
      return;
    }

    const sawBeforeBtn = e.target.closest(".saw-before-btn");
    if (sawBeforeBtn) {
      const card = sawBeforeBtn.closest(".position-card");
      if (!card) return;
      const { country, company, url, idempotencyKey } = card.dataset;
      const seen = sawBeforeBtn.dataset.seen !== "1";
      sawBeforeBtn.disabled = true;
      const result = await toggleSeen(country, company, url, seen, idempotencyKey);
      sawBeforeBtn.disabled = false;
      if (!result) return;
      return;
    }

    const pinJobBtn = e.target.closest(".pin-job-btn");
    if (pinJobBtn) {
      const card = pinJobBtn.closest(".position-card");
      if (!card) return;
      const { country, company, url, idempotencyKey } = card.dataset;
      if (await pinJob(country, company, url, idempotencyKey)) {
        toast("Pinned to top");
      }
      return;
    }

    const reapplyBtn = e.target.closest(".reapply-btn");
    if (reapplyBtn) {
      const card = reapplyBtn.closest(".position-card");
      if (!card) return;
      const { country, company, url } = card.dataset;
      reapplyBtn.disabled = true;
      const result = await reapplyJob(country, company, url);
      if (!result) {
        reapplyBtn.disabled = false;
        return;
      }
      toast("Moved back to open positions");
      return;
    }

    const restoreBtn = e.target.closest(".restore-job-btn");
    if (restoreBtn) {
      const card = restoreBtn.closest(".position-card");
      if (!card) return;
      const { country, company, url } = card.dataset;
      restoreBtn.disabled = true;
      const ok = await restoreJob(country, company, url);
      if (!ok) {
        restoreBtn.disabled = false;
        return;
      }
      toast("Role restored");
      return;
    }

    const fetchBtn = e.target.closest(".fetch-company-btn");
    if (fetchBtn) {
      await fetchOneCompany(fetchBtn.dataset.country, fetchBtn.dataset.company);
      return;
    }

    const editNameBtn = e.target.closest(".edit-name-btn");
    if (editNameBtn) {
      openEditCompanyNameDialog(
        editNameBtn.dataset.country,
        editNameBtn.dataset.company,
        editNameBtn.dataset.countryLabel || ""
      );
      return;
    }

    const editCareersBtn = e.target.closest(".edit-careers-btn");
    if (editCareersBtn) {
      openEditCareersDialog(
        editCareersBtn.dataset.country,
        editCareersBtn.dataset.company,
        editCareersBtn.dataset.url || "",
        editCareersBtn.dataset.countryLabel || ""
      );
      return;
    }

    const editCityBtn = e.target.closest(".edit-city-btn");
    if (editCityBtn) {
      let locations = [];
      try {
        locations = JSON.parse(editCityBtn.dataset.locations || "[]");
      } catch {
        locations = [];
      }
      openEditCityDialog(
        editCityBtn.dataset.country,
        editCityBtn.dataset.company,
        locations,
        editCityBtn.dataset.countryLabel || ""
      );
      return;
    }

    const removeBtn = e.target.closest(".remove-company-btn");
    if (removeBtn) {
      const { country, company } = removeBtn.dataset;
      if (!confirm(`Remove ${company} from ${country}? This deletes it from the catalog.`)) {
        return;
      }
      removeBtn.disabled = true;
      const result = await removeCompany(country, company);
      if (!result) {
        removeBtn.disabled = false;
        return;
      }
      toast(`Removed ${result.company}`);
      state.collapsedCompanies.delete(companyKey(country, company));
      saveCollapsedCompanies();
      await loadJobs();
    }
  });

}

function bindToolbarEvents() {
  $("country").addEventListener("change", async () => {
    updateFetchHeaderUI();
    await loadCities();
    await loadJobs({ force: true, overlayLabel: "Updating board…" });
  });
  $("ats")?.addEventListener("change", () => {
    void loadJobs({ force: true, overlayLabel: "Updating board…" });
  });
  $("location")?.addEventListener("focus", () => {
    void ensureLocationsLoaded();
  });
  $("location")?.addEventListener("change", () => {
    void loadJobs({ force: true, overlayLabel: "Updating board…" });
  });
  $("search").addEventListener("input", debounce(() => {
    void loadBoard({ force: true, noOverlay: true, preserveContent: true });
  }, SEARCH_DEBOUNCE_MS));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (fetchPanelState.open) {
      hideFetchPanel();
      ensureFetchPolling();
    }
    closeReferralPopovers();
    closeHideReasonPopovers();
    closeAtsPopovers();
  });

  $("atsScoreBackdrop")?.addEventListener("click", () => closeAtsPopovers());

  $("logoutBtn").addEventListener("click", () => {
    closeAllHeaderPopovers();
    logout();
  });
  $("loginForm").addEventListener("submit", submitAuth);
  $("toggleRegister").addEventListener("click", () => {
    setLoginMode(state.loginMode === "register" ? "login" : "register");
    $("loginError").textContent = "";
  });
}

export function bindEvents() {
  bindAtsPopoverEvents();
  bindHideReasonPopoverEvents();
  bindJobsListEvents();
  bindToolbarEvents();
}
