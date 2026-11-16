#!/usr/bin/env python3
"""IGNITION -- a procedural night-breach renderer.

A colossal whale breaches out of a deep-indigo ocean under a star
field.  The breach point blazes white-gold and throws a radial fan of
sparks, spray and crown droplets; a broken golden reflection shimmers
on the water, and far below-right a tiny lantern boat gives the scale
contrast.

Pure Python standard library: the scene is rasterised with bezier
spines, supersampled polygon fills and additive glow stamps, then
encoded as a PNG with zlib.  Deterministic -- every random choice
comes from explicitly seeded generators, so two runs produce
byte-identical output.
"""

import binascii
import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
HORIZON = 648
BURST = (428.0, 650.0)

fb = bytearray(W * H * 3)  # RGB framebuffer


# ---------------------------------------------------------------- pixels

def add_px(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        fb[i] = min(255, fb[i] + r)
        fb[i + 1] = min(255, fb[i + 1] + g)
        fb[i + 2] = min(255, fb[i + 2] + b)


def stamp(cx, cy, radius, rgb, alpha, mode="add"):
    """Soft round stamp: quadratic falloff, additive or alpha blend."""
    x0 = max(0, int(cx - radius))
    x1 = min(W - 1, int(cx + radius))
    y0 = max(0, int(cy - radius))
    y1 = min(H - 1, int(cy + radius))
    r2 = radius * radius
    for yy in range(y0, y1 + 1):
        dy = yy - cy
        for xx in range(x0, x1 + 1):
            dx = xx - cx
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue
            f = 1.0 - math.sqrt(d2) / radius
            a = alpha * f * f
            if a <= 0.003:
                continue
            i = (yy * W + xx) * 3
            if mode == "add":
                fb[i] = min(255, fb[i] + int(rgb[0] * a))
                fb[i + 1] = min(255, fb[i + 1] + int(rgb[1] * a))
                fb[i + 2] = min(255, fb[i + 2] + int(rgb[2] * a))
            else:
                ia = 1.0 - a
                fb[i] = int(fb[i] * ia + rgb[0] * a)
                fb[i + 1] = int(fb[i + 1] * ia + rgb[1] * a)
                fb[i + 2] = int(fb[i + 2] * ia + rgb[2] * a)


def hard_dot(cx, cy, radius, rgb):
    """Solid disc (silhouettes)."""
    x0 = max(0, int(cx - radius))
    x1 = min(W - 1, int(cx + radius))
    y0 = max(0, int(cy - radius))
    y1 = min(H - 1, int(cy + radius))
    r2 = radius * radius
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            if (xx - cx) ** 2 + (yy - cy) ** 2 <= r2:
                i = (yy * W + xx) * 3
                fb[i], fb[i + 1], fb[i + 2] = rgb


def line(x0, y0, x1, y1, rgb, alpha, width=2.0, mode="add", taper=0.0):
    steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for s in range(steps + 1):
        t = s / steps
        a = alpha * (1.0 - taper * t)
        stamp(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, width, rgb, a, mode)


# ------------------------------------------------------- polygon filling

def poly_alpha(points, ss=2):
    """Antialiased polygon mask via supersampled scanline fill.

    Returns (x0, y0, w, h, alpha bytearray) for the polygon's bbox.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0 = max(0, int(math.floor(min(xs))) - 1)
    x1 = min(W, int(math.ceil(max(xs))) + 1)
    y0 = max(0, int(math.floor(min(ys))) - 1)
    y1 = min(H, int(math.ceil(max(ys))) + 1)
    w, h = x1 - x0, y1 - y0
    hw, hh = w * ss, h * ss
    mask = bytearray(hw * hh)
    n = len(points)
    edges = [(points[i], points[(i + 1) % n]) for i in range(n)]
    for row in range(hh):
        yc = y0 + (row + 0.5) / ss
        nodes = []
        for (ax, ay), (bx, by) in edges:
            if (ay <= yc < by) or (by <= yc < ay):
                nodes.append(ax + (yc - ay) * (bx - ax) / (by - ay))
        nodes.sort()
        base = row * hw
        for k in range(0, len(nodes) - 1, 2):
            xa = max(0, int(math.ceil((nodes[k] - x0) * ss - 0.5)))
            xb = min(hw - 1, int(math.floor((nodes[k + 1] - x0) * ss - 0.5)))
            for xx in range(xa, xb + 1):
                mask[base + xx] = 255
    alpha = bytearray(w * h)
    for yy in range(h):
        for xx in range(w):
            s = 0
            for dy in range(ss):
                base = (yy * ss + dy) * hw + xx * ss
                for dx in range(ss):
                    s += mask[base + dx]
            alpha[yy * w + xx] = s // (ss * ss)
    return x0, y0, w, h, alpha


def composite(x0, y0, w, h, alpha, shade):
    """Blend a shaded polygon into the framebuffer.  shade(x, y) -> rgb."""
    bx, by = BURST
    for yy in range(h):
        Y = y0 + yy
        row = yy * w
        for xx in range(w):
            a = alpha[row + xx]
            if a == 0:
                continue
            X = x0 + xx
            r, g, b = shade(X, Y, bx, by)
            i = (Y * W + X) * 3
            ia = 255 - a
            fb[i] = (r * a + fb[i] * ia) // 255
            fb[i + 1] = (g * a + fb[i + 1] * ia) // 255
            fb[i + 2] = (b * a + fb[i + 2] * ia) // 255


# ------------------------------------------------------------ background

def paint_background():
    for y in range(H):
        if y < HORIZON:
            t = y / HORIZON
            col = (int(7 + 9 * t), int(10 + 40 * t * t), int(30 + 38 * t))
        else:
            t = (y - HORIZON) / (H - HORIZON)
            band = 1.0 + 0.035 * math.sin(y * 0.32)
            col = (int((9 - 5 * t) * band), int((32 - 20 * t) * band),
                   int((46 - 22 * t) * band))
        row = bytes(col) * W
        fb[y * W * 3:(y + 1) * W * 3] = row
    # faint bright horizon line
    for x in range(W):
        add_px(x, HORIZON, 14, 20, 18)


def paint_stars():
    rng = random.Random(42)
    for _ in range(360):
        x = rng.uniform(0, W)
        y = (rng.random() ** 1.25) * (HORIZON - 14)
        b = rng.random() ** 2
        a = (0.22 + 0.78 * b) * (1.0 - 0.45 * y / HORIZON)
        tint = rng.random()
        col = (int(200 + 55 * tint), int(215 + 30 * tint), 255)
        stamp(x, y, 1.0 + 1.5 * b, col, a)
        if b > 0.86:  # a few sparkle crosses
            L = 5 + 5 * b
            line(x - L, y, x + L, y, col, 0.28 * a, 1.0)
            line(x, y - L, x, y + L, col, 0.28 * a, 1.0)


def paint_reflection():
    bx, by = BURST
    for y in range(HORIZON + 6, 1006):
        depth = (y - HORIZON) / (H - HORIZON)
        rng = random.Random(1000 + y)
        halfw = 150 * (1.0 - 0.72 * depth)
        base_a = 0.42 * (1.0 - depth) ** 1.5
        if base_a <= 0.01:
            continue
        for _ in range(4):
            sx = bx + rng.gauss(0, halfw * 0.48)
            ln = rng.uniform(10, 70) * (1.0 - 0.5 * depth)
            a = base_a * rng.uniform(0.35, 1.0)
            for xx in range(int(sx - ln / 2), int(sx + ln / 2)):
                add_px(xx, y, int(255 * a), int(178 * a), int(76 * a))
    rng = random.Random(7)
    for _ in range(220):  # sparkle dust on the column
        x = bx + rng.gauss(0, 62)
        y = HORIZON + 8 + rng.random() ** 1.6 * 300
        stamp(x, y, 1.4, (255, 205, 110), rng.uniform(0.15, 0.5))


# ----------------------------------------------------------------- whale

P0, P1, P2, P3 = (428.0, 652.0), (390.0, 428.0), (438.0, 208.0), (522.0, 84.0)

HW_CTRL = [  # (t, back halfwidth, belly halfwidth)
    (0.00, 13, 13), (0.12, 26, 23), (0.28, 50, 42), (0.45, 73, 57),
    (0.60, 85, 64), (0.72, 90, 66), (0.82, 85, 62), (0.90, 66, 44),
    (0.96, 46, 24), (1.00, 21, 10),
]


def spine(t):
    u = 1.0 - t
    x = u ** 3 * P0[0] + 3 * u * u * t * P1[0] + 3 * u * t * t * P2[0] + t ** 3 * P3[0]
    y = u ** 3 * P0[1] + 3 * u * u * t * P1[1] + 3 * u * t * t * P2[1] + t ** 3 * P3[1]
    return x, y


def tangent(t):
    u = 1.0 - t
    dx = (3 * u * u * (P1[0] - P0[0]) + 6 * u * t * (P2[0] - P1[0])
          + 3 * t * t * (P3[0] - P2[0]))
    dy = (3 * u * u * (P1[1] - P0[1]) + 6 * u * t * (P2[1] - P1[1])
          + 3 * t * t * (P3[1] - P2[1]))
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def halfwidths(t):
    for i in range(len(HW_CTRL) - 1):
        t0, b0, f0 = HW_CTRL[i]
        t1, b1, f1 = HW_CTRL[i + 1]
        if t0 <= t <= t1:
            s = (t - t0) / (t1 - t0)
            s = s * s * (3 - 2 * s)
            return b0 + (b1 - b0) * s, f0 + (f1 - f0) * s
    return HW_CTRL[-1][1], HW_CTRL[-1][2]


def outline():
    """(back points, belly points), each sampled tail -> head."""
    back, belly = [], []
    N = 64
    for i in range(N + 1):
        t = i / N
        x, y = spine(t)
        tx, ty = tangent(t)
        hb, hf = halfwidths(t)
        back.append((x + ty * hb, y - tx * hb))    # normal (-ty? ) back side
        belly.append((x - ty * hf, y + tx * hf))   # belly side
    return back, belly


def side_point(t, side, out=0.0):
    x, y = spine(t)
    tx, ty = tangent(t)
    hb, hf = halfwidths(t)
    if side == "back":
        return x + ty * (hb + out), y - tx * (hb + out)
    return x - ty * (hf + out), y + tx * (hf + out)


def whale_polygon():
    back, belly = outline()
    # rostrum cap: a flattened top running forward from the back tip, a
    # blunt front face, then a gentle jaw curve down to the belly tip --
    # three quadratic segments instead of one round dome.
    cx, cy = spine(1.0)
    tx, ty = tangent(1.0)
    a, b = back[-1], belly[-1]
    nb = (ty, -tx)   # back-side outward normal
    nf = (-ty, tx)   # belly-side outward normal
    r1 = (a[0] + tx * 12 + nb[0] * 1.5, a[1] + ty * 12 + nb[1] * 1.5)
    r2 = (cx + tx * 23 + nb[0] * 6, cy + ty * 23 + nb[1] * 6)
    r3 = (cx + tx * 25 + nf[0] * 7, cy + ty * 25 + nf[1] * 7)
    r4 = (cx + tx * 16 + nf[0] * 13, cy + ty * 16 + nf[1] * 13)
    jaw_c = ((r4[0] + b[0]) / 2 + nf[0] * 2, (r4[1] + b[1]) / 2 + nf[1] * 2)
    cap = []
    for p, c, q in ((a, r1, r2), (r2, r3, r4), (r4, jaw_c, b)):
        for k in range(1, 5):
            s = k / 4
            u = 1 - s
            cap.append((u * u * p[0] + 2 * u * s * c[0] + s * s * q[0],
                        u * u * p[1] + 2 * u * s * c[1] + s * s * q[1]))
    return back + cap + belly[::-1]


def body_shade(X, Y, bx, by):
    d = math.hypot(X - bx, Y - by)
    glow = 1.0 / (1.0 + (d / 230.0) ** 2)
    g2 = glow * glow
    r = 31 + 24 * glow + 150 * g2
    g = 43 + 28 * glow + 88 * g2
    b = 71 + 26 * glow + 18 * g2
    return min(255, int(r)), min(255, int(g)), min(255, int(b))


def dark_shade(base):
    def shade(X, Y, bx, by):
        d = math.hypot(X - bx, Y - by)
        glow = 1.0 / (1.0 + (d / 210.0) ** 2)
        return (min(255, int(base[0] + 120 * glow * glow)),
                min(255, int(base[1] + 70 * glow * glow)),
                min(255, int(base[2] + 14 * glow * glow)))
    return shade


def paint_whale():
    back, belly = outline()
    # outer glow along the lower outline, behind the body
    for pts in (back, belly):
        for i, (x, y) in enumerate(pts):
            heat = max(0.0, min(1.0, (y - 150) / 500.0))
            if heat > 0.03:
                stamp(x, y, 13, (255, 166, 64), 0.10 * heat)
    # tail fluke at the waterline, behind the stalk: two curved lobes
    # with a centre notch, tips slightly upturned, sunk into the foam
    fluke = [(428, 632), (400, 623), (368, 612), (342, 603), (320, 597),
             (327, 611), (357, 623), (391, 637), (417, 647), (428, 655),
             (439, 647), (465, 637), (499, 623), (529, 611), (536, 597),
             (514, 603), (488, 612), (456, 623)]
    def fluke_shade(X, Y, bx, by):
        # like dark_shade but with the burst-glow term damped, so the
        # fluke stays slate-dark even where it sits inside the glare
        d = math.hypot(X - bx, Y - by)
        glow = 1.0 / (1.0 + (d / 210.0) ** 2)
        g2 = glow * glow * 0.35
        return (min(255, int(13 + 120 * g2)),
                min(255, int(19 + 70 * g2)),
                min(255, int(36 + 14 * g2)))

    composite(*poly_alpha(fluke), fluke_shade)
    # gold rim along the leading edges only (notch out to each tip)
    for pts in (((428, 632), (400, 623), (368, 612), (342, 603), (320, 597)),
                ((428, 632), (456, 623), (488, 612), (514, 603), (536, 597))):
        for i in range(len(pts) - 1):
            line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1],
                 (255, 196, 96), 0.6, 2.2)
    # body
    composite(*poly_alpha(whale_polygon()), body_shade)
    # pectoral flipper: a filled tapered paddle on the shoulder just
    # behind the head -- wide base on the belly edge, pointed tip swept
    # down-back, darker than the belly, thin gold leading edge only.
    f1 = side_point(0.875, "belly", out=-3)
    f2 = side_point(0.78, "belly", out=26)
    ftip = side_point(0.655, "belly", out=48)
    f3 = side_point(0.70, "belly", out=16)
    f4 = side_point(0.745, "belly", out=-3)
    composite(*poly_alpha([f1, f2, ftip, f3, f4]), dark_shade((12, 17, 34)))
    line(f1[0], f1[1], f2[0], f2[1], (255, 190, 88), 0.8, 2.2)
    line(f2[0], f2[1], ftip[0], ftip[1], (255, 190, 88), 0.8, 2.2)
    # jaw line: a gentle curve just inside the belly outline of the head
    jaw = [side_point(0.865 + 0.0125 * k, "belly", out=-6) for k in range(9)]
    for i in range(len(jaw) - 1):
        line(jaw[i][0], jaw[i][1], jaw[i + 1][0], jaw[i + 1][1],
             (5, 7, 15), 0.65, 2.4, mode="blend")
    # eye
    ex, ey = side_point(0.90, "belly", out=-halfwidths(0.90)[1] * 0.55)
    stamp(ex, ey, 9, (255, 200, 100), 0.35)
    stamp(ex, ey, 2.6, (255, 226, 160), 0.95)
    # rim light: gold on the burst-facing outline, cool starlight up top.
    # Drawn as continuous segments (discrete stamps bead along the edge).
    def rim_color(y, side):
        heat = max(0.05, min(1.0, (y - 120) / 540.0))
        if side == "belly":
            heat = min(1.0, heat * 1.12)
        warm = (255, int(150 + 76 * heat), int(60 + 110 * heat))
        if side == "back":
            return tuple(int(warm[c] * heat + (150, 180, 255)[c] * (1 - heat))
                         for c in range(3)), heat
        return warm, heat

    for pts, side in ((back, "back"), (belly, "belly")):
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            col, heat = rim_color((y0 + y1) / 2, side)
            line(x0, y0, x1, y1, col, 0.30 + 0.60 * heat, 2.8)
            if y0 > 430:
                line(x0, y0, x1, y1, (255, 240, 205), 0.5 * heat, 1.3)


def paint_sheeting():
    rng = random.Random(1234)
    back, belly = outline()
    N = len(back)
    for pts in (back, belly):
        for i in range(2, int(N * 0.30)):
            x, y = pts[i]
            for _ in range(3):
                ln = rng.uniform(12, 34)
                dx = rng.uniform(-3, 3)
                line(x + rng.uniform(-3, 3), y, x + dx, y + ln,
                     (185, 208, 238), 0.32, 1.8, taper=0.7)
    # droplets raining off the belly
    for i in range(int(N * 0.10), int(N * 0.45)):
        x, y = belly[i]
        for _ in range(2):
            fall = rng.uniform(24, 95)
            sx = x + rng.uniform(-2, 4)
            steps = int(fall / 6)
            for s in range(steps):
                stamp(sx + s * 0.4, y + s * 6, 1.3, (200, 220, 245),
                      0.34 * (1 - s / max(1, steps)))


# ------------------------------------------------------------------ burst

def paint_burst():
    bx, by = BURST
    # atmospheric halo in the sky
    stamp(bx, by, 430, (255, 170, 80), 0.055)
    # spray arcs off the fluke tips
    rng = random.Random(555)
    for cx, sgn in ((330, -1), (526, 1)):
        for _ in range(26):
            vx = sgn * rng.uniform(6, 60)
            vy = rng.uniform(38, 95)
            for s in range(14):
                u = s / 14
                stamp(cx + vx * u, by - 8 - vy * u + 120 * u * u,
                      1.5, (215, 230, 250), 0.5 * (1 - u))
    # radial spark fan
    rng = random.Random(7)
    for _ in range(240):
        th = math.radians(90 + (rng.random() * 2 - 1) * 72)
        L = (30 + 230 * rng.random() ** 1.6) * (0.5 + 0.5 * math.sin(th))
        ex = bx + math.cos(th) * L
        ey = by - math.sin(th) * L
        col = (255, int(196 + 40 * rng.random()), int(96 + 60 * rng.random()))
        line(bx + math.cos(th) * 8, by - math.sin(th) * 8, ex, ey,
             col, 0.5, 1.9, taper=0.85)
    # ballistic droplets
    rng = random.Random(21)
    for _ in range(650):
        th = math.radians(90 + (rng.random() * 2 - 1) * 80)
        sp = rng.uniform(60, 300)
        vx, vy = math.cos(th) * sp, math.sin(th) * sp
        steps = rng.randint(6, 16)
        for s in range(steps):
            u = s / steps * rng.uniform(0.75, 1.0)
            x = bx + vx * u
            y = by - vy * u + 250 * u * u
            stamp(x, y, 1.3, (255, 224, 160), 0.75 * (1 - u * 0.7))
    # crown droplets above the waterline
    rng = random.Random(33)
    for _ in range(110):
        th = math.radians(rng.uniform(15, 165))
        r = rng.uniform(64, 155)
        stamp(bx + math.cos(th) * r, by - math.sin(th) * r * 0.62,
              rng.uniform(1.4, 3.0), (220, 236, 255), rng.uniform(0.35, 0.75))
    # foam ring at the waterline
    rng = random.Random(44)
    for _ in range(280):
        x = bx + rng.gauss(0, 74)
        y = by + rng.gauss(0, 9)
        near = max(0.0, 1.0 - abs(x - bx) / 170)
        col = (int(200 + 55 * near), int(215 + 30 * near), int(235 + 20 * near))
        stamp(x, y, rng.uniform(1.2, 3.2), col, rng.uniform(0.25, 0.6))
    # blazing core
    x0, y0 = int(bx - 130), int(by - 130)
    for yy in range(y0, int(by + 130)):
        for xx in range(x0, int(bx + 130)):
            d = math.hypot(xx - bx, yy - by)
            i = math.exp(-((d / 95.0) ** 2) * 2.1)
            if i <= 0.004:
                continue
            add_px(xx, yy, int(255 * i), int(214 * i), int(130 * i))
            w = i ** 3
            add_px(xx, yy, int(255 * w), int(246 * w), int(220 * w))


# ------------------------------------------------------------------- boat

def paint_boat():
    hull = [(742, 800), (838, 800), (822, 826), (758, 826)]
    composite(*poly_alpha(hull), lambda X, Y, bx, by: (8, 10, 18))
    line(742, 800, 838, 800, (255, 190, 100), 0.22, 1.6)  # lantern-lit rim
    ink = (4, 5, 11)
    line(793, 800, 790, 774, ink, 1.0, 5.0, mode="blend")   # body
    hard_dot(789, 765, 6, ink)                              # head
    line(791, 780, 807, 759, ink, 1.0, 4.0, mode="blend")   # raised arm
    # lantern: glow, warm halo, bright core
    stamp(810, 752, 30, (255, 176, 84), 0.26)
    stamp(810, 752, 13, (255, 196, 104), 0.50)
    stamp(810, 752, 3.2, (255, 238, 196), 0.98)
    hard_dot(810, 757, 2, ink)
    # lantern shimmer on the water
    rng = random.Random(88)
    for y in range(834, 886, 3):
        depth = (y - 834) / 52
        sx = 810 + rng.gauss(0, 5 + 8 * depth)
        ln = rng.uniform(6, 20) * (1 - depth * 0.5)
        a = 0.16 * (1 - depth)
        for xx in range(int(sx - ln / 2), int(sx + ln / 2)):
            add_px(xx, y, int(255 * a), int(180 * a), int(84 * a))


# ------------------------------------------------------------------ final

def finish():
    rng = random.Random(99)
    dx2 = [((x - 512) / 512.0) ** 2 for x in range(W)]
    for y in range(H):
        dy2 = ((y - 512) / 512.0) ** 2
        base = y * W * 3
        for x in range(W):
            d2 = dx2[x] + dy2
            f = 1.0 - 0.40 * min(1.0, d2 * 0.62)
            n = rng.randint(-4, 4)
            i = base + x * 3
            fb[i] = max(0, min(255, int(fb[i] * f) + n))
            fb[i + 1] = max(0, min(255, int(fb[i + 1] * f) + n))
            fb[i + 2] = max(0, min(255, int(fb[i + 2] * f) + n))


def encode_png():
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        row = fb[y * stride:(y + 1) * stride]
        filt = bytearray(row)
        for i in range(stride - 1, 2, -1):
            filt[i] = (filt[i] - filt[i - 3]) & 0xFF
        raw.append(1)  # Sub filter
        raw += filt
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", binascii.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", comp)
            + chunk(b"IEND", b""))


def main():
    paint_background()
    paint_stars()
    paint_reflection()
    paint_whale()
    paint_sheeting()
    paint_burst()
    paint_boat()
    finish()
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "entry.png"), "wb") as fh:
        fh.write(encode_png())


if __name__ == "__main__":
    main()
