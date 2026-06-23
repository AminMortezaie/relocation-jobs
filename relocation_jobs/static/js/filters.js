/** Filter bar UI: popover, chips, sort sync. */

import { $, isNarrowViewport, lockBodyScroll, unlockBodyScroll } from "./utils.js";
import { saveFilterPreferences, saveSortPreference } from "./storage.js";
import { renderCompanies, releaseCompanyOrder } from "./render.js";
import { loadJobs } from "./data.js";

const FILTER_DEFS = [
  { id: "hidePositionApplied", label: "Hide applied positions", reload: true },
  { id: "positionAppliedOnly", label: "Applied positions only", reload: true },
  { id: "positionRejectedOnly", label: "Rejections only", reload: true },
  { id: "positionLookingToApplyOnly", label: "Looking to apply only", reload: true },
  { id: "hideApplied", label: "Hide applied companies", reload: true },
  { id: "hideEmpty", label: "Hide companies with no jobs", reload: true },
  { id: "hideCollapsedCompanies", label: "Hide collapsed companies", reload: false },
  { id: "notAppliedOnly", label: "Not applied, has openings", reload: true },
  { id: "fetchOkOnly", label: "Fetch OK only", reload: true },
  { id: "fetchProblemOnly", label: "Fetch problems", reload: true },
  { id: "visaOnly", label: "Visa / relocation", reload: true },
];

function syncSortFromSelect() {
  const newest = $("sortSelect").value === "newest";
  if ($("sortNewestFetch").checked !== newest) {
    $("sortNewestFetch").checked = newest;
  }
}

function syncSelectFromSortCheckbox() {
  $("sortSelect").value = $("sortNewestFetch").checked ? "newest" : "name";
}

function activeFilters() {
  return FILTER_DEFS.filter((f) => $(f.id).checked);
}

export function updateFilterUI() {
  const active = activeFilters();
  const badge = $("filterBadge");
  if (active.length) {
    badge.textContent = String(active.length);
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }

  const chips = $("filterChips");
  if (!active.length) {
    chips.hidden = true;
    chips.innerHTML = "";
    return;
  }

  chips.hidden = false;
  chips.innerHTML = active.map((f) => `
    <span class="filter-chip">
      ${f.label}
      <button type="button" class="filter-chip-remove" data-filter-id="${f.id}" aria-label="Remove ${f.label} filter">×</button>
    </span>
  `).join("");
}

function showFilterBackdrop() {
  const backdrop = $("filterBackdrop");
  if (!backdrop || !isNarrowViewport()) return;
  backdrop.hidden = false;
  backdrop.setAttribute("aria-hidden", "false");
  lockBodyScroll();
}

function hideFilterBackdrop() {
  const backdrop = $("filterBackdrop");
  if (backdrop) {
    backdrop.hidden = true;
    backdrop.setAttribute("aria-hidden", "true");
  }
  unlockBodyScroll();
}

function closeFilterPopover() {
  const popover = $("filterPopover");
  popover.hidden = true;
  popover.classList.remove("is-sheet");
  $("filterBtn").setAttribute("aria-expanded", "false");
  hideFilterBackdrop();
}

function toggleFilterPopover() {
  const popover = $("filterPopover");
  const open = popover.hidden;
  if (open) {
    popover.hidden = false;
    if (isNarrowViewport()) {
      popover.classList.add("is-sheet");
      showFilterBackdrop();
    } else {
      popover.classList.remove("is-sheet");
      hideFilterBackdrop();
    }
    $("filterBtn").setAttribute("aria-expanded", "true");
    return;
  }
  closeFilterPopover();
}

async function applyFilterChange(def, checked) {
  $(def.id).checked = checked;
  saveFilterPreferences();
  updateFilterUI();
  if (def.reload) {
    await loadJobs();
  } else {
    renderCompanies();
  }
}

export function bindFilterBar() {
  syncSelectFromSortCheckbox();
  updateFilterUI();

  $("sortSelect").addEventListener("change", () => {
    syncSortFromSelect();
    saveSortPreference();
    releaseCompanyOrder();
    renderCompanies();
  });

  $("filterBtn").addEventListener("click", (e) => {
    e.stopPropagation();
    toggleFilterPopover();
  });

  $("filterBackdrop")?.addEventListener("click", closeFilterPopover);

  $("clearFilters").addEventListener("click", async () => {
    let needsReload = false;
    for (const f of FILTER_DEFS) {
      if ($(f.id).checked) {
        $(f.id).checked = false;
        if (f.reload) needsReload = true;
      }
    }
    saveFilterPreferences();
    updateFilterUI();
    if (needsReload) {
      await loadJobs();
    } else {
      renderCompanies();
    }
  });

  $("filterPopover").addEventListener("click", (e) => e.stopPropagation());

  document.addEventListener("click", () => {
    if (!$("filterPopover").hidden) closeFilterPopover();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeFilterPopover();
  });

  for (const def of FILTER_DEFS) {
    $(def.id).addEventListener("change", async () => {
      saveFilterPreferences();
      updateFilterUI();
      if (def.reload) {
        await loadJobs();
      } else {
        renderCompanies();
      }
    });
  }

  $("filterChips").addEventListener("click", async (e) => {
    const btn = e.target.closest(".filter-chip-remove");
    if (!btn) return;
    const def = FILTER_DEFS.find((f) => f.id === btn.dataset.filterId);
    if (!def) return;
    await applyFilterChange(def, false);
  });
}

/** Call after loadConfig toggles scrape-only filters. */
export function refreshFilterBar() {
  updateFilterUI();
}
