import { BrandMark } from "@/components/BrandMark";

const NAV_LINKS = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/#benefits", label: "What you get" },
  { href: "/#board", label: "See the board" },
] as const;

export function Header() {
  return (
    <header className="surface-card relative overflow-visible rounded-app shadow-header">
      <span
        className="pointer-events-none absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-accent via-brand-sky to-visa"
        aria-hidden="true"
      />

      <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-5">
        <a href="/" className="inline-flex min-w-0 items-center gap-3 text-inherit no-underline">
          <BrandMark />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-lg font-semibold tracking-[-0.02em] text-text">
              Relocation Jobs
            </span>
            <span className="text-xs font-normal text-muted">
              Visa-friendly roles abroad
            </span>
          </span>
        </a>

        <div className="flex items-center gap-2 sm:gap-3">
          <nav aria-label="Primary" className="hidden sm:block">
            <ul className="flex items-center gap-2">
              {NAV_LINKS.map((link) => (
                <li key={link.label}>
                  <a href={link.href} className="pill-control text-sm font-medium">
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <a
            href="/panel"
            className="pill-control hidden text-sm font-semibold sm:inline-flex"
          >
            Sign in
          </a>

          <a
            href="/panel"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-[#6b5ce7] text-xs font-bold text-white shadow-[0_0_0_2px_#080a0f,0_0_0_3px_rgba(255,255,255,0.1)]"
            aria-label="Sign in to Relocation Jobs"
          >
            RJ
          </a>
        </div>
      </div>

      <nav aria-label="Primary mobile" className="border-t border-white/[0.07] px-4 py-3 sm:hidden">
        <ul className="flex flex-wrap gap-2">
          {NAV_LINKS.map((link) => (
            <li key={link.label}>
              <a href={link.href} className="pill-control text-sm font-medium">
                {link.label}
              </a>
            </li>
          ))}
          <li>
            <a href="/panel" className="pill-control text-sm font-semibold">
              Sign in
            </a>
          </li>
        </ul>
      </nav>
    </header>
  );
}
