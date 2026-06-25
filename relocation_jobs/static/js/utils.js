/** DOM helpers and small UI utilities. */

export const $ = (id) => document.getElementById(id);

export function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

export function escapeAttr(s) {
  return String(s).replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

export function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3500);
}

export const SEARCH_DEBOUNCE_MS = 450;

export function debounce(fn, waitMs = 200) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), waitMs);
  };
}

export function browserTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function formatLocalDateTime(ts) {
  const value = (ts || "").trim();
  if (!value) return "";

  const cleaned = value.replace(/\.\d+(?=[Z+-]|$)/, "");
  const parsed = new Date(cleaned.includes("T") ? cleaned : `${cleaned}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    return value.split(/[T+]/)[0] || value;
  }

  const pad = (n) => String(n).padStart(2, "0");
  const date = `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`;
  if (!/[T ]\d{2}:\d{2}/.test(value) && value.length === 10) return date;
  return `${date} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

export function formatAppliedLabel({ date = "", at = "" } = {}, { before = false } = {}) {
  const prefix = before ? "Applied before" : "Applied";
  const stamp = formatLocalDateTime(at || date);
  if (!stamp) return prefix;
  return `${prefix} · ${stamp}`;
}

export function formatAppliedHistoryTitle(events = []) {
  const list = (events || [])
    .map((entry) => {
      if (entry && typeof entry === "object") {
        return formatLocalDateTime(entry.at || entry.date || "");
      }
      return formatLocalDateTime(entry);
    })
    .filter(Boolean);
  if (!list.length) return "";
  return `Applied on: ${list.join(", ")}`;
}

export function formatActivityBadge(ts) {
  const value = (ts || "").trim();
  if (!value) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const cleaned = value.replace(/\.\d+(?=[Z+-]|$)/, "");
  const parsed = new Date(cleaned.includes("T") ? cleaned : `${cleaned}T00:00:00`);
  if (!Number.isNaN(parsed.getTime())) {
    const pad = (n) => String(n).padStart(2, "0");
    const date = `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}`;
    if (!/[T ]\d{2}:\d{2}/.test(value)) return date;
    return `${date} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
  }
  const match = value.match(/^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))/);
  if (match) return `${match[1]} ${match[2]}`;
  return value.split(/[T+]/)[0] || value;
}

export function formatFetchDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (total < 60) return `${total}s`;
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  if (mins < 60) return secs ? `${mins}m ${secs}s` : `${mins}m`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins ? `${hours}h ${remMins}m` : `${hours}h`;
}

export function parseFetchTimestamp(ts) {
  const value = (ts || "").trim();
  if (!value) return null;
  const cleaned = value.replace(/\.\d+(?=[Z+-]|$)/, "").replace(/Z$/, "+00:00");
  const parsed = new Date(cleaned.includes("T") ? cleaned : `${cleaned}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function elapsedSecondsBetween(startedAt, finishedAt) {
  const start = parseFetchTimestamp(startedAt);
  const finish = parseFetchTimestamp(finishedAt);
  if (!start || !finish) return null;
  return Math.max(0, Math.round((finish.getTime() - start.getTime()) / 1000));
}

export function elapsedSecondsSince(startedAt) {
  const start = parseFetchTimestamp(startedAt);
  if (!start) return null;
  return Math.max(0, Math.round((Date.now() - start.getTime()) / 1000));
}

export function atsScoreTone(score) {
  if (score >= 80) return "ats-high";
  if (score >= 60) return "ats-mid";
  return "ats-low";
}

import { beginScreenLoad, endScreenLoad, isScreenLoadActive, setScreenLoadProgress } from "./screen-loader.js";

export function setLoadingProgress(pct) {
  if (isScreenLoadActive()) {
    setScreenLoadProgress(pct);
    return;
  }
  const fill = document.getElementById("loadingBarFill");
  const bar = document.getElementById("loadingBar");
  if (!fill || !bar) return;
  bar.classList.remove("done");
  fill.style.opacity = "1";
  const current = parseFloat(fill.style.width) || 0;
  fill.style.width = `${Math.max(current, pct)}%`;
}

export function finishLoadingProgress() {
  if (isScreenLoadActive()) {
    endScreenLoad();
    return;
  }
  const fill = document.getElementById("loadingBarFill");
  const bar = document.getElementById("loadingBar");
  if (!fill || !bar) return;
  fill.style.width = "100%";
  setTimeout(() => bar.classList.add("done"), 380);
}

const NARROW_VIEWPORT = window.matchMedia("(max-width: 720px)");

export function isNarrowViewport() {
  return NARROW_VIEWPORT.matches;
}

let bodyScrollLockCount = 0;

export function lockBodyScroll() {
  bodyScrollLockCount += 1;
  if (bodyScrollLockCount === 1) {
    document.body.classList.add("scroll-locked");
  }
}

export function unlockBodyScroll() {
  bodyScrollLockCount = Math.max(0, bodyScrollLockCount - 1);
  if (bodyScrollLockCount === 0) {
    document.body.classList.remove("scroll-locked");
  }
}
