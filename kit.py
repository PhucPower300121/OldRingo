"""Bộ vẽ UI kiểu iPad đời đầu (iPhone OS 3.2/4): nav bar xanh xám, bảng grouped
trên nền sọc, hàng chọn màu xanh, nút bóng, công tắc ON/OFF. Chỉ phụ thuộc tkinter."""
import math
import tkinter as tk

UI_DELAY = [0]        # ms giữ highlight sau khi bấm (app đặt từ cài đặt)

S = 1.0
FONT = "Helvetica"
BG1, BG2 = "#c5ccd4", "#d0d6dc"          # nền sọc
BORDER, SEP = "#ababab", "#ababab"
SEL1, SEL2 = "#4a97f5", "#0b5bd6"        # hàng được chọn
NAV1, NAV2 = "#b4c1d4", "#6b83a3"        # thanh tiêu đề: gradient mượt một mạch như hàng được chọn
NAV_BTN1, NAV_BTN2 = "#8ba4ca", "#476597"  # nút trên thanh tiêu đề
NAV_BTN1P, NAV_BTN2P = "#5b76a1", "#2a4472"   # ... khi đang bấm
DETAIL, SECTION = "#385487", "#4c566c"
GOOD, BAD, MUTED = "#2f7d32", "#c0392b", "#7f8791"


def init_scale(root):
    global S
    S = max(1.0, root.winfo_fpixels("1i") / 96)


def u(n):
    return int(round(n * S))


def font(size, bold=False):
    return (FONT, -u(size), "bold" if bold else "normal")


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def lerp(c1, c2, t):
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _inset(r, k):
    """Độ lùi của dòng k (tính từ mép) trên góc bo bán kính r. Dùng chung cho MỌI hình bo
    để viền và phần ruột luôn khớp nhau."""
    d = r - (k + 0.5)
    return int(round(r - math.sqrt(max(r * r - d * d, 0))))


def rrect(cv, x1, y1, x2, y2, r, fill, outline=None, tags=""):
    if outline:
        rrect(cv, x1, y1, x2, y2, r, outline, None, tags)
        x1, y1, x2, y2, r = x1 + 1, y1 + 1, x2 - 1, y2 - 1, max(r - 1, 0)
    r = max(0, min(r, (y2 - y1) // 2, (x2 - x1) // 2))
    for k in range(r):
        e = _inset(r, k)
        cv.create_line(x1 + e, y1 + k, x2 - e, y1 + k, fill=fill, tags=tags)
        cv.create_line(x1 + e, y2 - 1 - k, x2 - e, y2 - 1 - k, fill=fill, tags=tags)
    cv.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", tags=tags)


def vgrad(cv, x1, y1, x2, y2, c1, c2, tag, rad=0, tl=False, tr=False, bl=False, br=False):
    """Gradient dọc, bo góc từng góc bằng cùng công thức với rrect."""
    h = y2 - y1
    rad = min(rad, h // 2) if rad else 0
    for k in range(h):
        t = k / max(h - 1, 1)
        il = ir = 0
        if rad:
            if k < rad:
                e = _inset(rad, k); il, ir = (e if tl else 0), (e if tr else 0)
            elif k >= h - rad:
                e = _inset(rad, h - 1 - k); il, ir = (e if bl else 0), (e if br else 0)
        cv.create_line(x1 + il, y1 + k, x2 - ir, y1 + k, fill=lerp(c1, c2, t), tags=tag)


def shadow_text(cv, x, y, text, fnt, fill="white", shade="#ffffff", dy=1, **kw):
    cv.create_text(x, y + dy, text=text, font=fnt, fill=shade, **kw)
    return cv.create_text(x, y, text=text, font=fnt, fill=fill, **kw)


# ======== Bốn kiểu nút riêng biệt (mỗi kiểu một hàm + bảng màu riêng, không dùng chung để khỏi xung đột) ========
# 1) popup_button: popup giữa màn hình và nút Cancel của menu đáy (viền mảnh)
#    (viền ngoài, viền sáng | nửa trên: 2 màu | nửa dưới: 2 màu | màu chữ, bóng chữ)
_POPUP = {"alert": ("#05070d", "#7e8696", "#9096a3", "#5d6574", "#363c49", "#474e5c", "#e9e9e9", "#0f1218"),
          "alertp": ("#030409", "#575d69", "#5f6470", "#3c4250", "#20242d", "#2c313c", "#d0d0d0", "#0b0d12"),
          "ralert": ("#2a0805", "#c98a84", "#ef8a7e", "#d9503f", "#bd2a1b", "#d4493a", "white", "#6e130a"),
          "dralert": ("#1c0503", "#8a5550", "#a95a52", "#8a2c21", "#6a1109", "#82200f", "white", "#3a0803")}
POPUP_PRESS = {"alert": "alertp", "ralert": "dralert"}          # đang bấm: chỉ tối đi

# 2) viewer_button: nút trong trình xem ảnh
#    (nửa trên: màu đầu, cuối | nửa dưới: màu đầu, cuối | vạch sáng mép trên | chữ, bóng chữ, hướng bóng)
_VIEWER = {"black": ("#727272", "#2f2f2f", "#151515", "#0d0d0d", "#aaaaaa", "white", "#000000", -1),
           "white": ("#dcdcdc", "#c8c8c8", "#c8c8c8", "#b2b2b2", "#e7e7e7", "#111111", "#ffffff", 1),
           "blue": ("#6aa0ee", "#4a85e0", "#4a85e0", "#2a64d0", "#c4d9fa", "white", "#14357f", -1),
           "red": ("#e2685c", "#d44f43", "#d44f43", "#bd3a2f", "#f5c8c2", "white", "#6e130a", -1),
           "dred": ("#a35850", "#8d3a2f", "#8d3a2f", "#76261c", "#cf9b95", "white", "#3a0803", -1)}
_VIEWER["dark"] = _VIEWER["black"]
PRESS = {"black": "blue", "dark": "blue", "white": "blue", "blue": "blue", "red": "dred"}   # trắng/đen -> xanh, đỏ chỉ tối đi

# 3) sheet_button: nút trắng/đỏ của menu đáy (bảng màu riêng, màu lạ -> trắng)
_SHEET = {"white": ("#dcdcdc", "#c8c8c8", "#c8c8c8", "#b2b2b2", "#e7e7e7", "#111111", "#ffffff", 1),
          "blue": ("#6aa0ee", "#4a85e0", "#4a85e0", "#2a64d0", "#c4d9fa", "white", "#14357f", -1),
          "red": ("#e2685c", "#d44f43", "#d44f43", "#bd3a2f", "#f5c8c2", "white", "#6e130a", -1),
          "dred": ("#a35850", "#8d3a2f", "#8d3a2f", "#76261c", "#cf9b95", "white", "#3a0803", -1)}
SHEET_PRESS = {"white": "blue", "red": "dred", "blue": "blue", "alert": "alertp"}

# 4) run_button: nút Run / Setup trong danh sách profile (kiểu cũ: bóng chia nửa, viền mảnh cùng tông)
#    (viền | nửa trên: 2 màu | nửa dưới: 2 màu | chữ, bóng chữ)
_RUN = {"runblue": ("#1b3f93", "#6fa5ee", "#3f7fe0", "#1d5ed0", "#3578e0", "white", "#1b3f93"),
        "runred": ("#7a140b", "#f0877b", "#df4f3f", "#c4281a", "#dd4b3b", "white", "#7a140b")}


def _ring_button(cv, x1, y1, x2, y2, text, pal, tag):
    """Nút viền kép: viền mảnh sáng ngoài cùng (dưới tối -> trên sáng), viền đen (trên đen -> dưới xám tối),
    thân hai nửa trên/dưới và vạch sáng ở mép trên. Màu đen viền không được trùng _TC (màu trong suốt của Modal).
    QUY ĐỊNH: viền đen kép này là ĐỘC QUYỀN của trình xem ảnh (viewer_button) và menu đáy (sheet_button);
    mọi nơi khác (Run/Setup, thùng rác trang Mirrors, popup...) không được dùng."""
    t1, t2, b1, b2, hl, tc, ts, dy = pal
    r = u(9)
    mid = (y1 + y2) // 2
    vgrad(cv, x1, y1, x2, mid, "#4c4c4c", "#272727", tag, rad=r, tl=True, tr=True)       # viền mảnh ngoài cùng:
    vgrad(cv, x1, mid, x2, y2, "#272727", "#707070", tag, rad=r, bl=True, br=True)       # nửa dưới sáng dần tới #707070
    vgrad(cv, x1 + 1, y1 + 1, x2 - 1, y2 - 1, "#020202", "#212121", tag, rad=r - 1, tl=True, tr=True, bl=True, br=True)
    e = 4                                                                                  # viền đen dày 3px
    vgrad(cv, x1 + e, y1 + e, x2 - e, mid, t1, t2, tag, rad=r - e, tl=True, tr=True)
    vgrad(cv, x1 + e, mid, x2 - e, y2 - e, b1, b2, tag, rad=r - e, bl=True, br=True)
    ei = _inset(r - e, 0)
    cv.create_line(x1 + e + ei, y1 + e, x2 - e - ei, y1 + e, fill=hl, tags=tag)
    shadow_text(cv, (x1 + x2) // 2, (y1 + y2) // 2, text, font(14, True), fill=tc, shade=ts, dy=dy, tags=tag)


def viewer_button(cv, x1, y1, x2, y2, text, color="black", tag="btn"):
    _ring_button(cv, x1, y1, x2, y2, text, _VIEWER.get(color, _VIEWER["black"]), tag)


def sheet_button(cv, x1, y1, x2, y2, text, color="white", tag="btn"):
    if color in _POPUP:                                   # Cancel của menu đáy: kiểu popup
        return popup_button(cv, x1, y1, x2, y2, text, color, tag)
    _ring_button(cv, x1, y1, x2, y2, text, _SHEET.get(color, _SHEET["white"]), tag)


def popup_button(cv, x1, y1, x2, y2, text, color="alert", tag="btn"):
    pal = _POPUP.get(color, _POPUP["alert"])
    r, e = u(9), 2
    rrect(cv, x1, y1, x2, y2, r, pal[0], tags=tag)
    rrect(cv, x1 + 1, y1 + 1, x2 - 1, y2 - 1, r - 1, pal[1], tags=tag)
    mid = (y1 + y2) // 2
    vgrad(cv, x1 + e, y1 + e, x2 - e, mid, pal[2], pal[3], tag, rad=r - e, tl=True, tr=True)
    vgrad(cv, x1 + e, mid, x2 - e, y2 - e, pal[4], pal[5], tag, rad=r - e, bl=True, br=True)
    shadow_text(cv, (x1 + x2) // 2, (y1 + y2) // 2, text, font(14, True), fill=pal[6], shade=pal[7], tags=tag)


def run_button(cv, x1, y1, x2, y2, text, color="runblue", tag="btn"):
    pal = _RUN.get(color, _RUN["runblue"])
    r = u(8)
    rrect(cv, x1, y1, x2, y2, r, pal[0], tags=tag)
    mid = (y1 + y2) // 2
    vgrad(cv, x1 + 1, y1 + 1, x2 - 1, mid, pal[1], pal[2], tag, rad=r - 1, tl=True, tr=True)
    vgrad(cv, x1 + 1, mid, x2 - 1, y2 - 1, pal[3], pal[4], tag, rad=r - 1, bl=True, br=True)
    shadow_text(cv, (x1 + x2) // 2, (y1 + y2) // 2, text, font(14, True), fill=pal[5], shade=pal[6], tags=tag)


def glossy_button(cv, x1, y1, x2, y2, text, color="blue", tag="btn"):
    """Tương thích mã cũ: chọn hàm vẽ theo tên màu."""
    fn = popup_button if color in _POPUP else run_button if color in _RUN else viewer_button
    fn(cv, x1, y1, x2, y2, text, color, tag)


def pin_button(cv, x1, y1, x2, y2, on, tag):
    """Đinh ghim kiểu bản đồ iOS 3: đầu tròn bóng + kim; đỏ = đã ghim, xám = chưa."""
    cx = (x1 + x2) // 2
    r = u(9)
    by = y1 + r + u(1)                                   # tâm đầu đinh
    tip = y2 - u(2)
    shades = (["#6e0808", "#b81414", "#e04040", "#ff8c8c"] if on else ["#4d525b", "#7d838d", "#aeb3bc", "#e9ecf0"])
    cv.create_oval(cx - u(1), tip - u(2), cx + u(9), tip + u(1), fill="#9aa1ad", outline="", tags=tag)   # bóng
    cv.create_line(cx + 1, by, cx + 1, tip, fill="#6b717c", width=max(2, u(2)), tags=tag)             # kim
    cv.create_line(cx, by, cx, tip, fill="#e3e6eb", width=max(1, u(1)), tags=tag)
    for n, col in enumerate(shades):                     # đầu tròn: các lớp nhỏ dần, lệch lên trái để tạo độ bóng
        rr = r - n * u(2) if n < 3 else u(2)
        off = n * u(1.5)
        cv.create_oval(cx - rr - off + (n and u(1)), by - rr - off, cx + rr - off + (n and u(1)), by + rr - off,
                       fill=col, outline="", tags=tag)


def bar_button(cv, x1, y1, x2, y2, tag="n", back=False, pressed=False):
    """Nút trên nav bar. back=True: mũi tên chỉ trái kiểu iOS 3."""
    h = y2 - y1
    tip = h // 2 if back else 0
    r = u(5)

    def draw(xa, ya, xb, yb, colorfn, off):
        hh = yb - ya
        for k in range(hh):
            frac = abs(k + 0.5 - hh / 2) / (hh / 2)
            left = xa + int(round(tip * frac)) + (off if back else 0)
            e = _inset(r, k) if k < r else (_inset(r, hh - 1 - k) if k >= hh - r else 0)
            cv.create_line(left + (0 if back else e), ya + k, xb - e, ya + k,
                           fill=colorfn(k / max(hh - 1, 1)), tags=tag)
    draw(x1, y1, x2, y2, lambda t: "#2d3b57", 0)
    c1, c2 = (NAV_BTN1P, NAV_BTN2P) if pressed else (NAV_BTN1, NAV_BTN2)      # đang bấm: tối đi
    draw(x1 + 1, y1 + 1, x2 - 1, y2 - 1, lambda t: lerp(c1, c2, t), 1)       # gradient mượt, không chia đôi
    return tip


ICON_COLS = {"profile": ("#d4b07a", "#8a5a2b"), "gallery": ("#9bd6f7", "#2a7fd0"), "system": ("#6a9be0", "#1a3f8c"),
             "howto": ("#fcee96", "#ecc93f"), "settings": ("#f7b25a", "#d9731a"), "general": ("#c4c9d1", "#6b717b"),
             "diag": ("#f27a6e", "#b3170f"), "shot": ("#d2d5db", "#5b616b"), "touch": ("#585d68", "#17191d"),
             "keyboard": ("#b6bcc5", "#5a616c"), "about": ("#74b6f8", "#1b5fc9")}


def _draw_icon_vec(cv, kind, x, y, size, tag):
    """Icon vẽ bằng code (dự phòng khi thiếu icons_data.py)."""
    s = size
    cols = ICON_COLS[kind]
    r = u(7)
    rrect(cv, x, y, x + s, y + s, r, "#3b414c", tags=tag)
    vgrad(cv, x + 1, y + 1, x + s - 1, y + s // 2, lerp(cols[0], "#ffffff", .30), lerp(cols[0], "#ffffff", .05), tag,
          rad=r - 1, tl=True, tr=True)
    vgrad(cv, x + 1, y + s // 2, x + s - 1, y + s - 1, cols[1], lerp(cols[1], cols[0], .45), tag,
          rad=r - 1, bl=True, br=True)
    cx, cy = x + s / 2, y + s / 2
    w, lw = "white", max(2, u(2))

    def P(*pts):                                           # toạ độ tương đối -> tuyệt đối
        return [v for px, py in pts for v in (x + s * px, y + s * py)]

    def box(x1, y1, x2, y2, rad, fill):
        rrect(cv, x + s * x1, y + s * y1, x + s * x2, y + s * y2, max(1, int(s * rad)), fill, tags=tag)

    if kind == "profile":                                  # sổ địa chỉ: gáy tối, hình người, mép trang
        cv.create_rectangle(x + s * .10, y + s * .06, x + s * .17, y + s * .94, fill="#5b3a1a", outline="", tags=tag)
        for yy in (.22, .40, .58):
            cv.create_rectangle(x + s * .90, y + s * yy, x + s * .97, y + s * (yy + .12), fill="#f3e2c0", outline="", tags=tag)
        cv.create_oval(cx - s * .12 + s * .02, cy - s * .27, cx + s * .12 + s * .02, cy - s * .03, fill="#f3e2c0", outline="", tags=tag)
        cv.create_arc(cx - s * .26 + s * .02, cy + s * .02, cx + s * .30 + s * .02, cy + s * .56, start=0, extent=180,
                      fill="#f3e2c0", outline="", tags=tag)
    elif kind == "gallery":                                # hoa hướng dương
        for i in range(10):
            a = i * math.pi / 5
            px, py = cx + math.cos(a) * s * .26, cy + math.sin(a) * s * .26
            cv.create_oval(px - s * .09, py - s * .09, px + s * .09, py + s * .09, fill="#ffd21f", outline="#e0a300", tags=tag)
        cv.create_oval(cx - s * .15, cy - s * .15, cx + s * .15, cy + s * .15, fill="#4a2a10", outline="#2a1608", tags=tag)
        cv.create_oval(cx - s * .08, cy - s * .08, cx + s * .02, cy + s * .02, fill="#7a4a22", outline="", tags=tag)
    elif kind == "system":                                 # biểu đồ giá
        for yy in (.30, .50, .70):
            cv.create_line(x + s * .12, y + s * yy, x + s * .88, y + s * yy, fill="#9bbdee", tags=tag)
        cv.create_line(*P((.12, .70), (.30, .52), (.44, .60), (.62, .32), (.76, .42), (.90, .22)),
                       fill=w, width=lw, joinstyle="round", capstyle="round", tags=tag)
    elif kind == "howto":                                  # tập ghi chú vàng
        cv.create_rectangle(x + s * .06, y + s * .06, x + s * .94, y + s * .20, fill="#c99a2e", outline="", tags=tag)
        for yy in (.38, .54, .70, .86):
            cv.create_line(x + s * .12, y + s * yy, x + s * .88, y + s * yy, fill="#c7a847", tags=tag)
        cv.create_line(x + s * .26, y + s * .20, x + s * .26, y + s * .94, fill="#d9776b", tags=tag)
    elif kind == "settings":                               # thanh trượt
        for i, kx in enumerate((.35, .62, .45)):
            yy = y + s * (.3 + i * .2)
            cv.create_line(x + s * .2, yy, x + s * .8, yy, fill=w, width=lw, tags=tag)
            cv.create_oval(x + s * kx - u(3), yy - u(3), x + s * kx + u(3), yy + u(3), fill=w, outline=w, tags=tag)
    elif kind == "general":                                # bánh răng kim loại
        for i in range(8):
            a = i * math.pi / 4
            cv.create_line(cx + math.cos(a) * s * .20, cy + math.sin(a) * s * .20,
                           cx + math.cos(a) * s * .34, cy + math.sin(a) * s * .34, fill="#f4f5f7", width=max(2, u(4)), tags=tag)
        cv.create_oval(cx - s * .25, cy - s * .25, cx + s * .25, cy + s * .25, fill="#f4f5f7", outline="#d6d9de", tags=tag)
        cv.create_oval(cx - s * .11, cy - s * .11, cx + s * .11, cy + s * .11, fill=cols[1], outline="#4a4f58", tags=tag)
    elif kind == "diag":                                   # nhịp tim
        cv.create_line(*P((.10, .52), (.32, .52), (.42, .28), (.54, .76), (.64, .42), (.70, .52), (.90, .52)),
                       fill=w, width=max(2, u(3)), joinstyle="round", capstyle="round", tags=tag)
    elif kind == "shot":                                   # máy ảnh
        box(.34, .22, .62, .36, .05, "#e8eaee")
        box(.12, .30, .88, .78, .10, "#f2f3f5")
        cv.create_oval(cx - s * .19, cy + s * .02 - s * .19 + s * .02, cx + s * .19, cy + s * .02 + s * .19 + s * .02,
                       fill="#3a3f48", outline="#23262c", tags=tag)
        cv.create_oval(cx - s * .10, cy + s * .04 - s * .10, cx + s * .10, cy + s * .04 + s * .10,
                       fill="#7fa6e0", outline="", tags=tag)
        cv.create_oval(cx - s * .06, cy - s * .05, cx - s * .01, cy, fill="#d8e6fa", outline="", tags=tag)
    elif kind == "touch":                                  # nút tròn Assistive Touch
        r1, r2 = s * .31, s * .18
        cv.create_oval(cx - r1, cy - r1, cx + r1, cy + r1, fill="#6b6b72", outline="#9a9aa2", width=max(1, u(1)), tags=tag)
        cv.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, fill="#f2f2f4", outline="", tags=tag)
    elif kind == "keyboard":                               # bàn phím
        kw, g = .15, .05
        for row, n in enumerate((4, 4)):
            x0 = .5 - (n * kw + (n - 1) * g) / 2
            for i in range(n):
                box(x0 + i * (kw + g), .26 + row * .20, x0 + i * (kw + g) + kw, .26 + row * .20 + .14, .03, w)
        box(.24, .66, .76, .80, .03, w)
    else:                                                  # about: chữ i trong vòng tròn
        cv.create_oval(cx - s * .31, cy - s * .31, cx + s * .31, cy + s * .31, outline=w, width=lw, tags=tag)
        cv.create_oval(cx - s * .04, cy - s * .20, cx + s * .04, cy - s * .12, fill=w, outline=w, tags=tag)
        cv.create_line(cx, cy - s * .06, cx, cy + s * .20, fill=w, width=max(2, u(3)), capstyle="round", tags=tag)


try:
    import icons_data
except ImportError:
    icons_data = None
_ICON_CACHE = {}


def _weights(n_src, n_dst):
    """Trọng số resize 1 chiều: thu nhỏ = trung bình theo diện tích, phóng to = nội suy tuyến tính."""
    out = []
    for d in range(n_dst):
        if n_dst < n_src:
            a, b = d * n_src / n_dst, (d + 1) * n_src / n_dst
            i0, i1 = int(a), min(int(math.ceil(b)), n_src)
            ws = [(i, min(b, i + 1) - max(a, i)) for i in range(i0, i1)]
        else:
            c = (d + .5) * n_src / n_dst - .5
            i = int(math.floor(c))
            f = c - i
            ws = [(min(max(i, 0), n_src - 1), 1 - f), (min(max(i + 1, 0), n_src - 1), f)]
        t = sum(w for _, w in ws)
        out.append([(i, w / t) for i, w in ws if w > 0])
    return out


def _icon_png(kind, s):
    """RGBA 57x57 (nén sẵn) -> PNG kích thước s x s, giữ nguyên độ trong suốt ở góc bo."""
    import base64, struct, zlib
    N = icons_data.N
    raw = zlib.decompress(base64.b64decode(icons_data.ICONS[kind]))
    px = [[(raw[(y * N + x) * 4] * raw[(y * N + x) * 4 + 3] / 255, raw[(y * N + x) * 4 + 1] * raw[(y * N + x) * 4 + 3] / 255,
            raw[(y * N + x) * 4 + 2] * raw[(y * N + x) * 4 + 3] / 255, raw[(y * N + x) * 4 + 3]) for x in range(N)]
          for y in range(N)]                                             # nhân sẵn alpha để trộn đúng viền
    wt = _weights(N, s)
    tmp = [[tuple(sum(px[y][i][c] * w for i, w in wt[x]) for c in range(4)) for x in range(s)] for y in range(N)]
    rows = []
    for y in range(s):
        line = bytearray([0])
        for x in range(s):
            r, g, b, a = (sum(tmp[j][x][c] * w for j, w in wt[y]) for c in range(4))
            if a > 0.5:
                r, g, b = r * 255 / a, g * 255 / a, b * 255 / a
            line += bytes(min(255, max(0, int(round(v)))) for v in (r, g, b, a))
        rows.append(bytes(line))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", s, s, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def draw_icon(cv, kind, x, y, size, tag):
    """Icon iOS gốc (cắt từ iPod touch). Thiếu icons_data.py thì vẽ bằng code."""
    if icons_data is None or kind not in icons_data.ICONS:
        return _draw_icon_vec(cv, kind, x, y, size, tag)
    key = (kind, size)
    if key not in _ICON_CACHE:
        import base64
        _ICON_CACHE[key] = tk.PhotoImage(data=base64.b64encode(_icon_png(kind, size)).decode())
    cv.create_image(x, y, image=_ICON_CACHE[key], anchor="nw", tags=tag)


def draw_ipod(cv, x, y, tag):
    w, h = u(36), u(62)
    rrect(cv, x, y, x + w, y + h, u(6), "#2b2e34", outline="#0e0f12", tags=tag)
    vgrad(cv, x + u(4), y + u(13), x + w - u(4), y + u(49), "#8fb2e0", "#3f6cae", tag)
    cv.create_rectangle(x + u(4), y + u(13), x + w - u(4), y + u(49), outline="#0e0f12", tags=tag)
    cv.create_line(x + w / 2 - u(5), y + u(6), x + w / 2 + u(5), y + u(6), fill="#9aa0a8", width=max(1, u(2)),
                   capstyle="round", tags=tag)
    cv.create_oval(x + w / 2 - u(4), y + u(52), x + w / 2 + u(4), y + u(60), fill="#17191d",
                   outline="#8a8f98", tags=tag)


def spinner(cv, cx, cy, r, phase, tag="spin", col=(0x6d, 0x6d, 0x72)):
    """Vòng tải kiểu iOS: 12 vạch, vạch đầu đậm nhất và mờ dần phía sau."""
    for i in range(12):
        a = math.radians(i * 30 - 90)
        fade = 1 - ((phase - i) % 12) / 12 * 0.85
        c = "#%02x%02x%02x" % tuple(int(255 - (255 - v) * fade) for v in col)
        ca, sa = math.cos(a), math.sin(a)
        cv.create_line(cx + ca * r * .5, cy + sa * r * .5, cx + ca * r, cy + sa * r, fill=c,
                       width=max(2, u(2)), capstyle="round", tags=tag)


class NavBar(tk.Canvas):
    """Thanh tiêu đề xanh xám kiểu UINavigationBar: nút Back trái, tiêu đề giữa, nút phải (tuỳ chọn)."""

    def __init__(self, master, title_fn, back_fn, right_fn, on_back, on_right):
        super().__init__(master, height=u(44), highlightthickness=0, bg="#6d84a3")
        self.title_fn, self.back_fn, self.right_fn = title_fn, back_fn, right_fn
        self.on_back, self.on_right = on_back, on_right
        self.back_box = self.right_box = None
        self.dim, self.modal = False, None
        self.pressed, self._wait = None, False
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<ButtonPress-1>", self._click)

    def set_dim(self, on):
        self.dim = on                 # chỉ chặn tương tác; lớp tối do Modal vẽ trong cửa sổ phủ riêng

    def _click(self, e):
        if self.dim:
            if self.modal:
                self.modal.press(self, e)
            return
        if self._wait:
            return
        for name, box, fn in (("back", self.back_box, self.on_back), ("right", self.right_box, self.on_right)):
            if box and box[0] <= e.x <= box[2] and box[1] <= e.y <= box[3]:
                self.pressed, self._wait = name, True          # tối nút đi, chạy sau UI delay
                self.draw()
                self.after(UI_DELAY[0], lambda: self._fire(fn))
                return

    def _fire(self, fn):
        self._wait, self.pressed = False, None
        fn()
        try:
            self.draw()
        except tk.TclError:
            pass

    def draw(self):
        from tkinter import font as tkfont
        self.delete("all")
        self.back_box = self.right_box = None
        w, h = self.winfo_width(), u(44)
        vgrad(self, 0, 0, w, h, NAV1, NAV2, "n")
        self.create_line(0, 0, w, 0, fill="#d9e0ea")
        self.create_line(0, h - 1, w, h - 1, fill="#2e3745")
        shadow_text(self, w // 2, h // 2, self.title_fn(), font(20, True), shade="#33415a", dy=-1)
        label = self.back_fn()
        if label:
            f = tkfont.Font(self, font=font(13, True))
            y1, y2 = u(7), h - u(7)
            tip = (y2 - y1) // 2
            x1 = u(8)
            x2 = x1 + tip + f.measure(label) + u(20)
            bar_button(self, x1, y1, x2, y2, back=True, pressed=self.pressed == "back")
            shadow_text(self, x1 + tip + u(4) + (x2 - x1 - tip - u(4)) // 2, (y1 + y2) // 2, label,
                        font(13, True), shade="#2d3b57", dy=-1)
            self.back_box = (x1, y1, x2, y2)
        txt = self.right_fn()
        if txt:
            f = tkfont.Font(self, font=font(13, True))
            bw = f.measure(txt) + u(28)
            x2 = w - u(10)
            bar_button(self, x2 - bw, u(7), x2, h - u(7), pressed=self.pressed == "right")
            shadow_text(self, x2 - bw // 2, h // 2, txt, font(13, True), shade="#2d3b57", dy=-1)
            self.right_box = (x2 - bw, u(7), x2, h - u(7))


class Table(tk.Canvas):
    """Canvas vẽ trang kiểu bảng grouped. build(table) gọi các hàm section/group/footer..."""
    plain = None                                   # màu nền đặc thay cho nền kẻ sọc (build đặt)
    _wait = False                                  # đang chờ UI delay sau cú bấm

    def __init__(self, master, build, inset=None, edge=False, **kw):
        super().__init__(master, bg=BG1, highlightthickness=0, yscrollincrement=u(20), **kw)
        self.build, self.fixed_inset, self.edge = build, inset, edge
        self.modal = None
        self.wins, self.rows, self.n, self.pressed, self.gen = [], {}, 0, None, 0
        self.dim = False                           # bị Modal làm tối
        self.spins, self.phase = [], 0             # các vòng tải đang hiện + pha hoạt ảnh
        self.y = self.W = self.H = self.x1 = self.x2 = 0
        self.bind("<Configure>", lambda e: self.render())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", lambda e: self.yview_scroll(-int(e.delta / 120) * 3, "units")
                  if self.y > self.H and not self.dim else None)

    def spin(self, cx, cy, r):
        self.spins.append((cx, cy, r))
        spinner(self, cx, cy, r, self.phase)

    def tick(self, phase):
        """Chỉ vẽ lại các vòng tải (không dựng lại cả trang)."""
        self.phase = phase
        if not self.spins or self.dim:
            return
        self.delete("spin")
        for cx, cy, r in self.spins:
            spinner(self, cx, cy, r, phase)

    # ---- vòng vẽ ----
    def render(self):
        for w in self.wins:
            w.destroy()
        self.wins, self.rows, self.n, self.pressed, self.spins = [], {}, 0, None, []
        self.gen += 1
        self.delete("all")
        self.W, self.H = self.winfo_width(), self.winfo_height()
        self.x1 = self.fixed_inset if self.fixed_inset is not None else max(u(24), (self.W - u(700)) // 2)
        self.x2 = self.W - self.x1
        self.y = u(14)
        self.build(self)
        self.y += u(20)
        top = max(self.y, self.H)
        self.configure(bg=self.plain or BG1)
        if not self.plain:                             # plain = màu nền đặc (không kẻ sọc), vd Gallery
            for x in range(0, self.W, u(4)):
                self.create_line(x + 1, 0, x + 1, top, fill=BG2, width=u(2), tags="bg")
            self.tag_lower("bg")
        if self.edge:                                  # đường kẻ phân cách sidebar / nội dung
            self.create_line(self.W - 1, 0, self.W - 1, top, fill="#2b2f36")
        self.configure(scrollregion=(0, 0, self.W, top))

    # ---- thành phần ----
    def section(self, title):
        self.y += u(8)
        shadow_text(self, self.x1 + u(18), self.y, title, font(16, True), fill=SECTION,
                    anchor="nw")
        self.y += u(26)

    def footer(self, text):
        cx = (self.x1 + self.x2) // 2
        wd = self.x2 - self.x1 - u(30)
        self.create_text(cx, self.y + 1, text=text, font=font(14), fill="white", width=wd,
                         justify="center", anchor="n")
        i = self.create_text(cx, self.y, text=text, font=font(14), fill=SECTION, width=wd,
                             justify="center", anchor="n")
        bb = self.bbox(i)
        self.y = bb[3] + u(10)

    def flat_text(self, text, size=14, bold=True, gap=12, maxw=None):
        """Đoạn chữ phẳng ngay trên nền sọc (kiểu trang Legal của iOS): chữ xám xanh, bóng trắng bên dưới.
        maxw: giới hạn bề rộng cột chữ (cột được căn giữa trang)."""
        wd = self.x2 - self.x1 - u(32)
        if maxw:
            wd = min(wd, maxw)
        x = (self.x1 + self.x2) // 2 - wd // 2
        f = font(size, bold)
        self.create_text(x, self.y + 1, text=text, font=f, fill="white", width=wd, anchor="nw")
        i = self.create_text(x, self.y, text=text, font=f, fill=SECTION, width=wd, anchor="nw")
        self.y = self.bbox(i)[3] + u(gap)

    def picture(self, photo, h):
        """Ảnh căn giữa trang (cao h px), chiếm chỗ theo chiều dọc."""
        self.create_image((self.x1 + self.x2) // 2, self.y, image=photo, anchor="n")
        self.y += h + u(14)

    def segmented(self, options, selected, cb):
        sw, sh = u(120), u(32)
        total = sw * len(options)
        x0 = (self.x1 + self.x2) // 2 - total // 2
        y0 = self.y + u(4)
        self.n += 1
        sid = self.n
        rrect(self, x0, y0, x0 + total, y0 + sh, u(6), "#3f5273")
        for i, name in enumerate(options):
            xa, xb = x0 + i * sw + (1 if i == 0 else 0), x0 + (i + 1) * sw - (1 if i == len(options) - 1 else 0)
            sel = name == selected
            tag = f"seg{sid}_{i}"
            vgrad(self, xa, y0 + 1, xb, y0 + sh - 1,
                  "#46689c" if sel else "#f6f7f9", "#6f8fc0" if sel else "#c4ccd7", tag,
                  rad=u(5), tl=i == 0, bl=i == 0, tr=i == len(options) - 1, br=i == len(options) - 1)
            if i:
                self.create_line(x0 + i * sw, y0, x0 + i * sw, y0 + sh, fill="#3f5273", tags=tag)
            self.create_text(x0 + i * sw + sw // 2, y0 + sh // 2, text=name, font=font(14, True),
                             fill="white" if sel else "#2c3e5c", tags=tag)
            self.tag_bind(tag, "<ButtonPress-1>", lambda e, n=name: cb(n))
        self.y = y0 + sh + u(10)

    def note(self, text, size=14):
        """Thẻ trắng chứa đoạn chữ tự xuống dòng (cao theo nội dung)."""
        wd = self.x2 - self.x1 - u(40)
        tmp = self.create_text(0, 0, text=text, font=font(size), width=wd, anchor="nw")
        bb = self.bbox(tmp); self.delete(tmp)
        self.group([{"kind": "note", "h": bb[3] - bb[1] + u(24), "text": text, "size": size, "wd": wd}])

    def group(self, rows):
        x1, x2, y0 = self.x1, self.x2, self.y
        hs = [r.get("h", u(44)) for r in rows]
        H = sum(hs) + len(rows) - 1
        rrect(self, x1, y0, x2, y0 + H, u(9), "white", outline=BORDER)
        y = y0
        for i, row in enumerate(rows):
            self.n += 1
            tag = f"r{self.n}"
            geom = (x1, y, x2, y + hs[i], i == 0, i == len(rows) - 1)
            self.rows[tag] = (row, geom)
            self._draw_row(tag, row, geom, row.get("selected", False))
            y += hs[i]
            if i < len(rows) - 1:
                self.create_line(x1 + 1, y, x2 - 1, y, fill=SEP)
                y += 1
        self.y = y0 + H + u(10)

    # ---- vẽ từng hàng ----
    def _draw_row(self, tag, row, geom, hl):
        x1, y1, x2, y2, first, last = geom
        cy, pad = (y1 + y2) // 2, u(16)
        if hl:
            vgrad(self, x1 + 1, y1 + (1 if first else 0), x2 - 1, y2 - (1 if last else 0), SEL1, SEL2, tag,
                  rad=u(9) - 1, tl=first, tr=first, bl=last, br=last)
        fg = "white" if hl else "#000000"
        k = row["kind"]
        if k == "value":
            self.create_text(x1 + pad, cy, text=row["label"], font=font(16, True), fill=fg, anchor="w", tags=tag)
            if row.get("spin"):
                self.spin(x2 - pad - u(9), cy, u(9))
            else:
                self.create_text(x2 - pad, cy, text=row.get("detail", ""), font=font(16),
                                 fill="white" if hl else row.get("color", DETAIL), anchor="e", tags=tag)
        elif k == "slider":
            stops, var, n = row["stops"], row["var"], len(row["stops"])
            cur = min(range(n), key=lambda i: abs(stops[i] - var.get()))
            tx1, tx2, ty, kr = x1 + pad + u(12), x2 - pad - u(12), y2 - u(24), u(12)
            fmt = row.get("fmt")
            lab = (lambda i: fmt(stops[i])) if fmt else (lambda i: "Unlimited (0 MB)" if stops[i] == 0 else f"{stops[i]} MB")
            self.create_text(x1 + pad, y1 + u(22), text=row["label"], font=font(16, True), fill=fg, anchor="w", tags=tag)
            vt = self.create_text(x2 - pad, y1 + u(22), text=lab(cur), font=font(15), fill=DETAIL, anchor="e", tags=tag)
            hit, at = f"sl{self.n}", lambda i: tx1 + (tx2 - tx1) * i / (n - 1)
            self.create_rectangle(x1 + pad, ty - u(16), x2 - pad, ty + u(16), fill="white", outline="", tags=(tag, hit))
            self.create_line(tx1, ty, tx2, ty, fill="#c7ccd4", width=u(6), capstyle="round", tags=(tag, hit))
            for i in range(n):
                self.create_oval(at(i) - u(2), ty - u(2), at(i) + u(2), ty + u(2), fill="#9aa0a8", outline="", tags=(tag, hit))
            fl = self.create_line(tx1, ty, at(cur), ty, fill="#2f77e3", width=u(6), capstyle="round", tags=(tag, hit))
            kn = self.create_oval(at(cur) - kr, ty - kr, at(cur) + kr, ty + kr, fill="#f6f6f6", outline="#6c747f",
                                  width=max(1, u(1)), tags=(tag, hit))

            def move(e):
                i = round(min(max((e.x - tx1) / (tx2 - tx1), 0), 1) * (n - 1))
                var.set(stops[i])
                self.coords(fl, tx1, ty, at(i), ty)
                self.coords(kn, at(i) - kr, ty - kr, at(i) + kr, ty + kr)
                self.itemconfigure(vt, text=lab(i))
            self.tag_bind(hit, "<ButtonPress-1>", lambda e: (stamp(e), move(e)))
            self.tag_bind(hit, "<B1-Motion>", move)
            self.tag_bind(hit, "<ButtonRelease-1>", lambda e: row.get("on_change") and row["on_change"]())
        elif k == "note":
            self.create_text(x1 + pad, y1 + u(11), text=row["text"], font=font(row.get("size", 14)), fill="#222",
                             width=row["wd"], anchor="nw", justify="left", tags=tag)
        elif k == "action":
            col = MUTED if row.get("disabled") else ("white" if hl else row.get("color", DETAIL))
            if row.get("spin"):
                self.spin((x1 + x2) // 2, cy, u(9))
            else:
                self.create_text((x1 + x2) // 2, cy, text=row["label"], font=font(16, True), fill=col, tags=tag)
        elif k == "nav":
            ic = row.get("icon")
            if ic:
                draw_icon(self, ic, x1 + u(12), cy - u(15), u(30), tag)
            self.create_text(x1 + (u(54) if ic else pad), cy, text=row["label"], font=font(17, True), fill=fg,
                             anchor="w", tags=tag)
            self.create_text(x2 - pad, cy, text="\u203a", font=font(24),
                             fill="white" if hl else "#b0b6bf", anchor="e", tags=tag)
            if row.get("detail"):
                self.create_text(x2 - pad - u(18), cy, text=row["detail"], font=font(15),
                                 fill="white" if hl else row.get("color", DETAIL), anchor="e", tags=tag)
        elif k == "profile":
            draw_ipod(self, x1 + u(18), cy - u(31), tag)
            self.create_text(x1 + u(72), cy - u(12), text=row["title"], font=font(19, True), fill=fg,
                             anchor="w", tags=tag)
            self.create_text(x1 + u(72), cy + u(12), text=row["sub"], font=font(14),
                             fill="white" if hl else "#6d6d72", anchor="w", tags=tag)
            bw = u(84)
            run_button(self, x2 - pad - bw, cy - u(17), x2 - pad, cy + u(17),
                          row["button"], row.get("bcolor", "runblue"), tag)
            self._pin(row, x2 - pad - bw - u(10), cy, tag)
        elif k == "mrow":
            on = row.get("on", True)
            rr = u(12)
            cx0, ea = x1 + pad + rr, f"el{self.n}a"
            col, edge = ("#d9302a", "#8f1713") if on else ("#3aa040", "#236f28")        # bật: đỏ "-" (tắt), tắt: xanh "+" (bật)
            self.create_oval(cx0 - rr, cy - rr, cx0 + rr, cy + rr, fill=col, outline=edge, width=max(1, u(1)), tags=(tag, ea))
            self.create_oval(cx0 - rr + u(4), cy - rr + u(2), cx0 + rr - u(4), cy - u(1), fill=lerp(col, "#ffffff", .35),
                             outline="", tags=(tag, ea))
            bw2, bh2 = u(7), max(2, u(2))
            self.create_rectangle(cx0 - bw2, cy - bh2, cx0 + bw2, cy + bh2, fill="white", outline="", tags=(tag, ea))
            if not on:
                self.create_rectangle(cx0 - bh2, cy - bw2, cx0 + bh2, cy + bw2, fill="white", outline="", tags=(tag, ea))
            self.tag_bind(ea, "<ButtonPress-1>", lambda ev, f=row["toggle"]: (stamp(ev), f()))
            tw, th, eb = u(42), u(28), f"el{self.n}b"
            bx1, by1 = x2 - pad - tw, cy - th // 2
            run_button(self, bx1, by1, bx1 + tw, by1 + th, "", "runred", (tag, eb))     # không dùng viền đen kép
            tx, ty = bx1 + tw // 2, cy + u(1)
            w2 = u(8)
            self.create_line(tx - w2, ty - u(6), tx + w2, ty - u(6), fill="white", width=max(2, u(2)), tags=(tag, eb))
            self.create_line(tx - u(3), ty - u(8), tx + u(3), ty - u(8), fill="white", width=max(2, u(2)), tags=(tag, eb))
            self.create_polygon(tx - w2 + u(2), ty - u(3), tx + w2 - u(2), ty - u(3), tx + w2 - u(3), ty + u(8),
                                tx - w2 + u(3), ty + u(8), fill="", outline="white", width=max(1, u(1)), tags=(tag, eb))
            for dx in (-u(2), u(2)):
                self.create_line(tx + dx, ty - u(1), tx + dx, ty + u(5), fill="white", tags=(tag, eb))
            self.tag_bind(eb, "<ButtonPress-1>", lambda ev, f=row["trash"]: (stamp(ev), f()))
            lx = x1 + pad + 2 * rr + u(10)
            self.create_text(lx, cy - (u(9) if row.get("sub") else 0), text=row["label"], font=font(16, True),
                             fill=fg if on else MUTED, anchor="w", tags=tag)
            if row.get("sub"):
                self.create_text(lx, cy + u(11), text=row["sub"], font=font(13), fill="#6d6d72", anchor="w", tags=tag)
            if row.get("detail"):
                self.create_text(bx1 - u(10), cy, text=row["detail"], font=font(14), fill=row.get("color", DETAIL),
                                 anchor="e", tags=tag)
        elif k == "item":
            self.create_text(x1 + pad, cy - (u(9) if row.get("sub") else 0), text=row["label"], font=font(16, True),
                             fill=fg, anchor="w", tags=tag)
            if row.get("sub"):
                self.create_text(x1 + pad, cy + u(11), text=row["sub"], font=font(13),
                                 fill="white" if hl else "#6d6d72", anchor="w", tags=tag)
            right = x2 - pad
            if row.get("menu"):
                bw, bh = u(44), u(28)
                bx1, by1 = right - bw, cy - bh // 2
                et = f"el{self.n}"
                rrect(self, bx1, by1, right, by1 + bh, u(6), "#eef0f4", outline="#8e949c", tags=et)
                for dx in (-u(10), 0, u(10)):
                    self.create_oval(bx1 + bw // 2 + dx - u(2), cy - u(2), bx1 + bw // 2 + dx + u(3), cy + u(3),
                                     fill="#4c566c", outline="#4c566c", tags=et)
                self.tag_bind(et, "<ButtonPress-1>", lambda ev, f=row["menu"]: (stamp(ev), f()))
                right = bx1 - u(14)
            if row.get("spin"):
                self.spin(right - u(9), cy, u(9))
            else:
                self.create_text(right, cy, text=row.get("detail", ""), font=font(15),
                                 fill="white" if hl else row.get("color", DETAIL), anchor="e", tags=tag)
        elif k == "choice":
            self.create_text(x1 + pad, cy - (u(9) if row.get("sub") else 0), text=row["label"], font=font(16, True),
                             fill=fg, anchor="w", tags=tag)
            if row.get("sub"):
                self.create_text(x1 + pad, cy + u(11), text=row["sub"], font=font(13),
                                 fill="white" if hl else "#6d6d72", anchor="w", tags=tag)
            if row.get("checked"):
                cx0 = x2 - pad - u(20)
                self.create_line(cx0, cy, cx0 + u(7), cy + u(8), cx0 + u(20), cy - u(9),
                                 fill="white" if hl else DETAIL, width=max(3, u(3)), tags=tag)
        elif k == "prow":
            draw_ipod(self, x1 + u(18), cy - u(31), tag)
            self.create_text(x1 + u(72), cy - u(11), text=row["title"], font=font(17, True), fill=fg, anchor="w", tags=tag)
            self.create_text(x1 + u(72), cy + u(11), text=row["sub"], font=font(13),
                             fill="white" if hl else "#6d6d72", anchor="w", tags=tag)
            dt = self.create_text(x2 - pad - u(18), cy, text=row.get("detail", ""), font=font(14),
                                  fill="white" if hl else row.get("color", DETAIL), anchor="e", tags=tag)
            self.create_text(x2 - pad, cy, text="\u203a", font=font(24), fill="white" if hl else "#b0b6bf",
                             anchor="e", tags=tag)
            self._pin(row, self.bbox(dt)[0] - u(10), cy, tag)
        elif k == "switch":
            self.create_text(x1 + pad, cy, text=row["label"], font=font(16, True), fill=fg, anchor="w", tags=tag)
            self._switch(x2 - pad - u(94), cy - u(13), row["var"], row.get("on_change"))
        elif k == "entry":
            self.create_text(x1 + pad, cy, text=row["label"], font=font(15, True), fill=fg, anchor="w", tags=tag)
            e = tk.Entry(self, textvariable=row["var"], relief="flat", bd=0, bg="white", fg=DETAIL,
                         highlightthickness=0, font=font(14))
            self.wins.append(e)
            self.create_window(x1 + u(100), cy, window=e, anchor="w",
                               width=x2 - x1 - u(100) - (u(92) if row.get("browse") else u(16)))
            if row.get("browse"):
                t2 = self.create_text(x2 - pad, cy, text="Choose", font=font(14, True), fill=DETAIL, anchor="e")
                self.tag_bind(t2, "<ButtonPress-1>", lambda ev, f=row["browse"]: f())
        elif k == "text":
            t = tk.Text(self, font=("Consolas", -u(12)), bg="white", fg="#222", relief="flat", bd=0,
                        wrap="char", highlightthickness=0, padx=u(4), pady=u(4))
            t.tag_configure("sep", font=("Consolas", -u(12), "bold"), foreground=DETAIL, background="#e6eaf1",
                            spacing1=u(8), spacing3=u(4))
            marks = dict(row.get("marks", ()))            # {chỉ số dòng: tên mark} - điểm chèn log realtime
            for i, line in enumerate(row["lines"]):
                if i in marks:
                    t.mark_set(marks[i], "end-1c"); t.mark_gravity(marks[i], "left")
                t.insert("end", line + "\n", ("sep",) if line.startswith("\u2501\u2501") else ())
            if len(row["lines"]) in marks:
                t.mark_set(marks[len(row["lines"])], "end-1c"); t.mark_gravity(marks[len(row["lines"])], "left")
            t.see("end"); t.configure(state="disabled")
            sb = tk.Scrollbar(self, orient="vertical", command=t.yview)
            t.configure(yscrollcommand=sb.set)
            self.wins += [t, sb]
            row["register"](t)
            sw = u(16)
            self.create_window(x1 + u(8), y1 + u(6), window=t, anchor="nw",
                               width=x2 - x1 - u(16) - sw, height=y2 - y1 - u(12))
            self.create_window(x2 - u(8), y1 + u(6), window=sb, anchor="ne", width=sw, height=y2 - y1 - u(12))

    def _switch(self, x, y, var, on_change):
        w, h = u(94), u(27)
        on = var.get()
        tag = f"sw{self.n}"
        rrect(self, x, y, x + w, y + h, h // 2, "#2f77e3" if on else "#f7f7f7", outline="#6c747f", tags=tag)
        self.create_text(x + (u(27) if on else w - u(27)), y + h // 2, text="ON" if on else "OFF",
                         font=font(13, True), fill="white" if on else "#7c828b", tags=tag)
        kx = x + w - h if on else x
        self.create_oval(kx, y, kx + h, y + h, fill="#f1f1f1", outline="#6c747f", tags=tag)

        def toggle(_e):
            var.set(not var.get())
            if on_change:
                on_change()
            self.render()
        self.tag_bind(tag, "<ButtonPress-1>", toggle)

    def set_dim(self, on):
        self.dim = on                 # chỉ chặn tương tác; lớp tối do Modal vẽ trong cửa sổ phủ riêng

    def _pin(self, row, right, cy, rtag):
        """Vẽ nút ghim (nếu hàng có pin_cb) ngay trái toạ độ `right`; bấm vào nút không kích hoạt cả hàng."""
        if row.get("pin_cb") is None:
            return
        box = (right - u(34), cy - u(14), right, cy + u(14))
        row["_pin"] = box
        et = f"el{self.n}"
        pin_button(self, *box, row.get("pin"), (et, rtag))
        self.tag_bind(et, "<ButtonPress-1>", lambda ev, f=row["pin_cb"]: f())

    # ---- tương tác hàng có cb ----
    def _hit(self, e):
        cy = self.canvasy(e.y)
        for tag, (row, g) in self.rows.items():
            if row.get("cb") and not row.get("disabled") and g[0] <= e.x <= g[2] and g[1] <= cy <= g[3]:
                pb = row.get("_pin")
                if pb and pb[0] <= e.x <= pb[2] and pb[1] <= cy <= pb[3]:
                    continue
                return tag
        return None

    def _press(self, e):
        if self.dim:
            if self.modal:
                self.modal.press(self, e)
            return
        if self._wait:
            return
        tag = self._hit(e)
        if tag and not self.rows[tag][0].get("selected"):
            self.pressed = tag
            row, g = self.rows[tag]
            self.delete(tag)
            self._draw_row(tag, row, g, True)

    def _release(self, e):
        if self.dim:
            return
        tag, self.pressed = self.pressed, None
        if not tag:
            return
        row, g = self.rows[tag]
        inside = self._hit(e) == tag
        if not inside:
            self.delete(tag)
            self._draw_row(tag, row, g, False)
        else:
            gen = self.gen
            if UI_DELAY[0] > 0:          # giữ highlight thêm một lúc rồi mới chạy cb
                self._wait = True
                self.after(UI_DELAY[0], lambda: self._fire(tag, row, g, gen))
            else:
                self._fire(tag, row, g, gen)

    def _fire(self, tag, row, g, gen):
        self._wait = False
        row["cb"]()
        if gen == self.gen and tag in self.rows:     # cb không vẽ lại trang -> bỏ highlight
            self.delete(tag)
            self._draw_row(tag, row, g, False)


# ================= Modal: menu 3 chấm / hộp xác nhận =================
# Vẽ NGAY TRONG cửa sổ chính (không phải cửa sổ riêng): các Canvas (header, sidebar, nội dung) cùng bị
# phủ tối, và hộp thoại được vẽ lên từng Canvas mà nó chồng lên -> luôn nằm chính giữa cửa sổ, liền mạch.
_ev = [None]


def stamp(ev):
    """Gọi trong handler của item: ghi lại thời điểm cú bấm để Modal không tự đóng bởi chính cú bấm đó."""
    _ev[0] = ev.time


def _wrap(fnt, text, width):
    out = []
    for para in text.split("\n"):
        line = ""
        for w in para.split(" "):
            t = (line + " " + w).strip()
            if fnt.measure(t) <= width or not line:
                line = t
            else:
                out.append(line); line = w
        out.append(line)
    return "\n".join(out)


def _no_activate(w):
    """Cửa sổ phủ không giành focus của cửa sổ chính (Windows)."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.GetParent.argtypes, u32.GetParent.restype = [ctypes.c_void_p], ctypes.c_void_p
        u32.GetWindowLongW.argtypes, u32.GetWindowLongW.restype = [ctypes.c_void_p, ctypes.c_int], ctypes.c_long
        u32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        w.update_idletasks()
        for h in (w.winfo_id(), u32.GetParent(w.winfo_id())):
            if h:
                u32.SetWindowLongW(h, -20, u32.GetWindowLongW(h, -20) | 0x08000000)   # WS_EX_NOACTIVATE
    except Exception:
        pass


_TC = "#ff00fe"      # màu trong suốt để bo góc hộp thoại (không được trùng màu nào trong UI)


_GLOSS_CACHE = {}


def _gloss(cv, x1, y1, x2, h, bulge, r, c1, c2, tag):
    """Dải sáng ở đầu hộp thoại, mép dưới cong lồi xuống giữa (UIAlertView iOS 3). Vẽ thành ảnh PNG có alpha
    để mép cong và góc bo được khử răng cưa."""
    import base64, struct, zlib
    w = x2 - x1
    key = (w, h, bulge, r, c1, c2)
    if key not in _GLOSS_CACHE:
        total = h + bulge
        cx, hw, ss = w / 2, w / 2, 4
        rows = []
        for py in range(total):
            col = lerp(c1, c2, min((py + .5) / total, 1))
            rgb = bytes(int(col[i:i + 2], 16) for i in (1, 3, 5))
            line = bytearray([0])
            for px in range(w):
                if r < py < h - 1 and r <= px < w - r:
                    cov = 16                                        # vùng trong: phủ kín
                else:
                    cov = 0
                    for j in range(ss):
                        y = py + (j + .5) / ss
                        for i in range(ss):
                            x = px + (i + .5) / ss
                            if y >= h:                              # dưới đường biên hai bên: chỉ còn phần giữa
                                s = (x - cx) / hw
                                ok = y <= h + bulge * (1 - s * s)
                            else:
                                ok = True
                            if ok and y < r:                        # góc trên bo tròn
                                if x < r:
                                    ok = (x - r) ** 2 + (y - r) ** 2 <= r * r
                                elif x > w - r:
                                    ok = (x - (w - r)) ** 2 + (y - r) ** 2 <= r * r
                            cov += ok
                line += rgb + bytes([cov * 255 // 16])
            rows.append(bytes(line))

        def chunk(t, d):
            c = t + d
            return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, total, 8, 6, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
        _GLOSS_CACHE[key] = tk.PhotoImage(data=base64.b64encode(png).decode())
    cv.create_image(x1, y1, image=_GLOSS_CACHE[key], anchor="nw", tags=tag)


class Modal:
    """Hộp thoại: vẽ sẵn trong 2 cửa sổ phủ (lớp tối bán trong suốt + hộp), rồi hiện cùng lúc -> không bị
    vẽ lần lượt từng vùng."""

    def __init__(self, root, dims):
        self.root, self.dims = root, dims
        self.spec = None
        self.dimw = self.boxw = None
        for d in dims:
            d.modal = self
        root.bind("<Escape>", lambda e: self._dismiss(), add="+")
        root.bind("<Configure>", lambda e: self._place() if e.widget is root and self.spec else None, add="+")

    def active(self):
        return self.spec is not None

    def show(self, title, buttons, message="", row=False, cancel=None, bottom=False):
        """buttons: [(label, màu, callback|None)]. row=True: các nút xếp ngang (nút cuối nằm bên phải).
        cancel: nếu có thì bấm ra ngoài / Esc sẽ đóng rồi gọi nó; None = chỉ đóng bằng nút."""
        from tkinter import font as tkfont
        if self.spec is not None:
            self.close()
        pad, gap, bh = u(16), u(10), u(46)
        W = max(u(260), min(u(400), self.root.winfo_width() - u(60)))
        tw = W - 2 * pad
        ft, fm = tkfont.Font(self.root, font=font(16, True)), tkfont.Font(self.root, font=font(14))
        msg = _wrap(fm, message, tw) if message else ""
        th = ft.metrics("linespace")
        mh = (msg.count("\n") + 1) * fm.metrics("linespace") if msg else 0
        block = bh if row else len(buttons) * bh + (len(buttons) - 1) * gap
        H = pad + th + (u(10) + mh if msg else 0) + u(16) + block + pad
        if bottom:                                   # menu đáy: cùng style nút trong trình xem ảnh
            eff = ["red" if c == "red" else "alert" if c in ("dark", "black") else "white" for _, c, _ in buttons]
        else:                                        # popup giữa: mọi nút cùng một kiểu, chỉ nút xoá là đỏ
            eff = ["ralert" if c == "red" else "alert" for _, c, _ in buttons]
        self.spec = dict(title=title, msg=msg, buttons=buttons, row=row, cancel=cancel, eff=eff,
                         W=W, H=H, bottom=bottom, pad=pad, gap=gap, bh=bh, th=th, tw=tw, block=block)
        for d in self.dims:
            d.set_dim(True)
        r = self.root
        # tạo + vẽ xong khi cửa sổ còn ẩn
        self.dimw = tk.Toplevel(r, bg="black")
        self.dimw.withdraw()
        self.dimw.overrideredirect(True)
        self.dimw.transient(r)
        self.dimw.attributes("-alpha", 0.5)
        self.dimw.bind("<ButtonPress-1>", lambda e: self._dismiss())
        self.boxw = tk.Toplevel(r, bg=_TC)
        self.boxw.withdraw()
        self.boxw.overrideredirect(True)
        self.boxw.transient(r)
        self.boxw.attributes("-transparentcolor", _TC)
        cv = tk.Canvas(self.boxw, width=W, height=H, bg=_TC, highlightthickness=0)
        cv.pack()
        cv.bind("<ButtonPress-1>", lambda e, c=cv: self.press(c, e))
        self.paint(cv)
        _no_activate(self.dimw)
        _no_activate(self.boxw)
        self._place()
        self.dimw.deiconify()                      # hiện cả hai cùng lúc
        self.boxw.deiconify()
        self.boxw.lift()
        self.boxw.update_idletasks()

    def _place(self):
        r, sp = self.root, self.spec
        if not sp or not self.dimw:
            return
        rx, ry, rw, rh = r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height()
        W, H = sp["W"], sp["H"]
        wy = rh - H - u(16) if sp["bottom"] else (rh - H) // 2          # menu: sát đáy; hộp thoại: giữa
        self.dimw.geometry(f"{rw}x{rh}+{rx}+{ry}")
        self.boxw.geometry(f"{W}x{H}+{rx + (rw - W) // 2}+{ry + wy}")

    def paint(self, cv):
        """Vẽ hộp thoại lên canvas `cv` (toạ độ cục bộ của cửa sổ hộp)."""
        sp = self.spec
        W, H, pad = sp["W"], sp["H"], sp["pad"]
        r, e = u(12), u(2)
        rrect(cv, 0, 0, W - 1, H - 1, r, "#9aa4b8", tags="modal")           # popup giữa và menu đáy dùng chung một kiểu
        rrect(cv, e, e, W - 1 - e, H - 1 - e, r - e, "#0b1838", tags="modal")
        gh, bulge, fade = u(24), u(7), u(26)
        vgrad(cv, e, e, W - 1 - e, e + gh + fade, "#2a3352", "#0b1838", "modal", rad=r - e, tl=True, tr=True)
        _gloss(cv, e, e, W - 1 - e, gh, bulge, r - e, "#8089a3", "#4a5470", "modal")      # gloss cong, khử răng cưa
        shadow_text(cv, W // 2, pad, sp["title"], font(16, True), fill="#ececec", shade="#050c1e", tags="modal",
                    anchor="n")
        if sp["msg"]:
            cv.create_text(W // 2, pad + sp["th"] + u(10), text=sp["msg"], anchor="n", font=font(14),
                           fill="#e4e4e4", justify="center", tags="modal")
        by, n = H - pad - sp["block"], len(sp["buttons"])
        if sp["row"]:
            bw, bx = (sp["tw"] - sp["gap"] * (n - 1)) // n, pad
            for i, (label, _c, _cb) in enumerate(sp["buttons"]):
                self._btn(cv, bx, by, bx + bw, by + sp["bh"], label, sp["eff"][i], f"mb{i}")
                sp.setdefault("geo", {})[i] = (bx, by, bx + bw, by + sp["bh"])
                bx += bw + sp["gap"]
        else:
            for i, (label, _c, _cb) in enumerate(sp["buttons"]):
                self._btn(cv, pad, by, W - pad, by + sp["bh"], label, sp["eff"][i], f"mb{i}")
                sp.setdefault("geo", {})[i] = (pad, by, W - pad, by + sp["bh"])
                by += sp["bh"] + sp["gap"]

    def press(self, cv, e):
        if self.spec is None:
            return
        for it in cv.find_overlapping(e.x, e.y, e.x, e.y):
            for t in cv.gettags(it):
                if t.startswith("mb"):
                    if getattr(self, "_busy", False):
                        return
                    i = int(t[2:])
                    label, _col, cb = self.spec["buttons"][i]
                    d = UI_DELAY[0]
                    if d > 0:                                    # đổi màu nút báo đã bấm, giữ hộp thoại thêm một lúc
                        self._busy = True
                        x1, y1, x2, y2 = self.spec["geo"][i]
                        cv.delete(t)
                        eff = self.spec["eff"][i]
                        self._btn(cv, x1, y1, x2, y2, label,
                                  (SHEET_PRESS if self.spec["bottom"] else POPUP_PRESS).get(eff, eff), t)
                        spec = self.spec
                        self.root.after(d, lambda: self._finish(spec, cb))
                    else:
                        self.close()
                        if cb:
                            cb()
                    return

    def _btn(self, cv, x1, y1, x2, y2, label, color, tag):
        """Menu đáy dùng sheet_button, popup giữa dùng popup_button (hai hàm vẽ độc lập)."""
        (sheet_button if self.spec["bottom"] else popup_button)(cv, x1, y1, x2, y2, label, color, tag)

    def _finish(self, spec, cb):
        self._busy = False
        if self.spec is not spec:            # hộp thoại đã bị đóng/thay trong lúc chờ
            return
        self.close()
        if cb:
            cb()

    def _dismiss(self):
        if getattr(self, "_busy", False):
            return
        if self.spec is not None and self.spec["cancel"] is not None:
            cb = self.spec["cancel"]
            self.close()
            cb()

    def close(self):
        if self.spec is None:
            return
        self.spec = None
        for w in (self.boxw, self.dimw):
            try:
                w and w.destroy()
            except tk.TclError:
                pass
        self.dimw = self.boxw = None
        for d in self.dims:
            d.set_dim(False)
