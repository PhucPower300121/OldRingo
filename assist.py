"""Nút nổi kiểu AssistiveTouch cho cửa sổ QEMU: kéo để di chuyển, bấm để mở bảng Home / Power / Screenshot."""
import ctypes, queue, threading, time, tkinter as tk
from ctypes import wintypes

import core
from kit import font, rrect, u

user32 = ctypes.windll.user32
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

TC = "#010101"                       # màu trong suốt (để bo góc)
KEYS = {"home": (0x48, 0x23), "power": (0x50, 0x19)}   # (virtual-key, scancode) của phím H và P


def find_vm_window():
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(h, buf, 128)
            if buf.value.startswith("QEMU"):
                found.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def send_key(name, count=1, gap=0.12):
    """Đưa cửa sổ VM lên trước rồi nhấn phím vào đó."""
    hwnd = find_vm_window()
    if not hwnd:
        raise RuntimeError("VM window not found.")
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    vk, sc = KEYS[name]
    core.alog(f"assistive touch: sending '{name}' key x{count} to the VM window", "INFO")
    for i in range(count):
        user32.keybd_event(vk, sc, 0, 0)
        time.sleep(0.06)
        user32.keybd_event(vk, sc, 2, 0)
        if i < count - 1:
            time.sleep(gap)


class Assist:
    IDLE = 0.3                                   # độ mờ khi không hover

    def __init__(self, app, proc, port, on_shot, meta=None):
        self.app, self.proc, self.port, self.on_shot, self.meta = app, proc, port, on_shot, meta
        self.msgs = queue.Queue()
        self.panel = self.toast_w = None
        self.moved = self.snapped = self.dragged = self.off = False
        self.taps, self.tap_job = 0, None
        self.n = 0
        self.s = u(58)
        sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
        self.btn = self._top()
        self.cv = tk.Canvas(self.btn, width=self.s, height=self.s, bg=TC, highlightthickness=0)
        self.cv.pack()
        self.draw_btn()
        self.btn.attributes("-alpha", self.IDLE)
        self.cv.bind("<Enter>", lambda e: self.btn.attributes("-alpha", 0.95))
        self.cv.bind("<Leave>", lambda e: None if self.dragged else self.btn.attributes("-alpha", self.IDLE))
        self.place(sw - self.s - u(40), sh // 2)
        for ev, fn in (("<ButtonPress-1>", self._down), ("<B1-Motion>", self._move), ("<ButtonRelease-1>", self._up)):
            self.cv.bind(ev, fn)
        self.tick()

    # ---------- cửa sổ ----------
    def _top(self):
        w = tk.Toplevel(self.app, bg=TC)
        w.overrideredirect(True)
        w.attributes("-topmost", True, "-transparentcolor", TC, "-alpha", 0.92)
        return w

    def draw_btn(self, flash=False):
        s, cv = self.s, self.cv
        cv.delete("all")
        rrect(cv, 0, 0, s, s, u(15), "#ffffff" if flash else "#1c1c1f", outline="#47474c")
        c, r1, r2 = s // 2, int(s * .31), int(s * .23)
        cv.create_oval(c - r1, c - r1, c + r1, c + r1, fill="#6b6b72", outline="#9a9aa2", width=max(1, u(1)))
        cv.create_oval(c - r2, c - r2, c + r2, c + r2, fill="#f2f2f4", outline="")

    def vrange(self):
        g = user32.GetSystemMetrics
        return g(76), g(77), g(76) + g(78), g(77) + g(79)

    def place(self, x, y):
        x0, y0, x1, y1 = self.vrange()
        x = min(max(x, x0), x1 - self.s)
        y = min(max(y, y0), y1 - self.s)
        self.x, self.y = x, y
        self.btn.geometry(f"+{x}+{y}")

    # ---------- kéo / bấm ----------
    def _down(self, e):
        self.d0, self.w0, self.dragged = (e.x_root, e.y_root), (self.x, self.y), False

    def _move(self, e):
        dx, dy = e.x_root - self.d0[0], e.y_root - self.d0[1]
        if abs(dx) + abs(dy) > u(5):
            if not self.dragged:
                self.close_panel()
            self.dragged = self.moved = True
        if self.dragged:
            self.place(self.w0[0] + dx, self.w0[1] + dy)

    def _up(self, e):
        if self.dragged:
            if not (0 <= e.x < self.s and 0 <= e.y < self.s):
                self.btn.attributes("-alpha", self.IDLE)
            return
        self.taps += 1
        if self.tap_job:
            self.app.after_cancel(self.tap_job)
        top = 3 if core.cfg_get("at_triple", "none") != "none" else 2 if core.cfg_get("at_double", "none") != "none" else 1
        if self.taps >= top:
            self._fire()
        else:
            self.tap_job = self.app.after(280, self._fire)      # chờ xem có bấm thêm không

    def _fire(self):
        n, self.taps, self.tap_job = self.taps, 0, None
        act = "menu" if n == 1 else core.cfg_get("at_double" if n == 2 else "at_triple", "none")
        core.alog(f"assistive touch: {n} tap(s) -> {act}", "DEBUG")
        if act == "menu":
            self.open_panel()
        elif act in ("home", "power"):
            self.do_key(act)
        elif act == "screenshot":
            self.do_shot()
        elif act == "media":
            self.do_media()

    # ---------- bảng tuỳ chọn ----------
    def open_panel(self):
        W = H = u(290)
        t, m = u(84), u(18)
        p = self.panel = self._top()
        cv = tk.Canvas(p, width=W, height=H, bg=TC, highlightthickness=0)
        cv.pack()
        rrect(cv, 0, 0, W, H, u(28), "#1d1d20", outline="#47474c")
        tiles = [("shot", "Screenshot", (W - t) // 2, m, self.do_shot),
                 ("power", "Power", m, (H - t) // 2, lambda: self.do_key("power")),
                 ("home", "Home", W - m - t, (H - t) // 2, lambda: self.do_key("home")),
                 ("media", "Media", (W - t) // 2, H - m - t, self.do_media)]
        for name, label, x, y, fn in tiles:
            tag = "t_" + name
            cv.create_rectangle(x, y, x + t, y + t, fill="#1d1d20", outline="", tags=(tag, "hit"))   # vùng bấm, trùng màu nền
            cx, cy, r = x + t // 2, y + t // 2 - u(8), u(15)
            if name == "home":
                r1, r2 = u(22), u(16)
                cv.create_oval(cx - r1, cy - r1, cx + r1, cy + r1, fill="#6b6b72", outline="#9a9aa2", tags=tag)
                cv.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, fill="#f2f2f4", outline="", tags=tag)
            elif name == "power":
                cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=120, extent=300, style="arc",
                              outline="white", width=u(3), tags=tag)
                cv.create_line(cx, cy - r - u(3), cx, cy, fill="white", width=u(3), capstyle="round", tags=tag)
            elif name == "media":                       # ▶| : quick media control
                cv.create_polygon(cx - r * .8, cy - r, cx - r * .8, cy + r, cx + r * .6, cy, fill="white", outline="",
                                  tags=tag)
                cv.create_rectangle(cx + r * .8, cy - r, cx + r * 1.1, cy + r, fill="white", outline="", tags=tag)
            else:
                cv.create_rectangle(cx - r, cy - r + u(4), cx + r, cy + r, outline="white", width=u(3), tags=tag)
                cv.create_oval(cx - u(6), cy - u(4), cx + u(6), cy + u(8), outline="white", width=u(2), tags=tag)
            cv.create_text(x + t // 2, y + t - u(14), text=label, fill="white", font=font(12, True), tags=tag)
            cv.tag_bind(tag, "<ButtonPress-1>", lambda ev, f=fn, tg=tag, c=cv: self._tap(c, tg, f))
        bx, by = self.x, self.y
        x0, y0, x1, y1 = self.vrange()
        px = min(max(bx + self.s // 2 - W // 2, x0 + u(8)), x1 - W - u(8))
        py = by + self.s + u(8)
        if py + H > y1 - u(8):
            py = by - H - u(8)
        p.geometry(f"+{px}+{max(py, y0 + u(8))}")
        self.busy = False
        self.btn.withdraw()                      # ẩn nút khi bảng đang mở
        p.focus_force()
        p.bind("<FocusOut>", lambda e: self.app.after(120, self._lost_focus))
        p.bind("<Escape>", lambda e: self.close_panel())

    def _tap(self, cv, tag, fn):
        if self.busy:
            return
        self.busy = True
        for i in cv.find_withtag(tag):          # làm mờ icon để báo đã bấm
            if "hit" in cv.gettags(i):
                continue
            ty = cv.type(i)
            if ty in ("text", "line"):
                cv.itemconfig(i, fill="#8e8e93")
            elif cv.itemcget(i, "fill") in ("white", "#f2f2f4"):
                cv.itemconfig(i, fill="#8e8e93")
            elif cv.itemcget(i, "outline") == "white":
                cv.itemconfig(i, outline="#8e8e93")
        self.app.after(int(core.cfg_get("ui_delay", 150)), lambda: (self.close_panel(), fn()))

    def _lost_focus(self):
        try:
            if self.panel and self.panel.focus_displayof() is None:
                self.close_panel()
        except tk.TclError:
            pass

    def close_panel(self):
        if self.panel:
            try:
                self.panel.destroy()
            except tk.TclError:
                pass
            self.panel = None
            try:
                if not self.off:
                    self.btn.deiconify()
            except tk.TclError:
                pass

    # ---------- hành động (chạy luồng nền, kết quả qua hàng đợi) ----------
    def do_key(self, name):
        self.close_panel()

        def work():
            try:
                send_key(name)
            except Exception as ex:
                core.alog(f"assistive touch: '{name}' failed: {ex}", "WARN")
                self.msgs.put(("toast", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def do_media(self):
        """Quick media control: nhấn Home 2 lần liên tiếp (nhấp đúp) vào VM."""
        self.close_panel()

        def work():
            try:
                send_key("home", 2)
            except Exception as ex:
                core.alog(f"assistive touch: quick media control failed: {ex}", "WARN")
                self.msgs.put(("toast", str(ex)))
        threading.Thread(target=work, daemon=True).start()

    def do_shot(self):
        self.close_panel()

        def work():
            try:
                core.vm_screenshot(self.port, self.meta() if self.meta else None)
                self.msgs.put(("shot", "Saved to Gallery"))
            except Exception as ex:
                core.alog_exc(f"assistive touch: screenshot failed: {ex}")
                self.msgs.put(("toast", f"Screenshot failed: {ex}"))
        threading.Thread(target=work, daemon=True).start()

    def toast(self, text):
        if self.toast_w:
            self.toast_w.destroy()
        w = self.toast_w = self._top()
        tk.Label(w, text=text, bg="#1d1d20", fg="white", font=font(13, True), padx=u(14), pady=u(8)).pack()
        w.update_idletasks()
        bx, by = self.x, self.y
        x0, y0, x1, y1 = self.vrange()
        tw, th = w.winfo_reqwidth(), w.winfo_reqheight()
        x = min(max(bx + self.s // 2 - tw // 2, x0), x1 - tw)
        y = by - th - u(8) if by - th - u(8) > y0 else by + self.s + u(8)
        w.geometry(f"+{x}+{y}")
        w.after(1600, lambda: (w.destroy(), setattr(self, "toast_w", None) if self.toast_w is w else None))

    # ---------- vòng lặp ----------
    def tick(self):
        try:
            if self.proc.poll() is not None:
                self.destroy(); return
            while not self.msgs.empty():
                kind, text = self.msgs.get()
                if kind == "shot":
                    self.draw_btn(True)
                    self.app.after(150, self.draw_btn)
                    self.on_shot()
                self.toast(text)
            self.n += 1
            if self.n % 3 == 0:                  # theo dõi công tắc Assistive Touch trong Settings
                en = bool(core.cfg_get("at_enabled", True))
                if not en and not self.off:
                    self.off = True
                    self.close_panel()
                    self.btn.withdraw()
                elif en and self.off:
                    self.off = False
                    self.btn.deiconify()
            if not self.moved and not self.snapped and self.n % 3 == 0:    # lần đầu: đặt cạnh phải cửa sổ VM
                h = find_vm_window()
                if h:
                    r = wintypes.RECT()
                    user32.GetWindowRect(h, ctypes.byref(r))
                    self.place(r.right - self.s - u(14), (r.top + r.bottom) // 2)
                    self.snapped = True
            self.app.after(300, self.tick)
        except tk.TclError:
            pass

    def destroy(self):
        self.close_panel()
        for w in (self.toast_w, self.btn):
            try:
                w and w.destroy()
            except tk.TclError:
                pass
