import { cleanup, render } from '@testing-library/react-native';
import { WeatherChip } from '../../../../features/outfit-ai/components/WeatherChip';
import type { WeatherResponse } from '../../../../features/outfit-ai/outfit-ai.types';

describe('WeatherChip', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the label when weather is present', async () => {
    const weather: WeatherResponse = {
      city: 'Mumbai',
      temp_c: 28.4,
      condition: 'partly_cloudy',
      humidity: 71,
      is_heavy_rain: false,
    };

    const { getByTestId, getByText } = await render(
      <WeatherChip weather={weather} />,
    );

    expect(getByTestId('weather-chip')).toBeOnTheScreen();
    expect(getByText('Dressing for 28°C, partly cloudy')).toBeOnTheScreen();
  });

  it('renders nothing when weather is null', async () => {
    const { queryByTestId } = await render(<WeatherChip weather={null} />);
    expect(queryByTestId('weather-chip')).toBeNull();
  });
});
