/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      spacing: {
        '0.2': '0.05rem',
        '4.5': '1.125rem', // 18px
        '6.5': '1.625rem', // 26px
        '8.5': '2.125rem', // 34px
        '9.5': '2.375rem', // 38px
        '13': '3.25rem',   // 52px
      },
      colors: {
        sidebar: '#f9f9fb',
        borderLight: '#ebecef',
        brand: {
          50: '#F0F9FF',
          100: '#E0F2FE',
          500: '#0284C7',
          600: '#0369A1',
          700: '#075985',
        }
      }
    },
  },
  plugins: [],
}
