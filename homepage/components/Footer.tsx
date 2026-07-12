const FOOTER_LINKS = [
  { href: "/panel", label: "Board" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/relocation-jobs-germany", label: "Jobs in Germany" },
  { href: "/relocation-jobs-netherlands", label: "Jobs in Netherlands" },
  { href: "/relocation-jobs-uk", label: "Jobs in UK" },
  { href: "/relocation-jobs-portugal", label: "Jobs in Portugal" },
  { href: "https://github.com/AminMortezaie/relocation-jobs/blob/main/docs/contributing.md", label: "Contributing", external: true },
  { href: "https://github.com/AminMortezaie/relocation-jobs", label: "Source", external: true },
] as const;

export function Footer() {
  return (
    <footer className="border-t border-white/[0.07] py-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-normal text-muted">Relocation Jobs</p>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-2">
            {FOOTER_LINKS.map((link) => (
              <li key={link.label}>
                <a
                  href={link.href}
                  className="pill-control text-sm font-medium text-muted hover:text-text"
                  {...("external" in link && link.external
                    ? { target: "_blank", rel: "noopener noreferrer" }
                    : {})}
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
