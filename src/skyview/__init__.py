"""
skyview-cli: Browse astronomical sky images from the command line and Jupyter.

Quick start::

    import skyview

    # Single object
    skyview.show("NGC 788")

    # Batch from DataFrame
    skyview.batch(df["ra"], df["dec"], fov=5)

    # Fetch raw image
    img = skyview.fetch("M31", fov=10)
    img.save("m31.jpg")
"""
__version__ = "0.1.0"

from skyview.api import show, batch, fetch, resolve, batch_from_file, browse  # noqa: F401
from skyview.cache import clear_cache, cache_size  # noqa: F401
