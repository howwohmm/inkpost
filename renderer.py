"""renderer — every d2 subprocess call. SPEC.md section 8.

LANE B owns this file. the signatures below are the lane contract and are
frozen.

job    = {"id": str, "src": str, "pattern": str, "mode": str, "fmt": "png"|"svg"|"gif"}
result = {**job, "ok": bool, "bytes": bytes|None, "ms": int, "cached": bool,
          "errors": list[dict]}

three rules that are not negotiable:
  * the pre-render gate is a REAL COMPILE (--stdout-format ascii), never
    `d2 validate` — validate is parse-only and waves through font-size: 0,
    shape: blob, near: nowhere and fill: notacolor. SPEC section 0, override 1.
  * check p.returncode ONLY. `success: successfully compiled ...` is printed to
    stderr on a SUCCESSFUL run.
  * a multiboard source (any `steps:`) is a hard error to stdout, and THE ASCII
    PREFLIGHT FAILS THE SAME WAY. --target steps.<max> fixes both. gif needs no
    target. --target '' is wrong: it compiles the root board only and returns
    rc=0 on a source that is broken in board 2. SPEC 8.2.
"""
import hashlib, os, re, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor

import config, presets, patterns

STEP_BOARD = re.compile(r"^\s*(\d+)\s*:\s*\{", re.M)
ACCENT_RE  = re.compile(r'style\.fill:\s*"#ffe8a3"', re.I)

EXT = {"png": "png", "svg": "svg", "gif": "gif"}


def _d2_version():
    try:
        p = subprocess.run([config.D2_BIN, "--version"], capture_output=True, timeout=10)
        return (p.stdout or p.stderr).decode("utf-8", "replace").strip() or "unknown"
    except Exception:
        return "unknown"


D2_VERSION = _d2_version()   # one call at import. it is part of the cache key.

_POOL = ThreadPoolExecutor(max_workers=config.RENDER_WORKERS,
                           thread_name_prefix="sketch-render")


class RenderError(Exception):
    """.errors is [{"line","col","msg"}], ascending."""

    def __init__(self, errors, message=None):
        super().__init__(message or "d2 render failed")
        self.errors = errors


def _run(args, src, timeout):
    """stdin -> stdout, always. the renderer never touches disk for input."""
    p = subprocess.run([config.D2_BIN, *args, "-", "-"],
                       input=src.encode("utf-8"), capture_output=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")


def layout_for(pattern, mode):
    """-> "tala" | "dagre". the pattern wins when it is known;
    mode.layout_default is the fallback for a hand-edited free-form source."""
    p = patterns.PATTERNS.get(pattern)
    if p:
        return p["layout"]
    m = presets.MODES.get(mode)
    return m["layout_default"] if m else "dagre"


def target_for(src):
    """-> "steps.<N>" | None, N = the highest board number in the steps block.
    parsed from the source, never assumed. SPEC 8.2."""
    if "steps:" not in src:
        return None
    ns = [int(m.group(1)) for m in STEP_BOARD.finditer(src)]
    return "steps.%d" % max(ns) if ns else None


def apply_mode(src, mode):
    """-> str. replace-ALL of style.fill: "#ffe8a3" with the mode's accent fill
    AND font-color. collapse and taxonomy legitimately carry the same concept
    twice. #f4f4f4 (the layers middle band) is untouched. SPEC 8.3."""
    a = presets.MODES[mode]["accent"]
    rep = 'style.fill: "%s"; style.font-color: "%s"' % (a["fill"], a["font"])
    return ACCENT_RE.sub(lambda _m: rep, src)


def parse_errors(stderr):
    """-> [{"line":int,"col":int,"msg":str}] sorted ASCENDING. d2 emits parse
    errors in descending line order. SPEC 8.5."""
    out = []
    for line in (stderr or "").splitlines():
        if not line.startswith("err:"):
            continue
        ms = list(re.finditer(r"(\d+):(\d+):\s*(.*)$", line))
        if ms:
            m = ms[-1]                       # take the LAST match on the line
            out.append({"line": int(m.group(1)), "col": int(m.group(2)),
                        "msg": m.group(3)})
        else:
            out.append({"line": 0, "col": 0, "msg": line[4:].strip()})
    out.sort(key=lambda e: (e["line"] == 0, e["line"], e["col"]))     # ASCENDING
    return out


# ---- the exact command lines. SPEC 8.4 ------------------------------------

def _preflight_argv(layout, target):
    args = ["--layout=%s" % layout]
    if target:
        args += ["--target", target]
    return args + ["--stdout-format", "ascii"]


def _render_argv(layout, mode, fmt, salt, target):
    """flags are ALWAYS passed explicitly — a flag beats an in-file
    vars.d2-config even when it equals d2's own default, so no model-emitted
    config block can hijack the render."""
    m = presets.MODES[mode]
    sketch = "true" if m["sketch"] else "false"
    args = ["--layout=%s" % layout, "--sketch=%s" % sketch, "--theme=%d" % m["theme"]]

    if fmt == "svg" and m.get("dark_theme") is not None:
        args += ["--dark-theme=%d" % m["dark_theme"]]

    args += ["--pad", str(config.PAD)]

    if fmt == "png":
        args += ["--scale", config.PNG_SCALE]
    elif fmt == "svg":
        args += ["--no-xml-tag", "--salt", salt]
    elif fmt == "gif":
        # never on a png target: `bad usage:` aborts with a useless last line.
        args += ["--animate-interval", str(config.ANIMATE_MS)]

    if fmt in ("png", "svg") and target:      # gif takes NO target. SPEC 8.2
        args += ["--target", target]

    return args + ["--stdout-format", fmt]


def preflight(src, layout):
    """-> list[dict]. [] means ok. applies target_for() internally. SPEC 8.4."""
    argv = _preflight_argv(layout, target_for(src))
    try:
        rc, _out, err = _run(argv, src, config.PREFLIGHT_TIMEOUT)
    except subprocess.TimeoutExpired:
        return [{"line": 0, "col": 0,
                 "msg": "d2 timed out after %ss" % config.PREFLIGHT_TIMEOUT}]
    if rc == 0:                                # returncode ONLY
        return []
    return parse_errors(err) or [{"line": 0, "col": 0,
                                  "msg": (err or "d2 failed").strip()[:400]}]


# ---- cache. SPEC 8.6 ------------------------------------------------------

def cache_key(src, mode, fmt, layout):
    blob = "\x00".join([src, mode, fmt, layout, D2_VERSION])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_path_for(src, mode, fmt, layout):
    """the file a render of this (canonical src, mode, fmt, layout) lands in.
    additive helper: it is what lets server.py hardlink a hit into the run's
    out/<mode>/ instead of writing the bytes again."""
    k = cache_key(src, mode, fmt, layout)
    return os.path.join(config.CACHE_DIR, k[:2], "%s.%s" % (k, EXT[fmt]))


def _cache_write(path, blob):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")   # same directory
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cache_clear():
    """-> int bytes freed. SPEC 8.6."""
    freed = 0
    root = config.CACHE_DIR
    if not os.path.isdir(root):
        return 0
    for dirpath, _dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                freed += os.path.getsize(p)
                os.unlink(p)
            except OSError:
                pass
        if dirpath != root:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    return freed


# ---- render ---------------------------------------------------------------

def _render_cached(src, pattern, mode, fmt, no_cache=False):
    """-> (bytes, cached: bool). the one place a render actually happens."""
    if fmt not in EXT:
        raise RenderError([{"line": 0, "col": 0, "msg": "unknown format %r" % (fmt,)}])

    # gate gif on the SOURCE, never on the exit code: a .gif target on a
    # single-board file renders a silent 1-frame gif rather than erroring.
    if fmt == "gif" and "steps:" not in src:
        raise RenderError([{"line": 0, "col": 0, "msg": "gif needs a steps pattern"}])

    layout = layout_for(pattern, mode)
    path = cache_path_for(src, mode, fmt, layout)

    if not no_cache:
        try:
            with open(path, "rb") as f:
                blob = f.read()
            if blob:
                return blob, True
        except OSError:
            pass

    salt = hashlib.sha256(src.encode("utf-8")).hexdigest()[:8]   # source-scoped
    argv = _render_argv(layout, mode, fmt, salt, target_for(src))
    painted = apply_mode(src, mode)

    try:
        rc, out, err = _run(argv, painted, config.RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RenderError([{"line": 0, "col": 0,
                            "msg": "d2 timed out after %ss" % config.RENDER_TIMEOUT}])

    if rc != 0:                                # returncode ONLY
        raise RenderError(parse_errors(err) or
                          [{"line": 0, "col": 0,
                            "msg": (err or "d2 failed").strip()[:400]}])
    if not out:
        raise RenderError([{"line": 0, "col": 0, "msg": "d2 produced no output"}])

    try:
        _cache_write(path, out)
    except Exception:
        pass                                   # a cache miss is never fatal
    return out, False


def render(src, pattern, mode, fmt):
    """-> bytes. takes the CANONICAL source and calls apply_mode itself.
    raises RenderError(errors). SPEC 8.4, 8.6."""
    return _render_cached(src, pattern, mode, fmt)[0]


def render_all(jobs):
    """-> list[dict] in INPUT ORDER. ThreadPoolExecutor(RENDER_WORKERS). one job
    raising never cancels the others; a TimeoutExpired is a CELL error. SPEC 8.7."""
    jobs = list(jobs)

    def one(job):
        t0 = time.time()
        res = dict(job)
        try:
            blob, cached = _render_cached(job["src"], job.get("pattern"),
                                          job["mode"], job["fmt"],
                                          no_cache=bool(job.get("no_cache")))
            res.update(ok=True, bytes=blob, cached=cached,
                       ms=0 if cached else int((time.time() - t0) * 1000),
                       errors=[])
        except RenderError as e:
            res.update(ok=False, bytes=None, cached=False,
                       ms=int((time.time() - t0) * 1000), errors=e.errors)
        except Exception as e:                 # never let one cell kill the run
            res.update(ok=False, bytes=None, cached=False,
                       ms=int((time.time() - t0) * 1000),
                       errors=[{"line": 0, "col": 0, "msg": str(e)}])
        return res

    return list(_POOL.map(one, jobs))
