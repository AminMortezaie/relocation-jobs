/** Header menus: user account and scrape settings popovers. */

import { $ } from "./utils.js";

function closePopover(popoverId, btnId) {
  $(popoverId).hidden = true;
  if (btnId) $(btnId).setAttribute("aria-expanded", "false");
}

function togglePopover(popoverId, btnId) {
  const open = $(popoverId).hidden;
  closeAllHeaderPopovers();
  if (open) {
    $(popoverId).hidden = false;
    $(btnId).setAttribute("aria-expanded", "true");
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
