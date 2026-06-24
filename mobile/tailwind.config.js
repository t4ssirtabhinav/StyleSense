module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        brand: '#E8A420',
        dark: '#1A1714',
        peacock: '#0D6B6E',
        emerald: '#2D6A4F',
        rose: '#C45B7C',
      },
    },
  },
  plugins: [],
};
