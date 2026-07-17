import { CompanyBoardCard } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";

const MOCK_COMPANIES = [
  {
    name: "Wolt",
    country: "Germany",
    roles: 4,
    city: "Berlin",
    status: <Pill variant="looking">Looking to apply</Pill>,
    jobs: [
      {
        title: "Senior Backend Engineer (Go)",
        badge: <Pill variant="looking">Looking to apply</Pill>,
      },
      {
        title: "Platform Engineer",
        badge: <Pill variant="visa">Visa-friendly</Pill>,
      },
    ],
  },
  {
    name: "Polarsteps",
    country: "Netherlands",
    roles: 2,
    city: "Amsterdam",
    status: <Pill variant="applied">Applied</Pill>,
    jobs: [
      {
        title: "Staff Python Engineer",
        badge: <Pill variant="applied">Applied · 12 Jun</Pill>,
      },
    ],
  },
  {
    name: "Fenergo",
    country: "UK",
    roles: 3,
    city: "London",
    status: <Pill variant="awaiting">Awaiting response</Pill>,
    jobs: [
      {
        title: "Java Engineer",
        badge: <Pill variant="awaiting">Awaiting response</Pill>,
      },
    ],
  },
] as const;

export function ProductScreenshot() {
  return (
    <section id="board" className="section-major" aria-labelledby="board-heading">
      <div className="mb-8 max-w-xl">
        <h2 id="board-heading" className="text-section-title text-text-primary">
          See it in action
        </h2>
        <p className="mt-2 text-sm font-normal leading-relaxed text-text-secondary">
          This is the board you&apos;ll use — company cards, open roles, and
          status pills in one view.
        </p>
      </div>

      <div className="card relative overflow-hidden rounded-2xl p-3 sm:p-4" aria-label="Board preview">
        <div
          className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 opacity-40"
          aria-hidden="true"
          style={{ background: "var(--glow-purple)", filter: "blur(80px)" }}
        />
        <div className="relative mb-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-text-primary">Company board</p>
          <div className="flex flex-wrap gap-2">
            <span className="pill-control text-xs font-semibold">Fetch jobs</span>
            <span className="pill-control text-xs font-semibold">Add company</span>
          </div>
        </div>

        <div className="relative mb-3 flex flex-wrap gap-2">
          <span className="pill-control text-sm">All countries</span>
          <span className="pill-control text-sm">All ATS</span>
          <span className="pill-control text-sm">All locations</span>
        </div>

        <div className="relative grid gap-3 lg:grid-cols-1">
          {MOCK_COMPANIES.map((company) => (
            <CompanyBoardCard
              key={company.name}
              name={company.name}
              country={company.country}
              roleCount={company.roles}
              city={company.city}
              status={company.status}
              jobs={[...company.jobs]}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
