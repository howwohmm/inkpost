"""server — http on 127.0.0.1:8788, the job state machine, runs/ on disk.

LANE C owns this file. SPEC.md section 9.

    python3 server.py      ->  sketch studio -> http://127.0.0.1:8788

the shape of the thing:

  POST /api/run returns 202 in milliseconds with a slug. a daemon thread walks
  queued -> planning -> assembling -> rendering -> done (or -> error at any
  step, with whatever finished staying on disk) and the ui polls /api/status
  every second. no streaming, no websockets, no sse — polling cannot half-fail.

  run.json is rewritten on EVERY transition, including each cell going
  pending -> rendering -> done: dumps -> run.json.tmp -> fsync -> os.replace,
  under a per-slug lock. a kill -9 mid-run leaves a valid earlier manifest,
  never a truncated file. /api/status serves the exact bytes last written, so
  a poll can never catch a half-mutated dict.

  every path in the manifest is relative to RUNS_DIR, because /runs/<...>
  joins onto RUNS_DIR and the ui just prefixes "/runs/".

standing rules baked in: bound to 127.0.0.1 only. the api key is read only by
config.load_env(), never logged, never returned by a route, never written into
a manifest. nothing is written outside runs/ and .cache/. no email, no
artifacts, no network at render time.
"""
import json, os, re, shutil, subprocess, sys, threading, time, traceback
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

import config, presets, patterns, planner, renderer

EXT_TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".gif": "image/gif",
             ".d2": "text/plain; charset=utf-8", ".json": "application/json",
             ".md": "text/plain; charset=utf-8"}

FMT_EXT = {"png": ".png", "svg": ".svg", "gif": ".gif"}
VALID_FORMATS = ("png", "svg", "gif")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
POST_FILE_RE = re.compile(r"^[A-Za-z0-9._-]+\.md$")
LOG_CAP = 200
NON_TERMINAL = ("queued", "planning", "assembling", "rendering")


# ---------------------------------------------------------------- small utils
def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def sha8(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def log_line(msg):
    sys.stderr.write("[sketch] %s\n" % msg)


def clean_post(text):
    """planner.clean_post, with a local fallback so the server still boots and
    lists posts while lane A is a stub. the fallback is never used for planning."""
    try:
        return planner.clean_post(text)
    except NotImplementedError:
        pass
    body = text
    meta = {"title": "", "description": ""}
    if body.startswith("---"):
        parts = body.split("\n")
        end = None
        for i, line in enumerate(parts[1:], 1):
            if line.strip() == "---":
                end = i
                break
        if end is not None:
            for line in parts[1:end]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k in meta:
                        meta[k] = v
            body = "\n".join(parts[end + 1:])
    body = body.strip()
    if not meta["title"]:
        for line in body.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                meta["title"] = line[2:].strip()[:60]
                break
            if line and not line.startswith("!["):
                meta["title"] = line[:60]
                break
    return meta, body


def slugify(title):
    try:
        return planner.slugify(title)
    except NotImplementedError:
        pass
    s = (title or "").lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60].strip("-")
    return s or ("sketch-" + datetime.now().strftime("%Y%m%d-%H%M%S"))


def resolve_backend(req="auto"):
    """(name, reason). planner.select_backend once lane A lands it; the same
    rule locally while it is a stub. SPEC 4."""
    try:
        return planner.select_backend(req)
    except NotImplementedError:
        pass
    if req in ("openrouter", "claude-code", "mock"):
        return req, "requested explicitly"
    if config.load_env():
        return "openrouter", "OPENROUTER_API_KEY found in .env"
    if shutil.which(config.CLAUDE_BIN):
        return "claude-code", "no api key, but claude is on PATH"
    return "mock", ("no OPENROUTER_API_KEY in .env and no claude on PATH — "
                    "running mock plans")


# --------------------------------------------------------- manifest i/o + lock
_locks = {}
_locks_guard = threading.Lock()
_snapshots = {}          # slug -> the exact bytes last written to run.json


def slug_lock(slug):
    with _locks_guard:
        lk = _locks.get(slug)
        if lk is None:
            lk = _locks[slug] = threading.Lock()
        return lk


def run_dir(slug):
    return os.path.join(config.RUNS_DIR, slug)


def save(m):
    """serialise -> run.json.tmp -> fsync -> os.replace, under the slug lock.
    called on EVERY transition. the previous manifest survives a failed write."""
    slug = m["slug"]
    with slug_lock(slug):
        data = json.dumps(m, ensure_ascii=False, indent=1).encode("utf-8")
        d = run_dir(slug)
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "run.json.tmp")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, os.path.join(d, "run.json"))
        _snapshots[slug] = data


def snapshot(slug):
    """the bytes /api/status serves. memory first, then disk."""
    data = _snapshots.get(slug)
    if data is not None:
        return data
    p = os.path.join(run_dir(slug), "run.json")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def read_manifest(slug):
    data = snapshot(slug)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        return None


def note(m, msg):
    """append one progress-log line. the only progress channel there is."""
    m["log"].append({"t": now_iso(), "msg": msg})
    if len(m["log"]) > LOG_CAP:
        del m["log"][:-LOG_CAP]
    log_line("%s · %s" % (m["slug"], msg))


def set_state(m, state, msg=None, error=None):
    m["state"] = state
    if error is not None:
        m["error"] = error
    note(m, msg or state)
    save(m)


# ------------------------------------------------------------------- the run
def new_slug(base):
    """re-run collision: <slug>, <slug>-2, <slug>-3 … never an overwrite."""
    if not SLUG_RE.match(base):
        base = slugify(base)
    if not os.path.exists(run_dir(base)):
        return base
    n = 2
    while os.path.exists(run_dir("%s-%d" % (base, n))):
        n += 1
    return "%s-%d" % (base, n)


def start_run(text, title, modes, formats, backend_req, model, no_cache):
    """everything cheap and synchronous, so POST /api/run answers in ms."""
    meta, body = clean_post(text)
    title = (title or meta.get("title") or "").strip() or "untitled sketch"
    slug = new_slug(slugify(title))
    d = run_dir(slug)
    os.makedirs(os.path.join(d, "src"), exist_ok=True)
    os.makedirs(os.path.join(d, "out"), exist_ok=True)
    with open(os.path.join(d, "post.md"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(d, "post.clean.txt"), "w", encoding="utf-8") as f:
        f.write(body)
    m = {"slug": slug, "title": title, "created": now_iso(), "state": "queued",
         "error": None, "modes": modes, "formats": formats, "log": [],
         "planner": None, "diagrams": [], "warnings": []}
    note(m, "queued · %d modes · %s" % (len(modes), ", ".join(formats)))
    save(m)
    t = threading.Thread(target=job, daemon=True,
                         args=(slug, body, title, backend_req, model, no_cache))
    t.start()
    return slug


def job(slug, body, title, backend_req, model, no_cache):
    m = read_manifest(slug)
    try:
        budget, diagrams = plan_stage(m, body, title, backend_req, model)
        assemble_stage(m, diagrams, budget, backend_req, model)
        render_stage(m, no_cache=no_cache)
        set_state(m, "done", "done · %d diagrams" % len(m["diagrams"]))
    except Exception as e:                                   # noqa: BLE001
        traceback.print_exc()
        msg = getattr(e, "message", None) or str(e) or e.__class__.__name__
        try:
            set_state(m, "error", "error: %s" % msg, error=msg)
        except Exception:                                    # noqa: BLE001
            traceback.print_exc()


def plan_stage(m, body, title, backend_req, model):
    backend, reason = resolve_backend(backend_req)
    set_state(m, "planning", "planning · %s · %s" % (backend, model or "auto"))
    if backend == "openrouter" and not config.load_env():
        raise RuntimeError("no OPENROUTER_API_KEY in .env — add it, or switch "
                           "the backend to claude-code")
    t0 = time.time()
    plan_dict, pmeta = planner.plan(body, backend, title=title, model=model)
    pmeta = dict(pmeta or {})
    pmeta.pop("key", None)                      # belt and braces: never a key
    m["planner"] = pmeta
    with open(os.path.join(run_dir(m["slug"]), "plan.json"), "w",
              encoding="utf-8") as f:
        json.dump(plan_dict, f, ensure_ascii=False, indent=1)
    diagrams = plan_dict.get("diagrams") or []
    note(m, "plan back in %.1fs · %d diagrams · %s"
         % (time.time() - t0, len(diagrams), pmeta.get("model") or backend))
    save(m)
    # the plan is passed as an argument, never stashed on the manifest — a poll
    # during assembling must not be served every d2 source twice.
    return max(0, config.MAX_LLM_CALLS_PER_RUN - int(pmeta.get("calls") or 1)), diagrams


def assemble_stage(m, diagrams, budget, backend_req, model):
    """lint -> preflight -> at most one llm repair -> preflight. a diagram that
    still fails is marked failed and the job carries on."""
    set_state(m, "assembling", "assembling · checking the d2")
    backend, _ = resolve_backend(backend_req)
    first_mode = (m["modes"] or presets.DEFAULT_MODES)[0]
    rows = []
    for i, d in enumerate(diagrams, 1):
        pattern = (d.get("pattern") or "").strip()
        if pattern not in patterns.PATTERNS:
            w = 'diagram %d dropped: pattern "%s" is not in the catalog' % (i, pattern)
            m["warnings"].append(w)
            note(m, w)
            continue
        did = "%02d-%s" % (i, pattern)
        src = d.get("d2") or ""
        src, problems, notes = safe_lint(src)
        layout = renderer.layout_for(pattern, first_mode)
        errors = renderer.preflight(src, layout)
        repairs = 0
        if (problems or errors) and budget > 0:
            note(m, "%s · repairing (%d problems, %d errors)"
                 % (did, len(problems), len(errors)))
            try:
                fixed, rmeta = planner.repair_d2(src, problems, errors, backend,
                                                 model=model)
                budget -= int((rmeta or {}).get("calls") or 1)
                repairs = 1
                fixed, problems, more = safe_lint(fixed)
                notes = notes + more
                errors = renderer.preflight(fixed, layout)
                src = fixed
                note(m, "%s repaired" % did)
            except Exception as e:                           # noqa: BLE001
                note(m, "%s repair failed: %s" % (did, e))
        src_path = os.path.join(run_dir(m["slug"]), "src", did + ".d2")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(src)
        row = {"id": did, "slug": d.get("slug") or did, "pattern": pattern,
               "title": d.get("title") or "", "move": d.get("move") or "",
               "layout": layout, "gif": "steps:" in src,
               "src_path": "%s/src/%s.d2" % (m["slug"], did),
               "src_sha": sha8(src), "edited": False, "repairs": repairs,
               "status": "failed" if errors else "ok",
               "errors": errors, "lint_notes": notes, "cells": []}
        row["cells"] = cells_for(row, m["modes"], m["formats"])
        if errors:
            # a failed source never renders, so its cells go red immediately
            # rather than sitting as skeletons the ui would spin on forever.
            for c in row["cells"]:
                c["state"], c["errors"] = "error", errors
            note(m, "%s failed: %s" % (did, errors[0].get("msg", "")))
        rows.append(row)
        m["diagrams"] = rows
        save(m)
    m["diagrams"] = rows
    if not [r for r in rows if r["status"] == "ok"]:
        raise RuntimeError("no diagram survived assembling — "
                           + ("; ".join(m["warnings"]) or "every source failed to compile"))
    save(m)


def safe_lint(src):
    try:
        fixed, problems, notes = planner.lint(src)
        return fixed, list(problems or []), list(notes or [])
    except NotImplementedError:
        return src, [], []


def cells_for(row, modes, formats):
    """gif on a non-steps source is SKIPPED, not errored — the cell does not
    exist at all, so the ui never offers a silent 1-frame file."""
    out = []
    for mode in modes:
        for fmt in formats:
            if fmt == "gif" and not row.get("gif"):
                continue
            out.append({"mode": mode, "fmt": fmt, "state": "pending",
                        "cached": False, "ms": 0, "bytes": 0,
                        "path": None, "errors": []})
    return out


def read_src(slug, did):
    p = os.path.join(run_dir(slug), "src", did + ".d2")
    with open(p, encoding="utf-8") as f:
        return f.read()


def render_stage(m, rows=None, no_cache=False):
    """fan diagrams x modes x formats into the render pool, in chunks, so the
    manifest fills in progressively. a cell error NEVER fails the run."""
    set_state(m, "rendering", "rendering")
    if no_cache:
        note(m, "no_cache — every cell is rendered fresh")
    rows = rows if rows is not None else m["diagrams"]
    jobs, index = [], {}
    for row in rows:
        if row["status"] != "ok":
            continue
        try:
            src = read_src(m["slug"], row["id"])
        except OSError as e:
            note(m, "%s: %s" % (row["id"], e))
            continue
        for cell in row["cells"]:
            if cell["state"] == "done" and cell.get("path"):
                continue
            jid = "%s|%s|%s" % (row["id"], cell["mode"], cell["fmt"])
            index[jid] = (row, cell)
            jb = {"id": jid, "src": src, "pattern": row["pattern"],
                  "mode": cell["mode"], "fmt": cell["fmt"]}
            if no_cache:
                jb["no_cache"] = True        # renderer honours it per job
            jobs.append(jb)
    n = max(1, int(config.RENDER_WORKERS))
    done = 0
    for i in range(0, len(jobs), n):
        chunk = jobs[i:i + n]
        for j in chunk:
            index[j["id"]][1]["state"] = "rendering"
        save(m)
        try:
            results = renderer.render_all(chunk)
        except Exception as e:                               # noqa: BLE001
            traceback.print_exc()
            results = [dict(j, ok=False, bytes=None, ms=0, cached=False,
                            errors=[{"line": 0, "col": 0, "msg": str(e)}])
                       for j in chunk]
        for r in results:
            row, cell = index[r["id"]]
            write_cell(m, row, cell, r)
            done += 1
        note(m, "rendered %d of %d" % (done, len(jobs)))
        save(m)


def write_cell(m, row, cell, r):
    data = r.get("bytes")
    cell["cached"] = bool(r.get("cached"))
    cell["ms"] = int(r.get("ms") or 0)
    cell["errors"] = list(r.get("errors") or [])
    if not r.get("ok") or not data:
        cell["state"] = "error"
        cell["bytes"] = 0
        first = (cell["errors"] or [{}])[0]
        note(m, "%s/%s.%s failed · %s" % (cell["mode"], row["id"], cell["fmt"],
                                          first.get("msg", "render failed")))
        return
    rel = "%s/out/%s/%s%s" % (m["slug"], cell["mode"], row["id"],
                             FMT_EXT[cell["fmt"]])
    dest = os.path.join(config.RUNS_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dest)
    cell["state"] = "done"
    cell["bytes"] = len(data)
    cell["path"] = rel
    note(m, "%s/%s.%s %s" % (cell["mode"], row["id"], cell["fmt"],
                             "cached" if cell["cached"] else "done in %dms" % cell["ms"]))


def rerender(slug, ids=None, modes=None, formats=None):
    """named cells reset to pending, then render. backs the per-row gif button
    and every source edit. never calls the llm."""
    m = read_manifest(slug)
    if m is None:
        return False
    modes = modes or m.get("modes") or presets.DEFAULT_MODES
    formats = formats or m.get("formats") or ["png"]
    rows = [r for r in m["diagrams"] if ids is None or r["id"] in ids]
    if not rows:
        return False
    for row in rows:
        keep = [c for c in row["cells"]
                if not (c["mode"] in modes and c["fmt"] in formats)]
        fresh = cells_for(row, modes, formats)
        if row["status"] != "ok":            # never render, so never pending
            for c in fresh:
                c["state"], c["errors"] = "error", row.get("errors") or []
        row["cells"] = keep + fresh
    save(m)

    def work():
        try:
            render_stage(m, rows=rows)
            set_state(m, "done", "re-rendered %d row(s)" % len(rows))
        except Exception as e:                               # noqa: BLE001
            traceback.print_exc()
            set_state(m, "error", "error: %s" % e, error=str(e))
    threading.Thread(target=work, daemon=True).start()
    return True


# --------------------------------------------------------------- read routes
def health():
    backend, reason = resolve_backend(config.BACKEND)
    return {"ok": True,
            "state": "degraded" if backend == "mock" else "ready",
            "d2": renderer.D2_VERSION,
            "backend": backend,
            "backend_reason": reason,
            "backends": {"openrouter": "ready" if config.load_env() else "no key",
                         "claude-code": "ready" if shutil.which(config.CLAUDE_BIN) else "not on PATH",
                         "mock": "ready"},
            "warnings": []}


def modes_payload():
    return {"ok": True,
            "modes": presets.MODES,
            "order": presets.MODE_ORDER,
            "default_modes": presets.DEFAULT_MODES,
            "patterns": {n: {k: v for k, v in p.items() if k != "d2"}
                         for n, p in patterns.PATTERNS.items()},
            "backends": ["openrouter", "claude-code", "mock"],
            "default_backend": resolve_backend(config.BACKEND)[0],
            "chain": config.OPENROUTER_CHAIN,
            "claude_model": config.CLAUDE_MODEL}


def posts_payload():
    """missing POSTS_DIR -> an empty list, never a 500."""
    out = []
    d = config.POSTS_DIR
    if not os.path.isdir(d):
        return {"ok": True, "posts": []}
    for name in os.listdir(d):
        if not name.endswith(".md") or name.startswith("."):
            continue
        p = os.path.join(d, name)
        try:
            st = os.stat(p)
            with open(p, encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except OSError:
            continue
        meta, _ = clean_post(raw)
        mm = re.match(r"^(\d{4}-\d{2}-\d{2})", name)
        date = mm.group(1) if mm else datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
        out.append({"file": name, "slug": name[:-3], "bytes": st.st_size,
                    "title": meta.get("title") or name[:-3], "date": date})
    out.sort(key=lambda r: (r["date"], r["file"]), reverse=True)
    return {"ok": True, "posts": out}


def runs_payload(limit=20):
    rows = []
    if os.path.isdir(config.RUNS_DIR):
        for slug in os.listdir(config.RUNS_DIR):
            if not SLUG_RE.match(slug):
                continue
            m = None
            p = os.path.join(config.RUNS_DIR, slug, "run.json")
            if not os.path.exists(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    m = json.load(f)
            except (OSError, ValueError):
                continue
            thumb = None
            for row in m.get("diagrams") or []:
                for c in row.get("cells") or []:
                    if c.get("fmt") == "png" and c.get("path") and c.get("state") == "done":
                        thumb = c["path"]
                        break
                if thumb:
                    break
            rows.append({"slug": m.get("slug", slug), "title": m.get("title", slug),
                         "created": m.get("created", ""), "state": m.get("state", ""),
                         "n_diagrams": len(m.get("diagrams") or []),
                         "modes": m.get("modes") or [], "thumb": thumb})
    rows.sort(key=lambda r: r["created"], reverse=True)
    return {"ok": True, "runs": rows[:limit]}


def accent_count(src):
    rx = getattr(renderer, "ACCENT_RE", None)
    if rx is not None:
        return len(rx.findall(src))
    return len(re.findall(r'style\.fill:\s*"#ffe8a3"', src, re.I))


def find_row(m, did):
    for row in m.get("diagrams") or []:
        if row["id"] == did:
            return row
    return None


def plan_source(slug, did):
    """plan.json is NEVER mutated, so revert always has somewhere to go. ids are
    derived from the plan's own order, so this match is exact."""
    p = os.path.join(run_dir(slug), "plan.json")
    with open(p, encoding="utf-8") as f:
        plan_dict = json.load(f)
    for i, d in enumerate(plan_dict.get("diagrams") or [], 1):
        if "%02d-%s" % (i, d.get("pattern") or "") == did:
            return d.get("d2") or ""
    return None


def write_source(slug, did, src):
    """returns (manifest, row, preflight_errors). the source is written either
    way — saving broken d2 is allowed and no llm is ever called here."""
    m = read_manifest(slug)
    row = find_row(m, did) if m else None
    if row is None:
        return None, None, None
    with open(os.path.join(run_dir(slug), "src", did + ".d2"), "w",
              encoding="utf-8") as f:
        f.write(src)
    errors = renderer.preflight(src, row.get("layout") or "dagre")
    row["src_sha"] = sha8(src)
    row["edited"] = True
    row["gif"] = "steps:" in src
    row["errors"] = errors
    row["status"] = "failed" if errors else "ok"
    note(m, "%s source saved%s" % (did, "" if not errors else " · %d errors" % len(errors)))
    save(m)
    return m, row, errors


# --------------------------------------------------------------- static guard
def safe_asset(relpath):
    """realpath must stay under RUNS_DIR and the extension must be mapped.
    returns (abs_path, content_type) or (None, reason)."""
    if "\x00" in relpath:
        return None, "null byte"
    parts = relpath.split("/", 1)
    slug = parts[0]
    if not SLUG_RE.match(slug):
        return None, "bad slug"
    full = os.path.realpath(os.path.join(config.RUNS_DIR, relpath))
    base = os.path.realpath(config.RUNS_DIR) + os.sep
    if not full.startswith(base):
        return None, "outside runs/"
    ctype = EXT_TYPES.get(os.path.splitext(full)[1].lower())
    if ctype is None:
        return None, "unmapped extension"
    if not os.path.isfile(full):
        return None, "not found"
    return full, ctype


# -------------------------------------------------------------------- handler
class Handler(BaseHTTPRequestHandler):
    server_version = "sketch"

    def log_message(self, fmt, *a):
        sys.stderr.write("[sketch] " + (fmt % a) + "\n")

    def _send(self, code, payload, ctype="application/json", headers=None):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, str):
            body = payload.encode("utf-8")
        else:
            body = payload
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _bad(self, msg, code=400):
        self._send(code, {"ok": False, "error": msg})

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ValueError("body is not json")
        if not isinstance(obj, dict):
            raise ValueError("body is not a json object")
        return obj

    # ---- GET
    def do_GET(self):
        try:
            u = urlparse(self.path)
            path, q = u.path, parse_qs(u.query)
            if path in ("/", "/index.html"):
                if not os.path.exists(config.UI_FILE):
                    return self._bad("ui/index.html missing", 404)
                with open(config.UI_FILE, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path == "/api/health":
                return self._send(200, health())
            if path == "/api/modes":
                return self._send(200, modes_payload())
            if path == "/api/posts":
                return self._send(200, posts_payload())
            if path == "/api/post":
                return self.get_post(q)
            if path == "/api/status":
                return self.get_status(q)
            if path == "/api/runs":
                try:
                    limit = int((q.get("limit") or ["20"])[0])
                except ValueError:
                    limit = 20
                return self._send(200, runs_payload(max(1, min(200, limit))))
            if path == "/api/source":
                return self.get_source(q)
            if path.startswith("/runs/"):
                return self.get_asset(unquote(path[len("/runs/"):]), q)
            self._bad("not found", 404)
        except Exception as e:                               # noqa: BLE001
            traceback.print_exc()
            self._send(500, {"ok": False, "error": str(e)})

    def get_post(self, q):
        name = (q.get("file") or [""])[0]
        if not POST_FILE_RE.match(name):
            return self._bad("bad filename")
        p = os.path.join(config.POSTS_DIR, name)
        if os.path.realpath(p) != os.path.join(os.path.realpath(config.POSTS_DIR), name) \
                or not os.path.isfile(p):
            return self._bad("no such post", 404)
        with open(p, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        meta, body = clean_post(raw)
        self._send(200, {"ok": True, "title": meta.get("title", ""),
                         "description": meta.get("description", ""),
                         "raw": raw, "clean": body})

    def get_status(self, q):
        slug = (q.get("slug") or [""])[0]
        if not SLUG_RE.match(slug):
            return self._bad("bad slug")
        data = snapshot(slug)
        if data is None:
            return self._bad("no such run", 404)
        self._send(200, data, "application/json")

    def get_source(self, q):
        slug = (q.get("slug") or [""])[0]
        did = (q.get("id") or [""])[0]
        if not SLUG_RE.match(slug) or not re.match(r"^[0-9]{2}-[a-z-]+$", did):
            return self._bad("bad slug or id")
        m = read_manifest(slug)
        row = find_row(m, did) if m else None
        if row is None:
            return self._bad("no such diagram", 404)
        try:
            src = read_src(slug, did)
        except OSError:
            return self._bad("no source on disk", 404)
        self._send(200, {"ok": True, "d2": src, "sha": sha8(src),
                         "edited": bool(row.get("edited")),
                         "accents": accent_count(src)})

    def get_asset(self, rel, q):
        full, ctype = safe_asset(rel)
        if full is None:
            return self._bad("forbidden", 403 if ctype != "not found" else 404)
        with open(full, "rb") as f:
            data = f.read()
        headers = {}
        if (q.get("dl") or [""])[0] == "1":
            headers["Content-Disposition"] = \
                'attachment; filename="%s"' % os.path.basename(full)
        self._send(200, data, ctype, headers)

    # ---- POST / PUT
    def do_POST(self):
        try:
            path = urlparse(self.path).path
            if path == "/api/run":
                return self.post_run()
            if path == "/api/rerender":
                return self.post_rerender()
            if path == "/api/revert":
                return self.post_revert()
            if path == "/api/open":
                return self.post_open()
            if path == "/api/cache/clear":
                return self._send(200, {"ok": True, "freed_bytes": renderer.cache_clear()})
            self._bad("not found", 404)
        except ValueError as e:
            self._bad(str(e))
        except Exception as e:                               # noqa: BLE001
            traceback.print_exc()
            self._send(500, {"ok": False, "error": str(e)})

    def do_PUT(self):
        try:
            path = urlparse(self.path).path
            if path == "/api/source":
                return self.put_source()
            self._bad("not found", 404)
        except ValueError as e:
            self._bad(str(e))
        except Exception as e:                               # noqa: BLE001
            traceback.print_exc()
            self._send(500, {"ok": False, "error": str(e)})

    def post_run(self):
        b = self._body()
        text = b.get("text") or ""
        if not text and b.get("post_file"):
            name = b["post_file"]
            if not POST_FILE_RE.match(name):
                return self._bad("bad filename")
            p = os.path.join(config.POSTS_DIR, name)
            if not os.path.isfile(p):
                return self._bad("no such post", 404)
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
        if not text.strip():
            return self._bad("empty post")
        modes = [x for x in (b.get("modes") or presets.DEFAULT_MODES)
                 if x in presets.MODES] or list(presets.DEFAULT_MODES)
        formats = [x for x in (b.get("formats") or ["png", "svg"])
                   if x in VALID_FORMATS] or ["png"]
        if "png" not in formats:
            formats.insert(0, "png")
        backend_req = b.get("backend") or config.BACKEND
        name, _ = resolve_backend(backend_req)
        if name == "openrouter" and not config.load_env():
            return self._bad("no OPENROUTER_API_KEY in .env — add it, or switch "
                             "the backend to claude-code")
        slug = start_run(text, b.get("title"), modes, formats, backend_req,
                         b.get("model") or None, bool(b.get("no_cache")))
        self._send(202, {"ok": True, "slug": slug})

    def post_rerender(self):
        b = self._body()
        slug = b.get("slug") or ""
        if not SLUG_RE.match(slug):
            return self._bad("bad slug")
        ids = [b["id"]] if b.get("id") else (b.get("ids") or None)
        modes = [x for x in (b.get("modes") or []) if x in presets.MODES] or None
        formats = [x for x in (b.get("formats") or []) if x in VALID_FORMATS] or None
        if not rerender(slug, ids, modes, formats):
            return self._bad("no such run or diagram", 404)
        self._send(202, {"ok": True, "slug": slug})

    def post_revert(self):
        b = self._body()
        slug, did = b.get("slug") or "", b.get("id") or ""
        if not SLUG_RE.match(slug):
            return self._bad("bad slug")
        try:
            src = plan_source(slug, did)
        except (OSError, ValueError):
            src = None
        if src is None:
            return self._bad("nothing to revert to", 404)
        m, row, errors = write_source(slug, did, src)
        if row is None:
            return self._bad("no such diagram", 404)
        row["edited"] = False
        row["repairs"] = row.get("repairs") or 0
        save(m)
        ok = not errors
        if ok:
            rerender(slug, [did], m.get("modes"), m.get("formats"))
        self._send(200, {"ok": True, "d2": src,
                         "preflight": {"ok": ok, "errors": errors},
                         "rerendering": ok})

    def put_source(self):
        b = self._body()
        slug, did = b.get("slug") or "", b.get("id") or ""
        src = b.get("d2")
        if not SLUG_RE.match(slug) or not isinstance(src, str):
            return self._bad("bad slug or d2")
        m, row, errors = write_source(slug, did, src)
        if row is None:
            return self._bad("no such diagram", 404)
        ok = not errors
        if ok:
            rerender(slug, [did], m.get("modes"), m.get("formats"))
        self._send(200, {"ok": True, "preflight": {"ok": ok, "errors": errors},
                         "rerendering": ok})

    def post_open(self):
        b = self._body()
        slug = b.get("slug") or ""
        if not SLUG_RE.match(slug):
            return self._bad("bad slug")
        m = read_manifest(slug)
        target, args = None, None
        for row in (m or {}).get("diagrams") or []:
            for c in row.get("cells") or []:
                if c.get("fmt") == "png" and c.get("path") and c.get("state") == "done":
                    full, _ = safe_asset(c["path"])
                    if full:
                        target, args = full, ["open", "-R", full]
                        break
            if target:
                break
        if target is None:
            d = os.path.realpath(os.path.join(run_dir(slug), "out"))
            if not d.startswith(os.path.realpath(config.RUNS_DIR) + os.sep) \
                    or not os.path.isdir(d):
                return self._send(200, {"ok": False, "error": "nothing to open yet"})
            target, args = d, ["open", d]
        try:
            p = subprocess.run(args, capture_output=True, timeout=10)
            ok = p.returncode == 0
        except Exception as e:                               # noqa: BLE001
            return self._send(200, {"ok": False, "error": str(e)})
        self._send(200, {"ok": ok, "path": target})


# ----------------------------------------------------------------- boot/serve
def sweep():
    """a manifest left mid-flight by a restart becomes an honest error, so the
    ui never shows a permanently spinning run."""
    n = 0
    if not os.path.isdir(config.RUNS_DIR):
        return 0
    for slug in os.listdir(config.RUNS_DIR):
        p = os.path.join(config.RUNS_DIR, slug, "run.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        if m.get("state") in NON_TERMINAL:
            m["state"] = "error"
            m["error"] = "interrupted — the server restarted"
            m.setdefault("log", []).append(
                {"t": now_iso(), "msg": "interrupted — the server restarted"})
            m.setdefault("slug", slug)
            save(m)
            n += 1
    return n


def boot():
    """before binding the port. SPEC 9."""
    if not os.path.exists(config.D2_BIN):
        sys.stderr.write("d2 not found at %s. brew install d2, or set SKETCH_D2.\n"
                         % config.D2_BIN)
        raise SystemExit(1)
    os.makedirs(config.RUNS_DIR, exist_ok=True)
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    n = sweep()
    if n:
        log_line("swept %d interrupted run(s)" % n)


def serve(host=config.HOST, port=config.PORT):
    boot()
    ThreadingHTTPServer.allow_reuse_address = True
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError as e:
        sys.stderr.write("[sketch] cannot bind %s:%d (%s). already running? → "
                         "http://%s:%d\n" % (host, port, e, host, port))
        raise SystemExit(1)
    h = health()
    log_line("sketch studio → http://%s:%d  ·  d2 %s · backend %s"
             % (host, port, h["d2"], h["backend"]))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[sketch] bye\n")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
