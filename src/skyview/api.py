"""
skyview.api — Core API for fetching and displaying astronomical sky images.

This module provides the main interface for both CLI and Jupyter notebook usage.
All public functions (show, batch, fetch, resolve, batch_from_file) are re-exported
from the top-level ``skyview`` package.

Typical Jupyter usage::

    import skyview

    # View a single object
    skyview.show("NGC 788")

    # Batch view from a DataFrame
    skyview.batch(df["ra"], df["dec"], fov=5)
"""

from __future__ import annotations
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence, Optional, Union
from PIL import Image
import numpy as np

from skyview.surveys import fetch_cutout, get_survey, SURVEYS, DEFAULT_SURVEY
from skyview.resolver import parse_coordinates, resolve_name

#: Maximum pixel size for batch thumbnails.
#: Keeps downloads fast while preserving enough detail for visual inspection.
BATCH_MAX_PIXELS = 512


def _is_array_like(obj):
    """Check if *obj* behaves like an array (has ``__iter__`` and ``__len__``)
    but is not a plain string.

    Returns True for: list, tuple, numpy ndarray, pandas Series/Index, etc.
    """
    if isinstance(obj, str):
        return False
    return hasattr(obj, '__iter__') and hasattr(obj, '__len__')


def _is_2d_array(obj):
    """Check if *obj* is a 2-D array-like with shape ``(N, 2+)``.

    Works with numpy ndarrays, pandas DataFrames, and anything exposing
    a ``.shape`` attribute.
    """
    if not _is_array_like(obj):
        return False
    try:
        shape = getattr(obj, 'shape', None)
        if shape is not None and len(shape) == 2 and shape[1] >= 2:
            return True
    except (TypeError, AttributeError):
        pass
    return False


def _coerce_targets(targets, dec=None):
    """Normalize heterogeneous input formats into a uniform list.

    Each element of the returned list is either:
    - ``(ra: float, dec: float)`` — a coordinate pair, or
    - ``str`` — an object name to be resolved later.

    Supported input styles
    ----------------------
    1. Two parallel arrays::

           batch(ra_array, dec_array)

    2. Tuple/list of two arrays::

           batch((df["ra"], df["dec"]))

    3. 2-D array (numpy / DataFrame ``.values``)::

           batch(df[["ra", "dec"]].values)

    4. List of ``(ra, dec)`` tuples::

           batch([(30.28, -23.5), (10.68, 41.27)])

    5. List of object names::

           batch(["NGC 788", "M31"])

    6. Pandas Series or numpy 1-D array of names::

           batch(pd.Series(["NGC 788", "M31"]))
           batch(np.array(["NGC 788", "M31"]))

    Parameters
    ----------
    targets : various
        Input targets in any of the formats above.
    dec : array-like, optional
        Declination values when *targets* contains RA values only.

    Returns
    -------
    list[tuple[float, float] | str]
        Normalized list of coordinate pairs or object name strings.
    """
    # --- Style 1: two parallel arrays ---
    if dec is not None:
        return [(float(r), float(d)) for r, d in zip(targets, dec)]

    # --- Style 3: 2-D array with shape (N, 2+) ---
    if _is_2d_array(targets):
        return [(float(row[0]), float(row[1])) for row in targets]

    # Fallback 2-D check via .ndim (catches edge cases with some array libs)
    if hasattr(targets, 'ndim') and targets.ndim == 2:
        return [(float(row[0]), float(row[1])) for row in targets]

    # --- Style 2: tuple/list wrapping two parallel arrays ---
    if isinstance(targets, (tuple, list)) and len(targets) == 2:
        a, b = targets[0], targets[1]
        if _is_array_like(a) and _is_array_like(b):
            try:
                la, lb = len(a), len(b)
                if la == lb and la > 0:
                    # Distinguish two parallel arrays from a list of two tuples:
                    # if elements are scalars (not iterable), treat as parallel.
                    first = next(iter(a))
                    if not hasattr(first, '__iter__') or isinstance(first, str):
                        return [(float(r), float(d)) for r, d in zip(a, b)]
            except (TypeError, StopIteration):
                pass

    # --- Styles 4/5/6: iterable of individual items ---
    result = []
    for t in targets:
        if isinstance(t, str):
            result.append(t)
        elif hasattr(t, '__len__') and not isinstance(t, str) and len(t) >= 2:
            # tuple, list, or numpy array row with 2+ elements
            result.append((float(t[0]), float(t[1])))
        elif hasattr(t, 'item'):
            # numpy scalar — convert to native Python type
            result.append(str(t.item()))
        else:
            result.append(str(t))
    return result


def _resolve_target(t):
    """Resolve a single target entry to ``(label, ra, dec)``.

    Parameters
    ----------
    t : tuple, list, ndarray, or str
        A coordinate pair ``(ra, dec)`` in any container type,
        or a string object name like ``"NGC 788"``.

    Returns
    -------
    tuple[str, float, float]
        ``(display_label, ra_deg, dec_deg)``

    Raises
    ------
    ValueError
        If the target cannot be resolved to coordinates.
    """
    # --- Coordinate pair: tuple, list, or any 2+ element container ---
    if isinstance(t, (tuple, list)) and len(t) >= 2:
        try:
            ra, dec = float(t[0]), float(t[1])
            return f"({ra:.4f}, {dec:.4f})", ra, dec
        except (ValueError, TypeError):
            pass

    # numpy array row or similar indexable object
    if hasattr(t, '__len__') and not isinstance(t, str):
        try:
            if len(t) >= 2:
                ra, dec = float(t[0]), float(t[1])
                return f"({ra:.4f}, {dec:.4f})", ra, dec
        except (ValueError, TypeError, IndexError):
            pass

    # Fall through: treat as object name or "ra dec" string
    name = str(t)
    ra, dec = parse_coordinates(name)
    return name, ra, dec


def _fetch_one(idx, label, ra, dec, survey, fov, size):
    """Fetch a single cutout image (designed for use in a thread pool).

    Returns
    -------
    tuple[int, str, Image | None, Exception | None]
        ``(index, label, image_or_None, error_or_None)``
    """
    try:
        img = fetch_cutout(ra, dec, survey=survey, fov=fov, size=size)
        return idx, label, img, None
    except Exception as e:
        return idx, label, None, e


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch(target: str = "", ra: float = None, dec: float = None,
          survey: str = None, size: int = 0, fov: float = 1.0) -> Image.Image:
    """Fetch a sky cutout as a PIL Image.

    Specify the position by *either* an object name / coordinate string
    (``target``) *or* explicit ``ra`` and ``dec`` in degrees.

    Parameters
    ----------
    target : str, optional
        Object name (e.g. ``"NGC 788"``) or coordinate string
        (e.g. ``"150.0 2.2"`` or ``"10:00:00 +02:12:00"``).
    ra, dec : float, optional
        Right Ascension and Declination in decimal degrees.
    survey : str, optional
        Survey layer name (default: ``ls-dr10``).
        Use ``skyview.surveys()`` or ``SURVEYS.keys()`` to list options.
    size : int, optional
        Cutout size in pixels.  Usually you should use *fov* instead.
    fov : float, optional
        Field of view in arc-minutes (default ``1.0``).

    Returns
    -------
    PIL.Image.Image
        The cutout image.

    Examples
    --------
    >>> img = skyview.fetch("NGC 788", fov=2.0)
    >>> img.save("ngc788.jpg")

    >>> img = skyview.fetch(ra=30.28, dec=-23.5, survey="sdss")
    """
    if target:
        ra, dec = parse_coordinates(target)
    if ra is None or dec is None:
        raise ValueError("Provide target name or ra/dec")
    return fetch_cutout(ra, dec, survey=survey, size=size, fov=fov)


def show(target: str = "", ra: float = None, dec: float = None,
         survey: str = None, fov: float = 1.0, size: int = 0,
         title: str = "", figsize: tuple = (6, 6),
         scale_bar: bool = True, crosshair: bool = False, **kwargs) -> None:
    """Fetch and display a single sky image interactively.

    Works in Jupyter notebooks (inline) and standalone matplotlib windows.
    Supports zoom/pan via the matplotlib toolbar.

    Parameters
    ----------
    target : str, optional
        Object name or coordinate string.
    ra, dec : float, optional
        Coordinates in decimal degrees.
    survey : str, optional
        Survey layer (default: ``ls-dr10``).
    fov : float, optional
        Field of view in arc-minutes (default ``1.0``).
    size : int, optional
        Pixel size (prefer *fov*).
    title : str, optional
        Custom plot title.
    figsize : tuple, optional
        Matplotlib figure size in inches (default ``(6, 6)``).
    scale_bar : bool, optional
        Draw angular scale bar (default True).
    crosshair : bool, optional
        Draw center crosshair (default True).

    Examples
    --------
    >>> skyview.show("NGC 788")
    >>> skyview.show(ra=30.28, dec=-23.5, survey="sdss", fov=3.0)
    >>> skyview.show("M31", fov=10, scale_bar=True, crosshair=False)
    """
    import matplotlib.pyplot as plt
    from skyview.overlay import annotate

    if target:
        ra_r, dec_r = parse_coordinates(target)
    else:
        ra_r, dec_r = ra, dec

    img = fetch(ra=ra_r, dec=dec_r, survey=survey, fov=fov, size=size)

    # Add overlays
    img = annotate(img, fov, scale_bar=scale_bar, crosshair=crosshair)

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
          save: str = "", workers: int = 3, **kwargs) -> None:
    """Fetch and display a grid of sky image thumbnails.

    Downloads images concurrently for speed.  Thumbnail pixel size is
    automatically capped at :data:`BATCH_MAX_PIXELS` (512 px) unless
    *size* is set explicitly.

    Parameters
    ----------
    targets : various
        Flexible input — accepts any of the following:

        - **Two separate arrays** (positional): ``batch(ra_arr, dec_arr)``
        - **Tuple of two arrays**: ``batch((df["ra"], df["dec"]))``
        - **2-D array / DataFrame values**: ``batch(df[["ra","dec"]].values)``
        - **List of (ra, dec) tuples**: ``batch([(30.28, -23.5), ...])``
        - **List of object names**: ``batch(["NGC 788", "M31"])``
        - **Pandas Series / numpy array**: ``batch(series_of_names)``

    dec : array-like, optional
        Declination values when *targets* is an array of RA values.
    survey : str, optional
        Survey layer (default: ``ls-dr10``).
    fov : float, optional
        Field of view in arc-minutes (default ``1.0``).
    size : int, optional
        Force pixel size (overrides automatic cap).
    cols : int, optional
        Number of columns in the thumbnail grid (default ``5``).
    thumb_size : tuple, optional
        ``(width, height)`` per thumbnail in inches (default ``(3, 3)``).
    save : str, optional
        If set, save the grid figure to this file path instead of displaying.
    workers : int, optional
        Number of concurrent download threads (default ``3``).
        Keep low to avoid 429 rate limits from survey servers.

    Examples
    --------
    >>> skyview.batch(["NGC 788", "M31", "Coma Cluster"])

    >>> skyview.batch(df["ra"], df["dec"], fov=5, survey="ls-dr9")

    >>> skyview.batch(df[["ra", "dec"]].values, fov=3, cols=4)

    >>> skyview.batch((df["ra"], df["dec"]), save="gallery.png")
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

    # Concurrent downloads with progress
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
            # Add scale bar to each thumbnail
            from skyview.overlay import add_scale_bar
            img_annotated = add_scale_bar(img, fov)
            ax.imshow(np.array(img_annotated))
            ax.set_title(label, fontsize=8)
        else:
            ax.text(0.5, 0.5, f"Error:\n{err}", ha="center", va="center",
                    fontsize=7, transform=ax.transAxes, color="red")
            ax.set_title(label, fontsize=8, color="red")
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused subplots
    for idx in range(n, rows * cols):
        axes[idx // cols][idx % cols].set_visible(False)

    plt.tight_layout()
    if save:
        fig.savefig(save, dpi=150, bbox_inches="tight")
        print(f"Saved to {save}")
    else:
        plt.show()

    # Store results for interactive browsing
    batch._last_results = results
    batch._last_fov = fov
    batch._last_survey = survey


def resolve(name: str) -> tuple[float, float]:
    """Resolve an astronomical object name to coordinates.

    Uses CDS Sesame service (SIMBAD / NED / VizieR).

    Parameters
    ----------
    name : str
        Object name, e.g. ``"NGC 788"``, ``"M31"``, ``"Coma Cluster"``.

    Returns
    -------
    tuple[float, float]
        ``(ra, dec)`` in decimal degrees.

    Examples
    --------
    >>> ra, dec = skyview.resolve("NGC 788")
    >>> print(f"RA={ra:.4f}, Dec={dec:.4f}")
    """
    return resolve_name(name)


def batch_from_file(filepath: str, ra_col: str = "ra", dec_col: str = "dec",
                    name_col: str = "", survey: str = None, fov: float = 1.0,
                    cols: int = 5, save: str = "", limit: int = 50,
                    **kwargs) -> None:
    """Load targets from a catalog file and display as a thumbnail grid.

    Supported file formats: ``.csv``, ``.tsv``, ``.fits``.

    Parameters
    ----------
    filepath : str
        Path to the catalog file.
    ra_col : str, optional
        Column name for Right Ascension (default ``"ra"``).
    dec_col : str, optional
        Column name for Declination (default ``"dec"``).
    name_col : str, optional
        Column name for object labels.  If empty, coordinates are used.
    survey : str, optional
        Survey layer (default: ``ls-dr10``).
    fov : float, optional
        Field of view in arc-minutes (default ``1.0``).
    cols : int, optional
        Grid columns (default ``5``).
    save : str, optional
        Save figure to file instead of displaying.
    limit : int, optional
        Maximum number of targets to load (default ``50``).

    Examples
    --------
    >>> skyview.batch_from_file("catalog.csv", ra_col="RA", dec_col="DEC")

    >>> skyview.batch_from_file("sources.fits", name_col="NAME", fov=3, save="out.png")
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
        batch(targets, survey=survey, fov=fov, cols=cols, save=save, **kwargs)
    else:
        batch(ras, dec=decs, survey=survey, fov=fov, cols=cols, save=save, **kwargs)


def browse(targets=None, dec=None,
           survey: str = None, fov: float = 1.0, size: int = 0,
           scale_bar: bool = True, crosshair: bool = False,
           viewer: str = "", outdir: str = "", **kwargs) -> str:
    """Download images and open with a system image viewer for browsing.

    Downloads all images to a directory (with scale bar overlay), then
    launches an external image viewer (feh, eog, sxiv, etc.) that supports
    native keyboard navigation (arrows, zoom, etc.) — much better quality
    than terminal character rendering.

    In Jupyter/GUI environments, falls back to matplotlib interactive mode.

    Parameters
    ----------
    targets : various, optional
        Same formats as ``batch()``. If None, uses last batch() results.
    dec : array-like, optional
        Dec values when targets is RA array.
    survey : str, optional
        Survey layer.
    fov : float, optional
        Field of view in arc-minutes.
    scale_bar, crosshair : bool
        Overlay options.
    viewer : str, optional
        Image viewer command (default: auto-detect feh/sxiv/eog/xdg-open).
    outdir : str, optional
        Directory to save images. Default: temp directory.

    Returns
    -------
    str
        Path to the directory containing saved images.

    Examples
    --------
    >>> skyview.browse(["NGC 788", "M31", "Coma Cluster"], fov=5)

    >>> # After batch, browse with full resolution
    >>> skyview.batch(df["ra"], df["dec"], fov=5)
    >>> skyview.browse()

    >>> # Save to specific dir
    >>> skyview.browse(targets, outdir="./my_images")
    """
    import os
    import shutil
    import subprocess
    import tempfile
    from skyview.overlay import annotate

    # --- Collect images ---
    if targets is not None:
        items = _coerce_targets(targets, dec)
        resolved = []
        for t in items:
            try:
                resolved.append(_resolve_target(t))
            except Exception:
                resolved.append((str(t), None, None))

        images = []
        print(f"Fetching {len(resolved)} images...", flush=True)
        for i, (label, ra_t, dec_t) in enumerate(resolved):
            if ra_t is not None:
                try:
                    img = fetch_cutout(ra_t, dec_t, survey=survey, fov=fov, size=size)
                    images.append((i, label, img, None))
                except Exception as e:
                    images.append((i, label, None, e))
            else:
                images.append((i, label, None, ValueError("Could not resolve")))
            if (i + 1) % 5 == 0 or i + 1 == len(resolved):
                print(f"  {i+1}/{len(resolved)}", flush=True)
        browse_fov = fov
    elif hasattr(batch, '_last_results') and batch._last_results:
        images = batch._last_results
        browse_fov = getattr(batch, '_last_fov', fov)
    else:
        print("No images to browse. Call batch() first or provide targets.")
        return ""

    valid = [(idx, label, img, err) for idx, label, img, err in images if img is not None]
    if not valid:
        print("No valid images to browse.")
        return ""

    # --- Save images to directory ---
    if outdir:
        save_dir = outdir
        os.makedirs(save_dir, exist_ok=True)
    else:
        save_dir = tempfile.mkdtemp(prefix="skyview_browse_")

    saved_paths = []
    for i, (idx, label, img, _) in enumerate(valid):
        img_ann = annotate(img, browse_fov, scale_bar=scale_bar, crosshair=crosshair)
        # Clean label for filename
        safe_label = label.replace("/", "_").replace(" ", "_").replace("(", "").replace(")", "").replace(",", "_")
        filename = f"{i+1:03d}_{safe_label}.jpg"
        path = os.path.join(save_dir, filename)
        img_ann.save(path, quality=95)
        saved_paths.append(path)

    print(f"\n📁 {len(saved_paths)} images saved to: {save_dir}")

    # --- Try to open with image viewer ---
    # Detect available viewer
    if not viewer:
        # Prefer viewers with built-in browsing (arrow keys)
        for v in ("feh", "nsxiv", "sxiv", "eog", "gpicview", "xdg-open", "open"):
            if shutil.which(v):
                viewer = v
                break

    if viewer and shutil.which(viewer):
        has_display = (
            os.sys.platform == "darwin"
            or bool(os.environ.get("DISPLAY"))
            or bool(os.environ.get("WAYLAND_DISPLAY"))
        )

        if has_display:
            print(f"🔭 Opening with {viewer}...")
            print(f"   Controls: ← → to navigate, q to quit")
            try:
                if viewer == "feh":
                    # feh: --scale-down fits to screen, -d shows filename
                    subprocess.Popen([
                        "feh", "--scale-down", "-d", "-S", "filename",
                        "--draw-tinted",
                    ] + saved_paths)
                elif viewer in ("nsxiv", "sxiv"):
                    subprocess.Popen([viewer, "-t"] + saved_paths)
                elif viewer == "open":
                    # macOS: open first image, user can arrow through in Preview
                    subprocess.Popen(["open"] + saved_paths)
                else:
                    subprocess.Popen([viewer] + saved_paths)
            except Exception as e:
                print(f"⚠️  Could not launch {viewer}: {e}")
        else:
            print(f"💡 No display. View images on local machine:")
            print(f"   scp -r {os.environ.get('USER', 'user')}@host:{save_dir} .")
            print(f"   feh --scale-down -d {os.path.basename(save_dir)}/")
    else:
        print(f"💡 No image viewer found. Install one:")
        print(f"   sudo apt install feh   # lightweight, supports arrow key browsing")
        print(f"   View images: feh --scale-down -d {save_dir}/")

    return save_dir
