import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#090b10",
        "bg-elevated": "#0f1218",
        surface: "#141820",
        surface2: "#1a1f28",
        text: "#eef1f6",
        muted: "#8b93a3",
        accent: "#5b8def",
        "accent-hover": "#7aa8ff",
        success: "#34d399",
        warn: "#f5a623",
        danger: "#f87171",
        visa: "#a78bfa",
        referral: "#7aa8ff",
        "brand-sky": "#38bdf8",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        app: "16px",
        "app-sm": "10px",
      },
      boxShadow: {
        app: "0 12px 40px rgba(0, 0, 0, 0.35)",
        "app-sm": "0 4px 16px rgba(0, 0, 0, 0.22)",
        header: "0 16px 34px rgba(0, 0, 0, 0.22)",
      },
      maxWidth: {
        site: "67.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
