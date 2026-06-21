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
