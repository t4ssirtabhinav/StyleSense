module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        // existing — unchanged, kept for backward compatibility
        brand: '#E8A420',
        dark: '#1A1714',
        peacock: '#0D6B6E',
        emerald: '#2D6A4F',
        rose: '#C45B7C',
        // new — flattened from components/ui/tokens.ts to avoid
        // `bg-bg-*`/`text-text-*` class-name stutter from nested keys
        surfacePrimary: '#FAFAF7', // = colors.bg.primary
        surfaceSecondary: '#F4F2ED', // = colors.bg.secondary
        textPrimary: '#1A1714', // = colors.text.primary (dupes `dark`, kept for discoverability)
        textSecondary: '#5A5550', // = colors.text.secondary
        textMuted: '#9A9590', // = colors.text.muted
        occasionWedding: '#D4A574',
        occasionOffice: '#4A7FA5',
        occasionFestival: '#E8A420', // dupes `brand` intentionally — same colour, different semantic name
        occasionCasual: '#78A878',
      },
      fontFamily: {
        display: ['PlayfairDisplay_400Regular'],
        'display-bold': ['PlayfairDisplay_700Bold'],
        heading: ['Poppins_400Regular'],
        'heading-semibold': ['Poppins_600SemiBold'],
        body: ['DMSans_400Regular'],
        'body-medium': ['DMSans_500Medium'],
        mono: ['JetBrainsMono_400Regular'],
        'mono-bold': ['JetBrainsMono_700Bold'],
        hindi: ['NotoSansDevanagari_400Regular'],
      },
      spacing: {
        xs: '4px',
        sm: '8px',
        md: '16px',
        lg: '24px',
        xl: '32px',
        xxl: '48px',
      },
      borderRadius: {
        sm: '8px',
        md: '12px',
        lg: '16px',
        xl: '24px',
        pill: '100px',
      },
    },
  },
  plugins: [],
};
