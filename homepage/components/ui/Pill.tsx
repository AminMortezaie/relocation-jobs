import type { ReactNode } from "react";

export type PillVariant =
  | "applied"
  | "awaiting"
  | "looking"
  | "rejected"
  | "not-for-me"
  | "referral"
  | "country"
  | "neutral"
  | "warn"
  | "visa";

const VARIANT_CLASSES: Record<PillVariant, string> = {
  applied:
    "border-[var(--color-ink)] bg-[var(--accent-primary)] text-[var(--text-on-accent)]",
  awaiting:
    "border-[var(--color-rule)] bg-[var(--color-paper-3)] text-[var(--color-ink)]",
  looking:
    "border-[var(--color-ink)] bg-[var(--accent-primary-soft)] text-[var(--color-ink)]",
  rejected:
    "border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--text-muted)_10%,transparent)] text-[var(--text-muted)]",
  "not-for-me":
    "border-[color-mix(in_srgb,var(--warn)_28%,transparent)] bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] text-[var(--warn)]",
  referral:
    "border-[var(--color-ink-2)] bg-[var(--accent-blue-soft)] text-[var(--color-ink-2)]",
  country:
    "border-[var(--color-rule)] bg-[var(--color-paper-2)] text-[var(--color-ink)]",
  neutral:
    "border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--text-muted)_8%,transparent)] text-[var(--text-muted)]",
  warn:
    "border-[color-mix(in_srgb,var(--warn)_28%,transparent)] bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] text-[var(--warn)]",
  visa:
    "border-[var(--color-rule)] bg-[var(--accent-green-soft)] text-[var(--accent-green)]",
};

type PillProps = {
  variant?: PillVariant;
  children: ReactNode;
  className?: string;
};

export function Pill({
  variant = "neutral",
  children,
  className = "",
}: PillProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium tracking-[0.02em] ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
