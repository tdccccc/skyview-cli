"""Core API — the main interface for both CLI and Jupyter."""

from __future__ import annotations
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence, Optional, Union
from PIL import Image
import numpy as np

from skyview.surveys import fetch_cutout, get_survey, SURVEYS, DEFAULT_SURVEY
from skyview.resolver import parse_coordinates, resolve_name

# Max pixel size for batch thumbnails (keeps downloads fast)
BATCH_MAX_PIXELS = 512


def _coerce_targets(targets, dec=None):
    """Normalize various input formats into a list of (ra, dec) or str.

    Handles:
        - targets=ra_array, dec=dec_array
        - targets=(ra_array, dec_array)   # tuple of two arrays
        - targets=[(ra, dec), ...]        # list of tuples
        - targets=["NGC 788", "M31"]      # list of names
        - targets=pandas DataFrame columns, numpy arrays, etc.
    """
    # Style: batch(ra_array, dec_array)
    if dec is not None:
        return [(float(r), float(d)) for r, d in zip(targets, dec)]

    # Style: batch((ra_series, dec_series)) — tuple/list of two array-likes
    if isinstance(targets, (tuple, list)) and len(targets) == 2:
        a, b = targets[0], targets[1]
        # Check if both look like arrays (have __iter__ and __len__) and aren't strings
        if (not isinstance(a, str) and not isinstance(b, str)
                and hasattr(a, '__iter__') and hasattr(b, '__iter__')
                and hasattr(a, '__len__') and hasattr(b, '__len__')):
            try:
                la, lb = len(a), len(b)
                if la == lb and la > 0:
                    # Could be two arrays OR a list of 2 (ra,dec) tuples
                    # Heuristic: if elements of a are iterable, it's a list of tuples
                    first = next(iter(a))
                    if not hasattr(first, '__iter__') or isinstance(first, str):
                        # Elements are scalars → two parallel arrays
                        return [(float(r), float(d)) for r, d in zip(a, b)]
            except (TypeError, StopIteration):
                pass

    # Already a list of something — normalize each element
    result = []
    for t in targets:
        if isinstance(t, str):
            result.append(t)
        elif isinstance(t, (list, tuple)) and len(t) >= 2:
            result.append((float(t[0]), float(t[1])))
        else:
            # numpy scalar or similar — can't be a coordinate pair
            result.append(t)
    return result


def _resolve_target(t):
    """Resolve a single target to (label, ra, dec)."""
    if isinstance(t, tuple) and len(t) == 2:
        ra, dec = t
        return f"({ra:.4f}, {dec:.4f})", float(ra), float(dec)
    else:
        name = str(t)
        ra, dec = parse_coordinates(name)
        return name, ra, dec


def _fetch_one(idx, label, ra, dec, survey, fov, size):
    """Fetch one cutout — for use in thread pool."""
    try:
        img = fetch_cutout(ra, dec, survey=survey, fov=fov, size=size)
        return idx, label, img, None
    except Exception as e:
        return idx, label, None, e


def fetch(target: str = "", ra: float = None, dec: float = None,
          survey: str = None, size: int = 0, fov: float = 1.0) -> Image.Image:
    """Fetch a sky cutout image.

    Args:
        target: object name or "ra dec" string
        ra, dec: coordinates in degrees (alternative to target)
        survey: survey layer name
        size: pixel size
        fov: field of view in arcmin (default 1')

    Returns:
        PIL Image
    """
    if target:
        ra, dec = parse_coordinates(target)
    if ra is None or dec is None:
        raise ValueError("Provide target name or ra/dec")
    return fetch_cutout(ra, dec, survey=survey, size=size, fov=fov)


def show(target: str = "", ra: float = None, dec: float = None,
         survey: str = None, fov: float = 1.0, size: int = 0,
         title: str = "", figsize: tuple = (6, 6), **kwargs) -> None:
    """Fetch and display a sky image (works in Jupyter and matplotlib).

    Usage in Jupyter:
        import skyview
        skyview.show("NGC 788")
        skyview.show(ra=30.28, dec=-23.5, survey="sdss")
    """
    import matplotlib.pyplot as plt

    if target:
        ra_r, dec_r = parse_coordinates(target)
    else:
        ra_r, dec_r = ra, dec

    img = fetch(ra=ra_r, dec=dec_r, survey=survey, fov=fov, size=size)

    fig, ax = plt.subplots(1, 1, figsize=figsize)
    ax.imshow(np.array(img))
    ax.set_xlabel("← E    W →")
    ax.set_ylabel("← S    N →")

    label = title or target or f"({ra_r:.4f}, {dec_r:.4f})"
    survey_name = survey or DEFAULT_SURVEY
    ax.set_title(f"{label}  [{survey_name}]  FoV={fov}'")
    ax.tick_params(labelbottom=False, labelleft=False)
    plt.tight_layout()
    plt.show()


def batch(targets, dec=None,
          survey: str = None, fov: float = 1.0, size: int = 0,
          cols: int = 5, thumb_size: tuple = (3, 3),
          save: str = "", workers: int = 8, **kwargs) -> None:
    """Fetch and display a grid of sky images.

    Args:
        targets: list of names, (ra,dec) tuples, or RA values (if dec given).
                 Also accepts (ra_array, dec_array) tuple.
        dec: optional Dec values (when targets is RA values)
        survey: survey layer
        fov: field of view in arcmin
        size: pixel size (auto-capped in batch for speed)
        cols: grid columns
        thumb_size: (w, h) per thumbnail in inches
        save: save to file instead of showing
        workers: concurrent download threads (default 8)

    Examples:
        batch(["NGC 788", "M31"])
        batch(df["ra"], df["dec"], fov=5)
        batch((df["ra"], df["dec"]), survey="sdss")
        batch(list(zip(df["ra"], df["dec"])))
    """
    import matplotlib.pyplot as plt

    items = _coerce_targets(targets, dec)
    n = len(items)
    if n == 0:
        print("No targets to display.")
        return

    # Cap pixel size for batch thumbnails to keep downloads fast
    batch_size = size
    if batch_size == 0:
        cfg = get_survey(survey)
        ps = cfg.default_pixscale
        computed = int(fov * 60 / ps) if fov > 0 else cfg.default_size
        batch_size = min(computed, BATCH_MAX_PIXELS)

    # Resolve all targets to (label, ra, dec)
    resolved = []
    for t in items:
        try:
            resolved.append(_resolve_target(t))
        except Exception as e:
            resolved.append((str(t), None, None))

    # Concurrent downloads
    results = [None] * n
    print(f"Fetching {n} images ({batch_size}px, fov={fov}')...", flush=True)

    with ThreadPoolExecutor(max_workers=min(workers, n)) as pool:
        futures = {}
        for idx, (label, ra_t, dec_t) in enumerate(resolved):
            if ra_t is not None:
                fut = pool.submit(_fetch_one, idx, label, ra_t, dec_t,
                                  survey, fov, batch_size)
                futures[fut] = idx
            else:
                results[idx] = (idx, label, None, ValueError("Could not resolve"))

        done = 0
        for fut in as_completed(futures):
            result = fut.result()
            results[result[0]] = result
            done += 1
            if done % 5 == 0 or done == n:
                print(f"  {done}/{n}", flush=True)

    # Plot grid
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols,
                             figsize=(thumb_size[0] * cols, thumb_size[1] * rows),
                             squeeze=False)

    for idx, (_, label, img, err) in enumerate(results):
        ax = axes[idx // cols][idx % cols]
        if img is not None:
            ax.imshow(np.array(img))
            ax.set_title(label, fontsize=8)
        else:
            ax.text(0.5, 0.5, f"Error:\n{err}", ha="center", va="center",
                    fontsize=7, transform=ax.transAxes, color="red")
            ax.set_title(label, fontsize=8, color="red")
        ax.set_xticks([])
        ax.set_yticks([])

    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].set_visible(False)

    plt.tight_layout()
    if save:
        fig.savefig(save, dpi=150, bbox_inches="tight")
        print(f"Saved to {save}")
    else:
        plt.show()


def resolve(name: str) -> tuple[float, float]:
    """Resolve object name to (ra, dec) in degrees."""
    return resolve_name(name)


def batch_from_file(filepath: str, ra_col: str = "ra", dec_col: str = "dec",
                    name_col: str = "", survey: str = None, fov: float = 1.0,
                    cols: int = 5, save: str = "", limit: int = 50,
                    **kwargs) -> None:
    """Load targets from CSV/FITS and display as grid.

    Args:
        filepath: path to CSV or FITS file
        ra_col, dec_col: column names for coordinates
        name_col: optional column for labels
        limit: max number of targets to show
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext in (".fits", ".fit"):
        from astropy.table import Table
        tbl = Table.read(str(path))
        ras = list(tbl[ra_col][:limit])
        decs = list(tbl[dec_col][:limit])
        names = list(tbl[name_col][:limit]) if name_col and name_col in tbl.colnames else None
    elif ext in (".csv", ".tsv", ".txt"):
        import csv
        sep = "\t" if ext == ".tsv" else ","
        with open(path) as f:
            reader = csv.DictReader(f, delimiter=sep)
            file_rows = list(reader)[:limit]
        ras = [float(r[ra_col]) for r in file_rows]
        decs = [float(r[dec_col]) for r in file_rows]
        names = [r[name_col] for r in file_rows] if name_col and name_col in file_rows[0] else None
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use .csv, .tsv, .fits")

    if names:
        targets = [(float(ra), float(dec)) for ra, dec in zip(ras, decs)]
        # Pass with labels — use batch with custom title override
        batch(targets, survey=survey, fov=fov, cols=cols, save=save, **kwargs)
    else:
        batch(ras, dec=decs, survey=survey, fov=fov, cols=cols, save=save, **kwargs)
