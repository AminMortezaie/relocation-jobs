"use client";

import { useLayoutEffect, useState } from "react";
import { AlivePill } from "@/components/ui/AlivePill";
import { FeatureCard } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { useInView } from "@/hooks/useInView";

const BENEFITS = [
  {
    title: "Every relevant role, one place",
    body: "Stop checking twenty company career pages. Openings from relocate.me companies land in one searchable board.",
    chip: { type: "static" as const, variant: "country" as const, label: "Germany · 42 roles" },
    icon: "search" as const,
  },
  {
    title: "Track it like a pipeline",
    body: "Applied, rejected, waiting on a referral — mark each role with status pills you control, not a spreadsheet.",
    chip: {
      type: "alive" as const,
      states: [
        { variant: "awaiting" as const, label: "Awaiting response" },
        { variant: "applied" as const, label: "Applied" },
      ],
    },
    icon: "pipeline" as const,
  },
  {
    title: "Tailor your resume per job",
    body: "Use the built-in assistant to align your CV to a posting. You approve every line before anything is saved.",
    chip: { type: "static" as const, variant: "looking" as const, label: "CV ready" },
    icon: "document" as const,
  },
] as const;

export function BenefitCards() {
  const { ref, visible } = useInView<HTMLElement>();
  const [animate, setAnimate] = useState(false);

  useLayoutEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    setAnimate(true);
  }, []);

  return (
    <section
      id="benefits"
      ref={ref}
      className="section-major"
      aria-labelledby="benefits-heading"
    >
      <div className="mb-8">
        <h2 id="benefits-heading" className="text-section-title text-text-primary">
          What you get
        </h2>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {BENEFITS.map((item, index) => (
          <FeatureCard
            key={item.title}
            title={item.title}
            body={item.body}
            icon={<BenefitIcon type={item.icon} />}
            chip={
              item.chip.type === "alive" ? (
                <AlivePill states={[...item.chip.states]} />
              ) : (
                <Pill variant={item.chip.variant}>{item.chip.label}</Pill>
              )
            }
            className={`reveal-card ${animate ? "reveal-pending" : ""} ${visible ? "is-visible" : ""}`}
            style={{ transitionDelay: visible && animate ? `${index * 80}ms` : undefined }}
          />
        ))}
      </div>
    </section>
  );
}

function BenefitIcon({ type }: { type: "search" | "pipeline" | "document" }) {
  const className = "h-5 w-5";
  if (type === "search") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-3-3" />
        <circle cx="11" cy="11" r="3" opacity="0.35" />
      </svg>
    );
  }
  if (type === "pipeline") {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <rect x="3" y="4" width="5" height="16" rx="1" />
        <rect x="10" y="4" width="5" height="10" rx="1" />
        <rect x="17" y="4" width="5" height="13" rx="1" />
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <path d="M14 3v5h5M9 13h6M9 17h6" />
    </svg>
  );
}
