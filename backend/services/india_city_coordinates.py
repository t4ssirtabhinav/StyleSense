"""SS-022 -- India city name -> lat/lng resolution, pure, no I/O.

``CITY_COORDINATES`` is the 50 rows of
``mobile/features/onboarding/onboarding.constants.ts::TOP_50_INDIAN_CITIES``
transcribed VERBATIM (``id``, ``name``, ``lat``, ``lng``) -- do not
re-derive coordinates from another source, do not round them. See
``docs/tickets/SS-022-design.md`` §2 for why this table is duplicated
(TS picker vs. Python weather resolution) rather than shared, and
``BL-151`` for the eventual `cities` reference-table fix.

``users.city`` stores the picker's **display name** (``city.name``, e.g.
``"Mumbai"``), never the ``id`` -- so matching is on the normalised name,
with the id accepted as a fallback (the two coincide for every row except
where a hyphen/underscore difference collapses under normalisation anyway).

``CITY_ALIASES`` is a short, explicit map for renamed/colloquial cities a
free-text "Other" entry is likely to use. Unknown/free-text input resolves
to ``None`` -- no geocoding fallback, no fuzzy match (`BL-152`): silently
reporting the wrong city's weather is worse than no weather at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["ResolvedCity", "CITY_COORDINATES", "CITY_ALIASES", "resolve_city"]


@dataclass(frozen=True)
class ResolvedCity:
    slug: str  # "mumbai" -- cache-key component, never user-facing
    name: str  # "Mumbai" -- the display name echoed in the response
    lat: float
    lng: float


def _normalise(raw: str) -> str:
    """``raw.strip().casefold()``, spaces/hyphens collapsed to a single
    ``_``. Never raises on empty input (returns ``""``)."""
    stripped = raw.strip().casefold()
    collapsed = re.sub(r"[\s\-]+", "_", stripped)
    return collapsed


# Transcribed verbatim from
# mobile/features/onboarding/onboarding.constants.ts:57-384 (TOP_50_INDIAN_CITIES).
# Keyed by the normalised NAME (matching what users.city actually stores);
# resolve_city() also tries the normalised `id` as a fallback key below.
_RAW_CITIES: tuple[tuple[str, str, float, float], ...] = (
    ("mumbai", "Mumbai", 19.076, 72.8777),
    ("delhi", "Delhi", 28.7041, 77.1025),
    ("bengaluru", "Bengaluru", 12.9716, 77.5946),
    ("hyderabad", "Hyderabad", 17.385, 78.4867),
    ("ahmedabad", "Ahmedabad", 23.0225, 72.5714),
    ("chennai", "Chennai", 13.0827, 80.2707),
    ("kolkata", "Kolkata", 22.5726, 88.3639),
    ("surat", "Surat", 21.1702, 72.8311),
    ("pune", "Pune", 18.5204, 73.8567),
    ("jaipur", "Jaipur", 26.9124, 75.7873),
    ("lucknow", "Lucknow", 26.8467, 80.9462),
    ("kanpur", "Kanpur", 26.4499, 80.3319),
    ("nagpur", "Nagpur", 21.1458, 79.0882),
    ("indore", "Indore", 22.7196, 75.8577),
    ("thane", "Thane", 19.2183, 72.9781),
    ("bhopal", "Bhopal", 23.2599, 77.4126),
    ("visakhapatnam", "Visakhapatnam", 17.6868, 83.2185),
    ("pimpri_chinchwad", "Pimpri-Chinchwad", 18.6298, 73.7997),
    ("patna", "Patna", 25.5941, 85.1376),
    ("vadodara", "Vadodara", 22.3072, 73.1812),
    ("ghaziabad", "Ghaziabad", 28.6692, 77.4538),
    ("ludhiana", "Ludhiana", 30.901, 75.8573),
    ("agra", "Agra", 27.1767, 78.0081),
    ("nashik", "Nashik", 19.9975, 73.7898),
    ("faridabad", "Faridabad", 28.4089, 77.3178),
    ("meerut", "Meerut", 28.9845, 77.7064),
    ("rajkot", "Rajkot", 22.3039, 70.8022),
    ("kalyan_dombivli", "Kalyan-Dombivli", 19.2403, 73.1305),
    ("vasai_virar", "Vasai-Virar", 19.4912, 72.8054),
    ("varanasi", "Varanasi", 25.3176, 82.9739),
    ("srinagar", "Srinagar", 34.0837, 74.7973),
    ("aurangabad", "Aurangabad", 19.8762, 75.3433),
    ("dhanbad", "Dhanbad", 23.7957, 86.4304),
    ("amritsar", "Amritsar", 31.634, 74.8723),
    ("navi_mumbai", "Navi Mumbai", 19.033, 73.0297),
    ("prayagraj", "Prayagraj", 25.4358, 81.8463),
    ("ranchi", "Ranchi", 23.3441, 85.3096),
    ("howrah", "Howrah", 22.5958, 88.2636),
    ("coimbatore", "Coimbatore", 11.0168, 76.9558),
    ("jabalpur", "Jabalpur", 23.1815, 79.9864),
    ("gwalior", "Gwalior", 26.2183, 78.1828),
    ("vijayawada", "Vijayawada", 16.5062, 80.648),
    ("jodhpur", "Jodhpur", 26.2389, 73.0243),
    ("madurai", "Madurai", 9.9252, 78.1198),
    ("raipur", "Raipur", 21.2514, 81.6296),
    ("kota", "Kota", 25.2138, 75.8648),
    ("guwahati", "Guwahati", 26.1445, 91.7362),
    ("chandigarh", "Chandigarh", 30.7333, 76.7794),
    ("thiruvananthapuram", "Thiruvananthapuram", 8.5241, 76.9366),
    ("bhubaneswar", "Bhubaneswar", 20.2961, 85.8245),
)

# id -> ResolvedCity (the id and the normalised-name key coincide for every
# row above except where a hyphen/underscore difference collapses under
# normalisation anyway, e.g. "kalyan_dombivli" both ways).
CITY_COORDINATES: dict[str, ResolvedCity] = {
    city_id: ResolvedCity(slug=city_id, name=name, lat=lat, lng=lng)
    for city_id, name, lat, lng in _RAW_CITIES
}

# Renamed/colloquial city -> canonical id. A user typing free text into the
# picker's "Other" row is likely to use the old/common name.
CITY_ALIASES: dict[str, str] = {
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "madras": "chennai",
    "poona": "pune",
    "baroda": "vadodara",
    "gurgaon": "delhi",  # NCR -- deliberate approximation, same weather within a few km
    "gurugram": "delhi",
    "noida": "delhi",
    "new_delhi": "delhi",
    "trivandrum": "thiruvananthapuram",
    "vizag": "visakhapatnam",
    "allahabad": "prayagraj",
}


def resolve_city(raw: str | None) -> ResolvedCity | None:
    """``None``/empty/whitespace-only/unresolvable free text -> ``None``.
    Matching order: normalised name (what ``users.city`` actually stores)
    -> normalised id -> ``CITY_ALIASES``. Never raises, never geocodes,
    never fuzzy-matches (`BL-152`)."""
    if not raw:
        return None
    normalised = _normalise(raw)
    if not normalised:
        return None

    for city in CITY_COORDINATES.values():
        if _normalise(city.name) == normalised:
            return city

    if normalised in CITY_COORDINATES:
        return CITY_COORDINATES[normalised]

    alias_target = CITY_ALIASES.get(normalised)
    if alias_target is not None:
        return CITY_COORDINATES.get(alias_target)

    return None
