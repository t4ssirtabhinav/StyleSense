import { fireEvent, render } from '@testing-library/react-native';
import { FootwearSection } from '../../../../features/outfit-ai/components/FootwearSection';
import {
  ADD_FOOTWEAR_CTA,
  FOOTWEAR_MISMATCH_HEADING,
  FOOTWEAR_SECTION_HEADING,
  MISSING_FOOTWEAR_HEADING,
} from '../../../../features/outfit-ai/outfit-ai.constants';
import type { PortfolioItemResponse } from '../../../../features/outfit-ai/outfit-ai.types';
import { useWardrobeFilterStore } from '../../../../features/wardrobe/wardrobe.store';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockOutfitItemStackRender = jest.fn();
jest.mock('../../../../features/outfit-ai/components/OutfitItemStack', () => ({
  OutfitItemStack: (props: unknown) => {
    mockOutfitItemStackRender(props);
    return null;
  },
}));

function item(
  overrides: Partial<PortfolioItemResponse> = {},
): PortfolioItemResponse {
  return {
    item_ids: ['top-1', 'bottom-1', 'shoe-1'],
    category_labels: {
      'top-1': 'ethnic_kurta',
      'bottom-1': 'western_bottom',
      'shoe-1': 'footwear_ethnic',
    },
    total_score: 0.8,
    rationale: 'A balanced ceremony look.',
    rationale_language: 'en',
    is_exploration: false,
    gap_flags: [],
    rank: 1,
    outfit_fingerprint: 'a'.repeat(64),
    ...overrides,
  };
}

describe('FootwearSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useWardrobeFilterStore.getState().reset();
  });

  it('renders the heading and exactly one thumbnail when footwear is present and gap_flags is empty', async () => {
    const { getByText, queryByTestId } = await render(
      <FootwearSection item={item()} />,
    );

    expect(getByText(FOOTWEAR_SECTION_HEADING)).toBeOnTheScreen();
    expect(mockOutfitItemStackRender).toHaveBeenCalledTimes(1);
    expect(mockOutfitItemStackRender).toHaveBeenCalledWith(
      expect.objectContaining({ itemIds: ['shoe-1'] }),
    );
    expect(queryByTestId('footwear-mismatch-nudge')).toBeNull();
  });

  it('renders the missing-footwear nudge and CTA, no thumbnail, when gap_flags contains missing_footwear', async () => {
    const { getByText, queryByText } = await render(
      <FootwearSection
        item={item({
          item_ids: ['top-1', 'bottom-1'],
          category_labels: {
            'top-1': 'ethnic_kurta',
            'bottom-1': 'western_bottom',
          },
          gap_flags: ['missing_footwear'],
        })}
      />,
    );

    expect(getByText(MISSING_FOOTWEAR_HEADING)).toBeOnTheScreen();
    expect(getByText(ADD_FOOTWEAR_CTA)).toBeOnTheScreen();
    expect(queryByText(FOOTWEAR_SECTION_HEADING)).toBeNull();
    expect(mockOutfitItemStackRender).not.toHaveBeenCalled();
  });

  it('renders the thumbnail AND the mismatch nudge when gap_flags contains footwear_formality_mismatch', async () => {
    const { getByText, getByTestId } = await render(
      <FootwearSection
        item={item({ gap_flags: ['footwear_formality_mismatch'] })}
      />,
    );

    expect(getByText(FOOTWEAR_SECTION_HEADING)).toBeOnTheScreen();
    expect(mockOutfitItemStackRender).toHaveBeenCalledWith(
      expect.objectContaining({ itemIds: ['shoe-1'] }),
    );
    expect(getByText(FOOTWEAR_MISMATCH_HEADING)).toBeOnTheScreen();
    expect(getByTestId('footwear-mismatch-nudge')).toBeOnTheScreen();
  });

  it('renders nothing when there is no footwear item and no footwear gap flag', async () => {
    const { queryByTestId } = await render(
      <FootwearSection
        item={item({
          item_ids: ['top-1', 'bottom-1'],
          category_labels: {
            'top-1': 'ethnic_kurta',
            'bottom-1': 'western_bottom',
          },
          gap_flags: [],
        })}
        testID="footwear-section"
      />,
    );

    expect(queryByTestId('footwear-section')).toBeNull();
    expect(mockOutfitItemStackRender).not.toHaveBeenCalled();
  });

  it('renders nothing when category_labels is empty (item deleted between suggestion and render)', async () => {
    const { queryByTestId } = await render(
      <FootwearSection
        item={item({ category_labels: {}, gap_flags: [] })}
        testID="footwear-section"
      />,
    );

    expect(queryByTestId('footwear-section')).toBeNull();
  });

  it('pressing "Add footwear" sets the wardrobe category filter to footwear and navigates to the wardrobe', async () => {
    const { getByText } = await render(
      <FootwearSection
        item={item({
          item_ids: ['top-1', 'bottom-1'],
          category_labels: {
            'top-1': 'ethnic_kurta',
            'bottom-1': 'western_bottom',
          },
          gap_flags: ['missing_footwear'],
        })}
      />,
    );

    fireEvent.press(getByText(ADD_FOOTWEAR_CTA));

    expect(useWardrobeFilterStore.getState().categoryFilter).toBe('footwear');
    expect(mockPush).toHaveBeenCalledWith('/(tabs)/wardrobe');
  });
});
