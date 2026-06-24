/** Header menus: user account and scrape settings popovers. */

import { $ } from "./utils.js";

function closePopover(popoverId, btnId) {
  const popover = $(popoverId);
  if (!popover) return;
  popover.hidden = true;
  if (btnId) {
    const btn = $(btnId);
    if (btn) btn.setAttribute("aria-expanded", "false");
  }
}

function togglePopover(popoverId, btnId) {
  const popover = $(popoverId);
  const btn = btnId ? $(btnId) : null;
  if (!popover || !btn) return;
  const open = popover.hidden;
  closeAllHeaderPopovers();
  if (open) {
    popover.hidden = false;
    btn.setAttribute("aria-expanded", "true");
  }
}

export function closeAllHeaderPopovers() {
  closePopover("userMenuPopover", "userMenuBtn");
  closePopover("scrapeSettingsPopover", "scrapeSettingsBtn");
}

export function bindHeaderBar() {
  const userBtn = $("userMenuBtn");
  if (userBtn) {
    userBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      togglePopover("userMenuPopover", "userMenuBtn");
    });
  }

  const scrapeBtn = $("scrapeSettingsBtn");
  if (scrapeBtn) {
    scrapeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      togglePopover("scrapeSettingsPopover", "scrapeSettingsBtn");
    });
  }

  $("userMenuPopover")?.addEventListener("click", (e) => e.stopPropagation());
  $("scrapeSettingsPopover")?.addEventListener("click", (e) => e.stopPropagation());

  document.addEventListener("click", closeAllHeaderPopovers);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllHeaderPopovers();
  });
}
