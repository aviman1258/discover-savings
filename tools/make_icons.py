#!/usr/bin/env python3
"""Generate the launcher icons.

Standard library only. Pillow isn't installed and three flat-colour PNGs aren't
worth a dependency, so this builds an RGBA pixel buffer by hand and encodes it
with zlib + struct.

Chrome's WebAPK generation wants raster, not SVG, and the maskable variant is
what stops Android letterboxing the icon inside its adaptive shape.

Run:  python tools/make_icons.py
"""

import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "icons")

# Matches --brand-light / --brand in css/app.css. Update together.
TOP = (249, 160, 33)     # #F9A021
BOTTOM = (229, 92, 32)   # #E55C20
WHITE = (255, 255, 255)

# Edges get supersampled at this factor then box-averaged down, which is what
# keeps the curves from looking like staircases.
SS = 3


def in_round_rect(x, y, w, h, r):
    """Clamp the point into the inner rectangle; inside if within r of it."""
    cx = min(max(x, r), w - r)
    cy = min(max(y, r), h - r)
    dx = x - cx
    dy = y - cy
    return dx * dx + dy * dy <= r * r


def in_disc(x, y, cx, cy, r):
    dx = x - cx
    dy = y - cy
    return dx * dx + dy * dy <= r * r


def in_arc(x, y, size, scale):
    """A swoosh: a band of a circle centred below the mark.

    The circle's topmost point (its apex) sits above the middle of the icon, so
    the band arches -- high in the centre, falling away to each side. Round caps
    come from a disc at each end.

    A smaller radius gives more curve. At radius 0.46 and half-width 0.33 the
    ends drop about 0.14 of the icon height below the apex, which reads as a
    swoosh rather than a straight lid.
    """
    mid = size / 2.0
    apex_y = size * 0.40 * scale + mid * (1 - scale)
    radius = size * 0.46 * scale
    centre_y = apex_y + radius

    half_thickness = size * 0.048 * scale
    half_width = size * 0.33 * scale
    left = mid - half_width
    right = mid + half_width

    dx = x - mid
    dy = y - centre_y
    dist = (dx * dx + dy * dy) ** 0.5

    # y <= centre_y keeps this to the circle's upper half. Without it the lower
    # half draws a second, upside-down arc wherever it falls back on the canvas
    # -- which it does once the mark is scaled down for the maskable variant.
    if left <= x <= right and y <= centre_y and abs(dist - radius) <= half_thickness:
        return True

    # Round caps. Solve the arc's y at each end so the discs sit on the band.
    for end_x in (left, right):
        span = radius * radius - (end_x - mid) ** 2
        if span <= 0:
            continue
        end_y = centre_y - span ** 0.5
        if in_disc(x, y, end_x, end_y, half_thickness):
            return True

    return False


def render(size, maskable):
    """Return `size` rows of RGBA bytes."""
    hi = size * SS

    # Maskable icons are cropped by the OS, so the background fills the whole
    # canvas and the mark is pulled into the safe zone.
    radius = 0.0 if maskable else hi * 0.22
    mark_scale = 0.66 if maskable else 1.0

    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            r_sum = g_sum = b_sum = a_sum = 0

            for sy in range(SS):
                hy = y * SS + sy
                # Vertical gradient, top colour to bottom colour.
                t = hy / float(hi - 1)
                base_r = int(round(TOP[0] + (BOTTOM[0] - TOP[0]) * t))
                base_g = int(round(TOP[1] + (BOTTOM[1] - TOP[1]) * t))
                base_b = int(round(TOP[2] + (BOTTOM[2] - TOP[2]) * t))

                for sx in range(SS):
                    hx = x * SS + sx

                    if radius > 0 and not in_round_rect(hx, hy, hi, hi, radius):
                        continue  # transparent outside the rounded square

                    if in_arc(hx, hy, hi, mark_scale):
                        r_sum += WHITE[0]
                        g_sum += WHITE[1]
                        b_sum += WHITE[2]
                    else:
                        r_sum += base_r
                        g_sum += base_g
                        b_sum += base_b
                    a_sum += 255

            samples = SS * SS
            if a_sum == 0:
                row += b"\x00\x00\x00\x00"
                continue

            # Colours are averaged over covered samples only, so edge pixels
            # don't darken toward black as coverage drops.
            covered = a_sum // 255
            row += bytes((
                r_sum // covered,
                g_sum // covered,
                b_sum // covered,
                a_sum // samples,
            ))

        rows.append(bytes(row))

    return rows


def write_png(path, size, rows):
    def chunk(tag, payload):
        body = tag + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    # Filter byte 0 (None) in front of every scanline.
    raw = b"".join(b"\x00" + row for row in rows)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", header)
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))

    with open(path, "wb") as handle:
        handle.write(png)

    return len(png)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    targets = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
    ]

    for name, size, maskable in targets:
        path = os.path.join(OUT_DIR, name)
        written = write_png(path, size, render(size, maskable))
        print("  %-24s %4dx%-4d %6d bytes%s"
              % (name, size, size, written, "  (maskable)" if maskable else ""))

    print("\nwrote %d icons to %s" % (len(targets), OUT_DIR))


if __name__ == "__main__":
    sys.exit(main())
