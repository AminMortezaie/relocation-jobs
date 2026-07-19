import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  children: ReactNode;
  className?: string;
  href?: string;
  as?: "button" | "a";
};

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary:
    "btn-primary inline-flex items-center justify-center rounded-app px-5 py-2.5 text-sm font-bold text-text-on-accent",
  secondary:
    "btn-secondary inline-flex items-center justify-center rounded-app px-5 py-2.5 text-sm font-semibold",
};

export function Button({
  variant = "primary",
  children,
  className = "",
  href,
  as,
  ...rest
}: ButtonProps) {
  const classes = `${VARIANT_CLASS[variant]} ${className}`;

  if (as === "a" || href) {
    return (
      <a href={href} className={classes}>
        {children}
      </a>
    );
  }

  return (
    <button type="button" className={classes} {...rest}>
      {children}
    </button>
  );
}
