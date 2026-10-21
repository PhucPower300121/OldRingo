"""Phím tắt toàn cục (hook bàn phím mức thấp, chỉ Windows): tổ hợp chụp screenshot + chặn phím P khi cửa sổ VM đang focus."""
import ctypes, threading, time
from ctypes import wintypes

import core

user32 = ctypes.windll.user32
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


class KBD(ctypes.Structure):
    _fields_ = [("vk", wintypes.DWORD), ("sc", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


MODS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C}
NAMES = {0x20: "Space", 0x0D: "Enter", 0x09: "Tab", 0x08: "Backspace", 0x2E: "Delete", 0x2D: "Insert",
         0x24: "Home", 0x23: "End", 0x21: "PageUp", 0x22: "PageDown", 0x25: "Left", 0x26: "Up",
         0x27: "Right", 0x28: "Down", 0x2C: "PrtSc"}

_st = dict(combo=None, block_p=False, cap_until=0.0)
_cb = [None]          # callback(kind) chạy ở luồng hook: "shot" | "captured"
_started = [False]


def reload():
    _st["combo"] = core.cfg_get("kb_shot")
    _st["block_p"] = bool(core.cfg_get("kb_block_p", False))


def label(combo):
    if not combo:
        return "Not set"
    vk = combo["vk"]
    k = NAMES.get(vk) or (f"F{vk - 0x6F}" if 0x70 <= vk <= 0x87 else chr(vk) if 0x30 <= vk <= 0x5A else f"Key {vk:#x}")
    return "+".join([m for m, f in (("Ctrl", "ctrl"), ("Alt", "alt"), ("Shift", "shift")) if combo.get(f)] + [k])


def capture(on=True):
    _st["cap_until"] = time.time() + 8 if on else 0.0


def capturing():
    return time.time() < _st["cap_until"]


def _down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _vm_focused():
    buf = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 128)
    return buf.value.startswith("QEMU")


def _proc(n, wp, lp):
    if n == 0:
        k = ctypes.cast(lp, ctypes.POINTER(KBD)).contents
        if not k.flags & 0x10 and k.vk not in MODS:               # bỏ qua phím do app tự gửi (Home/Power)
            vk, down = k.vk, wp in (0x100, 0x104)
            cur = dict(vk=vk, ctrl=_down(0x11), alt=_down(0x12), shift=_down(0x10))
            if capturing():
                if down:
                    _st["cap_until"] = 0.0
                    if vk != 0x1B:                               # Esc = huỷ
                        core.cfg_set("kb_shot", cur); reload()
                        core.alog(f"keyboard: screenshot shortcut set to {label(cur)}", "INFO")
                    else:
                        core.alog("keyboard: shortcut capture cancelled", "INFO")
                    if _cb[0]:
                        _cb[0]("captured")
                return 1
            c = _st["combo"]
            if c and vk == c["vk"] and all(cur[m] == bool(c.get(m)) for m in ("ctrl", "alt", "shift")) and _vm_focused():
                if down and _cb[0]:
                    _cb[0]("shot")
                return 1
            if vk == 0x50 and _st["block_p"] and _vm_focused():
                if down:
                    core.alog("keyboard: P key blocked in the VM window", "DEBUG")
                return 1
    return user32.CallNextHookEx(None, n, wp, lp)


def start(callback):
    if _started[0]:
        return
    _started[0] = True
    _cb[0] = callback
    reload()

    def run():
        proc = HOOKPROC(_proc)                                   # giữ tham chiếu
        hook = user32.SetWindowsHookExW(13, proc, None, 0)
        core.alog("keyboard hook " + ("installed" if hook else "FAILED to install"), "INFO" if hook else "ERROR")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg)); user32.DispatchMessageW(ctypes.byref(msg))
    threading.Thread(target=run, daemon=True).start()
