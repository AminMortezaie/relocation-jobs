/** Shared stats dashboard markup (main panel legacy + admin panel). */

function statCard(value, label, { escapeHtml, accent = false, muted = false } = {}) {
  const valueCls = [
    accent ? " stat-value--accent" : "",
    muted ? " stat-value--muted" : "",
  ].join("");
  return `
    <div class="stat">
      <div class="value${valueCls}">${value}</div>
      <div class="label">${escapeHtml(label)}</div>
    </div>
  `;
}

export function buildStatsDashboardHtml(stats, { escapeHtml, formatActivityBadge }) {
  const appliedToday = stats.applied_today_jobs || [];
  const appliedTodayDetail = appliedToday.length
    ? `<ul class="stats-applied-today-list">${appliedToday.map((job) => `
        <li>
          <span class="stats-applied-today-company">${escapeHtml(job.company || "Company")}</span>
          ${job.title ? `<span class="stats-applied-today-title">${escapeHtml(job.title)}</span>` : ""}
        </li>`).join("")}</ul>`
    : `<p class="stats-applied-today-empty">No applications recorded today.</p>`;

  return `
    <div class="stats-dashboard">
      <section class="stats-group">
        <div class="stats-row">
          ${statCard(stats.total_jobs, "Open roles", { escapeHtml, accent: true })}
          ${statCard(stats.companies_with_jobs, "Companies", { escapeHtml })}
          ${statCard(stats.latest_fetch_new_jobs ?? 0, "New last fetch", { escapeHtml })}
          ${statCard(escapeHtml(formatActivityBadge(stats.latest_job_fetch || "")) || "—", "Last fetch", { escapeHtml, muted: true })}
        </div>
      </section>
      <section class="stats-group">
        <div class="stats-row">
          <div class="stat stat-applied-today">
            <div class="value stat-value--accent">${stats.positions_applied_today ?? 0}</div>
            <div class="label">Applied today</div>
            ${appliedTodayDetail}
          </div>
          ${statCard(stats.positions_applied ?? 0, "Applied total", { escapeHtml })}
          ${statCard(stats.applied ?? 0, "Companies applied", { escapeHtml })}
          ${statCard(stats.positions_rejected ?? 0, "Rejections", { escapeHtml })}
          ${statCard(stats.not_for_me ?? 0, "Hidden", { escapeHtml })}
          ${statCard(stats.visa_sponsored, "Visa / relocation", { escapeHtml })}
          ${statCard(stats.fetch_problems ?? 0, "Fetch issues", { escapeHtml })}
        </div>
      </section>
    </div>
  `;
}
