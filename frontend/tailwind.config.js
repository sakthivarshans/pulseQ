/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: "class",
    theme: {
        extend: {
            colors: {
                // NeuralOps brand palette
                neural: {
                    50: "#f0f4ff",
                    100: "#e0e9ff",
                    200: "#b8ceff",
                    300: "#7aa9ff",
                    400: "#3d80ff",
                    500: "#0d5eff",
                    600: "#0047e8",
                    700: "#0038c0",
                    800: "#00299a",
                    900: "#001a73",
                },
                surface: {
                    950: "#060811",
                    900: "#0b0f1c",
                    800: "#111827",
                    700: "#1a2338",
                    600: "#222d48",
                    500: "#2a3855",
                },
                success: { DEFAULT: "#22c55e", dark: "#16a34a" },
                warning: { DEFAULT: "#f59e0b", dark: "#d97706" },
                danger: { DEFAULT: "#ef4444", dark: "#dc2626" },
                critical: { DEFAULT: "#7c3aed", dark: "#6d28d9" },
            },
            fontFamily: {
                sans: ["Inter", "system-ui", "sans-serif"],
                mono: ["JetBrains Mono", "Fira Code", "monospace"],
            },
            animation: {
                "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                "fade-in": "fadeIn 0.3s ease-in-out",
                "slide-in-right": "slideInRight 0.3s ease-in-out",
                "slide-in-up": "slideInUp 0.3s ease-in-out",
                "glow": "glow 2s ease-in-out infinite alternate",
                "spin-slow": "spin 4s linear infinite",
            },
            keyframes: {
                fadeIn: {
                    "0%": { opacity: "0" },
                    "100%": { opacity: "1" },
                },
                slideInRight: {
                    "0%": { transform: "translateX(20px)", opacity: "0" },
                    "100%": { transform: "translateX(0)", opacity: "1" },
                },
                slideInUp: {
                    "0%": { transform: "translateY(20px)", opacity: "0" },
                    "100%": { transform: "translateY(0)", opacity: "1" },
                },
                glow: {
                    "0%": { boxShadow: "0 0 5px rgba(13, 94, 255, 0.3)" },
                    "100%": { boxShadow: "0 0 20px rgba(13, 94, 255, 0.8), 0 0 40px rgba(13, 94, 255, 0.3)" },
                },
            },
            backgroundImage: {
                "grid-pattern": "url(\"data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%230d5eff' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E\")",
                "radial-neural": "radial-gradient(ellipse at top left, rgba(13,94,255,0.08) 0%, transparent 60%)",
            },
            boxShadow: {
                "neural": "0 0 0 1px rgba(13, 94, 255, 0.3), 0 4px 16px rgba(13, 94, 255, 0.15)",
                "neural-lg": "0 0 0 1px rgba(13, 94, 255, 0.4), 0 8px 32px rgba(13, 94, 255, 0.2)",
                "card": "0 1px 3px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.2)",
                "card-hover": "0 4px 16px rgba(0,0,0,0.4), 0 8px 32px rgba(0,0,0,0.2)",
            },
            borderRadius: {
                xl: "0.875rem",
                "2xl": "1rem",
                "3xl": "1.5rem",
            },
        },
    },
    plugins: [],
};
