// SS-023 — the capability seam for PNG export (raw ticket AC #4). Per the
// user's 2026-08-07 sign-off (docs/worklog/SS-023.md, Open Question #2,
// same decision as SS-021's identical AC): PNG export is DEFERRED. This
// seam ships the text/deep-link fallback ONLY — `BL-141` tracks the future
// image-export verification spike that unblocks both tickets.
//
// `exportOutfitCard(input) => Promise<ShareableCard>` is the whole contract.
// Platform files (`.native.ts` / `.web.ts`) resolve the concrete
// implementation via Metro's platform-extension resolution — importing
// `./outfitCardExport` (extensionless) picks up the right one automatically.
// Both currently delegate to this shared, platform-agnostic text builder;
// when the image half is eventually built, only the platform files change,
// never this one's exported TYPE contract.

export type ShareableCard =
  | { kind: 'image'; uri: string }
  | { kind: 'text'; body: string };

export interface OutfitShareInput {
  occasionLabel: string;
  itemCategoryLabels: string[];
}

export function buildShareText(input: OutfitShareInput): string {
  const items = input.itemCategoryLabels.filter(Boolean).join(', ');
  const itemsSuffix = items ? ` (${items})` : '';
  return `I just styled a ${input.occasionLabel} outfit on StyleSense${itemsSuffix}!`;
}

export async function exportOutfitCard(
  input: OutfitShareInput,
): Promise<ShareableCard> {
  return { kind: 'text', body: buildShareText(input) };
}
