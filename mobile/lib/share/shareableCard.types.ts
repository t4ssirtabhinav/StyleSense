// SS-021 — generalises SS-023's outfitCardExport.ts seam by exactly one
// step (design §7) so both features' "shareable card" seams can never drift
// into two different notions of the same concept. SS-023's file re-exports
// this type; its public export surface stays byte-compatible.

export type ShareableCard =
  | { kind: 'image'; uri: string }
  | { kind: 'text'; body: string };
