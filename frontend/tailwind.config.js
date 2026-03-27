/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Light corporate palette: grey spectrum + green accent
        surface: { DEFAULT: '#f8fafc', muted: '#f1f5f9', card: '#ffffff' },
        ink: { DEFAULT: '#334155', muted: '#64748b', subtle: '#94a3b8' },
        accent: { DEFAULT: '#047857', hover: '#059669', light: '#d1fae5' },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
