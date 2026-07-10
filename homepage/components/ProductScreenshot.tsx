import { Card } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";

const MOCK_COMPANIES = [
  {
    name: "Wolt",
    country: "Germany",
    roles: 4,
    city: "Berlin",
    jobs: [
      { title: "Senior Backend Engineer (Go)", pill: "looking" as const, label: "Looking to apply" },
      { title: "Platform Engineer", pill: "visa" as const, label: "Visa-friendly" },
    ],
    showLooking: true,
    state: "default" as const,
  },
  {
    name: "Polarsteps",
    country: "Netherlands",
    roles: 2,
    city: "Amsterdam",
    jobs: [{ title: "Staff Python Engineer", pill: "applied" as const, label: "Applied · 12 Jun" }],
    showApplied: true,
    state: "applied" as const,
  },
  {
    name: "Fenergo",
    country: "UK",
    roles: 3,
    city: "London",
    jobs: [{ title: "Java Engineer", pill: "awaiting" as const, label: "Awaiting response" }],
    showAwaiting: true,
    state: "awaiting" as const,
  },
] as const;

export function ProductScreenshot() {
  return (
    <section id="board" className="section-major" aria-labelledby="board-heading">
      <div className="mb-8 max-w-xl">
        <h2 id="board-heading" className="text-section-title text-text">
          See it in action
        </h2>
        <p className="mt-2 text-sm font-normal leading-relaxed text-muted">
          This is the board you&apos;ll use — company cards, open roles, and
          status pills in one view.
        </p>
      </div>

      <div className="surface-card rounded-app p-3 sm:p-4" aria-label="Board preview">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-text">Company board</p>
          <div className="flex flex-wrap gap-2">
            <span className="pill-control text-xs font-semibold">Fetch jobs</span>
            <span className="pill-control text-xs font-semibold">Add company</span>
          </div>
        </div>

        <div className="mb-3 flex flex-wrap gap-2">
          <span className="pill-control text-sm">All countries</span>
          <span className="pill-control text-sm">All ATS</span>
          <span className="pill-control text-sm">All locations</span>
        </div>

        <div className="space-y-3">
          {MOCK_COMPANIES.map((company) => (
            <MockCompanyCard key={company.name} company={company} />
          ))}
        </div>
      </div>
    </section>
  );
}

function MockCompanyCard({
  company,
}: {
  company: (typeof MOCK_COMPANIES)[number];
}) {
  const cardTone =
    company.state === "applied"
      ? "opacity-80 border-[rgba(61,214,140,0.35)]"
      : company.state === "awaiting"
        ? "border-[rgba(167,139,250,0.35)] bg-[color-mix(in_srgb,rgba(167,139,250,0.14)_35%,#0f1218)]"
        : "";

  return (
    <Card accentBar className={cardTone}>
      <div className="border-b border-white/[0.07] bg-gradient-to-b from-white/[0.02] to-white/[0.01] px-4 py-3.5 pl-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold tracking-[-0.02em] text-text">
                {company.name}
              </h3>
              <Pill variant="country">{company.country}</Pill>
              {"showApplied" in company && company.showApplied ? (
                <Pill variant="applied">Applied</Pill>
              ) : null}
              {"showAwaiting" in company && company.showAwaiting ? (
                <Pill variant="awaiting">Awaiting response</Pill>
              ) : null}
              {"showLooking" in company && company.showLooking ? (
                <Pill variant="looking">Looking to apply</Pill>
              ) : null}
            </div>
            <p className="mt-1 text-xs font-normal text-muted">
              {company.roles} roles · {company.city}
            </p>
          </div>
          <Pill variant="neutral">2h ago</Pill>
        </div>
      </div>

      <div className="space-y-2 px-4 py-3 pl-5">
        {company.jobs.map((job) => (
          <div
            key={job.title}
            className="rounded-app-sm border border-white/[0.06] bg-[#0d1118]/80 px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-text">{job.title}</p>
              <Pill variant={job.pill}>{job.label}</Pill>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
