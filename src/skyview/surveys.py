"""Survey image providers."""

from __future__ import annotations
import requests
from io import BytesIO
from PIL import Image
from typing import Optional
from dataclasses import dataclass


@dataclass
class SurveyConfig:
    name: str
    base_url: str
    default_pixscale: float  # arcsec/pixel
    default_size: int  # pixels
    max_size: int
    priority: int = 0  # higher = tried first in fallback
    bands: Optional[str] = None
    dec_range: tuple[float, float] = (-90, 90)

    def cutout_url(self, ra: float, dec: float, size: int = 0,
                   pixscale: float = 0, layer: str = "") -> str:
        sz = size or self.default_size
        ps = pixscale or self.default_pixscale
        return (f"{self.base_url}?ra={ra}&dec={dec}"
                f"&size={sz}&pixscale={ps}&layer={layer or self.name}")

    def covers(self, dec: float) -> bool:
        return self.dec_range[0] <= dec <= self.dec_range[1]


# priority: higher = preferred in auto-fallback
SURVEYS: dict[str, SurveyConfig] = {
    "ls-dr10": SurveyConfig(
        name="ls-dr10",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262, default_size=256, max_size=3000,
        priority=100, dec_range=(-70, 90),
    ),
    "ls-dr9": SurveyConfig(
        name="ls-dr9",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262, default_size=256, max_size=3000,
        priority=90, dec_range=(-70, 90),
    ),
    "panstarrs": SurveyConfig(
        name="panstarrs",
        base_url="https://ps1images.stsci.edu/cgi-bin/ps1cutouts",
        default_pixscale=0.25, default_size=256, max_size=1200,
        priority=80, dec_range=(-30, 90),
    ),
    "sdss": SurveyConfig(
        name="sdss",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.396, default_size=256, max_size=3000,
        priority=70, dec_range=(-20, 70),
    ),
    "des-dr1": SurveyConfig(
        name="des-dr1",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262, default_size=256, max_size=3000,
        priority=60, dec_range=(-65, 5),
    ),
    "unwise-neo7": SurveyConfig(
        name="unwise-neo7",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=2.75, default_size=256, max_size=3000,
        priority=20, dec_range=(-90, 90),
    ),
    "galex": SurveyConfig(
        name="galex",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=1.5, default_size=256, max_size=3000,
        priority=10, dec_range=(-90, 90),
    ),
}

DEFAULT_SURVEY = "ls-dr10"

# Fallback order: sorted by priority descending
FALLBACK_ORDER = sorted(SURVEYS.keys(),
                        key=lambda k: SURVEYS[k].priority, reverse=True)


def get_survey(name: str | None = None) -> SurveyConfig:
    key = (name or DEFAULT_SURVEY).lower()
    if key not in SURVEYS:
        raise ValueError(f"Unknown survey '{key}'. Available: {list(SURVEYS.keys())}")
    return SURVEYS[key]


def _is_blank_image(img: Image.Image, threshold: int = 10) -> bool:
    """Check if image is essentially blank (uniform color)."""
    import numpy as np
    arr = np.array(img)
    return arr.std() < threshold


def fetch_cutout(ra: float, dec: float, survey: str | None = None,
                 size: int = 0, pixscale: float = 0,
                 fov: float = 0, timeout: float = 30,
                 fallback: bool = True) -> Image.Image:
    """Fetch a JPEG cutout image with auto-fallback.

    If the requested survey returns a blank image, automatically tries
    other surveys in priority order.
    """
    surveys_to_try = []
    if survey == "auto" or survey is None:
        surveys_to_try = list(FALLBACK_ORDER)
    else:
        surveys_to_try = [survey]
        if fallback:
            surveys_to_try += [s for s in FALLBACK_ORDER if s != survey]

    last_img = None
    last_error = None

    for srv_name in surveys_to_try:
        try:
            img = _fetch_single(ra, dec, srv_name, size, pixscale, fov, timeout)
            if not _is_blank_image(img):
                return img
            last_img = img
            if not fallback:
                return img
        except Exception as e:
            last_error = e
            if not fallback:
                raise
            continue

    if last_img is not None:
        return last_img
    if last_error:
        raise last_error
    raise RuntimeError(f"No survey could provide image for ({ra}, {dec})")


def _fetch_single(ra: float, dec: float, survey: str,
                  size: int, pixscale: float, fov: float,
                  timeout: float) -> Image.Image:
    """Fetch from a single survey."""
    cfg = get_survey(survey)

    ps = pixscale or cfg.default_pixscale
    if fov > 0:
        sz = int(fov * 60 / ps)
    else:
        sz = size or cfg.default_size
    sz = min(sz, cfg.max_size)

    if cfg.name == "panstarrs":
        return _fetch_panstarrs(ra, dec, sz, ps, timeout)

    url = cfg.cutout_url(ra, dec, sz, ps)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type:
        raise RuntimeError(f"Survey {survey} returned non-image: {content_type}")

    return Image.open(BytesIO(resp.content))


def _fetch_panstarrs(ra: float, dec: float, size: int, pixscale: float,
                     timeout: float) -> Image.Image:
    """Fetch PanSTARRS color cutout via MAST API."""
    url = (
        f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"
        f"?ra={ra}&dec={dec}&size={size}&format=jpg"
        f"&output_size={size}&autoscale=99.5&filter=color"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content))
