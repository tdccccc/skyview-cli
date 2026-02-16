"""Name resolver — convert object names to RA/Dec."""

from __future__ import annotations
from functools import lru_cache
from astropy.coordinates import SkyCoord
import astropy.units as u


@lru_cache(maxsize=256)
def resolve_name(name: str) -> tuple[float, float]:
    """Resolve an astronomical object name to (ra, dec) in degrees.

    Uses CDS Sesame (SIMBAD/NED/VizieR).
    """
    coord = SkyCoord.from_name(name)
    return coord.ra.deg, coord.dec.deg


def parse_coordinates(text: str) -> tuple[float, float]:
    """Parse flexible coordinate input.

    Accepts:
        - "ra dec" in degrees: "150.0 2.2"
        - "HH:MM:SS DD:MM:SS": "10:00:00 +02:12:00"
        - Object name: "NGC 788", "M31"
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty coordinate string")

    # Try as two numbers (degrees)
    parts = text.replace(",", " ").split()
    if len(parts) == 2:
        try:
            ra, dec = float(parts[0]), float(parts[1])
            if 0 <= ra <= 360 and -90 <= dec <= 90:
                return ra, dec
        except ValueError:
            pass

        # Try as sexagesimal
        try:
            coord = SkyCoord(parts[0], parts[1], unit=(u.hourangle, u.deg))
            return coord.ra.deg, coord.dec.deg
        except Exception:
            pass

    # Try as object name
    return resolve_name(text)
