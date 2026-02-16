"""CLI interface for skyview."""

from __future__ import annotations
import sys
import click

from skyview.surveys import SURVEYS, DEFAULT_SURVEY


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

    Examples:

        skyview show NGC 788

        skyview show 30.28 -23.5

        skyview show "10:00:00 +02:12:00"

        skyview show NGC 788 -s sdss -f 3.0

        skyview show NGC 788 -o ngc788.jpg
    """
    from skyview.api import show as api_show, fetch
    from skyview.resolver import parse_coordinates

    target_str = " ".join(target)
    ra, dec = parse_coordinates(target_str)
    click.echo(f"📍 {target_str} → RA={ra:.5f}°, Dec={dec:.5f}°")

    if output:
        img = fetch(ra=ra, dec=dec, survey=survey, fov=fov, size=size)
        img.save(output)
        click.echo(f"💾 Saved to {output}")
    else:
        api_show(ra=ra, dec=dec, survey=survey, fov=fov, size=size,
                 title=target_str)


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

    Examples:

        skyview batch "NGC 788" "M31" "NGC 1275"

        skyview batch -f catalog.csv --ra-col RA --dec-col DEC

        skyview batch -f sources.fits -o gallery.png
    """
    from skyview.api import batch as api_batch, batch_from_file

    if filepath:
        batch_from_file(filepath, ra_col=ra_col, dec_col=dec_col,
                        name_col=name_col, survey=survey, fov=fov,
                        cols=cols, save=output, limit=limit)
    elif targets:
        api_batch(list(targets), survey=survey, fov=fov, cols=cols, save=output)
    else:
        click.echo("Provide targets or --file. See: skyview batch --help")
        sys.exit(1)


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
    """List available surveys."""
    for name, cfg in SURVEYS.items():
        marker = " ← default" if name == DEFAULT_SURVEY else ""
        click.echo(f"  {name:15s}  pixscale={cfg.default_pixscale}\"  "
                    f"max={cfg.max_size}px{marker}")


if __name__ == "__main__":
    main()
