import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-hover": "var(--surface-hover)",
        sidebar: "var(--sidebar)",
        ink: {
          DEFAULT: "var(--ink)",
          muted: "var(--ink-muted)",
          subtle: "var(--ink-subtle)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          soft: "var(--accent-soft)",
          ink: "var(--accent-ink)",
        },
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        line: {
          DEFAULT: "var(--line)",
          strong: "var(--line-strong)",
        },
      },
      fontFamily: {
        sans: ['"Inter"', "-apple-system", "system-ui", "sans-serif"],
        serif: ['"Inter"', "-apple-system", "system-ui", "sans-serif"],
        mono: ['ui-monospace', '"SF Mono"', "Menlo", "monospace"],
      },
      borderRadius: {
        card: "8px",
        button: "6px",
        chip: "4px",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
