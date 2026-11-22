#!/usr/bin/env python3
"""Generate resources/app.ico (dark rounded square + cyan play glyph).

Pure standard library: draws pixels, embeds PNG payloads into an .ico.
Run:  python tools/make_icon.py
"""
import struct, zlib, math, os

SIZES = [16, 24, 32, 48, 64, 128, 256]

def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def draw_base(n):
    """RGBA rows for an n x n icon frame (base art at 256, downscaled)."""
    hi = 256
    base = [[(0, 0, 0, 0)] * hi for _ in range(hi)]
    bg1, bg2, accent = (16, 22, 33), (9, 12, 19), (46, 202, 242)
    half = hi / 2
    radius = 58
    aa = 2.0
    for y in range(hi):
        for x in range(hi):
            # rounded-square coverage (corner at pixel (0,0) side)
            cx = min(x + 0.5, hi - x - 0.5)
            cy = min(y + 0.5, hi - y - 0.5)
            if cx <= radius and cy <= radius:
                d = math.hypot(radius - cx, radius - cy)   # dist from corner center
                cov = max(0.0, min(1.0, (radius - d) / aa + 0.5))
            else:
                cov = 1.0
            if cov <= 0:
                continue
            t = (y + 0.5) / hi
            col = lerp(bg1, bg2, t)
            # subtle top sheen
            if y < hi * 0.30:
                col = lerp(col, (30, 44, 66), 0.5 * (1 - y / (hi * 0.30)))
            # accent ring on the right edge
            dx, dy = x + 0.5 - half, y + 0.5 - half
            r = math.hypot(dx, dy)
            if abs(r - hi * 0.36) < 5 and dx > 0:
                col = lerp(col, accent, 0.6)
            # play triangle            
            nx = (x + 0.5 - half) / (hi / 2)
            ny = (y + 0.5 - half) / (hi / 2)
            v = [(-0.50, -0.72), (-0.50, 0.72), (0.92, 0.0)]
            def edge(ax, ay, bx, by, px_, py_):
                return (bx - ax) * (py_ - ay) - (by - ay) * (px_ - ax)
            e0 = edge(*v[0], *v[1], nx, ny)
            e1 = edge(*v[1], *v[2], nx, ny)
            e2 = edge(*v[2], *v[0], nx, ny)
            inside_tri = (e0 >= 0 and e1 >= 0 and e2 >= 0) or (e0 <= 0 and e1 <= 0 and e2 <= 0)
            if inside_tri:
                col = lerp(col, accent, 0.95)
            base[y][x] = (col[0], col[1], col[2], int(255 * cov))

    # box-downscale to n x n
    step = hi / n
    out = []
    for yy in range(n):
        row = []
        for xx in range(n):
            x0, x1 = int(xx * step), max(int((xx + 1) * step), int(xx * step) + 1)
            y0, y1 = int(yy * step), max(int((yy + 1) * step), int(yy * step) + 1)
            r = g = b = a = cnt = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    c = base[y][x]
                    r += c[0]; g += c[1]; b += c[2]; a += c[3]; cnt += 1
            row.append((r // cnt, g // cnt, b // cnt, a // cnt))
        out.append(row)
    return out

def png_rgba(rows):
    n = len(rows)
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frames = []
    for n in SIZES:
        rows = draw_base(n)
        frames.append((n, png_rgba(rows)))
        print(f"  {n}x{n} ok")
    # ICO: 6-byte header, 16-byte directory entries, then PNG payloads
    out = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    for n, png in frames:
        w = n if n < 256 else 0
        out += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    for _, png in frames:
        out += png
    dst = os.path.join(root, "resources", "app.ico")
    with open(dst, "wb") as f:
        f.write(out)
    print(f"wrote {dst} ({len(out)} bytes)")

if __name__ == "__main__":
    main()
