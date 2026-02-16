"""
skyview.cache — Local image cache to avoid repeated downloads.

Caches cutout images on disk, keyed by (ra, dec, survey, size, pixscale).
Default cache directory: ``~/.cache/skyview/``

Cache can be cleared with ``skyview cache-clear`` CLI command or
``skyview.cache.clear_cache()``.
"""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from PIL import Image

#: Default cache directory
CACHE_DIR = Path.home() / ".cache" / "skyview"


def _cache_key(ra: float, dec: float, survey: str, size: int, pixscale: float) -> str:
    """Generate a deterministic cache filename from request parameters."""
    params = json.dumps({
        "ra": round(ra, 6),
        "dec": round(dec, 6),
        "survey": survey,
        "size": size,
        "pixscale": round(pixscale, 4),
    }, sort_keys=True)
    h = hashlib.md5(params.encode()).hexdigest()[:12]
    return f"{survey}_{ra:.4f}_{dec:.4f}_{h}.jpg"


def get_cached(ra: float, dec: float, survey: str,
               size: int, pixscale: float) -> Image.Image | None:
    """Return cached image if it exists, otherwise None."""
    path = CACHE_DIR / _cache_key(ra, dec, survey, size, pixscale)
    if path.exists():
        try:
            return Image.open(path)
        except Exception:
            path.unlink(missing_ok=True)
    return None


def put_cache(ra: float, dec: float, survey: str,
              size: int, pixscale: float, img: Image.Image) -> Path:
    """Save an image to the cache. Returns the cache file path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / _cache_key(ra, dec, survey, size, pixscale)
    img.save(path, quality=92)
    return path


def clear_cache() -> int:
    """Delete all cached images. Returns number of files removed."""
    if not CACHE_DIR.exists():
        return 0
    count = 0
    for f in CACHE_DIR.iterdir():
        if f.is_file():
            f.unlink()
            count += 1
    return count


def cache_size() -> tuple[int, float]:
    """Return (file_count, total_size_mb) of the cache."""
    if not CACHE_DIR.exists():
        return 0, 0.0
    files = [f for f in CACHE_DIR.iterdir() if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    return len(files), total / (1024 * 1024)
