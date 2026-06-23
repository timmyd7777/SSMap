#!/usr/bin/env python3
"""Generate a zodiac star chart PDF centered on the south ecliptic pole.

Uses Lambert azimuthal equal-area projection. Shows stars within a band
around the ecliptic with IAU constellation stick figures.

Star data from SSCore Brightest.csv (HR catalog).
Constellation shapes from SSCore Shapes.csv (IAU stick figures).
"""

import os
import math
import re
import sys
import argparse
import urllib.request

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
except ImportError:
    sys.exit("Install reportlab first: pip install reportlab")


OBLIQUITY = math.radians(23.4393)  # J2000

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

STAR_FILE = os.path.join(DATA_DIR, "brightest.csv")
STAR_URL = ("https://raw.githubusercontent.com/timmyd7777/SSCore/"
            "master/SSData/Stars/Brightest.csv")

SHAPE_FILE = os.path.join(DATA_DIR, "shapes.csv")
SHAPE_URL = ("https://raw.githubusercontent.com/timmyd7777/SSCore/"
             "master/SSData/Constellations/Shapes.csv")

ZODIAC = {'Ari', 'Tau', 'Gem', 'Cnc', 'Leo', 'Vir',
          'Lib', 'Sco', 'Sgr', 'Cap', 'Aqr', 'Psc'}

ZODIAC_NAMES = {
    'Ari': 'Aries', 'Tau': 'Taurus', 'Gem': 'Gemini', 'Cnc': 'Cancer',
    'Leo': 'Leo', 'Vir': 'Virgo', 'Lib': 'Libra', 'Sco': 'Scorpius',
    'Sgr': 'Sagittarius', 'Cap': 'Capricornus', 'Aqr': 'Aquarius',
    'Psc': 'Pisces',
}


def ensure_file(path, url):
    if not os.path.exists(path):
        print(f"Downloading {os.path.basename(path)}...")
        urllib.request.urlretrieve(url, path)
        size_kb = os.path.getsize(path) // 1024
        print(f"  Saved ({size_kb} KB)")


def parse_hms(s):
    """Parse 'HH MM SS.ss' to radians."""
    parts = s.strip().split()
    h, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
    deg = (h + m / 60 + sec / 3600) * 15
    return math.radians(deg)


def parse_dms(s):
    """Parse '±DD MM SS.s' to radians."""
    s = s.strip()
    sign = -1 if s.startswith('-') else 1
    parts = s.lstrip('+-').split()
    d, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
    deg = sign * (d + m / 60 + sec / 3600)
    return math.radians(deg)


def eq_to_ecl(ra_rad, dec_rad):
    """Equatorial (J2000) to ecliptic coordinates."""
    sd, cd = math.sin(dec_rad), math.cos(dec_rad)
    sa, ca = math.sin(ra_rad), math.cos(ra_rad)
    se, ce = math.sin(OBLIQUITY), math.cos(OBLIQUITY)
    sin_beta = sd * ce - cd * se * sa
    beta = math.asin(max(-1.0, min(1.0, sin_beta)))
    lam = math.atan2(sd * se + cd * ce * sa, cd * ca)
    if lam < 0:
        lam += 2 * math.pi
    return lam, beta


# Earth orbital elements for Sun position computation
EARTH_ECC = 0.01671
EARTH_VARPI = math.radians(102.95)  # longitude of perihelion
EARTH_PERIOD = 365.26  # days
EARTH_JAN0_DPP = 362.0  # days past perihelion at "0 January"

MONTH_OFFSETS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

# Moon mean motion
MOON_PERIOD = 27.3217  # mean sidereal period in days
MOON_MEAN_MOTION = 2 * math.pi / MOON_PERIOD  # radians per day
MOON_L0 = math.radians(218.3165)  # mean ecliptic longitude at J2000.0


def solve_kepler(M, e, tol=1e-10):
    """Solve M = E - e*sin(E) for E."""
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


def sun_longitude(day_of_year):
    """Sun's ecliptic longitude for a given day of year (0 = Jan 0)."""
    dpp = (EARTH_JAN0_DPP + day_of_year) % EARTH_PERIOD
    M = 2 * math.pi * dpp / EARTH_PERIOD
    E = solve_kepler(M, EARTH_ECC)
    nu = true_anomaly_from_E(E, EARTH_ECC)
    return (nu + EARTH_VARPI + math.pi) % (2 * math.pi)


def project(lam, beta):
    """Stereographic projection from south ecliptic pole."""
    theta = math.pi / 2 + beta
    r = 2 * math.tan(theta / 2)
    return r * math.cos(lam), r * math.sin(lam)


def star_radius(mag):
    """Dot radius in points for a given visual magnitude."""
    return max(0.3, (5.5 - mag) * 0.65)


HR_RE = re.compile(r'\bHR (\d+)\b')


def load_stars(band_deg, mag_limit):
    """Load stars from SSCore Brightest.csv, convert to ecliptic coords."""
    ensure_file(STAR_FILE, STAR_URL)
    stars = {}  # keyed by HR number
    band_rad = math.radians(band_deg)
    with open(STAR_FILE, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            fields = line.split(',')
            if len(fields) < 10:
                continue
            try:
                ra_rad = parse_hms(fields[1])
                dec_rad = parse_dms(fields[2])
                mag = float(fields[5])
            except (ValueError, IndexError):
                continue

            # Find HR number in the identifier fields
            hr_match = HR_RE.search(line)
            if not hr_match:
                continue
            hr = int(hr_match.group(1))

            lam, beta = eq_to_ecl(ra_rad, dec_rad)

            # Find constellation from identifier fields (Bayer designations like "33 Psc")
            con = ''
            for field in fields[10:]:
                field = field.strip()
                if len(field) >= 3 and field[-3:].isalpha() and field[-3:] != 'III':
                    candidate = field.split()[-1] if ' ' in field else ''
                    if len(candidate) == 3 and candidate[0].isupper():
                        con = candidate
                        break

            stars[hr] = {
                'mag': mag,
                'lam': lam,
                'beta': beta,
                'con': con,
                'plot': abs(beta) <= band_rad and mag <= mag_limit,
            }
    return stars


def load_shapes():
    """Load constellation stick figures from SSCore Shapes.csv."""
    ensure_file(SHAPE_FILE, SHAPE_URL)
    shapes = {}  # con -> list of (hr1, hr2)
    with open(SHAPE_FILE, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) < 3:
                continue
            try:
                con = parts[0].strip()
                hr1 = int(parts[1].strip())
                hr2 = int(parts[2].strip())
                shapes.setdefault(con, []).append((hr1, hr2))
            except ValueError:
                continue
    return shapes


def generate(output, band_deg=15.0, mag_limit=5.0):
    page_w, page_h = letter
    cx, cy = page_w / 2, page_h / 2

    # Projection radii (stereographic)
    theta_outer = math.pi / 2 + math.radians(band_deg)
    r_outer = 2 * math.tan(theta_outer / 2)
    theta_inner = math.pi / 2 - math.radians(band_deg)
    r_inner = 2 * math.tan(theta_inner / 2)
    r_ecl = 2 * math.tan(math.pi / 4)

    usable = min(page_w, page_h) - 1.2 * inch
    scale = usable / (2 * r_outer)

    stars = load_stars(band_deg, mag_limit)
    shapes = load_shapes()

    c = canvas.Canvas(output, pagesize=letter)
    c.setTitle("Zodiac Star Chart")

    # Band boundary circles
    c.setStrokeColorRGB(0.60, 0.70, 0.82)
    c.setLineWidth(0.3)
    c.circle(cx, cy, r_inner * scale, stroke=1, fill=0)
    c.circle(cx, cy, r_outer * scale, stroke=1, fill=0)

    # Ecliptic circle
    c.setStrokeColorRGB(0.7, 0.5, 0.1)
    c.setLineWidth(0.6)
    c.circle(cx, cy, r_ecl * scale, stroke=1, fill=0)

    # Sun position tick marks around the ecliptic (365 days)
    tick_short = 3
    tick_long = 6
    font_size = 6.75
    r_ecl_pts = r_ecl * scale
    month_day_set = set(MONTH_OFFSETS)
    for day in range(365):
        lam_sun = sun_longitude(day)
        # Radial direction on the ecliptic circle
        ux, uy = math.cos(lam_sun), math.sin(lam_sun)
        px, py = cx + r_ecl_pts * ux, cy + r_ecl_pts * uy

        is_month = day in month_day_set
        tl = tick_long if is_month else tick_short

        # Tick outward from ecliptic
        c.setStrokeColorRGB(0.7, 0.5, 0.1)
        c.setLineWidth(0.25)
        tx, ty = px + ux * tl, py + uy * tl
        c.line(px, py, tx, ty)

        if is_month:
            month_num = MONTH_OFFSETS.index(day) + 1
            tang_deg = math.degrees(lam_sun) + 90 + 180
            gap = 4
            lx, ly = tx + ux * gap, ty + uy * gap
            c.saveState()
            c.setFont("Helvetica", font_size)
            c.setFillColorRGB(0.7, 0.5, 0.1)
            c.translate(lx, ly)
            c.rotate(tang_deg)
            c.drawCentredString(0, -font_size * 0.7, str(month_num))
            c.restoreState()

    # 30-degree longitude lines
    c.setStrokeColorRGB(0.60, 0.70, 0.82)
    c.setLineWidth(0.3)
    for deg in range(0, 360, 30):
        lam = math.radians(deg)
        x1, y1 = project(lam, -math.radians(band_deg))
        x2, y2 = project(lam, math.radians(band_deg))
        c.line(cx + x1 * scale, cy + y1 * scale,
               cx + x2 * scale, cy + y2 * scale)

    # Axes (extend to outer ring only)
    axis_r = r_outer * scale
    c.setStrokeColorRGB(0.65, 0.65, 0.65)
    c.setLineWidth(0.3)
    c.line(cx - axis_r, cy, cx + axis_r, cy)
    c.line(cx, cy - axis_r, cx, cy + axis_r)

    # Moon's circular orbit in the inner area
    moon_r = r_inner * scale * 0.7  # 70% of inner ring radius

    # Draw circular orbit
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    c.setLineWidth(0.6)
    c.circle(cx, cy, moon_r, stroke=1, fill=0)

    # Tick marks: one per day of mean motion, starting at Moon's
    # mean ecliptic longitude at J2000.0
    moon_tick_short = 3
    moon_tick_long = 5
    moon_font_size = 5.5
    n_moon_ticks = round(MOON_PERIOD)
    daily_step = MOON_MEAN_MOTION  # radians per day

    for i in range(n_moon_ticks):
        lam = MOON_L0 + i * daily_step
        ux, uy = math.cos(lam), math.sin(lam)
        px, py = cx + moon_r * ux, cy + moon_r * uy

        is_labeled = True
        tl = moon_tick_long if is_labeled else moon_tick_short

        tx, ty = px + ux * tl, py + uy * tl
        c.setStrokeColorRGB(0.35, 0.35, 0.35)
        c.setLineWidth(0.25)
        c.line(px, py, tx, ty)

        if is_labeled:
            tang_deg = math.degrees(lam) + 90 + 180
            gap = 3
            lx, ly = tx + ux * gap, ty + uy * gap
            c.saveState()
            c.setFont("Helvetica", moon_font_size)
            c.setFillColorRGB(0.35, 0.35, 0.35)
            c.translate(lx, ly)
            c.rotate(tang_deg)
            c.drawCentredString(0, -moon_font_size * 0.7, str(i))
            c.restoreState()

    # "Moon" label and period at the zero mark
    ux0 = math.cos(MOON_L0)
    uy0 = math.sin(MOON_L0)
    px0, py0 = cx + moon_r * ux0, cy + moon_r * uy0
    tang0 = math.degrees(MOON_L0) + 90 + 180

    gap_name = 14
    nx, ny = px0 + ux0 * gap_name, py0 + uy0 * gap_name
    c.saveState()
    c.setFont("Helvetica-Bold", 6)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.translate(nx, ny)
    c.rotate(tang0)
    c.drawCentredString(0, -6 * 0.7, "Moon")
    c.restoreState()

    gap_in = 6
    ix, iy = px0 - ux0 * gap_in, py0 - uy0 * gap_in
    c.saveState()
    c.setFont("Helvetica", moon_font_size)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.translate(ix, iy)
    c.rotate(tang0)
    c.drawCentredString(0, 0.5, f"{MOON_PERIOD:.1f}")
    c.restoreState()

    # Constellation stick figures
    c.setStrokeColorRGB(0.45, 0.55, 0.72)
    c.setLineWidth(0.6)
    for con, pairs in shapes.items():
        if con not in ZODIAC:
            continue
        for hr1, hr2 in pairs:
            if hr1 not in stars or hr2 not in stars:
                continue
            s1, s2 = stars[hr1], stars[hr2]
            x1, y1 = project(s1['lam'], s1['beta'])
            x2, y2 = project(s2['lam'], s2['beta'])
            c.line(cx + x1 * scale, cy + y1 * scale,
                   cx + x2 * scale, cy + y2 * scale)

    # Stars
    for s in stars.values():
        if not s['plot']:
            continue
        x, y = project(s['lam'], s['beta'])
        px, py = cx + x * scale, cy + y * scale
        if not (0 <= px <= page_w and 0 <= py <= page_h):
            continue
        r = star_radius(s['mag'])
        c.setFillColorRGB(0, 0, 0)
        c.circle(px, py, r, stroke=0, fill=1)

    # Constellation labels at centroid, oriented parallel to ecliptic
    con_info = {}
    for con, pairs in shapes.items():
        if con not in ZODIAC:
            continue
        seen_hr = set()
        lams = []
        pts = []
        for hr1, hr2 in pairs:
            for hr in (hr1, hr2):
                if hr in stars and hr not in seen_hr:
                    seen_hr.add(hr)
                    s = stars[hr]
                    x, y = project(s['lam'], s['beta'])
                    pts.append((x, y))
                    lams.append(s['lam'])
        if pts:
            con_info[con] = (pts, lams)

    # Radial nudge (points) to avoid collisions with tick marks
    label_nudge = {'Gem': 12, 'Aqr': 12, 'Cnc': -10}

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColorRGB(0.25, 0.25, 0.50)
    for con, (pts, lams) in con_info.items():
        ax = sum(p[0] for p in pts) / len(pts)
        ay = sum(p[1] for p in pts) / len(pts)
        avg_lam = math.atan2(
            sum(math.sin(l) for l in lams),
            sum(math.cos(l) for l in lams))
        tang_deg = math.degrees(avg_lam) + 90 + 180
        px = cx + ax * scale
        py = cy + ay * scale
        nudge = label_nudge.get(con, 0)
        if nudge:
            ux = math.cos(avg_lam)
            uy = math.sin(avg_lam)
            px += ux * nudge
            py += uy * nudge
        c.saveState()
        c.translate(px, py)
        c.rotate(tang_deg)
        c.drawCentredString(0, -7 * 0.7, ZODIAC_NAMES.get(con, con))
        c.restoreState()

    # Longitude labels around outside
    c.setFont("Helvetica", 6)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    label_r = r_outer * scale + 10
    for deg in range(0, 360, 30):
        lam = math.radians(deg)
        lx = cx + label_r * math.cos(lam)
        ly = cy + label_r * math.sin(lam)
        tang_deg = deg + 90 + 180
        c.saveState()
        c.translate(lx, ly)
        c.rotate(tang_deg)
        c.drawCentredString(0, -6 * 0.7, f"{deg}°")
        c.restoreState()

    # Title
    c.setFont("Helvetica-Bold", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(0.5 * inch, page_h - 0.5 * inch, "Ecliptic Star Chart")

    c.save()
    n_plotted = sum(1 for s in stars.values() if s['plot'])
    n_shapes = sum(len(p) for con, p in shapes.items() if con in ZODIAC)
    print(f"Wrote {output}")
    print(f"  {n_plotted} stars plotted, {n_shapes} constellation line segments")


def main():
    p = argparse.ArgumentParser(
        description="Generate a zodiac star chart PDF "
                    "(south ecliptic pole projection).")
    p.add_argument("-o", "--output", default="zodiac.pdf",
                   help="Output PDF path (default: zodiac.pdf)")
    p.add_argument("--band", type=float, default=15.0,
                   help="Ecliptic latitude band in degrees (default: 15)")
    p.add_argument("--mag", type=float, default=5.0,
                   help="Magnitude limit (default: 5.0)")
    args = p.parse_args()
    generate(args.output, args.band, args.mag)


if __name__ == "__main__":
    main()
