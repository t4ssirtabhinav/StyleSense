// SS-021 — native platform resolution of the export seam. No native-specific
// behaviour exists yet (PNG export deferred, BL-141) — re-exports the
// shared text-fallback implementation so this is the ONLY file a future
// image-export ticket needs to change for native.
export * from './styleScoreCardExport';
