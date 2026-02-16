"""
skyview.cli — Command-line interface for skyview.

Provides ``skyview show``, ``skyview batch``, ``skyview resolve``,
and ``skyview surveys`` commands.

When no graphical display is available (e.g. remote SSH), images are
automatically rendered in the terminal using kitty/iTerm2/sixel
protocols, or saved to a temp file as fallback.
"""

from __future__ import annotations
import os
import sys
import shutil
import tempfile
import click

from skyview.surveys import SURVEYS, DEFAULT_SURVEY


# ---------------------------------------------------------------------------
# Terminal image display helpers
# ---------------------------------------------------------------------------

def _has_display() -> bool:
    """Check if a graphical display (X11/Wayland/macOS) is available."""
    if sys.platform == "darwin":
        return True  # macOS always has a display
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _detect_terminal_protocol() -> str:
    """Detect which terminal image protocol is supported.

    Returns one of: 'kitty', 'iterm2', 'sixel', 'chafa', 'none'.
    """
    term = os.environ.get("TERM", "")
    term_program = os.environ.get("TERM_PROGRAM", "")

    # Kitty terminal
    if "kitty" in term or "kitty" in term_program:
        return "kitty"

    # iTerm2 (supports inline images)
    if term_program == "iTerm.app" or os.environ.get("ITERM_SESSION_ID"):
        return "iterm2"

    # Check for sixel support via terminal type
    if "sixel" in term:
        return "sixel"

    # Fallback: check if chafa/timg/viu CLI tools are available
    for tool in ("chafa", "timg", "viu"):
        if shutil.which(tool):
            return tool

    return "none"


def _display_in_terminal(image_path: str, width: int = 80) -> bool:
    """Try to display an image directly in the terminal.

    Returns True if successful.
    """
    import subprocess

    protocol = _detect_terminal_protocol()

    if protocol == "kitty":
        # Kitty graphics protocol via kitten icat
        kitten = shutil.which("kitten") or shutil.which("kitty")
        if kitten:
            cmd = [kitten, "icat" if "kitten" in kitten else "+kitten", "icat",
                   "--align=left", image_path]
            if "kitten" in (kitten or ""):
                cmd = [kitten, "icat", "--align=left", image_path]
            else:
                cmd = [kitten, "+kitten", "icat", "--align=left", image_path]
            try:
                subprocess.run(cmd, check=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

    elif protocol == "iterm2":
        # iTerm2 inline image protocol
        import base64
        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        # ESC ] 1337 ; File=inline=1 : <base64> ST
        sys.stdout.write(f"\033]1337;File=inline=1;width=auto:{data}\a\n")
        sys.stdout.flush()
        return True

    elif protocol == "sixel":
        # Try img2sixel
        img2sixel = shutil.which("img2sixel")
        if img2sixel:
            try:
                subprocess.run([img2sixel, "-w", str(width * 10), image_path],
                               check=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

    elif protocol in ("chafa", "timg", "viu"):
        try:
            if protocol == "chafa":
                # Use symbols mode for best quality, higher size for detail
                subprocess.run([
                    "chafa",
                    "--size", f"{width}x",
                    "--symbols", "block+border+space+extra",
                    "--color-space", "din99d",
                    image_path
                ], check=True)
            elif protocol == "timg":
                subprocess.run(["timg", "-g", f"{width}x0", image_path],
                               check=True)
            elif protocol == "viu":
                subprocess.run(["viu", "-w", str(width), image_path],
                               check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    return False


def _show_image_cli(img, title: str = ""):
    """Display a PIL Image in the best available way.

    Priority:
    1. If graphical display available → matplotlib window
    2. Terminal image protocol (kitty/iTerm2/sixel/chafa)
    3. Save to temp file and print path
    """
    if _has_display():
        # Use matplotlib GUI
        import matplotlib.pyplot as plt
        import numpy as np
        fig, ax = plt.subplots(1, 1, figsize=(8, 8))
        ax.imshow(np.array(img))
        ax.set_title(title)
        ax.set_xticks([])
        ax.set_yticks([])
        plt.tight_layout()
        plt.show()
        return

    # No GUI — try terminal display
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = f.name
        img.save(tmp_path, quality=90)

    if title:
        click.echo(f"🔭 {title}")

    if _display_in_terminal(tmp_path):
        os.unlink(tmp_path)
    else:
        # Can't display — keep the file and tell user
        click.echo(f"💾 No display available. Image saved to: {tmp_path}")
        click.echo(f"   Copy to local machine:  scp {os.environ.get('USER', 'user')}@host:{tmp_path} .")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
@click.version_option()
def main():
    """🔭 skyview — Browse astronomical sky images from the terminal."""
    pass


@main.command()
@click.argument("target", nargs=-1, required=True)
@click.option("-s", "--survey", default=DEFAULT_SURVEY,
              help=f"Survey layer ({', '.join(SURVEYS.keys())})")
@click.option("-f", "--fov", default=1.0, type=float,
              help="Field of view in arcmin (default: 1.0)")
@click.option("--size", default=0, type=int, help="Image size in pixels")
@click.option("-o", "--output", default="", help="Save image to file instead of displaying")
def show(target, survey, fov, size, output):
    """Show sky image at a position.

    TARGET can be an object name (NGC 788, M31) or coordinates (30.28 -23.5).

    On remote servers without a graphical display, the image is rendered
    directly in the terminal (kitty/iTerm2/sixel) or saved to a temp file.

    Examples:

        skyview show NGC 788

        skyview show 30.28 -23.5

        skyview show "10:00:00 +02:12:00"

        skyview show NGC 788 -s sdss -f 3.0

        skyview show NGC 788 -o ngc788.jpg
    """
    from skyview.api import fetch
    from skyview.resolver import parse_coordinates

    target_str = " ".join(target)
    ra, dec = parse_coordinates(target_str)
    click.echo(f"📍 {target_str} → RA={ra:.5f}°, Dec={dec:.5f}°")

    img = fetch(ra=ra, dec=dec, survey=survey, fov=fov, size=size)

    # Add scale bar and crosshair
    from skyview.overlay import annotate
    img = annotate(img, fov)

    if output:
        img.save(output)
        click.echo(f"💾 Saved to {output}")
    else:
        _show_image_cli(img, title=f"{target_str}  [{survey}]  FoV={fov}'")


@main.command()
@click.argument("targets", nargs=-1, required=False)
@click.option("-f", "--file", "filepath", default="",
              help="CSV/FITS file with coordinates")
@click.option("--ra-col", default="ra", help="RA column name")
@click.option("--dec-col", default="dec", help="Dec column name")
@click.option("--name-col", default="", help="Name/label column")
@click.option("-s", "--survey", default=DEFAULT_SURVEY)
@click.option("--fov", default=1.0, type=float, help="FoV in arcmin")
@click.option("--cols", default=5, type=int, help="Grid columns")
@click.option("-n", "--limit", default=50, type=int, help="Max targets")
@click.option("-o", "--output", default="", help="Save grid to file")
def batch(targets, filepath, ra_col, dec_col, name_col,
          survey, fov, cols, limit, output):
    """Show a grid of sky images.

    Pass object names or a file with coordinates.

    On remote servers, the grid is saved and displayed in terminal or
    as a temp file you can scp to your local machine.

    Examples:

        skyview batch "NGC 788" "M31" "NGC 1275"

        skyview batch -f catalog.csv --ra-col RA --dec-col DEC

        skyview batch -f sources.fits -o gallery.png
    """
    from skyview.api import batch as api_batch, batch_from_file

    # If no display and no output specified, auto-save to temp file
    if not output and not _has_display():
        output = tempfile.mktemp(suffix=".png", prefix="skyview_batch_")
        auto_save = True
    else:
        auto_save = False

    if filepath:
        batch_from_file(filepath, ra_col=ra_col, dec_col=dec_col,
                        name_col=name_col, survey=survey, fov=fov,
                        cols=cols, save=output, limit=limit)
    elif targets:
        api_batch(list(targets), survey=survey, fov=fov, cols=cols, save=output)
    else:
        click.echo("Provide targets or --file. See: skyview batch --help")
        sys.exit(1)

    # If we auto-saved, try to display in terminal
    if auto_save and os.path.exists(output):
        if not _display_in_terminal(output):
            click.echo(f"💾 Grid saved to: {output}")


@main.command()
@click.argument("name")
def resolve(name):
    """Resolve an object name to RA/Dec.

    Examples:

        skyview resolve "NGC 788"

        skyview resolve M31
    """
    from skyview.resolver import resolve_name

    try:
        ra, dec = resolve_name(name)
        click.echo(f"📍 {name} → RA={ra:.6f}°, Dec={dec:.6f}°")
    except Exception as e:
        click.echo(f"❌ Could not resolve '{name}': {e}", err=True)
        sys.exit(1)


@main.command()
def surveys():
    """List available surveys with coverage details."""
    click.echo("Available surveys (sorted by fallback priority):\n")
    for name in sorted(SURVEYS.keys(), key=lambda k: SURVEYS[k].priority, reverse=True):
        cfg = SURVEYS[name]
        marker = " ← default" if name == DEFAULT_SURVEY else ""
        bands = f"  bands={cfg.bands}" if cfg.bands else ""
        click.echo(f"  {name:15s}  pixscale={cfg.default_pixscale:.3f}\"/px  "
                    f"dec=[{cfg.dec_range[0]:+.0f}°,{cfg.dec_range[1]:+.0f}°]"
                    f"{bands}{marker}")


@main.command()
@click.argument("targets", nargs=-1, required=False)
@click.option("-f", "--file", "filepath", default="",
              help="CSV/FITS file with coordinates")
@click.option("--ra-col", default="ra", help="RA column name")
@click.option("--dec-col", default="dec", help="Dec column name")
@click.option("-s", "--survey", default=DEFAULT_SURVEY)
@click.option("--fov", default=1.0, type=float, help="FoV in arcmin")
@click.option("-n", "--limit", default=50, type=int, help="Max targets")
def browse(targets, filepath, ra_col, dec_col, survey, fov, limit):
    """Interactively browse sky images one by one (keyboard navigation).

    Works in terminal (SSH) — uses chafa/kitty/sixel for display.
    Controls: n/→ next, p/← prev, q quit.

    Examples:

        skyview browse "NGC 788" "M31" "NGC 1275"

        skyview browse -f catalog.csv --ra-col RA --dec-col DEC

        skyview browse -f sources.fits --fov 5
    """
    from skyview.api import browse as api_browse, batch_from_file

    if filepath:
        # Load from file
        from pathlib import Path
        ext = Path(filepath).suffix.lower()
        if ext in (".fits", ".fit"):
            from astropy.table import Table
            tbl = Table.read(filepath)
            ras = list(tbl[ra_col][:limit])
            decs = list(tbl[dec_col][:limit])
        elif ext in (".csv", ".tsv", ".txt"):
            import csv
            sep = "\t" if ext == ".tsv" else ","
            with open(filepath) as f:
                reader = csv.DictReader(f, delimiter=sep)
                rows = list(reader)[:limit]
            ras = [float(r[ra_col]) for r in rows]
            decs = [float(r[dec_col]) for r in rows]
        else:
            click.echo(f"Unsupported format: {ext}")
            sys.exit(1)
        api_browse(ras, dec=decs, survey=survey, fov=fov)
    elif targets:
        api_browse(list(targets), survey=survey, fov=fov)
    else:
        click.echo("Provide targets or --file. See: skyview browse --help")
        sys.exit(1)


@main.command(name="cache-clear")
def cache_clear():
    """Clear the local image cache."""
    from skyview.cache import clear_cache, cache_size, CACHE_DIR
    count, size_mb = cache_size()
    if count == 0:
        click.echo("Cache is empty.")
        return
    click.echo(f"Cache: {count} files, {size_mb:.1f} MB in {CACHE_DIR}")
    removed = clear_cache()
    click.echo(f"✅ Removed {removed} cached images.")


@main.command(name="cache-info")
def cache_info():
    """Show cache location and size."""
    from skyview.cache import cache_size, CACHE_DIR
    count, size_mb = cache_size()
    click.echo(f"📁 Cache directory: {CACHE_DIR}")
    click.echo(f"   Files: {count}")
    click.echo(f"   Size:  {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
