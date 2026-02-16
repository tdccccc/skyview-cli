"""Core API — the main interface for both CLI and Jupyter."""

from __future__ import annotations
import math
from pathlib import Path
from typing import Sequence, Optional, Union
from PIL import Image
import numpy as np

from skyview.surveys import fetch_cutout, get_survey, SURVEYS, DEFAULT_SURVEY
from skyview.resolver import parse_coordinates, resolve_name


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


def batch(targets: Sequence[Union[str, tuple]],
          dec: Sequence[float] = None,
          survey: str = None, fov: float = 1.0, size: int = 0,
          cols: int = 5, thumb_size: tuple = (3, 3),
          save: str = "", **kwargs) -> None:
    """Fetch and display a grid of sky images.

    Args:
        targets: list of object names, "ra dec" strings, or (ra, dec) tuples.
                 Can also be a sequence of RA values if `dec` is provided.
        dec: optional sequence of Dec values (when targets is a sequence of RAs)
        survey: survey layer
        fov: field of view in arcmin
        cols: number of columns in grid
        thumb_size: (width, height) per thumbnail in inches
        save: if set, save figure to this path instead of showing

    Examples:
        batch(["NGC 788", "M31"])
        batch([(30.28, -23.5), (10.68, 41.27)])
        batch(df["ra"], df["dec"])
        batch(list(zip(df["ra"], df["dec"])))
    """
    import matplotlib.pyplot as plt

    # Handle batch(ra_array, dec_array) style calls
    if dec is not None:
        targets = list(zip(targets, dec))
    else:
        # Detect batch((ra_series, dec_series)) — tuple of two array-likes
        if (isinstance(targets, tuple) and len(targets) == 2
                and hasattr(targets[0], '__len__') and hasattr(targets[1], '__len__')
                and not isinstance(targets[0], str)):
            try:
                if len(targets[0]) > 2:  # likely two arrays, not a single (ra,dec) pair
                    targets = list(zip(targets[0], targets[1]))
            except TypeError:
                pass

    n = len(targets)
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols,
                             figsize=(thumb_size[0] * cols, thumb_size[1] * rows),
                             squeeze=False)

    for idx, t in enumerate(targets):
        ax = axes[idx // cols][idx % cols]
        try:
            if isinstance(t, (list, tuple)) and len(t) >= 2:
                ra_t, dec_t = float(t[0]), float(t[1])
                label = f"({ra_t:.2f}, {dec_t:.2f})"
            else:
                ra_t, dec_t = parse_coordinates(str(t))
                label = str(t)

            img = fetch(ra=ra_t, dec=dec_t, survey=survey, fov=fov, size=size)
            ax.imshow(np.array(img))
            ax.set_title(label, fontsize=8)
        except Exception as e:
            ax.text(0.5, 0.5, f"Error:\n{e}", ha="center", va="center",
                    fontsize=7, transform=ax.transAxes, color="red")
            ax.set_title(str(t), fontsize=8, color="red")

        ax.set_xticks([])
        ax.set_yticks([])

    # Hide empty subplots
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
        ras = tbl[ra_col][:limit]
        decs = tbl[dec_col][:limit]
        names = tbl[name_col][:limit] if name_col and name_col in tbl.colnames else None
    elif ext in (".csv", ".tsv", ".txt"):
        import csv
        sep = "\t" if ext == ".tsv" else ","
        with open(path) as f:
            reader = csv.DictReader(f, delimiter=sep)
            rows = list(reader)[:limit]
        ras = [float(r[ra_col]) for r in rows]
        decs = [float(r[dec_col]) for r in rows]
        names = [r[name_col] for r in rows] if name_col and name_col in rows[0] else None
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use .csv, .tsv, .fits")

    if names:
        targets = [(f"{n}\n({ra:.2f},{dec:.2f})", ra, dec)
                    for n, ra, dec in zip(names, ras, decs)]
        # Override to pass labeled tuples
        _batch_labeled(targets, survey=survey, fov=fov, cols=cols, save=save, **kwargs)
    else:
        targets = list(zip(ras, decs))
        batch(targets, survey=survey, fov=fov, cols=cols, save=save, **kwargs)


def _batch_labeled(targets: list[tuple[str, float, float]],
                   survey: str = None, fov: float = 1.0, cols: int = 5,
                   thumb_size: tuple = (3, 3), save: str = "",
                   size: int = 0, **kwargs) -> None:
    """Internal: batch display with custom labels."""
    import matplotlib.pyplot as plt

    n = len(targets)
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols,
                             figsize=(thumb_size[0] * cols, thumb_size[1] * rows),
                             squeeze=False)
    for idx, (label, ra, dec) in enumerate(targets):
        ax = axes[idx // cols][idx % cols]
        try:
            img = fetch(ra=ra, dec=dec, survey=survey, fov=fov, size=size)
            ax.imshow(np.array(img))
            ax.set_title(label, fontsize=7)
        except Exception as e:
            ax.text(0.5, 0.5, str(e), ha="center", va="center",
                    fontsize=7, transform=ax.transAxes, color="red")
            ax.set_title(label, fontsize=7, color="red")
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
