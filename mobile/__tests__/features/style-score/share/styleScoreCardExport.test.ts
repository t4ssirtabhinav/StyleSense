// Loaded via jest.requireActual with the explicit `.ts` extension, not the
// extensionless specifier the app itself uses: Jest's haste platform
// resolution (`defaultPlatform: 'ios'`, `jest.config.js`) resolves the
// extensionless `./styleScoreCardExport` to the co-located
// `styleScoreCardExport.native.ts` passthrough
// (`export * from './styleScoreCardExport'`) even when the *importer* is
// this test file, not `.native.ts` itself — and because that passthrough
// resolves the SAME way from inside itself, it becomes a self-referential
// export of nothing under Jest specifically, so every named export comes
// back `undefined`. The explicit extension bypasses platform substitution
// and loads the real implementation. `jest.requireActual` (a plain string
// argument, not an ES import specifier) sidesteps TS5097's restriction on
// `.ts`-suffixed import paths; the `typeof import(...)` type query uses the
// normal extensionless specifier since it's compile-time only. Confirmed
// this is Jest-resolution-specific (not proven to reproduce under
// Metro/an actual device or web build) — logged as a new backlog row
// rather than silently worked around; see docs/worklog/SS-021.md.
// biome-ignore format: typeof import(...) must stay on one line -- multi-line breaks this TS version's parser (TS1005).
type StyleScoreCardExportModule = typeof import('../../../../features/style-score/share/styleScoreCardExport');

const impl = jest.requireActual(
  '../../../../features/style-score/share/styleScoreCardExport.ts',
) as StyleScoreCardExportModule;

const { buildStyleScoreShareText, exportStyleScoreCard } = impl;

describe('styleScoreCardExport', () => {
  it('buildStyleScoreShareText includes the total and the /100 framing', () => {
    const text = buildStyleScoreShareText({ total: 72 });
    expect(text).toContain('72');
    expect(text).toContain('/100');
  });

  it('exportStyleScoreCard resolves { kind: "text" } — a deliberate deferral, so a future PNG change is a visible test change', async () => {
    const card = await exportStyleScoreCard({ total: 55 });
    expect(card.kind).toBe('text');
    if (card.kind === 'text') {
      expect(card.body).toContain('55');
    }
  });
});
