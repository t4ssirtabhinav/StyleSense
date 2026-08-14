import { WEATHER_CONDITION_LABELS } from '../../../features/outfit-ai/outfit-ai.constants';
import type { WeatherCondition } from '../../../features/outfit-ai/outfit-ai.types';
import { formatWeatherChipLabel } from '../../../features/outfit-ai/weather.format';

describe('formatWeatherChipLabel', () => {
  it("matches the ticket's own literal example string", () => {
    expect(
      formatWeatherChipLabel({ temp_c: 28.4, condition: 'partly_cloudy' }),
    ).toBe('Dressing for 28°C, partly cloudy');
  });

  it('rounds to the nearest whole degree, no decimals', () => {
    expect(formatWeatherChipLabel({ temp_c: 27.6, condition: 'clear' })).toBe(
      'Dressing for 28°C, clear',
    );
  });

  it('rounds down when the fraction is below .5', () => {
    expect(formatWeatherChipLabel({ temp_c: 27.4, condition: 'clear' })).toBe(
      'Dressing for 27°C, clear',
    );
  });

  const allConditions: WeatherCondition[] = [
    'clear',
    'partly_cloudy',
    'cloudy',
    'fog',
    'drizzle',
    'rain',
    'heavy_rain',
    'thunderstorm',
    'snow',
  ];

  it.each(allConditions)(
    'every WeatherCondition (%s) has a label — a future condition cannot silently render undefined',
    (condition) => {
      expect(WEATHER_CONDITION_LABELS[condition]).toEqual(expect.any(String));
      expect(formatWeatherChipLabel({ temp_c: 20, condition })).not.toContain(
        'undefined',
      );
    },
  );
});
