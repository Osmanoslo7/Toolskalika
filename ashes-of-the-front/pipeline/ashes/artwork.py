"""Layer PNG checks for the artwork convention (CLAUDE.md, "Artwork convention").

Every check here is deterministic: the same bytes always produce the same result.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .config import ArtworkSettings
from .report import Report

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Perceptual hashes are taken over neutral grey, so transparent pixels don't skew them.
HASH_BACKGROUND = (128, 128, 128, 255)


class ArtworkError(Exception):
    """The file cannot be used as artwork. The message says why in a few words."""


@dataclass(frozen=True)
class LayerFacts:
    width: int
    height: int
    bbox: tuple[int, int, int, int]  # bounding box of visible (alpha > 0) pixels
    sha256: str  # exact identity of the file bytes
    ahash: str  # 64-bit average hash, for human-review comparisons
    dhash: str  # 64-bit difference hash, for human-review comparisons


def load_png(path: Path) -> Image.Image:
    """Read and fully decode a PNG. Raises ArtworkError if it is not a usable PNG."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ArtworkError(f"unreadable ({exc.strerror})") from exc
    if not data.startswith(PNG_SIGNATURE):
        raise ArtworkError("not a PNG (bad signature)")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()  # checks chunk CRCs and structure
        with Image.open(io.BytesIO(data)) as image:
            image.load()  # decodes the pixel data, catching truncation
            return image.copy()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise ArtworkError(f"corrupted PNG ({exc})") from exc


def _hash_bits(bits: list[bool]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def _grey(image: Image.Image) -> Image.Image:
    base = Image.new("RGBA", image.size, HASH_BACKGROUND)
    return Image.alpha_composite(base, image.convert("RGBA")).convert("L")


def average_hash(image: Image.Image) -> str:
    small = _grey(image).resize((8, 8), Image.Resampling.BOX)
    px = small.load()
    pixels = [px[x, y] for y in range(8) for x in range(8)]
    mean = sum(pixels) / len(pixels)
    return _hash_bits([p > mean for p in pixels])


def difference_hash(image: Image.Image) -> str:
    small = _grey(image).resize((9, 8), Image.Resampling.BOX)
    px = small.load()
    return _hash_bits([px[x, y] > px[x + 1, y] for y in range(8) for x in range(8)])


def hamming(a: str, b: str) -> int:
    """Number of differing bits between two 64-bit hashes. 0 = visually identical at this resolution."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def layer_facts(path: Path, image: Image.Image) -> LayerFacts:
    box = image.getchannel("A").getbbox() or (0, 0, 0, 0)
    return LayerFacts(
        width=image.width,
        height=image.height,
        bbox=box,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        ahash=average_hash(image),
        dhash=difference_hash(image),
    )


def check_point(report: Report, label: str, what: str, point: list[float], canvas: tuple[int, int]) -> None:
    """A pivot or root point must lie on the canvas (edges included)."""
    width, height = canvas
    x, y = point
    if not (0 <= x <= width and 0 <= y <= height):
        report.error(f"{label}: {what} {point} is outside the {width}x{height} canvas")


def check_layer(
    report: Report,
    label: str,
    rel: str,
    path: Path,
    canvas: tuple[int, int],
    settings: ArtworkSettings,
    approved: bool,
) -> LayerFacts | None:
    """Check one layer PNG against the artwork convention. Returns its facts if it is usable."""
    if not path.is_file():
        report.issue(approved, f"{label}: missing file '{rel}'")
        return None
    try:
        image = load_png(path)
    except ArtworkError as exc:
        report.error(f"{label}: '{rel}' is {exc}")
        return None

    if image.mode != "RGBA":
        reason = "no alpha channel" if "A" not in image.getbands() else f"mode {image.mode}"
        report.error(f"{label}: '{rel}' has {reason}; export layers as RGBA PNG")
        return None

    width, height = canvas
    if image.size != canvas:
        report.error(f"{label}: '{rel}' is {image.width}x{image.height}, canvas is {width}x{height}")
        return None

    alpha = image.getchannel("A")
    box = alpha.getbbox()
    if box is None:
        report.error(f"{label}: '{rel}' has no visible pixels")
        return None

    pixels = width * height
    pad = settings.padding_px
    left, top, right, bottom = box
    if left < pad or top < pad or right > width - pad or bottom > height - pad:
        report.error(f"{label}: '{rel}' content {list(box)} breaks the {pad}px transparent padding")

    transparent = alpha.histogram()[0] / pixels
    if transparent < settings.min_transparent_fraction:
        report.error(
            f"{label}: '{rel}' is only {transparent:.0%} transparent; "
            f"at least {settings.min_transparent_fraction:.0%} is required"
        )

    # A layer is a cut-out, not a picture. One opaque colour covering most of the canvas is a background.
    colours = image.getcolors(maxcolors=pixels) or []
    fill = max((count for count, px in colours if px[3] == 255), default=0)
    if fill / pixels > settings.max_background_fraction:
        report.error(
            f"{label}: '{rel}' has a solid opaque fill covering {fill / pixels:.0%} "
            "of the canvas (background pixels)"
        )

    return layer_facts(path, image)
