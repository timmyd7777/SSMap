#!/usr/bin/env python3
"""Generate a scaled PDF diagram of the solar system with elliptical orbits."""

import argparse
import math
import sys

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
except ImportError:
    sys.exit("Install reportlab first: pip install reportlab")


# Orbital elements (J2000 epoch, ecliptic plane)
# name, semi-major axis (AU), eccentricity, longitude of perihelion (deg), color RGB
PLANETS = [
    ("Mercury",  0.38710,  0.20563,   77.46,  (0.35, 0.35, 0.35)),
    ("Venus",    0.72333,  0.00677,  131.53,  (0.70, 0.45, 0.05)),
    ("Earth",    1.00000,  0.01671,  102.95,  (0.05, 0.30, 0.65)),
    ("Mars",     1.52368,  0.09341,  336.04,  (0.70, 0.15, 0.05)),
    ("Jupiter",  5.20260,  0.04839,   14.75,  (0.50, 0.30, 0.10)),
    ("Saturn",   9.55491,  0.05415,   92.43,  (0.60, 0.50, 0.15)),
    ("Uranus",  19.18171,  0.04717,  170.96,  (0.15, 0.55, 0.65)),
    ("Neptune", 30.06896,  0.00859,   44.97,  (0.10, 0.15, 0.60)),
]


def ellipse_point(a, b, theta, cx, cy, rot):
    """Point on a rotated ellipse in page coordinates."""
    x = a * math.cos(theta)
    y = b * math.sin(theta)
    cos_r, sin_r = math.cos(rot), math.sin(rot)
    return cx + x * cos_r - y * sin_r, cy + x * sin_r + y * cos_r


def is_visible(a, b, cx, cy, rot, page_w, page_h):
    """Check if any part of a rotated ellipse appears on the page."""
    for i in range(120):
        theta = 2 * math.pi * i / 120
        px, py = ellipse_point(a, b, theta, cx, cy, rot)
        if 0 <= px <= page_w and 0 <= py <= page_h:
            return True
    return False





def solve_kepler(M, e, tol=1e-10):
    """Solve M = E - e*sin(E) for E using Newton's method."""
    E = M
    for _ in range(50):
        dE = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < tol:
            break
    return E


def true_anomaly_from_E(E, e):
    """True anomaly from eccentric anomaly."""
    return 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2),
                          math.sqrt(1 - e) * math.cos(E / 2))


def orbit_pos(M, e, a_pts, varpi, sun_x, sun_y):
    """Compute page position and radial info for a mean anomaly M."""
    E = solve_kepler(M, e)
    nu = true_anomaly_from_E(E, e)
    r = a_pts * (1 - e * math.cos(E))
    x_orb = r * math.cos(nu)
    y_orb = r * math.sin(nu)
    cos_w, sin_w = math.cos(varpi), math.sin(varpi)
    px = sun_x + x_orb * cos_w - y_orb * sin_w
    py = sun_y + x_orb * sin_w + y_orb * cos_w
    return px, py


def orbit_tangent_deg(M, ecc, a_pts, varpi, sun_x, sun_y):
    """Return tangent angle (degrees) at mean anomaly M."""
    px, py = orbit_pos(M, ecc, a_pts, varpi, sun_x, sun_y)
    px2, py2 = orbit_pos(M + 0.001, ecc, a_pts, varpi, sun_x, sun_y)
    return math.degrees(math.atan2(py2 - py, px2 - px)) + 180


def draw_orbit_ticks(c, name, a_au, ecc, varpi_deg, color,
                     sun_x, sun_y, pts_per_au, page_w, page_h,
                     use_year_ticks=False):
    """Draw time-interval tick marks along an orbit using Kepler's equation."""
    a_pts = a_au * pts_per_au
    varpi = math.radians(varpi_deg)
    period_days = a_au ** 1.5 * 365.25

    if use_year_ticks and name == "Earth":
        # Calendar month ticks: 0=Jan, 1=Feb, ..., 11=Dec
        # Earth is ~362 days past perihelion at "0 January" (perihelion ~Jan 3)
        jan0_dpp = 362.0
        month_offsets = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        ticks = [((jan0_dpp + d) % period_days, i)
                 for i, d in enumerate(month_offsets)]
        label_every = 1  # label every tick
    elif use_year_ticks:
        tick_interval = 365.25 / 10  # 0.1 year
        n = round(period_days / tick_interval)
        ticks = [(i * tick_interval, i) for i in range(n)]
        label_every = 10  # every year
    else:
        n = round(period_days)
        ticks = [(float(d), d) for d in range(n)]
        label_every = 10  # every 10 days

    tick_short = 3
    tick_long = 6
    font_size = 6.75
    name_font_size = 7

    for day, idx in ticks:
        M = 2 * math.pi * day / period_days
        px, py = orbit_pos(M, ecc, a_pts, varpi, sun_x, sun_y)

        if not (-10 <= px <= page_w + 10 and -10 <= py <= page_h + 10):
            continue

        dx, dy = px - sun_x, py - sun_y
        dist = math.hypot(dx, dy)
        if dist < 0.5:
            continue
        ux, uy = dx / dist, dy / dist

        is_perihelion = (idx == 0)
        is_label_tick = (idx % label_every == 0)
        tl = tick_long if is_label_tick or is_perihelion else tick_short

        # Neptune: long ticks every year, but only label even years
        if name == "Neptune":
            is_labeled = is_perihelion or (is_label_tick and (idx // 10) % 2 == 0)
        else:
            is_labeled = is_perihelion or is_label_tick

        tx, ty = px + ux * tl, py + uy * tl
        c.setStrokeColorRGB(*color)
        c.setLineWidth(0.25)
        c.line(px, py, tx, ty)

        if not is_labeled:
            continue

        tang_deg = orbit_tangent_deg(M, ecc, a_pts, varpi, sun_x, sun_y)
        y_out = -font_size * 0.7
        y_in = 0.5

        earth_cal = (use_year_ticks and name == "Earth")

        if is_perihelion:
            # Tick label outside (month number for Earth calendar, "0" otherwise)
            tick_text = "1" if earth_cal else "0"
            gap = 4
            lx, ly = tx + ux * gap, ty + uy * gap
            c.saveState()
            c.setFont("Helvetica", font_size)
            c.setFillColorRGB(*color)
            c.translate(lx, ly)
            c.rotate(tang_deg)
            c.drawCentredString(0, y_out, tick_text)
            c.restoreState()

            # Planet name outside orbit, further out past the "0"
            gap_name = 12
            nx, ny = tx + ux * gap_name, ty + uy * gap_name
            c.saveState()
            c.setFont("Helvetica-Bold", name_font_size)
            c.setFillColorRGB(*color)
            c.translate(nx, ny)
            c.rotate(tang_deg)
            c.drawCentredString(0, -name_font_size * 0.7, name)
            c.restoreState()

            # Period inside orbit at perihelion (skip for Earth at outer scale)
            is_outer = name in ("Jupiter", "Saturn", "Uranus", "Neptune")
            if is_outer:
                period_text = f"{period_days / 365.25:.1f}"
            elif not use_year_ticks:
                period_text = str(round(period_days))
            else:
                period_text = None
            if period_text:
                gap_in = 8
                ix, iy = px - ux * gap_in, py - uy * gap_in
                c.saveState()
                c.setFont("Helvetica", font_size)
                c.setFillColorRGB(*color)
                c.translate(ix, iy)
                c.rotate(tang_deg)
                c.drawCentredString(0, y_in, period_text)
                c.restoreState()
        else:
            # Regular number label outside
            if earth_cal:
                text = str(idx + 1)
            elif use_year_ticks:
                text = str(idx // 10)
            else:
                text = str(idx)

            gap = 4
            lx, ly = tx + ux * gap, ty + uy * gap
            c.saveState()
            c.setFont("Helvetica", font_size)
            c.setFillColorRGB(*color)
            c.translate(lx, ly)
            c.rotate(tang_deg)
            c.drawCentredString(0, y_out, text)
            c.restoreState()

    # Inner calendar-month ticks for Earth in day-tick mode
    if name == "Earth" and not use_year_ticks:
        jan0_dpp = 362.0
        month_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        for month_idx, offset in enumerate(month_days):
            dpp = (jan0_dpp + offset) % period_days
            M = 2 * math.pi * dpp / period_days
            px, py = orbit_pos(M, ecc, a_pts, varpi, sun_x, sun_y)

            if not (-10 <= px <= page_w + 10 and -10 <= py <= page_h + 10):
                continue

            dx, dy = px - sun_x, py - sun_y
            dist = math.hypot(dx, dy)
            if dist < 0.5:
                continue
            ux, uy = dx / dist, dy / dist

            # Tick inward (toward Sun)
            tl = tick_long
            tx, ty = px - ux * tl, py - uy * tl
            c.setStrokeColorRGB(*color)
            c.setLineWidth(0.25)
            c.line(px, py, tx, ty)

            # Label inside
            tang_deg = orbit_tangent_deg(M, ecc, a_pts, varpi, sun_x, sun_y)
            gap = 4
            lx, ly = tx - ux * gap, ty - uy * gap
            c.saveState()
            c.setFont("Helvetica", font_size)
            c.setFillColorRGB(*color)
            c.translate(lx, ly)
            c.rotate(tang_deg)
            c.drawCentredString(0, 0.5, str(month_idx + 1))
            c.restoreState()


PRINT_MARGIN = 0.35 * inch


def draw_grid(c, sun_x, sun_y, page_w, page_h):
    """Draw graph-paper grid centered on the Sun, 1/4 inch spacing."""
    spacing = 0.25 * inch
    m = PRINT_MARGIN
    c.setStrokeColorRGB(0.60, 0.70, 0.82)
    c.setLineWidth(0.25)

    # Vertical lines outward from sun_x
    x = sun_x + spacing
    while x <= page_w - m:
        c.line(x, m, x, page_h - m)
        x += spacing
    x = sun_x - spacing
    while x >= m:
        c.line(x, m, x, page_h - m)
        x -= spacing

    # Horizontal lines outward from sun_y
    y = sun_y + spacing
    while y <= page_h - m:
        c.line(m, y, page_w - m, y)
        y += spacing
    y = sun_y - spacing
    while y >= m:
        c.line(m, y, page_w - m, y)
        y -= spacing


def draw_axes(c, sun_x, sun_y, page_w, page_h):
    """Draw X-Y axes. Vernal equinox is to the right."""
    m = PRINT_MARGIN
    margin_top = max(m, 40)

    ax = (0.55, 0.55, 0.55)

    # Axis lines
    c.setStrokeColorRGB(*ax)
    c.setLineWidth(0.4)
    c.line(m, sun_y, page_w - m, sun_y)
    c.line(sun_x, m, sun_x, page_h - margin_top)

    # Vernal equinox arrow and label at right end of X-axis
    arrow_x = page_w - m
    c.setStrokeColorRGB(*ax)
    c.setFillColorRGB(*ax)
    p = c.beginPath()
    p.moveTo(arrow_x, sun_y)
    p.lineTo(arrow_x - 6, sun_y + 3)
    p.lineTo(arrow_x - 6, sun_y - 3)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def generate(output, scale_ipa):
    page_w, page_h = letter
    pts_per_au = scale_ipa * inch

    # If Jupiter's orbit is visible, Sun at center; otherwise shift right
    # to keep Mars's orbit on the printed page
    jup_a = 5.20260 * pts_per_au
    jup_visible = jup_a < max(page_w, page_h)
    if jup_visible:
        sun_x, sun_y = page_w / 2, page_h / 2
    else:
        sun_x, sun_y = page_w / 2 + 0.25 * inch, page_h / 2

    c = canvas.Canvas(output, pagesize=letter)
    title = "Outer Planet Orbits" if jup_visible else "Inner Planet Orbits"
    c.setTitle(title)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(0.5 * inch, page_h - 36, title)

    # Scale bar
    if jup_visible:
        bar_au = 10.0
    else:
        bar_au = 1.0
        bar_len = bar_au * pts_per_au
        while bar_len > 3 * inch:
            bar_au /= 2
            bar_len = bar_au * pts_per_au
        while bar_len < 0.5 * inch:
            bar_au *= 2
            bar_len = bar_au * pts_per_au
    bar_len = bar_au * pts_per_au

    bar_x = 0.5 * inch
    bar_y = page_h - 52
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.8)
    c.line(bar_x, bar_y, bar_x + bar_len, bar_y)
    c.line(bar_x, bar_y - 3, bar_x, bar_y + 3)
    c.line(bar_x + bar_len, bar_y - 3, bar_x + bar_len, bar_y + 3)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(bar_x + bar_len + 4, bar_y - 3, f"{bar_au:g} AU")

    # Grid and axes behind everything
    draw_grid(c, sun_x, sun_y, page_w, page_h)
    draw_axes(c, sun_x, sun_y, page_w, page_h)

    visible = []
    hidden = []

    for name, a_au, ecc, varpi_deg, color in PLANETS:
        if jup_visible and name in ("Mercury", "Venus", "Mars"):
            continue
        a = a_au * pts_per_au
        b = a * math.sqrt(1 - ecc ** 2)
        c_focus = a * ecc
        varpi = math.radians(varpi_deg)

        # Ellipse center: offset from Sun so Sun sits at the correct focus
        cx = sun_x - c_focus * math.cos(varpi)
        cy = sun_y - c_focus * math.sin(varpi)

        if not is_visible(a, b, cx, cy, varpi, page_w, page_h):
            hidden.append(name)
            continue
        visible.append(name)

        c.saveState()
        c.setStrokeColorRGB(*color)
        c.setLineWidth(0.6)
        c.translate(cx, cy)
        c.rotate(varpi_deg)
        c.ellipse(-a, -b, a, b, stroke=1, fill=0)
        c.restoreState()

        is_outer = name in ("Jupiter", "Saturn", "Uranus", "Neptune")
        use_year = is_outer or (jup_visible and name == "Earth")
        draw_orbit_ticks(c, name, a_au, ecc, varpi_deg, color,
                         sun_x, sun_y, pts_per_au, page_w, page_h,
                         use_year_ticks=use_year)

    # Sun
    r_sun = max(2, min(5, 0.04 * pts_per_au))
    c.setFillColorRGB(1.0, 0.85, 0.0)
    c.setStrokeColorRGB(0.9, 0.7, 0.0)
    c.circle(sun_x, sun_y, r_sun, stroke=1, fill=1)
    if not jup_visible:
        c.setFont("Helvetica-Bold", 7)
        c.setFillColorRGB(0, 0, 0)
        c.drawCentredString(sun_x, sun_y - r_sun - 9, "Sun")

    if hidden:
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(0.5 * inch, 0.2 * inch,
                     f"Beyond page: {', '.join(hidden)}")

    c.save()
    print(f"Wrote {output}")
    if visible:
        print(f"Visible: {', '.join(visible)}")
    if hidden:
        print(f"Off page: {', '.join(hidden)}")


def main():
    p = argparse.ArgumentParser(
        description="Generate a PDF solar system diagram with scaled elliptical orbits.")
    p.add_argument("scale", type=float, help="Scale in inches per AU")
    p.add_argument("-o", "--output", default="solar_system.pdf",
                   help="Output PDF path (default: solar_system.pdf)")
    args = p.parse_args()
    if args.scale <= 0:
        p.error("Scale must be positive")
    generate(args.output, args.scale)


if __name__ == "__main__":
    main()
