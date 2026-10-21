"""Launcher OldRingo - giao diện kiểu iPad đời đầu. Logic ở core.py, vẽ UI ở kit.py."""
import base64, math, os, queue, shutil, struct, subprocess, sys, threading, time, tkinter as tk
from tkinter import filedialog

try:  # chữ nét trên màn hình scale >100%
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

import assist
import core
import imgkit
import keys
import kit
from kit import GOOD, BAD, MUTED, NavBar, Table, u

VERSION = "1.4"
SEP = "\u2501\u2501\u2501\u2501\u2501\u2501 "
REQ = [("res", "Computer resources"), ("msys", "MSYS2"), ("pkgs", "Build packages")]
LIMITS = [0, 5, 10, 25, 50, 100, 250, 500, 1000]   # MB
DELAYS = [0, 100, 150, 250, 400, 600, 1000]          # ms
RAMS = {"1 GB": "1G", "2 GB": "2G", "4 GB": "4G"}


def fw_label(fid):
    if fid == "custom":
        return "Custom firmware"
    return core.FIRMWARE[fid]["name"]


def fmt_dur(sec):
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}"


def load_photo(p):
    """PhotoImage từ PNG hoặc BMP (Tk không đọc BMP -> đổi sang PPM trong bộ nhớ)."""
    if p.suffix.lower() == ".bmp":
        w, h, pix = core.parse_ppm(core.bmp_to_ppm(p))
        return tk.PhotoImage(data=imgkit.Img(w, h, pix).tk_data())
    return tk.PhotoImage(file=str(p))


class Viewer(Table):
    """Trang xem ảnh toàn cửa sổ: vẽ trên Table để hộp thoại (Modal) phủ lên được."""

    def __init__(self, master, build):
        super().__init__(master, build)
        self.hits = []

    def _press(self, e):
        if self.dim:
            return super()._press(e)
        cy = self.canvasy(e.y)
        if self._wait:
            return
        for h in self.hits:
            x1, y1, x2, y2, fn = h[:5]
            if x1 <= e.x <= x2 and y1 <= cy <= y2:
                if len(h) > 5:                         # nút glossy / nút thanh tiêu đề: tối/đổi màu, chạy sau UI delay
                    spec = h[5]
                    if spec[0] == "btn":
                        _, i, label, color = spec
                        tag = f"vbtn{i}"
                        self.delete(tag)
                        kit.viewer_button(self, x1, y1, x2, y2, label, kit.PRESS.get(color, "blue"), tag=tag)
                        restore = lambda: (self.delete(tag),
                                           kit.viewer_button(self, x1, y1, x2, y2, label, color, tag=tag))
                    else:                              # ("bar", label, tip, top)
                        _, label, tip, top = spec
                        kit.bar_button(self, x1, y1, x2, y2, tag="vdonep", back=True, pressed=True)
                        kit.shadow_text(self, x1 + tip + (x2 - x1 - tip) // 2, top // 2, label, kit.font(13, True),
                                        shade="#2d3b57", dy=-1, tags="vdonep")
                        restore = lambda: self.delete("vdonep")
                    self._wait = True
                    self.after(kit.UI_DELAY[0], lambda: self._vfire(fn, restore))
                else:
                    fn()
                return
        super()._press(e)

    def _vfire(self, fn, restore):
        self._wait = False
        gen = self.gen
        fn()
        try:
            if self.gen == gen:                        # trang không vẽ lại -> trả nút về như cũ
                restore()
        except tk.TclError:
            pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        kit.init_scale(self)
        self.title("OldRingo")
        w = min(u(1024), self.winfo_screenwidth() - u(60))
        h = min(u(720), self.winfo_screenheight() - u(100))
        self.geometry(f"{w}x{h}")
        self.minsize(u(820), u(560))

        # điều hướng: trạng thái hiện tại + ngăn xếp các trang trước (cho nút Back)
        self.tab, self.sys_tab, self.page = "Profile", "Requirements", ("list",)
        self.stack = []
        self.status = []
        self.busy, self.target = False, None
        self.phase, self.setup_msg = 0, ""
        self.tail, self.tail_n, self.log_marks = (None, 0), 0, []
        self.q = queue.Queue()
        self._init_logging()
        self.log_last, self.log_text = "", None
        self.photo, self.thumbs, self._vimg, self._cfgvars = None, {}, None, []
        self.sessions, self.vmode, self.pc_layout, self.working = {}, "photo", 1, False
        self._shot, self._pc, self.pc_hw, self._pc_busy = None, {}, "n72ap", set()

        core.migrate_legacy()
        self.profiles = core.profiles_load()
        self.dbg = tk.BooleanVar(value=core.cfg_get("debug", True))
        self.auto = tk.BooleanVar(value=core.cfg_get("auto_check", True))
        self.logs = tk.BooleanVar(value=core.cfg_get("save_logs", False))
        self.limit = tk.IntVar(value=core.cfg_get("log_limit_mb", 0))
        self.uidelay = tk.IntVar(value=core.cfg_get("ui_delay", 150))
        self.mirror_url, self.mirror_ms, self.mirror_draft = tk.StringVar(), {}, None          # trang Mirrors: ô nhập + kết quả đo (ms)
        kit.UI_DELAY[0] = self.uidelay.get()
        keys.start(lambda kind: self.q.put(("hotkey" if kind == "shot" else "kbcap", None)))
        self.form, self.f_name = {}, tk.StringVar()
        self.f_custom = {k: tk.StringVar() for k in ("bootrom", "iboot", "nor", "nand")}

        self.nav = NavBar(self, self.title_now, self.back_label, self.right_label, self.go_back, self.on_right)
        self.nav.pack(fill="x")
        body = tk.Frame(self)
        body.pack(fill="both", expand=True)
        self.side = Table(body, self.build_side, inset=u(16), edge=True, width=u(301))
        self.side.pack(side="left", fill="y")
        self.main = Table(body, self.build_main)
        self.main.pack(side="left", fill="both", expand=True)

        # màn hình thiết lập: phủ toàn cửa sổ lúc mở app, tới khi môi trường đủ mới vào app
        self.setup_mode = self.checking = self.auto.get()
        self.setup_view = tk.Frame(self, bg=kit.BG1)
        self.setup = Table(self.setup_view, self.build_setup)
        self.setup.pack(fill="both", expand=True)
        if self.setup_mode:
            self.setup_view.place(x=0, y=0, relwidth=1, relheight=1)

        self.viewer = None                                        # trang xem ảnh: tạo mới cho mỗi ảnh được mở
        self.modal = kit.Modal(self, [self.nav, self.side, self.main, self.setup])   # menu/hộp thoại
        self.wm_vars = {k: tk.BooleanVar(value=True) for k in ("app", "profile", "device", "firmware", "time")}
        self.after(100, self.pump)
        self.after(1000, self.sess_tick)
        self.after(80, self.anim)
        self.after(500, self.tail_log)
        self.after(1000, self.trim_logs)
        if self.auto.get():
            self.after(300, lambda: self.refresh(prompt=True))

    # ================= điều hướng =================
    def _init_logging(self):
        """Banner khởi động + bắt mọi exception chưa xử lý (UI, luồng nền, chính) vào log của app."""
        import atexit, platform, traceback
        core.alog("=" * 60, "INFO")
        core.alog(f"OldRingo {VERSION} starting | Python {sys.version.split()[0]} | Tk {tk.TkVersion} | "
                  f"{platform.platform()} | pid {os.getpid()}", "INFO")
        core.alog(f"data dir: {core.BASE} | config: {core.CONFIG} | screen {self.winfo_screenwidth()}x"
                  f"{self.winfo_screenheight()} | ui scale {u(100) / 100:.2f}", "INFO")

        def fmt(et, ev, tb):
            return "".join(traceback.format_exception(et, ev, tb)).rstrip()
        self.report_callback_exception = lambda et, ev, tb: core.alog("Unhandled UI exception:\n" + fmt(et, ev, tb), "ERROR")
        threading.excepthook = lambda a: core.alog(
            f"Unhandled exception in thread '{a.thread.name if a.thread else '?'}':\n"
            + fmt(a.exc_type, a.exc_value, a.exc_traceback), "ERROR")
        sys.excepthook = lambda et, ev, tb: core.alog("Unhandled exception:\n" + fmt(et, ev, tb), "ERROR")
        atexit.register(lambda: core.alog("OldRingo exited", "INFO"))

    def snap(self):
        return (self.tab, self.sys_tab, self.page)

    def nav_log(self, how):
        core.alog(f"navigate ({how}): tab={self.tab} sys_tab={self.sys_tab} page={self.page} depth={len(self.stack)}",
                  "DEBUG")

    def pname(self, pid):
        p = self.get_profile(pid)
        return p["name"] if p else "Profile"

    def title_of(self, snap, back=False):
        tab, sys_tab, page = snap
        if tab == "System":
            return sys_tab if back else "System"
        if tab == "Settings":
            return SET_TITLES.get(page[0], "Settings")
        if tab == "How to?":
            return "How to?"
        if tab == "Gallery":
            return "Gallery"
        if page[0] == "list":
            return "Profiles"
        if page[0] == "detail":
            return self.pname(page[1])
        return "Edit Profile" if page[1] else "New Profile"

    def title_now(self):
        return self.title_of(self.snap())

    def back_label(self):
        if self.mirror_draft is not None:
            return "Cancel"
        if not self.stack:
            return None
        name = self.title_of(self.stack[-1], back=True)
        return name if len(name) <= 14 else name[:13] + "…"

    def go(self, tab=None, sys_tab=None, page=None):
        """Đi sâu vào một trang: đẩy trang hiện tại vào ngăn xếp -> hiện nút Back."""
        before = self.snap()
        self.mirror_draft = None
        if tab:
            self.tab = tab
        if sys_tab:
            self.sys_tab = sys_tab
        if page:
            self.page = page
        if self.snap() != before:
            self.stack.append(before)
        self.nav_log("go")
        self.redraw()

    def go_back(self):
        if self.mirror_draft is not None:             # đang Edit mirror: Back = Cancel, bỏ nháp và ở lại trang Mirrors
            self.mirror_draft = None
            core.alog("mirrors: edit cancelled, draft discarded", "INFO")
            self.redraw()
            return
        if self.stack:
            self.tab, self.sys_tab, self.page = self.stack.pop()
        self.nav_log("back")
        self.redraw()

    def select(self, tab):      # chọn ở sidebar: về trang gốc của mục đó
        self.stack.clear()
        self.mirror_draft = None
        self.tab = tab
        self.page = ("list",)
        self.nav_log("select")
        self.redraw()

    def set_sys_tab(self, name):
        self.sys_tab = name; self.main.render(); self.nav.draw()

    def right_label(self):
        if self.tab == "Settings" and self.page[0] == "mirror":
            return "Save" if self.mirror_draft is not None else "Edit"
        if self.tab != "Profile":
            return ""
        return {"list": "+ Add", "detail": "Edit", "form": "Save"}[self.page[0]]

    def on_right(self):
        if self.modal.active():
            return
        if self.tab == "Settings" and self.page[0] == "mirror":          # Edit <-> Save
            if self.mirror_draft is None:
                self.mirror_draft = core.mirrors_get()
                core.alog("mirrors: edit started", "INFO")
            else:
                core.mirrors_set(self.mirror_draft)
                core.alog("mirrors: saved " + ", ".join(f"{m['url']} ({'on' if m['on'] else 'off'})"
                                                        for m in self.mirror_draft), "INFO")
                self.mirror_draft = None
            self.redraw()
            return
        if self.tab != "Profile":
            return
        kind = self.page[0]
        if kind == "list":
            self.open_form(None)
        elif kind == "detail":
            self.open_form(self.page[1])
        else:
            self.save_form()

    def redraw(self):
        self.nav.draw(); self.side.render(); self.main.render()

    # ================= dữ liệu =================
    def get_profile(self, pid):
        return next((p for p in self.profiles if p["id"] == pid), None)

    def save_cfg(self):
        core.cfg_set("debug", self.dbg.get()); core.cfg_set("auto_check", self.auto.get())
        core.cfg_set("save_logs", self.logs.get()); core.cfg_set("log_limit_mb", self.limit.get())
        core.enforce_log_limit(self.limit.get())

    def save_delay(self):
        core.cfg_set("ui_delay", self.uidelay.get()); kit.UI_DELAY[0] = self.uidelay.get()

    def hotkey_shot(self):
        """Phím tắt chụp screenshot: chụp phiên VM đang chạy."""
        for s in self.sessions.values():
            if s["proc"].poll() is not None:
                continue
            ast = s.get("assist")
            if ast and ast.proc.poll() is None:
                ast.do_shot()
            else:
                def work(port=s["port"], meta=s["meta"]):
                    try:
                        core.vm_screenshot(port, meta); self.q.put(("gallery", None))
                    except Exception as ex:
                        core.alog_exc(f"hotkey screenshot failed: {ex}")
                threading.Thread(target=work, daemon=True).start()
            return

    def start_capture(self):
        keys.capture(True); self.main.render()

        self.after(8200, lambda: keys.capturing() or self.main.render())

    def clear_combo(self):
        core.cfg_set("kb_shot", None); keys.reload(); self.main.render()

    def refresh(self, prompt=False):
        def work():
            self.q.put(("status", (core.get_status(), prompt)))
        threading.Thread(target=work, daemon=True).start()

    def apply_status(self, st, prompt):
        self.status, self.checking = st, False
        ready = core.is_ready(st)
        core.alog("status check: " + ", ".join(f"{c.key}={'ok' if c.ok else 'MISSING'}" for c in st)
                  + f" | ready={ready} | hardware installed: "
                  + (", ".join(h for h in core.HARDWARE if core.find_qemu(h)) or "none")
                  + " | firmware: " + (", ".join(f for f in core.FIRMWARE if core.fw_downloaded(f)) or "none"), "INFO")
        if self.setup_mode and ready and not self.busy:           # đủ môi trường -> vào app
            self.setup_mode = False
            self.setup_view.place_forget()
        elif prompt and not self.setup_mode and not ready and not self.busy:
            self.setup_mode = True
            self.setup_view.place(x=0, y=0, relwidth=1, relheight=1)
        self.redraw(); self.setup.render()

    def req_rows(self):
        """Các dòng yêu cầu: vòng tải ở bước đang chạy, 'OK' khi xong lần lượt."""
        by = {c.key: c for c in self.status}
        setting = self.busy and self.target == ("setup",)
        cur, rows = None, []
        for key, label in REQ:
            c, row = by.get(key), {"kind": "value", "label": label}
            if self.checking:
                row["spin"] = True
            elif c is None:
                row.update(detail="Not checked", color=MUTED)
            elif c.ok:
                row.update(detail=c.detail or "OK", color=GOOD)
            elif setting and key in ("msys", "pkgs"):
                if cur is None:
                    cur = key; row["spin"] = True
                else:
                    row.update(detail="Waiting", color=MUTED)
            else:
                row.update(detail=(c.detail + " - low" if key == "res" else "Missing"), color=BAD)
            rows.append(row)
        return rows

    def build_setup(self, t):
        t.section("OLDRINGO SETUP")
        t.note("Checking your environment..." if self.checking else
               "OldRingo needs MSYS2 and the build packages to build and run the emulator. "
               "They are installed automatically, only once.")
        t.group(self.req_rows())
        if not self.checking:
            working = self.busy and self.target == ("setup",)
            t.group([{"kind": "action", "label": "Set Up", "spin": working, "disabled": self.busy,
                      "cb": lambda: self.run_task(core.setup, target=("setup",))}])
            t.footer(self.setup_msg[:90] if working and self.setup_msg else
                     "Needs an internet connection and may take a few minutes.")

    def trim_logs(self):
        core.enforce_log_limit(self.limit.get())
        self.after(30000, self.trim_logs)

    def anim(self):
        if self.busy or self.checking:
            self.phase = (self.phase + 1) % 12
            self.main.tick(self.phase); self.setup.tick(self.phase)
        self.after(80, self.anim)

    def tail_log(self):
        """Log realtime: nối thêm phần mới của log phiên đang chạy vào đúng vị trí của nó."""
        try:
            path, off = self.tail
            if self.log_text is not None and path:
                if len(core.session_logs()) != self.tail_n:        # có phiên mới -> dựng lại
                    self.main.render()
                elif os.path.getsize(path) > off:
                    with open(path, "rb") as f:
                        f.seek(off); data = f.read()
                    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
                    tw = self.log_text
                    at_end = tw.yview()[1] >= 0.999
                    tw.configure(state="normal")
                    pos = tw.index("sess_end")
                    tw.insert(pos, text)
                    tw.mark_set("sess_end", f"{pos}+{len(text)}c")
                    tw.configure(state="disabled")
                    if at_end:
                        tw.see("end")
                    self.tail = (path, off + len(data))
        except (OSError, tk.TclError):
            pass
        self.after(500, self.tail_log)

    def pump(self):
        while not self.q.empty():
            kind, val = self.q.get()
            if kind == "log":
                lines = []
                for ln in (val.splitlines() or [""]):
                    lines += core.alog(ln, "TASK")
                lines = lines or [val]
                try:
                    if self.log_text is not None:
                        tw = self.log_text
                        tw.configure(state="normal")
                        if self.log_last != "app":          # sau phiên -> mở mục APP mới ở cuối
                            tw.insert("end", SEP + "APP\n", ("sep",))
                        tw.insert("end", "\n".join(lines) + "\n"); tw.see("end")
                        tw.configure(state="disabled")
                except tk.TclError:
                    self.log_text = None
                self.log_last = "app"
                if "[2/3]" in val:                      # MSYS2 xong -> cập nhật trạng thái các dòng
                    self.refresh()
                if self.setup_mode:
                    self.setup_msg = next((x.strip() for x in reversed(lines) if x.strip()), self.setup_msg)
                    self.setup.render()
            elif kind == "gallery":
                if self.tab == "Gallery":
                    self.main.render()
            elif kind == "pcdone":
                key, res = val
                self._pc_busy.discard(key)
                if len(self._pc) > 8:
                    self._pc.clear()
                try:
                    self._pc[key] = res if isinstance(res, Exception) else {
                        n: (tk.PhotoImage(data=d), w, h) for n, (d, w, h) in res.items()}
                except tk.TclError as e:
                    self._pc[key] = e
                if self.vmode == "postcard":
                    self.viewer.render()
            elif kind == "mirror":
                core.alog(f"mirror test: {val[0]} -> " + (f"{val[1]} ms" if val[1] >= 0 else "failed"),
                          "INFO" if val[1] >= 0 else "WARN")
                self.mirror_ms[val[0]] = val[1]
                if self.tab == "Settings" and self.page[0] == "mirror":
                    self.main.render()
            elif kind == "mirrordone":
                core.alog(f"mirrors: apply to MSYS2 -> {val}", "INFO")
                self.notify("Mirrors", val)
            elif kind == "kbcap":
                self.main.render()
            elif kind == "hotkey":
                core.alog("hotkey: screenshot shortcut pressed", "INFO")
                self.hotkey_shot()
            elif kind == "edited":
                core.alog(f"edit finished: {val}", "INFO")
                self.working, self.vmode = False, "photo"
                self.open_photo(val)
                if self.tab == "Gallery":
                    self.main.render()
            elif kind == "edit_err":
                self.working = False
                if self.viewer:
                    self.viewer.render()
                self.notify("Edit", val)
            elif kind == "status":
                self.apply_status(*val)
            elif kind == "done":
                self.busy, self.target = False, None
                if val:
                    self.notify("Task Failed", val)
                self.refresh(); self.redraw(); self.setup.render()
        self.after(100, self.pump)

    # ================= tác vụ nền (cài / gỡ / tải) =================
    def run_task(self, fn, *args, target=None):
        if self.busy:
            self.notify("OldRingo", "Another task is still running."); return
        self.busy, self.target = True, target
        if not self.setup_mode:
            self.go(tab="System", sys_tab="Log")      # sang Log, có nút Back quay lại
        self.redraw(); self.setup.render()
        name = getattr(fn, "__name__", "task")
        core.alog(f"task started: {name} args={args} target={target}", "INFO")

        def work():
            t0 = time.time()
            try:
                fn(*args, lambda s: self.q.put(("log", s))); err = None
                core.alog(f"task finished: {name} ({time.time() - t0:.1f}s)", "INFO")
            except Exception as e:
                err = str(e)
                core.alog_exc(f"task failed: {name} after {time.time() - t0:.1f}s: {e}")
            self.q.put(("done", err))
        threading.Thread(target=work, daemon=True).start()

    # ---- menu 3 chấm & hộp thoại (căn giữa cửa sổ, làm tối toàn cửa sổ) ----
    def open_sheet(self, title, buttons):
        core.alog(f"menu shown: {title} [{', '.join(b[0] for b in buttons)}]", "DEBUG")
        self.modal.show(title, list(buttons) + [("Cancel", "dark", None)], cancel=lambda: None, bottom=True)

    def confirm(self, title, message, ok_label, ok_color, on_ok, cancel_label="Cancel"):
        core.alog(f"dialog (confirm): {title} - {message[:150]!r}", "DEBUG")
        self.modal.show(title, [(cancel_label, "dark", None), (ok_label, ok_color, on_ok)], message=message, row=True)

    def notify(self, title, message):
        core.alog(f"dialog (notice): {title} - {message[:150]!r}", "INFO")
        self.modal.show(title, [("OK", "blue", None)], message=message)

    def ask_cleanup(self):
        self.confirm("Clean Up", "This deletes the downloaded .zip files, setup scripts, the package cache and "
                     "the qemu-ios source code.\nBuilt hardware and unpacked firmware are kept.",
                     "Delete", "red", lambda: self.run_task(core.cleanup))

    def hw_menu(self, hid):
        name = core.HARDWARE[hid]["name"]
        if core.hw_installed(hid):
            self.open_sheet(name, [("Uninstall", "red", lambda: self.run_task(
                core.uninstall_hardware, hid, target=("hw", hid)))])
        else:
            self.open_sheet(name, [("Install", "blue", lambda: self.run_task(
                core.install_hardware, hid, target=("hw", hid)))])

    def fw_menu(self, fid):
        name = fw_label(fid)
        if core.fw_downloaded(fid):
            self.open_sheet(name, [("Delete", "red", lambda: self.run_task(
                core.delete_firmware, fid, target=("fw", fid)))])
        else:
            self.open_sheet(name, [("Download", "blue", lambda: self.run_task(
                core.download_firmware, fid, target=("fw", fid)))])

    # ================= profile =================
    def run_profile(self):
        p = self.get_profile(self.page[1])
        if self.busy:
            self.notify("OldRingo", "A task is still running."); return
        if core.profile_issues(p):
            self.go(tab="System", sys_tab="Hardware"); return
        s = self.sessions.get(p["id"])
        if s and s["proc"].poll() is None:
            self.notify("OldRingo", "This profile is already running."); return
        core.enforce_log_limit(self.limit.get())
        core.alog(f"run profile: '{p['name']}' (hw={p['hw']}, fw={p['fw']}, ram={p.get('ram')}, debug={self.dbg.get()})",
                  "INFO")
        try:
            keep = self.logs.get()
            logpath = core.new_log_path(p) if keep else core.temp_session_log()   # luôn ghi log để phát hiện panic
            port = core.free_port()
            proc = core.launch(p["hw"], core.profile_paths(p), p.get("ram", core.HARDWARE[p["hw"]]["default_ram"]),
                               self.dbg.get(), logpath, port)
        except Exception as e:
            core.alog_exc(f"run profile failed: '{p['name']}': {e}")
            self.notify("OldRingo", str(e)); return
        core.alog(f"session started: '{p['name']}' (pid {proc.pid}, monitor port {port}, log {logpath}, "
                  f"saved={keep})", "INFO")
        fw, ver = fw_label(p["fw"]), core.FIRMWARE.get(p["fw"], {}).get("version")
        meta = {"profile": p["name"], "device": core.HARDWARE[p["hw"]]["name"], "hw": p["hw"], "app": "OldRingo",
                "firmware": f"{fw} ({ver})" if ver and ver not in fw else fw}
        self.sessions[p["id"]] = dict(proc=proc, t0=time.time(), log=logpath, keep=keep, off=0, carry=b"",
                                      panicked=False, port=port, meta=meta)
        p["runs"] = p.get("runs", 0) + 1
        core.profiles_save(self.profiles)
        self.main.render()
        if core.cfg_get("at_enabled", True):
            self.sessions[p["id"]]["assist"] = assist.Assist(self, proc, port, lambda: self.q.put(("gallery", None)), lambda: meta)

    def sess_tick(self):
        """Mỗi giây: dò panic trong log phiên, kết thúc phiên khi VM tắt, cập nhật bộ đếm thời gian."""
        try:
            changed = False
            for pid, s in list(self.sessions.items()):
                p = self.get_profile(pid)
                if p and not s["panicked"]:
                    try:
                        with open(s["log"], "rb") as f:
                            f.seek(s["off"])
                            new = f.read()
                        s["off"] += len(new)
                        if core.PANIC_RE.search(s["carry"] + new):
                            s["panicked"], changed = True, True
                            core.alog(f"PANIC detected in session '{p['name']}' (total panics: {p.get('panics', 0) + 1})",
                                      "WARN")
                            p["panics"] = p.get("panics", 0) + 1
                            core.profiles_save(self.profiles)
                        s["carry"] = new[-64:]
                    except OSError:
                        pass
                if s["proc"].poll() is not None:
                    el = time.time() - s["t0"]
                    core.alog(f"session ended: '{p['name'] if p else pid}' (exit code {s['proc'].returncode}, "
                              f"{el:.0f}s, panicked={s['panicked']})", "INFO")
                    if p:
                        p["play"], p["last"] = p.get("play", 0) + el, el
                        core.profiles_save(self.profiles)
                    if not s["keep"]:
                        try:
                            os.remove(s["log"])
                        except OSError:
                            pass
                    del self.sessions[pid]
                    changed = True
            on_detail = self.tab == "Profile" and self.page[0] == "detail"
            if on_detail and not self.modal.active() and (changed or self.page[1] in self.sessions):
                self.main.render()
        except Exception:
            core.alog_exc("session monitor error")
        self.after(1000, self.sess_tick)

    def toggle_pin(self, pid):
        p = self.get_profile(pid)
        if p:
            p["pin"] = not p.get("pin")
            core.profiles_save(self.profiles)
            self.main.render()

    def delete_profile(self):
        p = self.get_profile(self.page[1])
        if not p:
            return

        def do():
            self.profiles = [x for x in self.profiles if x["id"] != p["id"]]
            core.profiles_save(self.profiles)
            self.go_back()
        self.confirm("Delete Profile", f"Delete \"{p['name']}\"? This cannot be undone.", "Delete", "red", do)

    def open_form(self, pid):
        p = self.get_profile(pid) if pid else None
        installed = [h for h in core.HARDWARE if core.hw_installed(h)]
        hw = p["hw"] if p else (installed[0] if installed else "")
        self.form = {"hw": hw, "fw": p["fw"] if p else "",
                     "ram": p.get("ram") if p else (core.HARDWARE[hw]["default_ram"] if hw else "2G")}
        self.f_name.set(p["name"] if p else "")
        for k, v in self.f_custom.items():
            v.set((p.get("custom", {}).get(k, "") if p else ""))
        self.go(tab="Profile", page=("form", pid))

    def save_form(self):
        f, pid = self.form, self.page[1]
        name = self.f_name.get().strip()
        files = core.HARDWARE[f["hw"]]["files"] if f["hw"] else ()
        custom = {k: self.f_custom[k].get().strip() for k in files}
        problem = ("Enter a name for the profile." if not name else
                   "Choose the hardware." if not f["hw"] else
                   "Choose a firmware." if not f["fw"] else
                   "Choose every file of the custom firmware."
                   if f["fw"] == "custom" and not all(v and os.path.exists(v) for v in custom.values()) else "")
        if problem:
            self.notify("OldRingo", problem); return
        rec = {"id": pid or core.new_profile_id(), "name": name, "hw": f["hw"], "fw": f["fw"],
               "custom": custom if f["fw"] == "custom" else {}, "ram": f["ram"]}
        if pid:
            self.profiles = [rec if x["id"] == pid else x for x in self.profiles]
        else:
            self.profiles.append(rec)
        core.profiles_save(self.profiles)
        self.go_back()

    def browse(self, key):
        init = str(core.FW) if core.FW.exists() else None
        p = filedialog.askdirectory(initialdir=init) if key == "nand" else filedialog.askopenfilename(initialdir=init)
        if p:
            self.f_custom[key].set(p)

    # ================= các trang =================
    def build_side(self, t):
        t.y += u(8)
        t.group([{"kind": "nav", "icon": "howto" if k == "How to?" else k.lower(), "label": k,
                  "selected": self.tab == k, "cb": lambda k=k: self.select(k)}
                 for k in ("Profile", "Gallery", "System", "How to?", "Settings")])

    def build_main(self, t):
        t.plain = "white" if self.tab == "Gallery" else None        # Gallery: nền trắng, không kẻ sọc
        if self.tab == "Profile":
            {"list": self.page_list, "detail": self.page_detail, "form": self.page_form}[self.page[0]](t)
        else:
            {"Gallery": self.page_gallery, "System": self.page_system, "Settings": self.page_settings,
             "How to?": self.page_howto}[self.tab](t)

    # ---- Gallery ----
    def thumb(self, p, cell):
        """Ảnh vuông (crop giữa) kích thước ~cell x cell."""
        key = (str(p), p.stat().st_mtime_ns, cell)
        ph = self.thumbs.get(key)
        if ph is None:
            try:
                img = load_photo(p)
            except (OSError, tk.TclError, ValueError, struct.error):
                return None
            w, h = img.width(), img.height()
            m = min(w, h)
            r = cell / m
            a, b = min(((a, b) for a in range(1, 5) for b in range(1, 7)), key=lambda ab: abs(ab[0] / ab[1] - r))
            m2 = min(m, round(cell * b / a))
            x0, y0 = (w - m2) // 2, (h - m2) // 2
            ph = tk.PhotoImage()
            ph.tk.call(ph.name, "copy", img.name, "-from", x0, y0, x0 + m2, y0 + m2)
            if a > 1:
                ph = ph.zoom(a)
            if b > 1:
                ph = ph.subsample(b)
            if len(self.thumbs) > 300:
                self.thumbs.clear()
            self.thumbs[key] = ph
        return ph

    def page_gallery(self, t):
        t.section("SCREENSHOTS")
        files = core.gallery_list()
        if not files:
            t.footer("No screenshots yet. Run a profile and use the floating button to take one.")
            return
        avail, gap = t.x2 - t.x1, u(2)
        cols = max(1, (avail + gap) // (u(120) + gap))
        cell = (avail - gap * (cols - 1)) // cols
        for i, p in enumerate(files):
            r, c = divmod(i, cols)
            x, y, tag = t.x1 + c * (cell + gap), t.y + r * (cell + gap), f"ph{i}"
            ph = self.thumb(p, cell)
            if ph:
                t.create_image(x, y, image=ph, anchor="nw", tags=tag)
            else:
                t.create_rectangle(x, y, x + cell, y + cell, fill="#d0d3d8", outline="", tags=tag)
            t.tag_bind(tag, "<ButtonPress-1>", lambda e, p=p: self.modal.active() or self.open_photo(p))
        t.y += -(-len(files) // cols) * (cell + gap) + u(4)
        t.footer(f"{len(files)} screenshot{'s' if len(files) != 1 else ''}")

    def _drop_viewer(self):
        v, self.viewer = self.viewer, None
        if v:
            if v in self.modal.dims:
                self.modal.dims.remove(v)
            v.destroy()

    def open_photo(self, path):
        self._drop_viewer()                               # mỗi ảnh một trang riêng, không dùng lại trang cũ
        core.alog(f"photo opened: {os.path.basename(str(path))}", "DEBUG")
        self.photo, self.vmode = path, "photo"
        v = self.viewer = Viewer(self, self.build_viewer)
        v.modal = self.modal
        self.modal.dims.append(v)
        v.place(x=0, y=0, relwidth=1, relheight=1)
        v.lift()
        v.render()

    def close_photo(self):
        self.photo, self.vmode = None, "photo"
        self._drop_viewer()
        self.main.render()

    def viewer_image(self, aw, ah):
        p = self.photo
        try:
            key = (str(p), p.stat().st_mtime_ns, aw, ah)
            if self._vimg and self._vimg[0] == key:
                return self._vimg[1]
            img = load_photo(p)
        except (OSError, tk.TclError, ValueError, struct.error):
            return None
        s = min(aw / img.width(), ah / img.height())
        best, bs = (1, max(1, math.ceil(1 / s))), 0
        for a in range(1, 5):
            for b in range(1, 7):
                if bs < a / b <= s:
                    bs, best = a / b, (a, b)
        if best[0] > 1:
            img = img.zoom(best[0])
        if best[1] > 1:
            img = img.subsample(best[1])
        self._vimg = (key, img)
        return img

    def set_vmode(self, mode):
        if self.working:
            return
        self.vmode = mode
        core.alog(f"viewer mode: {mode}", "DEBUG")
        self.viewer.render()
        self.viewer.yview_moveto(0)

    def vbar(self, t, title, back, fn):
        """Thanh tiêu đề của trang xem ảnh; trả về chiều cao."""
        W, top = t.W, u(44)
        kit.vgrad(t, 0, 0, W, top, kit.NAV1, kit.NAV2, "vt")
        kit.shadow_text(t, W // 2, top // 2, self.photo.name if self.vmode == "photo" else title,
                        kit.font(15, True), shade="#33415a", dy=-1)
        bx1, by1, bx2, by2 = u(8), u(7), u(8) + u(96), top - u(7)
        tip = kit.bar_button(t, bx1, by1, bx2, by2, tag="vdone", back=True)
        kit.shadow_text(t, bx1 + tip + (bx2 - bx1 - tip) // 2, top // 2, back, kit.font(13, True),
                        shade="#2d3b57", dy=-1)
        if not self.working:
            t.hits.append((bx1, by1, bx2, by2, fn, ("bar", back, tip, top)))
        return top

    def vbottom(self, t, buttons):
        """Thanh nút phía dưới; trả về chiều cao."""
        W, H, bot, gap = t.W, t.H, u(68), u(10)
        mid = H - bot // 2                                 # thanh nút kiểu iOS 3: nửa trên xám, nửa dưới đen
        kit.vgrad(t, 0, H - bot, W, mid, "#363636", "#262626", "vb")
        kit.vgrad(t, 0, mid, W, H, "#0e0e0e", "#050505", "vb")
        t.create_line(0, H - bot, W, H - bot, fill="#505050", tags="vb")
        if self.working:
            kit.shadow_text(t, W // 2, H - bot // 2, "Creating...", kit.font(15, True), fill="white", shade="#000000")
            return bot
        n = len(buttons)
        bw = min(u(150), (W - u(40) - gap * (n - 1)) // n)
        x = (W - (n * bw + (n - 1) * gap)) // 2
        for i, (label, color, fn) in enumerate(buttons):
            y1, y2 = H - bot + u(12), H - u(12)
            kit.viewer_button(t, x, y1, x + bw, y2, label, color, tag=f"vbtn{i}")
            t.hits.append((x, y1, x + bw, y2, fn, ("btn", i, label, color)))
            x += bw + gap
        return bot

    def build_viewer(self, t):
        t.hits = []
        if not self.photo:
            t.create_rectangle(0, 0, t.W, t.H, fill="black", outline="")
            return
        try:
            {"photo": self.vw_photo, "props": self.vw_props, "postcard": self.vw_postcard,
             "watermark": self.vw_watermark}[self.vmode](t)
        except Exception as e:
            import traceback
            core.alog_exc(f"viewer render failed (mode {self.vmode})")
            t.create_text(t.W // 2, t.H // 2, text=f"Error: {e}", fill=BAD, font=kit.font(14), width=t.W - u(40))

    def vw_photo(self, t):
        t.create_rectangle(0, 0, t.W, t.H, fill="black", outline="")
        W, H = t.W, t.H
        top, bot = self.vbar(t, "", "Gallery", self.close_photo), u(68)
        img = self.viewer_image(W - u(20), H - top - bot - u(20))
        if img:
            t.create_image(W // 2, top + (H - top - bot) // 2, image=img)
        self.vbottom(t, (("Edit", "white", self.photo_edit), ("Properties", "black", lambda: self.set_vmode("props")),
                         ("Open with", "black", self.photo_open_with), ("Copy to", "black", self.photo_copy),
                         ("Delete", "red", self.photo_delete)))

    def vw_props(self, t):
        top = self.vbar(t, "Properties", "Photo", lambda: self.set_vmode("photo"))
        t.y = top + u(14)
        t.section("PHOTO")
        t.group([{"kind": "value", "label": a, "detail": b} for a, b in core.photo_props(self.photo)])
        if core.meta_get(self.photo.name):
            t.group([{"kind": "action", "label": "Clear Metadata", "color": BAD, "cb": self.clear_meta}])
            t.footer("Removes the profile, device, firmware and app info saved with this photo.")

    def clear_meta(self):
        name = self.photo.name
        self.confirm("Clear Metadata", "Remove the saved profile, device, firmware and time info from this photo?",
                     "Clear", "red", lambda: (core.meta_drop(name), self.viewer.render()))

    def shot_key(self):
        return (str(self.photo), self.photo.stat().st_mtime_ns)

    def shot_img(self):
        key = self.shot_key()
        if not self._shot or self._shot[0] != key:
            w, h, pix = core.load_rgb(self.photo)
            self._shot = (key, imgkit.Img(w, h, pix))
        return self._shot[1]

    def photo_edit(self):
        self.open_sheet("Edit", [("Create Postcard", "blue", self.open_postcard),
                                 ("Create Watermark", "blue", lambda: self.set_vmode("watermark"))])

    def open_postcard(self):
        hw = (core.meta_get(self.photo.name) or {}).get("hw")
        self.pc_hw = hw if hw in core.HARDWARE else "n72ap"
        imgkit._PHOTO.clear(); imgkit._SIZED.clear(); self._pc.clear()   # đọc lại ảnh thật nếu vừa thêm vào thư mục frames
        self.set_vmode("postcard")

    def pick_layout(self, n):
        self.pc_layout = n
        self.viewer.render()

    def vw_postcard(self, t):
        W, H = t.W, t.H
        top = self.vbar(t, "Postcard", "Cancel", lambda: self.set_vmode("photo"))
        bot = self.vbottom(t, (("Create", "white", lambda: self.start_edit("postcard")),))
        hid = self.pc_hw
        pad, gap = u(8), u(14)
        avail = W - u(40) - 2 * gap - 6 * pad
        hgt = max(u(80), min(u(320), H - top - bot - u(150)))

        def get(h):                                      # None = đang dựng ở luồng nền
            k = (self.shot_key(), hid, h)
            v = self._pc.get(k)
            if v is None:
                self.pc_start(k)
            return v
        pv = get(hgt)
        if isinstance(pv, dict):
            tw = sum(v[1] for v in pv.values())
            if tw > avail:                               # hẹp quá -> thu nhỏ cho vừa
                hgt = max(u(60), int(hgt * avail / tw))
                pv = get(hgt)
        if pv is None or isinstance(pv, Exception):
            msg = str(pv) if pv is not None else "Preparing preview..."
            t.create_text(W // 2, H // 2, text=msg, fill=kit.DETAIL, font=kit.font(15))
            return
        cw = {n: pv[n][1] + 2 * pad for n in pv}
        ch = max(v[2] for v in pv.values()) + 2 * pad
        x, y = (W - sum(cw.values()) - 2 * gap) // 2, top + u(54)
        kit.shadow_text(t, W // 2, top + u(22), "Choose a frame", kit.font(16, True), fill=kit.SECTION,
                        shade="white", dy=1)
        for n in imgkit.LAYOUTS:
            if n == self.pc_layout:
                kit.rrect(t, x - 3, y - 3, x + cw[n] + 3, y + ch + 3, u(11), "#2563d6")
            kit.rrect(t, x, y, x + cw[n], y + ch, u(9), "white", outline=kit.BORDER)
            t.create_image(x + cw[n] // 2, y + ch // 2, image=pv[n][0])
            t.create_text(x + cw[n] // 2, y + ch + u(18), text=imgkit.LAYOUTS[n], font=kit.font(14, True),
                          fill=kit.DETAIL)
            t.hits.append((x, y, x + cw[n], y + ch + u(34), lambda n=n: self.pick_layout(n)))
            x += cw[n] + gap

    def pc_start(self, key):
        """Dựng 3 ảnh xem trước ở luồng nền (đọc ảnh + vẽ + mã hoá PNG), xong gửi về hàng đợi."""
        if key in self._pc_busy:
            return
        self._pc_busy.add(key)
        _, hid, hgt = key

        def work():
            try:
                shot = self.shot_img()
                res = {}
                for n in imgkit.LAYOUTS:
                    im = imgkit.make_postcard(shot, hid, n, preview_h=hgt)
                    res[n] = (im.tk_data(), im.w, im.h)
                self.q.put(("pcdone", (key, res)))
            except Exception as e:
                self.q.put(("pcdone", (key, e)))
        threading.Thread(target=work, daemon=True).start()

    def wm_lines(self):
        m, v = core.meta_get(self.photo.name) or {}, self.wm_vars
        taken = m.get("time") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.photo.stat().st_mtime))
        lines = []
        if v["app"].get():
            lines.append((m.get("app") or "OldRingo", True))
        for key, label, val in (("profile", "Profile", m.get("profile")), ("device", "Device", m.get("device")),
                                ("firmware", "Firmware", m.get("firmware")), ("time", "Taken", taken)):
            if v[key].get() and val:
                lines.append((f"{label}: {val}", False))
        return lines

    def vw_watermark(self, t):
        W, H = t.W, t.H
        top = self.vbar(t, "Watermark", "Cancel", lambda: self.set_vmode("photo"))
        bot = self.vbottom(t, (("Create", "white", lambda: self.start_edit("watermark")),))
        try:
            shot = self.shot_img()
        except Exception as e:
            t.create_text(W // 2, H // 2, text=str(e), fill=kit.DETAIL, font=kit.font(14)); return
        ah = max(u(120), H - top - bot - 5 * u(44) - u(110))
        prev = imgkit.watermark(imgkit.Img(shot.w, shot.h, bytes(shot.buf)), self.wm_lines())
        ph = tk.PhotoImage(data=prev.tk_data())
        k = max(1, math.ceil(ph.height() / ah))
        self._wmph = ph.subsample(k) if k > 1 else ph
        t.create_image(W // 2, top + u(12) + self._wmph.height() // 2, image=self._wmph)
        t.y = top + u(24) + self._wmph.height()
        t.group([{"kind": "switch", "label": lab, "var": self.wm_vars[key], "on_change": self.viewer.render}
                 for key, lab in (("profile", "Profile name"), ("device", "Device type"),
                                  ("firmware", "Firmware version"), ("app", "App name"), ("time", "Capture time"))])
        if not core.meta_get(self.photo.name):
            t.footer("This photo has no metadata, so only the app name and time are available.")

    def start_edit(self, kind):
        if self.working:
            return
        core.alog(f"edit started: {kind} on {self.photo.name} (layout={self.pc_layout})", "INFO")
        self.working = True
        self.viewer.render()
        path, layout, lines = self.photo, self.pc_layout, self.wm_lines()
        m = core.meta_get(path.name)
        hid = self.pc_hw
        fmt, comp = core.cfg_get("shot_format", "png"), bool(core.cfg_get("shot_compress", True))
        fmt = fmt if fmt in ("png", "bmp") else "png"

        def work():
            try:
                w, h, pix = core.load_rgb(path)
                shot = imgkit.Img(w, h, pix)
                if kind == "postcard":
                    out = imgkit.make_postcard(shot, hid, layout, max(2, round(w / 320)))
                else:
                    out = imgkit.watermark(shot, lines)
                dst = path.with_name(f"{path.stem}_{kind}_{int(time.time() * 1000) % 100000}.{fmt}")
                out.save(dst, fmt, comp)
                if m:
                    core.meta_set(dst.name, dict(m))
                self.q.put(("edited", dst))
            except Exception as e:
                core.alog_exc(f"edit failed ({kind}) for {path.name}: {e}")
                self.q.put(("edit_err", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def photo_open_with(self):
        core.alog(f"open with: {self.photo}", "INFO")
        try:
            subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", str(self.photo)])
        except Exception as e:
            self.notify("Gallery", str(e))

    def photo_copy(self):
        ext = self.photo.suffix.lower()
        dest = filedialog.asksaveasfilename(initialfile=self.photo.name, defaultextension=ext,
                                            filetypes=[(ext[1:].upper() + " image", "*" + ext)])
        if not dest:
            return
        try:
            shutil.copy2(self.photo, dest)
            core.alog(f"photo copied: {self.photo.name} -> {dest}", "INFO")
            self.notify("Gallery", "Copied.")
        except Exception as e:
            core.alog_exc(f"photo copy failed: {self.photo.name} -> {dest}: {e}")
            self.notify("Gallery", str(e))

    def photo_delete(self):
        p = self.photo

        def do():
            core.alog(f"photo deleted: {p.name}", "INFO")
            core.gallery_delete(p)
            self.close_photo()
        self.confirm("Delete Photo", "Delete this screenshot? This cannot be undone.", "Delete", "red", do)

    # ---- Profile: danh sách ----
    def page_list(self, t):
        if not self.profiles:
            t.section("PROFILES")
            t.footer("No profiles yet. Tap + Add to create one."); return

        def row(p):
            bad = core.profile_issues(p)
            return {"kind": "prow", "title": p["name"], "h": u(72),
                    "sub": f"{core.HARDWARE[p['hw']]['name']} - {fw_label(p['fw'])}",
                    "detail": "Setup needed" if bad else "Ready", "color": BAD if bad else GOOD,
                    "pin": p.get("pin"), "pin_cb": lambda pid=p["id"]: self.toggle_pin(pid),
                    "cb": lambda pid=p["id"]: self.go(page=("detail", pid))}
        pinned = [p for p in self.profiles if p.get("pin")]
        rest = [p for p in self.profiles if not p.get("pin")]
        if pinned:
            t.section("PINNED")
            t.group([row(p) for p in pinned])
        if rest:
            t.section("PROFILES")
            t.group([row(p) for p in rest])

    # ---- Profile: chi tiết ----
    def page_detail(self, t):
        p = self.get_profile(self.page[1])
        if not p:
            t.footer("This profile no longer exists."); return
        hw, bad = core.HARDWARE[p["hw"]], core.profile_issues(p)
        t.section("PROFILE")
        t.group([{"kind": "profile", "title": p["name"], "sub": fw_label(p["fw"]), "h": u(88),
                  "button": "Setup" if bad else "Run", "bcolor": "runred" if bad else "runblue", "cb": self.run_profile,
                  "pin": p.get("pin"), "pin_cb": lambda pid=p["id"]: self.toggle_pin(pid)}])
        t.footer("Tap the profile to start the emulator." if not bad else
                 f"{' and '.join(bad)}. Tap the profile to open System.")
        t.section("USAGE")
        sess = self.sessions.get(p["id"])
        urows = [{"kind": "value", "label": "Times played", "detail": str(p.get("runs", 0))},
                 {"kind": "value", "label": "Panics", "detail": str(p.get("panics", 0)),
                  "color": BAD if p.get("panics") else kit.DETAIL}]
        live = time.time() - sess["t0"] if sess else 0
        if sess:
            urows.append({"kind": "value", "label": "Current session", "detail": fmt_dur(live), "color": GOOD})
        elif p.get("last"):
            urows.append({"kind": "value", "label": "Last session", "detail": fmt_dur(p["last"])})
        urows.append({"kind": "value", "label": "Total play time", "detail": fmt_dur(p.get("play", 0) + live)})
        t.group(urows)
        t.section("DEVICE")
        t.group([{"kind": "value", "label": "Model", "detail": hw["name"]},
                 {"kind": "value", "label": "Identifier", "detail": hw["model"]},
                 {"kind": "value", "label": "Chip", "detail": hw["chip"]},
                 {"kind": "value", "label": "Memory", "detail": p.get("ram", hw["default_ram"]).replace("G", " GB")}])
        t.section("OPERATING SYSTEM")
        rows = [{"kind": "value", "label": "Firmware", "detail": fw_label(p["fw"])}]
        ver = core.FIRMWARE.get(p["fw"], {}).get("version")
        if ver:
            rows.append({"kind": "value", "label": "Version", "detail": ver})
        if p["fw"] == "custom":
            c = p.get("custom", {})
            rows += [{"kind": "value", "label": k, "detail": os.path.basename(c.get(k, "").rstrip("\\/")) or "-"}
                     for k in hw["files"]]
        t.group(rows)
        t.group([{"kind": "action", "label": "Delete Profile", "color": BAD, "cb": self.delete_profile}])

    # ---- Profile: form Add / Edit ----
    def page_form(self, t):
        f = self.form
        t.section("NAME")
        t.group([{"kind": "entry", "label": "Name", "var": self.f_name, "h": u(48)}])

        t.section("HARDWARE")
        installed = [h for h in core.HARDWARE if core.hw_installed(h)]
        if installed:
            t.group([{"kind": "choice", "label": core.HARDWARE[h]["name"], "checked": f["hw"] == h,
                      "cb": lambda h=h: self.pick("hw", h)} for h in installed])
        else:
            t.group([{"kind": "value", "label": "No hardware installed", "detail": "", "color": MUTED}])
            t.footer("Install hardware in System > Hardware first.")

        t.section("FIRMWARE")
        rows = [{"kind": "choice", "label": fw_label(fid), "sub": f"for {core.HARDWARE[x['hw']]['name']}",
                 "checked": f["fw"] == fid, "h": u(54), "cb": lambda fid=fid: self.pick("fw", fid)}
                for fid, x in core.FIRMWARE.items()
                if core.fw_downloaded(fid) and (not f["hw"] or x["hw"] == f["hw"])]
        rows.append({"kind": "choice", "label": "Custom firmware", "checked": f["fw"] == "custom",
                     "cb": lambda: self.pick("fw", "custom")})
        t.group(rows)
        if len(rows) == 1:
            t.footer("Download firmware in System > Hardware, or use a custom firmware.")

        if f["fw"] == "custom":
            files = core.HARDWARE[f["hw"]]["files"] if f["hw"] else ("bootrom", "nor", "nand")
            t.section("CUSTOM FIRMWARE")
            t.group([{"kind": "entry", "label": k, "var": self.f_custom[k], "h": u(48),
                      "browse": lambda k=k: self.browse(k)} for k in files])
            t.footer("nand is a folder, the others are files.")

        opts = core.HARDWARE[f["hw"]]["ram"] if f["hw"] else ("2G",)
        if len(opts) > 1:
            t.section("MEMORY")
            names = [n for n, v in RAMS.items() if v in opts]
            cur = next((n for n, v in RAMS.items() if v == f["ram"]), names[0])
            t.segmented(names, cur, lambda n: self.pick("ram", RAMS[n]))
            t.footer(f"{core.HARDWARE[f['hw']]['default_ram'].replace('G', ' GB')} is recommended.")

    def pick(self, key, val):
        self.form[key] = val
        if key == "hw":          # firmware và RAM phải hợp với phần cứng
            fw = self.form["fw"]
            if fw in core.FIRMWARE and core.FIRMWARE[fw]["hw"] != val:
                self.form["fw"] = ""
            if self.form["ram"] not in core.HARDWARE[val]["ram"]:
                self.form["ram"] = core.HARDWARE[val]["default_ram"]
        self.main.render()

    # ---- System ----
    def page_system(self, t):
        t.segmented(["Requirements", "Hardware", "Log"], self.sys_tab, self.set_sys_tab)
        {"Requirements": self.sys_req, "Hardware": self.sys_hw, "Log": self.sys_log}[self.sys_tab](t)

    def sys_req(self, t):
        t.section("REQUIREMENTS")
        rows = self.req_rows()
        t.group(rows)
        t.group([{"kind": "action", "label": "Check again", "cb": self.refresh},
                 {"kind": "action", "label": "Set up automatically", "cb": lambda: self.run_task(core.setup, target=("setup",)),
                  "spin": self.busy and self.target == ("setup",), "disabled": self.busy}])
        t.footer("Installs MSYS2 and the build packages only. Hardware and firmware are installed "
                 "separately in the Hardware tab.")

    def _status(self, kind, key, installed, can):
        if self.busy and self.target == (kind, key):
            return "", MUTED, False
        if not can:
            return "Coming soon", MUTED, False
        word = ("Installed", "Not installed") if kind == "hw" else ("Downloaded", "Not downloaded")
        return (word[0], GOOD, True) if installed else (word[1], MUTED, True)

    def sys_hw(self, t):
        t.section("HARDWARE")
        rows = []
        for hid, hw in core.HARDWARE.items():
            text, color, usable = self._status("hw", hid, core.hw_installed(hid), True)
            rows.append({"kind": "item", "label": hw["name"], "sub": f"{hw['model']} - {hw['chip']}", "h": u(56),
                         "detail": text, "color": color,
                         "spin": self.busy and self.target == ("hw", hid),
                         "menu": (lambda hid=hid: self.hw_menu(hid)) if usable and not self.busy else None})
        t.group(rows)
        t.footer("Hardware is built from the qemu-ios source. Tap the dots to install or uninstall.")
        t.section("FIRMWARE")
        rows = []
        for fid, fw in core.FIRMWARE.items():
            text, color, usable = self._status("fw", fid, core.fw_downloaded(fid), True)
            rows.append({"kind": "item", "label": fw_label(fid), "sub": f"for {core.HARDWARE[fw['hw']]['name']}",
                         "h": u(56), "detail": text, "color": color,
                         "spin": self.busy and self.target == ("fw", fid),
                         "menu": (lambda fid=fid: self.fw_menu(fid)) if not self.busy else None})
        t.group(rows)
        t.footer("Firmware (bootrom, nor, nand) is downloaded from the qemu-ios releases.")
        t.section("MAINTENANCE")
        t.group([{"kind": "action", "label": "Clean Up Temporary Files", "cb": self.ask_cleanup,
                  "disabled": self.busy}])
        t.footer("Removes install leftovers only. Installed hardware and firmware keep working.")

    def log_view(self):
        """Log tuần tự theo thời gian: đoạn log app và các phiên emulator xen kẽ, mới nhất ở cuối."""
        ev = [(ts, 0, txt) for ts, txt in core.app_log_read()]
        ev += [(core.session_start(p), 1, p) for p in core.session_logs()]
        ev.sort(key=lambda e: (e[0], e[1]))
        lines, last = [], ""
        self.tail, self.tail_n, self.log_marks = (None, 0), len(core.session_logs()), []
        for ts, kind, v in ev:
            if kind == 0:
                if last != "app":
                    lines.append(SEP + "APP")
                lines.append(f"{ts}  {v}"); last = "app"
            else:
                lines.append(SEP + "SESSION - " + core.session_label(v))
                raw = open(v, "rb").read()
                lines += raw.decode("utf-8", errors="replace").splitlines(); last = "session"
                self.tail, self.log_marks = (v, len(raw)), [(len(lines), "sess_end")]
        self.log_last = last
        return lines

    def sys_log(self, t):
        t.section("LOG")
        lines = self.log_view()
        hh = max(u(240), t.H - t.y - u(270))
        t.group([{"kind": "text", "h": hh, "lines": lines, "marks": self.log_marks,
                  "register": lambda w: setattr(self, "log_text", w)}])
        t.group([{"kind": "action", "label": "Open App Logs Folder", "cb": lambda: self.open_dir(core.APP_LOG_DIR)},
                 {"kind": "action", "label": "Open QEMU Log Folder", "cb": lambda: self.open_dir(core.LOGS)}])
        t.group([{"kind": "action", "label": "Refresh", "cb": self.main.render},
                 {"kind": "action", "label": "Clear Log", "color": BAD, "cb": self.ask_clear_log,
                  "spin": self.busy and self.target == ("log", "clear"), "disabled": self.busy}])
        t.footer("Shows the app log and the saved emulator session logs in order (Settings > Save session logs).")

    def open_dir(self, path):
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except Exception as e:
            self.notify("Log", str(e))

    def ask_clear_log(self):
        self.confirm("Clear Log", "Delete the app log and all saved session logs?", "Delete", "red",
                     lambda: self.run_task(lambda log: core.clear_logs(), target=("log", "clear")))

    # ---- Settings ----
    def page_settings(self, t):
        sub = self.page[0]
        if sub == "about":
            self.page_about(t); return
        if sub in SET_TITLES:
            getattr(self, "set_" + sub)(t); return
        t.section("SETTINGS")
        t.group([{"kind": "nav", "icon": ic, "label": SET_TITLES[k], "cb": lambda k=k: self.go(page=(k,))}
                 for k, ic in (("general", "settings"), ("diagnosis", "diag"), ("screenshot", "shot"),
                               ("assistive", "touch"), ("keyboard", "keyboard"))])
        t.section("INFORMATION")
        t.group([{"kind": "nav", "icon": "about", "label": "About", "cb": lambda: self.go(page=("about",))}])

    def choices(self, key, opts, default):
        """Nhóm hàng chọn 1 (dấu tick) lưu vào config."""
        cur = core.cfg_get(key, default)
        return [{"kind": "choice", "label": lab, "checked": cur == val,
                 "cb": lambda val=val: (core.cfg_set(key, val), self.main.render())} for val, lab in opts]

    def cfg_switch(self, label, key, default):
        var = tk.BooleanVar(value=core.cfg_get(key, default))
        self._cfgvars.append(var)                       # giữ tham chiếu
        return {"kind": "switch", "label": label, "var": var, "on_change": lambda: core.cfg_set(key, var.get())}

    def set_general(self, t):
        t.section("GENERAL")
        t.group([{"kind": "switch", "label": "Auto-check compatibility", "var": self.auto, "on_change": self.save_cfg}])
        t.footer("Checks the requirements every time the app starts.")
        t.section("INTERFACE")
        t.group([{"kind": "slider", "label": "UI delay", "stops": DELAYS, "var": self.uidelay, "h": u(70),
                  "fmt": lambda v: "Off" if v == 0 else f"{v} ms", "on_change": self.save_delay}])
        t.footer("How long a tapped row stays highlighted before the action runs. Off = instant.")
        t.section("NETWORK")
        n = sum(m["on"] for m in core.mirrors_get())
        t.group([{"kind": "nav", "label": "Mirrors", "detail": f"{n} active", "cb": lambda: self.go(page=("mirror",))}])
        t.footer("Servers used to download build tools when setting up a component.")

    # ---- trang con General > Mirrors ----
    def mlist(self):
        """Danh sách mirror đang làm việc: bản nháp khi đang Edit, ngược lại là cấu hình đã lưu."""
        return [dict(m) for m in (self.mirror_draft if self.mirror_draft is not None else core.mirrors_get())]

    def msave(self, ms):
        if self.mirror_draft is not None:
            self.mirror_draft = ms
        else:
            core.mirrors_set(ms)

    def set_mirror(self, t):
        from urllib.parse import urlparse
        editing = self.mirror_draft is not None
        ms = self.mlist()
        t.section("MSYS2 MIRRORS")
        if ms:
            rows = []
            for i, m in enumerate(ms):
                v = self.mirror_ms.get(m["url"])
                det, col = (("", kit.DETAIL) if v is None else ("Testing...", kit.DETAIL) if v == -2 else
                            ("Failed", BAD) if v < 0 else (f"{v} ms", GOOD))
                row = {"kind": "item", "label": urlparse(m["url"]).netloc or m["url"],
                       "sub": f"#{i + 1} \u00b7 " + ("Enabled" if m["on"] else "Disabled"),
                       "detail": det, "color": col, "cb": lambda i=i: self.mirror_menu(i)}
                if editing:                                   # Edit: +/- bên trái, thùng rác bên phải, bỏ cb bấm hàng
                    row.update(kind="mrow", on=m["on"], toggle=lambda i=i: self.mirror_edit(i, "toggle"),
                               trash=lambda i=i: self.mirror_edit(i, "del"))
                    del row["cb"]
                rows.append(row)
            t.group(rows)
        else:
            t.note("No mirrors: MSYS2 uses its own default servers.")
        if editing:
            t.group([{"kind": "entry", "label": "New URL", "var": self.mirror_url, "h": u(48)},
                     {"kind": "action", "label": "Add mirror", "cb": self.add_mirror}])
            t.footer("Tap \u2212 or + to disable or enable a mirror, the trash to remove it. Save keeps the changes; "
                     "going back discards them.")
            return
        t.footer("Tap a mirror to enable, disable, reorder or remove it. Higher mirrors are tried first.")
        t.section("TOOLS")
        t.group([{"kind": "action", "label": "Test speed", "cb": self.test_mirrors},
                 {"kind": "action", "label": "Apply to MSYS2 now", "cb": self.apply_mirrors},
                 {"kind": "action", "label": "Reset to defaults", "color": BAD,
                  "cb": lambda: self.confirm("Reset Mirrors", "Restore the default mirror list?", "Reset", "red",
                                             self.reset_mirrors)}])
        t.footer("Changes are used the next time build tools are installed. Apply to MSYS2 now rewrites its mirror "
                 "list immediately.")

    def mirror_menu(self, i):
        ms = self.mlist()
        if i >= len(ms):
            return
        from urllib.parse import urlparse
        btns = [("Disable" if ms[i]["on"] else "Enable", "blue", lambda: self.mirror_edit(i, "toggle"))]
        if i > 0:
            btns.append(("Move to top", "blue", lambda: self.mirror_edit(i, "top")))
        btns.append(("Remove", "red", lambda: self.mirror_edit(i, "del")))
        self.open_sheet(urlparse(ms[i]["url"]).netloc or ms[i]["url"], btns)

    def mirror_edit(self, i, op):
        ms = self.mlist()
        if i >= len(ms):
            return
        if op == "toggle":
            ms[i]["on"] = not ms[i]["on"]
        elif op == "top":
            ms.insert(0, ms.pop(i))
        else:
            ms.pop(i)
        self.msave(ms)
        core.alog(f"mirrors: {op} -> {ms[i]['url'] if op != 'del' else '(removed)'}"
                  + (" [draft]" if self.mirror_draft is not None else ""), "INFO")
        self.main.render()

    def add_mirror(self):
        url = self.mirror_url.get().strip().rstrip("/")
        if not core.MIRROR_URL_RE.fullmatch(url):
            self.notify("Invalid URL", "Enter a link starting with http:// or https://"); return
        ms = self.mlist()
        if any(m["url"].rstrip("/") == url for m in ms):
            self.notify("Already added", "This mirror is already in the list."); return
        ms.append({"url": url, "on": True})
        core.alog(f"mirrors: added {url}" + (" [draft]" if self.mirror_draft is not None else ""), "INFO")
        self.msave(ms)
        self.mirror_url.set("")
        self.main.render()

    def reset_mirrors(self):
        core.alog("mirrors: reset to defaults", "INFO")
        core.mirrors_set(None)
        self.mirror_ms.clear()
        self.main.render()

    def test_mirrors(self):
        ms = core.mirrors_get()
        core.alog(f"mirrors: testing {len(ms)} mirrors", "INFO")
        for m in ms:
            self.mirror_ms[m["url"]] = -2
        self.main.render()
        for m in ms:
            threading.Thread(target=lambda url=m["url"]: self.q.put(("mirror", (url, core.mirror_ping(url)))),
                             daemon=True).start()

    def apply_mirrors(self):
        core.alog("mirrors: applying to MSYS2", "INFO")
        if not core.BASH.exists():
            self.notify("MSYS2 not installed", "Mirrors will be applied automatically when build tools are installed.")
            return

        def work():
            try:
                rc = core.apply_mirrors()
                self.q.put(("mirrordone", "Mirror list updated." if rc == 0 else f"Failed (code {rc})."))
            except Exception as ex:
                core.alog_exc(f"mirrors: apply failed: {ex}")
                self.q.put(("mirrordone", f"Failed: {ex}"))
        threading.Thread(target=work, daemon=True).start()

    def set_keyboard(self, t):
        self._cfgvars = []
        cap = keys.capturing()
        t.section("SCREENSHOT SHORTCUT")
        t.group([{"kind": "item", "label": "Shortcut", "detail": "Press keys... (Esc cancels)" if cap
                  else keys.label(core.cfg_get("kb_shot")), "cb": self.start_capture},
                 {"kind": "action", "label": "Clear shortcut", "color": BAD, "cb": self.clear_combo}])
        t.footer("Tap Shortcut, then press the combination (e.g. Ctrl+Shift+S). It works while the VM window is focused.")
        t.section("PROTECTION")
        var = tk.BooleanVar(value=core.cfg_get("kb_block_p", False))
        self._cfgvars.append(var)
        t.group([{"kind": "switch", "label": "Disable P key", "var": var,
                  "on_change": lambda: (core.cfg_set("kb_block_p", var.get()), keys.reload())}])
        t.footer("Blocks the P key in the VM window to avoid an accidental Power press (kernel panic). "
                 "The Power button of Assistive Touch still works.")

    def set_diagnosis(self, t):
        t.section("EMULATION")
        t.group([{"kind": "switch", "label": "Log unimplemented devices", "var": self.dbg, "on_change": self.save_cfg},
                 {"kind": "switch", "label": "Save session logs", "var": self.logs, "on_change": self.save_cfg},
                 {"kind": "slider", "label": "Log size limit", "stops": LIMITS, "var": self.limit, "h": u(70),
                  "on_change": self.save_cfg}])
        t.footer("Counts the app log and session logs together. When the total goes over the limit, "
                 "the oldest logs are deleted. 0 MB means unlimited.")

    def set_screenshot(self, t):
        t.section("FILE FORMAT")
        t.group(self.choices("shot_format", [("png", "PNG"), ("bmp", "BMP")], "png"))
        t.section("QUALITY")
        t.group(self.choices("shot_scale", [(1, "Original (1x)"), (2, "High (2x)"), (3, "Ultra (3x)")], 1))
        t.footer("Enlarges the screenshot by the chosen factor.")
        t.section("COMPRESSION")
        self._cfgvars = []
        t.group([self.cfg_switch("Compress image", "shot_compress", True)])
        t.footer("PNG only: off saves faster but makes larger files. BMP is never compressed.")

    def set_assistive(self, t):
        self._cfgvars = []
        t.section("ASSISTIVE TOUCH")
        t.group([self.cfg_switch("Assistive Touch", "at_enabled", True)])
        t.footer("The floating button that appears next to the VM window. A single tap opens the menu. "
                 "Quick Media Control presses Home twice in a row.")
        acts = [("none", "None"), ("home", "Home"), ("power", "Power"), ("screenshot", "Screenshot"),
                ("media", "Quick Media Control")]
        t.section("DOUBLE TAP")
        t.group(self.choices("at_double", acts, "none"))
        t.section("TRIPLE TAP")
        t.group(self.choices("at_triple", acts, "none"))
        t.footer("When a double or triple tap action is set, a single tap waits a moment before opening the menu.")

    def page_about(self, t):
        t.section("ABOUT THE APP")
        t.group([{"kind": "value", "label": "Name", "detail": "OldRingo"},
                 {"kind": "value", "label": "Version", "detail": VERSION},
                 {"kind": "value", "label": "Runtime", "detail": f"Python {sys.version.split()[0]} / Tk {tk.TkVersion}"},
                 {"kind": "value", "label": "Data folder", "detail": str(core.BASE)}])
        t.section("ABOUT THE LIBRARY")
        t.group([{"kind": "value", "label": "Name", "detail": "qemu-ios (devos50)"},
                 {"kind": "value", "label": "Based on", "detail": (f"QEMU {core.lib_version()}"
                                                                   if core.lib_version() != "-" else "QEMU 8.2 fork")}])
        t.section("LEGAL")
        t.group([{"kind": "nav", "label": "Legal", "cb": lambda: self.go(page=("legal",))}])

    # ---- About > Legal (mô phỏng trang Legal của Apple; toàn bộ tiếng Anh) ----
    def set_legal(self, t):
        """Mô phỏng trang Legal của iOS: chữ phẳng trên nền sọc, logo ở đầu trang (toàn bộ tiếng Anh)."""
        import legal_text
        W = u(580)
        t.plain = "#f6f6f6"                                  # nền đặc, không kẻ sọc
        t.y += u(6)
        cx = (t.x1 + t.x2) // 2
        f = ("Yu Gothic UI", -u(40), "bold")
        t.create_text(cx, t.y + 1, text="Old\u308a\u3093\u3054", font=f, fill="white", anchor="n")
        i = t.create_text(cx, t.y, text="Old\u308a\u3093\u3054", font=f, fill="#8f939c", anchor="n")
        t.y = t.bbox(i)[3] + u(16)
        for para in LEGAL_NOTICES:
            t.flat_text(para, 14, True, 14, W)
        t.flat_text("License:", 14, True, 14, W)
        t.flat_text(LEGAL_GPL_INTRO, 14, True, 14, W)
        for chunk in legal_chunks(legal_text.GPL3):
            t.flat_text(chunk, 12, False, 14, W)
        t.flat_text("Acknowledgements:", 14, True, 14, W)
        t.flat_text(LEGAL_THANKS, 14, True, 14, W)
        for body in LEGAL_CREDITS:
            t.flat_text(body, 14, True, 14, W)
        t.flat_text("Authors:", 14, True, 14, W)
        t.flat_text("Ph\u00fac Power (https://github.com/PhucPower300121)\n"
                    "Developer, designer, tester and maintainer of this project.", 14, True, 14, W)
        t.y += u(10)

    # ---- How to? ----
    def page_howto(self, t):
        for title, body in HOWTO:
            t.section(title)
            t.note(body)


LEGAL_NOTICES = [
    "Legal Notices:",
    "OldRingo Launcher was developed by M\u1eaft Th\u1ea7n Team.",
    "OldRingo is an independent project. It is not affiliated with, authorized by, sponsored by, endorsed by, or in "
    "any way officially connected to Apple Inc. or any of its subsidiaries or affiliates.",
    "Apple, iPod, iPod touch, iPhone, iPhone OS, iOS and other Apple names, logos and marks are trademarks of Apple "
    "Inc., registered in the U.S. and other countries. All other trademarks are the property of their respective "
    "owners.",
    "OldRingo does not bundle any Apple software. Firmware and other files that you choose to download or provide are "
    "not part of OldRingo, and you are solely responsible for making sure that your use of them complies with the "
    "license terms and the laws that apply to you.",
    "Disclaimer:",
    "THIS SOFTWARE IS PROVIDED \u201cAS IS\u201d AND \u201cAS AVAILABLE\u201d, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR "
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE "
    "AND NON-INFRINGEMENT. IN NO EVENT SHALL M\u1eaeT TH\u1ea6N TEAM OR ITS CONTRIBUTORS BE LIABLE FOR ANY CLAIM, "
    "DAMAGES, LOSS OF DATA OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT "
    "OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. YOU USE THIS SOFTWARE AT YOUR "
    "OWN RISK."]
LEGAL_GPL_INTRO = (
    "OldRingo is free software: you can redistribute it and/or modify it under the terms of the GNU General Public "
    "License, version 3, as published by the Free Software Foundation. The full text of the license follows.")
LEGAL_THANKS = (
    "OldRingo would not be possible without the following projects and the people behind them. Thank you.")
LEGAL_CREDITS = [
    "MSYS2\nSoftware distribution and building platform for Windows \u2014 https://www.msys2.org\n\n"
    "OldRingo uses MSYS2 to install the compiler toolchain and to build the emulator. MSYS2 is a software distribution "
    "made of several independent parts, each with its own license, comparable to a Linux distribution; its package "
    "build scripts are licensed under the BSD 3-Clause \u201cNew\u201d or \u201cRevised\u201d License.",
    "QEMU-iOS\nBy Martijn de Vos (DevOS, devos50) \u2014 https://github.com/devos50/qemu-ios\n\n"
    "A fork of QEMU that emulates legacy Apple devices (iPod touch 1st and 2nd generation). OldRingo downloads and "
    "builds it. License: GNU General Public License, version 2 (some components are licensed under the GNU Lesser "
    "General Public License, version 2.1). QEMU is developed by the QEMU project \u2014 https://www.qemu.org",
    "Apple\nThank you to Apple Inc. for creating iPhone OS / iOS for the iPod touch (1st and 2nd generation). Without "
    "that software and the hardware it ran on, there would be nothing to emulate. iPod touch and iOS are trademarks of "
    "Apple Inc."]


def legal_chunks(text, limit=2200):
    """Chia văn bản giấy phép thành các thẻ ~limit ký tự. Đoạn bị ngắt cứng ở ~80 cột thì nối lại để tự xuống dòng;
    đoạn có dòng ngắn cố ý (ví dụ mẫu thông báo) giữ nguyên. Không đổi từ ngữ nào."""
    pars = []
    for raw in text.split("\n\n"):
        lines = [ln.rstrip() for ln in raw.strip("\n").splitlines() if ln.strip()]
        if not lines:
            continue
        hard = all(len(ln.strip()) >= 45 for ln in lines[:-1])
        if len(lines) > 1 and hard:
            pars.append(" ".join(ln.strip() for ln in lines))
        else:
            pars.append("\n".join(ln.strip() if len(lines) > 1 else ln.strip() for ln in lines))
    out, cur = [], []
    for p in pars:
        if cur and sum(len(x) for x in cur) + len(p) > limit:
            head = []
            while cur and len(cur[-1]) < 60:          # tiêu đề ngắn đi theo đoạn sau
                head.insert(0, cur.pop())
            if cur:
                out.append("\n\n".join(cur))
            cur = head
        cur.append(p)
    if cur:
        out.append("\n\n".join(cur))
    return out


SET_TITLES = {"general": "General", "diagnosis": "Diagnosis", "screenshot": "Screenshot",
              "assistive": "Assistive Touch", "keyboard": "Keyboard", "mirror": "Mirrors", "about": "About",
              "legal": "Legal"}

HOWTO = [
    ("1. SET UP THE ENVIRONMENT",
     "Open System > Requirements. If MSYS2 or the build packages are missing, tap Set Up (or accept the prompt "
     "at startup). The app downloads MSYS2 and installs the build packages automatically. Wait until every "
     "item shows as ready; progress is shown in System > Log."),
    ("2. DOWNLOAD THE HARDWARE",
     "Open System > Hardware, tap the \u2022\u2022\u2022 button next to a device (iPod touch 1G / 2G) and choose Install. "
     "The app downloads the source and compiles the emulator. This takes 30-90 minutes, so keep the app open."),
    ("3. DOWNLOAD THE FIRMWARE",
     "In the same page, tap \u2022\u2022\u2022 next to a firmware and choose Download. You can also pick your own "
     "files with Custom firmware when creating a profile."),
    ("4. CREATE A PROFILE",
     "Go to Profile > + Add. Choose a name, the hardware, the firmware and the memory size, then tap Save."),
    ("5. RUN THE VM",
     "Open the profile and tap Run. A QEMU window and a terminal window will appear. "
     "Turn on Settings > Diagnosis > Save session logs if you want the output saved to System > Log."),
    ("6. CONTROLS INSIDE THE VM",
     "Mouse: use the mouse instead of your finger on the touch screen (click = tap, drag = swipe).\n"
     "H key: go to the Home screen.\n"
     "P key: power button.\n"
     "Floating button: appears next to the VM window. Drag it to move it, tap it for Home / Power / Screenshot. "
     "Screenshots are saved to the Gallery tab."),
    ("WARNING ABOUT THE P KEY",
     "On a real device, the power button turns the screen off and locks it. The VM is still incomplete because of "
     "Apple's hardware design, so pressing P currently makes the VM panic. Avoid pressing P for now."),
]


if __name__ == "__main__":
    App().mainloop()
