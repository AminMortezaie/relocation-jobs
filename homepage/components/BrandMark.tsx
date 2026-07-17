import { BirdIcon } from "@/components/BirdIcon";

type BrandMarkProps = {
  size?: "default" | "compact" | "hero";
  className?: string;
};

const SIZE_CLASS = {
  compact: "h-8 w-8",
  default: "h-9 w-9",
  hero: "h-48 w-48 sm:h-64 sm:w-64 lg:h-[22rem] lg:w-[22rem]",
} as const;

/** Transparent vector mark — inline SVG scales cleanly (nav + hero). */
export function BrandMark({ size = "default", className = "" }: BrandMarkProps) {
  const isHero = size === "hero";

  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center ${SIZE_CLASS[size]} ${className}`}
      aria-hidden="true"
    >
      {isHero ? (
        <span
          className="pointer-events-none absolute inset-[-18%] -z-10 opacity-60"
          style={{
            background:
              "radial-gradient(circle at 55% 45%, color-mix(in srgb, var(--accent-primary) 40%, transparent), transparent 58%), radial-gradient(circle at 35% 60%, color-mix(in srgb, var(--accent-blue) 30%, transparent), transparent 55%)",
            filter: "blur(40px)",
          }}
        />
      ) : null}
      <BirdIcon className="h-full w-full" />
    </span>
  );
}

type BrandLockupProps = {
  className?: string;
  markSize?: "default" | "compact";
};

/** Full lockup: transparent mark + KUCHUP wordmark (nav). */
export function BrandLockup({ className = "", markSize = "default" }: BrandLockupProps) {
  return (
    <span className={`inline-flex min-w-0 items-center gap-2.5 ${className}`}>
      <BrandMark size={markSize} />
      <span className="font-display text-lg font-extrabold tracking-[0.12em] text-text-primary sm:text-xl">
        KUCHUP
      </span>
    </span>
  );
}
