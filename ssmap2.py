#!/usr/bin/env python3
"""Generate a combined ecliptic star chart + geocentric solar system diagram.

The outer ring shows zodiac constellations and Sun day-marks (from ecliptic.py).
The inner area shows heliocentric planet orbits centered on Earth's position
at a given date, with sight lines from Earth through each planet to the
ecliptic ring showing where each planet appears among the constellations.
"""

import os
import math
import re
import sys
import argparse
import urllib.request
from datetime import date

from drawctx import PDFDraw, PNGDraw

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
except ImportError:
    letter = (612, 792)
    inch = 72


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

# Planet orbital elements: name, a(AU), e, varpi(deg), color, period(days), M0(deg at J2000)
PLANETS = [
    ("Mercury",  0.38710,  0.20563,   77.46,  (0.35, 0.35, 0.35),   87.969, 174.795),
    ("Venus",    0.72333,  0.00677,  131.53,  (0.70, 0.45, 0.05),  224.701,  50.416),
    ("Earth",    1.00000,  0.01671,  102.95,  (0.05, 0.30, 0.65),  365.260, 357.529),
    ("Mars",     1.52368,  0.09341,  336.04,  (0.70, 0.15, 0.05),  686.996,  19.373),
    ("Jupiter",  5.20260,  0.04839,   14.75,  (0.50, 0.30, 0.10), 4332.59,   20.020),
    ("Saturn",   9.55491,  0.05415,   92.43,  (0.60, 0.50, 0.15),10759.22,  317.020),
    ("Uranus",  19.18171,  0.04717,  170.96,  (0.15, 0.55, 0.65),30688.5,   142.238),
    ("Neptune", 30.06896,  0.00859,   44.97,  (0.10, 0.15, 0.60),60182.0,   256.225),
]

# Sun position on ecliptic
EARTH_ECC = 0.01671
EARTH_VARPI = math.radians(102.95)
EARTH_PERIOD = 365.26
EARTH_JAN0_DPP = 362.0

MONTH_OFFSETS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

J2000_DATE = date(2000, 1, 1)
J2000_OFFSET = 0.5

# Moon orbital elements
MOON_ECC = 0.0549
MOON_PERIOD = 27.3217  # sidereal period, days
MOON_M0 = 134.9  # mean anomaly at J2000, degrees
MOON_VARPI0 = 83.35  # ecliptic longitude of perigee at J2000, degrees
MOON_VARPI_RATE = 40.69  # precession of perigee, degrees/year
MOON_DISPLAY_A = 0.2  # exaggerated semi-major axis in AU


def ensure_file(path, url):
    if not os.path.exists(path):
        print(f"Downloading {os.path.basename(path)}...")
        urllib.request.urlretrieve(url, path)
        size_kb = os.path.getsize(path) // 1024
        print(f"  Saved ({size_kb} KB)")


def parse_hms(s):
    parts = s.strip().split()
    h, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
    return math.radians((h + m / 60 + sec / 3600) * 15)


def parse_dms(s):
    s = s.strip()
    sign = -1 if s.startswith('-') else 1
    parts = s.lstrip('+-').split()
    d, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
    return math.radians(sign * (d + m / 60 + sec / 3600))


def eq_to_ecl(ra_rad, dec_rad):
    sd, cd = math.sin(dec_rad), math.cos(dec_rad)
    sa, ca = math.sin(ra_rad), math.cos(ra_rad)
    se, ce = math.sin(OBLIQUITY), math.cos(OBLIQUITY)
    sin_beta = sd * ce - cd * se * sa
    beta = math.asin(max(-1.0, min(1.0, sin_beta)))
    lam = math.atan2(sd * se + cd * ce * sa, cd * ca)
    if lam < 0:
        lam += 2 * math.pi
    return lam, beta


def solve_kepler(M, e, tol=1e-10):
    E = M
    for _ in range(50):
        dE = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= dE
        if abs(dE) < tol:
            break
    return E


def true_anomaly_from_E(E, e):
    return 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2),
                          math.sqrt(1 - e) * math.cos(E / 2))


def draw_moon_phase(dc, mx, my, mr, phase_angle, toward_sun_angle):
    """Draw a Moon phase disk. phase_angle: 0=new, pi=full."""
    dc.set_fill(0.25, 0.25, 0.25)
    dc.set_stroke(0.4, 0.4, 0.4)
    dc.circle(mx, my, mr, stroke=True, fill=True)

    pa = phase_angle % (2 * math.pi)
    if pa < 0.03 or pa > 2 * math.pi - 0.03:
        return

    k = math.cos(pa)
    steps = 24
    cos_r, sin_r = math.cos(toward_sun_angle), math.sin(toward_sun_angle)

    points = []
    for i in range(steps + 1):
        t = math.pi / 2 - i * math.pi / steps
        x = mr * math.cos(t)
        y = mr * math.sin(t)
        points.append((mx + x * cos_r - y * sin_r,
                        my + x * sin_r + y * cos_r))
    for i in range(steps + 1):
        t = -math.pi / 2 + i * math.pi / steps
        x = mr * k * math.cos(t)
        y = mr * math.sin(t)
        points.append((mx + x * cos_r - y * sin_r,
                        my + x * sin_r + y * cos_r))

    dc.set_fill(0.95, 0.95, 0.85)
    dc.draw_path(points, closed=True, stroke=False, fill=True)
    dc.set_stroke(0.4, 0.4, 0.4)
    dc.set_line_width(0.3)
    dc.circle(mx, my, mr, stroke=True, fill=False)


def sun_longitude(day_of_year):
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
    return max(0.3, (5.5 - mag) * 0.65)


HR_RE = re.compile(r'\bHR (\d+)\b')


def load_stars(band_deg, mag_limit):
    ensure_file(STAR_FILE, STAR_URL)
    stars = {}
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
            hr_match = HR_RE.search(line)
            if not hr_match:
                continue
            hr = int(hr_match.group(1))
            lam, beta = eq_to_ecl(ra_rad, dec_rad)
            con = ''
            for field in fields[10:]:
                field = field.strip()
                if len(field) >= 3 and field[-3:].isalpha() and field[-3:] != 'III':
                    candidate = field.split()[-1] if ' ' in field else ''
                    if len(candidate) == 3 and candidate[0].isupper():
                        con = candidate
                        break
            stars[hr] = {
                'mag': mag, 'lam': lam, 'beta': beta, 'con': con,
                'plot': abs(beta) <= band_rad and mag <= mag_limit,
            }
    return stars


def load_shapes():
    ensure_file(SHAPE_FILE, SHAPE_URL)
    shapes = {}
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


def planet_helio_xy(a_au, ecc, varpi_deg, period, M0_deg, target_date):
    """Heliocentric ecliptic x,y position (AU) for a planet on a date."""
    dt = (target_date - J2000_DATE).days - J2000_OFFSET
    n = 360.0 / period
    M_deg = (M0_deg + n * dt) % 360.0
    M = math.radians(M_deg)
    E = solve_kepler(M, ecc)
    nu = true_anomaly_from_E(E, ecc)
    r = a_au * (1 - ecc * math.cos(E))
    varpi = math.radians(varpi_deg)
    ang = nu + varpi
    return r * math.cos(ang), r * math.sin(ang)


def generate(output, target_date, au_radius=2.0,
             band_deg=15.0, mag_limit=5.0, png_size=None, dark=False):
    if png_size:
        page_w = page_h = 612.0
        cx, cy = page_w / 2, page_h / 2
    else:
        page_w, page_h = letter
        cx, cy = page_w / 2, page_h / 2

    # Color scheme
    if dark:
        bg = (0, 0, 0)
        fg = (1, 1, 1)
        grid_c = (0.2, 0.25, 0.35)
        ecl_c = (0.55, 0.40, 0.10)
        stick_c = (0.30, 0.40, 0.55)
        con_label_c = (0.45, 0.45, 0.70)
        lon_label_c = (0.5, 0.5, 0.5)
        star_c = (1, 1, 1)
        moon_orbit_c = (0.6, 0.6, 0.6)
        moon_dot_c = (0.7, 0.7, 0.7)
        title_c = (1, 1, 1)
    else:
        bg = (1, 1, 1)
        fg = (0, 0, 0)
        grid_c = (0.60, 0.70, 0.82)
        ecl_c = (0.7, 0.5, 0.1)
        stick_c = (0.45, 0.55, 0.72)
        con_label_c = (0.25, 0.25, 0.50)
        lon_label_c = (0.35, 0.35, 0.35)
        star_c = (0, 0, 0)
        moon_orbit_c = (0.35, 0.35, 0.35)
        moon_dot_c = (0.5, 0.5, 0.5)
        title_c = (0, 0, 0)

    # Ecliptic ring projection
    theta_outer = math.pi / 2 + math.radians(band_deg)
    r_outer = 2 * math.tan(theta_outer / 2)
    theta_inner = math.pi / 2 - math.radians(band_deg)
    r_inner = 2 * math.tan(theta_inner / 2)
    r_ecl = 2 * math.tan(math.pi / 4)

    if png_size:
        usable = min(page_w, page_h) - 2.0  # ~1 pixel margin
    else:
        usable = min(page_w, page_h) - 0.6 * inch
    ecl_scale = usable / (2 * r_outer)

    # Inner area scale: map au_radius AU to fit inside inner ring
    inner_radius_pts = r_inner * ecl_scale * 0.95
    au_scale = inner_radius_pts / au_radius  # points per AU

    # Earth's heliocentric position on target date
    earth_x, earth_y = planet_helio_xy(1.0, 0.01671, 102.95, 365.260,
                                        357.529, target_date)

    stars = load_stars(band_deg, mag_limit)
    shapes = load_shapes()

    title_str = f"Solar System Map — {target_date}"
    if png_size:
        dc = PNGDraw(output, png_size, png_size, title_str, bg=bg)
    else:
        dc = PDFDraw(output, page_w, page_h, title_str, bg=bg)

    # --- Ecliptic ring ---

    # Band boundaries
    dc.set_stroke(*grid_c)
    dc.set_line_width(0.3)
    dc.circle(cx, cy, r_inner * ecl_scale, stroke=True, fill=False)
    dc.circle(cx, cy, r_outer * ecl_scale, stroke=True, fill=False)

    # Ecliptic circle
    dc.set_stroke(*ecl_c)
    dc.set_line_width(0.6)
    dc.circle(cx, cy, r_ecl * ecl_scale, stroke=True, fill=False)

    r_ecl_pts = r_ecl * ecl_scale

    # 30-degree longitude lines
    dc.set_stroke(*grid_c)
    dc.set_line_width(0.3)
    for deg in range(0, 360, 30):
        lam = math.radians(deg)
        x1, y1 = project(lam, -math.radians(band_deg))
        x2, y2 = project(lam, math.radians(band_deg))
        dc.line(cx + x1 * ecl_scale, cy + y1 * ecl_scale,
                cx + x2 * ecl_scale, cy + y2 * ecl_scale)

    # Constellation stick figures
    dc.set_stroke(*stick_c)
    dc.set_line_width(0.6)
    for con, pairs in shapes.items():
        if con not in ZODIAC:
            continue
        for hr1, hr2 in pairs:
            if hr1 not in stars or hr2 not in stars:
                continue
            s1, s2 = stars[hr1], stars[hr2]
            x1, y1 = project(s1['lam'], s1['beta'])
            x2, y2 = project(s2['lam'], s2['beta'])
            dc.line(cx + x1 * ecl_scale, cy + y1 * ecl_scale,
                    cx + x2 * ecl_scale, cy + y2 * ecl_scale)

    # Stars
    for s in stars.values():
        if not s['plot']:
            continue
        x, y = project(s['lam'], s['beta'])
        px, py = cx + x * ecl_scale, cy + y * ecl_scale
        if not (0 <= px <= page_w and 0 <= py <= page_h):
            continue
        r = star_radius(s['mag'])
        dc.set_fill(*star_c)
        dc.circle(px, py, r, stroke=False, fill=True)

    # Constellation labels
    con_info = {}
    for con, pairs in shapes.items():
        if con not in ZODIAC:
            continue
        seen_hr = set()
        lams_list = []
        pts = []
        for hr1, hr2 in pairs:
            for hr in (hr1, hr2):
                if hr in stars and hr not in seen_hr:
                    seen_hr.add(hr)
                    s = stars[hr]
                    x, y = project(s['lam'], s['beta'])
                    pts.append((x, y))
                    lams_list.append(s['lam'])
        if pts:
            con_info[con] = (pts, lams_list)

    label_nudge = {'Gem': 12, 'Aqr': 12, 'Cnc': -10}
    dc.set_font("Helvetica-Oblique", 7)
    dc.set_fill(*con_label_c)
    for con, (pts, lams_list) in con_info.items():
        ax = sum(p[0] for p in pts) / len(pts)
        ay = sum(p[1] for p in pts) / len(pts)
        avg_lam = math.atan2(
            sum(math.sin(l) for l in lams_list),
            sum(math.cos(l) for l in lams_list))
        tang_deg = math.degrees(avg_lam) + 90 + 180
        px = cx + ax * ecl_scale
        py = cy + ay * ecl_scale
        nudge = label_nudge.get(con, 0)
        if nudge:
            px += math.cos(avg_lam) * nudge
            py += math.sin(avg_lam) * nudge
        dc.text_rotated(px, py, tang_deg,
                        ZODIAC_NAMES.get(con, con))

    # Longitude labels (inside inner ring)
    dc.set_font("Helvetica", 6)
    dc.set_fill(*lon_label_c)
    label_r = r_inner * ecl_scale - 6
    for deg in range(0, 360, 30):
        lam = math.radians(deg)
        lx = cx + label_r * math.cos(lam)
        ly = cy + label_r * math.sin(lam)
        tang_deg = deg + 90 + 180
        dc.text_rotated(lx, ly, tang_deg, f"{deg}°")

    # --- Inner area: geocentric solar system ---

    # Draw planet orbits (heliocentric ellipses, offset so Earth is at center)
    # Sun position on page = center + (sun_helio - earth_helio) * au_scale
    # But sun_helio = (0,0), so sun on page = center + (-earth_x, -earth_y) * au_scale
    sun_px = cx + (-earth_x) * au_scale
    sun_py = cy + (-earth_y) * au_scale

    planet_positions = []

    skip_inner = au_radius > 10
    for name, a_au, ecc, varpi_deg, color, period, M0 in PLANETS:
        if a_au > au_radius:
            continue
        if skip_inner and name in ("Mercury", "Venus", "Mars"):
            continue

        # Draw orbit ellipse centered on Sun's page position
        a_pts = a_au * au_scale
        b_pts = a_pts * math.sqrt(1 - ecc ** 2)
        c_focus = a_pts * ecc
        varpi = math.radians(varpi_deg)

        orbit_cx = sun_px - c_focus * math.cos(varpi)
        orbit_cy = sun_py - c_focus * math.sin(varpi)

        dc.set_stroke(*color)
        dc.set_line_width(0.5)
        dc.ellipse(orbit_cx, orbit_cy, a_pts, b_pts, varpi_deg)

        # Planet position on target date (geocentric)
        if name == "Earth":
            # Earth is at the center
            planet_positions.append((name, cx, cy, color, 0, 0))
            continue

        hx, hy = planet_helio_xy(a_au, ecc, varpi_deg, period, M0, target_date)
        # Geocentric position
        geo_x = hx - earth_x
        geo_y = hy - earth_y
        pp_x = cx + geo_x * au_scale
        pp_y = cy + geo_y * au_scale
        planet_positions.append((name, pp_x, pp_y, color, geo_x, geo_y))

    # Draw sight lines from Earth through each planet to the ecliptic ring
    dc.set_line_width(0.25)
    for name, pp_x, pp_y, color, geo_x, geo_y in planet_positions:
        if name == "Earth":
            continue
        ang = math.atan2(geo_y, geo_x)
        ring_x = cx + r_ecl_pts * math.cos(ang)
        ring_y = cy + r_ecl_pts * math.sin(ang)
        dc.set_stroke(*color)
        dc.line(cx, cy, ring_x, ring_y)
        dc.set_fill(*color)
        dc.circle(ring_x, ring_y, 2.5, stroke=False, fill=True)

    # Sun sight line from Earth to ecliptic ring
    sun_ang = math.atan2(-earth_y, -earth_x)
    sun_ring_x = cx + r_ecl_pts * math.cos(sun_ang)
    sun_ring_y = cy + r_ecl_pts * math.sin(sun_ang)
    dc.set_stroke(0.9, 0.7, 0.0)
    dc.set_line_width(0.25)
    dc.line(cx, cy, sun_ring_x, sun_ring_y)
    dc.set_fill(1.0, 0.85, 0.0)
    dc.set_stroke(0.9, 0.7, 0.0)
    dc.circle(sun_ring_x, sun_ring_y, 4, stroke=True, fill=True)

    # Draw Sun dot
    dc.set_fill(1.0, 0.85, 0.0)
    dc.set_stroke(0.9, 0.7, 0.0)
    dc.circle(sun_px, sun_py, 2, stroke=True, fill=True)

    # Draw planet dots and labels
    for name, pp_x, pp_y, color, geo_x, geo_y in planet_positions:
        if name == "Earth":
            dc.set_fill(*color)
            dc.circle(cx, cy, 1.25, stroke=False, fill=True)
            dc.set_font("Helvetica-Bold", 5.5)
            dc.text_centered(cx, cy - 10, "Earth")
            continue

        dc.set_fill(*color)
        dc.circle(pp_x, pp_y, 1.25, stroke=False, fill=True)
        dc.set_font("Helvetica-Bold", 5.5)
        dc.text_left(pp_x + 4, pp_y - 2, name)

    # Moon's orbit around Earth (only at small scales)
    if au_radius <= 10:
        dt_days = (target_date - J2000_DATE).days - J2000_OFFSET
        dt_years = dt_days / 365.25

        # Perigee longitude precesses
        moon_varpi_deg = MOON_VARPI0 + MOON_VARPI_RATE * dt_years
        moon_varpi = math.radians(moon_varpi_deg)

        # Moon's mean anomaly on target date
        n_moon = 360.0 / MOON_PERIOD
        moon_M_deg = (MOON_M0 + n_moon * dt_days) % 360.0
        moon_M = math.radians(moon_M_deg)

        # Solve Kepler for true anomaly
        moon_E = solve_kepler(moon_M, MOON_ECC)
        moon_nu = true_anomaly_from_E(moon_E, MOON_ECC)

        # Draw Moon's orbit ellipse centered on Earth (page center)
        moon_a_pts = MOON_DISPLAY_A * au_scale
        moon_b_pts = moon_a_pts * math.sqrt(1 - MOON_ECC ** 2)
        moon_c_focus = moon_a_pts * MOON_ECC

        moon_cx = cx - moon_c_focus * math.cos(moon_varpi)
        moon_cy = cy - moon_c_focus * math.sin(moon_varpi)

        dc.set_stroke(*moon_orbit_c)
        dc.set_line_width(0.5)
        dc.ellipse(moon_cx, moon_cy, moon_a_pts, moon_b_pts,
                   moon_varpi_deg)

        # Moon's position dot
        moon_r = moon_a_pts * (1 - MOON_ECC * math.cos(moon_E))
        moon_x = moon_r * math.cos(moon_nu)
        moon_y = moon_r * math.sin(moon_nu)
        cos_w = math.cos(moon_varpi)
        sin_w = math.sin(moon_varpi)
        moon_px = cx + moon_x * cos_w - moon_y * sin_w
        moon_py = cy + moon_x * sin_w + moon_y * cos_w

        # Moon sight line to ecliptic
        moon_geo_ang = math.atan2(moon_py - cy, moon_px - cx)
        moon_ring_x = cx + r_ecl_pts * math.cos(moon_geo_ang)
        moon_ring_y = cy + r_ecl_pts * math.sin(moon_geo_ang)
        dc.set_stroke(*moon_orbit_c)
        dc.set_line_width(0.25)
        dc.line(cx, cy, moon_ring_x, moon_ring_y)

        # Phase angle (elongation from Sun)
        sun_ang = math.atan2(-earth_y, -earth_x)
        phase = (moon_geo_ang - sun_ang) % (2 * math.pi)

        # Moon dot on orbit
        dc.set_fill(*moon_dot_c)
        dc.circle(moon_px, moon_py, 1.25, stroke=False, fill=True)
        dc.set_font("Helvetica-Bold", 5.5)
        dc.set_fill(*moon_dot_c)
        dc.text_left(moon_px + 4, moon_py - 2, "Moon")

        # Moon dot on ecliptic (same size as Sun, with phase)
        # Bright side faces Sun along the ecliptic (tangent direction),
        # so the terminator is radial (perpendicular to ecliptic)
        delta = (sun_ang - moon_geo_ang) % (2 * math.pi)
        if delta < math.pi:
            toward_sun_ecl = moon_geo_ang + math.pi / 2
        else:
            toward_sun_ecl = moon_geo_ang - math.pi / 2
        draw_moon_phase(dc, moon_ring_x, moon_ring_y, 4, phase,
                        toward_sun_ecl)

    # Title and date
    if png_size:
        tx, ty = 4, page_h - 4
    else:
        tx, ty = 0.5 * inch, page_h - 0.5 * inch
    dc.set_font("Helvetica-Bold", 12)
    dc.set_fill(*title_c)
    dc.text_left(tx, ty, "Solar System Map")
    dc.set_font("Helvetica", 9)
    dc.text_left(tx, ty - 14, f"to {au_radius:g} AU — {target_date.strftime('%d %B %Y')}")

    dc.save()
    n_plotted = sum(1 for s in stars.values() if s['plot'])
    n_planets = sum(1 for _, a, *_ in PLANETS if a <= au_radius)
    print(f"Wrote {output}")
    print(f"  {n_plotted} stars, {n_planets} planet orbits, date: {target_date}")


def main():
    p = argparse.ArgumentParser(
        description="Generate a combined ecliptic + geocentric solar system map.")
    p.add_argument("-o", "--output",
                   help="Output path (default: auto-generated)")
    p.add_argument("--date",
                   help="Date as YYYY-MM-DD (default: today)")
    p.add_argument("--au", type=float, default=10.0,
                   help="Radius of inner solar system in AU (default: 10.0)")
    p.add_argument("--band", type=float, default=15.0,
                   help="Ecliptic latitude band in degrees (default: 15)")
    p.add_argument("--mag", type=float, default=5.0,
                   help="Magnitude limit (default: 5.0)")
    p.add_argument("--png", type=int, default=None,
                   help="Output as PNG with given size in pixels (e.g. 1080)")
    p.add_argument("--dark", action="store_true",
                   help="Dark background mode")
    args = p.parse_args()

    target = date.fromisoformat(args.date) if args.date else date.today()
    ext = "png" if args.png else "pdf"

    if args.output is None:
        dark_tag = "-dark" if args.dark else ""
        args.output = (f"ssmap-{target.isoformat()}-"
                       f"{args.au:g}au{dark_tag}.{ext}")

    generate(args.output, target, args.au, args.band, args.mag,
             png_size=args.png, dark=args.dark)


if __name__ == "__main__":
    main()
