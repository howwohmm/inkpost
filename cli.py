#!/usr/bin/env python3
"""inkpost — turn a blog post into hand-drawn diagrams, from the terminal.

  inkpost                             pick a post interactively
  inkpost post.md                     a file, or a slug from the blog folder
  inkpost post.md -m paper,midnight   choose modes
  inkpost --list                      posts and modes
  inkpost --runs                      what you have made before
  inkpost --open <slug>               reopen a finished run

styling uses clypi when the local venv is there, and degrades to plain ansi
otherwise. no server needed — this calls planner + renderer directly.
"""
import argparse
import os
import shutil
import subprocess
import sys
import threading
import time

__version__ = "0.1.0"

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config          # noqa: E402
import patterns        # noqa: E402
import planner         # noqa: E402
import presets         # noqa: E402
import renderer        # noqa: E402

# --------------------------------------------------------------------- style
try:
    from clypi import Spin, Spinner, boxed, style
    HAVE_CLYPI = True
except Exception:                                    # noqa: BLE001
    HAVE_CLYPI = False

    def style(*msg, fg=None, bold=False, dim=False, italic=False, **kw):
        codes = {"black": 30, "red": 31, "green": 32, "yellow": 33, "blue": 34,
                 "magenta": 35, "cyan": 36, "white": 37, "bright_black": 90,
                 "bright_yellow": 93, "bright_cyan": 96}
        s = " ".join(str(m) for m in msg)
        pre = ""
        if fg in codes:
            pre += "\033[%dm" % codes[fg]
        if bold:
            pre += "\033[1m"
        if dim:
            pre += "\033[2m"
        if italic:
            pre += "\033[3m"
        return (pre + s + "\033[0m") if pre else s

    def boxed(lines, width="auto", title=None, color=None, **kw):
        rows = list(lines) if not isinstance(lines, str) else [lines]
        w = max([len(_plain(r)) for r in rows] + [len(title or "")]) + 2
        top = "┏━" + (title or "").ljust(w - 1, "━") + "┓"
        out = [top]
        for r in rows:
            out.append("┃ " + r + " " * (w - 1 - len(_plain(r))) + "┃")
        out.append("┗" + "━" * (w + 1) + "┛")
        return out


def _plain(s):
    out, i = [], 0
    s = str(s)
    while i < len(s):
        if s[i] == "\033":
            while i < len(s) and s[i] != "m":
                i += 1
            i += 1
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


DIM = lambda s: style(s, fg="bright_black")                       # noqa: E731
BOLD = lambda s: style(s, bold=True)                              # noqa: E731
OK = lambda s: style(s, fg="green")                               # noqa: E731
WARN = lambda s: style(s, fg="yellow")                            # noqa: E731
BAD = lambda s: style(s, fg="red")                                # noqa: E731
ACC = lambda s: style(s, fg="bright_yellow", bold=True)           # noqa: E731


def say(*a):
    print(*a, flush=True)


def rule(label=""):
    w = min(shutil.get_terminal_size((80, 20)).columns, 78)
    if label:
        head = "── " + label + " "
        say(DIM(head + "─" * max(0, w - len(head))))
    else:
        say(DIM("─" * w))


class Progress:
    """a ticking spinner line on stderr. clypi's own Spinner is async-only, so
    we borrow its frames and drive them from a thread."""

    FRAMES = list(Spin.DOTS.value) if HAVE_CLYPI else list("|/-\\")

    def __init__(self, title):
        self.title = title
        self._stop = threading.Event()
        self._t = None
        self._width = 0

    def __enter__(self):
        if not sys.stderr.isatty():
            return self

        def spin():
            i, t0 = 0, time.time()
            while not self._stop.is_set():
                line = "  %s %s %s" % (
                    style(self.FRAMES[i % len(self.FRAMES)], fg="bright_yellow"),
                    self.title, DIM("%ds" % int(time.time() - t0)))
                self._width = max(self._width, len(_plain(line)))
                sys.stderr.write("\r" + line + " " * (self._width - len(_plain(line))))
                sys.stderr.flush()
                i += 1
                time.sleep(0.1)
            sys.stderr.write("\r" + " " * (self._width + 2) + "\r")
            sys.stderr.flush()

        self._t = threading.Thread(target=spin, daemon=True)
        self._t.start()
        return self

    def text(self, msg):
        self.title = msg

    def __exit__(self, *exc):
        self._stop.set()
        if self._t is not None:
            self._t.join(timeout=1)
        return False


# ---------------------------------------------------------------- discovery
def blog_posts():
    d = config.POSTS_DIR
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d), reverse=True):
        if not f.endswith(".md"):
            continue
        path = os.path.join(d, f)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                meta, _ = planner.clean_post(fh.read())
            title = meta.get("title") or f
        except Exception:                            # noqa: BLE001
            title = f
        out.append({"file": f, "path": path, "title": title,
                    "slug": f[:-3], "bytes": os.path.getsize(path)})
    return out


def resolve_post(arg):
    """a path, a filename, or a slug fragment -> (text, title, slug)."""
    if os.path.isfile(arg):
        path = arg
    else:
        hits = [p for p in blog_posts()
                if arg == p["file"] or arg == p["slug"] or arg.lower() in p["slug"].lower()]
        if not hits:
            raise SystemExit(BAD("no post matches %r. try --list" % arg))
        if len(hits) > 1:
            say(WARN("several posts match %r:" % arg))
            for h in hits:
                say("   " + h["slug"])
            raise SystemExit(1)
        path = hits[0]["path"]
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    meta, _ = planner.clean_post(text)
    base = os.path.basename(path)[:-3] if path.endswith(".md") else os.path.basename(path)
    return text, (meta.get("title") or base), planner.slugify(meta.get("title") or base)


def pick_post():
    posts = blog_posts()
    if not posts:
        raise SystemExit(BAD("no posts in %s — pass a file instead" % config.POSTS_DIR))
    say()
    say(BOLD("  which post?"))
    say()
    for i, p in enumerate(posts, 1):
        say("   %s  %s  %s" % (ACC("%2d" % i), p["title"][:52].ljust(52),
                               DIM("%4.1fkb" % (p["bytes"] / 1024.0))))
    say()
    try:
        raw = input(DIM("   number (or q) › ")).strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(0)
    if raw.lower() in ("q", "quit", ""):
        raise SystemExit(0)
    try:
        p = posts[int(raw) - 1]
    except Exception:                                # noqa: BLE001
        raise SystemExit(BAD("not a number on the list"))
    return resolve_post(p["path"])


def parse_modes(spec):
    names = list(presets.MODE_ORDER)
    if not spec:
        return list(presets.DEFAULT_MODES)
    if spec.strip().lower() == "all":
        return names
    want, bad = [], []
    for raw in spec.split(","):
        m = raw.strip().lower()
        if not m:
            continue
        if m in presets.MODES:
            want.append(m)
        else:
            bad.append(m)
    if bad:
        raise SystemExit(BAD("unknown mode(s): %s" % ", ".join(bad)) +
                         DIM("\n  available: " + ", ".join(names)))
    return want or list(presets.DEFAULT_MODES)


# --------------------------------------------------------------------- views
def show_list():
    say()
    say(BOLD("  posts"))
    for p in blog_posts():
        say("   %s  %s" % (DIM(p["slug"][:44].ljust(44)), p["title"][:40]))
    say()
    say(BOLD("  modes"))
    for name in presets.MODE_ORDER:
        m = presets.MODES[name]
        say("   %s  %s" % (ACC(name.ljust(11)), DIM(m.get("note", "")[:58])))
    say()
    say(BOLD("  backends"))
    for b, ok in backend_status().items():
        mark = OK("ready") if ok else DIM("unavailable")
        say("   %s  %s" % (b.ljust(11), mark))
    say()


def backend_status():
    have_claude = bool(shutil.which(config.CLAUDE_BIN) or os.path.exists(config.CLAUDE_BIN))
    return {"claude-code": have_claude, "openrouter": bool(config.load_env()), "mock": True}


def show_runs():
    d = config.RUNS_DIR
    rows = []
    if os.path.isdir(d):
        for slug in sorted(os.listdir(d)):
            rd = os.path.join(d, slug)
            if not os.path.isdir(rd):
                continue
            src = os.path.join(rd, "src")
            n = len([f for f in os.listdir(src)]) if os.path.isdir(src) else 0
            out = os.path.join(rd, "out")
            modes = sorted(os.listdir(out)) if os.path.isdir(out) else []
            rows.append((slug, n, modes))
    if not rows:
        say(DIM("  nothing made yet."))
        return
    say()
    for slug, n, modes in rows:
        say("   %s  %s  %s" % (ACC(slug[:44].ljust(44)),
                               DIM("%d diagrams" % n),
                               DIM(", ".join(modes))))
    say()



# ------------------------------------------------------------------- doctor
def _which(name):
    return shutil.which(name) or (name if os.path.exists(name) else None)


def check_all():
    """-> list of (ok, label, detail, fix, required). the readiness picture.
    `required` is False for things that are nice to have but not needed."""
    rows = []

    d2 = _which(config.D2_BIN) or _which("d2")
    if d2:
        try:
            v = subprocess.run([d2, "--version"], capture_output=True, text=True,
                               timeout=10).stdout.strip()
        except Exception:                            # noqa: BLE001
            v = "?"
        rows.append((True, "d2", "%s  %s" % (v, d2), "", True))
        try:
            lay = subprocess.run([d2, "layout"], capture_output=True, text=True,
                                 timeout=10).stdout.lower()
            has = "tala" in lay
        except Exception:                            # noqa: BLE001
            has = False
        rows.append((has, "tala layout",
                     "bundled with d2" if has else "missing. most patterns need it",
                     "" if has else "update d2 to v0.9.0 or newer", True))
    else:
        rows.append((False, "d2", "not found",
                     "brew install d2", True))
        rows.append((False, "tala layout", "cannot check without d2", "", True))

    claude = _which(config.CLAUDE_BIN)
    key = bool(config.load_env())
    rows.append((bool(claude), "claude cli",
                 "best wording, ~2 min a post" if claude else "not installed",
                 "" if claude else "npm i -g @anthropic-ai/claude-code", False))
    rows.append((key, "openrouter key",
                 "free models, 12-25s a post" if key else "no key in .env",
                 "" if key else "inkpost --setup", False))

    ready = bool(claude) or key
    rows.append((ready, "a model",
                 "ready" if ready else "none. only the mock backend works",
                 "" if ready else "inkpost --setup", True))

    posts = blog_posts()
    rows.append((bool(posts), "posts folder",
                 "%d posts in %s" % (len(posts), config.POSTS_DIR) if posts
                 else "nothing in %s" % config.POSTS_DIR,
                 "" if posts else "pass a file path, or set INKPOST_POSTS_DIR", False))
    return rows


def show_doctor():
    say()
    say(BOLD("  checking your setup"))
    say()
    blocked = False
    for ok, label, detail, fix, required in check_all():
        if ok:
            mark = OK("ok  ")
        elif required:
            mark = BAD("no  ")
            blocked = True
        else:
            mark = DIM("--  ")
        say("   %s %s  %s" % (mark, label.ljust(15), DIM(detail)))
        if not ok and fix:
            say("        %s %s" % (DIM("optional:" if not required else "fix:"), fix))
    say()
    if blocked:
        say(DIM("  run ") + BOLD("inkpost --setup") + DIM(" to be walked through it."))
    else:
        say(OK("  ready.") + DIM("  try: inkpost"))
    say()
    return 1 if blocked else 0


def show_setup():
    """a short interactive walkthrough. writes .env only with consent."""
    say()
    say(BOLD("  inkpost setup"))
    say(DIM("  three things decide whether this works: d2, a model, and some posts."))
    say()

    d2 = _which(config.D2_BIN) or _which("d2")
    if d2:
        say("   %s d2 is installed" % OK("✓"))
    else:
        say("   %s d2 is missing. it does the drawing, so it is required." % BAD("✗"))
        say("     " + BOLD("brew install d2"))
        say(DIM("     or: curl -fsSL https://d2lang.com/install.sh | sh -s --"))
        say(DIM("     then run inkpost setup again."))
        say()
        return 1

    if config.load_env():
        say("   %s openrouter key found" % OK("✓"))
    elif _which(config.CLAUDE_BIN):
        say("   %s the claude cli is installed — that is enough" % OK("✓"))
        say(DIM("     an openrouter key would also give you a faster free option."))
    else:
        say("   %s no model yet. the free option takes about a minute to set up:" % WARN("!"))
        say("     1. open " + BOLD("https://openrouter.ai/keys"))
        say("     2. make a key (free models cost nothing)")
        say("     3. paste it below")
        say()
        try:
            key = input(DIM("   paste key (or press enter to skip) › ")).strip()
        except (EOFError, KeyboardInterrupt):
            key = ""
        if key.startswith("sk-or-"):
            envp = os.path.join(config.ROOT, ".env")
            existing = ""
            if os.path.exists(envp):
                with open(envp, encoding="utf-8") as fh:
                    existing = fh.read()
            if "OPENROUTER_API_KEY" in existing:
                say("   " + WARN("a key is already in .env — leaving it alone"))
            else:
                with open(envp, "a", encoding="utf-8") as fh:
                    if existing and not existing.endswith("\n"):
                        fh.write("\n")
                    fh.write("OPENROUTER_API_KEY=%s\n" % key)
                say("   %s saved to .env (gitignored)" % OK("✓"))
        elif key:
            say("   " + BAD("that does not look like an openrouter key (they start sk-or-)"))
        else:
            say(DIM("   skipped. the mock backend still works for trying things out."))

    posts = blog_posts()
    if posts:
        say("   %s %d posts in %s" % (OK("✓"), len(posts), config.POSTS_DIR))
    else:
        say("   %s no posts folder yet" % WARN("!"))
        say(DIM("     point at yours: ") + BOLD("export INKPOST_POSTS_DIR=/path/to/your/posts"))
        say(DIM("     or just pass a file: ") + BOLD("inkpost some-post.md"))

    say()
    say("  " + BOLD("you are set.") + DIM("  run ") + BOLD("inkpost") + DIM(" to pick a post."))
    say()
    return 0


# ----------------------------------------------------------------------- run
def do_run(text, title, slug, modes, fmts, backend, model, open_after):
    run_dir = os.path.join(config.RUNS_DIR, slug)
    src_dir = os.path.join(run_dir, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(run_dir, "post.md"), "w", encoding="utf-8") as f:
        f.write(text)

    name, reason = planner.select_backend(backend)
    say()
    say("  " + BOLD(title))
    say("  " + DIM("%s · %s · %s" % (name, model or config.CLAUDE_MODEL,
                                     ", ".join(modes))))
    say()

    t0 = time.time()
    with Progress("reading the post") as pr:
        try:
            plan, meta = planner.plan(text, name, title=title, model=model)
        except planner.PlannerError as e:
            say(BAD("  ✗ " + e.message))
            raise SystemExit(1)
        pr.text("planned")
    took = time.time() - t0
    diagrams = plan["diagrams"]
    say("  %s %s %s" % (OK("✓"), "%d diagrams" % len(diagrams),
                        DIM("in %.0fs · %s" % (took, meta.get("model") or name))))
    for w in plan.get("warnings", []):
        say("    " + WARN("! " + str(w)[:90]))
    say()

    for d in diagrams:
        say("   %s  %s" % (ACC("◆"), BOLD(d["title"])))
        say("      %s" % DIM(d.get("move", "")[:72]))

    # validate + write sources
    ok_rows = []
    for i, d in enumerate(diagrams, 1):
        pat = d["pattern"]
        layout = renderer.layout_for(pat, modes[0])
        errs = renderer.preflight(d["d2"], layout)
        if errs:
            fixed, _ = planner.repair_d2(d["d2"], [], errs, name, model)
            if not renderer.preflight(fixed, layout):
                d["d2"] = fixed
            else:
                say("   " + BAD("✗ %s did not compile — skipped" % d["slug"]))
                continue
        with open(os.path.join(src_dir, d["slug"] + ".d2"), "w", encoding="utf-8") as f:
            f.write(d["d2"])
        ok_rows.append(d)

    if not ok_rows:
        say(BAD("  nothing compiled."))
        raise SystemExit(1)

    jobs = []
    for d in ok_rows:
        for mode in modes:
            for fmt in fmts:
                if fmt == "gif" and not patterns.PATTERNS[d["pattern"]].get("gif"):
                    continue
                jobs.append({"src": d["d2"], "pattern": d["pattern"], "slug": d["slug"],
                             "mode": mode, "fmt": fmt})

    say()
    made = []
    with Progress("rendering %d images" % len(jobs)) as pr:
        done = 0
        for j in jobs:
            try:
                blob = renderer.render(j["src"], j["pattern"], j["mode"], j["fmt"])
                dest_dir = os.path.join(run_dir, "out", j["mode"])
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, j["slug"] + "." + j["fmt"])
                with open(dest, "wb") as fh:
                    fh.write(blob)
                made.append(dest)
            except Exception as e:                   # noqa: BLE001
                say("   " + BAD("✗ %s/%s: %s" % (j["mode"], j["slug"], str(e)[:60])))
            done += 1
            pr.text("rendering %d/%d" % (done, len(jobs)))

    say()
    lines = ["%s  %s" % (OK("✓"), BOLD("%d images" % len(made))),
             DIM("   %s" % run_dir)]
    for ln in boxed(lines, title=" inkpost ", color="yellow"):
        say("  " + ln if not HAVE_CLYPI else ln)
    say()
    if open_after and made:
        subprocess.run(["open", os.path.join(run_dir, "out")], check=False)
    return run_dir


# ---------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="inkpost", add_help=True,
        description="turn a post into hand-drawn diagrams")
    ap.add_argument("post", nargs="?", help="a .md file, or a slug from the blog folder")
    ap.add_argument("-m", "--modes", default="",
                    help="comma separated, or 'all' (default: %s)" %
                         ",".join(presets.DEFAULT_MODES))
    ap.add_argument("-f", "--formats", default="png,svg", help="png,svg,gif")
    ap.add_argument("-b", "--backend", default="auto",
                    help="auto|claude-code|openrouter|mock")
    ap.add_argument("--model", default=None, help="override the model")
    ap.add_argument("--list", action="store_true", help="posts, modes, backends")
    ap.add_argument("--runs", action="store_true", help="what you have made")
    ap.add_argument("--doctor", action="store_true", help="check d2, models and posts")
    ap.add_argument("--setup", action="store_true", help="walk through first-time setup")
    ap.add_argument("--open", dest="open_slug", default=None, help="reopen a run")
    ap.add_argument("--posts-dir", default=None,
                    help="folder of .md posts to pick from (else INKPOST_POSTS_DIR, else ./posts)")
    ap.add_argument("--no-open", action="store_true", help="do not open a file browser at the end")
    ap.add_argument("--version", action="version", version="inkpost " + __version__)
    a = ap.parse_args(argv)

    if a.posts_dir:
        config.POSTS_DIR = os.path.abspath(os.path.expanduser(a.posts_dir))

    if a.doctor:
        raise SystemExit(show_doctor())
    if a.setup:
        raise SystemExit(show_setup())
    if a.list:
        return show_list()
    if a.runs:
        return show_runs()
    if a.open_slug:
        p = os.path.join(config.RUNS_DIR, a.open_slug, "out")
        if not os.path.isdir(p):
            raise SystemExit(BAD("no run called %r" % a.open_slug))
        return subprocess.run(["open", p], check=False) and None

    modes = parse_modes(a.modes)
    fmts = [x.strip() for x in a.formats.split(",") if x.strip()]

    # first-run kindness: if the essentials are missing, say so plainly instead
    # of failing somewhere deeper with a stack trace.
    blockers = [r for r in check_all() if not r[0] and r[4]]
    if blockers and a.backend == "auto":
        hard = [r for r in blockers if r[1] in ("d2", "a model")]
        if hard:
            say()
            for _, label, detail, fix, _req in hard:
                say("  %s %s — %s" % (BAD("✗"), label, detail))
                say("    %s %s" % (DIM("fix:"), fix))
            say()
            say(DIM("  or see everything at once: ") + BOLD("inkpost --doctor"))
            say()
            raise SystemExit(1)

    text, title, slug = resolve_post(a.post) if a.post else pick_post()
    do_run(text, title, slug, modes, fmts, a.backend, a.model, not a.no_open)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say()
        say(DIM("  stopped."))
        sys.exit(130)
