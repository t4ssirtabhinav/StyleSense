import {
  DMSans_400Regular,
  DMSans_500Medium,
} from '@expo-google-fonts/dm-sans';
import {
  JetBrainsMono_400Regular,
  JetBrainsMono_700Bold,
} from '@expo-google-fonts/jetbrains-mono';
import { NotoSansDevanagari_400Regular } from '@expo-google-fonts/noto-sans-devanagari';
/**
 * Centralises the `@expo-google-fonts/*` imports mapped to the exact
 * family-constant keys `expo-font`'s `useFonts` expects. Imported once by
 * `app/_layout.tsx` so no other screen needs to know the raw font-constant
 * names — see docs/tickets/SS-008-design.md's "Font loading" section.
 *
 * One Regular + one heavier weight per family (Architect judgement call,
 * flagged in the design doc's Open Questions #7): sufficient for the 5
 * `Text` variants plus a bold/semibold accent option. Additive change if
 * more weights are needed later.
 */
import {
  PlayfairDisplay_400Regular,
  PlayfairDisplay_700Bold,
} from '@expo-google-fonts/playfair-display';
import {
  Poppins_400Regular,
  Poppins_600SemiBold,
} from '@expo-google-fonts/poppins';

export const fontAssets = {
  PlayfairDisplay_400Regular,
  PlayfairDisplay_700Bold,
  Poppins_400Regular,
  Poppins_600SemiBold,
  DMSans_400Regular,
  DMSans_500Medium,
  JetBrainsMono_400Regular,
  JetBrainsMono_700Bold,
  NotoSansDevanagari_400Regular,
} as const;
