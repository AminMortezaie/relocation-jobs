import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "bg-base": "var(--bg-base)",
        "bg-surface": "var(--bg-surface)",
        "bg-surface-hover": "var(--bg-surface-hover)",
        "border-subtle": "var(--border-subtle)",
        "border-hover": "var(--border-hover)",
        "accent-primary": "var(--accent-primary)",
        "accent-primary-hover": "var(--accent-primary-hover)",
        "accent-blue": "var(--accent-blue)",
        "accent-purple": "var(--accent-purple)",
        "accent-green": "var(--accent-green)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-muted": "var(--text-muted)",
        "text-on-accent": "var(--text-on-accent)",
        bg: "var(--bg-base)",
        "bg-elevated": "var(--bg-surface)",
        surface: "var(--bg-surface)",
        surface2: "var(--bg-surface-hover)",
        text: "var(--text-primary)",
        muted: "var(--text-muted)",
        accent: "var(--accent-primary)",
        "accent-hover": "var(--accent-primary-hover)",
        success: "var(--accent-green)",
        warn: "var(--warn)",
        danger: "var(--text-muted)",
        visa: "var(--accent-purple)",
        referral: "var(--accent-blue)",
        "brand-sky": "var(--accent-blue)",
      },
      fontFamily: {
        sans: ["var(--font-body)", "Manrope", "system-ui", "sans-serif"],
        display: [
          "var(--font-display)",
          "Lexend",
          "system-ui",
          "sans-serif",
        ],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        app: "0.25rem",
        "app-sm": "0.25rem",
      },
      boxShadow: {
        app: "var(--shadow-card)",
        "app-sm": "var(--shadow-sm)",
        header: "var(--shadow-card)",
      },
      maxWidth: {
        site: "67.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
