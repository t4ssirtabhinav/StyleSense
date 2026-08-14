// SS-022 — pure weather-chip copy formatting, split out from the component
// specifically so the copy is unit-testable without rendering (design §7).

import {
  WEATHER_CHIP_PREFIX,
  WEATHER_CONDITION_LABELS,
} from './outfit-ai.constants';
import type { WeatherResponse } from './outfit-ai.types';

export function formatWeatherChipLabel(
  weather: Pick<WeatherResponse, 'temp_c' | 'condition'>,
): string {
  return `${WEATHER_CHIP_PREFIX} ${Math.round(weather.temp_c)}°C, ${WEATHER_CONDITION_LABELS[weather.condition]}`;
}
