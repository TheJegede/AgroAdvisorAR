/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['selector', '[data-theme="hc"] &'],
  theme: {
    extend: {
      colors: {
        field: {
          DEFAULT: '#2D6A4F',
          light: '#40916C',
          dark: '#1B4332',
        },
        harvest: {
          DEFAULT: '#E9A228',
          light: '#F4C55A',
          dark: '#B57D1A',
        },
        arred: {
          DEFAULT: '#CC2936',
          light: '#E05561',
          dark: '#9B1E29',
        },
        terracotta: '#8B6B5E',
        parchment: '#F7F4EF',
        charcoal: '#1C1917',
        surface: '#FFFFFF',
        hc: {
          bg: '#FFFFFF',
          surface: '#FFFFFF',
          fg: '#000000',
          muted: '#1A1A1A',
          border: '#000000',
          accent: '#0033A0',
          'accent-fg': '#FFFFFF',
          danger: '#B00020',
          'danger-fg': '#FFFFFF',
          focus: '#FFD700',
          'sidebar-bg': '#000000',
          'sidebar-fg': '#FFFFFF',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      minHeight: {
        touch: '44px',
      },
      borderRadius: {
        card: '12px',
      },
    },
  },
  plugins: [],
}
