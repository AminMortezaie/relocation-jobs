"use client";

import { useEffect, useId, useState } from "react";
import { BrandLockup } from "@/components/BrandMark";
import { Button } from "@/components/ui/Button";

const NAV_LINKS = [
  { href: "/#product", label: "Product" },
  { href: "/mcp", label: "MCP" },
  { href: "/#countries", label: "Countries" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#access", label: "Access" },
] as const;

export function Header() {
  const [open, setOpen] = useState(false);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    function onResize() {
      if (window.matchMedia("(min-width: 768px)").matches) setOpen(false);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <header className="nav-glass relative sticky top-3 z-40 rounded-app shadow-header">
      <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5">
        <a
          href="/"
          className="inline-flex min-w-0 items-center text-inherit no-underline"
          onClick={() => setOpen(false)}
        >
          <BrandLockup markSize="compact" />
        </a>

        <nav aria-label="Primary" className="hidden md:block">
          <ul className="flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <li key={link.label}>
                <a
                  href={link.href}
                  className="rounded-app px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            as="a"
            href="/panel"
            variant="primary"
            className="hidden px-4 py-2 sm:inline-flex"
          >
            Sign in
          </Button>
          <Button
            as="a"
            href="/panel"
            variant="primary"
            className="px-3.5 py-2 text-xs sm:hidden"
          >
            Sign in
          </Button>
          <button
            type="button"
            className="inline-flex h-11 w-11 items-center justify-center rounded-app border border-[var(--color-rule)] text-text-primary transition-transform duration-150 ease-out active:translate-y-px md:hidden"
            aria-expanded={open}
            aria-controls={menuId}
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>

      <nav
        id={menuId}
        aria-label="Primary mobile"
        aria-hidden={!open}
        data-open={open}
        className="mobile-menu-panel absolute left-0 right-0 top-full z-50 mt-1.5 overflow-hidden rounded-app border border-[var(--color-rule)] bg-[var(--color-paper)] px-2 py-2 shadow-header md:hidden"
      >
        <ul className="flex flex-col gap-0.5">
          {NAV_LINKS.map((link) => (
            <li key={link.label}>
              <a
                href={link.href}
                tabIndex={open ? undefined : -1}
                className="block rounded-app px-3 py-2.5 text-sm font-medium text-text-secondary transition-[color,background-color,transform] duration-150 ease-out active:translate-y-px hover:bg-bg-surface-hover hover:text-text-primary"
                onClick={() => setOpen(false)}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}

function MenuIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}
