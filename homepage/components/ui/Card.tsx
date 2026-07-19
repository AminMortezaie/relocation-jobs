import type { CSSProperties, ReactNode } from "react";

type CardVariant = "default" | "feature" | "company" | "testimonial";

type CardProps = {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  accentBar?: boolean;
  interactive?: boolean;
  variant?: CardVariant;
  as?: "div" | "article" | "section";
};

export function Card({
  children,
  className = "",
  style,
  accentBar = false,
  interactive = false,
  variant = "default",
  as: Tag = "div",
}: CardProps) {
  const interactiveClass = interactive
    ? "card-interactive surface-card-interactive"
    : "";

  return (
    <Tag
      className={`card surface-card relative overflow-hidden ${interactiveClass} ${className}`}
      style={style}
      data-variant={variant}
    >
      {accentBar ? (
        <span
          className="pointer-events-none absolute bottom-0 left-0 top-0 w-1 bg-accent-primary"
          aria-hidden="true"
        />
      ) : null}
      {children}
    </Tag>
  );
}

type FeatureCardProps = {
  title: string;
  body: string;
  icon: ReactNode;
  chip?: ReactNode;
  className?: string;
  style?: CSSProperties;
};

export function FeatureCard({
  title,
  body,
  icon,
  chip,
  className = "",
  style,
}: FeatureCardProps) {
  return (
    <Card interactive variant="feature" className={`flex h-full flex-col p-5 ${className}`} style={style}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-app border border-[var(--color-rule)] bg-bg-surface-hover text-accent-primary">
          {icon}
        </span>
        {chip}
      </div>
      <h3 className="font-display text-xl font-bold tracking-[-0.02em] text-text-primary">
        {title}
      </h3>
      <p className="mt-2 flex-1 text-sm font-normal leading-relaxed text-text-secondary">
        {body}
      </p>
    </Card>
  );
}

type CompanyBoardCardProps = {
  name: string;
  country: string;
  roleCount: number;
  city?: string;
  timestamp?: string;
  status?: ReactNode;
  jobs: { title: string; badge: ReactNode }[];
  className?: string;
};

export function CompanyBoardCard({
  name,
  country,
  roleCount,
  city,
  timestamp = "2h ago",
  status,
  jobs,
  className = "",
}: CompanyBoardCardProps) {
  return (
    <Card variant="company" className={className}>
      <div className="border-b border-border-subtle px-4 py-3.5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-display text-xl font-bold tracking-[-0.02em] text-text-primary">
                {name}
              </h3>
              <span className="rounded-app border border-[var(--color-rule)] bg-bg-surface-hover px-2.5 py-0.5 text-xs font-medium text-text-primary">
                {country}
              </span>
              {status}
            </div>
            <p className="mt-1 text-xs font-medium tracking-[0.02em] text-text-muted">
              {roleCount} roles{city ? ` · ${city}` : ""}
            </p>
          </div>
          <span className="text-xs font-medium tracking-[0.02em] text-text-muted">
            {timestamp}
          </span>
        </div>
      </div>
      <div className="space-y-2 px-4 py-3">
        {jobs.map((job) => (
          <div
            key={job.title}
            className="rounded-app border border-border-subtle bg-bg-base/60 px-3 py-2.5"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-text-primary">{job.title}</p>
              {job.badge}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
