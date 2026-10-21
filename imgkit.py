"""Dựng ảnh thuần Python (không cần PIL): khung iPod touch cho postcard, watermark chữ (GDI của Windows)."""
import json, math, struct, sys, zlib
from pathlib import Path

import core

_LUT = {}


def _lut(c, a):
    k = (c, round(a, 3))
    t = _LUT.get(k)
    if t is None:
        t = _LUT[k] = bytes(min(255, int(i * (1 - a) + c * a + 0.5)) for i in range(256))
    return t


class Img:
    def __init__(self, w, h, rgb=None, color=(255, 255, 255)):
        self.w, self.h = w, h
        self.buf = bytearray(rgb) if rgb is not None else bytearray(bytes(color) * (w * h))

    def span(self, y, xa, xb, color, alpha=1.0):
        """Tô/pha màu đơn sắc cho đoạn ngang [xa, xb) ở hàng y."""
        xa, xb = max(xa, 0), min(xb, self.w)
        if xb <= xa or not 0 <= y < self.h:
            return
        o, n = (y * self.w + xa) * 3, xb - xa
        if alpha >= 1:
            self.buf[o:o + n * 3] = bytes(color) * n
            return
        seg = self.buf[o:o + n * 3]
        for c in range(3):
            seg[c::3] = seg[c::3].translate(_lut(color[c], alpha))
        self.buf[o:o + n * 3] = seg

    def px(self, x, y, color, alpha):
        if 0 <= x < self.w and 0 <= y < self.h and alpha > 0:
            o = (y * self.w + x) * 3
            for c in range(3):
                self.buf[o + c] = int(self.buf[o + c] * (1 - alpha) + color[c] * alpha + 0.5)

    def blit(self, src, x, y):
        for j in range(src.h):
            yy = y + j
            if not 0 <= yy < self.h:
                continue
            xa, xb = max(x, 0), min(x + src.w, self.w)
            if xb > xa:
                so = (j * src.w + (xa - x)) * 3
                self.buf[(yy * self.w + xa) * 3:(yy * self.w + xb) * 3] = src.buf[so:so + (xb - xa) * 3]

    def blit_rgba(self, src, x, y):
        """Dán ảnh RGBA (w, h, bytearray) có trong suốt lên ảnh này."""
        sw, sh, sb = src
        for j in range(sh):
            yy = y + j
            if not 0 <= yy < self.h:
                continue
            row = sb[j * sw * 4:(j + 1) * sw * 4]
            A = bytes(row[3::4])
            xa, xb = len(A) - len(A.lstrip(b"\0")), len(A.rstrip(b"\0"))
            xa, xb = max(xa, -x, 0), min(xb, self.w - x, sw)
            if xb <= xa:
                continue
            o, n = (yy * self.w + x + xa) * 3, xb - xa
            R, G, B, A = row[0::4][xa:xb], row[1::4][xa:xb], row[2::4][xa:xb], A[xa:xb]
            if A.count(255) == n:
                seg = bytearray(n * 3)
                seg[0::3], seg[1::3], seg[2::3] = R, G, B
            else:
                seg = self.buf[o:o + n * 3]
                for c, S in enumerate((R, G, B)):
                    seg[c::3] = bytes((d * (255 - a) + s * a + 127) // 255 for d, s, a in zip(seg[c::3], S, A))
            self.buf[o:o + n * 3] = seg

    def resized(self, nw, nh):
        """Phóng/thu bằng nearest-neighbor."""
        if (nw, nh) == (self.w, self.h):
            return self
        xmap = [min(self.w - 1, x * self.w // nw) * 3 for x in range(nw)]
        out, cache = bytearray(), {}
        for y in range(nh):
            sy = min(self.h - 1, y * self.h // nh)
            r = cache.get(sy)
            if r is None:
                row = self.buf[sy * self.w * 3:(sy + 1) * self.w * 3]
                r = cache[sy] = b"".join(bytes(row[x:x + 3]) for x in xmap)
                if len(cache) > 2:
                    cache.pop(next(iter(cache)))
            out += r
        return Img(nw, nh, out)

    def rows(self):
        n = self.w * 3
        return [bytes(self.buf[y * n:(y + 1) * n]) for y in range(self.h)]

    def tk_data(self):
        """Chuỗi base64 của PNG - dùng cho tk.PhotoImage(data=...)."""
        import base64
        return base64.b64encode(core._png(self.w, self.h, self.rows(), False)).decode("ascii")

    def save(self, path, fmt="png", compress=True):
        core.save_image(path, self.w, self.h, self.rows(), fmt, compress)


# ---------- cọ tô ----------
def _lerp(a, b, t):
    t = min(1.0, max(0.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t + 0.5) for i in range(3))


class Solid:
    def __init__(self, color):
        self.color = tuple(color)

    def row(self, y, xa, xb):
        return bytes(self.color) * (xb - xa)

    def at(self, x, y):
        return self.color


class VGrad:
    def __init__(self, y1, y2, c1, c2):
        self.y1, self.y2, self.c1, self.c2 = y1, max(y2, y1 + 1), c1, c2

    def at(self, x, y):
        return _lerp(self.c1, self.c2, (y - self.y1) / (self.y2 - self.y1))

    def row(self, y, xa, xb):
        return bytes(self.at(0, y)) * (xb - xa)


class HVGrad:
    """Gradient ngang theo `stops` [(t, màu)], tối dần theo chiều dọc (v1 -> v2)."""

    def __init__(self, x1, x2, stops, y1=0, y2=1, v1=1.0, v2=1.0):
        self.x1, self.y1, self.y2, self.v1, self.v2 = x1, y1, max(y2, y1 + 1), v1, v2
        n = max(x2 - x1, 1)
        self.cols = []
        for i in range(n):
            t = i / max(n - 1, 1)
            for k in range(len(stops) - 1):
                if stops[k][0] <= t <= stops[k + 1][0]:
                    a, b = stops[k], stops[k + 1]
                    self.cols.append(_lerp(a[1], b[1], (t - a[0]) / max(b[0] - a[0], 1e-9)))
                    break
            else:
                self.cols.append(stops[-1][1])
        self.base = b"".join(bytes(c) for c in self.cols)

    def _f(self, y):
        return round(self.v1 + (self.v2 - self.v1) * min(1, max(0, (y - self.y1) / (self.y2 - self.y1))), 3)

    def row(self, y, xa, xb):
        seg = self.base[(xa - self.x1) * 3:(xb - self.x1) * 3]
        f = self._f(y)
        return seg if f == 1.0 else seg.translate(_lut(0, 1 - f))

    def at(self, x, y):
        c = self.cols[min(max(x - self.x1, 0), len(self.cols) - 1)]
        return tuple(int(v * self._f(y)) for v in c)


def rrect(img, x1, y1, x2, y2, r, paint, alpha=1.0, ymin=None, ymax=None, xmin=None, xmax=None):
    """Hình chữ nhật bo góc có khử răng cưa ở mép cong. Hình tròn: r = bán kính, hộp vuông."""
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    ya, yb = max(y1, 0, ymin if ymin is not None else 0), min(y2, img.h, ymax if ymax is not None else img.h)
    for y in range(ya, yb):
        yc = y + 0.5
        dy = y1 + r - yc if yc < y1 + r else (yc - (y2 - r) if yc > y2 - r else 0)
        dx = r - math.sqrt(max(r * r - dy * dy, 0)) if dy > 0 else 0
        xl, xr = x1 + dx, x2 - dx
        il, ir = math.ceil(xl), math.floor(xr)
        lo, hi = max(0, xmin if xmin is not None else 0), min(img.w, xmax if xmax is not None else img.w)
        a, b = max(il, lo), min(ir, hi)
        if b > a:
            if alpha >= 1:
                o = (y * img.w + a) * 3
                img.buf[o:o + (b - a) * 3] = paint.row(y, a, b)
            else:
                img.span(y, a, b, paint.color, alpha)
        cl, cr = il - xl, xr - ir
        if cl > 0.02 and il - 1 >= lo:
            img.px(il - 1, y, paint.at(il - 1, y), cl * alpha)
        if cr > 0.02 and ir < hi:
            img.px(ir, y, paint.at(ir, y), cr * alpha)


# ---------- chữ (GDI) ----------
_TEXT = {}


def _gdi_text(text, px, bold, face):
    import ctypes
    from ctypes import wintypes as wt
    V = ctypes.c_void_p
    gdi = ctypes.windll.gdi32
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [V], V
    gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [ctypes.c_wchar_p]
    gdi.CreateFontW.restype = V
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [V, V], V
    gdi.DeleteObject.argtypes = [V]
    gdi.DeleteDC.argtypes = [V]
    gdi.GetTextExtentPoint32W.argtypes = [V, ctypes.c_wchar_p, ctypes.c_int, ctypes.POINTER(wt.SIZE)]
    gdi.CreateDIBSection.argtypes = [V, V, wt.UINT, ctypes.POINTER(V), V, wt.DWORD]
    gdi.CreateDIBSection.restype = V
    gdi.SetBkColor.argtypes = gdi.SetTextColor.argtypes = [V, wt.DWORD]
    gdi.SetBkMode.argtypes = [V, ctypes.c_int]
    gdi.TextOutW.argtypes = [V, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p, ctypes.c_int]

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]
    hdc = gdi.CreateCompatibleDC(None)
    font = gdi.CreateFontW(-px, 0, 0, 0, 700 if bold else 400, 0, 0, 0, 1, 0, 0, 4, 0, face)
    old = gdi.SelectObject(hdc, font)
    try:
        sz = wt.SIZE()
        gdi.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(sz))
        w, h = sz.cx + 4, sz.cy + 2
        bih = BIH(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = V()
        hbm = gdi.CreateDIBSection(hdc, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
        oldbm = gdi.SelectObject(hdc, hbm)
        try:
            gdi.SetBkMode(hdc, 2)
            gdi.SetBkColor(hdc, 0)
            gdi.SetTextColor(hdc, 0xFFFFFF)
            gdi.TextOutW(hdc, 2, 1, text, len(text))
            gdi.GdiFlush()
            mask = bytes(ctypes.string_at(bits.value, w * h * 4)[1::4])
        finally:
            gdi.SelectObject(hdc, oldbm)
            gdi.DeleteObject(hbm)
    finally:
        gdi.SelectObject(hdc, old)
        gdi.DeleteObject(font)
        gdi.DeleteDC(hdc)
    return w, h, mask


def text_mask(text, px, bold=False, face="Segoe UI"):
    """(rộng, cao, mặt nạ alpha 8-bit) của dòng chữ."""
    key = (text, px, bold, face)
    if key not in _TEXT:
        if sys.platform == "win32":
            _TEXT[key] = _gdi_text(text, px, bold, face)
        else:                                   # nền khác Windows (chỉ để thử): vẽ khối thay chữ
            cw, w, h = int(px * 0.6), int(px * 0.6) * len(text) + 4, px + 4
            m = bytearray(w * h)
            for i, ch in enumerate(text):
                if ch != " ":
                    for y in range(int(px * .2), int(px * .9)):
                        m[(y + 1) * w + 2 + i * cw:(y + 1) * w + 2 + i * cw + cw - 2] = b"\xff" * (cw - 2)
            _TEXT[key] = (w, h, bytes(m))
        if len(_TEXT) > 200:
            _TEXT.pop(next(iter(_TEXT)))
    return _TEXT[key]


def draw_text(img, x, y, text, px, color=(255, 255, 255), bold=False, alpha=1.0):
    w, h, m = text_mask(text, px, bold)
    draw_mask(img, x, y, w, h, m, color, alpha)
    return w, h


def draw_mask(img, x, y, w, h, m, color, alpha=1.0):
    for j in range(h):
        yy = y + j
        if not 0 <= yy < img.h:
            continue
        row = m[j * w:(j + 1) * w]
        if not any(row):
            continue
        for i, a in enumerate(row):
            if a:
                img.px(x + i, yy, color, a / 255 * alpha)


_LOGO = {}


def apple_mask(h):
    """Mặt nạ alpha hình quả táo cắn dở, cao h px (dựng từ các hình tròn, khử răng cưa 3x3)."""
    if h not in _LOGO:
        W = int(h * 0.88)
        lobes = ((-0.145, -0.05, 0.27), (0.145, -0.05, 0.27), (-0.12, 0.17, 0.27), (0.12, 0.17, 0.27))
        ca, sa = math.cos(math.radians(-38)), math.sin(math.radians(-38))

        def inside(x, y):
            for cx, cy, r in lobes:
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    break
            else:
                lx, ly = x - 0.07, y + 0.395                       # lá: elip nghiêng
                u, v = lx * ca + ly * sa, -lx * sa + ly * ca
                return (u / 0.105) ** 2 + (v / 0.042) ** 2 <= 1
            if x * x + (y + 0.355) ** 2 <= 0.085 ** 2:             # khuyết trên đỉnh
                return False
            return (x - 0.335) ** 2 + (y + 0.07) ** 2 > 0.135 ** 2  # vết cắn
        m = bytearray(W * h)
        for j in range(h):
            for i in range(W):
                n = 0
                for b in range(3):
                    for a in range(3):
                        n += inside((i + (a + .5) / 3) / h - W / (2 * h), (j + (b + .5) / 3) / h - 0.48)
                m[j * W + i] = n * 255 // 9
        _LOGO[h] = (W, h, bytes(m))
    return _LOGO[h]


PRINT = (66, 70, 78)


def imprint(img, cx, y, kind, size):
    """In phẳng (không nổi/chìm) lên mặt lưng. kind: 'logo' hoặc chuỗi chữ (font Arial, giống chữ in thật)."""
    w, h, m = apple_mask(size) if kind == "logo" else text_mask(kind, size, False, "Arial")
    draw_mask(img, cx - w // 2, y, w, h, m, PRINT, 0.92)
    return h


# ---------- watermark ----------
def watermark(img, lines):
    """lines: [(chữ, đậm?)] -> khung mờ ở góc dưới trái ảnh."""
    if not lines:
        return img
    px = max(12, img.w // 24)
    while True:
        ms = [text_mask(t, px, b) for t, b in lines]
        pad = max(6, px // 2)
        bw, bh = max(m[0] for m in ms) + 2 * pad, sum(m[1] for m in ms) + 2 * pad
        if bw <= img.w * 0.94 or px <= 8:
            break
        px -= 1
    mg = max(6, px // 2)
    x, y = mg, img.h - mg - bh
    rrect(img, x, y, x + bw, y + bh, pad, Solid((0, 0, 0)), alpha=0.55)
    cy = y + pad
    for (t, b), m in zip(lines, ms):
        draw_text(img, x + pad, cy, t, px, bold=b)
        cy += m[1]
    return img


# ---------- ảnh thật (thư mục frames) ----------
# thư mục asset nằm cạnh app (đóng gói/chia sẻ cùng code)
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
FRAMES = APP_DIR / "asset"
_PHOTO, _SIZED = {}, {}


def _unfilter(raw, h, stride, bpp):
    out, prev, pos = bytearray(h * stride), bytearray(stride), 0
    for y in range(h):
        f, row = raw[pos], bytearray(raw[pos + 1:pos + 1 + stride])
        pos += stride + 1
        if f == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif f == 2:
            row = bytearray((a + b) & 255 for a, b in zip(row, prev))
        elif f == 3:
            for i in range(stride):
                row[i] = (row[i] + (((row[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a, b, c = (row[i - bpp], prev[i], prev[i - bpp]) if i >= bpp else (0, prev[i], 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        out[y * stride:(y + 1) * stride] = row
        prev = row
    return out


def read_png_rgba(path):
    """Đọc PNG 8-bit (không xen kẽ) -> (w, h, bytearray RGBA)."""
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file.")
    pos, idat, plte, trns, hdr = 8, [], b"", b"", None
    while pos < len(d):
        n, t = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + n]
        pos += 12 + n
        if t == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body[:13])
        elif t == b"PLTE":
            plte = body
        elif t == b"tRNS":
            trns = body
        elif t == b"IDAT":
            idat.append(body)
    w, h, bd, ct, _, _, il = hdr
    if bd != 8 or il or ct not in (0, 2, 3, 4, 6):
        raise ValueError("Only 8-bit non-interlaced PNG is supported (RGB/RGBA/palette/grayscale).")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    px = _unfilter(zlib.decompress(b"".join(idat)), h, w * ch, ch)
    n, out = w * h, bytearray(w * h * 4)
    if ct == 6:
        out[:] = px
    elif ct == 2:
        out[0::4], out[1::4], out[2::4], out[3::4] = px[0::3], px[1::3], px[2::3], b"\xff" * n
    elif ct == 0:
        out[0::4] = out[1::4] = out[2::4] = px
        out[3::4] = b"\xff" * n
    elif ct == 4:
        out[0::4] = out[1::4] = out[2::4] = px[0::2]
        out[3::4] = px[1::2]
    else:
        tb = lambda k: bytes(plte[i * 3 + k] if i * 3 + k < len(plte) else 0 for i in range(256))
        px = bytes(px)
        out[0::4], out[1::4], out[2::4] = px.translate(tb(0)), px.translate(tb(1)), px.translate(tb(2))
        out[3::4] = px.translate(bytes(trns[i] if i < len(trns) else 255 for i in range(256)))
    return w, h, out


def _load_photo(hid, view):
    key = (hid, view)
    if key not in _PHOTO:
        p = FRAMES / f"{hid}_{view}.png"
        try:
            _PHOTO[key] = read_png_rgba(p) if p.exists() else None
        except Exception:
            _PHOTO[key] = None
    return _PHOTO[key]


def photos_missing(hid, layout):
    """Danh sách ảnh còn thiếu trong thư mục frames cho layout này."""
    need = {1: ["front"], 2: ["front", "back"], 3: ["front", "side", "back"]}[layout]
    return [f"{hid}_{v}.png" for v in need if _load_photo(hid, v) is None]


def _rgba_resize(src, nw, nh):
    w, h, b = src
    xmap = [min(w - 1, x * w // nw) * 4 for x in range(nw)]
    out, cache = bytearray(), {}
    for y in range(nh):
        sy = min(h - 1, y * h // nh)
        r = cache.get(sy)
        if r is None:
            row = b[sy * w * 4:(sy + 1) * w * 4]
            r = cache[sy] = b"".join(bytes(row[x:x + 4]) for x in xmap)
            if len(cache) > 2:
                cache.pop(next(iter(cache)))
        out += r
    return nw, nh, out


def _sized(hid, view, nh):
    key = (hid, view, nh)
    if key not in _SIZED:
        src = _load_photo(hid, view)
        _SIZED[key] = src if src[1] == nh else _rgba_resize(src, max(1, round(src[0] * nh / src[1])), nh)
        if len(_SIZED) > 24:
            _SIZED.pop(next(iter(_SIZED)))
    return _SIZED[key]


def _find_screen(hid, front):
    """Vùng màn hình trên ảnh mặt trước: file <hid>_front.json {"screen":[x,y,w,h]} hoặc lỗ trong suốt khép kín."""
    jp = FRAMES / f"{hid}_front.json"
    if jp.exists():
        x, y, w, h = json.loads(jp.read_text(encoding="utf-8"))["screen"]
        return (x, y, w, h), False
    w, h, b = front
    st = max(2, min(w, h) // 150)
    gw, gh = w // st, h // st
    A = b[3::4]
    tr = [[A[(gy * st + st // 2) * w + gx * st + st // 2] < 16 for gx in range(gw)] for gy in range(gh)]
    seen = [[False] * gw for _ in range(gh)]
    stack = [(x, y) for x in range(gw) for y in (0, gh - 1)] + [(x, y) for y in range(gh) for x in (0, gw - 1)]
    while stack:
        x, y = stack.pop()
        if 0 <= x < gw and 0 <= y < gh and tr[y][x] and not seen[y][x]:
            seen[y][x] = True
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    cells = [(x, y) for y in range(gh) for x in range(gw) if tr[y][x] and not seen[y][x]]
    if len(cells) < 20:
        return None, False
    x0, y0 = min(c[0] for c in cells) * st, min(c[1] for c in cells) * st
    return (x0, y0, (max(c[0] for c in cells) + 1) * st - x0, (max(c[1] for c in cells) + 1) * st - y0), True


def _photo_postcard(shot, hid, layout, target_h=None):
    names = {1: ["front"], 2: ["front", "back"], 3: ["front", "side", "back"]}[layout]
    if photos_missing(hid, layout):
        return None
    front = _load_photo(hid, "front")
    rect, hole = _find_screen(hid, front)
    if rect is None:
        return None
    base = front[1]
    fh = max(40, round(target_h / 1.24)) if target_h else base
    k = fh / base
    imgs = [_sized(hid, v, fh) for v in names]
    mg, gap = int(fh * 0.12), int(fh * 0.09)
    out = Img(sum(i[0] for i in imgs) + gap * (len(imgs) - 1) + 2 * mg, fh + 2 * mg)
    rrect(out, 0, 0, out.w, out.h, 0, VGrad(0, out.h, (247, 248, 250), (212, 216, 223)))
    x = mg
    for v, ph in zip(names, imgs):
        _shadow(out, x, mg, x + ph[0], mg + fh, int(ph[0] * 0.12), fh / 712)
        if v == "front":
            sx, sy, sw, sh = (int(round(c * k)) for c in rect)
            pad = 2 if hole else 0
            scr = shot.resized(sw + 2 * pad, sh + 2 * pad)
            if hole:
                out.blit(scr, x + sx - pad, mg + sy - pad)
                out.blit_rgba(ph, x, mg)
            else:
                out.blit_rgba(ph, x, mg)
                out.blit(scr, x + sx, mg + sy)
        else:
            out.blit_rgba(ph, x, mg)
        x += ph[0] + gap
    return out


# ---------- postcard ----------
BW, BH, TOP, SIDE, CR = 400, 712, 104, 40, 54      # thân máy / viền màn hình (đơn vị cơ sở; màn hình 320x480)
EDGE, M, G = 54, 90, 80
CHROME = [(0, (122, 126, 134)), (0.07, (233, 236, 240)), (0.30, (192, 196, 203)), (0.55, (246, 247, 249)),
          (0.80, (178, 182, 190)), (0.94, (232, 235, 239)), (1, (112, 116, 124))]
LAYOUTS = {1: "Front", 2: "Front & Back", 3: "Front, Side & Back"}


def layout_size(layout):
    w = {1: BW, 2: 2 * BW + G, 3: 2 * BW + EDGE + 2 * G}[layout]
    return w + 2 * M, BH + 2 * M


def _shadow(img, x1, y1, x2, y2, r, s):
    for k in range(1, 9):
        g = int(round(2.8 * k * s))
        rrect(img, x1 - g, y1 - g + int(14 * s), x2 + g, y2 + g + int(14 * s), r + g, Solid((0, 0, 0)), alpha=0.02)


CHROME_FLAT = [(0, (118, 122, 130)), (0.06, (206, 209, 215)), (0.30, (172, 176, 184)), (0.55, (232, 234, 238)),
               (0.80, (170, 174, 182)), (0.95, (206, 209, 215)), (1, (118, 122, 130))]
CHROME_CURVED = [(0, (66, 70, 78)), (0.05, (158, 162, 170)), (0.16, (228, 231, 236)), (0.5, (247, 248, 250)),
                 (0.84, (214, 217, 223)), (0.95, (150, 154, 162)), (1, (60, 64, 72))]
MATTE = [(0, (30, 30, 33)), (0.5, (58, 58, 63)), (1, (30, 30, 33))]


def _cr(hid):
    return 46 if hid == "n45ap" else 60            # 2G bo tròn hơn 1G


def _front(img, shot, hid, ox, oy, s):
    S = lambda v: int(round(v * s))
    x1, y1, x2, y2, cr = S(ox), S(oy), S(ox + BW), S(oy + BH), _cr(hid)
    _shadow(img, x1, y1, x2, y2, S(cr), s)
    if hid == "n45ap":                                         # 1G: viền đen mờ
        rrect(img, x1, y1, x2, y2, S(cr), HVGrad(x1, x2, MATTE, y1, y2, 1.0, 0.9))
        rrect(img, x1 + S(4), y1 + S(4), x2 - S(4), y2 - S(4), S(cr - 3), VGrad(y1, y2, (16, 16, 19), (7, 7, 9)))
    else:                                                      # 2G: viền chrome quanh máy
        rrect(img, x1, y1, x2, y2, S(cr), HVGrad(x1, x2, CHROME, y1, y2, 1.0, 0.9))
        rrect(img, x1 + S(7), y1 + S(7), x2 - S(7), y2 - S(7), S(cr - 6), VGrad(y1, y2, (24, 25, 29), (8, 8, 10)))
    sx, sy = S(ox + SIDE), S(oy + TOP)
    rrect(img, sx - S(2), sy - S(2), sx + S(322), sy + S(482), 0, Solid((0, 0, 0)))
    img.blit(shot.resized(S(320), S(480)), sx, sy)
    cx, cy = S(ox + BW / 2), S(oy + TOP + 480 + 64)
    r = S(32)
    rrect(img, cx - r, cy - r, cx + r, cy + r, r, VGrad(cy - r, cy + r, (74, 75, 82), (22, 22, 26)))
    r2 = S(29)
    rrect(img, cx - r2, cy - r2, cx + r2, cy + r2, r2, VGrad(cy - r2, cy + r2, (14, 14, 17), (38, 39, 45)))
    q = S(12)
    rrect(img, cx - q, cy - q, cx + q, cy + q, S(4), Solid((206, 209, 216)))
    q = S(9.5)
    rrect(img, cx - q, cy - q, cx + q, cy + q, S(2.5), Solid((20, 20, 23)))


def _back(img, hid, ox, oy, s):
    S = lambda v: int(round(v * s))
    x1, y1, x2, y2, cr = S(ox), S(oy), S(ox + BW), S(oy + BH), _cr(hid)
    _shadow(img, x1, y1, x2, y2, S(cr), s)
    plastic = lambda xa, xb, ya, yb: HVGrad(xa, xb, [(0, (36, 38, 43)), (0.5, (62, 64, 70)), (1, (34, 36, 41))],
                                            ya, yb, 1.0, 0.9)
    if hid == "n45ap":                       # 1G: lưng phẳng, "cửa sổ" ăng-ten hình chữ nhật chiếm góc trên trái
        rrect(img, x1, y1, x2, y2, S(cr), HVGrad(x1, x2, CHROME_FLAT, y1, y2, 1.0, 0.84))
        wx, wy = x1 + S(196), y1 + S(104)
        rrect(img, x1, y1, wx + S(cr), wy + S(cr), S(cr), plastic(x1, wx, y1, wy), xmax=wx, ymax=wy)
    else:                                    # 2G: lưng cong, cửa sổ ăng-ten hình oval
        rrect(img, x1, y1, x2, y2, S(cr), HVGrad(x1, x2, CHROME_CURVED, y1, y2, 1.0, 0.9))
        ox1, oy1, ox2, oy2 = x1 + S(46), y1 + S(40), x1 + S(236), y1 + S(104)
        rrect(img, ox1, oy1, ox2, oy2, (oy2 - oy1) // 2, plastic(ox1, ox2, oy1, oy2))
    cx = S(ox + BW / 2)
    lh = S(84)
    y = y1 + S(BH * 0.36)
    imprint(img, cx, y, "logo", lh)
    imprint(img, cx, y + lh + S(24), "iPod touch", S(27))
    ty = y1 + S(BH * 0.83)
    for line in ("Designed by Apple in California", "Assembled in China",
                 "Model A1213" if hid == "n45ap" else "Model A1288"):
        ty += imprint(img, cx, ty, line, max(7, S(11)))


def _edge(img, hid, ox, oy, s):
    S = lambda v: int(round(v * s))
    x1, y1, x2, y2 = S(ox), S(oy), S(ox + EDGE), S(oy + BH)
    _shadow(img, x1, y1, x2, y2, S(EDGE / 2), s)
    rrect(img, x1, y1, x2, y2, S(EDGE / 2), HVGrad(x1, x2, CHROME, y1, y2, 1.0, 0.92))
    rrect(img, x1 + S(5), y1 + S(16), x1 + S(14), y2 - S(16), S(4), Solid((10, 10, 12)))      # mép kính mặt trước
    if hid != "n45ap":                                        # nút âm lượng của 2G
        for k in range(2):
            ya = y1 + S(150 + k * 44)
            rrect(img, x2 - S(14), ya, x2 - S(5), ya + S(34), S(4), Solid((70, 73, 80)))


def make_postcard(shot, hid, layout, s=2.0, preview_h=None):
    """shot: Img 320x480 (hoặc bội số). Ưu tiên ảnh thật trong thư mục frames; không có thì dùng khung tự vẽ.
    preview_h: chiều cao đích (px) cho ảnh xem trước."""
    real = _photo_postcard(shot, hid, layout, preview_h)
    if real is not None:
        return real
    lw, lh = layout_size(layout)
    if preview_h:
        s = preview_h / lh
    out = Img(max(1, int(round(lw * s))), max(1, int(round(lh * s))))
    rrect(out, 0, 0, out.w, out.h, 0, VGrad(0, out.h, (247, 248, 250), (212, 216, 223)))
    x = M
    _front(out, shot, hid, x, M, s)
    if layout == 2:
        _back(out, hid, x + BW + G, M, s)
    elif layout == 3:
        _edge(out, hid, x + BW + G, M, s)
        _back(out, hid, x + BW + G + EDGE + G, M, s)
    return out
