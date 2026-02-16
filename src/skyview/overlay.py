"""
skyview.overlay — Image overlays: scale bar, crosshair, labels.

Draws annotations on sky cutout images using PIL.
"""

from __future__ import annotations
from PIL import Image, ImageDraw, ImageFont


def add_scale_bar(img: Image.Image, fov_arcmin: float,
                  bar_fraction: float = 0.2,
                  color: str = "white", shadow: bool = True,
                  position: str = "bottom-right") -> Image.Image:
    """Draw an angular scale bar on the image.

    Parameters
    ----------
    img : PIL.Image.Image
        Input image (not modified in-place; a copy is returned).
    fov_arcmin : float
        Field of view of the image in arc-minutes.
    bar_fraction : float
        Target bar length as fraction of image width (default 0.2 = 20%).
    color : str
        Bar color (default "white").
    shadow : bool
        Draw dark shadow behind bar for contrast (default True).
    position : str
        Bar position: "bottom-right", "bottom-left", "top-right", "top-left".

    Returns
    -------
    PIL.Image.Image
        Annotated copy of the image.
    """
    img = img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # Calculate a "nice" bar length in arcsec
    target_arcsec = fov_arcmin * 60 * bar_fraction
    nice_values = [1, 2, 5, 10, 15, 20, 30, 60, 120, 180, 300, 600, 1200, 1800, 3600]
    bar_arcsec = min(nice_values, key=lambda x: abs(x - target_arcsec))

    # Bar length in pixels
    arcsec_per_pixel = (fov_arcmin * 60) / w
    bar_px = int(bar_arcsec / arcsec_per_pixel)
    bar_px = max(10, min(bar_px, int(w * 0.4)))  # clamp

    # Label
    if bar_arcsec >= 60:
        label = f"{bar_arcsec / 60:.0f}'"
    else:
        label = f'{bar_arcsec:.0f}"'

    # Position
    margin = int(w * 0.05)
    bar_h = max(3, int(h * 0.008))

    if "bottom" in position:
        y = h - margin - bar_h
    else:
        y = margin

    if "right" in position:
        x_end = w - margin
        x_start = x_end - bar_px
    else:
        x_start = margin
        x_end = x_start + bar_px

    # Draw shadow first for contrast
    if shadow:
        offset = max(1, bar_h // 2)
        draw.rectangle([x_start - offset, y - offset,
                        x_end + offset, y + bar_h + offset],
                       fill="black", outline=None)

    # Draw bar
    draw.rectangle([x_start, y, x_end, y + bar_h], fill=color)

    # Draw ticks at ends
    tick_h = bar_h * 3
    draw.rectangle([x_start, y - tick_h // 2, x_start + max(1, bar_h // 2), y + bar_h + tick_h // 2], fill=color)
    draw.rectangle([x_end - max(1, bar_h // 2), y - tick_h // 2, x_end, y + bar_h + tick_h // 2], fill=color)

    # Draw label
    try:
        font_size = max(10, int(h * 0.03))
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()

    text_x = (x_start + x_end) // 2
    text_y = y - int(h * 0.04)

    # Shadow text
    if shadow:
        draw.text((text_x + 1, text_y + 1), label, fill="black", font=font, anchor="mm")
    draw.text((text_x, text_y), label, fill=color, font=font, anchor="mm")

    return img


def add_crosshair(img: Image.Image, color: str = "lime",
                  size: float = 0.05, width: int = 1) -> Image.Image:
    """Draw a crosshair at the center of the image.

    Parameters
    ----------
    img : PIL.Image.Image
        Input image.
    color : str
        Crosshair color (default "lime").
    size : float
        Crosshair arm length as fraction of image size (default 0.05).
    width : int
        Line width in pixels.

    Returns
    -------
    PIL.Image.Image
        Annotated copy.
    """
    img = img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    cx, cy = w // 2, h // 2
    arm = int(min(w, h) * size)
    gap = max(2, arm // 4)  # small gap at center

    # Horizontal arms
    draw.line([(cx - arm, cy), (cx - gap, cy)], fill=color, width=width)
    draw.line([(cx + gap, cy), (cx + arm, cy)], fill=color, width=width)
    # Vertical arms
    draw.line([(cx, cy - arm), (cx, cy - gap)], fill=color, width=width)
    draw.line([(cx, cy + gap), (cx, cy + arm)], fill=color, width=width)

    return img


def annotate(img: Image.Image, fov_arcmin: float,
             scale_bar: bool = True, crosshair: bool = True) -> Image.Image:
    """Add standard annotations (scale bar + crosshair) to an image.

    Parameters
    ----------
    img : PIL.Image.Image
        Input image.
    fov_arcmin : float
        Field of view in arc-minutes.
    scale_bar : bool
        Whether to add a scale bar (default True).
    crosshair : bool
        Whether to add a center crosshair (default True).

    Returns
    -------
    PIL.Image.Image
        Annotated copy.
    """
    result = img
    if scale_bar:
        result = add_scale_bar(result, fov_arcmin)
    if crosshair:
        result = add_crosshair(result)
    return result
