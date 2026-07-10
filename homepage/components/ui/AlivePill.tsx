"use client";

import { useEffect, useState } from "react";
import { Pill, type PillVariant } from "@/components/ui/Pill";

type AlivePillProps = {
  states: { variant: PillVariant; label: string }[];
};

export function AlivePill({ states }: AlivePillProps) {
  const [index, setIndex] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(true);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (reducedMotion || states.length < 2) return;
    const id = window.setInterval(() => {
      setIndex((current) => (current + 1) % states.length);
    }, 3200);
    return () => window.clearInterval(id);
  }, [reducedMotion, states.length]);

  const current = states[index] ?? states[0];

  return (
    <span className="alive-pill inline-flex min-w-[9.5rem]">
      <Pill
        key={`${current.variant}-${current.label}`}
        variant={current.variant}
        className="alive-pill-swap"
      >
        {current.label}
      </Pill>
    </span>
  );
}
