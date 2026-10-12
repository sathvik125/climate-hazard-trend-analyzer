"""Preconfigured point locations (city centre coordinates, WGS84 decimal degrees).

Each entry is a single point that maps to one reanalysis grid cell. It does not
represent the city's administrative area, its state, or any bounding box.
"""

from __future__ import annotations

PRESET_LOCATIONS = [
    {"id": "hyderabad", "name": "Hyderabad", "country": "India", "latitude": 17.3850, "longitude": 78.4867},
    {"id": "delhi", "name": "Delhi", "country": "India", "latitude": 28.6139, "longitude": 77.2090},
    {"id": "mumbai", "name": "Mumbai", "country": "India", "latitude": 19.0760, "longitude": 72.8777},
    {"id": "bengaluru", "name": "Bengaluru", "country": "India", "latitude": 12.9716, "longitude": 77.5946},
    {"id": "chennai", "name": "Chennai", "country": "India", "latitude": 13.0827, "longitude": 80.2707},
]


def find_preset(latitude: float, longitude: float, precision: int) -> dict | None:
    """Return the preset whose rounded coordinates match, if any."""
    for loc in PRESET_LOCATIONS:
        if (
            round(loc["latitude"], precision) == round(latitude, precision)
            and round(loc["longitude"], precision) == round(longitude, precision)
        ):
            return loc
    return None
