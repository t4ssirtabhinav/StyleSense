// SS-021 — the capability seam for PNG export (raw ticket AC #4). Per
// BL-141's 2026-08-07 sign-off (taken for SS-023 and SS-021 together, see
// docs/tickets/SS-021-design.md §7): no verified client-side image-export
// path exists, so this ships the text/deep-link fallback ONLY, mirroring
// mobile/features/outfit-ai/share/outfitCardExport.ts exactly. `BL-141`
// tracks the future image-export verification spike that unblocks both
// tickets.
//
// Platform files (.native.ts / .web.ts) resolve the concrete implementation
// via Metro's platform-extension resolution; both currently delegate to
// this shared, platform-agnostic text builder — when the image half is
// eventually built, only the platform files change, never this one's
// exported TYPE contract.

import type { ShareableCard } from '../../../lib/share/shareableCard.types';

export interface StyleScoreShareInput {
  total: number;
}

export function buildStyleScoreShareText(input: StyleScoreShareInput): string {
  return `My StyleSense style score is ${input.total}/100. How does your wardrobe score?`;
}

export async function exportStyleScoreCard(
  input: StyleScoreShareInput,
): Promise<ShareableCard> {
  return { kind: 'text', body: buildStyleScoreShareText(input) };
}
