#!/usr/bin/env python3
"""
Prepare a raw image (upload or clipboard) for use as a figure in these notes:
flattens transparency onto a solid white background, trims excess margin,
adds a uniform white border, and writes a PNG under assets/images/.

Examples:
    # From an uploaded/saved file, writing straight to an assets/images/ subfolder
    python3 tools/prepare-figure.py ~/Downloads/screenshot.png \\
        -o ch-01-biomolecules/sec-amino-acids/fig-new-diagram.png

    # From the clipboard (no input file given)
    python3 tools/prepare-figure.py -o ch-02-cells/sec-cell-membranes/fig-pump.png

    # Write to an arbitrary path instead of under assets/images/
    python3 tools/prepare-figure.py in.png -o /tmp/out.png --absolute
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageGrab

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSETS_ROOT = REPO_ROOT / "assets" / "images"


def load_from_clipboard() -> Image.Image:
    try:
        grabbed = ImageGrab.grabclipboard()
    except Exception as exc:
        raise SystemExit(
            f"Clipboard access failed ({exc}).\n"
            "This environment likely has no working display/clipboard "
            "(headless container). Save the image to a file and pass its "
            "path instead."
        )
    if grabbed is None:
        raise SystemExit(
            "No image found on the clipboard.\n"
            "This can also mean the environment has no clipboard access "
            "(headless container without xclip/wl-clipboard + a display).\n"
            "Save the image to a file and pass its path instead."
        )
    if isinstance(grabbed, list):
        # Some platforms hand back a list of file paths (e.g. a copied file)
        # rather than image bytes.
        if not grabbed:
            raise SystemExit("Clipboard did not contain an image or file.")
        return Image.open(grabbed[0])
    return grabbed


def load_image(input_path: str | None) -> Image.Image:
    if input_path is None:
        return load_from_clipboard()
    path = Path(input_path).expanduser()
    if not path.is_file():
        raise SystemExit(f"Input file not found: {path}")
    return Image.open(path)


def autocrop(im: Image.Image, tolerance: int = 8) -> Image.Image:
    """Trim uniform background margin. Uses the alpha channel if the image
    has real transparency, otherwise diffs against the corner color."""
    if im.mode == "RGBA":
        alpha = im.split()[-1]
        if alpha.getextrema()[0] < 255:  # some real transparency present
            bbox = alpha.getbbox()
            return im.crop(bbox) if bbox else im

    rgb = im.convert("RGB")
    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)),
        rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    bg_color = max(set(corners), key=corners.count)
    bg = Image.new("RGB", rgb.size, bg_color)
    diff = ImageChops.difference(rgb, bg)
    diff = diff.convert("L").point(lambda p: 255 if p > tolerance else 0)
    bbox = diff.getbbox()
    return im.crop(bbox) if bbox else im


def flatten_onto_white(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        white = Image.new("RGB", im.size, (255, 255, 255))
        white.paste(im, mask=im.split()[-1])
        return white
    return im.convert("RGB")


def add_padding(im: Image.Image, pad_fraction: float) -> Image.Image:
    if pad_fraction <= 0:
        return im
    pad = round(pad_fraction * max(im.size))
    if pad == 0:
        return im
    padded = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), (255, 255, 255))
    padded.paste(im, (pad, pad))
    return padded


def downscale_if_needed(im: Image.Image, max_dim: int) -> Image.Image:
    if max_dim <= 0 or max(im.size) <= max_dim:
        return im
    scale = max_dim / max(im.size)
    new_size = (round(im.width * scale), round(im.height * scale))
    return im.resize(new_size, Image.LANCZOS)


def resolve_output_path(out_arg: str, absolute: bool) -> Path:
    out_path = Path(out_arg).expanduser()
    if absolute or out_path.is_absolute():
        return out_path
    return DEFAULT_ASSETS_ROOT / out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Path to the source image. Omit to read from the clipboard instead.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help=(
            "Where to write the processed PNG. By default this is resolved "
            "relative to assets/images/ (e.g. 'ch-01-biomolecules/sec-amino-acids/"
            "fig-foo.png'). Use --absolute (or pass an absolute path) to write "
            "somewhere else."
        ),
    )
    parser.add_argument(
        "--absolute",
        action="store_true",
        help="Treat --output as a literal path instead of resolving it under assets/images/.",
    )
    parser.add_argument(
        "--pad",
        type=float,
        default=0.06,
        metavar="FRACTION",
        help="White padding to add on each side, as a fraction of the larger "
        "dimension after cropping (default: 0.06). Use 0 to disable.",
    )
    parser.add_argument(
        "--no-autocrop",
        action="store_true",
        help="Skip trimming the existing background margin before padding.",
    )
    parser.add_argument(
        "--max-dim",
        type=int,
        default=2200,
        help="Downscale so the larger dimension is at most this many pixels "
        "(default: 2200). Use 0 to disable.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    args = parser.parse_args()

    out_path = resolve_output_path(args.output, args.absolute)
    if out_path.exists() and not args.force:
        raise SystemExit(f"{out_path} already exists. Pass --force to overwrite.")

    im = load_image(args.input)
    im = flatten_onto_white(im)
    if not args.no_autocrop:
        im = autocrop(im)
    im = add_padding(im, args.pad)
    im = downscale_if_needed(im, args.max_dim)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, "PNG", optimize=True)
    print(f"Wrote {im.width}x{im.height} image to {out_path}")


if __name__ == "__main__":
    main()
