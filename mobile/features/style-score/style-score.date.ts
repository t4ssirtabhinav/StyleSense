// SS-021 — the single place the IST month boundary is expressed (design
// §5.4). Pure: shifts into IST, truncates to the month in UTC-space, then
// shifts back — never `toLocaleString`, whose ICU availability varies
// across Hermes/web. Asia/Kolkata has had no DST in the modern era, so a
// fixed +05:30 offset is correct and needs no timezone database.
// [trained-knowledge; the offset is also the fixed constant
// backend/services/ist_window.py already relies on.]

export const IST_OFFSET_MINUTES = 330; // UTC+05:30

export interface IstMonthStart {
  /** UTC ISO-8601 instant of the first moment of the current IST month —
   *  for TIMESTAMPTZ comparisons (e.g. outfits.created_at). */
  isoTimestamp: string;
  /** YYYY-MM-01 of the current IST month — for DATE comparisons (e.g.
   *  wardrobe_item_wears.worn_on). */
  isoDate: string;
}

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

export function getIstMonthStart(now: Date): IstMonthStart {
  const offsetMs = IST_OFFSET_MINUTES * 60_000;
  // A UTC-labelled Date whose y/m/d/h/m/s fields ARE the IST wall-clock
  // reading for `now`.
  const shifted = new Date(now.getTime() + offsetMs);
  const year = shifted.getUTCFullYear();
  const month = shifted.getUTCMonth(); // 0-indexed

  // IST midnight on the 1st, still expressed as UTC-labelled fields.
  const istMonthStartAsShiftedMs = Date.UTC(year, month, 1, 0, 0, 0, 0);
  // Shift back to the real UTC instant that IST midnight corresponds to.
  const utcInstantMs = istMonthStartAsShiftedMs - offsetMs;

  return {
    isoTimestamp: new Date(utcInstantMs).toISOString(),
    isoDate: `${year}-${pad2(month + 1)}-01`,
  };
}
