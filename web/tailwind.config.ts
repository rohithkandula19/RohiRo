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
        ink: {
          DEFAULT: "var(--ink)",
          muted: "var(--ink-muted)",
          subtle: "var(--ink-subtle)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          soft: "var(--accent-soft)",
          ink: "var(--accent-ink)",
        },
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        line: {
          DEFAULT: "var(--line)",
          subtle: "var(--line-subtle)",
        },
      },
      fontFamily: {
        serif: ['"Iowan Old Style"', "Charter", "Georgia", "serif"],
        sans: ["-apple-system", "Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", '"SF Mono"', "Menlo", "monospace"],
      },
      letterSpacing: {
        kicker: "0.14em",
      },
      fontSize: {
        kicker: ["11px", { lineHeight: "1.4" }],
        body: ["14px", { lineHeight: "1.7" }],
      },
      borderRadius: {
        card: "8px",
        button: "6px",
        chip: "3px",
      },
      borderWidth: {
        hair: "0.5px",
      },
      transitionDuration: {
        page: "150ms",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
