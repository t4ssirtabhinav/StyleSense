// SS-022 — AC #4's chip: "Dressing for 28°C, partly cloudy". Wraps
// components/ui/Badge (never a bare View/Text, per CLAUDE.md). Renders
// nothing when `weather` is `null` — no placeholder, no skeleton, no
// "weather unavailable" copy. Silent absence is the designed degradation
// (a missing/unresolvable city, or Open-Meteo unreachable).

import { Badge } from '../../../components/ui';
import type { WeatherResponse } from '../outfit-ai.types';
import { formatWeatherChipLabel } from '../weather.format';

export interface WeatherChipProps {
  weather: WeatherResponse | null;
}

export function WeatherChip({ weather }: WeatherChipProps) {
  // `!weather` (not `=== null`) is deliberate belt-and-braces: a mocked or
  // legacy caller that omits the field entirely (`undefined`) degrades
  // exactly like an explicit `null`, never a crash on `.temp_c`.
  if (!weather) {
    return null;
  }

  return (
    <Badge
      testID="weather-chip"
      label={formatWeatherChipLabel(weather)}
      truncate={false}
    />
  );
}
