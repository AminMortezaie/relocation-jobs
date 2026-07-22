import { countryLinks } from "@/lib/countries";

const PRODUCT_LINKS = [
  { href: "/panel", label: "Board" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/mcp", label: "MCP" },
  { href: "/pricing", label: "Pricing" },
] as const;

const META_LINKS = [
  {
    href: "https://github.com/AminMortezaie/relocation-jobs/blob/main/docs/contributing.md",
    label: "Contributing",
    external: true,
  },
  {
    href: "https://github.com/AminMortezaie/relocation-jobs",
    label: "Source",
    external: true,
  },
] as const;

export function Footer() {
  const countryNav = countryLinks();
  return (
    <footer className="landing-footer">
      <div className="landing-shell flex flex-col gap-7 py-10">
        <div className="footer-brand">
          <p className="font-display text-sm font-bold tracking-[0.06em] text-text-primary">
            KUCHUP
          </p>
          <p>
            A relocation job-search workspace for finding the role, keeping the
            thread, and preparing what comes next.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-3">
          <FooterGroup title="Product" links={PRODUCT_LINKS} />
          <FooterGroup title="Countries" links={countryNav} />
          <FooterGroup title="Project" links={META_LINKS} />
        </div>
      </div>
    </footer>
  );
}

function FooterGroup({
  title,
  links,
}: {
  title: string;
  links: readonly {
    href: string;
    label: string;
    external?: boolean;
  }[];
}) {
  return (
    <nav aria-label={title}>
      <p className="mb-2 text-xs font-medium uppercase tracking-[0.08em] text-text-muted">
        {title}
      </p>
      <ul className="flex flex-col gap-1.5">
        {links.map((link) => (
          <li key={link.label}>
            <a
              href={link.href}
              className="text-sm font-medium text-text-secondary transition-colors duration-150 ease-out hover:text-text-primary"
              {...(link.external
                ? { target: "_blank", rel: "noopener noreferrer" }
                : {})}
            >
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
