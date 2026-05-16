/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
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
