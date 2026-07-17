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
    "border-[color-mix(in_srgb,var(--accent-green)_28%,transparent)] bg-[color-mix(in_srgb,var(--accent-green)_14%,transparent)] text-[var(--accent-green)]",
  awaiting:
    "border-[color-mix(in_srgb,var(--accent-purple)_28%,transparent)] bg-[color-mix(in_srgb,var(--accent-purple)_14%,transparent)] text-[var(--accent-purple)]",
  looking:
    "border-[color-mix(in_srgb,var(--accent-blue)_28%,transparent)] bg-[color-mix(in_srgb,var(--accent-blue)_14%,transparent)] text-[var(--accent-blue)]",
  rejected:
    "border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--text-muted)_10%,transparent)] text-[var(--text-muted)]",
  "not-for-me":
    "border-[color-mix(in_srgb,var(--warn)_28%,transparent)] bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] text-[var(--warn)]",
  referral:
    "border-[color-mix(in_srgb,var(--accent-blue)_28%,transparent)] bg-[color-mix(in_srgb,var(--accent-blue)_14%,transparent)] text-[var(--accent-blue)]",
  country:
    "border-[color-mix(in_srgb,var(--accent-blue)_24%,transparent)] bg-[color-mix(in_srgb,var(--accent-blue)_12%,transparent)] text-[var(--accent-blue)]",
  neutral:
    "border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--text-muted)_8%,transparent)] text-[var(--text-muted)]",
  warn:
    "border-[color-mix(in_srgb,var(--warn)_28%,transparent)] bg-[color-mix(in_srgb,var(--warn)_12%,transparent)] text-[var(--warn)]",
  visa:
    "border-[color-mix(in_srgb,var(--accent-green)_28%,transparent)] bg-[color-mix(in_srgb,var(--accent-green)_14%,transparent)] text-[var(--accent-green)]",
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
