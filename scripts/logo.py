"""Draw docs/logo.jpg in Unicode braille, at each size the window may show it,
as the frames of one beat of its wings, while the snake's scales creep on.

    python scripts/logo.py            # rewrites src/elsewhere/interface/tui/logo.json.xz

Needs Pillow, which nothing else here does: the window only reads the frames
this writes. Each braille character is a 2x4 grid of dots (U+2800 plus one
bit per dot), so line art keeps far more of its shape than it would in ASCII.
The drawing is thresholded rather than dithered: dithering turns the paper's
grain into scattered dots. The threshold is local (adaptive mean thresholding,
Gonzalez & Woods, *Digital Image Processing*, §10.3; OpenCV's
ADAPTIVE_THRESH_MEAN_C): a dot is ink when it is darker than the dots around
it, not darker than one grey for the whole picture. A single grey turns shaded
parts - the snake's scales, the feathers - into solid blocks once they are
scaled down; a local one keeps their lines.

The wings are cut out along an outline measured on docs/logo.jpg and turned
about the shoulder, the beat a sine so it slows at the top and the bottom. On
top of the beat each point of a wing turns a little more, by a wave whose phase
runs across the fan of feathers and out from the shoulder, so neighbouring
feathers are out of step and the tips trail the root. The turn varies from
point to point, so it is applied as a piecewise warp (Pillow's MESH transform).
Where a raised wing uncovers the ring, the ring's own reflection from the bottom
of the drawing fills in.

The snake does not move, its scales do: each stretch of its body slides along
its own centre line toward the tail, so the outline stays and nothing behind it
is uncovered. Its body is told from what lies across it - the tree's bars and
circles, which stay put - by its hatching, whose grey varies far more from dot
to dot. A slide cannot loop by itself, so two slides half a crawl apart are
cross-faded, each at its strongest where the other jumps back ("flow map"
animation: Vlachos, *Water Flow in Portal 2*, SIGGRAPH 2010).

Every frame differs only in the wings and the snake, so the file is compressed
with LZMA, whose window spans all of them.
"""

from __future__ import annotations

import json
import lzma
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "docs" / "logo.jpg"
TARGET = REPOSITORY / "src" / "elsewhere" / "interface" / "tui" / "logo.json.xz"

#: Widths in columns, smallest first; the window shows the largest that fits.
#: Close together, so a terminal of any height is filled: the logo is about
#: half as many rows as columns, and height is what runs out first.
WIDTHS = tuple(range(40, 129, 8))
#: How far around a dot, in dots, its neighbourhood reaches.
RADIUS = 3
#: How much darker than its neighbourhood's mean a dot must be to be ink
#: (0 black, 255 white); lower keeps more of the shading, and more grain.
OFFSET = 6
#: Lighter than this counts as paper when cropping to the drawing.
PAPER = 215
#: Paper kept above the drawing, in pixels of docs/logo.jpg, for raised tips.
HEADROOM = 40

#: Unicode's braille dot numbering: down the left column (1, 2, 3, 7), then
#: down the right (4, 5, 6, 8).
BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))

# Measured on docs/logo.jpg, in its pixels.
#: The left wing's outline; the right wing is its mirror image.
WING = ((165, 160), (230, 170), (300, 178), (355, 178), (440, 183), (452, 215),
        (466, 255), (510, 272), (522, 320), (512, 368), (470, 382), (420, 382),
        (350, 352), (290, 337), (240, 297), (205, 272), (175, 205))
#: x of a point plus x of its mirror image.
MIRROR = 1057
#: Where the left wing turns about.
SHOULDER = (505, 290)
#: From the shoulder to the wing tip.
SPAN = 360.0
#: The top circle of the tree, left where it is though the wings overlap it.
CROWN = (488, 328, 572, 412)
#: The ring's centre, and half-width and half-height of the ellipses bounding
#: it: outside the ring, inside it, and the edge past which is only paper.
CENTER = (530.5, 507.0)
OUTER = (396, 398)
INNER = (348, 352)
EDGE = (392, 394)
#: Grey of the paper, and lighter than this in a wing counts as paper too.
PAPER_GREY = 243
WING_PAPER = 225

#: Frames in one beat.
FRAMES = 24
#: The beat: degrees the tips are raised at rest, and how far either way.
REST = 1.5
SWING = 5.0
#: The flutter: degrees at the tip, waves across the fan of feathers, cycles
#: in one beat, and how far behind the root a tip is, in cycles.
FLUTTER = 1.8
FEATHERS = 3.0
CYCLES = 3
LAG = 0.6
#: Side of a square of the warps, in pixels.
CELL = 4

#: The snake: the centre line of each stretch of its body that shows between
#: what lies across it, head end first.
SNAKE = (
    ((557, 490), (567, 468), (555, 448), (525, 440), (495, 447), (478, 470), (478, 495)),
    ((490, 500), (535, 520), (575, 540), (600, 565)),
    ((600, 565), (605, 595), (595, 622)),
    ((478, 500), (462, 540), (455, 580), (457, 620), (470, 640)),
    ((470, 640), (510, 652), (550, 665), (580, 678)),
    ((595, 622), (560, 643), (520, 660), (485, 680), (468, 700)),
    ((468, 700), (466, 730), (485, 752)),
    ((485, 752), (525, 765), (560, 775)),
    ((580, 678), (592, 705), (585, 735), (565, 755)),
    ((560, 775), (568, 790), (557, 803)),
)
#: Half the width of its body.
BODY = 17
#: Hatching: the standard deviation of grey over a window this far around a
#: point is above SPREAD, and the mean below SHADE.
WINDOW = 5
SPREAD = 22
SHADE = 200
#: Pixels the scales slide in one crawl, and crawls in one beat.
SLIDE = 12
CRAWLS = 2


def braille(image: Image.Image, columns: int) -> list:
    width = columns * 2
    height = round(image.height * width / image.width / 4) * 4
    scaled = ImageOps.autocontrast(image.resize((width, height), Image.LANCZOS), cutoff=1)
    grey, mean = scaled.load(), scaled.filter(ImageFilter.BoxBlur(RADIUS)).load()
    lines = []
    for top in range(0, height, 4):
        characters = []
        for left in range(0, width, 2):
            code = 0
            for down, row in enumerate(BITS):
                for across, bit in enumerate(row):
                    x, y = left + across, top + down
                    if grey[x, y] < mean[x, y] - OFFSET:
                        code |= bit
            # A blank cell is a space: some fonts draw U+2800 with a width of its own.
            characters.append(chr(0x2800 + code) if code else " ")
        lines.append("".join(characters).rstrip())
    return lines


def ellipse(half: tuple) -> tuple:
    return (CENTER[0] - half[0], CENTER[1] - half[1], CENTER[0] + half[0], CENTER[1] + half[1])


def stencil(outline: tuple, size: tuple) -> Image.Image:
    """A mask of one wing: its outline, less the crown."""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(outline, fill=255)
    draw.ellipse(CROWN, fill=0)
    return mask


def backdrop(image: Image.Image, wings: Image.Image) -> Image.Image:
    """The drawing without its wings: paper where they were, and the ring
    where it ran under them, taken from its reflection at the bottom."""
    ring = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(ring)
    draw.ellipse(ellipse(OUTER), fill=255)
    draw.ellipse(ellipse(INNER), fill=0)
    reflection = ImageChops.offset(image.transpose(Image.FLIP_TOP_BOTTOM), 0,
                                   round(2 * CENTER[1] - image.height + 1))
    behind = Image.composite(reflection, Image.new("L", image.size, PAPER_GREY), ring)
    bare = Image.composite(behind, image, wings)
    beyond = Image.new("L", image.size, 255)
    ImageDraw.Draw(beyond).ellipse(ellipse(EDGE), fill=0)
    return Image.composite(Image.new("L", image.size, 255), bare, beyond)


def angle(x: float, y: float, shoulder: tuple, side: int, time: float) -> float:
    """Degrees the tip side of a wing is raised at (x, y), `time` into the beat
    (0 to 1); `side` is 1 for the left wing, -1 for the right."""
    across, down = side * (x - shoulder[0]), y - shoulder[1]
    reach = min(1.0, math.hypot(across, down) / SPAN)
    direction = math.atan2(down, -across)             # 0 along the wing, toward the tip
    beat = REST + SWING * math.sin(2 * math.pi * time)
    phase = 2 * math.pi * (CYCLES * time - FEATHERS * direction / math.pi - LAG * reach)
    return beat + FLUTTER * reach ** 1.5 * math.sin(phase)


def turn(x: float, y: float, shoulder: tuple, degrees: float) -> tuple:
    radians = math.radians(degrees)
    across, down = x - shoulder[0], y - shoulder[1]
    return (shoulder[0] + across * math.cos(radians) - down * math.sin(radians),
            shoulder[1] + across * math.sin(radians) + down * math.cos(radians))


def raised(wing: Image.Image, extent: tuple, shoulder: tuple, side: int,
           time: float) -> Image.Image:
    """The wing, lying within `extent`, turned by `angle` everywhere: each
    square of the result is taken from the quadrilateral turning it back lands on."""
    left, top, right, bottom = extent
    reach = round(SPAN * math.radians(REST + SWING + FLUTTER)) + CELL
    mesh = []
    for y in range(top - reach, bottom + reach, CELL):
        for x in range(left - reach, right + reach, CELL):
            corners = ((x, y), (x, y + CELL), (x + CELL, y + CELL), (x + CELL, y))
            quadrilateral: list = []
            for corner in corners:
                degrees = angle(*corner, shoulder, side, time)
                quadrilateral += turn(*corner, shoulder, -side * degrees)
            mesh.append(((x, y, x + CELL, y + CELL), quadrilateral))
    return wing.transform(wing.size, Image.MESH, mesh, resample=Image.BICUBIC, fillcolor=255)


def track(points: tuple) -> list:
    """Each straight piece of a centre line: where it starts, its direction,
    its length, and how far along the line it starts."""
    pieces, start = [], 0.0
    for (x, y), (next_x, next_y) in zip(points, points[1:]):
        length = math.hypot(next_x - x, next_y - y)
        pieces.append((x, y, (next_x - x) / length, (next_y - y) / length, length, start))
        start += length
    return pieces


def project(x: float, y: float, pieces: list) -> tuple:
    """Distance from (x, y) to the line, how far along it the nearest point
    is, and how far to its side (x, y) lies."""
    nearest = (math.inf, 0.0, 0.0)
    for start_x, start_y, across, down, length, start in pieces:
        along = max(0.0, min(length, (x - start_x) * across + (y - start_y) * down))
        foot_x, foot_y = start_x + across * along, start_y + down * along
        distance = math.hypot(x - foot_x, y - foot_y)
        if distance < nearest[0]:
            side = (y - foot_y) * across - (x - foot_x) * down
            nearest = (distance, start + along, side)
    return nearest


def place(along: float, side: float, pieces: list) -> tuple:
    """The point `along` the line and `side` of it; past either end the line
    runs on straight."""
    for start_x, start_y, across, down, length, start in pieces:
        if along <= start + length:
            break
    distance = along - start
    return (start_x + across * distance - down * side, start_y + down * distance + across * side)


def hatching(image: Image.Image, extent: tuple) -> Image.Image:
    """A mask of the hatched parts of `extent`: a sample standard deviation
    over a box, from the box means of grey and of grey squared."""
    mean = image.filter(ImageFilter.BoxBlur(WINDOW)).load()
    squares = image.point(lambda grey: grey * grey // 255).filter(ImageFilter.BoxBlur(WINDOW)).load()
    mask = Image.new("L", image.size, 0)
    marks = mask.load()
    left, top, right, bottom = extent
    for y in range(top, bottom):
        for x in range(left, right):
            if squares[x, y] * 255 - mean[x, y] ** 2 > SPREAD ** 2 and mean[x, y] < SHADE:
                marks[x, y] = 255
    # Close the gaps between strokes, drop stray marks, then give the edge back.
    return (mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(7))
            .filter(ImageFilter.MaxFilter(5)))


def body(image: Image.Image) -> tuple:
    """Where the snake is, and for each square of the warp over it, the
    stretch it lies on and where along and beside that stretch its corners are."""
    tracks = [track(points) for points in SNAKE]
    band = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(band)
    for points in SNAKE:
        draw.line(points, fill=255, width=2 * BODY)
        for x, y in points:
            draw.ellipse((x - BODY, y - BODY, x + BODY, y + BODY), fill=255)
    left, top, right, bottom = band.getbbox()
    mask = ImageChops.multiply(band, hatching(image, (left, top, right, bottom)))
    squares = []
    for y in range(top, bottom, CELL):
        for x in range(left, right, CELL):
            middle = (x + CELL / 2, y + CELL / 2)
            distance, pieces = min(((project(*middle, pieces)[0], pieces) for pieces in tracks),
                                   key=lambda candidate: candidate[0])
            if distance > BODY + CELL:
                continue
            corners = [project(*corner, pieces)[1:] for corner in
                       ((x, y), (x, y + CELL), (x + CELL, y + CELL), (x + CELL, y))]
            squares.append(((x, y, x + CELL, y + CELL), pieces, corners))
    return mask, squares


def crept(image: Image.Image, squares: list, slide: float) -> Image.Image:
    """The image with every stretch's scales moved `slide` toward the tail."""
    mesh = []
    for box, pieces, corners in squares:
        quadrilateral: list = []
        for along, side in corners:
            quadrilateral += place(along - slide, side, pieces)
        mesh.append((box, quadrilateral))
    return image.transform(image.size, Image.MESH, mesh, resample=Image.BICUBIC, fillcolor=255)


def scales(image: Image.Image, snake: tuple, time: float) -> Image.Image:
    """The image with the snake's scales `time` into the beat."""
    mask, squares = snake
    phase = (CRAWLS * time) % 1.0
    other = (phase + 0.5) % 1.0
    # Each slide is faded out as it nears its jump back to the start.
    crawl = Image.blend(crept(image, squares, phase * SLIDE), crept(image, squares, other * SLIDE),
                        abs(1 - 2 * phase))
    return Image.composite(crawl, image, mask)


def frame(image: Image.Image, background: Image.Image, wings: tuple, snake: tuple,
          time: float) -> Image.Image:
    lighter = image.point(lambda grey: 255 if grey > WING_PAPER else grey)
    white = Image.new("L", image.size, 255)
    picture = Image.composite(scales(image, snake, time), background, snake[0])
    for mask, shoulder, side in wings:
        wing = Image.composite(lighter, white, mask)
        picture = ImageChops.darker(picture, raised(wing, mask.getbbox(), shoulder, side, time))
    return picture


def main() -> None:
    image = Image.open(SOURCE).convert("L")
    left = stencil(WING, image.size)
    right = stencil(tuple((MIRROR - x, y) for x, y in WING), image.size)
    wings = ((left, SHOULDER, 1), (right, (MIRROR - SHOULDER[0], SHOULDER[1]), -1))
    background = backdrop(image, ImageChops.lighter(left, right))
    drawing = ImageOps.invert(image).point(lambda grey: 255 if grey > 255 - PAPER else 0)
    left_edge, top_edge, right_edge, bottom_edge = drawing.getbbox()
    box = (left_edge, top_edge - HEADROOM, right_edge, bottom_edge)
    snake = body(image)
    pictures = [frame(image, background, wings, snake, index / FRAMES).crop(box)
                for index in range(FRAMES)]
    sizes = [[braille(picture, columns) for picture in pictures] for columns in WIDTHS]
    TARGET.write_bytes(lzma.compress(json.dumps(sizes, ensure_ascii=False).encode("utf-8")))
    print(f"wrote {TARGET.relative_to(REPOSITORY)} ({TARGET.stat().st_size // 1024} KB): "
          f"{FRAMES} frames at {', '.join(map(str, WIDTHS))} columns")


if __name__ == "__main__":
    main()
