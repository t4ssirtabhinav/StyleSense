// SS-023 — web platform resolution of the export seam. No web-specific
// (DOM-capture) behaviour exists yet (PNG export deferred, `BL-141`) —
// re-exports the shared text-fallback implementation so this is the ONLY
// file a future image-export ticket needs to change for web.
export * from './outfitCardExport';
