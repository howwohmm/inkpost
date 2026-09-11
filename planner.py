"""planner — postprep, prompt, three backends, lint, validate, repair.

LANE A owns this file. SPEC.md section 7. the signatures are the lane contract
and are frozen.

signature note — SPEC contradicts itself in two places. section 7.0 (the lane
contract) and the file map win over the section headers of 7.5/7.6:
  validate_plan(plan) -> (problems, warnings)      NOT -> list[str]
  lint(src)           -> (fixed_src, problems, notes)   NOT -> (fixed, problems)

plan json shape (SPEC 7.4):
  {"diagrams": [{"slug","title","pattern","move","d2"}]}   2..4 items

meta from plan() and repair_d2():
  {"backend","model","provider","generation_id","ms","calls","cost_usd"}
  it NEVER contains the api key. nothing in this module prints, logs or returns
  the key; it is read once per request from config.load_env() and dropped.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime

import config
import patterns

# ---------------------------------------------------------------------------
# the json schema (SPEC 7.4) — sent as text inside the system prompt and
# enforced locally by validate_plan(). every field is a string and `pattern` is
# a hard enum, so no provider has to support anything exotic.
# ---------------------------------------------------------------------------
PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["diagrams"],
    "properties": {"diagrams": {"type": "array", "minItems": 2, "maxItems": 4,
        "items": {"type": "object", "additionalProperties": False,
            "required": ["slug", "title", "pattern", "move", "d2"],
            "properties": {
                "slug":    {"type": "string", "maxLength": 60},
                "title":   {"type": "string", "maxLength": 120},
                "pattern": {"type": "string", "enum": list(patterns.PATTERNS)},
                "move":    {"type": "string", "maxLength": 200},
                "d2":      {"type": "string", "minLength": 20}}}}}}

PATTERN_NAMES = list(patterns.PATTERNS)
DIAGRAM_KEYS = ("slug", "title", "pattern", "move", "d2")

_RULE = "\u2500" * 62


def _render_catalog():
    """the {{CATALOG}} block, built from patterns.PATTERNS at import time so the
    prompt can never drift from the code (SPEC 7.2, test 34). every `d2`
    template goes in byte-identically."""
    out = []
    for name, p in patterns.PATTERNS.items():
        d2 = p["d2"]
        if not d2.endswith("\n"):
            d2 += "\n"
        out.append(
            "%s\npattern: %s\nmove: %s\nuse when: %s\nlayout: %s\ntemplate:\n%snotes: %s\n"
            % (_RULE, name, p["move"], p["when"], p["layout_note"], d2, p["notes"]))
    return "".join(out) + _RULE


CATALOG = _render_catalog()

# the literal system prompt of SPEC 7.2. the only interpolations are
# {{CATALOG}} (SPEC 7.2) and {{SCHEMA}} (SPEC 7.4 — "sent as text inside the
# system prompt"; 7.2 leaves it no slot of its own, so it sits with the OUTPUT
# rules where it belongs).
_SYSTEM_PROMPT_TEMPLATE = r"""you are the diagram planner for "inkpost", a tool that turns {{AUTHORS}} blog posts into
hand-drawn d2 diagrams. {{STYLE}}

your job: read the post, find the 2 to 4 distinct MOVES it makes, pick one pattern
for each move, and write the d2 source for it by taking that pattern's template and
replacing its placeholder labels with {{AUTHORS_CAPS}} OWN SENTENCES.

VOICE RULES — these are the whole job, not decoration:
{{LOWERCASE_RULE}}- use {{AUTHORS}} words VERBATIM. lift their phrases straight out of the post. cutting a
  sentence short is fine; rewriting it is not. do not summarise them, do not
  paraphrase them into clean english, do not add words they did not write. the
  diagram is a re-typesetting of their sentences, not a description of them.
- break every label into short lines with a literal \n inside the quoted string.
  2 to 6 words per line, under 34 characters per line, at most 4 lines per label.
  "plan how to\ndo the work" — never "plan how to do the work".
- keep their curly quotes “ ” ’ exactly as they appear in the post. they are safe
  inside d2 labels and they need no escaping.
- no emoji. no clip-art. no gradients. no marketing words. no exclamation marks
  they did not write themselves.

D2 RULES — break one of these and the diagram fails to compile:
- keep the template's structure, keys and shapes. change the LABELS. you may add
  or remove repeated sibling nodes (options, steps, panels, inputs) within the
  count the pattern allows. do not invent new syntax.
- a key must never contain an unquoted . or : — `a.b: hello` silently becomes a
  container and `a:b: hello` silently becomes a node labelled "b: hello". d2 will
  not warn you. use plain keys: o1, s2, p4, hub, done.
- never use |md ... | labels. they render borderless and over-wide. use a quoted
  "line\nline" string.
- never use icon:. never set style.font-size outside 8 to 100.
- exactly ONE yellow node per diagram: style.fill: "#ffe8a3" on the payoff — the
  thing the essay is actually for. everything else stays default. the SAME concept
  may carry the yellow in two places (collapse paints "me" yellow in both
  containers; taxonomy paints the third kind and the summary). that is one concept,
  not two accents. write the fill exactly as "#ffe8a3" — the tool recolours it.
- captions are {shape: text; style.italic: true} pinned with a separate
  `caption.near: bottom-center` line.

CHOOSING:
- one diagram per DISTINCT move. two diagrams of the same move is a failure. one
  diagram for a post that makes three moves is a failure.
- 2 diagrams for a short post, 3 to 4 for a long one. never more than 4.
- do not use the same pattern twice in one plan.
- if the post has no structure, only one great sentence, use `poster` with that line.

FOR EACH DIAGRAM ALSO WRITE:
  "slug"  - lowercase, hyphenated, 2-4 words, unique within the plan.
  "title" - a short {{LC}}name for the diagram, 3-8 words.
  "move"  - ONE {{LC}}sentence naming the essay move this diagram carries.
            this is what {{AUTHOR}} reads to decide whether you understood the post.

OUTPUT — one json object, nothing before it, nothing after it, no code fence:

{"diagrams":[{"slug":"...","title":"...","pattern":"<one of the names below>",
              "move":"...","d2":"<the full d2 source as one string>"}]}

the "d2" value is a json string, so every newline in the source is \n and every
quote inside it is \". 2 to 4 diagrams.

the json schema, checked locally on every answer:
{{SCHEMA}}

THE PATTERNS
{{CATALOG}}"""

def _voice_bits(voice=None):
    """-> (author, possessive, style, lowercase). config.VOICE by default."""
    v = voice or config.VOICE
    author = str(v.get("author") or "the author").strip() or "the author"
    style = str(v.get("style") or "").replace("{author}", author).strip()
    return author, author + "'s", style, bool(v.get("lowercase"))


def _apply_voice(template, voice=None, lowercase_rule=""):
    """fill the voice placeholders of a prompt template. everything else in the
    template is a craft rule and is the same for every author."""
    author, poss, style, lower = _voice_bits(voice)
    return (template
            .replace("{{AUTHORS_CAPS}}", poss.upper())
            .replace("{{AUTHORS}}", poss)
            .replace("{{AUTHOR}}", author)
            .replace("{{STYLE}}", style)
            .replace("{{LOWERCASE_RULE}}", lowercase_rule if lower else "")
            .replace("{{LC}}", "lowercase " if lower else ""))


# the lowercase demand is the one voice rule that is not universal, so it is a
# whole bullet that appears only when the voice asks for it.
_LOWERCASE_RULE = "- every label is lowercase. no title case. no capital i. ever.\n"


def build_system_prompt(voice=None):
    """the full-authoring prompt (claude-code backend), rendered for a voice."""
    return (_apply_voice(_SYSTEM_PROMPT_TEMPLATE, voice, _LOWERCASE_RULE)
            .replace("{{SCHEMA}}", json.dumps(PLAN_SCHEMA, ensure_ascii=False))
            .replace("{{CATALOG}}", CATALOG))


SYSTEM_PROMPT = build_system_prompt()

# SPEC 7.3
USER_TEMPLATE = """post title: {title}
post description: {description}

--- POST ---
{body}
--- END POST ---

plan the diagrams. 2 to 4. return the json object and nothing else."""

# SPEC 7.8
D2_REPAIR_PROMPT = """you fix d2 v0.9.0 source. return ONLY the corrected d2, no code fence, no prose,
no explanation. change as little as possible. never change any label TEXT — only
the syntax around it. keep the "#ffe8a3" fill exactly where it is."""


class PlannerError(Exception):
    """.message is one lowercase line, safe to show the user."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# 7.1 postprep
# ---------------------------------------------------------------------------
_HERO_RE = re.compile(r"^!\[.*\]\(.*\)$")
_SHARE_RE = re.compile(r"^\[Share\]\(<?https?://.*\)$")
_BOILERPLATE = (
    "Thanks for reading! Subscribe for free to receive new posts and support my work.",
    "Thanks for reading! This post is public so feel free to share it.",
)
_MAX_BODY = 24000


def _norm(line):
    return re.sub(r"\s+", " ", line.strip())


def _parse_frontmatter(lines):
    """~15-line hand scanner. quoted or bare values, [a, b] lists. only `title`
    and `description` are kept."""
    meta = {}
    for line in lines:
        if not line.strip() or line.startswith("#") or ":" not in line:
            continue
        if line[:1] in (" ", "\t", "-"):
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = v[1:-1]
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]          # outer STRAIGHT quotes only. curly ones survive.
        meta[k] = v
    return meta


def clean_post(text):
    """-> (meta, body). meta = {"title","description"}, empty strings when absent.

    SPEC 7.1. drops frontmatter, the leading hero image, the substack
    boilerplate WHEREVER it appears (snap-out-of-it strands it mid-body), the
    [Share](...) lines. never touches curly quotes.
    """
    meta = {"title": "", "description": ""}
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    # 1. frontmatter
    if s.startswith("---"):
        lines = s.split("\n")
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end is not None:
            fm = _parse_frontmatter(lines[1:end])
            meta["title"] = fm.get("title", "") or ""
            meta["description"] = fm.get("description", "") or ""
            s = "\n".join(lines[end + 1:])

    lines = s.split("\n")

    # 2. a leading hero image
    first = 0
    while first < len(lines) and not lines[first].strip():
        first += 1
    if first < len(lines) and _HERO_RE.match(lines[first].strip()):
        del lines[first]

    # 3 + 4. boilerplate anywhere, share links anywhere
    kept = []
    for line in lines:
        n = _norm(line)
        if n in _BOILERPLATE:
            continue
        if _SHARE_RE.match(n):
            continue
        kept.append(line)

    body = "\n".join(kept)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()        # 5

    # 7. title
    if not meta["title"]:
        for line in body.split("\n"):
            if line.startswith("# "):
                meta["title"] = line[2:].strip()
                break
    if not meta["title"]:
        for line in body.split("\n"):
            if line.strip():
                meta["title"] = line.strip()
                break
    meta["title"] = meta["title"][:60].strip()

    # 8. length
    if len(body) > _MAX_BODY:
        body = body[:18000] + "\n\n[…middle trimmed…]\n\n" + body[-6000:]

    return meta, body


def slugify(title):
    """-> str. delete ' and U+2019 FIRST so the slug matches the blog's own
    filenames (theres, not there-s). SPEC 7.1."""
    t = (title or "").lower()
    for ch in ("'", "\u2019", "\u2018"):
        t = t.replace(ch, "")
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = re.sub(r"-{2,}", "-", t).strip("-")[:60].strip("-")
    if not t:
        t = "sketch-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    return t


# ---------------------------------------------------------------------------
# backend selection (SPEC 4 / 7.0)
# ---------------------------------------------------------------------------
def select_backend(req="auto"):
    """-> (name, reason). name in openrouter|claude-code|mock.

    mock is never auto-selected over a working backend; it is chosen explicitly
    or reached only when nothing else exists."""
    req = (req or "auto").strip() or "auto"
    if req == "openrouter":
        if config.load_env():
            return "openrouter", "openrouter chosen explicitly"
        return "openrouter", "openrouter chosen explicitly but no OPENROUTER_API_KEY in .env"
    if req == "claude-code":
        return "claude-code", "claude-code chosen explicitly"
    if req == "mock":
        return "mock", "mock chosen explicitly"
    if req != "auto":
        raise PlannerError("unknown backend %r — use auto, openrouter, claude-code or mock" % req)

    # quality first. the claude cli writes the diagram source directly and picks
    # the author's own sentences; the free openrouter models can only fill slots and
    # their wording is noticeably weaker. prefer claude when it exists.
    if shutil.which(config.CLAUDE_BIN) or os.path.exists(config.CLAUDE_BIN):
        return "claude-code", "the claude cli — best wording"
    if config.load_env():
        return "openrouter", "no claude cli — using a free openrouter model"
    return "mock", ("no claude cli and no OPENROUTER_API_KEY in .env — "
                    "running mock plans")


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------
_THINK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.S | re.I)
_FENCE_OPEN = re.compile(r"^```[A-Za-z0-9_+-]*[ \t]*\r?\n?")
_FENCE_CLOSE = re.compile(r"\r?\n?```\s*$")


def strip_fences(text):
    """drop a leading <think> block and any surrounding code fence. the
    claude-code `result` is fence-wrapped in practice even when the prompt
    forbids it, so this is mandatory rather than defensive."""
    t = (text or "").strip()
    t = _THINK_RE.sub("", t).strip()
    if t.startswith("```"):
        t = _FENCE_OPEN.sub("", t)
        t = _FENCE_CLOSE.sub("", t)
    return t.strip()


def _extract_json(text):
    """fence-strip -> parse -> outermost-brace extract. None when nothing parses."""
    t = strip_fences(text)
    if not t:
        return None
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        try:
            obj = json.loads(t[i:j + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _blank_meta(backend, model):
    return {"backend": backend, "model": model, "provider": None,
            "generation_id": None, "ms": 0, "calls": 0, "cost_usd": 0.0}


# ---------------------------------------------------------------------------
# 7.7 backends — generate(system, user) -> (text, meta)
# ---------------------------------------------------------------------------
def _mock_pick(body):
    """2 or 3 DISTINCT patterns, chosen from sha256(body). deterministic."""
    d = hashlib.sha256(body.encode("utf-8")).digest()
    n = 2 + (d[0] % 2)
    picked = []
    step = 0
    while len(picked) < n and step < 64:
        name = PATTERN_NAMES[d[(step + 1) % len(d)] % len(PATTERN_NAMES)]
        if name not in picked:
            picked.append(name)
        step += 1
    for name in PATTERN_NAMES:                       # deterministic backstop
        if len(picked) >= n:
            break
        if name not in picked:
            picked.append(name)
    return picked


def _mock_body(user):
    a = user.find("--- POST ---")
    b = user.find("--- END POST ---")
    if a != -1 and b > a:
        return user[a + len("--- POST ---"):b].strip()
    return user.strip()


def _mock_title(user):
    for line in user.split("\n"):
        if line.startswith("post title:"):
            return line[len("post title:"):].strip()
    return ""


def _gen_mock(system, user, model=None):
    """no network, no subprocess, deterministic. returns the real house
    templates verbatim, so every mock plan lints clean, compiles clean and
    renders — a working end-to-end fixture, not a stub."""
    t0 = time.monotonic()
    body = _mock_body(user)
    title = _mock_title(user)
    base = slugify(title)[:36] if title.strip() else "mock-plan"
    diagrams = []
    for name in _mock_pick(body):
        p = patterns.PATTERNS[name]
        d2 = p["d2"]
        diagrams.append({
            "slug": (base + "-" + name)[:60].strip("-"),
            "title": "%s (%s)" % (p["move"], name),
            "pattern": name,
            "move": p["move"],
            "d2": d2,
        })
    if os.environ.get("INKPOST_MOCK_FAIL") == "compile" and diagrams:
        # `shape: blob` is invalid at compile time and lint cannot fix it, so
        # the repair path is exercised on purpose rather than by luck.
        diagrams[0]["d2"] = (diagrams[0]["d2"]
                             + 'broken: "boom" {shape: blob; style.font-size: 0}\n')
    text = json.dumps({"diagrams": diagrams}, ensure_ascii=False)
    meta = _blank_meta("mock", model or "mock")
    meta.update({"provider": "mock", "ms": int((time.monotonic() - t0) * 1000),
                 "calls": 1, "cost_usd": 0.0})
    return text, meta


def _gen_claude(system, user, model=None):
    """the existing claude login, no api key. CLAUDECODE is stripped from the
    env — the proven nested-claude fix from post-cooker."""
    m = model or config.CLAUDE_MODEL
    cmd = [config.CLAUDE_BIN, "-p", user,
           "--system-prompt", system,
           "--model", m,
           "--tools", "",
           "--output-format", "json"]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    last = ""
    for attempt in (1, 2):
        t0 = time.monotonic()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=config.CLAUDE_TIMEOUT, cwd=config.ROOT, env=env)
        except FileNotFoundError:
            raise PlannerError("claude not found at %s — the claude-code backend is "
                               "unavailable" % config.CLAUDE_BIN)
        except subprocess.TimeoutExpired:
            raise PlannerError("claude -p timed out after %ss. not retried — a second run "
                               "costs real money." % config.CLAUDE_TIMEOUT)
        ms = int((time.monotonic() - t0) * 1000)
        out = (r.stdout or "").strip()
        try:
            env_obj = json.loads(out)
        except Exception:
            env_obj = None
        if isinstance(env_obj, dict):
            bad = (env_obj.get("is_error") is True
                   or env_obj.get("subtype", "success") != "success")
            text = env_obj.get("result") or ""
            cost = env_obj.get("total_cost_usd") or 0.0
            dur = env_obj.get("duration_ms") or ms
        else:
            bad = r.returncode != 0
            text = out
            cost, dur = 0.0, ms
        if bad or not str(text).strip():
            last = (r.stderr or "").strip()[:200] or "claude returned an empty result"
            if attempt == 1:
                continue
            raise PlannerError("claude -p failed twice: %s" % (last or "empty result"))
        meta = _blank_meta("claude-code", m)
        meta.update({"provider": "anthropic", "ms": int(dur), "calls": 1,
                     "cost_usd": float(cost)})
        return strip_fences(str(text)), meta
    raise PlannerError("claude -p failed: %s" % last)


# --- openrouter -------------------------------------------------------------
_BUCKET = deque()
_BUCKET_LOCK = threading.Lock()


def _throttle():
    """module-level token bucket: OPENROUTER_RPM requests per rolling 60s on a
    time.monotonic() deque, shared by plan and repair calls. it sleeps rather
    than erroring."""
    while True:
        with _BUCKET_LOCK:
            now = time.monotonic()
            while _BUCKET and now - _BUCKET[0] > 60:
                _BUCKET.popleft()
            if len(_BUCKET) < config.OPENROUTER_RPM:
                _BUCKET.append(now)
                return
            wait = 60 - (now - _BUCKET[0]) + 0.05
        time.sleep(max(0.05, min(wait, 60)))


def _hdr(resp, name):
    try:
        h = getattr(resp, "headers", None)
        if h is not None:
            get = getattr(h, "get", None)
            if get:
                return get(name)
    except Exception:
        pass
    try:
        return resp.getheader(name)
    except Exception:
        return None


def _err_envelope(raw):
    """{"error":{"code":int,"message":str,"metadata":{...}}} — no top-level
    `type`, and often no `metadata` key at all. parse it defensively."""
    try:
        obj = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    e = obj.get("error")
    return e if isinstance(e, dict) else {}


def _or_request(key, model, system, user, max_tokens, minimal):
    body = {"model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": 0.4}
    if not minimal:
        body["response_format"] = {"type": "json_object"}
        body["plugins"] = [{"id": "response-healing"}]
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    headers.update(config.OPENROUTER_HEADERS)
    req = urllib.request.Request(config.OPENROUTER_URL,
                                 data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    _throttle()
    return urllib.request.urlopen(req, timeout=config.OPENROUTER_TIMEOUT)


def _gen_openrouter(system, user, model=None):
    key = config.load_env()
    if not key:
        raise PlannerError("no OPENROUTER_API_KEY in .env — add it, or switch the backend "
                           "to claude-code")
    chain = [model] if model else list(config.OPENROUTER_CHAIN)
    user_orig = user
    last = "no model was tried"
    calls = 0
    t_all = time.monotonic()

    for name in chain:
        max_tokens = config.OPENROUTER_MAX_TOKENS
        minimal = False
        length_retried = False
        minimal_retried = False
        soft_retried = False
        rl_retries = 0
        json_retried = False
        user = user_orig
        while True:
            try:
                resp = _or_request(key, name, system, user, max_tokens, minimal)
                calls += 1
                raw = resp.read()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "replace")
                gen_id = _hdr(resp, "X-Generation-Id")
                provider = _hdr(resp, "X-Provider-Name")
            except urllib.error.HTTPError as e:
                calls += 1
                code = getattr(e, "code", 0)
                try:
                    ebody = e.read()
                    if isinstance(ebody, bytes):
                        ebody = ebody.decode("utf-8", "replace")
                except Exception:
                    ebody = ""
                env = _err_envelope(ebody)
                msg = str(env.get("message") or ebody)[:300]
                md = env.get("metadata") if isinstance(env.get("metadata"), dict) else {}

                if code == 400:
                    if not minimal_retried:
                        minimal, minimal_retried = True, True
                        continue
                    last = "%s: 400 %s" % (name, msg)
                    break
                if code == 401:
                    raise PlannerError("openrouter rejected the key. check .env")
                if code == 402:
                    raise PlannerError("openrouter says insufficient credits — a negative "
                                       "balance blocks even free models")
                if code == 403:
                    # "only available on <tier>" is model-specific, not key-wide.
                    if "only available" in msg.lower() or "not available" in msg.lower():
                        last = "%s: 403 model not available on this tier" % name
                        break                       # hop
                    raise PlannerError("openrouter refused the input: %s reasons=%s "
                                       "flagged_input=%s"
                                       % (msg, md.get("reasons"), md.get("flagged_input")))
                if code == 408:
                    if not soft_retried:
                        soft_retried = True
                        continue
                    last = "%s: 408 timeout" % name
                    break
                if code == 429:
                    ra = _hdr(e, "Retry-After")
                    try:
                        ra = float(ra) if ra is not None else None
                    except Exception:
                        ra = None
                    if ra is not None and ra <= 5 and not soft_retried:
                        soft_retried = True
                        time.sleep(ra)
                        continue
                    # upstream/provider limits are model-specific -> try the next
                    # model. openrouter sends provider_error_code + limit_source;
                    # older shapes used provider_code.
                    upstream = (md.get("provider_code") == "rate_limited"
                                or md.get("provider_error_code")
                                or md.get("provider_name")
                                or str(md.get("limit_source") or "").startswith("upstream")
                                or "upstream" in msg.lower()
                                or "provider returned error" in msg.lower())
                    if upstream:
                        last = "%s: 429 upstream provider rate limit" % name
                        break                       # hop
                    # bare 429 = openrouter's own free-tier limiter (per-minute
                    # or per-day). the per-minute one clears on its own, so back
                    # off and retry before giving up on the whole chain.
                    if rl_retries < 3:
                        rl_retries += 1
                        time.sleep(6 * rl_retries)
                        continue
                    last = ("%s: 429 openrouter free-tier limit (per-minute or the "
                            "50/day cap under $10 lifetime spend)" % name)
                    break                           # hop to the next model
                if code in (502, 503):
                    last = "%s: %s %s" % (name, code, msg)
                    break                           # hop immediately
                last = "%s: %s %s" % (name, code, msg)
                break
            except urllib.error.URLError as e:
                calls += 1
                last = "%s: network error %s" % (name, getattr(e, "reason", e))
                break
            except (TimeoutError, OSError) as e:
                calls += 1
                last = "%s: %s" % (name, e)
                break

            try:
                obj = json.loads(raw)
            except Exception:
                last = "%s: unparseable response body" % name
                break
            choices = obj.get("choices") or []
            if not choices:
                env = obj.get("error") if isinstance(obj.get("error"), dict) else {}
                last = "%s: no choices (%s)" % (name, str(env.get("message") or "")[:200])
                break
            ch = choices[0] or {}
            msg_obj = ch.get("message") or {}
            if ch.get("finish_reason") == "length" and not length_retried:
                # healing cannot repair a max_tokens truncation. a bigger budget
                # is the fix, on the SAME model. do not hop.
                length_retried = True
                max_tokens = max_tokens * 2
                continue
            text = msg_obj.get("content")
            if not text:
                text = msg_obj.get("reasoning") or ""
            text = strip_fences(str(text))
            if not text:
                last = "%s: empty completion" % name
                break
            # thinking models sometimes answer with prose instead of json.
            # retry the same model once with a blunt json-only nudge, then hop
            # rather than failing the whole chain.
            if _extract_json(text) is None:
                if not json_retried:
                    json_retried = True
                    minimal = False
                    user = (user_orig + "\n\nRESPOND WITH THE JSON OBJECT ONLY. "
                            "No analysis, no reasoning, no prose, no code fences. "
                            "Your entire reply must start with { and end with }.")
                    continue
                last = "%s: answered with prose, not json" % name
                break
            usage = obj.get("usage") if isinstance(obj.get("usage"), dict) else {}
            meta = _blank_meta("openrouter", obj.get("model") or name)
            meta.update({"provider": provider or obj.get("provider"),
                         "generation_id": gen_id or obj.get("id"),
                         "ms": int((time.monotonic() - t_all) * 1000),
                         "calls": 1,          # hops and retries are internal
                         "cost_usd": float(usage.get("cost") or 0.0)})
            return text, meta

    raise PlannerError("every free model failed: %s. if these are all 429s, "
                       "the free tier is rate-limited right now — wait a minute "
                       "or switch the backend to claude-code." % last)


def _generate(system, user, backend, model=None):
    if backend == "mock":
        return _gen_mock(system, user, model)
    if backend == "claude-code":
        return _gen_claude(system, user, model)
    if backend == "openrouter":
        return _gen_openrouter(system, user, model)
    raise PlannerError("unknown backend %r — use openrouter, claude-code or mock" % backend)


# ---------------------------------------------------------------------------
# 7.5 validate_plan
# ---------------------------------------------------------------------------
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
_QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _label_lines(d2):
    for m in _QUOTED_RE.finditer(d2):
        s = m.group(1)
        for part in re.split(r"\\n|\n", s):
            yield part


def validate_plan(plan):
    """-> (problems, warnings), both list[str]. problems == [] means valid.
    pure: no network, no subprocess, no mutation. SPEC 7.5."""
    problems, warnings = [], []
    if not isinstance(plan, dict):
        return ["the plan is not a json object"], warnings
    diagrams = plan.get("diagrams")
    if not isinstance(diagrams, list):
        return ['the plan has no "diagrams" list'], warnings
    if len(diagrams) < config.MIN_DIAGRAMS:
        problems.append("%d diagram(s): %d to %d are required"
                        % (len(diagrams), config.MIN_DIAGRAMS, config.MAX_DIAGRAMS))
    if len(diagrams) > config.MAX_DIAGRAMS:
        problems.append("%d diagrams: at most %d are allowed"
                        % (len(diagrams), config.MAX_DIAGRAMS))

    seen_patterns, seen_slugs, moves = {}, {}, {}
    for i, d in enumerate(diagrams, 1):
        tag = "diagram %d" % i
        if not isinstance(d, dict):
            problems.append("%s is not an object" % tag)
            continue
        missing = [k for k in DIAGRAM_KEYS if k not in d]
        if missing:
            problems.append("%s is missing %s" % (tag, ", ".join(missing)))
        extra = [k for k in d if k not in DIAGRAM_KEYS]
        if extra:
            problems.append("%s has unexpected keys: %s" % (tag, ", ".join(sorted(extra))))
        for k in DIAGRAM_KEYS:
            if k in d and not isinstance(d[k], str):
                problems.append('%s: "%s" must be a string' % (tag, k))
        pat = d.get("pattern")
        if isinstance(pat, str):
            if pat not in patterns.PATTERNS:
                problems.append('%s: "%s" is not one of the %d patterns'
                                % (tag, pat, len(PATTERN_NAMES)))
            elif pat in seen_patterns:
                problems.append("%s: pattern %s is already used by diagram %d"
                                % (tag, pat, seen_patterns[pat]))
            else:
                seen_patterns[pat] = i
        slug = d.get("slug")
        if isinstance(slug, str):
            if not _SLUG_RE.match(slug):
                problems.append('%s: slug "%s" is not lowercase-hyphenated' % (tag, slug))
            elif slug in seen_slugs:
                problems.append('%s: slug "%s" collides with diagram %d'
                                % (tag, slug, seen_slugs[slug]))
            else:
                seen_slugs[slug] = i
        src = d.get("d2")
        if isinstance(src, str):
            if not src.strip():
                problems.append("%s: the d2 source is empty" % tag)
            elif ":" not in src:
                problems.append("%s: the d2 source has no ':' — it looks like prose" % tag)
            else:
                for line in _label_lines(src):
                    if len(line) > 34:
                        warnings.append('%s: a label line is %d chars — "%s"'
                                        % (tag, len(line), line[:40]))
                        break
        mv = d.get("move")
        if isinstance(mv, str) and mv.strip():
            key = _norm(mv).lower()
            if key in moves:
                warnings.append("%s: the same move as diagram %d — one diagram per distinct "
                                "move" % (tag, moves[key]))
            else:
                moves[key] = i
    return problems, warnings


def _normalize_plan(plan):
    """the forgiving half of 7.5, kept out of validate_plan so that function
    stays pure. -> (plan, warnings). truncates to MAX_DIAGRAMS and rewrites a
    bad or colliding slug to <NN>-<pattern> rather than rejecting it."""
    warnings = []
    if not isinstance(plan, dict):
        return plan, warnings
    diagrams = plan.get("diagrams")
    if not isinstance(diagrams, list):
        return plan, warnings
    if len(diagrams) > config.MAX_DIAGRAMS:
        warnings.append("the plan had %d diagrams — kept the first %d"
                        % (len(diagrams), config.MAX_DIAGRAMS))
        diagrams = diagrams[:config.MAX_DIAGRAMS]
    seen = set()
    for i, d in enumerate(diagrams, 1):
        if not isinstance(d, dict):
            continue
        pat = d.get("pattern") if isinstance(d.get("pattern"), str) else "diagram"
        slug = d.get("slug")
        if not isinstance(slug, str) or not _SLUG_RE.match(slug) or slug in seen:
            new = "%02d-%s" % (i, slugify(pat) or "diagram")
            if isinstance(slug, str) and slug:
                warnings.append('slug "%s" rewritten to "%s"' % (slug[:40], new))
            d["slug"] = new
            slug = new
        seen.add(slug)
        for k in ("title", "move"):
            if not isinstance(d.get(k), str):
                d[k] = ""
    plan["diagrams"] = diagrams
    return plan, warnings


def _salvage(plan):
    """keep the diagrams that are individually valid; the rest become warnings
    (SPEC 11, 'valid json, wrong shape')."""
    kept, warnings = [], []
    seen_pat = set()
    for i, d in enumerate(plan.get("diagrams") or [], 1):
        p, _ = validate_plan({"diagrams": [d, d]})   # per-item checks only
        bad = [x for x in p if x.startswith("diagram 1")]
        pat = d.get("pattern") if isinstance(d, dict) else None
        if bad or pat in seen_pat:
            warnings.append("diagram %d dropped: %s" % (i, bad[0] if bad
                                                        else "duplicate pattern " + str(pat)))
            continue
        seen_pat.add(pat)
        kept.append(d)
        if len(kept) >= config.MAX_DIAGRAMS:
            break
    return kept, warnings


# ---------------------------------------------------------------------------
# 7.6 lint — deterministic, free, runs before any compile
# ---------------------------------------------------------------------------
_RESERVED_TAIL = {
    "near", "shape", "label", "icon", "width", "height", "direction", "link",
    "tooltip", "constraint", "class", "top", "left", "grid-rows", "grid-columns",
    "grid-gap", "vertical-gap", "horizontal-gap", "source-arrowhead",
    "target-arrowhead", "style", "layers", "scenarios", "steps",
}
_ICON_RE = re.compile(r'(^|[\s{;.])icon\s*:', re.I)
_FONTSIZE_RE = re.compile(r'(font-size\s*:\s*)(-?\d+)')
_MD_LABEL_RE = re.compile(r'(:\s*)\|[A-Za-z0-9_+-]*[ \t]*(.*?)[ \t]*\|', re.S)
_NEAR_RE = re.compile(r'(^|[\s.{;])near\s*:')
_DIRECTION_RE = re.compile(r'^\s*direction\s*:')


def _strip_quoted(line):
    return _QUOTED_RE.sub('""', line)


def _brace_depth(src):
    depth, in_q, esc = 0, False, False
    for ch in src:
        if in_q:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_q = False
            continue
        if ch == '"':
            in_q = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return depth


def _strip_vars_d2config(src):
    """remove a `vars: { ... d2-config ... }` map. cli flags beat it anyway, so
    stripping is cheaper than arguing."""
    changed = False
    while True:
        m = re.search(r'^[ \t]*vars\s*:\s*\{', src, re.M)
        if not m:
            return src, changed
        i = m.end() - 1
        depth, j, in_q, esc = 0, i, False, False
        while j < len(src):
            ch = src[j]
            if in_q:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_q = False
            elif ch == '"':
                in_q = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(src):
            return src, changed
        block = src[m.start():j + 1]
        if "d2-config" not in block:
            return src, changed
        end = j + 1
        if end < len(src) and src[end] == "\n":
            end += 1
        src = src[:m.start()] + src[end:]
        changed = True


def lint(src):
    """-> (fixed_src, problems, notes). deterministic, never calls a model.

    autofixes (recorded in notes): font-size clamped to 8..100, icon: lines
    deleted, |md ...| labels quoted, vars.d2-config stripped, one trailing
    unclosed brace closed. reports (problems): a key with an unquoted . or :
    (the two silent misparses), near: inside a sequence diagram, direction: in
    a grid source, unbalanced braces. SPEC 7.6.
    """
    notes, problems = [], []
    src = src or ""

    # --- autofix: vars.d2-config ------------------------------------------
    src, stripped = _strip_vars_d2config(src)
    if stripped:
        notes.append("stripped an injected vars.d2-config map — the cli flags own the render")

    # --- autofix: |md ... | labels ----------------------------------------
    if "|" in src:
        def _md(m):
            inner = m.group(2).strip()
            inner = inner.replace("\\", "\\\\").replace('"', '\\"')
            inner = re.sub(r"\s*\n\s*", "\\\\n", inner)
            return '%s"%s"' % (m.group(1), inner)
        new = _MD_LABEL_RE.sub(_md, src)
        if new != src:
            notes.append("converted a |md …| label to a quoted string")
            src = new

    # --- autofix: icon: lines ---------------------------------------------
    lines = src.split("\n")
    kept = []
    dropped = 0
    for line in lines:
        if _ICON_RE.search(_strip_quoted(line)):
            dropped += 1
            continue
        kept.append(line)
    if dropped:
        notes.append("deleted %d icon: line(s) — icons are d2's only network dependency"
                     % dropped)
        src = "\n".join(kept)

    # --- autofix: font-size clamp -----------------------------------------
    clamped = []

    def _clamp(m):
        n = int(m.group(2))
        c = max(config.FONT_SIZE_MIN, min(config.FONT_SIZE_MAX, n))
        if c != n:
            clamped.append("%d→%d" % (n, c))
        return "%s%d" % (m.group(1), c)
    src = _FONTSIZE_RE.sub(_clamp, src)
    if clamped:
        notes.append("clamped font-size %s into %d..%d"
                     % (", ".join(clamped), config.FONT_SIZE_MIN, config.FONT_SIZE_MAX))

    # --- autofix: one trailing unclosed brace ------------------------------
    depth = _brace_depth(src)
    if depth == 1:
        if not src.endswith("\n"):
            src += "\n"
        src += "}\n"
        notes.append("closed one unclosed { at the end of the source")
        depth = _brace_depth(src)
    if depth != 0:
        problems.append("unbalanced braces: %s%d %s"
                        % ("+" if depth > 0 else "", depth,
                           "unclosed {" if depth > 0 else "extra }"))

    # --- report: pattern guards -------------------------------------------
    is_sequence = re.search(r'shape\s*:\s*sequence_diagram', src) is not None
    is_grid = re.search(r'grid-(rows|columns)\s*:', src) is not None

    for n, line in enumerate(src.split("\n"), 1):
        bare = _strip_quoted(line)
        stripped_line = bare.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if is_sequence and _NEAR_RE.search(bare):
            problems.append('line %d: near: does not work inside a shape: sequence_diagram '
                            'source. drop the line.' % n)
        if is_grid and _DIRECTION_RE.match(bare):
            problems.append('line %d: a direction: line fights grid-rows/grid-columns. '
                            'drop it.' % n)

        # the two silent misparses. edges are exempt: `a -> b.c` is legal.
        if "->" in bare or "<-" in bare or "--" in bare:
            continue
        m = re.match(r'^\s*([^:{}#]+?)\s*:\s*(.*)$', bare)
        if not m:
            continue
        key, value = m.group(1), m.group(2).split("{")[0]
        if key.startswith('"') or key.endswith('"'):
            continue
        if "." in key:
            segs = [x.strip().lower() for x in key.split(".")]
            # `outer.middle.core.style.fill: "#x"` is valid path-based attribute
            # setting, not a container. any reserved segment clears the line.
            if not (any(x in _RESERVED_TAIL for x in segs)
                    or segs[0] in ("style", "vars", "classes")):
                problems.append('line %d: key "%s" contains an unquoted "." — d2 will '
                                'silently make a container. quote it or rename it.'
                                % (n, key.strip()))
        if ":" in value and not re.match(r'^\s*[a-z][a-z0-9+.-]*://', value):
            problems.append('line %d: key "%s" is followed by a second unquoted ":" — d2 '
                            'will silently fold it into the label. quote it or rename it.'
                            % (n, key.strip()))
    return src, problems, notes


# ---------------------------------------------------------------------------
# 7.2 / 7.7 / 7.8 — plan and repair
# ---------------------------------------------------------------------------
def _render_user(title, description, body):
    return (USER_TEMPLATE
            .replace("{title}", title or "")
            .replace("{description}", description or "")
            .replace("{body}", body or ""))


def _merge_meta(base, extra, calls):
    out = dict(base)
    for k in ("backend", "model", "provider", "generation_id"):
        if extra.get(k):
            out[k] = extra[k]
    out["ms"] = int(base.get("ms", 0)) + int(extra.get("ms", 0))
    out["cost_usd"] = float(base.get("cost_usd", 0.0)) + float(extra.get("cost_usd", 0.0))
    out["calls"] = calls
    return out


def plan(text, backend, title=None, model=None):
    """-> (plan_dict, meta). generate -> validate -> at most one re-prompt.
    SPEC 7.2, 7.7, 7.8."""
    if backend in getattr(config, "SLOT_BACKENDS", ()):
        return plan_slots(text, backend, title=title, model=model)

    post_meta, body = clean_post(text)
    if not body.strip():
        raise PlannerError("empty post")
    user = _render_user(title or post_meta["title"], post_meta["description"], body)

    calls = 0
    meta = _blank_meta(backend, model or "")
    warnings = []

    text_out, m1 = _generate(SYSTEM_PROMPT, user, backend, model)
    calls += 1
    meta = _merge_meta(meta, m1, calls)

    obj = _extract_json(text_out)
    if obj is None:
        problems = ["the answer was not json: " + strip_fences(text_out)[:300]]
        warns = []
    else:
        obj, warns = _normalize_plan(obj)
        problems, w2 = validate_plan(obj)
        warns = warns + w2

    if problems and calls < config.MAX_LLM_CALLS_PER_RUN:
        retry_user = (user
                      + "\n\n--- your last answer ---\n" + strip_fences(text_out)[:6000]
                      + "\n--- end ---\n\nyour last answer was not valid. these are the "
                        "problems: " + "; ".join(problems)
                      + ". return the corrected json object, nothing else.")
        text_out2, m2 = _generate(SYSTEM_PROMPT, retry_user, backend, model)
        calls += 1
        meta = _merge_meta(meta, m2, calls)
        obj2 = _extract_json(text_out2)
        if obj2 is not None:
            obj2, w3 = _normalize_plan(obj2)
            p2, w4 = validate_plan(obj2)
            if not p2:
                obj, problems, warns = obj2, [], w3 + w4
            else:
                kept, w5 = _salvage(obj2)
                if len(kept) >= config.MIN_DIAGRAMS:
                    obj = {"diagrams": kept}
                    problems, warns = [], w3 + w5
                else:
                    problems = p2

    if problems:
        # last chance: keep whatever was individually valid from the first answer
        kept, w6 = _salvage(obj) if isinstance(obj, dict) else ([], [])
        if len(kept) >= config.MIN_DIAGRAMS:
            obj = {"diagrams": kept}
            warns = warns + w6
        else:
            raise PlannerError("the planner could not produce a valid plan: "
                               + "; ".join(problems)[:300])

    warnings.extend(warns)
    plan_out = {"diagrams": obj["diagrams"]}
    if warnings:
        plan_out["warnings"] = warnings
    return plan_out, meta


def repair_d2(src, problems, errors, backend, model=None):
    """-> (src, meta). the ONE llm d2 repair. SPEC 7.8."""
    numbered = "\n".join("%4d| %s" % (i, line)
                         for i, line in enumerate((src or "").split("\n"), 1))
    lines = ["the source:", numbered, ""]
    if problems:
        lines.append("problems:")
        lines.extend("- " + str(p) for p in problems)
        lines.append("")
    if errors:
        lines.append("errors:")
        for e in errors:
            if isinstance(e, dict):
                lines.append("%s:%s: %s" % (e.get("line", 0), e.get("col", 0),
                                            e.get("msg", "")))
            else:
                lines.append(str(e))
        lines.append("")
    lines.append("return the corrected d2 source only.")
    user = "\n".join(lines)

    if backend == "mock":
        # the mock backend cannot fix d2. it returns the source untouched so the
        # failure path stays visible instead of being papered over.
        meta = _blank_meta("mock", model or "mock")
        meta.update({"provider": "mock", "calls": 1})
        return src, meta

    out, meta = _generate(D2_REPAIR_PROMPT, user, backend, model)
    fixed = strip_fences(out)
    fixed = re.sub(r"^\s*the source:\s*\n", "", fixed)
    body_lines = [l for l in fixed.split("\n") if l.strip()]
    if body_lines and all(re.match(r"^\s*\d+\s*\|", l) for l in body_lines):
        fixed = "\n".join(re.sub(r"^\s*\d+\s*\|\s?", "", l) for l in fixed.split("\n"))
    if not fixed.strip() or ":" not in fixed:
        return src, meta                     # garbage back: keep what we had
    if not fixed.endswith("\n"):
        fixed += "\n"
    return fixed, meta


# ------------------------------------------------------------ slot-fill mode
# small/free models pick patterns well but cannot author d2. in slot mode they
# only choose a pattern and supply the words; patterns.fill() builds the source,
# so the d2 is valid by construction. SPEC 7.2 variant.

_SLOTS_SYSTEM_TEMPLATE = """you are the diagram planner for "inkpost". {{STYLE}}
you turn one of {{AUTHORS}} posts into 2 to 4 hand-drawn diagrams.

you do NOT write diagram code. you pick a pattern and fill in its labels. the tool
builds the source, so you cannot break it — spend all your effort on the WORDS.

VOICE — this is the whole job, not decoration:
- use {{AUTHORS}} words VERBATIM. lift their phrases straight out of the post. cutting a
  sentence short is fine. rewriting it is not. never summarise them into clean
  english. a label like "internal conflict" or "productivity cycle" is a FAILURE —
  those are your words, not theirs. "the internal committee shuts up" is theirs.
{{LOWERCASE_RULE}}- break a label into short lines with \\n. 2 to 6 words per line, at most 4 lines.
  "plan how to\\ndo the work" — never one long run-on line.
- keep their curly quotes “ ” ’ exactly as they wrote them.
- a label of 1 or 2 generic words is almost always wrong. if the post gives you a
  whole clause, use the whole clause.
- no emoji, no marketing words, no exclamation marks they did not write.

CHOOSING:
- one diagram per DISTINCT move the post makes. never the same pattern twice.
- 2 diagrams for a short post, 3 to 4 for a long one.
- only pick a pattern whose "when" genuinely matches. if just two fit, return two.
- if the post has no structure and only one great sentence, use `poster`.

FILLING:
- return a "labels" object per diagram. copy each key EXACTLY from that pattern's
  label list below. fill EVERY key — a skipped key keeps a placeholder like
  "step one" and ruins the picture.
- also return "quote": the single sentence from the post this diagram is built on,
  verbatim. this is how you prove to yourself you are lifting, not inventing.

the patterns, and the exact label keys each takes:

{CATALOG}

the example below shows only the SHAPE of an answer. it is from a different
post about moving house. NEVER copy any of its words into your answer — every
label you write must come from the post you were given.

{"diagrams":[{"pattern":"collapse","title":"the boxes and the doorway",
 "move":"a room full of things narrows to the one box that matters",
 "quote":"i stood in the hallway at midnight holding a kettle i did not need.",
 "labels":{"the open field":"the whole flat:\\neverything i own",
   "option":"books i never\\nfinished","another option":"the good plates",
   "the meta-option":"a box of cables","the guilt":"my father's chair",
   "the question":"“do i still\\nneed this?”","the rabbit hole":"three broken lamps",
   "me":"me","the hallway":"the van, 8am","the task":"one box",
   "the clock":"the new door",
   "the thing that collapses it":"the van comes at eight.\\nyou stop deciding\\nand start carrying."}}]}

reply with ONE json object and nothing else. no prose, no markdown fences.
start with { and end with }."""

_SLOTS_LOWERCASE_RULE = ("- every label is lowercase. no title case, no capital i, no full stops unless\n"
                         "  the author wrote one.\n")


def build_slots_system_prompt(voice=None):
    """the slot-fill prompt (openrouter backend), rendered for a voice. the
    {CATALOG} placeholder is still open — _slots_system() fills it."""
    return _apply_voice(_SLOTS_SYSTEM_TEMPLATE, voice, _SLOTS_LOWERCASE_RULE)


SLOTS_SYSTEM_PROMPT = build_slots_system_prompt()


def _slots_catalog():
    return patterns.slot_block()


def _slots_system(voice=None):
    prompt = build_slots_system_prompt(voice) if voice else SLOTS_SYSTEM_PROMPT
    return prompt.replace("{CATALOG}", _slots_catalog())



def _same_slot(a, b):
    n = lambda s: str(s or "").replace("\\n", "\n").replace("\n", " ").strip().lower()
    return n(a) == n(b)

def _build_from_slots(obj):
    """turn {pattern, title, move, labels} rows into real diagram rows with d2.
    returns (rows, warnings). invalid rows are dropped, not fatal."""
    rows, warns = [], []
    seen = set()
    for i, d in enumerate(obj.get("diagrams") or []):
        if not isinstance(d, dict):
            continue
        name = str(d.get("pattern") or "").strip().lower()
        if name not in patterns.PATTERNS:
            warns.append("dropped a diagram with unknown pattern %r" % name)
            continue
        if name in seen:
            warns.append("dropped a duplicate %s" % name)
            continue
        seen.add(name)
        labels = d.get("labels")
        if not isinstance(labels, dict):
            labels = {}
        # a half-filled template leaks placeholders like "step one" into the
        # picture. demand most of the slots before we accept the diagram.
        wanted = patterns.slots(name)
        filled = sum(1 for k in wanted
                     if patterns.fill(name, {k: "x"}) != patterns.PATTERNS[name]["d2"]
                     and any(patterns._clean(v) and _same_slot(k, kk)
                             for kk, v in labels.items()))
        if wanted and filled / float(len(wanted)) < config.MIN_SLOT_FILL:
            warns.append("dropped %s — only %d of %d labels filled"
                         % (name, filled, len(wanted)))
            seen.discard(name)
            continue
        src = patterns.fill(name, labels)
        title = str(d.get("title") or name).strip().lower()[:80] or name
        rows.append({"slug": "%02d-%s" % (len(rows) + 1, name),
                     "title": title,
                     "pattern": name,
                     "move": str(d.get("move") or patterns.PATTERNS[name]["move"])[:120],
                     "d2": src})
        if len(rows) >= config.MAX_DIAGRAMS:
            break
    return rows, warns


def plan_slots(text, backend, title=None, model=None):
    """slot-fill planning. the model never writes d2, so the source always
    compiles. -> (plan_dict, meta)"""
    post_meta, body = clean_post(text)
    if not body.strip():
        raise PlannerError("empty post")
    user = _render_user(title or post_meta["title"], post_meta["description"], body)
    system = _slots_system()

    calls = 0
    meta = _blank_meta(backend, model or "")
    text_out, m1 = _generate(system, user, backend, model)
    calls += 1
    meta = _merge_meta(meta, m1, calls)

    obj = _extract_json(text_out)
    rows, warns = ([], []) if obj is None else _build_from_slots(obj)

    if len(rows) < config.MIN_DIAGRAMS and calls < config.MAX_LLM_CALLS_PER_RUN:
        why = ("your answer was not json" if obj is None
               else "you returned %d usable diagrams" % len(rows))
        retry = (user + "\n\n" + why + ". return ONE json object with 2 to 4 "
                 "diagrams, each {pattern, title, move, labels}. the label keys "
                 "must come from the pattern's list. nothing else.")
        text_out2, m2 = _generate(system, retry, backend, model)
        calls += 1
        meta = _merge_meta(meta, m2, calls)
        obj2 = _extract_json(text_out2)
        if obj2 is not None:
            rows2, w2 = _build_from_slots(obj2)
            if len(rows2) > len(rows):
                rows, warns = rows2, w2

    if len(rows) < config.MIN_DIAGRAMS:
        raise PlannerError("the planner could not pick usable patterns for this "
                           "post (got %d)" % len(rows))

    out = {"diagrams": rows}
    if warns:
        out["warnings"] = warns
    return out, meta
