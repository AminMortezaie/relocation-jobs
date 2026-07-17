import { BrandLockup } from "@/components/BrandMark";
import { Button } from "@/components/ui/Button";

const NAV_LINKS = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/#benefits", label: "What you get" },
  { href: "/#board", label: "See the board" },
] as const;

export function Header() {
  return (
    <header className="nav-glass sticky top-3 z-40 rounded-2xl shadow-header">
      <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3.5 sm:px-5">
        <a href="/" className="inline-flex min-w-0 items-center text-inherit no-underline">
          <BrandLockup />
        </a>

        <div className="flex items-center gap-2 sm:gap-3">
          <nav aria-label="Primary" className="hidden md:block">
            <ul className="flex items-center gap-2">
              {NAV_LINKS.map((link) => (
                <li key={link.label}>
                  <a
                    href={link.href}
                    className="rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <Button as="a" href="/panel" variant="primary" className="hidden sm:inline-flex">
            Sign in
          </Button>
        </div>
      </div>

      <nav
        aria-label="Primary mobile"
        className="border-t border-border-subtle px-4 py-3 md:hidden"
      >
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
