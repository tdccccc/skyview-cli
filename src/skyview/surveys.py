"""
skyview.surveys — Survey definitions and image fetching backend.

Each survey is represented by a :class:`SurveyConfig` dataclass that stores
API endpoint, pixel scale, size limits, and priority for automatic fallback.

When a requested survey returns a blank image (e.g. the coordinates fall
outside the survey footprint), the fetcher automatically tries the next
survey in priority order.

Priority order (high → low):
    ls-dr10 → ls-dr9 → panstarrs → sdss → des-dr1 → unwise-neo7 → galex
"""

from __future__ import annotations
import requests
from io import BytesIO
from PIL import Image
from typing import Optional
from dataclasses import dataclass


@dataclass
class SurveyConfig:
    """Configuration for a single sky survey image service.

    Attributes
    ----------
    name : str
        Short identifier used in API calls (e.g. ``"ls-dr10"``).
    base_url : str
        Base URL for the cutout endpoint.
    default_pixscale : float
        Default pixel scale in arcseconds per pixel.
    default_size : int
        Default cutout size in pixels when neither *size* nor *fov* is given.
    max_size : int
        Maximum allowed cutout size in pixels (server-side limit).
    priority : int
        Fallback priority — higher value = tried first (default ``0``).
    bands : str, optional
        Photometric bands available (informational).
    dec_range : tuple[float, float]
        Approximate declination coverage ``(dec_min, dec_max)`` in degrees.
    """
    name: str
    base_url: str
    default_pixscale: float  # arcsec/pixel
    default_size: int        # pixels
    max_size: int            # pixels
    priority: int = 0
    bands: Optional[str] = None
    dec_range: tuple[float, float] = (-90, 90)

    def cutout_url(self, ra: float, dec: float, size: int = 0,
                   pixscale: float = 0, layer: str = "") -> str:
        """Build the full cutout request URL."""
        sz = size or self.default_size
        ps = pixscale or self.default_pixscale
        return (f"{self.base_url}?ra={ra}&dec={dec}"
                f"&size={sz}&pixscale={ps}&layer={layer or self.name}")

    def covers(self, dec: float) -> bool:
        """Check if a declination falls within the survey's approximate footprint."""
        return self.dec_range[0] <= dec <= self.dec_range[1]


# ---------------------------------------------------------------------------
# Survey registry
# ---------------------------------------------------------------------------
# Priority: higher value = preferred in auto-fallback.
# dec_range: approximate sky coverage (not exact — used for quick filtering).

SURVEYS: dict[str, SurveyConfig] = {
    "ls-dr10": SurveyConfig(
        name="ls-dr10",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262, default_size=256, max_size=3000,
        priority=100, dec_range=(-70, 90),
        bands="grz",
    ),
    "ls-dr9": SurveyConfig(
        name="ls-dr9",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262, default_size=256, max_size=3000,
        priority=90, dec_range=(-70, 90),
        bands="grz",
    ),
    "panstarrs": SurveyConfig(
        name="panstarrs",
        base_url="https://ps1images.stsci.edu/cgi-bin/ps1cutouts",
        default_pixscale=0.25, default_size=256, max_size=1200,
        priority=80, dec_range=(-30, 90),
        bands="grizy",
    ),
    "sdss": SurveyConfig(
        name="sdss",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.396, default_size=256, max_size=3000,
        priority=70, dec_range=(-20, 70),
        bands="ugriz",
    ),
    "des-dr1": SurveyConfig(
        name="des-dr1",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262, default_size=256, max_size=3000,
        priority=60, dec_range=(-65, 5),
        bands="grizY",
    ),
    "unwise-neo7": SurveyConfig(
        name="unwise-neo7",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=2.75, default_size=256, max_size=3000,
        priority=20, dec_range=(-90, 90),
        bands="W1W2",
    ),
    "galex": SurveyConfig(
        name="galex",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=1.5, default_size=256, max_size=3000,
        priority=10, dec_range=(-90, 90),
        bands="FUV/NUV",
    ),
}

#: Default survey used when none is specified.
DEFAULT_SURVEY = "ls-dr10"

#: Surveys sorted by descending priority — used for automatic fallback.
FALLBACK_ORDER = sorted(SURVEYS.keys(),
                        key=lambda k: SURVEYS[k].priority, reverse=True)


def get_survey(name: str | None = None) -> SurveyConfig:
    """Look up a survey by name.

    Parameters
    ----------
    name : str, optional
        Survey identifier (case-insensitive).  Defaults to :data:`DEFAULT_SURVEY`.

    Returns
    -------
    SurveyConfig

    Raises
    ------
    ValueError
        If *name* is not a recognized survey.
    """
    key = (name or DEFAULT_SURVEY).lower()
    if key not in SURVEYS:
        raise ValueError(f"Unknown survey '{key}'. Available: {list(SURVEYS.keys())}")
    return SURVEYS[key]


def _is_blank_image(img: Image.Image, threshold: int = 10) -> bool:
    """Return True if the image is essentially uniform (blank/empty).

    A blank image typically means the coordinates fall outside the survey
    footprint.  The check uses the standard deviation of pixel values.
    """
    import numpy as np
    arr = np.array(img)
    return arr.std() < threshold


def fetch_cutout(ra: float, dec: float, survey: str | None = None,
                 size: int = 0, pixscale: float = 0,
                 fov: float = 0, timeout: float = 30,
                 fallback: bool = None) -> Image.Image:
    """Fetch a JPEG cutout image, with optional automatic fallback.

    If the requested survey returns a blank image (e.g. no coverage at
    the given coordinates), the function automatically tries other surveys
    in descending priority order.

    Parameters
    ----------
    ra, dec : float
        Position in decimal degrees.
    survey : str, optional
        Survey name.  ``None`` or ``"auto"`` uses the full fallback chain.
        When a specific survey is given, fallback is **disabled** by default
        (the image is returned as-is even if dark/blank).
    size : int, optional
        Cutout size in pixels.
    pixscale : float, optional
        Pixel scale in arcsec/pixel (overrides survey default).
    fov : float, optional
        Field of view in arc-minutes (overrides *size* if given).
    timeout : float, optional
        HTTP request timeout in seconds (default ``30``).
    fallback : bool, optional
        Whether to try other surveys when the result is blank.
        Default: ``True`` when survey is ``None``/``"auto"``,
        ``False`` when a specific survey is given.

    Returns
    -------
    PIL.Image.Image
    """
    # Determine fallback behavior:
    # - explicit survey → no fallback (dark images may be valid)
    # - auto/None → fallback enabled
    auto_mode = (survey is None or survey == "auto")
    if fallback is None:
        fallback = auto_mode

    if auto_mode:
        surveys_to_try = list(FALLBACK_ORDER)
    else:
        surveys_to_try = [survey]
        if fallback:
            surveys_to_try += [s for s in FALLBACK_ORDER if s != survey]

    best_img = None
    best_std = -1
    last_error = None

    for srv_name in surveys_to_try:
        try:
            img = _fetch_single(ra, dec, srv_name, size, pixscale, fov, timeout)
            if not fallback:
                # No fallback — return immediately whatever we got
                return img
            # In fallback mode, keep the image with highest std (most content)
            import numpy as np
            std = np.array(img).std()
            if std > best_std:
                best_img = img
                best_std = std
            if not _is_blank_image(img):
                return img  # Good enough, stop trying
        except Exception as e:
            last_error = e
            continue

    if best_img is not None:
        return best_img
    if last_error:
        raise last_error
    raise RuntimeError(f"No survey could provide image for ({ra}, {dec})")


def _fetch_single(ra: float, dec: float, survey: str,
                  size: int, pixscale: float, fov: float,
                  timeout: float, max_retries: int = 3,
                  use_cache: bool = True) -> Image.Image:
    """Fetch a cutout from a single specific survey (no fallback).

    Checks local cache first; retries with exponential backoff on 429.
    """
    import time
    from skyview.cache import get_cached, put_cache

    cfg = get_survey(survey)

    ps = pixscale or cfg.default_pixscale
    if fov > 0:
        sz = int(fov * 60 / ps)  # fov (arcmin) → pixels
    else:
        sz = size or cfg.default_size
    sz = min(sz, cfg.max_size)

    # Check cache first
    if use_cache:
        cached = get_cached(ra, dec, cfg.name, sz, ps)
        if cached is not None:
            return cached

    # PanSTARRS uses a different API endpoint
    if cfg.name == "panstarrs":
        img = _fetch_panstarrs(ra, dec, sz, ps, timeout)
        if use_cache:
            put_cache(ra, dec, cfg.name, sz, ps, img)
        return img

    url = cfg.cutout_url(ra, dec, sz, ps)

    for attempt in range(max_retries + 1):
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 429:
            # Rate limited — wait and retry
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)
            continue
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            raise RuntimeError(f"Survey {survey} returned non-image: {content_type}")

        img = Image.open(BytesIO(resp.content))
        if use_cache:
            put_cache(ra, dec, cfg.name, sz, ps, img)
        return img

    # All retries exhausted
    resp.raise_for_status()  # will raise the 429 error


def _fetch_panstarrs(ra: float, dec: float, size: int, pixscale: float,
                     timeout: float) -> Image.Image:
    """Fetch a PanSTARRS color cutout via the MAST fitscut service."""
    url = (
        f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"
        f"?ra={ra}&dec={dec}&size={size}&format=jpg"
        f"&output_size={size}&autoscale=99.5&filter=color"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content))
