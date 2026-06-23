"""Drawing context abstraction for PDF (reportlab) and PNG (Pillow) output."""

import math

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas
except ImportError:
    rl_canvas = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None


def _rgb8(r, g, b):
    return (int(r * 255), int(g * 255), int(b * 255))


class PDFDraw:
    """Drawing context wrapping reportlab canvas."""

    def __init__(self, path, width, height, title="", bg=(1, 1, 1)):
        self.c = rl_canvas.Canvas(path, pagesize=(width, height))
        self.c.setTitle(title)
        self.w, self.h = width, height
        if bg != (1, 1, 1):
            self.c.setFillColorRGB(*bg)
            self.c.rect(0, 0, width, height, stroke=0, fill=1)
        self._stroke = (0, 0, 0)
        self._fill = (0, 0, 0)
        self._lw = 1
        self._font = ("Helvetica", 10)

    def set_stroke(self, r, g, b):
        self._stroke = (r, g, b)
        self.c.setStrokeColorRGB(r, g, b)

    def set_fill(self, r, g, b):
        self._fill = (r, g, b)
        self.c.setFillColorRGB(r, g, b)

    def set_line_width(self, w):
        self._lw = w
        self.c.setLineWidth(w)

    def set_font(self, name, size):
        self._font = (name, size)
        self.c.setFont(name, size)

    def line(self, x1, y1, x2, y2):
        self.c.line(x1, y1, x2, y2)

    def circle(self, x, y, r, stroke=True, fill=False):
        self.c.circle(x, y, r, stroke=int(stroke), fill=int(fill))

    def ellipse(self, cx, cy, a, b, rotation_deg):
        self.c.saveState()
        self.c.translate(cx, cy)
        self.c.rotate(rotation_deg)
        self.c.ellipse(-a, -b, a, b, stroke=1, fill=0)
        self.c.restoreState()

    def text_centered(self, x, y, s):
        self.c.drawCentredString(x, y, s)

    def text_left(self, x, y, s):
        self.c.drawString(x, y, s)

    def text_rotated(self, x, y, angle_deg, s, anchor="center"):
        self.c.saveState()
        self.c.translate(x, y)
        self.c.rotate(angle_deg)
        vc = -self._font[1] * 0.35  # vertical center offset
        if anchor == "center":
            self.c.drawCentredString(0, vc, s)
        else:
            self.c.drawString(0, vc, s)
        self.c.restoreState()

    def draw_path(self, points, closed=True, stroke=True, fill=True):
        p = self.c.beginPath()
        p.moveTo(*points[0])
        for pt in points[1:]:
            p.lineTo(*pt)
        if closed:
            p.close()
        self.c.drawPath(p, stroke=int(stroke), fill=int(fill))

    def save(self):
        self.c.save()


class PNGDraw:
    """Drawing context wrapping Pillow."""

    def __init__(self, path, width, height, title="", bg=(1, 1, 1)):
        self.path = path
        self.w, self.h = width, height
        self.img = Image.new('RGB', (width, height), _rgb8(*bg))
        self.draw = ImageDraw.Draw(self.img, 'RGBA')
        self._stroke = (0, 0, 0)
        self._fill = (0, 0, 0)
        self._lw = 1
        self._font_name = "Helvetica"
        self._font_size = 10
        self._font = ImageFont.load_default()
        self._scale = width / 612.0  # scale relative to letter-width PDF

    def _s(self, v):
        """Scale a PDF-coordinate value to pixel coordinates."""
        return v * self._scale

    def _px(self, x):
        return x * self._scale

    def _py(self, y):
        return self.h - y * self._scale

    def set_stroke(self, r, g, b):
        self._stroke = _rgb8(r, g, b)

    def set_fill(self, r, g, b):
        self._fill = _rgb8(r, g, b)

    def set_line_width(self, w):
        self._lw = max(1, round(w * self._scale))

    def set_font(self, name, size):
        self._font_name = name
        self._font_size = size
        scaled = max(8, round(size * self._scale))
        try:
            self._font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", scaled)
        except (IOError, OSError):
            try:
                self._font = ImageFont.truetype("arial.ttf", scaled)
            except (IOError, OSError):
                self._font = ImageFont.load_default()
        if "Bold" in name:
            try:
                self._font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", scaled)
            except (IOError, OSError):
                pass
        if "Oblique" in name or "Italic" in name:
            try:
                self._font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", scaled)
            except (IOError, OSError):
                pass

    def line(self, x1, y1, x2, y2):
        self.draw.line([(self._px(x1), self._py(y1)),
                        (self._px(x2), self._py(y2))],
                       fill=self._stroke, width=self._lw)

    def circle(self, x, y, r, stroke=True, fill=False):
        px, py = self._px(x), self._py(y)
        pr = self._s(r)
        bbox = [px - pr, py - pr, px + pr, py + pr]
        if fill:
            self.draw.ellipse(bbox, fill=self._fill,
                              outline=self._stroke if stroke else None,
                              width=self._lw if stroke else 0)
        elif stroke:
            self.draw.ellipse(bbox, outline=self._stroke, width=self._lw)

    def ellipse(self, cx, cy, a, b, rotation_deg):
        pcx, pcy = self._px(cx), self._py(cy)
        pa, pb = self._s(a), self._s(b)
        steps = 120
        pts = []
        rot = math.radians(rotation_deg)
        cos_r, sin_r = math.cos(rot), math.sin(rot)
        for i in range(steps):
            t = 2 * math.pi * i / steps
            ex = pa * math.cos(t)
            ey = pb * math.sin(t)
            rx = pcx + ex * cos_r + ey * sin_r
            ry = pcy - ex * sin_r + ey * cos_r
            pts.append((rx, ry))
        pts.append(pts[0])
        self.draw.line(pts, fill=self._stroke, width=self._lw)

    def text_centered(self, x, y, s):
        px, py = self._px(x), self._py(y)
        bbox = self._font.getbbox(s)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        self.draw.text((px - tw / 2, py - th / 2), s,
                       fill=self._fill, font=self._font)

    def text_left(self, x, y, s):
        px, py = self._px(x), self._py(y)
        bbox = self._font.getbbox(s)
        th = bbox[3] - bbox[1]
        self.draw.text((px, py - th / 2), s,
                       fill=self._fill, font=self._font)

    def text_rotated(self, x, y, angle_deg, s, anchor="center"):
        px, py = self._px(x), self._py(y)
        bbox = self._font.getbbox(s)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        txt_img = Image.new('RGBA', (tw + 4, th + 4), (0, 0, 0, 0))
        txt_draw = ImageDraw.Draw(txt_img)
        txt_draw.text((2, 2), s, fill=self._fill + (255,), font=self._font)
        rotated = txt_img.rotate(angle_deg, expand=True,
                                 resample=Image.BICUBIC)
        rw, rh = rotated.size
        if anchor == "center":
            paste_x = int(px - rw / 2)
            paste_y = int(py - rh / 2)
        else:
            paste_x = int(px)
            paste_y = int(py - rh / 2)
        self.img.paste(rotated, (paste_x, paste_y), rotated)

    def draw_path(self, points, closed=True, stroke=True, fill=True):
        ppts = [(self._px(x), self._py(y)) for x, y in points]
        if fill:
            self.draw.polygon(ppts, fill=self._fill,
                              outline=self._stroke if stroke else None,
                              width=self._lw if stroke else 0)
        elif stroke:
            if closed:
                ppts.append(ppts[0])
            self.draw.line(ppts, fill=self._stroke, width=self._lw)

    def save(self):
        self.img.save(self.path)
