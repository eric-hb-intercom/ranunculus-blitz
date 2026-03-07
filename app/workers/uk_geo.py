"""UK geographic classification for observations.

Classifies lat/lng coordinates into territories (England, Scotland, Wales,
Northern Ireland), and detects whether they fall within major cities or
national parks.  Uses simplified boundary rules — no external GIS dependencies.
"""

import math
from typing import Optional

# ---------------------------------------------------------------------------
# Haversine distance (km)
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Territory classification
# ---------------------------------------------------------------------------

def classify_territory(lat: float, lng: float) -> Optional[str]:
    """Return 'England', 'Scotland', 'Wales', or 'Northern Ireland'.

    Uses simplified lat/lng boundary rules.  Returns None if the point
    doesn't fall within any recognised territory (e.g. offshore).
    """
    # Northern Ireland
    if 54.0 <= lat <= 55.45 and -8.2 <= lng <= -5.4:
        return "Northern Ireland"

    # Must be on the British mainland (rough bounding box)
    if not (49.9 <= lat <= 60.9 and -8.2 <= lng <= 1.8):
        return None

    # Scotland — north of the border (roughly lat 55.3)
    if lat >= 55.3:
        return "Scotland"

    # Wales — west of roughly lng -3.0, south of lat 53.4
    # More nuanced: the Wales/England border runs roughly along these lines
    if lat <= 53.4 and lng <= -2.7:
        # Southern Wales boundary — below ~51.4 needs to be west of -2.9
        if lat <= 51.4 and lng > -2.9:
            return "England"
        return "Wales"

    return "England"


# ---------------------------------------------------------------------------
# Major UK cities — (name, lat, lng, radius_km)
# ---------------------------------------------------------------------------

_CITIES = [
    ("London",       51.5074, -0.1278, 25),
    ("Birmingham",   52.4862, -1.8904, 12),
    ("Manchester",   53.4808, -2.2426, 12),
    ("Leeds",        53.8008, -1.5491, 10),
    ("Glasgow",      55.8642, -4.2518, 12),
    ("Edinburgh",    55.9533, -3.1883, 10),
    ("Liverpool",    53.4084, -2.9916, 10),
    ("Bristol",      51.4545, -2.5879, 10),
    ("Sheffield",    53.3811, -1.4701, 10),
    ("Newcastle",    54.9783, -1.6178, 10),
    ("Nottingham",   52.9548, -1.1581,  9),
    ("Cardiff",      51.4816, -3.1791, 10),
    ("Belfast",      54.5973, -5.9301, 10),
    ("Southampton",  50.9097, -1.4044,  9),
    ("Oxford",       51.7520, -1.2577,  8),
]


def is_city(lat: float, lng: float) -> bool:
    """Return True if the point is within a major UK city radius."""
    for _, clat, clng, radius in _CITIES:
        if _haversine_km(lat, lng, clat, clng) <= radius:
            return True
    return False


# ---------------------------------------------------------------------------
# UK National Parks — bounding boxes (south_lat, north_lat, west_lng, east_lng)
# ---------------------------------------------------------------------------

_NATIONAL_PARKS = {
    "Lake District":        (54.25, 54.70, -3.40, -2.75),
    "Peak District":        (53.00, 53.55, -2.05, -1.50),
    "Snowdonia":            (52.60, 53.10, -4.15, -3.55),
    "Yorkshire Dales":      (54.05, 54.50, -2.55, -1.80),
    "North York Moors":     (54.20, 54.55, -1.35, -0.60),
    "Dartmoor":             (50.40, 50.75, -4.10, -3.60),
    "Exmoor":               (51.05, 51.30, -3.90, -3.30),
    "Brecon Beacons":       (51.70, 52.10, -3.80, -3.05),
    "Pembrokeshire Coast":  (51.60, 51.95, -5.35, -4.65),
    "Cairngorms":           (56.75, 57.20, -4.10, -3.20),
    "Loch Lomond":          (56.05, 56.50, -5.00, -4.20),
    "New Forest":           (50.70, 50.95, -1.80, -1.30),
    "South Downs":          (50.80, 51.10, -1.05,  0.00),
    "Norfolk Broads":       (52.55, 52.80,  1.30,  1.75),
    "Northumberland":       (55.15, 55.55, -2.60, -1.80),
}


def is_national_park(lat: float, lng: float) -> bool:
    """Return True if the point falls within a UK national park bounding box."""
    for s_lat, n_lat, w_lng, e_lng in _NATIONAL_PARKS.values():
        if s_lat <= lat <= n_lat and w_lng <= lng <= e_lng:
            return True
    return False


# ---------------------------------------------------------------------------
# Batch classification
# ---------------------------------------------------------------------------

def classify_observations(
    obs_data: dict[int, dict],
) -> dict[int, dict]:
    """Classify a batch of observations.

    Parameters
    ----------
    obs_data : {obs_id: {"lat": float|None, "lng": float|None, ...}}

    Returns
    -------
    {obs_id: {"territory": str|None, "is_city": bool, "is_national_park": bool}}
    """
    result: dict[int, dict] = {}
    for obs_id, info in obs_data.items():
        lat = info.get("lat")
        lng = info.get("lng")
        if lat is None or lng is None:
            result[obs_id] = {
                "territory": None,
                "is_city": False,
                "is_national_park": False,
            }
        else:
            result[obs_id] = {
                "territory": classify_territory(lat, lng),
                "is_city": is_city(lat, lng),
                "is_national_park": is_national_park(lat, lng),
            }
    return result
