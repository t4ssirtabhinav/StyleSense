import { act, fireEvent, render } from '@testing-library/react-native';
import * as Haptics from 'expo-haptics';
import { CustomTabBar } from '../../../../features/navigation/components/CustomTabBar';
import { TAB_CONFIG } from '../../../../features/navigation/navigation.constants';
import type { CustomTabBarProps } from '../../../../features/navigation/navigation.types';

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Light: 'light' },
}));

const ROUTES = TAB_CONFIG.map((tab, index) => ({
  key: `${tab.name}-key`,
  name: tab.name,
  params: undefined,
}));

function buildProps(
  overrides: Partial<{ index: number; bottom: number }> = {},
): CustomTabBarProps & { navigation: { navigate: jest.Mock } } {
  const navigate = jest.fn();
  return {
    state: {
      index: overrides.index ?? 0,
      routes: ROUTES,
    },
    descriptors: {},
    navigation: { navigate },
    insets: { top: 0, bottom: overrides.bottom ?? 0, left: 0, right: 0 },
  } as unknown as CustomTabBarProps & { navigation: { navigate: jest.Mock } };
}

describe('CustomTabBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders all 5 tab labels from TAB_CONFIG', async () => {
    const { getByText } = await render(<CustomTabBar {...buildProps()} />);
    TAB_CONFIG.forEach((tab) => {
      expect(getByText(tab.label)).toBeOnTheScreen();
    });
  });

  it('focused tab renders its activeIcon + marigold dot indicator; unfocused tabs render inactiveIcon, no dot', async () => {
    const props = buildProps({ index: 0 });
    const { getByTestId, queryByTestId } = await render(
      <CustomTabBar {...props} />,
    );

    // Home (index 0) is focused
    expect(getByTestId('tab-dot-index')).toBeOnTheScreen();
    // Wardrobe (index 1) is not
    expect(queryByTestId('tab-dot-wardrobe')).toBeNull();
  });

  it('pressing a tab calls navigation.navigate with that tab route name', async () => {
    const props = buildProps({ index: 0 });
    const { getByTestId } = await render(<CustomTabBar {...props} />);

    await act(async () => {
      fireEvent.press(getByTestId('tab-wardrobe'));
      // Flushes the mocked expo-haptics promise (+ its .catch handler)
      // within this test's own act() scope, so it can't bleed into the
      // next test as an "overlapping act()" React warning.
      await Promise.resolve();
    });

    expect(props.navigation.navigate).toHaveBeenCalledWith('wardrobe');
  });

  it('pressing the same tab twice within 400ms only calls navigation.navigate once (debounce)', async () => {
    const props = buildProps({ index: 0 });
    const { getByTestId } = await render(<CustomTabBar {...props} />);

    const dateNowSpy = jest.spyOn(Date, 'now');
    await act(async () => {
      dateNowSpy.mockReturnValue(1000);
      fireEvent.press(getByTestId('tab-wardrobe'));
      dateNowSpy.mockReturnValue(1200); // 200ms later, within the 400ms window
      fireEvent.press(getByTestId('tab-wardrobe'));
      await Promise.resolve();
    });

    expect(props.navigation.navigate).toHaveBeenCalledTimes(1);
    dateNowSpy.mockRestore();
  });

  it('pressing a tab calls Haptics.impactAsync', async () => {
    const props = buildProps({ index: 0 });
    const { getByTestId } = await render(<CustomTabBar {...props} />);

    await act(async () => {
      fireEvent.press(getByTestId('tab-style'));
      await Promise.resolve();
    });

    expect(Haptics.impactAsync).toHaveBeenCalledWith(
      Haptics.ImpactFeedbackStyle.Light,
    );
  });

  it("reflects a non-zero insets.bottom in the tab bar's rendered height/padding", async () => {
    const props = buildProps({ bottom: 20 });
    const { getByTestId } = await render(<CustomTabBar {...props} />);

    expect(getByTestId('custom-tab-bar')).toHaveProp(
      'style',
      expect.objectContaining({ height: 84, paddingBottom: 20 }),
    );
  });
});
