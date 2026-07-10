import {
  colors,
  radii,
  spacing,
  typography,
} from '../../../components/ui/tokens';

describe('design tokens', () => {
  it('transcribes colour values verbatim from the design doc', () => {
    expect(colors.bg.primary).toBe('#FAFAF7');
    expect(colors.bg.secondary).toBe('#F4F2ED');
    expect(colors.bg.dark).toBe('#1A1714');
    expect(colors.accent.marigold).toBe('#E8A420');
    expect(colors.accent.peacock).toBe('#0D6B6E');
    expect(colors.accent.rose).toBe('#C45B7C');
    expect(colors.accent.emerald).toBe('#2D6A4F');
    expect(colors.text.primary).toBe('#1A1714');
    expect(colors.text.secondary).toBe('#5A5550');
    expect(colors.text.muted).toBe('#9A9590');
    expect(colors.occasion.wedding).toBe('#D4A574');
    expect(colors.occasion.office).toBe('#4A7FA5');
    expect(colors.occasion.festival).toBe('#E8A420');
    expect(colors.occasion.casual).toBe('#78A878');
  });

  it('exposes exactly one BL-007 error placeholder, not a real semantic error colour', () => {
    // BL-007 (docs/BACKLOG.md, Open): parked decision — this must stay a
    // clearly-named placeholder, not silently promoted to a real token.
    expect(colors.accent.errorPlaceholder).toBe('#D32F2F');
  });

  it('defines typography family names for all 5 typefaces', () => {
    expect(typography.display).toBe('Playfair Display');
    expect(typography.heading).toBe('Poppins');
    expect(typography.body).toBe('DM Sans');
    expect(typography.mono).toBe('JetBrains Mono');
    expect(typography.hindi).toBe('Noto Sans Devanagari');
  });

  it('defines exactly the 6 spacing keys with the exact numeric values', () => {
    expect(Object.keys(spacing).sort()).toEqual(
      ['lg', 'md', 'sm', 'xl', 'xs', 'xxl'].sort(),
    );
    expect(spacing).toEqual({ xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 });
  });

  it('defines exactly the 5 radii keys with the exact numeric values', () => {
    expect(Object.keys(radii).sort()).toEqual(
      ['lg', 'md', 'pill', 'sm', 'xl'].sort(),
    );
    expect(radii).toEqual({ sm: 8, md: 12, lg: 16, xl: 24, pill: 100 });
  });
});
