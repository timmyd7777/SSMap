# SSMap

Solar system mapping tools — interactive viewer, printable PDF charts, and orbital position tables.

## What's here

- **ssmap.html** — Interactive browser-based solar system map with zoomable elliptical orbits, date picker, and light/dark themes. Open directly in any browser.
- **ssmap.py** — Generate a scaled PDF diagram of the solar system with elliptical orbits.
- **ssmap2.py** — Combined ecliptic star chart + geocentric solar system diagram. Shows heliocentric planet orbits centered on Earth's position with sight lines to zodiac constellations.
- **ecliptic.py** — Zodiac star chart PDF using Lambert azimuthal equal-area projection, with IAU constellation stick figures.
- **sstable.py** — Generate tables of orbital positions past perihelion at monthly intervals (PDF or CSV).
- **drawctx.py** — Drawing context abstraction supporting both PDF (reportlab) and PNG (Pillow) output.

## Requirements

- Python 3
- [ReportLab](https://pypi.org/project/reportlab/) — for PDF generation
- [Pillow](https://pypi.org/project/Pillow/) — for PNG output (optional)

```
pip install reportlab Pillow
```

## Quick start

Open `ssmap.html` in a browser for the interactive map.

Generate a PDF solar system diagram:

```
python ssmap.py
```

Generate a combined star chart + solar system map for a specific date:

```
python ssmap2.py --date 2025-06-21
```

Generate an ecliptic star chart:

```
python ecliptic.py
```

Generate an orbital position table:

```
python sstable.py
```

## License

This project is released into the public domain under [The Unlicense](LICENSE). Use it for any purpose whatsoever.
