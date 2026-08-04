#!/usr/bin/env python3
"""Build the app's images from the source logos in dist/.

Standard library only -- Pillow isn't installed and this is the whole reason
there's a PNG codec in here. An .png is length-prefixed chunks wrapping a zlib
stream, so zlib + struct covers both directions.

Inputs (put them in dist/):
    Discover-logo-main.png   the wordmark, black text with the orange sphere
    Discover-logo-app.png    the rounded-square app icon, white text on navy

Outputs:
    img/wordmark.png              wordmark recoloured white, margins trimmed
    icons/icon-192.png            launcher icon
    icons/icon-512.png            large icon, used for splash screens
    icons/icon-maskable-512.png   full-bleed navy so Android can crop it

Run:  python tools/build_assets.py
"""

import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
DIST = os.path.join(PROJECT, "dist")
ICONS = os.path.join(PROJECT, "icons")
IMG = os.path.join(PROJECT, "img")

SRC_WORDMARK = os.path.join(DIST, "Discover-logo-main.png")
SRC_ICON = os.path.join(DIST, "Discover-logo-app.png")

# Any pixel whose brightest channel is below this is treated as part of the
# black wordmark. The orange sphere sits around R=230, so there's a wide gap
# and nothing to tune.
TEXT_MAX_CHANNEL = 120


# --- PNG decode -------------------------------------------------------------

def unfilter(raw, width, height, bpp):
    """Undo the per-scanline filters. Returns a bytearray of raw RGBA."""
    stride = width * bpp
    out = bytearray(height * stride)
    pos = 0

    for y in range(height):
        filter_type = raw[pos]
        pos += 1
        line = raw[pos:pos + stride]
        pos += stride

        base = y * stride
        prior = base - stride

        if filter_type == 0:
            out[base:base + stride] = line

        elif filter_type == 1:  # Sub
            for i in range(stride):
                left = out[base + i - bpp] if i >= bpp else 0
                out[base + i] = (line[i] + left) & 0xFF

        elif filter_type == 2:  # Up
            for i in range(stride):
                above = out[prior + i] if y else 0
                out[base + i] = (line[i] + above) & 0xFF

        elif filter_type == 3:  # Average
            for i in range(stride):
                left = out[base + i - bpp] if i >= bpp else 0
                above = out[prior + i] if y else 0
                out[base + i] = (line[i] + ((left + above) >> 1)) & 0xFF

        elif filter_type == 4:  # Paeth
            for i in range(stride):
                left = out[base + i - bpp] if i >= bpp else 0
                above = out[prior + i] if y else 0
                upper_left = out[prior + i - bpp] if (y and i >= bpp) else 0
                p = left + above - upper_left
                pa, pb, pc = abs(p - left), abs(p - above), abs(p - upper_left)
                if pa <= pb and pa <= pc:
                    pred = left
                elif pb <= pc:
                    pred = above
                else:
                    pred = upper_left
                out[base + i] = (line[i] + pred) & 0xFF

        else:
            raise ValueError("unsupported PNG filter type %d" % filter_type)

    return out


def read_png(path):
    """Return (width, height, pixels) where pixels is a flat RGBA bytearray."""
    with open(path, "rb") as handle:
        data = handle.read()

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s is not a PNG" % path)

    pos = 8
    width = height = None
    idat = bytearray()

    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length  # 4 length + 4 tag + body + 4 crc

        if tag == b"IHDR":
            width, height, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or colour != 6:
                raise ValueError("%s must be 8-bit RGBA (got depth %d, colour type %d)"
                                 % (path, depth, colour))
            if interlace:
                raise ValueError("%s is interlaced, which isn't supported" % path)
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break

    return width, height, unfilter(zlib.decompress(bytes(idat)), width, height, 4)


# --- PNG encode -------------------------------------------------------------

def write_png(path, width, height, pixels):
    def chunk(tag, payload):
        body = tag + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: None
        raw += pixels[y * stride:(y + 1) * stride]

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(png)
    return len(png)


# --- pixel helpers ----------------------------------------------------------

def get(pixels, width, x, y):
    i = (y * width + x) * 4
    return pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3]


def resize(src, sw, sh, dw, dh):
    """Area-average when shrinking, bilinear when growing.

    Alpha is premultiplied before interpolation and divided back out after.
    Skipping that step pulls transparent black into the edges of anything
    anti-aliased, which shows up as a dark halo.
    """
    out = bytearray(dw * dh * 4)
    x_ratio = sw / float(dw)
    y_ratio = sh / float(dh)
    shrinking = x_ratio > 1.0 or y_ratio > 1.0

    for dy in range(dh):
        for dx in range(dw):
            if shrinking:
                x0 = int(dx * x_ratio)
                x1 = max(x0 + 1, int((dx + 1) * x_ratio))
                y0 = int(dy * y_ratio)
                y1 = max(y0 + 1, int((dy + 1) * y_ratio))
                r = g = b = a = 0.0
                n = 0
                for sy in range(y0, min(y1, sh)):
                    for sx in range(x0, min(x1, sw)):
                        pr, pg, pb, pa = get(src, sw, sx, sy)
                        w = pa / 255.0
                        r += pr * w
                        g += pg * w
                        b += pb * w
                        a += pa
                        n += 1
                if n == 0:
                    continue
                a /= n
                if a > 0:
                    scale = n * (a / 255.0)
                    r, g, b = r / scale, g / scale, b / scale
                else:
                    r = g = b = 0.0
            else:
                fx = min(max((dx + 0.5) * x_ratio - 0.5, 0.0), sw - 1.0)
                fy = min(max((dy + 0.5) * y_ratio - 0.5, 0.0), sh - 1.0)
                x0, y0 = int(fx), int(fy)
                x1, y1 = min(x0 + 1, sw - 1), min(y0 + 1, sh - 1)
                tx, ty = fx - x0, fy - y0

                r = g = b = a = 0.0
                for (sx, sy, weight) in ((x0, y0, (1 - tx) * (1 - ty)),
                                         (x1, y0, tx * (1 - ty)),
                                         (x0, y1, (1 - tx) * ty),
                                         (x1, y1, tx * ty)):
                    pr, pg, pb, pa = get(src, sw, sx, sy)
                    m = weight * (pa / 255.0)
                    r += pr * m
                    g += pg * m
                    b += pb * m
                    a += pa * weight
                if a > 0:
                    scale = a / 255.0
                    r, g, b = r / scale, g / scale, b / scale
                else:
                    r = g = b = 0.0

            i = (dy * dw + dx) * 4
            out[i] = min(255, max(0, int(round(r))))
            out[i + 1] = min(255, max(0, int(round(g))))
            out[i + 2] = min(255, max(0, int(round(b))))
            out[i + 3] = min(255, max(0, int(round(a))))

    return out


def flood_corners(pixels, width, height, replacement):
    """Replace the light background outside the icon's rounded corners.

    The source icon is a rounded square on an opaque WHITE field, not a
    transparent one, so the corners otherwise show up as white wedges.

    Flood filling inward from each corner rather than replacing white globally
    is what keeps the white DISCOVER wordmark intact -- it's in the interior and
    never connected to a corner. The threshold is deliberately loose (any
    channel-minimum at or above 150) so the anti-aliased ring along each corner
    arc gets swallowed too; the navy is (35,35,66) and the orange arc bottoms out
    around 40, so neither comes close.
    """
    seen = bytearray(width * height)
    stack = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    filled = 0

    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        flat = y * width + x
        if seen[flat]:
            continue
        seen[flat] = 1

        i = flat * 4
        r, g, b, a = pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3]
        if a != 0 and min(r, g, b) < 150:
            continue  # hit the icon itself

        pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3] = replacement
        filled += 1

        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))

    return filled


def trim(pixels, width, height):
    """Crop away fully transparent margins so CSS sizing is predictable."""
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if pixels[(y * width + x) * 4 + 3] > 2:
                if x < left: left = x
                if x > right: right = x
                if y < top: top = y
                if y > bottom: bottom = y

    if right < 0:
        return pixels, width, height

    nw, nh = right - left + 1, bottom - top + 1
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        src = ((y + top) * width + left) * 4
        out[y * nw * 4:(y + 1) * nw * 4] = pixels[src:src + nw * 4]
    return out, nw, nh


# --- builders ---------------------------------------------------------------

def build_wordmark(text_colour, filename):
    """Cut the wordmark out of its white background and set the text colour.

    The source is 100% opaque -- black text and an orange sphere on a solid white
    rectangle, no alpha anywhere. Flood filling from the corners (the trick the
    icon needs) is wrong here: the counters inside D, O, S and R are enclosed
    white regions that a fill can never reach, so they'd stay as white blobs.

    Instead, judge each pixel by saturation. The artwork is black text plus an
    orange sphere, so anything near-grey has to be text-over-white and its
    darkness IS its coverage -- a mid-grey pixel is a half-covered edge. That
    recovers proper anti-aliasing rather than a hard 1-bit cutout. Saturated
    pixels are the sphere and pass through untouched.
    """
    width, height, pixels = read_png(SRC_WORDMARK)

    GREY_TOLERANCE = 26

    cut = 0
    for i in range(0, len(pixels), 4):
        r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]
        if max(r, g, b) - min(r, g, b) < GREY_TOLERANCE:
            # Grey: coverage is how far it is from white.
            alpha = 255 - min(r, g, b)
            pixels[i] = text_colour[0]
            pixels[i + 1] = text_colour[1]
            pixels[i + 2] = text_colour[2]
            pixels[i + 3] = alpha
            if alpha < 250:
                cut += 1
        else:
            pixels[i + 3] = 255  # the sphere

    pixels, width, height = trim(pixels, width, height)

    out = os.path.join(IMG, filename)
    size = write_png(out, width, height, pixels)
    print("  img/%-26s %dx%-4d %6d bytes  (text #%02X%02X%02X, %d px made transparent)"
          % (filename, width, height, size,
             text_colour[0], text_colour[1], text_colour[2], cut))
    return width, height


def sample_navy(pixels, width, height):
    """The icon's background colour, taken from just inside the top edge."""
    y = max(2, height // 14)
    r, g, b, a = get(pixels, width, width // 2, y)
    if a < 250:
        r, g, b, a = get(pixels, width, width // 2, height // 2)
    return (r, g, b)


def build_icons():
    width, height, pixels = read_png(SRC_ICON)

    # Square it off by centre-cropping, so nothing ends up stretched.
    side = min(width, height)
    ox, oy = (width - side) // 2, (height - side) // 2
    square = bytearray(side * side * 4)
    for y in range(side):
        src = ((y + oy) * width + ox) * 4
        square[y * side * 4:(y + 1) * side * 4] = pixels[src:src + side * 4]

    navy = sample_navy(square, side, side)
    print("  background sampled from the icon: #%02X%02X%02X" % navy)

    # For the "any" icons the area outside the rounded corners should be
    # transparent, so the rounded shape reads correctly on any wallpaper.
    clear = bytearray(square)
    cleared = flood_corners(clear, side, side, (0, 0, 0, 0))
    print("  corners cleared to transparent: %d px" % cleared)

    for name, target in (("icon-192.png", 192), ("icon-512.png", 512)):
        scaled = resize(clear, side, side, target, target)
        size = write_png(os.path.join(ICONS, name), target, target, scaled)
        note = "upscaled from %d" % side if target > side else "downscaled from %d" % side
        print("  icons/%-24s %dx%-4d %6d bytes  (%s)" % (name, target, target, size, note))

    # Maskable: Android crops this to whatever shape the launcher uses, so the
    # background has to run right to the edges. Filling the corners with the
    # same navy makes the source's rounded corners disappear, giving a full-bleed
    # square. The slight inset keeps the orange arc clear of the crop -- the safe
    # zone is only the middle 80%.
    canvas_size = 512
    inner = 460

    solid = bytearray(square)
    flood_corners(solid, side, side, (navy[0], navy[1], navy[2], 255))

    canvas = bytearray(canvas_size * canvas_size * 4)
    for i in range(0, len(canvas), 4):
        canvas[i], canvas[i + 1], canvas[i + 2], canvas[i + 3] = navy[0], navy[1], navy[2], 255

    art = resize(solid, side, side, inner, inner)
    offset = (canvas_size - inner) // 2
    for y in range(inner):
        for x in range(inner):
            si = (y * inner + x) * 4
            alpha = art[si + 3]
            if alpha == 0:
                continue
            di = ((y + offset) * canvas_size + (x + offset)) * 4
            if alpha == 255:
                canvas[di:di + 3] = art[si:si + 3]
            else:
                t = alpha / 255.0
                for c in range(3):
                    canvas[di + c] = int(round(art[si + c] * t + canvas[di + c] * (1 - t)))

    size = write_png(os.path.join(ICONS, "icon-maskable-512.png"),
                     canvas_size, canvas_size, canvas)
    print("  icons/%-24s %dx%-4d %6d bytes  (full bleed, art at %d)"
          % ("icon-maskable-512.png", canvas_size, canvas_size, size, inner))

    return navy


def main():
    for path in (SRC_WORDMARK, SRC_ICON):
        if not os.path.exists(path):
            sys.exit("missing source image: %s" % path)

    print("building from dist/\n")
    # Black for light and orange backgrounds, white knockout for navy. Both are
    # needed: black on navy is unreadable, white on orange is worse.
    build_wordmark((0, 0, 0), "wordmark.png")
    build_wordmark((255, 255, 255), "wordmark-white.png")
    print("")
    navy = build_icons()
    print("\nset background_color in manifest.webmanifest to #%02X%02X%02X" % navy)
    print("remember: bump CACHE_VERSION in sw.js")


if __name__ == "__main__":
    main()
