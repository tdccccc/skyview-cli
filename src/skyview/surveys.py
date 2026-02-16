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
    bands: Optional[str] = None

    def cutout_url(self, ra: float, dec: float, size: int = 0,
                   pixscale: float = 0, layer: str = "") -> str:
        sz = size or self.default_size
        ps = pixscale or self.default_pixscale
        return f"{self.base_url}?ra={ra}&dec={dec}&size={sz}&pixscale={ps}&layer={layer or self.name}"


# --- Built-in survey configs ---

SURVEYS: dict[str, SurveyConfig] = {
    "ls-dr10": SurveyConfig(
        name="ls-dr10",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262,
        default_size=256,
        max_size=3000,
    ),
    "ls-dr9": SurveyConfig(
        name="ls-dr9",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262,
        default_size=256,
        max_size=3000,
    ),
    "sdss": SurveyConfig(
        name="sdss",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.396,
        default_size=256,
        max_size=3000,
    ),
    "des-dr1": SurveyConfig(
        name="des-dr1",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=0.262,
        default_size=256,
        max_size=3000,
    ),
    "unwise-neo7": SurveyConfig(
        name="unwise-neo7",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=2.75,
        default_size=256,
        max_size=3000,
    ),
    "galex": SurveyConfig(
        name="galex",
        base_url="https://www.legacysurvey.org/viewer/cutout.jpg",
        default_pixscale=1.5,
        default_size=256,
        max_size=3000,
    ),
    # PanSTARRS via their own cutout service
    "panstarrs": SurveyConfig(
        name="panstarrs",
        base_url="https://ps1images.stsci.edu/cgi-bin/ps1cutouts",
        default_pixscale=0.25,
        default_size=256,
        max_size=1200,
    ),
}

DEFAULT_SURVEY = "ls-dr10"


def get_survey(name: str | None = None) -> SurveyConfig:
    key = (name or DEFAULT_SURVEY).lower()
    if key not in SURVEYS:
        raise ValueError(f"Unknown survey '{key}'. Available: {list(SURVEYS.keys())}")
    return SURVEYS[key]


def fetch_cutout(ra: float, dec: float, survey: str | None = None,
                 size: int = 0, pixscale: float = 0,
                 fov: float = 0, timeout: float = 30) -> Image.Image:
    """Fetch a JPEG cutout image.

    Args:
        ra, dec: coordinates in degrees
        survey: survey name (default: ls-dr10)
        size: image size in pixels
        pixscale: arcsec/pixel
        fov: field of view in arcmin (overrides size if given)
        timeout: request timeout in seconds

    Returns:
        PIL Image
    """
    cfg = get_survey(survey)

    ps = pixscale or cfg.default_pixscale
    if fov > 0:
        # fov in arcmin -> size in pixels
        sz = int(fov * 60 / ps)
    else:
        sz = size or cfg.default_size

    sz = min(sz, cfg.max_size)

    # PanSTARRS uses a different API
    if cfg.name == "panstarrs":
        return _fetch_panstarrs(ra, dec, sz, ps, timeout)

    url = cfg.cutout_url(ra, dec, sz, ps)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content))


def _fetch_panstarrs(ra: float, dec: float, size: int, pixscale: float,
                     timeout: float) -> Image.Image:
    """Fetch PanSTARRS color cutout via MAST API."""
    # Use the fitscut color image service
    url = (
        f"https://ps1images.stsci.edu/cgi-bin/fitscut.cgi"
        f"?ra={ra}&dec={dec}&size={size}&format=jpg"
        f"&output_size={size}&autoscale=99.5&filter=color"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content))
