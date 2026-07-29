/**
 * SS-025 — pure occasion-registry helpers.
 *
 * The normalisation contract (design doc §3.6) is implemented THREE times:
 * here, in `public.occasion_normalize_one`
 * (supabase/migrations/007_occasions_registry.sql), and in
 * `backend/services/occasion_normalizer.py`. The same case table is asserted
 * in `backend/tests/test_occasion_normalizer.py` so the three cannot drift
 * silently.
 */
import {
  BADGE_OCCASION_KEYS,
  activeOccasionsPlus,
  humanizeOccasionSlug,
  normalizeOccasionSlug,
  normalizeOccasionTags,
  occasionAppliesTo,
  occasionBadgeColor,
  occasionLabel,
  occasionAppliesTo as predicate,
  resolveOccasionKey,
  topLevelOccasions,
} from '../../../features/onboarding/onboarding.occasions';
import type {
  OccasionOption,
  OnboardingTaxonomies,
} from '../../../features/onboarding/onboarding.types';

function occasion(
  key: string,
  overrides: Partial<OccasionOption> = {},
): OccasionOption {
  return {
    key,
    label: humanizeOccasionSlug(key),
    sortOrder: 1,
    badgeColor: 'casual',
    kind: 'everyday',
    parentKey: null,
    regionScope: null,
    cultureScope: null,
    ...overrides,
  };
}

// The 12 seeded registry rows plus the 8 seeded aliases (007's seed block).
function snapshot(
  overrides: Partial<OnboardingTaxonomies> = {},
): OnboardingTaxonomies {
  return {
    styleKeywords: [],
    colourPalette: [],
    isStale: false,
    occasions: [
      occasion('office', {
        label: 'Office',
        badgeColor: 'office',
        kind: 'professional',
        sortOrder: 1,
      }),
      occasion('casual', { label: 'Casual', sortOrder: 2 }),
      occasion('date_night', {
        label: 'Date Night',
        badgeColor: 'wedding',
        kind: 'social',
        sortOrder: 3,
      }),
      occasion('wedding_guest', {
        label: 'Wedding Guest',
        badgeColor: 'wedding',
        kind: 'ceremony',
        sortOrder: 4,
      }),
      occasion('festival', {
        label: 'Festival',
        badgeColor: 'festival',
        kind: 'festival',
        sortOrder: 5,
      }),
      occasion('puja', {
        label: 'Puja',
        badgeColor: 'festival',
        kind: 'religious',
        sortOrder: 6,
      }),
      occasion('party', {
        label: 'Party',
        badgeColor: 'festival',
        kind: 'social',
        sortOrder: 7,
      }),
      occasion('travel', { label: 'Travel', kind: 'travel', sortOrder: 8 }),
      occasion('workout', { label: 'Workout', kind: 'sport', sortOrder: 9 }),
      occasion('beach', { label: 'Beach', kind: 'travel', sortOrder: 10 }),
      occasion('formal_event', {
        label: 'Formal Event',
        badgeColor: 'wedding',
        kind: 'ceremony',
        sortOrder: 11,
      }),
      occasion('college', { label: 'College', sortOrder: 12 }),
    ],
    occasionAliases: [
      { alias: 'wedding', occasionKey: 'wedding_guest' },
      { alias: 'date', occasionKey: 'date_night' },
      { alias: 'work', occasionKey: 'office' },
      { alias: 'gym', occasionKey: 'workout' },
      { alias: 'pooja', occasionKey: 'puja' },
      { alias: 'vacation', occasionKey: 'travel' },
      { alias: 'formal', occasionKey: 'formal_event' },
      { alias: 'everyday', occasionKey: 'casual' },
    ],
    ...overrides,
  };
}

describe('normalizeOccasionSlug (step 1 of the contract)', () => {
  it.each([
    ['casual', 'casual'],
    ['  Wedding Guest ', 'wedding_guest'],
    ['Wedding Guest!!', 'wedding_guest'],
    ['Ganesh-Chaturthi', 'ganesh_chaturthi'],
    ['date   night', 'date_night'],
    ['DATE_NIGHT', 'date_night'],
    ['', ''],
    ['   ', ''],
    ['!!!', ''],
  ])('normalises %p to %p', (raw, expected) => {
    expect(normalizeOccasionSlug(raw)).toBe(expected);
  });
});

describe('resolveOccasionKey (steps 2-4)', () => {
  it('passes a canonical key through unchanged', () => {
    expect(resolveOccasionKey('wedding_guest', snapshot())).toBe(
      'wedding_guest',
    );
  });

  it('maps the two load-bearing aliases to their canonical keys', () => {
    expect(resolveOccasionKey('wedding', snapshot())).toBe('wedding_guest');
    expect(resolveOccasionKey('date', snapshot())).toBe('date_night');
  });

  it('normalises shape before the alias lookup', () => {
    expect(resolveOccasionKey('  Wedding ', snapshot())).toBe('wedding_guest');
  });

  it('keeps an unknown slug rather than dropping it', () => {
    expect(resolveOccasionKey('Ganesh Chaturthi', snapshot())).toBe(
      'ganesh_chaturthi',
    );
  });

  it('resolves a key/alias collision to the canonical key (resolution order)', () => {
    const colliding = snapshot({
      occasionAliases: [
        ...snapshot().occasionAliases,
        { alias: 'festival', occasionKey: 'party' },
      ],
    });
    expect(resolveOccasionKey('festival', colliding)).toBe('festival');
  });

  it('degrades to shape-only normalisation with no snapshot, never throwing', () => {
    expect(resolveOccasionKey('  Wedding Guest ', undefined)).toBe(
      'wedding_guest',
    );
    expect(resolveOccasionKey('wedding', undefined)).toBe('wedding');
  });
});

describe('normalizeOccasionTags', () => {
  it('dedupes preserving first-occurrence order and never sorts', () => {
    expect(
      normalizeOccasionTags(
        ['travel', 'wedding', 'Travel', 'wedding_guest', 'casual'],
        snapshot(),
      ),
    ).toEqual(['travel', 'wedding_guest', 'casual']);
  });

  it('drops entries that normalise to nothing but keeps unknown slugs', () => {
    expect(
      normalizeOccasionTags(['', '   ', '!!!', 'Sangeet Night'], snapshot()),
    ).toEqual(['sangeet_night']);
  });

  it('returns an empty array for an empty input', () => {
    expect(normalizeOccasionTags([], snapshot())).toEqual([]);
  });
});

describe('occasionLabel', () => {
  it('returns the registry label', () => {
    expect(occasionLabel('wedding_guest', snapshot())).toBe('Wedding Guest');
  });

  it('falls back to the humanised slug for an unknown slug', () => {
    expect(occasionLabel('ganesh_chaturthi', snapshot())).toBe(
      'Ganesh Chaturthi',
    );
  });

  it('falls back to the humanised slug when there is no snapshot at all', () => {
    expect(occasionLabel('wedding_guest', undefined)).toBe('Wedding Guest');
  });
});

describe('occasionBadgeColor', () => {
  it('returns the registry token', () => {
    expect(occasionBadgeColor('office', snapshot())).toBe('office');
    expect(occasionBadgeColor('wedding_guest', snapshot())).toBe('wedding');
  });

  it('returns undefined (neutral) for a slug not in the snapshot', () => {
    expect(occasionBadgeColor('ganesh_chaturthi', snapshot())).toBeUndefined();
  });

  it('returns undefined for a badge_color outside Badge’s four keys', () => {
    const widened = snapshot({
      occasions: [
        occasion('mystery', {
          badgeColor: 'chartreuse' as OccasionOption['badgeColor'],
        }),
      ],
    });
    expect(occasionBadgeColor('mystery', widened)).toBeUndefined();
  });

  it('exposes exactly the four Badge occasion tokens', () => {
    expect([...BADGE_OCCASION_KEYS]).toEqual([
      'wedding',
      'office',
      'festival',
      'casual',
    ]);
  });
});

describe('topLevelOccasions', () => {
  it('returns all 12 seeded rows (every seed is top-level)', () => {
    expect(topLevelOccasions(snapshot())).toHaveLength(12);
  });

  it('excludes rows with a parentKey, so a child occasion never floods onboarding', () => {
    const withChild = snapshot({
      occasions: [
        ...snapshot().occasions,
        occasion('ganesh_chaturthi', {
          label: 'Ganesh Chaturthi',
          parentKey: 'festival',
        }),
      ],
    });

    const keys = topLevelOccasions(withChild).map((option) => option.key);
    expect(keys).toHaveLength(12);
    expect(keys).not.toContain('ganesh_chaturthi');
  });

  it('returns an empty array with no snapshot', () => {
    expect(topLevelOccasions(undefined)).toEqual([]);
  });
});

describe('activeOccasionsPlus (the union rule)', () => {
  it('includes an unknown slug exactly once, at the end, humanised and neutral', () => {
    const options = activeOccasionsPlus(['ganesh_chaturthi'], snapshot());

    expect(options).toHaveLength(13);
    const last = options[options.length - 1];
    expect(last.key).toBe('ganesh_chaturthi');
    expect(last.label).toBe('Ganesh Chaturthi');
    expect(last.badgeColor).toBeUndefined();
    expect(options.filter((o) => o.key === 'ganesh_chaturthi')).toHaveLength(1);
  });

  it('does not duplicate a tag that is already in the registry', () => {
    const options = activeOccasionsPlus(['festival', 'casual'], snapshot());
    expect(options).toHaveLength(12);
  });

  it('surfaces a deactivated occasion the item still carries', () => {
    // A deactivated row is absent from the fetched (active-only) snapshot,
    // so it arrives here purely via the union.
    const options = activeOccasionsPlus(['beach_bonfire'], snapshot());
    expect(options.map((o) => o.key)).toContain('beach_bonfire');
  });

  it('carries the registry badge colour through for known occasions', () => {
    const options = activeOccasionsPlus([], snapshot());
    expect(options.find((o) => o.key === 'office')?.badgeColor).toBe('office');
    expect(options.find((o) => o.key === 'wedding_guest')?.badgeColor).toBe(
      'wedding',
    );
  });

  it('returns just the extra tags when there is no snapshot', () => {
    expect(activeOccasionsPlus(['casual'], undefined)).toEqual([
      { key: 'casual', label: 'Casual' },
    ]);
  });
});

describe('occasionAppliesTo (null means UNIVERSAL, not "no regions")', () => {
  it('matches every user region when regionScope is null', () => {
    const universal = occasion('festival');
    expect(predicate(universal, { region: 'maharashtra' })).toBe(true);
    expect(predicate(universal, { region: 'kerala' })).toBe(true);
    expect(predicate(universal, { region: null })).toBe(true);
    expect(predicate(universal, {})).toBe(true);
  });

  it('matches only listed regions when regionScope is populated', () => {
    const scoped = occasion('onam', { regionScope: ['kerala'] });
    expect(occasionAppliesTo(scoped, { region: 'kerala' })).toBe(true);
    expect(occasionAppliesTo(scoped, { region: 'punjab' })).toBe(false);
    expect(occasionAppliesTo(scoped, { region: null })).toBe(false);
  });

  it('applies the same null semantics to cultureScope', () => {
    const scoped = occasion('eid', { cultureScope: ['muslim'] });
    expect(
      occasionAppliesTo(scoped, { region: 'delhi', culture: 'muslim' }),
    ).toBe(true);
    expect(
      occasionAppliesTo(scoped, { region: 'delhi', culture: 'hindu' }),
    ).toBe(false);
  });
});

describe('humanizeOccasionSlug', () => {
  it('title-cases underscore-separated slugs', () => {
    expect(humanizeOccasionSlug('wedding_guest')).toBe('Wedding Guest');
    expect(humanizeOccasionSlug('puja')).toBe('Puja');
  });

  it('never produces stray spaces from repeated or trailing underscores', () => {
    expect(humanizeOccasionSlug('ganesh__chaturthi_')).toBe('Ganesh Chaturthi');
  });
});
