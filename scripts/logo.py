"""Draw docs/logo.jpg in Unicode braille, at each size the window may show it.

    python scripts/logo.py            # rewrites src/elsewhere/tui/logo.txt

Needs Pillow, which nothing else here does: the window only reads the text
this writes. Each braille character is a 2x4 grid of dots (U+2800 plus one
bit per dot), so line art keeps far more of its shape than it would in ASCII.
The drawing is thresholded rather than dithered: dithering turns the paper's
grain into scattered dots.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "docs" / "logo.jpg"
TARGET = REPOSITORY / "src" / "elsewhere" / "tui" / "logo.txt"

#: Widths in columns, smallest first; the window shows the largest that fits.
#: Close together, so a terminal of any height is filled: the logo is about
#: half as many rows as columns, and height is what runs out first.
WIDTHS = tuple(range(40, 129, 8))
#: Grey above this is paper, at or below it is ink (0 black, 255 white).
THRESHOLD = 150
#: Lighter than this counts as paper when cropping to the drawing.
PAPER = 215

#: Unicode's braille dot numbering: down the left column (1, 2, 3, 7), then
#: down the right (4, 5, 6, 8).
BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))

#: Between one size and the next in the file.
SEPARATOR = "\f\n"


def braille(image: Image.Image, columns: int) -> str:
    width = columns * 2
    height = round(image.height * width / image.width / 4) * 4
    scaled = ImageOps.autocontrast(image.resize((width, height), Image.LANCZOS), cutoff=1)
    ink = scaled.point(lambda grey: 0 if grey <= THRESHOLD else 255).load()
    lines = []
    for top in range(0, height, 4):
        characters = []
        for left in range(0, width, 2):
            code = 0
            for down, row in enumerate(BITS):
                for across, bit in enumerate(row):
                    if ink[left + across, top + down] == 0:
                        code |= bit
            # A blank cell is a space: some fonts draw U+2800 with a width of its own.
            characters.append(chr(0x2800 + code) if code else " ")
        lines.append("".join(characters).rstrip())
    return "\n".join(lines) + "\n"


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    image = Image.open(source).convert("L")
    drawing = ImageOps.invert(image).point(lambda grey: 255 if grey > 255 - PAPER else 0)
    image = image.crop(drawing.getbbox())
    TARGET.write_text(SEPARATOR.join(braille(image, columns) for columns in WIDTHS),
                      encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPOSITORY)}: {', '.join(map(str, WIDTHS))} columns")


if __name__ == "__main__":
    main()
