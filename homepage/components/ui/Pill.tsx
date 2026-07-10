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
    "border-[rgba(52,211,153,0.22)] bg-gradient-to-b from-[rgba(52,211,153,0.16)] to-[rgba(52,211,153,0.08)] text-[#6ee7b7]",
  awaiting:
    "border-[rgba(167,139,250,0.28)] bg-gradient-to-b from-[rgba(167,139,250,0.18)] to-[rgba(167,139,250,0.08)] text-[#c4b5fd]",
  looking:
    "border-[rgba(36,140,251,0.28)] bg-gradient-to-b from-[rgba(36,140,251,0.14)] to-[rgba(36,140,251,0.06)] text-[#248cfb]",
  rejected:
    "border-[rgba(248,113,113,0.22)] bg-gradient-to-b from-[rgba(248,113,113,0.16)] to-[rgba(248,113,113,0.08)] text-[#fca5a5]",
  "not-for-me":
    "border-[rgba(245,166,35,0.22)] bg-gradient-to-b from-[rgba(245,166,35,0.16)] to-[rgba(245,166,35,0.08)] text-[#fbbf24]",
  referral:
    "border-[rgba(122,168,255,0.24)] bg-gradient-to-b from-[rgba(122,168,255,0.16)] to-[rgba(122,168,255,0.08)] text-referral",
  country:
    "border-[rgba(91,141,239,0.2)] bg-gradient-to-b from-[rgba(91,141,239,0.18)] to-[rgba(91,141,239,0.08)] text-accent-hover",
  neutral:
    "border-[rgba(148,163,184,0.2)] bg-gradient-to-b from-[rgba(148,163,184,0.1)] to-[rgba(148,163,184,0.04)] text-[#94a3b8]",
  warn:
    "border-[rgba(245,166,35,0.22)] bg-gradient-to-b from-[rgba(245,166,35,0.16)] to-[rgba(245,166,35,0.08)] text-[#fbbf24]",
  visa:
    "border-[rgba(167,139,250,0.22)] bg-gradient-to-b from-[rgba(167,139,250,0.16)] to-[rgba(167,139,250,0.08)] text-[#c4b5fd]",
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
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium shadow-[inset_0_1px_0_rgba(255,255,255,0.08),inset_0_-1px_2px_rgba(0,0,0,0.12)] ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
