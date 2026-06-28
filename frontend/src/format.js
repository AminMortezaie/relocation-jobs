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

export function atsScoreTone(score) {
  if (score >= 80) return "ats-high";
  if (score >= 60) return "ats-mid";
  return "ats-low";
}

export function newestStatusDate(dates, fallback = "") {
  const list = (dates || []).filter(Boolean).map((d) => String(d).trim()).filter(Boolean);
  const fb = (fallback || "").trim();
  if (fb) list.push(fb);
  list.sort();
  return list.length ? list[list.length - 1] : "";
}

export function jobActivityTs(job) {
  return (job?.fetched || job?.last_seen || "").trim();
}

export function companyActivityTs(company) {
  return (company?.newest_job_fetched || company?.latest_fetched || "").trim();
}
