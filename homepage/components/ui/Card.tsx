import type { CSSProperties, ReactNode } from "react";

type CardProps = {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  accentBar?: boolean;
  interactive?: boolean;
  as?: "div" | "article" | "section";
};

export function Card({
  children,
  className = "",
  style,
  accentBar = false,
  interactive = false,
  as: Tag = "div",
}: CardProps) {
  return (
    <Tag
      className={`surface-card relative overflow-hidden rounded-app ${interactive ? "surface-card-interactive" : ""} ${className}`}
      style={style}
    >
      {accentBar ? (
        <span
          className="pointer-events-none absolute bottom-0 left-0 top-0 w-1 rounded-l-app bg-gradient-to-b from-brand-sky via-accent to-visa opacity-70"
          aria-hidden="true"
        />
      ) : null}
      {children}
    </Tag>
  );
}
