import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        command: {
          950: "#06080f",
          900: "#0a0f1a",
          850: "#0d1422",
          800: "#121b2c",
          700: "#1b2942"
        },
        signal: {
          cyan: "#38d6ff",
          teal: "#2dd4bf",
          amber: "#f6c453",
          red: "#ff4f64",
          violet: "#9a8cff"
        }
      },
      boxShadow: {
        glow: "0 0 45px rgba(56, 214, 255, 0.12)",
        alert: "0 0 28px rgba(255, 79, 100, 0.18)"
      },
      backgroundImage: {
        "radial-scan": "radial-gradient(circle at 50% 0%, rgba(56,214,255,0.18), transparent 34%), radial-gradient(circle at 85% 20%, rgba(246,196,83,0.08), transparent 28%)"
      }
    }
  },
  plugins: []
};

export default config;
