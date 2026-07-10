/**
 * Design token source of truth for StyleSense's `components/ui/` kit.
 * Transcribed verbatim from `docs/tickets/SS-008-design.md`'s "Concrete
 * values" section — do not restyle or invent new values here.
 *
 * `mobile/tailwind.config.js` mirrors these same hex values under flattened
 * key names (to avoid Tailwind's `bg-bg-*`/`text-text-*` class-name stutter)
 * — if a value here ever changes, update both files.
 */

export const colors = {
  bg: {
    primary: '#FAFAF7',
    secondary: '#F4F2ED',
    dark: '#1A1714',
  },
  accent: {
    marigold: '#E8A420',
    peacock: '#0D6B6E',
    rose: '#C45B7C',
    emerald: '#2D6A4F',
    // BL-007 (docs/BACKLOG.md, Open): the ticket's token set has no semantic
    // error/danger color — `accent.rose` above is explicitly scoped to the
    // beauty/makeup module, not general form validation. Per user decision,
    // this is a parked placeholder (Material red, a conventional stand-in),
    // named so BL-007's resolution is a one-line change here, not a hunt
    // through scattered magic hex values across components.
    errorPlaceholder: '#D32F2F',
  },
  text: {
    primary: '#1A1714',
    secondary: '#5A5550',
    muted: '#9A9590',
  },
  occasion: {
    wedding: '#D4A574',
    office: '#4A7FA5',
    festival: '#E8A420',
    casual: '#78A878',
  },
} as const;

export const typography = {
  display: 'Playfair Display',
  heading: 'Poppins',
  body: 'DM Sans',
  mono: 'JetBrains Mono',
  hindi: 'Noto Sans Devanagari',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;
export const radii = { sm: 8, md: 12, lg: 16, xl: 24, pill: 100 } as const;
