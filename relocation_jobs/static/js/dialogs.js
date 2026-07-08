/** Add-company and edit-careers dialogs. */

import { state } from "./state.js";
import { $, escapeAttr, escapeHtml, toast } from "./utils.js";
import { addCompany, updateCareersUrl, updateCompanyCity, updateCompanyName, fetchAtsTypes, addCustomLocation, addCustomCountry } from "./api.js";
import { loadJobs, loadCities, getCachedAtsTypes, loadPickerLocations, invalidatePickerLocationsCache } from "./data.js";
import { migrateCompanyKeyInState } from "./storage.js";

function getAddCompanyCountryOptions() {
  return [...$("country").options]
    .map((option) => ({ id: option.value, label: option.textContent.trim() }))
    .filter((country) => country.id !== "all");
}

let addCompanyPickerLocations = [];

export function populateAddCompanyCountryPicker({ force = false } = {}) {
  const container = $("addCompanyCountryOptions");
  if (!container) return;
  if (!force && container.dataset.ready === "1") return;

  container.innerHTML = getAddCompanyCountryOptions()
    .map(
      (country) => `
        <button
          type="button"
          class="country-chip"
          data-value="${escapeHtml(country.id)}"
          aria-pressed="false"
        >${escapeHtml(country.label)}</button>`
    )
    .join("");
  container.dataset.ready = "1";
}

function renderAddCompanyAtsOptions(types) {
  const container = $("addCompanyAtsOptions");
  if (!container) return;

  container.innerHTML = [
    `<button
      type="button"
      class="country-chip country-chip--auto"
      data-value="auto"
      aria-pressed="false"
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/><path d="M19 3v4M21 5h-4"/>
      </svg>
      Auto-detect
    </button>`,
    ...types
      .filter((item) => item?.id)
      .map(
        (item) => `
        <button
          type="button"
          class="country-chip"
          data-value="${escapeAttr(item.id)}"
          aria-pressed="false"
        >${escapeHtml(item.label || item.id)}</button>`
      ),
  ].join("");
  setAddCompanyAts(getAddCompanyAts());
}

export async function populateAddCompanyAtsPicker() {
  const container = $("addCompanyAtsOptions");
  if (!container) return;

  let types = getCachedAtsTypes();
  if (!types.length) {
    types = await fetchAtsTypes();
    if (types.length) state.atsTypes = types;
  }
  renderAddCompanyAtsOptions(types);
}

function setAddCompanyAts(value) {
  const next = String(value ?? "").trim() || "auto";
  if ($("addCompanyAts")) $("addCompanyAts").value = next;
  const autoBtn = $("addCompanyAtsAutoBtn");
  if (autoBtn) autoBtn.hidden = next === "auto";
  document.querySelectorAll("#addCompanyForm .add-company-ats-chips .country-chip").forEach((chip) => {
    const chipValue = chip.getAttribute("data-value") ?? "";
    const selected = chipValue === next;
    chip.classList.toggle("is-selected", selected);
    chip.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  updateAddCompanyAtsSummary();
}

function handleAddCompanyAtsChipClick(e) {
  const chip = e.target.closest(".add-company-ats-chips .country-chip");
  if (!chip || !chip.hasAttribute("data-value")) return;
  const value = chip.getAttribute("data-value");
  if (value == null || value === "") return;
  setAddCompanyAts(value);
}

function getAddCompanyAtsLabel(value = getAddCompanyAts()) {
  if (value === "auto") return "Auto-detect";
  const chip = document.querySelector(
    `#addCompanyForm .add-company-ats-chips .country-chip[data-value="${CSS.escape(value)}"]`
  );
  return chip?.textContent.trim() || value;
}

function updateAddCompanyAtsSummary() {
  const summary = $("addCompanyAtsSummary");
  if (summary) summary.textContent = getAddCompanyAtsLabel();
}

function getAddCompanyCountryLabels() {
  const options = getAddCompanyCountryOptions();
  const byId = new Map(options.map((item) => [item.id, item.label]));
  return getAddCompanySelectedCountries().map((id) => byId.get(id) || id);
}

function updateAddCompanyCountrySummary() {
  const summary = $("addCompanyCountrySummary");
  if (!summary) return;
  if (isAddCompanyCountryAuto()) {
    summary.textContent = "Auto from URL";
    return;
  }
  const labels = getAddCompanyCountryLabels();
  summary.textContent = labels.length ? labels.join(", ") : "Auto from URL";
}

function updateAddCompanyLocationsSummary() {
  const summary = $("addCompanyLocationsSummary");
  if (!summary) return;
  const locations = getAddCompanyLocations();
  if (!locations.length) {
    summary.textContent = "None selected";
    return;
  }
  const labels = locations.map((loc) => loc.label || `${loc.city} (${formatCountryLabel(loc.country)})`);
  summary.textContent = labels.length <= 3
    ? labels.join(", ")
    : `${labels.slice(0, 2).join(", ")} +${labels.length - 2} more`;
}

function setAddCompanyAccordionExpanded(itemId, expanded) {
  const item = $(itemId);
  if (!item) return;
  const trigger = item.querySelector(".add-company-accordion-trigger");
  const panel = item.querySelector(".add-company-accordion-panel");
  if (!trigger || !panel) return;
  trigger.setAttribute("aria-expanded", expanded ? "true" : "false");
  panel.hidden = !expanded;
}

function toggleAddCompanyAccordion(itemId) {
  const item = $(itemId);
  if (!item || item.hidden) return;
  const trigger = item.querySelector(".add-company-accordion-trigger");
  const expanded = trigger?.getAttribute("aria-expanded") === "true";
  const willExpand = !expanded;
  setAddCompanyAccordionExpanded(itemId, willExpand);
  if (willExpand && itemId === "addCompanyLocationsAccordion") {
    void loadAddCompanyLocationsWhenNeeded();
  }
}

function collapseAllAddCompanyAccordions() {
  setAddCompanyAccordionExpanded("addCompanyAtsAccordion", false);
  setAddCompanyAccordionExpanded("addCompanyCountryAccordion", false);
  setAddCompanyAccordionExpanded("addCompanyLocationsAccordion", false);
}

function getAddCompanySelectedCountries() {
  const panel = document.querySelector("#addCompanyForm .add-company-country-chips");
  if (!panel) return [];
  return [...panel.querySelectorAll(".country-chip.is-selected")]
    .map((chip) => chip.dataset.value)
    .filter(Boolean);
}

function isAddCompanyCountryAuto() {
  return ($("addCompanyCountryMode")?.value || "auto") === "auto";
}

function getAddCompanyAts() {
  return ($("addCompanyAts")?.value || "auto").trim() || "auto";
}

function syncAddCompanyCountryUi() {
  const auto = isAddCompanyCountryAuto();
  const selected = getAddCompanySelectedCountries();
  const autoBtn = $("addCompanyCountryAutoBtn");
  if (autoBtn) {
    autoBtn.hidden = auto;
  }
  document.querySelectorAll("#addCompanyForm .add-company-country-chips .country-chip").forEach((chip) => {
    const isSelected = !auto && selected.includes(chip.dataset.value);
    chip.classList.toggle("is-selected", isSelected);
    chip.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
  const locationsAccordion = $("addCompanyLocationsAccordion");
  if (locationsAccordion) {
    locationsAccordion.hidden = auto || selected.length === 0;
    if (locationsAccordion.hidden) {
      setAddCompanyAccordionExpanded("addCompanyLocationsAccordion", false);
    }
  }
  updateAddCompanyCountrySummary();
  updateAddCompanyLocationsSummary();
}

function setAddCompanyCountryAuto() {
  if ($("addCompanyCountryMode")) $("addCompanyCountryMode").value = "auto";
  setAddCompanyLocations([]);
  syncAddCompanyCountryUi();
  renderAddCompanyLocationOptions();
}

function toggleAddCompanyCountry(chip) {
  const country = chip.dataset.value;
  if (!country) return;

  if ($("addCompanyCountryMode")) $("addCompanyCountryMode").value = "manual";
  const selected = new Set(getAddCompanySelectedCountries());
  if (selected.has(country)) {
    selected.delete(country);
  } else {
    selected.add(country);
  }

  if (!selected.size) {
    setAddCompanyCountryAuto();
    return;
  }

  document.querySelectorAll("#addCompanyForm .add-company-country-chips .country-chip").forEach((option) => {
    const isSelected = selected.has(option.dataset.value);
    option.classList.toggle("is-selected", isSelected);
    option.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });

  pruneAddCompanyLocations(selected);
  syncAddCompanyCountryUi();
  renderAddCompanyLocationOptions();
}

function setAddCompanyCountries(countries) {
  const list = Array.isArray(countries) ? countries.filter(Boolean) : [];
  if (!list.length) {
    setAddCompanyCountryAuto();
    return;
  }
  if ($("addCompanyCountryMode")) $("addCompanyCountryMode").value = "manual";
  const allowed = new Set(getAddCompanyCountryOptions().map((c) => c.id));
  const selected = list.filter((id) => allowed.has(id));
  if (!selected.length) {
    setAddCompanyCountryAuto();
    return;
  }
  document.querySelectorAll("#addCompanyForm .add-company-country-chips .country-chip").forEach((chip) => {
    const isSelected = selected.includes(chip.dataset.value);
    chip.classList.toggle("is-selected", isSelected);
    chip.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
  syncAddCompanyCountryUi();
  renderAddCompanyLocationOptions();
}

function getAddCompanyLocations() {
  try {
    return normalizeLocationList(JSON.parse($("addCompanyLocationsValue")?.value || "[]"));
  } catch {
    return [];
  }
}

function setAddCompanyLocations(selectedLocations) {
  const selected = normalizeLocationList(selectedLocations);
  if ($("addCompanyLocationsValue")) {
    $("addCompanyLocationsValue").value = JSON.stringify(
      selected.map((loc) => ({ country: loc.country, city: loc.city }))
    );
  }
  const picker = document.querySelector("#addCompanyForm .add-company-location-chips");
  if (!picker) return;
  const selectedKeys = new Set(selected.map((loc) => locationSelectionKey(loc)));
  picker.querySelectorAll(".country-chip[data-location-key]").forEach((chip) => {
    const isSelected = selectedKeys.has(locationKeyFromChip(chip));
    chip.classList.toggle("is-selected", isSelected);
    chip.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
  updateAddCompanyLocationsSummary();
  updateAddCompanyLocationGroupMeta();
}

function pruneAddCompanyLocations(selectedCountries) {
  const allowed = selectedCountries instanceof Set ? selectedCountries : new Set(selectedCountries);
  const kept = getAddCompanyLocations().filter((loc) => allowed.has(loc.country));
  setAddCompanyLocations(kept);
}

function toggleAddCompanyLocationChip(chip) {
  const selected = getAddCompanyLocations();
  const key = locationKeyFromChip(chip);
  const idx = selected.findIndex((loc) => locationSelectionKey(loc) === key);
  if (idx >= 0) {
    setAddCompanyLocations(selected.filter((loc) => locationSelectionKey(loc) !== key));
  } else {
    selected.push({
      country: chip.dataset.country,
      city: chip.dataset.city,
      key: chip.dataset.locationKey,
      label: chip.textContent.trim(),
    });
    setAddCompanyLocations(selected);
  }
  updateAddCompanyLocationGroupMeta();
}

function getAddCompanyLocationFilter() {
  return ($("addCompanyLocationSearch")?.value || "").trim().toLowerCase();
}

function locationMatchesFilter(loc, filter) {
  if (!filter) return true;
  const hay = [
    loc.label,
    loc.city,
    loc.country_label,
    loc.country,
  ].filter(Boolean).join(" ").toLowerCase();
  return hay.includes(filter);
}

function slugifyGroupId(label) {
  return (label || "group").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function updateAddCompanyLocationGroupMeta() {
  document.querySelectorAll("#addCompanyForm .add-company-location-group").forEach((group) => {
    const meta = group.querySelector(".add-company-location-group-meta");
    const country = group.dataset.country;
    if (!meta || !country) return;
    const selectedInCountry = getAddCompanyLocations().filter(
      (loc) => loc.country === country
    ).length;
    const chipCount = group.querySelectorAll(".country-chip[data-location-key]").length;
    if (selectedInCountry) {
      meta.textContent = `${selectedInCountry} selected`;
    } else {
      meta.textContent = chipCount ? `${chipCount} cities` : "Add a city";
    }
  });
}

function toggleAddCompanyLocationGroup(trigger) {
  const panel = trigger.nextElementSibling;
  if (!panel) return;
  const expanded = trigger.getAttribute("aria-expanded") === "true";
  trigger.setAttribute("aria-expanded", expanded ? "false" : "true");
  panel.hidden = expanded;
}

function renderAddCompanyLocationOptions() {
  const container = $("addCompanyLocationOptions");
  if (!container) return;

  const selectedCountries = getAddCompanySelectedCountries();
  if (isAddCompanyCountryAuto() || !selectedCountries.length) {
    container.innerHTML = "";
    updateAddCompanyLocationsSummary();
    return;
  }

  const filter = getAddCompanyLocationFilter();
  const allowed = new Set(selectedCountries);
  const options = addCompanyPickerLocations.filter((loc) => allowed.has(loc.country));
  const selectedKeys = new Set(getAddCompanyLocations().map((loc) => locationSelectionKey(loc)));

  container.innerHTML = selectedCountries.map((countryId) => {
    const locs = options.filter((loc) => loc.country === countryId);
    const groupLabel = locs[0]?.country_label || formatCountryLabel(countryId);
    const filtered = locs.filter((loc) => locationMatchesFilter(loc, filter));
    const selectedInGroup = getAddCompanyLocations().filter(
      (loc) => loc.country === countryId
    ).length;
    const groupId = `addCompanyLocGroup-${slugifyGroupId(countryId)}`;
    const autoExpand = Boolean(filter) || selectedInGroup > 0;
    const metaText = selectedInGroup
      ? `${selectedInGroup} selected`
      : (filtered.length ? `${filtered.length} cities` : "Add a city");

    const chipsHtml = filtered.map((loc) => {
      const isSelected = selectedKeys.has(locationSelectionKey(loc));
      return `
        <button
          type="button"
          class="country-chip${isSelected ? " is-selected" : ""}"
          data-location-key="${escapeAttr(loc.key)}"
          data-country="${escapeAttr(loc.country)}"
          data-city="${escapeAttr(loc.city)}"
          aria-pressed="${isSelected ? "true" : "false"}"
        >${escapeHtml(loc.label || loc.city)}</button>
      `;
    }).join("");

    return `
      <div class="add-company-location-group" data-country="${escapeAttr(countryId)}">
        <button
          type="button"
          class="add-company-location-group-trigger"
          aria-expanded="${autoExpand ? "true" : "false"}"
          aria-controls="${escapeAttr(groupId)}"
        >
          <span class="add-company-location-group-label">${escapeHtml(groupLabel)}</span>
          <span class="add-company-location-group-meta">${escapeHtml(metaText)}</span>
          <svg class="add-company-accordion-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="m6 9 6 6 6-6"/>
          </svg>
        </button>
        <div class="add-company-location-group-panel" id="${escapeAttr(groupId)}" ${autoExpand ? "" : "hidden"}>
          ${chipsHtml ? `<div class="country-chips-list">${chipsHtml}</div>` : ""}
          ${renderCustomCityAddRow(countryId, groupLabel)}
        </div>
      </div>
    `;
  }).join("");

  updateAddCompanyLocationsSummary();
}

async function ensureAddCompanyPickerLocations() {
  if (!addCompanyPickerLocations.length) {
    addCompanyPickerLocations = await loadPickerLocations();
  }
}

async function loadAddCompanyLocationsWhenNeeded() {
  const container = $("addCompanyLocationOptions");
  if (!container) return;
  if (addCompanyPickerLocations.length) {
    renderAddCompanyLocationOptions();
    return;
  }
  container.innerHTML = `<p class="text-muted">Loading cities…</p>`;
  try {
    await ensureAddCompanyPickerLocations();
    renderAddCompanyLocationOptions();
  } catch {
    container.innerHTML = `<p class="text-muted">Could not load cities</p>`;
  }
}

export function openAddCompanyDialog() {
  populateAddCompanyCountryPicker();
  $("addCompanyName").value = "";
  $("addCompanyUrl").value = "";
  if ($("addCompanyLocationSearch")) $("addCompanyLocationSearch").value = "";
  if ($("addCompanyAts")) setAddCompanyAts("auto");
  setAddCompanyLocations([]);
  collapseAllAddCompanyAccordions();
  const panelCountry = $("country").value;
  if (panelCountry && panelCountry !== "all") {
    setAddCompanyCountries([panelCountry]);
  } else {
    setAddCompanyCountryAuto();
  }
  updateAddCompanyAtsSummary();
  $("addCompanyDialog").classList.add("open");
  $("addCompanyDialog").setAttribute("aria-hidden", "false");
  $("addCompanyName").focus();
  void populateAddCompanyAtsPicker();
}

export function closeAddCompanyDialog() {
  $("addCompanyDialog").classList.remove("open");
  $("addCompanyDialog").setAttribute("aria-hidden", "true");
  resetAddCompanySubmit();
}

function setAddCompanySubmitLoading(loading) {
  const btn = $("addCompanySubmit");
  const label = $("addCompanySubmitLabel");
  const spinner = $("addCompanySubmitSpinner");
  btn.disabled = loading;
  label.textContent = loading ? "Detecting…" : "Add company";
  if (spinner) spinner.hidden = !loading;
}

function resetAddCompanySubmit() {
  setAddCompanySubmitLoading(false);
}

export async function submitAddCompany(e) {
  e.preventDefault();
  const name = $("addCompanyName").value.trim();
  const careers_url = $("addCompanyUrl").value.trim();
  const ats = getAddCompanyAts();
  const countries = isAddCompanyCountryAuto() ? [] : getAddCompanySelectedCountries();
  const locations = getAddCompanyLocations();
  setAddCompanySubmitLoading(true);
  try {
    const data = await addCompany({
      country: countries[0] || "auto",
      countries,
      name,
      careers_url,
      ats,
      locations,
    });
    if (!data) return;
    const c = data.company;
    const bits = [
      c.country_label,
      c.ats_type && `ATS: ${c.ats_type}`,
      c.city && c.city,
      c.size && c.size,
    ].filter(Boolean);
    toast(`Added ${c.name} → ${bits.join(", ")}`);
    closeAddCompanyDialog();
    if ($("country").value === "all" || $("country").value === c.country) {
      await loadCities();
      await loadJobs();
    } else {
      $("country").value = c.country;
      await loadCities();
      await loadJobs();
    }
  } catch {
    toast("Network error");
  } finally {
    resetAddCompanySubmit();
  }
}

function formatCountryLabel(country) {
  const raw = (country || "").trim();
  if (!raw) return "";
  const fromHeader = getAddCompanyCountryOptions().find((item) => item.id === raw.toLowerCase());
  if (fromHeader) return fromHeader.label;
  const fromPicker = addCompanyPickerLocations.find((loc) => loc.country === raw.toLowerCase());
  if (fromPicker?.country_label) return fromPicker.country_label;
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function ensurePickerLocation(entry) {
  const key = locationSelectionKey(entry);
  if (addCompanyPickerLocations.some((loc) => locationSelectionKey(loc) === key)) return;
  addCompanyPickerLocations.push(entry);
  addCompanyPickerLocations.sort((a, b) => {
    const byCountry = (a.country_label || a.country).localeCompare(
      b.country_label || b.country,
      undefined,
      { sensitivity: "base" }
    );
    if (byCountry !== 0) return byCountry;
    return (a.city || "").localeCompare(b.city || "", undefined, { sensitivity: "base" });
  });
}

function renderCustomCityAddRow(country, countryLabel, { idPrefix = "addCompany" } = {}) {
  const inputId = `${idPrefix}CustomCity-${slugifyGroupId(country)}`;
  return `
    <div class="custom-city-add-row">
      <input
        type="text"
        class="custom-city-add-input"
        id="${escapeAttr(inputId)}"
        data-country="${escapeAttr(country)}"
        placeholder="Add a city…"
        autocomplete="off"
        spellcheck="false"
      />
      <button
        type="button"
        class="dialog-btn dialog-btn-ghost custom-city-add-btn"
        data-country="${escapeAttr(country)}"
        data-country-label="${escapeAttr(countryLabel)}"
      >Add city</button>
    </div>
  `;
}

function locationFromApi(saved, countryLabel = "") {
  if (!saved) return null;
  return {
    country: saved.country,
    city: saved.city,
    key: saved.key,
    country_label: saved.country_label || countryLabel || formatCountryLabel(saved.country),
    label: saved.label || `${saved.city} (${saved.country_label || formatCountryLabel(saved.country)})`,
  };
}

async function addCustomCompanyCountry(label) {
  const trimmed = (label || "").trim();
  if (!trimmed) {
    toast("Enter a country name");
    return false;
  }
  const saved = await addCustomCountry(trimmed);
  if (!saved?.id) return false;

  const { loadCountries } = await import("./data.js");
  await loadCountries();
  populateAddCompanyCountryPicker({ force: true });

  const selected = new Set(getAddCompanySelectedCountries());
  selected.add(saved.id);
  setAddCompanyCountries([...selected]);
  toast(`Added ${saved.label}`);
  return true;
}

function handleAddCompanyCustomCountryClick() {
  const input = $("addCompanyCustomCountryInput");
  const label = (input?.value || "").trim();
  void addCustomCompanyCountry(label).then((ok) => {
    if (ok && input) input.value = "";
  });
}

async function addCustomCompanyLocation(country, city, countryLabel = "") {
  const trimmed = (city || "").trim();
  if (!trimmed) {
    toast("Enter a city name");
    return false;
  }
  const saved = await addCustomLocation(country, trimmed);
  const entry = locationFromApi(saved, countryLabel);
  if (!entry) return false;
  const selected = getAddCompanyLocations();
  if (selected.some((loc) => locationSelectionKey(loc) === entry.key)) {
    toast(`${entry.label} is already selected`);
    return false;
  }
  ensurePickerLocation(entry);
  invalidatePickerLocationsCache();
  addCompanyPickerLocations = [];
  selected.push(entry);
  setAddCompanyLocations(selected);
  renderAddCompanyLocationOptions();
  toast(`Added ${entry.label}`);
  return true;
}

function handleAddCompanyCustomCityClick(btn) {
  const country = btn.dataset.country;
  const row = btn.closest(".custom-city-add-row");
  const input = row?.querySelector(".custom-city-add-input");
  const city = (input?.value || "").trim();
  void addCustomCompanyLocation(country, city, btn.dataset.countryLabel || "").then((ok) => {
    if (ok && input) input.value = "";
  });
}

function populateEditCityCountrySelect() {
  const select = $("editCityAddCountry");
  if (!select) return;
  const countries = getAddCompanyCountryOptions();
  select.innerHTML = countries
    .map(
      (country) => `<option value="${escapeAttr(country.id)}">${escapeHtml(country.label)}</option>`
    )
    .join("");
}

async function addCustomEditCityLocation() {
  const country = ($("editCityAddCountry")?.value || "").trim();
  const city = ($("editCityAddCity")?.value || "").trim();
  if (!city) {
    toast("Enter a city name");
    return;
  }
  const saved = await addCustomLocation(country, city);
  const entry = locationFromApi(saved);
  if (!entry) return;
  const selected = getEditCitySelection();
  if (selected.some((loc) => locationSelectionKey(loc) === entry.key)) {
    toast(`${entry.label} is already selected`);
    return;
  }
  selected.push(entry);
  setEditCitySelection(selected);
  if ($("editCityAddCity")) $("editCityAddCity").value = "";
  await populateEditCityOptions(selected);
  toast(`Added ${entry.label}`);
}

const EDIT_CAREERS_DETECT_ICON = `<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/>`;
const EDIT_CAREERS_SAVE_ICON = `<path d="M20 6 9 17l-5-5"/>`;

function updateEditCareersSubmitLabel() {
  const redetect = $("editCareersRedetect").checked;
  const label = $("editCareersSubmitLabel");
  const icon = $("editCareersSubmitIcon");
  if (!label || $("editCareersSubmit").disabled) return;
  label.textContent = redetect ? "Save & detect" : "Save URL";
  if (icon) icon.innerHTML = redetect ? EDIT_CAREERS_DETECT_ICON : EDIT_CAREERS_SAVE_ICON;
}

function setEditCareersSubmitLoading(loading, redetect = true) {
  const btn = $("editCareersSubmit");
  const label = $("editCareersSubmitLabel");
  const icon = $("editCareersSubmitIcon");
  btn.disabled = loading;
  label.textContent = loading ? (redetect ? "Detecting…" : "Saving…") : (redetect ? "Save & detect" : "Save URL");
  if (icon && !loading) {
    icon.innerHTML = redetect ? EDIT_CAREERS_DETECT_ICON : EDIT_CAREERS_SAVE_ICON;
  }
}

function resetEditCareersSubmit() {
  setEditCareersSubmitLoading(false, $("editCareersRedetect").checked);
}

export function openEditCareersDialog(country, company, url, countryLabel = "") {
  state.editCareersContext = { country, company };
  $("editCareersCompanyName").textContent = company;
  $("editCareersCompanyCountry").textContent = countryLabel || formatCountryLabel(country);
  $("editCareersUrl").value = url || "";
  $("editCareersRedetect").checked = true;
  resetEditCareersSubmit();
  $("editCareersDialog").classList.add("open");
  $("editCareersDialog").setAttribute("aria-hidden", "false");
  const input = $("editCareersUrl");
  input.focus();
  if (input.value) {
    requestAnimationFrame(() => input.select());
  }
}

export function closeEditCareersDialog() {
  state.editCareersContext = null;
  $("editCareersDialog").classList.remove("open");
  $("editCareersDialog").setAttribute("aria-hidden", "true");
  resetEditCareersSubmit();
}

export async function submitEditCareers(e) {
  e.preventDefault();
  if (!state.editCareersContext) return;
  const { country, company } = state.editCareersContext;
  const careers_url = $("editCareersUrl").value.trim();
  const redetect_ats = $("editCareersRedetect").checked;
  setEditCareersSubmitLoading(true, redetect_ats);
  try {
    const result = await updateCareersUrl(country, company, careers_url, redetect_ats);
    if (!result) return;
    const bits = [
      result.ats_type && `ATS: ${result.ats_type}`,
    ].filter(Boolean);
    toast(`Saved careers URL${bits.length ? ` (${bits.join(", ")})` : ""}`);
    closeEditCareersDialog();
    await loadJobs();
  } finally {
    resetEditCareersSubmit();
  }
}

function setEditCompanyNameSubmitLoading(loading) {
  const btn = $("editCompanyNameSubmit");
  const label = $("editCompanyNameSubmitLabel");
  if (!btn || !label) return;
  btn.disabled = loading;
  label.textContent = loading ? "Saving…" : "Save name";
}

function resetEditCompanyNameSubmit() {
  setEditCompanyNameSubmitLoading(false);
}

export function openEditCompanyNameDialog(country, company, countryLabel = "") {
  state.editCompanyNameContext = { country, company };
  $("editCompanyNameCurrent").textContent = company;
  $("editCompanyNameCountry").textContent = countryLabel || formatCountryLabel(country);
  $("editCompanyNameInput").value = company;
  resetEditCompanyNameSubmit();
  $("editCompanyNameDialog").classList.add("open");
  $("editCompanyNameDialog").setAttribute("aria-hidden", "false");
  const input = $("editCompanyNameInput");
  input.focus();
  requestAnimationFrame(() => input.select());
}

export function closeEditCompanyNameDialog() {
  state.editCompanyNameContext = null;
  $("editCompanyNameDialog").classList.remove("open");
  $("editCompanyNameDialog").setAttribute("aria-hidden", "true");
  resetEditCompanyNameSubmit();
}

export async function submitEditCompanyName(e) {
  e.preventDefault();
  if (!state.editCompanyNameContext) return;
  const { country, company } = state.editCompanyNameContext;
  const new_name = $("editCompanyNameInput").value.trim();
  if (!new_name) {
    toast("Company name is required");
    return;
  }
  setEditCompanyNameSubmitLoading(true);
  try {
    const result = await updateCompanyName(country, company, new_name);
    if (!result) return;
    migrateCompanyKeyInState(country, company, result.company || new_name);
    toast(`Renamed to ${result.company || new_name}`);
    closeEditCompanyNameDialog();
    await loadJobs();
  } finally {
    resetEditCompanyNameSubmit();
  }
}

function setEditCitySubmitLoading(loading) {
  const btn = $("editCitySubmit");
  const label = $("editCitySubmitLabel");
  btn.disabled = loading;
  label.textContent = loading ? "Saving…" : "Save locations";
}

function resetEditCitySubmit() {
  setEditCitySubmitLoading(false);
}

function normalizeLocationList(raw) {
  let items = [];
  if (Array.isArray(raw)) {
    items = raw
      .map((item) => {
        if (typeof item === "string") {
          if (item.includes(":")) {
            const [country, city] = item.split(":", 2);
            return { country, city };
          }
          return null;
        }
        if (item && typeof item === "object") {
          return {
            country: item.country || "",
            city: item.city || "",
            key: item.key || "",
            label: item.label || "",
          };
        }
        return null;
      })
      .filter((item) => item && item.country && item.city);
  } else if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (trimmed.startsWith("[")) {
      try {
        return normalizeLocationList(JSON.parse(trimmed));
      } catch {
        return [];
      }
    }
  }
  return dedupeLocationList(items);
}

function normalizeCityKey(city) {
  return String(city || "")
    .trim()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function locationSelectionKey(loc) {
  const country = String(loc?.country || "").trim().toLowerCase();
  const city = normalizeCityKey(loc?.city || "");
  if (country && city) {
    return `${country}:${city}`;
  }
  const rawKey = String(loc?.key || "").trim().toLowerCase();
  if (!rawKey.includes(":")) return rawKey;
  const [keyCountry, keyCity] = rawKey.split(":", 2);
  return `${String(keyCountry || "").trim().toLowerCase()}:${normalizeCityKey(keyCity || "")}`;
}

function locationKeyFromChip(chip) {
  return locationSelectionKey({
    country: chip.dataset.country,
    city: chip.dataset.city,
    key: chip.dataset.locationKey,
  });
}

function dedupeLocationList(locations) {
  const byKey = new Map();
  for (const loc of locations) {
    if (!loc?.country || !loc?.city) continue;
    const key = locationSelectionKey(loc);
    const prev = byKey.get(key);
    byKey.set(key, {
      country: loc.country,
      city: loc.city,
      key: loc.key || key,
      label: loc.label || prev?.label || "",
    });
  }
  return [...byKey.values()].sort((a, b) => {
    const byCountry = (a.country || "").localeCompare(b.country || "");
    if (byCountry !== 0) return byCountry;
    return (a.city || "").localeCompare(b.city || "", undefined, { sensitivity: "base" });
  });
}

function getEditCitySelection() {
  try {
    return normalizeLocationList(JSON.parse($("editCityValue").value || "[]"));
  } catch {
    return [];
  }
}

function formatLocationLabel(loc) {
  return loc.label || `${loc.city} (${formatCountryLabel(loc.country)})`;
}

function updateEditCityHeaderBadge(selectedLocations, catalogCountryLabel = "") {
  const badge = $("editCityCompanyCountry");
  const chip = $("editCityCompanyChip");
  if (!badge) return;
  const selected = normalizeLocationList(selectedLocations);
  if (selected.length) {
    badge.textContent = selected.map(formatLocationLabel).join(" · ");
    if (chip) {
      chip.title = catalogCountryLabel
        ? `${catalogCountryLabel} catalog — tags can span multiple countries`
        : "Selected location tags";
    }
    return;
  }
  badge.textContent = catalogCountryLabel
    ? `${catalogCountryLabel} catalog`
    : "No locations tagged";
  if (chip) {
    chip.title = catalogCountryLabel
      ? `Company is stored in the ${catalogCountryLabel} catalog`
      : "";
  }
}

function setEditCitySelection(selectedLocations) {
  const picker = document.querySelector("#editCityForm .city-chips");
  if (!picker) return;
  const selected = normalizeLocationList(selectedLocations);
  $("editCityValue").value = JSON.stringify(
    selected.map((loc) => ({ country: loc.country, city: loc.city }))
  );
  const selectedKeys = new Set(selected.map((loc) => locationSelectionKey(loc)));
  picker.querySelectorAll(".country-chip[data-location-key]").forEach((chip) => {
    const isSelected = selectedKeys.has(locationKeyFromChip(chip));
    chip.classList.toggle("is-selected", isSelected);
    chip.setAttribute("aria-pressed", isSelected ? "true" : "false");
  });
  updateEditCityHeaderBadge(
    selected,
    state.editCityContext?.catalogCountryLabel || ""
  );
}

function toggleEditCityChip(chip) {
  const selected = getEditCitySelection();
  const key = locationKeyFromChip(chip);
  const idx = selected.findIndex((loc) => locationSelectionKey(loc) === key);
  if (idx >= 0) {
    setEditCitySelection(selected.filter((loc) => locationSelectionKey(loc) !== key));
  } else {
    selected.push({
      country: chip.dataset.country,
      city: chip.dataset.city,
      key: chip.dataset.locationKey,
      label: chip.textContent.trim(),
    });
    setEditCitySelection(selected);
  }
}

async function populateEditCityOptions(selectedLocations) {
  const container = $("editCityOptions");
  if (!container) return;

  const options = await loadPickerLocations();
  const selected = normalizeLocationList(selectedLocations);
  const optionKeys = new Set(options.map((loc) => locationSelectionKey(loc)));

  for (const loc of selected) {
    const key = locationSelectionKey(loc);
    if (!optionKeys.has(key) && loc.country && loc.city) {
      options.push({
        country: loc.country,
        city: loc.city,
        country_label: loc.country_label || formatCountryLabel(loc.country),
        key: loc.key || `${loc.country}:${loc.city}`,
        label: loc.label || `${loc.city} (${formatCountryLabel(loc.country)})`,
      });
      optionKeys.add(key);
    }
  }

  options.sort((a, b) => {
    const byCountry = (a.country_label || a.country).localeCompare(
      b.country_label || b.country,
      undefined,
      { sensitivity: "base" }
    );
    if (byCountry !== 0) return byCountry;
    return (a.city || "").localeCompare(b.city || "", undefined, { sensitivity: "base" });
  });

  const groups = new Map();
  for (const loc of options) {
    const groupKey = loc.country_label || loc.country;
    if (!groups.has(groupKey)) groups.set(groupKey, []);
    groups.get(groupKey).push(loc);
  }

  container.innerHTML = [...groups.entries()].map(([groupLabel, locs]) => `
    <div class="location-country-group">
      <p class="location-country-label">${escapeHtml(groupLabel)}</p>
      <div class="country-chips-list">
        ${locs.map((loc) => `
          <button
            type="button"
            class="country-chip"
            data-location-key="${escapeAttr(loc.key)}"
            data-country="${escapeAttr(loc.country)}"
            data-city="${escapeAttr(loc.city)}"
            aria-pressed="false"
          >${escapeHtml(loc.label || loc.city)}</button>
        `).join("")}
      </div>
    </div>
  `).join("");
  setEditCitySelection(selected);
}

export async function openEditCityDialog(country, company, locations, countryLabel = "") {
  const catalogCountryLabel = countryLabel || formatCountryLabel(country);
  const normalized = normalizeLocationList(locations);
  state.editCityContext = { country, company, catalogCountryLabel };
  $("editCityCompanyName").textContent = company;
  updateEditCityHeaderBadge(normalized, catalogCountryLabel);
  resetEditCitySubmit();
  populateEditCityCountrySelect();
  if ($("editCityAddCountry")) {
    $("editCityAddCountry").value = normalized[0]?.country || country || "";
  }
  if ($("editCityAddCity")) $("editCityAddCity").value = "";
  $("editCityDialog").classList.add("open");
  $("editCityDialog").setAttribute("aria-hidden", "false");
  await populateEditCityOptions(normalized);
  $("editCityAddCity")?.focus();
}

export function closeEditCityDialog() {
  state.editCityContext = null;
  $("editCityDialog").classList.remove("open");
  $("editCityDialog").setAttribute("aria-hidden", "true");
  resetEditCitySubmit();
}

export async function submitEditCity(e) {
  e.preventDefault();
  if (!state.editCityContext) return;
  const { country, company } = state.editCityContext;
  const locations = getEditCitySelection();
  setEditCitySubmitLoading(true);
  try {
    const result = await updateCompanyCity(country, company, locations);
    if (!result) return;
    toast(
      locations.length
        ? `Locations: ${locations.map((loc) => loc.label || `${loc.city} (${formatCountryLabel(loc.country)})`).join(", ")}`
        : "Location tags cleared"
    );
    closeEditCityDialog();
    await loadCities();
    await loadJobs();
  } finally {
    resetEditCitySubmit();
  }
}

export function bindDialogEvents() {
  $("addCompanyBtn").addEventListener("click", openAddCompanyDialog);
  $("addCompanyCancel").addEventListener("click", closeAddCompanyDialog);
  $("addCompanyClose").addEventListener("click", closeAddCompanyDialog);
  $("addCompanyDialog").addEventListener("click", (e) => {
    if (e.target === $("addCompanyDialog")) closeAddCompanyDialog();
  });
  $("addCompanyForm").addEventListener("submit", submitAddCompany);

  $("addCompanyCountryAutoBtn")?.addEventListener("click", setAddCompanyCountryAuto);
  $("addCompanyCustomCountryBtn")?.addEventListener("click", handleAddCompanyCustomCountryClick);
  $("addCompanyCustomCountryInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    handleAddCompanyCustomCountryClick();
  });
  $("addCompanyAtsAutoBtn")?.addEventListener("click", () => setAddCompanyAts("auto"));
  $("addCompanyLocationsClear")?.addEventListener("click", () => setAddCompanyLocations([]));

  $("addCompanyAtsTrigger")?.addEventListener("click", () => toggleAddCompanyAccordion("addCompanyAtsAccordion"));
  $("addCompanyCountryTrigger")?.addEventListener("click", () => toggleAddCompanyAccordion("addCompanyCountryAccordion"));
  $("addCompanyLocationsTrigger")?.addEventListener("click", () => toggleAddCompanyAccordion("addCompanyLocationsAccordion"));

  $("addCompanyLocationSearch")?.addEventListener("input", () => renderAddCompanyLocationOptions());

  $("addCompanyForm")?.addEventListener("click", handleAddCompanyAtsChipClick);

  document.querySelector("#addCompanyForm .add-company-country-chips")?.addEventListener("click", (e) => {
    const chip = e.target.closest(".country-chip[data-value]");
    if (!chip) return;
    toggleAddCompanyCountry(chip);
  });

  document.querySelector("#addCompanyForm .add-company-location-chips")?.addEventListener("click", (e) => {
    const customBtn = e.target.closest(".custom-city-add-btn");
    if (customBtn?.closest("#addCompanyLocationOptions")) {
      handleAddCompanyCustomCityClick(customBtn);
      return;
    }
    const groupTrigger = e.target.closest(".add-company-location-group-trigger");
    if (groupTrigger) {
      toggleAddCompanyLocationGroup(groupTrigger);
      return;
    }
    const chip = e.target.closest(".country-chip[data-location-key]");
    if (!chip) return;
    toggleAddCompanyLocationChip(chip);
  });

  $("addCompanyForm")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const input = e.target.closest(".custom-city-add-input");
    if (!input?.closest("#addCompanyLocationOptions")) return;
    e.preventDefault();
    const btn = input.closest(".custom-city-add-row")?.querySelector(".custom-city-add-btn");
    if (btn) handleAddCompanyCustomCityClick(btn);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if ($("addCompanyDialog").classList.contains("open")) closeAddCompanyDialog();
    else if ($("editCompanyNameDialog").classList.contains("open")) closeEditCompanyNameDialog();
    else if ($("editCareersDialog").classList.contains("open")) closeEditCareersDialog();
    else if ($("editCityDialog").classList.contains("open")) closeEditCityDialog();
  });

  $("editCompanyNameCancel").addEventListener("click", closeEditCompanyNameDialog);
  $("editCompanyNameClose").addEventListener("click", closeEditCompanyNameDialog);
  $("editCompanyNameDialog").addEventListener("click", (e) => {
    if (e.target === $("editCompanyNameDialog")) closeEditCompanyNameDialog();
  });
  $("editCompanyNameForm").addEventListener("submit", submitEditCompanyName);

  $("editCareersCancel").addEventListener("click", closeEditCareersDialog);
  $("editCareersClose").addEventListener("click", closeEditCareersDialog);
  $("editCareersRedetect").addEventListener("change", updateEditCareersSubmitLabel);
  $("editCareersDialog").addEventListener("click", (e) => {
    if (e.target === $("editCareersDialog")) closeEditCareersDialog();
  });
  $("editCareersForm").addEventListener("submit", submitEditCareers);

  $("editCityCancel").addEventListener("click", closeEditCityDialog);
  $("editCityClose").addEventListener("click", closeEditCityDialog);
  $("editCityDialog").addEventListener("click", (e) => {
    if (e.target === $("editCityDialog")) closeEditCityDialog();
  });
  $("editCityForm").addEventListener("submit", submitEditCity);
  $("editCityClearAll")?.addEventListener("click", () => setEditCitySelection([]));
  $("editCityAddBtn")?.addEventListener("click", () => addCustomEditCityLocation());
  $("editCityAddCity")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    addCustomEditCityLocation();
  });

  document.querySelector("#editCityForm .city-chips")?.addEventListener("click", (e) => {
    const chip = e.target.closest(".country-chip[data-location-key]");
    if (!chip) return;
    toggleEditCityChip(chip);
  });
}
