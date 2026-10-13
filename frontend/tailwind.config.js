/** Design tokens. Ivory canvas, forest green for action, marigold for highlights, terracotta for alerts. */
const INDIC = ["Noto Sans Devanagari Variable", "Noto Sans Kannada Variable", "Noto Sans Tamil Variable", "Noto Sans Telugu Variable",
  "Noto Sans Malayalam Variable", "Noto Sans Bengali Variable", "Noto Sans Gujarati Variable", "Noto Sans Gurmukhi Variable"];

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#faf6ee", rail: "#f2ebdc", line: "#e9e0cc", "line-strong": "#d6cab0",
        ink: { DEFAULT: "#1c2a23", 2: "#485850", 3: "#76827b" },
        brand: { DEFAULT: "#166a4d", hover: "#0f5239", soft: "#e2f0e8", ink: "#0e4b36" },
        sun: { DEFAULT: "#e8a317", soft: "#fdf0cf", ink: "#6f4a00" },
        bad: { DEFAULT: "#b3412a", soft: "#fbe9e3" },
      },
      fontFamily: {
        sans: ["IBM Plex Sans Variable", ...INDIC, "system-ui", "sans-serif"],
        display: ['"Source Serif 4 Variable"', "Georgia", ...INDIC, "serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(60,45,10,.05), 0 10px 28px -12px rgba(60,45,10,.14)",
        lift: "0 2px 4px rgba(60,45,10,.06), 0 18px 36px -14px rgba(60,45,10,.22)",
        orb: "0 10px 30px -8px rgba(22,106,77,.55)",
      },
      keyframes: {
        rise: { from: { opacity: 0, transform: "translateY(10px)" }, to: { opacity: 1, transform: "none" } },
        shimmer: { to: { backgroundPosition: "-200% 0" } },
        halo: { "0%": { transform: "scale(1)", opacity: 0.35 }, "100%": { transform: "scale(1.75)", opacity: 0 } },
      },
      animation: {
        rise: "rise .45s cubic-bezier(.2,.7,.2,1) both", shimmer: "shimmer 1.6s linear infinite",
        halo: "halo 2.6s ease-out infinite", "halo-fast": "halo 1.2s ease-out infinite",
      },
    },
  },
};
