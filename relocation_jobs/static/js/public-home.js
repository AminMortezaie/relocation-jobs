function formatNumber(value) {
  return new Intl.NumberFormat("en").format(Number(value) || 0);
}

function text(value, fallback = "-") {
  return value || fallback;
}

let previewCompanies = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function matchesSearch(company, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    company.name,
    company.country,
    company.country_label,
    company.city,
    ...(company.preview_jobs || []).map((job) => job.title),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

function renderOverview(payload) {
  const totals = payload.totals || {};
  const countries = payload.countries || [];
  const countryMeta = payload.country_meta || [];

  document.getElementById("statCompanies").textContent = formatNumber(totals.companies);
  document.getElementById("statJobs").textContent = formatNumber(totals.jobs);
  document.getElementById("statVisaJobs").textContent = formatNumber(totals.visa_jobs);
  document.getElementById("statCountries").textContent = formatNumber(countries.length);

  const metaByCountry = new Map(countryMeta.map((row) => [row.country, row]));
  const grid = document.getElementById("countryGrid");
  grid.innerHTML = "";

  for (const row of countries) {
    const meta = metaByCountry.get(row.country) || {};
    const card = document.createElement("article");
    card.className = "country-card";
    card.innerHTML = `
      <h3>${text(row.label, row.country)}</h3>
      <p class="country-meta">
        ${formatNumber(row.companies)} companies<br />
        ${formatNumber(row.jobs)} open roles<br />
        ${formatNumber(row.visa_jobs)} visa-friendly roles<br />
        Latest job seen: ${text(meta.latest_job_fetch, "n/a")}
      </p>
    `;
    grid.appendChild(card);
  }
}

function renderPreview(companies) {
  const grid = document.getElementById("previewGrid");
  grid.innerHTML = "";

  if (!companies.length) {
    grid.innerHTML = '<div class="empty-state">No companies match this preview search yet.</div>';
    return;
  }

  for (const company of companies) {
    const jobs = company.preview_jobs || [];
    const list = jobs.length
      ? `<ul class="job-list">${jobs.map((job) => `<li>${escapeHtml(text(job.title))}</li>`).join("")}</ul>`
      : '<p class="preview-meta">No sample roles published for this company yet.</p>';
    const visaClass = company.visa_job_count > 0 ? "pill pill-success" : "pill";
    const visaLabel = company.visa_job_count > 0
      ? `${formatNumber(company.visa_job_count)} visa roles`
      : "Preview";
    const locationLabel = company.city ? escapeHtml(company.city) : "Location signal pending";
    const card = document.createElement("article");
    card.className = "preview-card";
    card.innerHTML = `
      <div class="card-topline">
        <strong class="preview-title">${escapeHtml(text(company.name))}</strong>
        <span class="${visaClass}">${visaLabel}</span>
      </div>
      <div class="preview-subline">
        <span class="surface-chip">${escapeHtml(text(company.country_label, company.country))}</span>
        <span class="surface-chip surface-chip-muted">${locationLabel}</span>
      </div>
      <p class="preview-meta">
        ${formatNumber(company.job_count)} open roles<br />
        Latest fetch: ${text(company.latest_fetched, "n/a")}
      </p>
      ${list}
      <div class="preview-footer">
        <a class="preview-link" href="/">Open private workspace</a>
      </div>
    `;
    grid.appendChild(card);
  }
}

function applyPreviewSearch(query) {
  const filtered = previewCompanies.filter((company) => matchesSearch(company, query));
  renderPreview(filtered);
}

function bindPreviewSearch() {
  const form = document.getElementById("previewSearchForm");
  const input = document.getElementById("previewSearchInput");
  if (!form || !input) return;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    applyPreviewSearch(input.value);
  });
  input.addEventListener("input", () => {
    applyPreviewSearch(input.value);
  });
}

async function loadPublicData() {
  const [overviewRes, previewRes] = await Promise.all([
    fetch("/api/public/overview"),
    fetch("/api/public/preview"),
  ]);

  if (!overviewRes.ok || !previewRes.ok) {
    throw new Error("Failed to load public data");
  }

  const overview = await overviewRes.json();
  const preview = await previewRes.json();
  renderOverview(overview);
  previewCompanies = preview.companies || [];
  renderPreview(previewCompanies);
}

bindPreviewSearch();

loadPublicData().catch(() => {
  document.getElementById("countryGrid").innerHTML =
    '<div class="empty-state">Public catalog data is temporarily unavailable.</div>';
  document.getElementById("previewGrid").innerHTML =
    '<div class="empty-state">Preview data is temporarily unavailable.</div>';
});
