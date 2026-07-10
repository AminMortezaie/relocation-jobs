/** <position-card> Web Component — position state management for panel & company page. */

import { escapeHtml, formatActivityBadge, formatAppliedLabel, formatAppliedHistoryTitle, atsScoreTone } from "./utils.js";
import { HIDE_REASONS, notForMeReasonMeta } from "./render.js";

const API = {
  applied: "/api/jobs/applied",
  rejected: "/api/jobs/rejected",
  notForMe: "/api/jobs/not-for-me",
  lookingToApply: "/api/jobs/looking-to-apply",
  seen: "/api/jobs/seen",
  waitingReferral: "/api/jobs/waiting-referral",
  atsScore: "/api/jobs/ats-score",
  pin: "/api/jobs/pin",
  reapply: "/api/jobs/reapply",
};

function newestStatusDate(dates, fallback) {
  const list = (dates || []).filter(Boolean).map((d) => String(d).trim()).filter(Boolean);
  const fb = (fallback || "").trim();
  if (fb) list.push(fb);
  list.sort();
  return list.length ? list[list.length - 1] : "";
}

function jobActivityTs(job) {
  return (job?.fetched || job?.last_seen || "").trim();
}

function companySlug(name) {
  return String(name || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function companyWorkspacePath(country, companyName) {
  const countryKey = String(country || "").trim().toLowerCase();
  const slug = companySlug(companyName);
  if (!countryKey || !slug) return "/";
  return `/company/${encodeURIComponent(countryKey)}/${encodeURIComponent(slug)}`;
}

function posCls(job) {
  return [
    job.pinned ? " position-pinned" : "",
    job.applied ? " position-applied" : "",
    job.waiting_referral ? " position-waiting-referral" : "",
    job.looking_to_apply && !job.applied ? " position-looking-to-apply" : "",
    job.seen ? " position-seen" : "",
  ].join("");
}

function cvBadges(job) {
  const country = job.country || "";
  const companyName = job.company || "";
  const hasCv = Boolean(job.has_tailored_tex || job.has_pdf);
  const hasCl = Boolean(job.has_cover_letter_tex || job.has_cover_letter_pdf);
  if (!hasCv && !hasCl && !job.master_resume_slug) return "";
  const href = String(job.workspace_path || "").trim() || companyWorkspacePath(country, companyName);
  let html = "";
  if (job.has_pdf) {
    html += `<a class="badge cv-pdf" href="${href}" title="Open tailored CV and PDF preview">PDF ready</a>`;
  } else if (job.has_tailored_tex) {
    html += `<a class="badge cv-tex" href="${href}" title="Open tailored LaTeX source">CV ready</a>`;
  }
  if (job.has_cover_letter_pdf) {
    html += `<a class="badge cv-pdf" href="${href}" title="Open cover letter PDF preview">CL PDF</a>`;
  } else if (job.has_cover_letter_tex) {
    html += `<a class="badge cv-tex" href="${href}" title="Open cover letter LaTeX source">CL ready</a>`;
  }
  if (job.master_resume_slug) {
    html += `<span class="badge cv-master" title="Master resume variant used">${escapeHtml(job.master_resume_slug)}</span>`;
  }
  return html;
}

const CITY_PREVIEW_LIMIT = 3;

/** Split a job location string into de-duped city entries. Locations are
 *  separated by ";" (e.g. "Belgrade, Serbia; Berlin, Germany"); a lone
 *  "City, Country" stays a single entry (we do not split on its comma). */
function splitJobCities(text) {
  const trimmed = (text || "").trim();
  if (!trimmed) return [];
  let parts;
  if (trimmed.includes(";")) parts = trimmed.split(";");
  else if (trimmed.includes(" · ")) parts = trimmed.split(" · ");
  else return [trimmed];
  const seen = new Set();
  const out = [];
  for (const part of parts) {
    const label = part.trim();
    if (!label) continue;
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(label);
  }
  return out;
}

class PositionCard extends HTMLElement {
  static observedAttributes = ["variant"];

  constructor() {
    super();
    this._job = null;
    this._variant = "open";
    this._citiesExpanded = false;
    this._closeOnScrollHandler = null;
  }

  get job() { return this._job; }
  set job(val) {
    const prev = this._job;
    this._job = val;
    if (this.isConnected && val !== prev) {
      this._citiesExpanded = false;
      this.render();
    }
  }

  get variant() { return this._variant; }
  set variant(val) {
    if (val !== this._variant) {
      this._variant = val;
      if (this.isConnected) this.render();
    }
  }

  attributeChangedCallback(name, oldVal, newVal) {
    if (name === "variant" && newVal !== oldVal) this.variant = newVal;
  }

  connectedCallback() {
    if (this.hasAttribute("variant")) this._variant = this.getAttribute("variant");
    if (!this._listening) {
      this.addEventListener("click", this);
      this.addEventListener("input", this);
      this.addEventListener("change", this);
      this.addEventListener("keydown", this);
      this._popoverClose = () => this._closeAllPopovers();
      document.addEventListener("position-card-popover-open", this._popoverClose);
      this._listening = true;
    }
    this.render();
  }

  disconnectedCallback() {
    if (this._popoverClose) {
      document.removeEventListener("position-card-popover-open", this._popoverClose);
    }
  }

  handleEvent(e) {
    if (e.type === "click") this._onClick(e);
    else if (e.type === "input") this._onInput(e);
    else if (e.type === "change") this._onChange(e);
    else if (e.type === "keydown") this._onKeydown(e);
  }

  // --- API ---

  async _api(path, body) {
    const res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.status === 401) { this._dispatch("auth-required"); return null; }
    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) return res.ok ? {} : null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { this._dispatch("error", { message: data.error || `Request failed (${res.status})` }); return null; }
    return data;
  }

  _dispatch(type, detail) {
    this.dispatchEvent(new CustomEvent("position-state-changed", {
      bubbles: true, composed: true,
      detail: {
        type,
        country: this._job?.country || "",
        company: this._job?.company || "",
        url: this._job?.url || "",
        idempotencyKey: this._job?.idempotency_key || "",
        variant: this._variant,
        job: this._job,
        ...detail,
      },
    }));
  }

  _toast(msg) { this._dispatch("toast", { message: msg }); }

  _apply(data) {
    if (!data) return;
    this._job = { ...this._job, ...data };
    this.render();
    this._dispatch("mutated", { job: this._job, apiData: data });
  }

  // --- Actions ---

  async _toggleApplied() {
    const applied = !this._job.applied;
    const data = await this._api(API.applied, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      applied, ...(this._job.idempotency_key ? { idempotency_key: this._job.idempotency_key } : {}),
    });
    if (!data) return;
    this._apply(data);
    this._toast(applied ? "Marked as applied" : "Applied mark cleared");
  }

  async _toggleRejected() {
    const rejected = !this._job.rejected;
    const data = await this._api(API.rejected, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      rejected, ...(this._job.idempotency_key ? { idempotency_key: this._job.idempotency_key } : {}),
    });
    if (!data) return;
    if (rejected) { this._variant = "rejected"; this._toast("Marked as rejected"); }
    this._apply(data);
  }

  async _toggleLookingToApply() {
    const looking = !this._job.looking_to_apply;
    const data = await this._api(API.lookingToApply, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      looking_to_apply: looking,
      ...(this._job.idempotency_key ? { idempotency_key: this._job.idempotency_key } : {}),
    });
    if (!data) return;
    this._apply(data);
    this._toast(looking ? "Marked as looking to apply" : "Looking-to-apply cleared");
  }

  async _toggleSeen() {
    const seen = !this._job.seen;
    const data = await this._api(API.seen, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      seen, ...(this._job.idempotency_key ? { idempotency_key: this._job.idempotency_key } : {}),
    });
    if (!data) return;
    this._apply(data);
    this._toast(seen ? "Marked as seen" : "Seen mark cleared");
  }

  async _togglePin() {
    const pinned = !this._job.pinned;
    const data = await this._api(API.pin, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      pinned, ...(this._job.idempotency_key ? { idempotency_key: this._job.idempotency_key } : {}),
    });
    if (!data) return;
    this._apply(data);
    this._toast(pinned ? "Pinned to top" : "Unpinned");
  }

  async _setNotForMe(reason) {
    const curReason = this._job.not_for_me_reason || "";
    if (curReason && curReason === reason) return;
    const data = await this._api(API.notForMe, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      not_for_me: true, reason,
    });
    if (!data) return;
    this._variant = "not_for_me";
    this._apply(data);
    this._toast(`Hidden · ${notForMeReasonMeta(reason).label}`);
  }

  async _restore() {
    const data = await this._api(API.notForMe, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      not_for_me: false,
    });
    if (!data) return;
    this._variant = "open";
    this._apply(data);
    this._toast("Role restored");
  }

  async _reapply() {
    const data = await this._api(API.reapply, {
      country: this._job.country, company: this._job.company, url: this._job.url,
    });
    if (!data) return;
    this._variant = "open";
    this._apply(data);
    this._toast("Moved back to open positions");
  }

  async _saveAtsScore(score) {
    const data = await this._api(API.atsScore, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      ats_score: score,
    });
    if (!data) return;
    this._apply(data);
    this._closeAtsPopover();
    this._toast(score == null ? "ATS score removed" : `ATS score · ${score}`);
  }

  async _saveWaitingReferral(url) {
    const data = await this._api(API.waitingReferral, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      waiting_referral: true, linkedin_url: url,
    });
    if (!data) return;
    this._apply(data);
    this._closeReferralPopover();
    this._toast("Waiting for referral");
  }

  async _clearWaitingReferral() {
    const data = await this._api(API.waitingReferral, {
      country: this._job.country, company: this._job.company, url: this._job.url,
      waiting_referral: false,
    });
    if (!data) return;
    this._apply(data);
    this._closeReferralPopover();
    this._toast("Referral status cleared");
  }

  async _markSeen() {
    const job = this._job;
    const country = (job.country || "").trim();
    const company = (job.company || "").trim();
    const url = (job.url || "").trim();
    if (!country || country === "all" || !company || !url) return;
    const data = await this._api(API.seen, {
      country, company, url, seen: true,
      ...(job.idempotency_key ? { idempotency_key: job.idempotency_key } : {}),
    });
    if (data) this._apply(data);
  }

  // --- Render ---

  render() {
    // Rebuilding innerHTML drops any open popover, so clear the raised stacking.
    this._setRaised(false);
    if (!this._job) { this.innerHTML = ""; return; }
    const v = this._variant;
    if (v === "rejected") this.innerHTML = this._htmlRejected();
    else if (v === "not_for_me") this.innerHTML = this._htmlNotForMe();
    else this.innerHTML = this._htmlOpen();
  }

  _attrRow() {
    const j = this._job;
    return `data-country="${escapeHtml(j.country || "")}" data-company="${escapeHtml(j.company || "")}" data-url="${escapeHtml(j.url || "")}" data-idempotency-key="${escapeHtml(j.idempotency_key || "")}"`;
  }

  _titleRow(job) {
    return `<div class="position-title-row"><a class="job-title" href="${escapeHtml(job.url || "")}" target="_blank" rel="noopener noreferrer">${escapeHtml(job.title || "")}</a>${this._cityBadge(job)}</div>`;
  }

  /** Location badge showing at most CITY_PREVIEW_LIMIT cities, with an
   *  expand/collapse control (mirrors the company card's behaviour). */
  _cityBadge(job) {
    const cities = splitJobCities(job.job_city || job.location || "");
    if (!cities.length) return "";
    const overflow = cities.length > CITY_PREVIEW_LIMIT;
    const shown = this._citiesExpanded || !overflow ? cities : cities.slice(0, CITY_PREVIEW_LIMIT);
    const badge = `<span class="badge job-city">${escapeHtml(shown.join(" · "))}</span>`;
    if (!overflow) return badge;
    const btn = this._citiesExpanded
      ? `<button type="button" class="expand-cities-btn" title="Show fewer locations">Show less</button>`
      : `<button type="button" class="expand-cities-btn" title="Show all locations">+${cities.length - CITY_PREVIEW_LIMIT} more</button>`;
    return badge + btn;
  }

  _htmlOpen() {
    const j = this._job;
    const hist = j.applied_history || [];
    const evts = j.applied_events || [];
    const latest = newestStatusDate(hist, j.applied_date || "");
    const label = formatAppliedLabel({ date: latest, at: j.applied_at || "" });
    const title = formatAppliedHistoryTitle(evts.length ? evts : hist);

    return `<div class="position-card${posCls(j)}" ${this._attrRow()}>
      <div class="position-top">
        <div class="position-head">
          ${this._titleRow(j)}
          <div class="position-badges">
            ${j.visa_sponsorship === true ? '<span class="badge visa">Visa / relocation</span>' : ""}
            ${j.applied ? `<span class="badge applied"${title ? ` title="Applied on: ${escapeHtml(title)}"` : ""}>${escapeHtml(label)}</span>` : ""}
            ${!j.applied && latest ? `<span class="badge applied" title="${escapeHtml(formatAppliedHistoryTitle(evts.length ? evts : hist))}">${escapeHtml(formatAppliedLabel({ date: latest, at: j.applied_at || "" }, { before: true }))}</span>` : ""}
            ${j.waiting_referral && j.referral_linkedin_url ? `<a class="badge referral" href="${escapeHtml(j.referral_linkedin_url)}" target="_blank" rel="noopener noreferrer">Referrer</a>` : j.waiting_referral ? '<span class="badge referral">Waiting referral</span>' : ""}
            ${j.looking_to_apply && !j.applied ? `<span class="badge looking-to-apply">Looking to apply${j.looking_to_apply_date ? ` · ${escapeHtml(j.looking_to_apply_date)}` : ""}</span>` : ""}
            ${j.seen ? `<span class="badge seen">Saw before${j.seen_date ? ` · ${escapeHtml(j.seen_date)}` : ""}</span>` : ""}
            ${cvBadges(j)}
            <span class="badge date">${formatActivityBadge(jobActivityTs(j))}</span>
          </div>
        </div>
        <div class="position-side">${this._pinBtn()}${this._atsWidget()}</div>
      </div>
      <div class="position-actions">
        ${j.applied ? `<button type="button" class="applied-btn active" data-applied="1"${title ? ` title="Applied on: ${escapeHtml(title)}"` : ' title="Clear applied mark"'}>${escapeHtml(label)}</button>`
          : '<button type="button" class="applied-btn" data-applied="0" title="Mark that you applied">I applied</button>'}
        <button type="button" class="rejected-btn" data-rejected="0" title="Mark that you got a rejection">Got rejection</button>
        ${!j.applied ? (j.looking_to_apply
          ? `<button type="button" class="looking-to-apply-btn active" data-looking="1" title="Clear looking-to-apply mark">Looking to apply${j.looking_to_apply_date ? ` · ${escapeHtml(j.looking_to_apply_date)}` : ""}</button>`
          : '<button type="button" class="looking-to-apply-btn" data-looking="0" title="Mark as interested in applying">Looking to apply</button>') : ""}
        ${j.seen ? `<button type="button" class="saw-before-btn active" data-seen="1" title="Clear saw-before mark">Saw before${j.seen_date ? ` · ${escapeHtml(j.seen_date)}` : ""}</button>`
          : '<button type="button" class="saw-before-btn" data-seen="0" title="Mark that you saw this position before">Saw before</button>'}
        ${this._referralTrigger()}
        ${!j.applied ? this._hideReason() : ""}
      </div>
    </div>`;
  }

  _htmlRejected() {
    const j = this._job;
    const rHist = j.rejected_history || [];
    const aHist = j.applied_history || [];
    const aEvts = j.applied_events || [];
    const latestR = newestStatusDate(rHist, j.rejected_date || "");
    const latestA = newestStatusDate(aHist, j.applied_date || "");
    const rLabel = latestR ? `Rejected · ${latestR}` : "Rejected";
    const rTitle = rHist.filter(Boolean).join(", ");
    const aTitle = formatAppliedHistoryTitle(aEvts.length ? aEvts : aHist);

    return `<div class="position-card rejected-role${j.pinned ? " position-pinned" : ""}${j.seen ? " position-seen" : ""}" ${this._attrRow()}>
      <div class="position-top">
        <div class="position-head">
          ${this._titleRow(j)}
          <div class="position-badges">
            <span class="badge rejected"${rTitle ? ` title="Rejected on: ${escapeHtml(rTitle)}"` : ""}>${escapeHtml(rLabel)}</span>
            ${latestA ? `<span class="badge applied"${aTitle ? ` title="${escapeHtml(aTitle)}"` : ""}>${escapeHtml(formatAppliedLabel({ date: latestA, at: j.applied_at || "" }))}</span>` : ""}
            ${j.visa_sponsorship === true ? '<span class="badge visa">Visa / relocation</span>' : ""}
            ${j.seen ? `<span class="badge seen">Saw before${j.seen_date ? ` · ${escapeHtml(j.seen_date)}` : ""}</span>` : ""}
            ${cvBadges(j)}
            <span class="badge date">${formatActivityBadge(jobActivityTs(j))}</span>
          </div>
        </div>
        <div class="position-side">${this._pinBtn()}${this._atsWidget()}</div>
      </div>
      <div class="position-actions">
        <button type="button" class="reapply-btn" title="Return to open positions so you can apply again">Reapply</button>
      </div>
    </div>`;
  }

  _htmlNotForMe() {
    const j = this._job;
    const tagged = j.not_for_me_date ? ` · ${j.not_for_me_date}` : "";
    const { label: hLabel, badgeCls: hBadgeCls } = notForMeReasonMeta(j.not_for_me_reason);

    return `<div class="position-card not-for-me-role${j.pinned ? " position-pinned" : ""}" ${this._attrRow()}>
      <div class="position-top">
        <div class="position-head">
          ${this._titleRow(j)}
          <div class="position-badges">
            <span class="badge ${hBadgeCls}">${escapeHtml(hLabel)}${escapeHtml(tagged)}</span>
            ${j.visa_sponsorship === true ? '<span class="badge visa">Visa / relocation</span>' : ""}
            <span class="badge date">${formatActivityBadge(jobActivityTs(j))}</span>
          </div>
        </div>
        <div class="position-side">${this._pinBtn()}${this._atsWidget()}</div>
      </div>
      <div class="position-actions">
        ${this._hideReason()}
        <button type="button" class="restore-job-btn" title="Move back to applicable roles">Restore</button>
      </div>
    </div>`;
  }

  _pinBtn() {
    const p = Boolean(this._job.pinned);
    return `<button type="button" class="pin-job-btn${p ? " is-pinned" : ""}" title="${p ? "Pinned to top of this company" : "Pin role to top of this company"}" aria-label="${p ? "Pinned in company" : "Pin in company"}" aria-pressed="${p}"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 9V4h1c.55 0 1-.45 1-1s-.45-1-1-1H8c-.55 0-1 .45-1 1s.45 1 1 1h1v5c0 1.66-1.34 3-3 3v2h5.97v7l1.03-1 1.03 1v-7H19v-2c-1.66 0-3-1.34-3-3z"/></svg></button>`;
  }

  _atsWidget() {
    const j = this._job;
    const has = j.ats_score != null && j.ats_score !== "";
    const s = has ? Number(j.ats_score) : 70;
    const tone = has ? atsScoreTone(s) : "";
    return `<div class="ats-score-wrap">
      <button type="button" class="ats-score-trigger${has ? ` ats-has-score ${tone}` : " ats-empty"}" aria-expanded="false" aria-haspopup="dialog" title="${has ? `ATS score ${s} — click to edit` : 'Set ATS resume match score'}">
        ${has ? `<span class="ats-score-ring" style="--ats-pct:${s}"><span class="ats-score-num">${s}</span></span>` : '<span class="ats-score-ring ats-score-ring--empty" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg></span><span class="ats-score-trigger-text">ATS</span>'}
      </button>
      <div class="ats-score-popover" hidden role="dialog" aria-label="ATS score for ${escapeHtml(j.title || "")}" style="position:fixed;z-index:10000">
        <div class="ats-score-popover-head"><span class="ats-score-popover-title">Resume ATS match</span><button type="button" class="ats-score-close" aria-label="Close">×</button></div>
        <div class="ats-score-preview-wrap ${has ? atsScoreTone(s) : "ats-mid"}">
          <div class="ats-score-ring-preview" style="--ats-pct:${s}"><span class="ats-score-preview">${s}</span></div>
          <div class="ats-score-manual"><input type="number" class="ats-score-number" min="0" max="100" step="1" value="${s}" aria-label="ATS score" /><span class="ats-score-manual-unit">/ 100</span></div>
        </div>
        <div class="ats-score-slider-wrap">
          <input type="range" class="ats-score-slider" min="0" max="100" step="1" value="${s}" aria-label="ATS score slider" />
          <div class="ats-score-slider-labels"><span>0</span><span>50</span><span>100</span></div>
        </div>
        <div class="ats-score-quick" role="group" aria-label="Quick scores">
          <button type="button" class="ats-quick-chip" data-score="40">40</button>
          <button type="button" class="ats-quick-chip" data-score="60">60</button>
          <button type="button" class="ats-quick-chip" data-score="75">75</button>
          <button type="button" class="ats-quick-chip" data-score="90">90</button>
        </div>
        <div class="ats-score-popover-foot">
          <button type="button" class="ats-score-save-btn">Save score</button>
          ${has ? '<button type="button" class="ats-score-clear-btn link-btn">Remove score</button>' : ""}
        </div>
      </div>
    </div>`;
  }

  _referralTrigger() {
    const active = Boolean(this._job.waiting_referral);
    const ds = this._job.waiting_referral_date ? ` · ${this._job.waiting_referral_date}` : "";
    return `<div class="referral-wrap">
      <button type="button" class="referral-btn${active ? " active" : ""}" aria-expanded="false" aria-haspopup="dialog" title="${active ? "Edit referrer LinkedIn" : "Waiting for someone to refer you"}">Waiting referral${active ? ds : ""}</button>
    </div>
    <div class="referral-popover" hidden role="dialog" aria-label="Referrer LinkedIn for ${escapeHtml(this._job.title || "")}" style="position:fixed;z-index:10000">
      <div class="referral-popover-head"><span class="referral-popover-title">Referrer LinkedIn</span><button type="button" class="referral-close" aria-label="Close">×</button></div>
      <p class="referral-popover-hint">Profile of the person you asked to refer you.</p>
      <input type="url" class="referral-linkedin-input" placeholder="https://www.linkedin.com/in/username" value="${escapeHtml(this._job.referral_linkedin_url || "")}" spellcheck="false" />
      <div class="referral-popover-foot">
        <button type="button" class="referral-save-btn">Save</button>
        ${active ? '<button type="button" class="referral-clear-btn link-btn">Clear status</button>' : ""}
      </div>
    </div>`;
  }

  _hideReason() {
    const cur = this._job.not_for_me_reason || "";
    const active = cur ? notForMeReasonMeta(cur) : null;
    const tone = active?.badgeCls || "not-for-me";
    const label = active ? active.label : "Not for me";
    const popTitle = cur ? "Change category" : "Why hide this role?";
    return `<div class="hide-reason-wrap" data-current-reason="${escapeHtml(cur)}">
      <button type="button" class="hide-reason-trigger hide-reason-trigger--${tone}" aria-expanded="false" aria-haspopup="menu" title="${cur ? "Change hide category" : "Hide this role"}">${label}<svg class="hide-reason-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>
      <div class="hide-reason-popover" hidden role="menu" aria-label="${popTitle}" style="position:fixed;z-index:10000">
        <p class="hide-reason-popover-title">${popTitle}</p>
        <div class="hide-reason-options">${HIDE_REASONS.map(r => {
          const isCur = Boolean(cur) && r.id === cur;
          return `<button type="button" class="hide-reason-option hide-reason-option--${r.tone}${isCur ? " is-current" : ""}" data-reason="${r.id}" role="menuitem"${isCur ? ' aria-current="true"' : ""}><span class="hide-reason-option-dot" aria-hidden="true"></span><span class="hide-reason-option-text"><span class="hide-reason-option-label">${r.label}</span><span class="hide-reason-option-desc">${r.desc}</span></span></button>`;
        }).join("")}</div>
      </div>
    </div>`;
  }

  // --- Event handlers ---

  _onClick(e) {
    const t = e.target.closest("button, a");
    if (!t) return;

    if (t.closest(".expand-cities-btn")) { e.stopPropagation(); this._citiesExpanded = !this._citiesExpanded; this.render(); return; }

    if (t.closest(".job-title")) { e.stopPropagation(); void this._markSeen(); return; }

    if (t.closest(".pin-job-btn")) { e.stopPropagation(); void this._togglePin(); return; }
    if (t.closest(".applied-btn")) { e.stopPropagation(); void this._toggleApplied(); return; }
    if (t.closest(".rejected-btn")) { e.stopPropagation(); void this._toggleRejected(); return; }
    if (t.closest(".looking-to-apply-btn")) { e.stopPropagation(); void this._toggleLookingToApply(); return; }
    if (t.closest(".saw-before-btn")) { e.stopPropagation(); void this._toggleSeen(); return; }
    if (t.closest(".reapply-btn")) { e.stopPropagation(); void this._reapply(); return; }
    if (t.closest(".restore-job-btn")) { e.stopPropagation(); void this._restore(); return; }

    if (t.closest(".ats-score-trigger")) { e.stopPropagation(); this._toggleAtsPopover(t.closest(".ats-score-wrap")); return; }
    if (t.closest(".ats-score-close")) { e.stopPropagation(); this._closeAtsPopover(); return; }
    if (t.closest(".ats-quick-chip")) { e.stopPropagation(); this._updateAtsPreview(t.closest(".ats-score-wrap"), Number(t.dataset.score)); return; }
    if (t.closest(".ats-score-save-btn")) {
      e.stopPropagation(); const wrap = this.querySelector(".ats-score-wrap"); if (!wrap) return;
      const score = this._readAtsScore(wrap); if (score != null) void this._saveAtsScore(score); return;
    }
    if (t.closest(".ats-score-clear-btn")) { e.stopPropagation(); void this._saveAtsScore(null); return; }
    if (t.closest(".hide-reason-trigger")) { e.stopPropagation(); this._toggleHideReasonPopover(t.closest(".hide-reason-wrap")); return; }
    if (t.closest(".hide-reason-option")) {
      e.stopPropagation(); const wrap = t.closest(".hide-reason-wrap"); const reason = t.dataset.reason;
      if (wrap && reason) void this._setNotForMe(reason); return;
    }
    if (t.closest(".referral-btn")) { e.stopPropagation(); this._toggleReferralPopover(); return; }
    if (t.closest(".referral-close")) { e.stopPropagation(); this._closeReferralPopover(); return; }
    if (t.closest(".referral-save-btn")) {
      e.stopPropagation(); const input = this.querySelector(".referral-linkedin-input"); const val = input?.value?.trim();
      if (!val) { this._toast("Paste the referrer's LinkedIn profile URL"); input?.focus(); return; }
      void this._saveWaitingReferral(val); return;
    }
    if (t.closest(".referral-clear-btn")) { e.stopPropagation(); void this._clearWaitingReferral(); return; }

    if (t.closest(".ats-score-popover, .hide-reason-popover, .referral-popover")) e.stopPropagation();
  }

  _onInput(e) {
    const slider = e.target.closest(".ats-score-slider");
    if (slider) { e.stopPropagation(); this._updateAtsPreview(slider.closest(".ats-score-wrap"), Number(slider.value)); return; }
    const number = e.target.closest(".ats-score-number");
    if (number) {
      e.stopPropagation(); const wrap = number.closest(".ats-score-wrap"); const raw = number.value.trim();
      if (raw !== "") { const parsed = Number(raw); if (Number.isFinite(parsed)) this._updateAtsPreview(wrap, parsed, { skipNumber: true }); }
    }
  }

  _onChange(e) {
    const number = e.target.closest(".ats-score-number");
    if (number) { e.stopPropagation(); this._updateAtsPreview(number.closest(".ats-score-wrap"), Number(number.value)); }
  }

  _onKeydown(e) {
    if (e.key !== "Enter") return;
    const number = e.target.closest(".ats-score-number");
    if (!number) return;
    e.preventDefault(); e.stopPropagation();
    const wrap = number.closest(".ats-score-wrap"); if (!wrap) return;
    const score = this._readAtsScore(wrap);
    if (score == null) { this._toast("ATS score must be a whole number 0–100"); number.focus(); return; }
    void this._saveAtsScore(score);
  }

  // --- Popover management ---

  _toggleAtsPopover(wrap) {
    if (!wrap) return;
    const popover = wrap.querySelector(".ats-score-popover");
    const trigger = wrap.querySelector(".ats-score-trigger");
    if (!popover || !trigger) return;
    const open = popover.hidden;
    this._closeAllPopovers(open ? wrap : null);
    if (open) {
      document.dispatchEvent(new CustomEvent("position-card-popover-open"));
      popover.hidden = false;
      this._positionPopover(popover, trigger);
      popover.querySelector(".ats-score-slider")?.focus();
    }
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
  }

  _closeAtsPopover() {
    this.querySelectorAll(".ats-score-popover").forEach(p => p.hidden = true);
    this.querySelectorAll(".ats-score-trigger").forEach(t => t.setAttribute("aria-expanded", "false"));
    this._setRaised(false);
  }

  _updateAtsPreview(wrap, score, opts) {
    const v = Math.max(0, Math.min(100, Number(score) || 0));
    const pop = wrap?.querySelector(".ats-score-popover");
    if (!pop) return v;
    const preview = pop.querySelector(".ats-score-preview");
    const ring = pop.querySelector(".ats-score-ring-preview");
    const pw = pop.querySelector(".ats-score-preview-wrap");
    const slider = pop.querySelector(".ats-score-slider");
    const number = pop.querySelector(".ats-score-number");
    if (preview) preview.textContent = String(v);
    if (ring) ring.style.setProperty("--ats-pct", String(v));
    if (pw) { pw.classList.remove("ats-high", "ats-mid", "ats-low"); pw.classList.add(atsScoreTone(v)); }
    if (!opts?.skipSlider && slider && Number(slider.value) !== v) slider.value = String(v);
    if (!opts?.skipNumber && number && document.activeElement !== number) number.value = String(v);
    pop.querySelectorAll(".ats-quick-chip").forEach(chip => chip.classList.toggle("is-active", Number(chip.dataset.score) === v));
    return v;
  }

  _readAtsScore(wrap) {
    const pop = wrap?.querySelector(".ats-score-popover");
    if (!pop) return null;
    const number = pop.querySelector(".ats-score-number");
    const slider = pop.querySelector(".ats-score-slider");
    const raw = (number?.value ?? "").trim();
    if (raw !== "") {
      const parsed = Number(raw);
      if (!Number.isInteger(parsed) || parsed < 0 || parsed > 100) return null;
      return parsed;
    }
    return this._updateAtsPreview(wrap, slider?.value ?? 0);
  }

  _toggleHideReasonPopover(wrap) {
    if (!wrap) return;
    const popover = wrap.querySelector(".hide-reason-popover");
    const trigger = wrap.querySelector(".hide-reason-trigger");
    if (!popover || !trigger) return;
    const open = popover.hidden;
    this._closeAllPopovers(open ? wrap : null);
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      popover.hidden = false;
      this._positionPopover(popover, trigger);
    }
  }

  _closeHideReasonPopover() {
    this.querySelectorAll(".hide-reason-popover").forEach(p => p.hidden = true);
    this.querySelectorAll(".hide-reason-trigger").forEach(t => t.setAttribute("aria-expanded", "false"));
    this._setRaised(false);
  }

  _toggleReferralPopover() {
    const popover = this.querySelector(".referral-popover");
    const trigger = this.querySelector(".referral-btn");
    if (!popover || !trigger) return;
    const open = popover.hidden;
    this._closeAllPopovers();
    trigger.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      popover.hidden = false;
      this._positionPopover(popover, trigger);
      popover.querySelector(".referral-linkedin-input")?.focus();
    }
  }

  _closeReferralPopover() {
    const pop = this.querySelector(".referral-popover");
    const trig = this.querySelector(".referral-btn");
    if (pop) pop.hidden = true;
    if (trig) trig.setAttribute("aria-expanded", "false");
    this._setRaised(false);
  }

  _closeAllPopovers(except) {
    this._closeAtsPopover();
    this._closeHideReasonPopover();
    this._closeReferralPopover();
  }

  _positionPopover(popover, trigger) {
    if (!popover || !trigger) return;
    const tr = trigger.getBoundingClientRect();
    const pr = popover.getBoundingClientRect();
    const gap = 8;
    const m = 12;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let top = tr.bottom + gap;
    if (top + pr.height > vh - m) top = tr.top - pr.height - gap;
    if (top < m) top = m;
    if (top + pr.height > vh - m) top = vh - pr.height - m;
    let left = tr.left;
    if (left + pr.width > vw - m) left = vw - pr.width - m;
    left = Math.max(m, left);
    popover.style.top = `${Math.round(top)}px`;
    popover.style.left = `${Math.round(left)}px`;
    popover.classList.add("is-floating");
    this._setRaised(true);
    this._addCloseOnScroll();
  }

  /** Close popovers on first scroll so the position:fixed popover doesn't
   *  float disconnected from its trigger. */
  _addCloseOnScroll() {
    this._removeCloseOnScroll();
    this._closeOnScrollHandler = () => { this._closeAllPopovers(); };
    window.addEventListener("scroll", this._closeOnScrollHandler, { once: true, passive: true });
  }

  _removeCloseOnScroll() {
    if (this._closeOnScrollHandler) {
      window.removeEventListener("scroll", this._closeOnScrollHandler);
      this._closeOnScrollHandler = null;
    }
  }

  /** Lift this card and its company above siblings while a popover is open.
   *  Dimmed cards (.position-seen use opacity < 1) create a stacking context
   *  that traps the popover's z-index behind later siblings. We target the
   *  inner .position-card (which carries the opacity SC) so the SC itself
   *  gets positioned above siblings.  We also raise the .company-card so
   *  the popover doesn't fall behind the *next* company card. */
  _setRaised(on) {
    const inner = this.querySelector(".position-card");
    if (inner) {
      inner.style.position = on ? "relative" : "";
      inner.style.zIndex = on ? "10000" : "";
    }
    // company-card already has position:relative from CSS
    const cc = this.closest(".company-card");
    if (cc) {
      cc.style.zIndex = on ? "10000" : "";
    }
    if (!on) this._removeCloseOnScroll();
  }
}

customElements.define("position-card", PositionCard);

export default PositionCard;
