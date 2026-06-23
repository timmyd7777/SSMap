#!/usr/bin/env python3
"""Generate a table of orbital positions past perihelion at monthly intervals.

Each row is the "0th" of a month — the user adds the day of the month to get
the approximate position on any day. Mercury-Mars in days, Jupiter-Neptune in years.
"""

import argparse
import csv
import sys
from datetime import date, timedelta

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
except ImportError:
    pass  # only needed for PDF output


# Orbital elements at J2000.0 (noon, January 1, 2000)
# (name, anomalistic_period_days, mean_anomaly_at_J2000_degrees)
PLANETS = [
    ("Mercury",  87.969,  174.795),
    ("Venus",   224.701,   50.416),
    ("Earth",   365.260,  357.529),
    ("Mars",    686.996,   19.373),
    ("Jupiter", 4332.59,   20.020),
    ("Saturn", 10759.22,  317.020),
    ("Uranus", 30688.5,   142.238),
    ("Neptune",60182.0,   256.225),
]

INNER = {"Mercury", "Venus", "Earth", "Mars"}

MOON_PERIOD = 27.3217  # mean sidereal period in days

J2000_DATE = date(2000, 1, 1)
J2000_OFFSET = 0.5  # J2000.0 is noon, not midnight


def days_past_perihelion(period, M0_deg, target_date):
    """Days past perihelion for a planet on a given date."""
    dt = (target_date - J2000_DATE).days - J2000_OFFSET
    n = 360.0 / period
    M = (M0_deg + n * dt) % 360.0
    return M / 360.0 * period


def moon_position(target_date):
    """Moon's position on the zodiac chart (days from J2000 zero mark, mod period)."""
    dt = (target_date - J2000_DATE).days - J2000_OFFSET
    return dt % MOON_PERIOD


def generate_table(start_year, start_month, end_year, end_month):
    """Generate rows of (label, {planet/moon: value}) for each month in range."""
    rows = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        day0 = date(y, m, 1) - timedelta(days=1)
        label = f"{y}-{m:02d}"
        positions = {}
        for name, period, M0 in PLANETS:
            dpp = days_past_perihelion(period, M0, day0)
            positions[name] = dpp
        positions['Moon'] = moon_position(day0)
        rows.append((label, positions))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return rows


def format_val(name, val):
    if name == 'Moon':
        return f"{val:.1f}"
    if name in INNER:
        return str(round(val))
    return f"{val / 365.25:.1f}"


def write_csv(rows, names, output):
    with open(output, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(["Month"] + names)
        for label, positions in rows:
            w.writerow([label] + [format_val(n, positions[n]) for n in names])


def write_pdf(rows, names, output):
    page_w, page_h = letter
    c = canvas.Canvas(output, pagesize=letter)
    c.setTitle("Orbital Positions Past Perihelion")

    margin_l = 0.5 * inch
    margin_top = 0.5 * inch
    font_size = 9
    header_size = 10
    line_height = font_size + 2.5
    col_width = 52
    month_col_width = 52

    # Column x positions: right edge of each column for right-alignment
    col_x = [margin_l + month_col_width]  # right edge of Month column
    for i in range(len(names)):
        col_x.append(col_x[0] + (i + 1) * col_width)

    def draw_header(c, y):
        c.setFont("Times-Bold", header_size)
        c.drawString(margin_l, y, "Month")
        for i, name in enumerate(names):
            c.drawRightString(col_x[i + 1], y, name)
        y -= 3
        c.setLineWidth(0.5)
        c.line(margin_l, y, col_x[-1], y)
        return y - line_height + 1

    page_bottom = 0.5 * inch
    y = page_h - margin_top
    y = draw_header(c, y)

    c.setFont("Times-Roman", font_size)
    for label, positions in rows:
        if y < page_bottom:
            c.showPage()
            y = page_h - margin_top
            y = draw_header(c, y)
            c.setFont("Times-Roman", font_size)

        c.drawString(margin_l, y, label)
        for i, name in enumerate(names):
            c.drawRightString(col_x[i + 1], y, format_val(name, positions[name]))
        y -= line_height

    c.save()


def main():
    p = argparse.ArgumentParser(
        description="Generate orbital position table at monthly intervals. "
                    "Mercury-Mars in days past perihelion, "
                    "Jupiter-Neptune in years past perihelion.")
    p.add_argument("--start", default="2026-01",
                   help="Start year-month (default: 2026-01)")
    p.add_argument("--end", default="2030-12",
                   help="End year-month (default: 2030-12)")
    p.add_argument("--pdf", action="store_true",
                   help="Output as PDF instead of CSV")
    p.add_argument("-o", "--output",
                   help="Output path (default: orbit_positions.csv or .pdf)")
    args = p.parse_args()

    if args.output is None:
        args.output = "orbit_positions.pdf" if args.pdf else "orbit_positions.csv"

    sy, sm = map(int, args.start.split("-"))
    ey, em = map(int, args.end.split("-"))

    rows = generate_table(sy, sm, ey, em)
    names = ['Moon'] + [name for name, _, _ in PLANETS]

    if args.pdf:
        write_pdf(rows, names, args.output)
    else:
        write_csv(rows, names, args.output)

    print(f"Wrote {args.output}")
    print(f"  {len(rows)} months, {len(names)} planets")


if __name__ == "__main__":
    main()
