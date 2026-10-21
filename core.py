"""Logic thuần (không GUI) của OldRingo launcher. GUI nào cũng gọi được."""
import ctypes, json, os, re, shutil, socket, stat, struct, subprocess, sys, threading, time, urllib.request, zipfile, zlib
from dataclasses import dataclass
from pathlib import Path

BASE = Path(r"C:\qemu-ios")
MSYS = Path(r"C:\msys64")
BASH = MSYS / "usr/bin/bash.exe"
SRC = BASE / "src"
FW = BASE / "firmware"
REPO = "https://github.com/devos50/qemu-ios.git"
BRANCH = "ipod_touch_2g"
RELEASE_API = "https://api.github.com/repos/devos50/qemu-ios/releases/tags/{tag}"
MSYS_INSTALLER = "https://github.com/msys2/msys2-installer/releases/latest/download/msys2-x64-latest.exe"
PKGS = ("git make mingw-w64-x86_64-ninja mingw-w64-x86_64-gcc mingw-w64-x86_64-glib2 "
        "mingw-w64-x86_64-pixman mingw-w64-x86_64-SDL2 mingw-w64-x86_64-openssl "
        "mingw-w64-x86_64-pkgconf mingw-w64-x86_64-python mingw-w64-x86_64-python-pip "
        "mingw-w64-x86_64-python-setuptools mingw-w64-x86_64-python-distlib mingw-w64-x86_64-meson")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = {"User-Agent": "qemu-ios-launcher"}

# Mirror MSYS2 dự phòng (mặc định hay bị 403/chậm ở VN): được thêm lên đầu mirrorlist của pacman.
DEFAULT_MIRRORS = ["https://mirrors.tuna.tsinghua.edu.cn/msys2", "https://mirrors.ustc.edu.cn/msys2",
                   "https://mirrors.bfsu.edu.cn/msys2", "https://mirror.sjtu.edu.cn/msys2",
                   "https://mirror.yandex.ru/mirrors/msys2", "https://mirror.selfnet.de/msys2"]
MIRROR_URL_RE = re.compile(r"https?://[A-Za-z0-9._~:/%-]+")


def mirrors_get():
    """Danh sách mirror [{url, on}] theo thứ tự ưu tiên; chưa cấu hình thì dùng mặc định."""
    ms = cfg_get("mirrors")
    if not isinstance(ms, list):
        return [{"url": m, "on": True} for m in DEFAULT_MIRRORS]
    return [{"url": str(m["url"]), "on": bool(m.get("on", True))} for m in ms
            if isinstance(m, dict) and MIRROR_URL_RE.fullmatch(str(m.get("url", "")))]


def mirrors_set(ms):
    cfg_set("mirrors", ms)          # None = quay về mặc định


def mirror_ping(url, timeout=6):
    """Thời gian phản hồi (ms) của mirror, -1 nếu lỗi."""
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url.rstrip("/") + "/", headers=UA), timeout=timeout) as r:
            r.read(1024)
        return int((time.perf_counter() - t0) * 1000)
    except Exception:
        return -1


def mirrors_sh():
    """Script chèn các mirror đang bật lên đầu mirrorlist; chạy lại sẽ thay khối cũ."""
    ms = " ".join(m["url"].rstrip("/") for m in mirrors_get() if m["on"])
    return ("cd /etc/pacman.d\n" f'MIRRORS="{ms}"\n' + r"""for f in mirrorlist.mingw32 mirrorlist.mingw64 mirrorlist.ucrt64 mirrorlist.clang64 mirrorlist.clangarm64 mirrorlist.msys; do
  [ -f $f ] || continue
  case $f in
    mirrorlist.msys) sub='msys/$arch';;
    mirrorlist.mingw32) sub=mingw/i686;;
    mirrorlist.mingw64) sub=mingw/mingw64;;
    mirrorlist.ucrt64) sub=mingw/ucrt64;;
    mirrorlist.clang64) sub=mingw/clang64;;
    mirrorlist.clangarm64) sub=mingw/clangarm64;;
  esac
  awk '/^# qemu-ios-mirrors/{s=1;next} s&&/^Server = /{next} {s=0;print}' $f > $f.tmp && mv $f.tmp $f
  [ -n "$MIRRORS" ] || continue
  { echo '# qemu-ios-mirrors'; for m in $MIRRORS; do echo "Server = $m/$sub"; done; cat $f; } > $f.new && mv $f.new $f
done
""")


def apply_mirrors(log=None):
    """Ghi lại mirrorlist của MSYS2 theo cấu hình hiện tại. Trả về returncode."""
    if not BASH.exists():
        raise RuntimeError("MSYS2 is not installed.")
    _write_sh("mirrors.sh", mirrors_sh())
    return msys_run("/c/qemu-ios/mirrors.sh", log)


@dataclass
class Check:
    key: str      # msys | pkgs | src | build | fw | res
    label: str
    ok: bool
    required: bool = True
    detail: str = ""


# ---------- tiện ích ----------
def _msys_env():
    e = os.environ.copy()
    e.update(MSYSTEM="MINGW64", CHERE_INVOKING="1")
    return e


def msys_run(cmd, log=None):
    """Chạy lệnh trong MSYS2 mingw64, stream output về log(). Trả về returncode."""
    alog(f"msys_run: {cmd}", "DEBUG")
    p = subprocess.Popen([str(BASH), "-lc", cmd], env=_msys_env(), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", creationflags=NOWIN)
    for line in p.stdout:
        if log:
            log(line.rstrip())
    rc = p.wait()
    alog(f"msys_run exited with code {rc}: {cmd}", "DEBUG" if rc == 0 else "WARN")
    return rc


def _write_sh(name, text):
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / name).write_text(text, encoding="utf-8", newline="\n")


def download(url, dest, log=print):
    log(f"Downloading {Path(dest).name} ...")
    alog(f"download: {url} -> {dest}", "DEBUG")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, -1
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total and done * 10 // total != last:
                last = done * 10 // total
                log(f"  {done * 100 // total}%")
    alog(f"download finished: {Path(dest).name} ({done} bytes)", "DEBUG")


# ---------- danh mục phần cứng / firmware ----------
HARDWARE = {   # build từ nhánh git `branch` của repo qemu-ios vào thư mục riêng `dir`
    "n72ap": dict(name="iPod touch 2G", model="N72AP", chip="S5L8720", branch="ipod_touch_2g",
                  dir="src", files=("bootrom", "nor", "nand"), ram=("1G", "2G", "4G"), default_ram="2G"),
    "n45ap": dict(name="iPod touch 1G", model="N45AP", chip="S5L8900", branch="ipod_touch_1g",
                  dir="src_1g", files=("bootrom", "iboot", "nor", "nand"), ram=("1G",), default_ram="1G"),
}
FIRMWARE = {   # bộ file tải từ GitHub release `tag` của repo qemu-ios
    "os2": dict(name="iPhone OS 2", version="2.1.1", hw="n72ap", tag="n72ap_v1"),
    "os1": dict(name="iPhone OS 1", version="1.0", hw="n45ap", tag="n45ap_v1"),
}

CONFIG = BASE / "config.json"


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def cfg_get(key, default=None):
    return load_config().get(key, default)


def cfg_set(key, value):
    BASE.mkdir(parents=True, exist_ok=True)
    cfg = load_config(); cfg[key] = value
    CONFIG.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    alog(f"config set: {key} = {str(value)[:200]}", "DEBUG")


def hw_src(hid):
    return BASE / HARDWARE[hid]["dir"]


def lib_version():
    for hid in HARDWARE:
        try:
            return (hw_src(hid) / "VERSION").read_text().strip()
        except Exception:
            pass
    return "-"


def _rmtree(path):
    def onerr(func, p, _exc):          # file .git/readonly trên Windows
        os.chmod(p, stat.S_IWRITE); func(p)
    shutil.rmtree(path, onerror=onerr)


# ---------- phần cứng ----------
def find_qemu(hid="n72ap"):
    src = hw_src(hid)
    for p in (src / "build/qemu-system-arm.exe", src / "build/arm-softmmu/qemu-system-arm.exe"):
        if p.exists():
            return p
    return None


def hw_installed(hid):
    return find_qemu(hid) is not None


# ---------- firmware ----------
def _scan(root, maxdepth=4):
    """Quét nông, không đi vào thư mục 'nand' (rất nhiều file)."""
    files, dirs = [], []
    base = len(root.parts)
    for dp, dn, fn in os.walk(root):
        dpp = Path(dp)
        files += [dpp / f for f in fn]
        for d in list(dn):
            dirs.append(dpp / d)
            if d.lower() == "nand":
                dn.remove(d)
        if len(dpp.parts) - base >= maxdepth:
            dn[:] = []
    return files, dirs


def discover(root, files=("bootrom", "nor", "nand")):
    """Tự nhận các file/thư mục trong `files` (bootrom, iboot, nor, nand) bên trong root."""
    r = {k: "" for k in files}
    root = Path(root)
    if not root.exists():
        return r
    fl, dirs = _scan(root)
    fl = [p for p in fl if p.suffix.lower() != ".zip"]
    low = lambda p: p.name.lower()
    if "bootrom" in r:
        r["bootrom"] = next((str(p) for p in fl if any(k in low(p) for k in ("bootrom", "s5l8720", "s5l8900"))), "")
    if "iboot" in r:
        r["iboot"] = next((str(p) for p in fl if "iboot" in low(p)), "")
    if "nand" in r:
        r["nand"] = next((str(d) for d in dirs if low(d) == "nand"), "")
    if "nor" in r:
        nor = next((p for p in fl if "nor" in low(p) and low(p).endswith(".bin")), None) \
            or next((p for p in fl if "nor" in low(p) and "nand" not in low(p)
                     and str(p) not in (r.get("bootrom"), r.get("iboot"))), None) \
            or next((d for d in dirs if low(d) == "nor"), None)
        r["nor"] = str(nor) if nor else ""
    return r


def fw_files(fid):
    return HARDWARE[FIRMWARE[fid]["hw"]]["files"]


def fw_paths(fid):
    return discover(FW / fid, fw_files(fid))


def fw_downloaded(fid):
    return all(fw_paths(fid).values())


def migrate_legacy():
    """Bản cũ để firmware thẳng trong firmware\\ -> chuyển vào firmware\\os2\\."""
    if not FW.exists() or (FW / "os2").exists():
        return
    old = [p for p in FW.iterdir() if p.name not in ("os1", "os2")]
    if old:
        (FW / "os2").mkdir()
        for p in old:
            shutil.move(str(p), str(FW / "os2" / p.name))


# ---------- profile ----------
def profiles_load():
    ps = cfg_get("profiles")
    if ps is None:   # lần đầu: tạo sẵn profile iPod touch 2G / iPhone OS 2
        ps = [{"id": "p1", "name": "iPod touch 2G", "hw": "n72ap", "fw": "os2", "custom": {},
               "ram": cfg_get("ram", "2G")}]
        cfg_set("profiles", ps)
    return ps


def profiles_save(ps):
    cfg_set("profiles", ps)


def new_profile_id():
    return f"p{int(time.time() * 1000)}"


def profile_paths(p):
    if p["fw"] == "custom":
        c = p.get("custom", {})
        return {k: c.get(k, "") for k in HARDWARE[p["hw"]]["files"]}
    return fw_paths(p["fw"])


def profile_issues(p):
    out = []
    if not hw_installed(p["hw"]):
        out.append("Hardware not installed")
    if not all(v and os.path.exists(v) for v in profile_paths(p).values()):
        out.append("Firmware missing")
    return out


# ---------- kiểm tra hệ thống ----------
def _ram_gb():
    class MS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("m", ctypes.c_ulong)] + [(f"x{i}", ctypes.c_ulonglong) for i in range(7)]
    s = MS(); s.l = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
    return s.x0 / 2**30


def pkgs_ok():
    db = MSYS / "var/lib/pacman/local"
    if not db.exists():
        return False
    names = [p.name for p in db.iterdir()]
    for pkg in PKGS.split():
        if not any(n.startswith(pkg + "-") and n[len(pkg) + 1:len(pkg) + 2].isdigit() for n in names):
            return False
    return True


def get_status():
    ram, free = _ram_gb(), shutil.disk_usage("C:\\").free / 2**30
    res_ok = ram >= 3.5 and free >= 10   # máy 4GB thường báo ~3.7-3.9GB
    msys = BASH.exists()
    return [
        Check("res", "Computer resources", res_ok, required=False,
              detail=f"RAM {ram:.1f} GB, {free:.0f} GB free"),
        Check("msys", "MSYS2 (C:\\msys64)", msys),
        Check("pkgs", "Build packages", msys and pkgs_ok()),
    ]


def is_ready(status):
    return all(c.ok for c in status if c.required)


# ---------- cài / gỡ ----------
def install_toolchain(log=print):
    BASE.mkdir(parents=True, exist_ok=True)
    if not BASH.exists():
        log("[1/3] Installing MSYS2...")
        inst = Path(__file__).parent / "msys2.exe"  # bộ cài có sẵn cùng thư mục
        if inst.exists():
            log(f"Using the bundled installer: {inst}")
        else:
            inst = Path(os.environ.get("TEMP", ".")) / "msys2.exe"
            try:
                download(MSYS_INSTALLER, inst, log)
            except Exception as e:
                raise RuntimeError(f"Could not download MSYS2 ({e}). Put msys2.exe next to app.py and try again.")
        subprocess.run([str(inst), "in", "--confirm-command", "--accept-messages", "--root", "C:/msys64"], check=False)
        if not BASH.exists():
            raise RuntimeError("MSYS2 installation failed (try running again as Administrator).")
    if not pkgs_ok():
        log("[2/3] Installing build packages...")
        _write_sh("pkgs.sh", mirrors_sh() + "for i in 1 2 3; do\n"
                  f"  pacman -Sy --noconfirm --needed base-devel mingw-w64-x86_64-toolchain {PKGS} && break\n"
                  "  [ $i = 3 ] && exit 1\n  echo 'Retrying...'\ndone\n")
        if msys_run("/c/qemu-ios/pkgs.sh", log):
            raise RuntimeError("Package installation failed.")


def install_hardware(hid, log=print):
    hw = HARDWARE[hid]
    d = hw["dir"]
    if find_qemu(hid):
        log(f"{hw['name']} is already installed."); return
    install_toolchain(log)
    src = hw_src(hid)
    if not (src / "configure").exists():
        log(f"[3/3] Downloading {hw['name']} source (branch {hw['branch']})...")
        _write_sh(f"clone_{hid}.sh", f"set -e\nrm -rf /c/qemu-ios/{d}\n"
                  f"git clone --depth 1 -b {hw['branch']} {REPO} /c/qemu-ios/{d}\n")
        if msys_run(f"/c/qemu-ios/clone_{hid}.sh", log):
            raise RuntimeError("Clone failed.")
    if not find_qemu(hid):
        log(f"Building {hw['name']} (30-90 minutes, please wait)...")
        _write_sh(f"build_{hid}.sh", f"""set -e
cd /c/qemu-ios/{d}
rm -rf build/pyvenv
mkdir -p build && cd build
[ -f build.ninja ] || ../configure --enable-sdl --disable-cocoa --target-list=arm-softmmu --disable-capstone --disable-slirp --disable-pie --extra-cflags=-I/mingw64/include/openssl --extra-ldflags='-L/mingw64/lib -lcrypto' --disable-stack-protector --disable-werror
ninja -j$(nproc) qemu-system-arm.exe
""")
        if msys_run(f"/c/qemu-ios/build_{hid}.sh", log):
            raise RuntimeError("Build failed, see the log.")
        if not find_qemu(hid):
            raise RuntimeError("qemu-system-arm.exe not found after the build.")
    log("DONE.")


def uninstall_hardware(hid, log=print):
    log(f"Uninstalling {HARDWARE[hid]['name']}...")
    if hw_src(hid).exists():
        _rmtree(hw_src(hid))
    log("DONE.")


def _size(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def _strip_source(src, exe):
    """Xoá toàn bộ source, chỉ giữ lại file emulator đã build (và VERSION)."""
    keep = BASE / f".keep_{src.name}"
    if keep.exists():
        _rmtree(keep)
    keep.mkdir(parents=True)
    shutil.move(str(exe), str(keep / exe.name))
    ver = src / "VERSION"
    if ver.exists():
        shutil.copy(ver, keep / "VERSION")
    _rmtree(src)
    exe.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(keep / exe.name), str(exe))
    if (keep / "VERSION").exists():
        shutil.copy(keep / "VERSION", src / "VERSION")
    _rmtree(keep)


def cleanup(log=print):
    """Dọn file chỉ dùng cho quá trình cài: zip nand đã giải nén, file tạm, source đã build."""
    freed = 0

    def drop(path, what):
        nonlocal freed
        try:
            n = _size(path)
            (_rmtree if Path(path).is_dir() else Path.unlink)(path)
            freed += n
            log(f"  - {what}")
        except Exception as e:
            log(f"  ! skipped {what}: {e}")

    log("Cleaning up extracted firmware zips...")
    for fid in FIRMWARE:
        d = FW / fid
        for z in (d.glob("*.zip") if d.exists() else []):
            if (d / z.stem).exists():
                drop(z, z.name)
    log("Cleaning up temporary files...")
    for f in list(BASE.glob("*.sh")) + [Path(os.environ.get("TEMP", ".")) / "msys2.exe"]:
        if f.exists():
            drop(f, f.name)
    cache = MSYS / "var/cache/pacman/pkg"
    n = sum(1 for f in (cache.glob("*") if cache.exists() else []) if f.is_file())
    if n:
        for f in cache.glob("*"):
            if f.is_file():
                try:
                    freed += f.stat().st_size; f.unlink()
                except Exception:
                    pass
        log(f"  - MSYS2 package cache ({n} files)")
    log("Cleaning up qemu-ios source code...")
    for hid, hw in HARDWARE.items():
        src, exe = hw_src(hid), find_qemu(hid)
        if not src.exists():
            continue
        if not exe:
            log(f"  ! keeping {hw['name']}: build not finished"); continue
        try:
            before = _size(src)
            _strip_source(src, exe)
            freed += before - _size(src)
            log(f"  - source {hw['name']}")
        except Exception as e:
            log(f"  ! skipped source {hw['name']}: {e}")
    log(f"DONE. Freed {freed / 2**30:.2f} GB.")


def download_firmware(fid, log=print):
    fw = FIRMWARE[fid]
    dest = FW / fid
    dest.mkdir(parents=True, exist_ok=True)
    log(f"Downloading firmware {fw['name']} (release {fw['tag']})...")
    rel = json.load(urllib.request.urlopen(urllib.request.Request(RELEASE_API.format(tag=fw["tag"]), headers=UA)))
    for a in rel["assets"]:
        out = dest / a["name"]
        if not out.exists() and not (out.suffix == ".zip" and (dest / out.stem).exists()):
            download(a["browser_download_url"], out, log)
        if out.suffix == ".zip" and out.exists() and not (dest / out.stem).exists():
            with zipfile.ZipFile(out) as z:
                z.extractall(dest / out.stem)
    if not fw_downloaded(fid):
        log(f"Could not auto-detect all required files in {dest}.")
    log("DONE.")


def delete_firmware(fid, log=print):
    log(f"Deleting firmware {FIRMWARE[fid]['name']}...")
    if (FW / fid).exists():
        _rmtree(FW / fid)
    log("DONE.")


def setup(log=print):
    """Thiết lập tự động: CHỈ cài MSYS2 + gói biên dịch. Phần cứng / firmware cài riêng."""
    install_toolchain(log)
    log("DONE.")


# ---------- chạy ----------
LOGS = BASE / "logs"


def new_log_path(profile):
    LOGS.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.-]+", "_", profile["name"]).strip("_")[:40] or "profile"
    return LOGS / f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.log"


APP_LOG_DIR = BASE / "app-logs"      # log của app nằm thư mục riêng, tách khỏi log phiên (LOGS)
APP_LOG = APP_LOG_DIR / "app.txt"
try:                                  # chuyển file cũ (logs/app.txt) sang thư mục mới
    _old = LOGS / "app.txt"
    if _old.exists() and not APP_LOG.exists():
        APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        _old.replace(APP_LOG)
except OSError:
    pass


def _stamp():
    t = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}"


def app_log_write(line, level=None):
    """Ghi log của app, mỗi dòng kèm timestamp (ms) và mức [LEVEL]. Trả về các dòng đã định dạng để hiển thị."""
    shown = []
    try:
        APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(APP_LOG, "a", encoding="utf-8", errors="replace") as f:
            for ln in (str(line).splitlines() or [""]):
                text = f"[{level}] {ln}" if level else ln
                ts = _stamp()
                f.write(f"{ts}\t{text}\n")
                shown.append(f"{ts}  {text}")
    except OSError:
        pass
    return shown


def alog(msg, level="INFO"):
    """Log có cấu trúc của app (DEBUG / INFO / WARN / ERROR / TASK)."""
    return app_log_write(msg, level)


def alog_exc(msg):
    """Ghi lỗi kèm traceback của exception đang xử lý."""
    import traceback
    return app_log_write(f"{msg}\n{traceback.format_exc().rstrip()}", "ERROR")


def app_log_read():
    """[(mốc thời gian, nội dung)] theo thứ tự ghi."""
    if not APP_LOG.exists():
        return []
    out = []
    for ln in APP_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        ts, _, txt = ln.partition("\t")
        out.append((ts, txt))
    return out


def session_logs():
    """Các file log phiên chạy, mới nhất trước."""
    return sorted(LOGS.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True) if LOGS.exists() else []


def session_start(path):
    """Mốc bắt đầu phiên (từ tên file; không có thì dùng mtime)."""
    m = re.search(r"_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$", Path(path).stem)
    if m:
        return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}:{m[6]}"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(Path(path).stat().st_mtime))


def session_label(path):
    m = re.match(r"(.+)_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$", Path(path).stem)
    return f"{m[1]} - {m[2]}-{m[3]}-{m[4]} {m[5]}:{m[6]}:{m[7]}" if m else Path(path).stem


def read_all(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def clear_logs():
    for p in session_logs() + [APP_LOG]:
        try:
            p.unlink()
        except OSError:
            pass


def _tee_main(argv):
    """Chế độ phụ (chạy trong cửa sổ terminal mới): chạy QEMU, hiển thị output như thường
    và đồng thời ghi vào file log. argv = [logfile, "--", *lệnh qemu]."""
    logfile, cmd = argv[0], argv[2:]
    with open(logfile, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}\n# {' '.join(cmd)}\n\n"); lf.flush()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = getattr(sys.stdout, "buffer", None)
        while True:
            chunk = p.stdout.read1(4096)
            if not chunk:
                break
            if out:
                out.write(chunk); out.flush()
            lf.write(chunk.decode("utf-8", errors="replace")); lf.flush()
        rc = p.wait()
        lf.write(f"\n# exit code {rc}\n")
    if rc:
        print(f"\nQEMU exited with code {rc}. Log: {logfile}")
        input("Press Enter to close...")

def launch(hid, paths, ram, debug=True, log_path=None, monitor_port=None):
    exe = find_qemu(hid)
    if not exe:
        raise RuntimeError(f"{HARDWARE[hid]['name']} is not installed.")
    env = os.environ.copy()
    env["PATH"] = f"{MSYS / 'mingw64/bin'};{env['PATH']}"
    f = lambda p: str(p).replace("\\", "/")
    if hid == "n45ap":      # iPod touch 1G: bootrom + iboot + nand, NOR đưa qua -pflash
        machine = f"iPod-Touch,bootrom={f(paths['bootrom'])},iboot={f(paths['iboot'])},nand={f(paths['nand'])}"
        extra = ["-pflash", f(paths["nor"])]
    else:                   # iPod touch 2G
        machine = f"iPod-Touch,bootrom={f(paths['bootrom'])},nand={f(paths['nand'])},nor={f(paths['nor'])}"
        extra = []
    args = [str(exe), "-M", machine, "-serial", "mon:stdio", "-cpu", "max", "-m", ram]
    args += ["-d", "unimp"] if debug else []
    args += extra
    if monitor_port:    # monitor TCP riêng để chụp màn hình (screendump)
        args += ["-monitor", f"tcp:127.0.0.1:{monitor_port},server,nowait"]
    if log_path:    # chạy qua bộ "tee": vẫn có cửa sổ terminal, đồng thời lưu log
        py = Path(sys.executable)
        if py.name.lower() == "pythonw.exe" and py.with_name("python.exe").exists():
            py = py.with_name("python.exe")
        args = [str(py), str(Path(__file__).resolve()), "--tee", str(log_path), "--"] + args
    alog(f"launch {hid}: {' '.join(args)}", "INFO")
    return subprocess.Popen(args, cwd=exe.parent, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)


if __name__ == "__main__" and len(sys.argv) > 2 and sys.argv[1] == "--tee":
    _tee_main(sys.argv[2:])


# ---------- screenshot / gallery ----------
GALLERY = BASE / "gallery"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _hmp(port, cmd, timeout=4):
    """Gửi 1 lệnh tới QEMU monitor (TCP), trả về output."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.settimeout(timeout)

        def until_prompt():
            buf = b""
            try:
                while b"(qemu)" not in buf:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
            except socket.timeout:
                pass
            return buf
        until_prompt()
        s.sendall(cmd.encode() + b"\r\n")
        return until_prompt().decode("utf-8", errors="replace")


def read_ppm(src):
    """Đọc ảnh PPM (P6) của QEMU -> (w, h, bytes RGB)."""
    return parse_ppm(Path(src).read_bytes())


def parse_ppm(data):
    pos, toks = 0, []
    while len(toks) < 4 and pos < len(data):
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        st = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        toks.append(data[st:pos])
    if len(toks) < 4 or toks[0] != b"P6":
        raise RuntimeError("Invalid screenshot.")
    w, h, pos = int(toks[1]), int(toks[2]), pos + 1
    return w, h, data[pos:pos + w * h * 3]


def _png(w, h, rows, compress):
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9 if compress else 0)) + chunk(b"IEND", b""))


def _swap_rb(r):
    b = bytearray(r)
    b[0::3], b[2::3] = r[2::3], r[0::3]
    return bytes(b)


def _bmp(w, h, rows):
    pad = b"\x00" * ((-w * 3) % 4)
    body = b"".join(_swap_rb(r) + pad for r in reversed(rows))
    return (b"BM" + struct.pack("<IHHI", 54 + len(body), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(body), 2835, 2835, 0, 0) + body)


def bmp_to_ppm(path):
    """Đọc BMP 24-bit do app tạo -> PPM (để Tk hiển thị được)."""
    d = Path(path).read_bytes()
    off = struct.unpack_from("<I", d, 10)[0]
    w, h = struct.unpack_from("<ii", d, 18)
    stride, rows = (w * 3 + 3) // 4 * 4, []
    for y in range(abs(h)):
        rows.append(_swap_rb(d[off + y * stride: off + y * stride + w * 3]))
    if h > 0:
        rows.reverse()
    return b"P6\n%d %d\n255\n" % (w, abs(h)) + b"".join(rows)


def save_image(dst, w, h, rows, fmt="png", compress=True):
    Path(dst).write_bytes(_bmp(w, h, rows) if fmt == "bmp" else _png(w, h, rows, compress))


def load_rgb(path):
    """Đọc ảnh PNG/BMP do app tạo -> (w, h, bytes RGB)."""
    p = Path(path)
    if p.suffix.lower() == ".bmp":
        return parse_ppm(bmp_to_ppm(p))
    d = p.read_bytes()
    pos, idat, w, h, spec = 8, b"", 0, 0, None
    while pos < len(d):
        n, t = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + n]
        pos += 12 + n
        if t == b"IHDR":
            w, h, bd, ct = struct.unpack(">IIBB", body[:10])
            spec = (bd, ct)
        elif t == b"IDAT":
            idat += body
    if spec != (8, 2):
        raise RuntimeError("Unsupported image format.")
    raw, stride, rows = zlib.decompress(idat), w * 3 + 1, []
    for y in range(h):
        row = raw[y * stride:(y + 1) * stride]
        if row[0] != 0:
            raise RuntimeError("Unsupported image format.")
        rows.append(row[1:])
    return w, h, b"".join(rows)


def image_size(path):
    d = Path(path).read_bytes()[:32]
    if d[:2] == b"BM":
        return struct.unpack_from("<ii", d, 18)[0], abs(struct.unpack_from("<ii", d, 18)[1])
    return struct.unpack(">II", d[16:24])


def save_shot(src, dst, fmt="png", compress=True, scale=1):
    w, h, pix = read_ppm(src)
    rows = [pix[y * w * 3:(y + 1) * w * 3] for y in range(h)]
    if scale > 1:
        rows = [r2 for r in rows for r2 in [b"".join(r[k:k + 3] * scale for k in range(0, len(r), 3))] * scale]
        w, h = w * scale, h * scale
    save_image(dst, w, h, rows, fmt, compress)


def vm_screenshot(port, meta=None):
    """Chụp màn hình VM đang chạy -> lưu vào gallery theo cài đặt Screenshot, trả về đường dẫn."""
    GALLERY.mkdir(parents=True, exist_ok=True)
    fmt = cfg_get("shot_format", "png")
    fmt = fmt if fmt in ("png", "bmp") else "png"
    stem = time.strftime("Screenshot_%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
    ppm, out = GALLERY / f"{stem}.ppm", GALLERY / f"{stem}.{fmt}"
    _hmp(port, f"screendump {ppm.as_posix()}")
    last = -1
    for _ in range(60):
        n = ppm.stat().st_size if ppm.exists() else 0
        if n and n == last:
            break
        last = n
        time.sleep(0.05)
    else:
        alog(f"screenshot failed: screendump file never appeared ({ppm})", "ERROR")
        raise RuntimeError("Could not capture the VM screen.")
    try:
        save_shot(ppm, out, fmt, bool(cfg_get("shot_compress", True)), int(cfg_get("shot_scale", 1)))
    finally:
        try:
            ppm.unlink()
        except OSError:
            pass
    meta_set(out.name, {**(meta or {}), "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    alog(f"screenshot saved: {out} ({out.stat().st_size} bytes, format {fmt})", "INFO")
    return out


def gallery_list():
    if not GALLERY.exists():
        return []
    return sorted([*GALLERY.glob("*.png"), *GALLERY.glob("*.bmp")], key=lambda p: p.stat().st_mtime, reverse=True)


def gallery_delete(path):
    try:
        Path(path).unlink()
    except OSError:
        pass
    meta_drop(Path(path).name)


# ---------- metadata ảnh (file meta.json trong gallery) ----------
_META_LOCK = threading.Lock()


def meta_all():
    try:
        return json.loads((GALLERY / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _meta_write(m):
    GALLERY.mkdir(parents=True, exist_ok=True)
    (GALLERY / "meta.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def meta_get(name):
    return meta_all().get(name)


def meta_set(name, data):
    with _META_LOCK:
        m = meta_all()
        m[name] = data
        _meta_write(m)


def meta_drop(name):
    with _META_LOCK:
        m = meta_all()
        if m.pop(name, None) is not None:
            _meta_write(m)


def photo_props(path):
    """Danh sách (nhãn, giá trị) hiển thị trong Properties."""
    p = Path(path)
    st = p.stat()
    w, h = image_size(p)
    size = f"{st.st_size / 1048576:.2f} MB" if st.st_size >= 1048576 else f"{max(1, st.st_size // 1024)} KB"
    m = meta_get(p.name) or {}
    rows = [("Name", p.name), ("Format", p.suffix[1:].upper()), ("Dimensions", f"{w} x {h}"), ("Size", size),
            ("Date", m.get("time") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)))]
    for k, lab in (("profile", "Profile"), ("device", "Device"), ("firmware", "Firmware"), ("app", "App")):
        if m.get(k):
            rows.append((lab, m[k]))
    if not m:
        rows.append(("Metadata", "None"))
    return rows


PANIC_RE = re.compile(rb"Debugger message:|Waiting for remote debugger connection")


def temp_session_log():
    """Log tạm để phát hiện panic khi người dùng tắt 'Save session logs'."""
    APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return APP_LOG_DIR / f"session_{int(time.time() * 1000)}.tmp"


def enforce_log_limit(mb):
    """Tổng log app + phiên vượt `mb` MB thì xoá phần cũ nhất trước (0 = không giới hạn).
    Không xoá phiên mới nhất vì có thể đang chạy."""
    if not mb or mb <= 0:
        return
    limit = int(mb * 2**20)
    try:
        sess = sorted(session_logs(), key=session_start)               # cũ -> mới
        sizes = {p: p.stat().st_size for p in sess}
        lines = APP_LOG.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) \
            if APP_LOG.exists() else []
        sz = [len(x.encode("utf-8", "replace")) for x in lines]
        total = sum(sizes.values()) + sum(sz)
        if total <= limit:
            return
        i = 0
        while total > limit:
            a_ts = lines[i].partition("\t")[0] if i < len(lines) else None
            if len(sess) > 1 and (a_ts is None or session_start(sess[0]) < a_ts):
                p = sess.pop(0)
                try:
                    p.unlink(); total -= sizes[p]
                except OSError:
                    pass
            elif a_ts is not None:
                total -= sz[i]; i += 1
            else:
                break
        if i:
            APP_LOG.write_text("".join(lines[i:]), encoding="utf-8")
    except OSError:
        pass
