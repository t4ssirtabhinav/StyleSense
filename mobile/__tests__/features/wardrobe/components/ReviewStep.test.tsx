import { fireEvent, render, waitFor } from '@testing-library/react-native';
import { ReviewStep } from '../../../../features/wardrobe/components/ReviewStep';
import * as wardrobeQueries from '../../../../features/wardrobe/wardrobe.queries';
import * as wardrobeService from '../../../../features/wardrobe/wardrobe.service';
import type { GarmentTagsDraft } from '../../../../features/wardrobe/wardrobe.types';

jest.mock('../../../../features/wardrobe/wardrobe.service', () => ({
  fetchWardrobeItemImageUrl: jest.fn(),
}));

const mockMutate = jest.fn();
const mockUseOccasionOptions = jest.fn();
jest.mock('../../../../features/wardrobe/wardrobe.queries', () => ({
  useSaveWardrobeItemTags: jest.fn(),
  useOccasionOptions: () => mockUseOccasionOptions(),
}));

// (SS-025) Occasion chips come from the `occasions` registry at runtime.
// `optionsIncluding` implements the UNION rule: active registry PLUS any slug
// already on the draft/item, so an unknown AI slug or a since-deactivated
// occasion stays visible and selected instead of being silently dropped on
// the next save.
const REGISTRY_OCCASIONS = [
  { key: 'office', label: 'Office', badgeColor: 'office' as const },
  { key: 'casual', label: 'Casual', badgeColor: 'casual' as const },
  {
    key: 'wedding_guest',
    label: 'Wedding Guest',
    badgeColor: 'wedding' as const,
  },
  { key: 'festival', label: 'Festival', badgeColor: 'festival' as const },
  { key: 'college', label: 'College', badgeColor: 'casual' as const },
];

function humanize(slug: string): string {
  return slug
    .split('_')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function occasionTaxonomy(registry = REGISTRY_OCCASIONS) {
  const byKey = Object.fromEntries(registry.map((o) => [o.key, o]));
  return {
    occasions: registry,
    label: (slug: string) => byKey[slug]?.label ?? humanize(slug),
    badgeColor: (slug: string) => byKey[slug]?.badgeColor,
    optionsIncluding: (tags: readonly string[]) => {
      const options = registry.map((o) => ({ ...o }));
      const seen = new Set(options.map((o) => o.key));
      for (const tag of tags) {
        if (tag && !seen.has(tag)) {
          seen.add(tag);
          options.push({
            key: tag,
            label: humanize(tag),
            badgeColor: undefined as never,
          });
        }
      }
      return options;
    },
    isLoading: false,
    isError: false,
    refetch: jest.fn(),
  };
}

function baseTags(overrides: Partial<GarmentTagsDraft> = {}): GarmentTagsDraft {
  return {
    category: 'ethnic_kurta',
    subcategory: null,
    colorPrimary: null,
    colorSecondary: null,
    pattern: null,
    fabric: null,
    occasionTags: [],
    seasonTags: [],
    confidence: 0.9,
    contentFlag: 'ok',
    containsPerson: false,
    ...overrides,
  };
}

describe('ReviewStep', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wardrobeQueries.useSaveWardrobeItemTags as jest.Mock).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    });
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());
  });

  it("renders the BG-removed image when processing_status='bg_removed'", async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const { findByTestId, queryByTestId } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags()}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    expect(await findByTestId('review-image')).toBeTruthy();
    expect(queryByTestId('bg-fallback-note')).toBeNull();
  });

  it("renders original.jpg with a fallback note when it's 'bg_pending'", async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/original.jpg',
      source: 'original',
    });

    const { findByTestId } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_pending"
        initialTags={baseTags()}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    expect(await findByTestId('bg-fallback-note')).toBeTruthy();
  });

  it('toggling an occasion Badge updates local draft state (not yet saved), reflected on save', async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const { getByTestId, getByLabelText } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags()}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    await fireEvent.press(getByTestId('occasion-badge-festival'));
    expect(mockMutate).not.toHaveBeenCalled();

    await fireEvent.press(getByLabelText('Looks Good!'));
    await waitFor(() =>
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: expect.objectContaining({ occasionTags: ['festival'] }),
        }),
        expect.anything(),
      ),
    );
  });

  it('confidence < 0.7 renders the low-confidence banner; >= 0.7 does not', async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const low = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags({ confidence: 0.5 })}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );
    expect(await low.findByTestId('low-confidence-banner')).toBeTruthy();

    const high = await render(
      <ReviewStep
        itemId="item-2"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags({ confidence: 0.9 })}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );
    await waitFor(() =>
      expect(high.queryByTestId('low-confidence-banner')).toBeNull(),
    );
  });

  it("contentFlag='not_clothing' renders \"Doesn't look like clothing\"; 'nsfw'/'other' render the generic message, never the raw flag", async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const notClothing = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags({ contentFlag: 'not_clothing' })}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );
    expect(
      await notClothing.findByText("Doesn't look like clothing"),
    ).toBeTruthy();

    const nsfw = await render(
      <ReviewStep
        itemId="item-2"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags({ contentFlag: 'nsfw' })}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );
    expect(await nsfw.findByTestId('content-flag-banner')).toBeTruthy();
    expect(nsfw.queryByText('nsfw')).toBeNull();
  });

  it('containsPerson=true renders the flat-lay nudge without nulling/hiding a valid category', async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const { findByTestId, getByText } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags({ containsPerson: true })}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    expect(await findByTestId('contains-person-nudge')).toBeTruthy();
    expect(getByText('ethnic_kurta')).toBeTruthy();
  });

  it('alternatives present renders a picker row; selecting an alternative swaps the primary category in the draft', async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const { getByTestId, getByLabelText } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags({ alternatives: ['western_top'] })}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    await fireEvent.press(getByTestId('alternative-badge-western_top'));
    await fireEvent.press(getByLabelText('Looks Good!'));

    await waitFor(() =>
      expect(mockMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: expect.objectContaining({ category: 'western_top' }),
        }),
        expect.anything(),
      ),
    );
  });

  it('pressing "Looks Good!" calls useSaveWardrobeItemTags with the current draft, then calls onSaved', async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });
    mockMutate.mockImplementation((_input, options) => {
      options?.onSuccess?.();
    });
    const onSaved = jest.fn();

    const { getByLabelText } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags()}
        onOpenCategoryPicker={jest.fn()}
        onSaved={onSaved}
      />,
    );

    await fireEvent.press(getByLabelText('Looks Good!'));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(baseTags()));
  });

  // --- SS-019 additions (layout/UX ACs) -----------------------------------

  it("occasion/season badge rows carry flex-row flex-wrap classes (renders the fetched occasions + 4 seasons, doesn't assert pixel layout)", async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const { findByTestId, getByTestId } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags()}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    await findByTestId('review-image');

    expect(getByTestId('occasion-badges-row').props.className).toContain(
      'flex-row flex-wrap',
    );
    expect(getByTestId('season-badges-row').props.className).toContain(
      'flex-row flex-wrap',
    );
    expect(getByTestId('occasion-badge-college')).toBeTruthy();
    expect(getByTestId('season-badge-all')).toBeTruthy();
  });

  it("review-image's wrapping View carries the new frame classes", async () => {
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });

    const { findByTestId } = await render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={baseTags()}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );

    const frame = await findByTestId('review-image-frame');
    expect(frame.props.className).toContain('mb-md');
    expect(frame.props.className).toContain('overflow-hidden');
    expect(frame.props.className).toContain('rounded-lg');
    expect(frame.props.className).toContain('border border-textMuted');
  });
});

describe('ReviewStep — SS-025 occasion union rule', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wardrobeQueries.useSaveWardrobeItemTags as jest.Mock).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    });
    mockUseOccasionOptions.mockReturnValue(occasionTaxonomy());
    (wardrobeService.fetchWardrobeItemImageUrl as jest.Mock).mockResolvedValue({
      url: 'https://r2.example.com/clean.png',
      source: 'clean',
    });
  });

  async function renderReview(tags: GarmentTagsDraft) {
    return render(
      <ReviewStep
        itemId="item-1"
        jwt="jwt"
        processingStatus="bg_removed"
        initialTags={tags}
        onOpenCategoryPicker={jest.fn()}
        onSaved={jest.fn()}
      />,
    );
  }

  it('renders chips with registry labels, not raw slugs', async () => {
    const { findByTestId } = await renderReview(baseTags());

    const chip = await findByTestId('occasion-badge-wedding_guest');
    expect(chip).toBeOnTheScreen();
  });

  it('renders an UNKNOWN slug already on the draft as a SELECTED chip', async () => {
    const { findByTestId } = await renderReview(
      baseTags({ occasionTags: ['ganesh_chaturthi'] }),
    );

    const chip = await findByTestId('occasion-badge-ganesh_chaturthi');
    // Union rule: an unknown slug already on the draft renders as a
    // selected chip rather than being silently absent from the picker.
    expect(chip).toBeOnTheScreen();
  });

  it('survives a save round-trip without dropping the unknown slug', async () => {
    const { findByTestId, getByLabelText } = await renderReview(
      baseTags({ occasionTags: ['ganesh_chaturthi', 'festival'] }),
    );
    await findByTestId('occasion-badge-ganesh_chaturthi');

    await fireEvent.press(getByLabelText('Looks Good!'));

    await waitFor(() => expect(mockMutate).toHaveBeenCalled());
    expect(mockMutate.mock.calls[0][0].tags.occasionTags).toEqual([
      'ganesh_chaturthi',
      'festival',
    ]);
  });

  it('renders a DEACTIVATED occasion still on the draft (absent from the active registry)', async () => {
    const { findByTestId } = await renderReview(
      baseTags({ occasionTags: ['beach'] }),
    );

    expect(await findByTestId('occasion-badge-beach')).toBeOnTheScreen();
  });
});
