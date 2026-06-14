/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#E76B38",
          50:  "#FEF3EE",
          100: "#FDE4D3",
          200: "#FBC5A6",
          300: "#F8A070",
          400: "#F47B41",
          500: "#E76B38",
          600: "#D85D2B",
          700: "#B94A1E",
          800: "#963B18",
          900: "#7A3015",
        },
        surface: {
          DEFAULT: "#F8F9FA",
          card:    "#FFFFFF",
          border:  "#E5E7EB",
        },
        ink: {
          DEFAULT: "#1F2937",
          secondary: "#6B7280",
          muted:     "#9CA3AF",
          disabled:  "#D1D5DB",
        },
        sidebar: {
          bg:     "#111827",
          hover:  "#1F2937",
          active: "#E76B38",
          text:   "#9CA3AF",
          textHover: "#F9FAFB",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card:       "0 1px 3px 0 rgba(0,0,0,0.06), 0 1px 2px -1px rgba(0,0,0,0.06)",
        "card-md":  "0 4px 12px 0 rgba(0,0,0,0.08)",
        "card-lg":  "0 10px 30px 0 rgba(0,0,0,0.10)",
        brand:      "0 4px 14px 0 rgba(231,107,56,0.35)",
        "brand-sm": "0 2px 8px 0 rgba(231,107,56,0.25)",
      },
      borderRadius: {
        DEFAULT: "0.5rem",
        lg: "0.75rem",
        xl: "1rem",
        "2xl": "1.25rem",
      },
      animation: {
        "fade-in":    "fadeIn 0.2s ease-out",
        "slide-up":   "slideUp 0.3s ease-out",
        "slide-right":"slideRight 0.3s ease-out",
      },
      keyframes: {
        fadeIn:     { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp:    { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        slideRight: { "0%": { opacity: "0", transform: "translateX(16px)" }, "100%": { opacity: "1", transform: "translateX(0)" } },
      },
    },
  },
  plugins: [],
}
