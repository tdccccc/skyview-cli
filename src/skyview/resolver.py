"""
skyview.resolver — Astronomical name resolution and coordinate parsing.

Converts object names (e.g. "NGC 788") to RA/Dec coordinates via the
CDS Sesame service (SIMBAD/NED/VizieR), and parses various coordinate
string formats.
"""

from __future__ import annotations
from functools import lru_cache
from astropy.coordinates import SkyCoord
import astropy.units as u


@lru_cache(maxsize=256)
def resolve_name(name: str) -> tuple[float, float]:
    """Resolve an astronomical object name to equatorial coordinates.

    Uses ``astropy.coordinates.SkyCoord.from_name()`` which queries the
    CDS Sesame name resolver (SIMBAD → NED → VizieR).

    Results are cached (up to 256 entries) to avoid repeated network calls.

    Parameters
    ----------
    name : str
        Object name, e.g. ``"NGC 788"``, ``"M31"``, ``"Coma Cluster"``.

    Returns
    -------
    tuple[float, float]
        ``(ra, dec)`` in decimal degrees (ICRS).

    Raises
    ------
    astropy.coordinates.name_resolve.NameResolveError
        If the name cannot be resolved by any service.
    """
    coord = SkyCoord.from_name(name)
    return coord.ra.deg, coord.dec.deg


def parse_coordinates(text: str) -> tuple[float, float]:
    """Parse flexible coordinate input into ``(ra, dec)`` in degrees.

    Tries the following formats in order:

    1. **Decimal degrees**: ``"150.0 2.2"`` or ``"150.0, 2.2"``
       — two numbers separated by space or comma, with RA in [0, 360]
       and Dec in [-90, 90].

    2. **Sexagesimal (HMS/DMS)**: ``"10:00:00 +02:12:00"``
       — interpreted as (hour-angle, degrees).

    3. **Object name**: ``"NGC 788"``, ``"M31"``
       — resolved via :func:`resolve_name`.

    Parameters
    ----------
    text : str
        Coordinate string or object name.

    Returns
    -------
    tuple[float, float]
        ``(ra, dec)`` in decimal degrees.

    Raises
    ------
    ValueError
        If the input is empty.
    astropy.coordinates.name_resolve.NameResolveError
        If name resolution fails.
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty coordinate string")

    # Try as two numbers (decimal degrees)
    parts = text.replace(",", " ").split()
    if len(parts) == 2:
        try:
            ra, dec = float(parts[0]), float(parts[1])
            if 0 <= ra <= 360 and -90 <= dec <= 90:
                return ra, dec
        except ValueError:
            pass

        # Try as sexagesimal (HH:MM:SS DD:MM:SS)
        try:
            coord = SkyCoord(parts[0], parts[1], unit=(u.hourangle, u.deg))
            return coord.ra.deg, coord.dec.deg
        except Exception:
            pass

    # Fall through to name resolution
    return resolve_name(text)
