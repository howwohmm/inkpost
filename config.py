"""sketch studio config. stdlib only. every knob lives here.

SPEC.md section 4. written first, then frozen — every other module imports this
and nothing else crosses a lane boundary.

two things are per-user rather than per-install: where your posts live, and what
your writing sounds like. both resolve env var -> ~/.config/inkpost/config.json
-> a sane default, and neither can raise.
"""
import json, os, shutil

ROOT      = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR  = os.path.join(ROOT, "runs")
CACHE_DIR = os.path.join(ROOT, ".cache", "renders")
UI_FILE   = os.path.join(ROOT, "ui", "index.html")
ENV_FILE  = os.path.join(ROOT, ".env")

HOST, PORT = "127.0.0.1", 8788          # never 0.0.0.0

# ---- user config file -----------------------------------------------------
# ~/.config/inkpost/config.json — entirely optional. recognised keys:
#   {"posts_dir": "~/writing/posts",
#    "voice": "lowercase-diary" | {"author": ..., "style": ..., "lowercase": ...},
#    "author": "...", "style": "...", "lowercase": true}
APP_NAME   = "inkpost"
CONFIG_DIR = os.path.expanduser(
    os.environ.get("INKPOST_CONFIG_DIR") or os.path.join("~", ".config", APP_NAME))
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def _env(name):
    """an env var, or None. an empty or blank value counts as unset."""
    v = os.environ.get(name)
    v = v.strip() if isinstance(v, str) else ""
    return v or None


def _flag(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def user_config():
    """the optional json config file as a dict. a missing, unreadable or
    malformed file is simply an empty dict — this never raises."""
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cwd():
    try:
        return os.getcwd()
    except OSError:                                   # cwd was deleted
        return ROOT


# ---- posts ----------------------------------------------------------------
def posts_dir():
    """where the picker looks for .md posts. resolution order:

      1. $INKPOST_POSTS_DIR
      2. "posts_dir" in ~/.config/inkpost/config.json
      3. ./posts, relative to where you ran the command
      4. the package's own posts/, if it ships one

    the first two win even when they do not exist yet — they are explicit
    intent. a missing directory is never fatal: callers already treat it as an
    empty list and you can always pass a file path instead.
    """
    for cand in (_env("INKPOST_POSTS_DIR"), user_config().get("posts_dir")):
        if isinstance(cand, str) and cand.strip():
            return os.path.abspath(os.path.expanduser(cand.strip()))
    local = os.path.abspath(os.path.join(_cwd(), "posts"))
    if os.path.isdir(local):
        return local
    shipped = os.path.join(ROOT, "posts")
    if os.path.isdir(shipped):
        return shipped
    return local


# module-level for the callers that read it directly (server.py, cli.py).
POSTS_DIR = posts_dir()

# ---- voice ----------------------------------------------------------------
# the planner builds its system prompts from this. the craft rules (lift the
# author's words verbatim, short lines, one accent node) are generic and live in
# planner.py; only the name, the register and the lowercase demand are yours.
#
# a preset may also be a json file, which is looked up before the built-ins:
#   ~/.config/inkpost/voices/<name>.json   or   <package>/voices/<name>.json
VOICE_KEYS = ("author", "style", "lowercase")

GENERIC_VOICE = {
    "author": "the author",
    "style": ("you have never read {author} before, so do not invent a voice for them: "
              "every label must be lifted verbatim from the post in front of you and must "
              "match that post's own register, whatever the register turns out to be."),
    "lowercase": False,
}

VOICE_PRESETS = {
    "generic": GENERIC_VOICE,
    # the original house voice this tool was built for. restore it with
    #   INKPOST_VOICE=lowercase-diary INKPOST_AUTHOR=<name>
    "lowercase-diary": {
        "author": "the author",
        "style": "{author} writes lowercase diary prose about building things.",
        "lowercase": True,
    },
}


def _voice_file(name):
    safe = os.path.basename(str(name).strip())
    for d in (os.path.join(CONFIG_DIR, "voices"), os.path.join(ROOT, "voices")):
        p = os.path.join(d, safe + ".json")
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _voice_preset(name):
    return _voice_file(name) or VOICE_PRESETS.get(str(name).strip().lower())


def voice(name=None):
    """-> {"author": str, "style": str, "lowercase": bool}.

    each layer overrides the one before it:
      1. the `generic` preset — no name, no register, no lowercase demand
      2. the preset named by `name`, $INKPOST_VOICE, or "voice" in the config
         file (a preset name, or an inline object with the same three keys)
      3. "author" / "style" / "lowercase" at the top level of the config file
      4. $INKPOST_AUTHOR / $INKPOST_VOICE_STYLE / $INKPOST_VOICE_LOWERCASE

    "{author}" inside a style string is replaced with the resolved author, so a
    preset can be named-in-place without hardcoding anyone.
    """
    cfg = user_config()
    out = dict(GENERIC_VOICE)

    picked = name or _env("INKPOST_VOICE") or cfg.get("voice")
    if isinstance(picked, dict):
        out.update({k: v for k, v in picked.items() if k in VOICE_KEYS})
    elif isinstance(picked, str) and picked.strip():
        preset = _voice_preset(picked)
        if preset:
            out.update({k: v for k, v in preset.items() if k in VOICE_KEYS})

    for k in VOICE_KEYS:
        if isinstance(cfg.get(k), (str, bool)) and cfg.get(k) != "":
            out[k] = cfg[k]

    for k, var in (("author", "INKPOST_AUTHOR"), ("style", "INKPOST_VOICE_STYLE")):
        v = _env(var)
        if v:
            out[k] = v
    lc = _env("INKPOST_VOICE_LOWERCASE")
    out["lowercase"] = _flag(lc, _flag(out.get("lowercase")))

    out["author"] = (str(out.get("author") or "").strip() or GENERIC_VOICE["author"])
    out["style"] = str(out.get("style") or "").replace("{author}", out["author"]).strip()
    return out


VOICE = voice()

# ---- d2 -------------------------------------------------------------------
D2_BIN         = os.environ.get("INKPOST_D2") or shutil.which("d2") or "/opt/homebrew/bin/d2"
PAD            = 40
PNG_SCALE      = "1"      # png is ALREADY 2x the svg viewBox. --scale 2 = 4x, 1.2MB, 1.0s.
ANIMATE_MS     = 1200
PREFLIGHT_TIMEOUT = 15
RENDER_TIMEOUT    = 60
RENDER_WORKERS    = 4
VALID_THEMES = {0,1,3,4,5,6,7,8,100,101,102,103,104,105,200,201,300,301,302,303}  # no theme 2

# ---- planner --------------------------------------------------------------
BACKEND       = os.environ.get("INKPOST_BACKEND", "auto")   # auto|openrouter|claude-code|mock
MIN_DIAGRAMS, MAX_DIAGRAMS = 2, 4
MAX_LLM_CALLS_PER_RUN = 4        # 1 plan + 1 plan-repair + up to 2 d2-repairs. hard cap.
PLAN_TIMEOUT  = 480

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_HEADERS = {"HTTP-Referer": "http://localhost:8788",
                      "X-OpenRouter-Title": "sketch"}
# all three support response_format, so there is exactly one request shape.
# backends that plan by filling pattern slots instead of authoring d2.
# small/free models cannot write valid d2; slot mode makes them reliable.
MIN_SLOT_FILL = 1.0   # every label must come back filled, else drop that diagram

SLOT_BACKENDS = ("openrouter",)

# benchmarked on a real post, 11 Sep 2026: wall-clock to a valid plan.
# free models 429 often (shared upstream pool), so the chain matters.
OPENROUTER_CHAIN = ["poolside/laguna-xs-2.1:free",        # ~14s
                    "inclusionai/ling-3.0-flash-fin:free", # ~19s
                    "poolside/laguna-s-2.1:free",          # ~21s
                    "dots-studio/dots-3-note-preview:free"]  # ~45s, last resort
OPENROUTER_MAX_TOKENS = 8000     # response-healing CANNOT repair a max_tokens truncation
OPENROUTER_RPM        = 18       # under the documented 20/min ceiling
OPENROUTER_TIMEOUT    = 45

CLAUDE_BIN   = os.environ.get("INKPOST_CLAUDE") or shutil.which("claude") or "claude"
CLAUDE_MODEL = os.environ.get("INKPOST_CLAUDE_MODEL", "opus")
CLAUDE_TIMEOUT = 420

# ---- labels ---------------------------------------------------------------
FONT_SIZE_MIN, FONT_SIZE_MAX = 8, 100     # d2's hard limits. verified: 8/60/100 ok, 0/5/101/200 fail.
ACCENT_FILL = "#ffe8a3"                   # the literal in every template. renderer substitutes it.
ACCENT_FONT = "#111111"


def load_env(name="OPENROUTER_API_KEY"):
    """~10 line .env parser. no python-dotenv. the value is never logged, never
    returned by a route, never written into a manifest."""
    if not os.path.exists(ENV_FILE):
        return None
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip("'\"") or None
    return None
