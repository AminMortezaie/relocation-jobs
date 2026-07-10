type BrandMarkProps = {
  size?: "default" | "compact";
};

export function BrandMark({ size = "default" }: BrandMarkProps) {
  const box =
    size === "compact"
      ? "h-[2.15rem] w-[2.15rem] rounded-[10px]"
      : "h-[2.65rem] w-[2.65rem] rounded-xl";

  const icon = size === "compact" ? "h-[1.15rem] w-[1.15rem]" : "h-[1.4rem] w-[1.4rem]";

  return (
    <span
      className={`flex shrink-0 items-center justify-center bg-gradient-to-br from-accent via-brand-sky to-visa text-white shadow-[0_6px_18px_rgba(56,189,248,0.28)] ${box}`}
      aria-hidden="true"
    >
      <svg
        className={icon}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="12" cy="11" r="8" />
        <path d="M4 11h16" />
        <path d="M12 3a8 8 0 0 1 0 16" />
        <path d="M12 3a8 8 0 0 0 0 16" />
        <rect x="8.5" y="15.5" width="7" height="5" rx="1" fill="currentColor" stroke="none" />
        <path d="M10 15.5V14a2 2 0 0 1 4 0v1.5" />
      </svg>
    </span>
  );
}
