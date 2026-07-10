"use client";

import { useLayoutEffect, useState } from "react";
import { AlivePill } from "@/components/ui/AlivePill";
import { Card } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import { useInView } from "@/hooks/useInView";

const BENEFITS = [
  {
    title: "Every relevant role, one place",
    body: "Stop checking twenty company career pages. Openings from relocate.me companies land in one searchable board.",
    chip: { type: "static" as const, variant: "country" as const, label: "Germany · 42 roles" },
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
  },
  {
    title: "Tailor your resume per job",
    body: "Use the built-in assistant to align your CV to a posting. You approve every line before anything is saved.",
    chip: { type: "static" as const, variant: "looking" as const, label: "CV ready" },
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
        <h2 id="benefits-heading" className="text-section-title text-text">
          What you get
        </h2>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {BENEFITS.map((item, index) => (
          <Card
            key={item.title}
            accentBar
            interactive
            className={`reveal-card flex h-full flex-col p-5 pl-6 ${animate ? "reveal-pending" : ""} ${visible ? "is-visible" : ""}`}
            style={{ transitionDelay: visible && animate ? `${index * 80}ms` : undefined }}
          >
            <div className="mb-4">
              {item.chip.type === "alive" ? (
                <AlivePill states={[...item.chip.states]} />
              ) : (
                <Pill variant={item.chip.variant}>{item.chip.label}</Pill>
              )}
            </div>
            <h3 className="text-base font-semibold tracking-[-0.02em] text-text">
              {item.title}
            </h3>
            <p className="mt-2 flex-1 text-sm font-normal leading-relaxed text-muted">
              {item.body}
            </p>
          </Card>
        ))}
      </div>
    </section>
  );
}
