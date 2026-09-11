# sketch studio — build spec

a localhost tool at `http://127.0.0.1:8788`. ohm pastes a post (or picks one off disk), ticks
aesthetic mode chips, hits **sketch it**. an llm reads the post, decides 2–4 visual moves, writes
one d2 diagram per move starting from the house pattern templates. python lints it, compiles it,
repairs it once if it broke, then renders every diagram × every mode and lays the results out in a
gallery where every cell is comparable, editable, re-renderable and downloadable. everything
persists under `runs/<slug>/`.

lives at `/Users/ohm_home/projects/sketch`. **stdlib python only.** no pip, no npm, no build step,
no framework, no CDN. one html file. seven python files.

```
python3 server.py      →  sketch studio → http://127.0.0.1:8788
```

---

## 0. two overrides of the brief, and why

everything in the build brief is taken as given except two points that live measurement on this
machine contradicts. both overrides are load-bearing.

**override 1 — the pre-render gate is a real compile, not `d2 validate`.**
the brief says "d2 validated with `d2 validate` before render". `d2 validate` is **parse-only**.
measured on this machine, d2 v0.9.0:

| source | `d2 validate` | real compile |
|---|---|---|
| `a: hi { style.font-size: 0 }` | rc=0 ✅ | rc=1 ❌ |
| `a: hi { shape: blob }` | rc=0 ✅ | rc=1 ❌ |
| `a: hi { near: nowhere }` | rc=0 ✅ | rc=1 ❌ |
| `a: hi { style.fill: notacolor }` | rc=0 ✅ | rc=1 ❌ |

those four are exactly the class of error an llm produces. `validate` would wave all of them
through and the gallery would show a broken cell with a green check next to it. the gate is
`d2 --layout=<L> [--target …] --stdout-format ascii - -`, stdout discarded. it costs ~37 ms — the
same as `validate` — and is a strict superset. **`d2 validate` appears nowhere in this codebase**,
and there is a test asserting that.

**override 2 — a mode's accent is a colour PAIR, not one hex.**
the brief says each preset carries an "accent hex". one hex is not enough. theme 200 (`midnight`)
paints label ink `#CDD6F4`; near-white text on `#ffe8a3` is unreadable. verified: rendering
`{style.fill: "#ffe8a3"}` under `--theme=200` produces zero occurrences of a dark ink in the svg;
adding `style.font-color: "#111111"` produces one. so every preset carries
`accent: {"fill": …, "font": …}` and the renderer always writes both properties.

everything else — port 8788, the flat file layout, the three backends with auto-select, the free
model chain, named presets, the `{slug,title,pattern,move,d2}` plan shape, one llm repair with the
error text, sha256 render caching, the runs/ layout, the polling ui, `python3 server.py` — is
exactly as briefed.

---

## 1. verified ground truth

every row below was run on this machine on 2026-09-08 against d2 v0.9.0 at `/opt/homebrew/bin/d2`.
nothing here is doc-derived.

| fact | how it was proved |
|---|---|
| `d2 validate` is parse-only; a real compile catches 4 more error classes | the table in §0 |
| png is **native go raster** — no chrome, no network, works offline | renders under `BROWSER=0` and a `(deny network*)` sandbox |
| png is **already 2× the svg viewBox** with no `--scale` at all | `--scale 1` → 510×868 from a 255×434 box |
| `success: successfully compiled …` prints to **stderr with rc=0** | key on returncode only, never on stderr being non-empty |
| parse errors arrive in **descending** line order (4:1, then 3:6, then 2:11) | sort ascending before display |
| stdin→stdout works for every format via `- -` | svg, png, ascii, gif all rc=0 |
| **a multiboard source to stdout is a hard error** — `err: failed to compile -: multiboard output cannot be written to stdout`, rc=1, 0 bytes | ran `patterns/steps.d2` → png on stdout |
| **the ascii preflight fails the same way** on a multiboard source | ran it → same error. *this is the finding that matters most; see §7.2* |
| `--target 'steps.<N>'` fixes both: preflight rc=0, png rc=0 / 139 284 bytes | ran both |
| targeting the **last** board still catches an error planted in board 2 | planted `style.font-size: 0` in board 2, targeted `steps.3` → rc=1 with the right line |
| `--target ''` compiles only the root board and would **miss** that error | rc=0 on the same broken source |
| **gif needs no target** — multiboard to stdout is fine for gif | rc=0, 914 409 bytes, magic `GIF89a` |
| `--no-xml-tag` and `--salt` both exist and work | rc=0; salt AAA vs BBB produced different md5s |
| `d2 fmt -` reads stdin and writes formatted source to stdout | `a   ->b:   x` → `a -> b: x`, rc=0 |
| `style.fill: "#X"; style.font-color: "#Y"` on one line compiles inside a nested block body | rc=0 |
| `style.font-color` genuinely overrides theme-200 ink | `#111111` present with it, absent without it |
| `--tala-seeds` is a **no-op** for variation (1/7/42/99 byte-identical) | do not build a "reshuffle" feature on it |
| 4 parallel renders are byte-identical to serial and 2.4× faster | md5-compared |
| theme 2 does **not** exist; themes 5, 8, 102, 104, 301 do | `d2 themes` |

**two stale docs get fixed as part of this build, one line each.**
`BRIEF.md` line 30 says "png needs Chrome (d2 uses it); cairosvg renders sketch svgs blank" —
rewrite to "png uses d2's native rasterizer: no chrome, works offline, and is already 2× the svg
box, so `--scale 1` is the retina asset." keep the gif clause.
`REFERENCE.md`'s theme list is missing 5, 8, 102, 104 and 301, and implies a theme 2 exists.

---

## 2. the organising principle

**the model writes d2, starting from the house templates.** the plan shape is
`{diagrams:[{slug,title,pattern,move,d2}]}` — `d2` is a full source string. the eleven pattern
sources are embedded **verbatim** in the system prompt as the starting shapes; the model's job is
to keep the skeleton and swap ohm's own sentences into the labels.

that choice buys the thing that matters: ohm can read the `.d2` in the gallery, change a word, and
hit re-render, and what he edits is the same artifact the model produced. it costs the two silent
d2 misparse hazards, which are handled by a **deterministic lint pass that runs before any llm
repair and costs nothing**:

- `a.b: hello` silently becomes a **container** `a` holding a child labelled `hello`. rc=0, no warning.
- `a:b: hello` silently becomes a single node keyed `a` whose **label** is `b: hello`. rc=0, no warning.

d2 will never tell you about either. `planner.lint()` catches them, plus `icon:`, `|md`, out-of-range
font sizes and injected `d2-config` maps. only after lint does the source meet a compiler, and only
after a failed compile does an llm see it again.

the json schema is trivially simple as a result — every field is a string, `pattern` is an enum —
so **one code path** (`response_format: json_object` + the schema pasted into the system prompt +
a local validator) covers every model in the chain. no strict/non-strict tiering, no per-provider
`anyOf` support roulette.

---

## 3. file map

```
/Users/ohm_home/projects/sketch/
├── config.py          paths, ports, timeouts, model chain, .env loader        ~120 lines
├── presets.py         the 7 named aesthetic modes                            ~60 lines
├── patterns.py        the 11 patterns: template d2, layout, flags, gif        ~260 lines
├── planner.py         postprep, prompt, 3 backends, lint, validate, repair    ~480 lines
├── renderer.py        preflight, mode substitution, render, cache, parallel   ~200 lines
├── server.py          http on 127.0.0.1:8788, job state machine, runs/        ~300 lines
├── ui/index.html      the whole front end, one file                           ~420 lines
├── tests.py           unittest, no network, no tokens                         ~340 lines
├── runs/              [gitignored]  <slug>/{post.md,plan.json,run.json,src/,out/<mode>/}
├── .cache/renders/    [gitignored]  content-addressed render cache
├── .env               [gitignored, NOT created by the build]  OPENROUTER_API_KEY=…
├── .env.example       committed.  OPENROUTER_API_KEY=
└── .gitignore         committed, written BEFORE any git init
```

existing files stay untouched: `BRIEF.md` (one line fixed), `REFERENCE.md` (theme list fixed),
`README.md`, `render`, `patterns/*.d2`, `examples/`. the ten `.d2` files in `patterns/` become
**test oracles and prompt source material**; the runtime copies live as strings in `patterns.py` so
the tool has no filesystem dependency at plan time.

`.gitignore` — write it **before** `git init`; sketch is not a repo yet. anchor the paths, because
a bare `out/` would swallow `examples/variations/out/` and `examples/final/`, which are committed
work:

```
.env
/runs/
/.cache/
__pycache__/
.DS_Store
```

also delete the stray `.DS_Store` files in `patterns/` and `examples/`.

### parallel build split

four lanes, disjoint files. **`config.py`, `presets.py` and `patterns.py` are written first,
together, then frozen** — every other lane imports them and nothing else crosses a boundary.

| lane | owns | depends on |
|---|---|---|
| **A · planner** | `planner.py` | `config`, `patterns` (reads the catalog as data) |
| **B · renderer** | `renderer.py` | `config`, `presets`. testable against `patterns/*.d2` from minute one |
| **C · server** | `server.py` | `planner.plan/lint/validate/repair`, `renderer.preflight/render_all` |
| **D · ui** | `ui/index.html` | the http api in §8 only. builds against `backend=mock`. |

`tests.py` is shared: each lane contributes its own numbered cases from §11.

---

## 4. config.py

```python
"""sketch studio config. stdlib only. every knob lives here."""
import os, shutil

ROOT      = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR  = os.path.join(ROOT, "runs")
CACHE_DIR = os.path.join(ROOT, ".cache", "renders")
UI_FILE   = os.path.join(ROOT, "ui", "index.html")
POSTS_DIR = os.path.expanduser("~/projects/chaos-to-order/content/posts")
ENV_FILE  = os.path.join(ROOT, ".env")

HOST, PORT = "127.0.0.1", 8788          # never 0.0.0.0

# ---- d2 -------------------------------------------------------------------
D2_BIN         = os.environ.get("SKETCH_D2") or shutil.which("d2") or "/opt/homebrew/bin/d2"
PAD            = 40
PNG_SCALE      = "1"      # png is ALREADY 2x the svg viewBox. --scale 2 = 4x, 1.2MB, 1.0s.
ANIMATE_MS     = 1200
PREFLIGHT_TIMEOUT = 15
RENDER_TIMEOUT    = 60
RENDER_WORKERS    = 4
VALID_THEMES = {0,1,3,4,5,6,7,8,100,101,102,103,104,105,200,201,300,301,302,303}  # no theme 2

# ---- planner --------------------------------------------------------------
BACKEND       = os.environ.get("SKETCH_BACKEND", "auto")   # auto|openrouter|claude-code|mock
MIN_DIAGRAMS, MAX_DIAGRAMS = 2, 4
MAX_LLM_CALLS_PER_RUN = 4        # 1 plan + 1 plan-repair + up to 2 d2-repairs. hard cap.
PLAN_TIMEOUT  = 180

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_HEADERS = {"HTTP-Referer": "http://localhost:8788",
                      "X-OpenRouter-Title": "sketch"}
# all three support response_format, so there is exactly one request shape.
OPENROUTER_CHAIN = ["google/gemma-4-31b-it:free",
                    "google/gemma-4-26b-a4b-it:free",
                    "nvidia/nemotron-3-super-120b-a12b:free"]
OPENROUTER_MAX_TOKENS = 8000     # response-healing CANNOT repair a max_tokens truncation
OPENROUTER_RPM        = 18       # under the documented 20/min ceiling
OPENROUTER_TIMEOUT    = 120

CLAUDE_BIN   = os.environ.get("SKETCH_CLAUDE") or shutil.which("claude") or "claude"
CLAUDE_MODEL = os.environ.get("SKETCH_CLAUDE_MODEL", "sonnet")
CLAUDE_TIMEOUT = 180

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
```

**backend auto-select**, exactly as briefed, and the resolved answer is always reported to the ui so
a silent mock run is impossible:

1. `openrouter` if `load_env()` returns a key
2. else `claude-code` if `shutil.which(CLAUDE_BIN)`
3. else `mock`, and `/api/health` returns `degraded` with
   `"no OPENROUTER_API_KEY in .env and no claude on PATH — running mock plans"`.
   the ui header turns amber and says **mock**.

`mock` is never auto-selected over a working backend; it is chosen explicitly from the dropdown or
reached only when nothing else exists.

---

## 5. presets.py — the seven modes

a preset is **surface only**: theme, sketch, dark theme, accent pair, and a `layout_default` that
is the fallback for a source whose pattern is unknown (a hand-edited free-form diagram). when the
pattern is one of the eleven, **the pattern's layout wins** — `collapse` needs tala's edgeless
scatter to read as an open field, `loop-exit` needs dagre because cycles read wrong in tala. a
mode may not override that.

```python
MODES = {
 "paper":     {"theme": 1,   "sketch": True,  "dark_theme": None, "layout_default": "tala",
               "accent": {"fill": "#ffe8a3", "font": "#111111"}, "swatch": "#ffffff",
               "note": "the house look. grey ink, one yellow. all 11 finished diagrams are this."},
 "blueprint": {"theme": 0,   "sketch": False, "dark_theme": None, "layout_default": "dagre",
               "accent": {"fill": "#ffe8a3", "font": "#111111"}, "swatch": "#ffffff",
               "note": "clean lines, no wobble. for a flow that should look precise."},
 "newsprint": {"theme": 300, "sketch": True,  "dark_theme": None, "layout_default": "dagre",
               "accent": {"fill": "#ffe8a3", "font": "#111111"}, "swatch": "#000410",
               "note": "terminal theme. black and white. closest to the printed paper."},
 "toast":     {"theme": 105, "sketch": True,  "dark_theme": None, "layout_default": "tala",
               "accent": {"fill": "#ffd166", "font": "#312102"}, "swatch": "#fff8ec",
               "note": "warm and tinted. deeper yellow because the theme already tints nodes."},
 "grape":     {"theme": 7,   "sketch": True,  "dark_theme": None, "layout_default": "tala",
               "accent": {"fill": "#ffe8a3", "font": "#170034"}, "swatch": "#f6f2fb",
               "note": "aubergine. the most designed light mode. good for a poster."},
 "midnight":  {"theme": 200, "sketch": True,  "dark_theme": 200,  "layout_default": "tala",
               "accent": {"fill": "#ffe8a3", "font": "#111111"}, "swatch": "#1e1e2e",
               "note": "dark mauve. the accent font colour is mandatory here or the label vanishes."},
 "origami":   {"theme": 302, "sketch": True,  "dark_theme": None, "layout_default": "tala",
               "accent": {"fill": "#ffe8a3", "font": "#170206"}, "swatch": "#faf7f2",
               "note": "soft paper-fold palette. the gentlest light mode."},
}
MODE_ORDER    = ["paper","blueprint","newsprint","toast","grape","midnight","origami"]
DEFAULT_MODES = ["paper"]
```

`dark_theme` is applied **only to svg** — `--dark-theme` writes a `prefers-color-scheme` block, and
a png bakes exactly one palette. offering it as a png option would be a lie.

**known and accepted:** on the tinted themes (`toast` 105, `grape` 7) d2 tints nodes by nesting
level, so the single yellow stops reading as *the one special box*. `toast` compensates with a
deeper `#ffd166`; `grape` does not. the chip's hover note says so. the accent only reads as
genuinely special on themes 1, 300, 301 and 303.

---

## 6. patterns.py — the eleven

```python
PATTERNS = {
  "<name>": {
     "move":  str,     # the BRIEF row, verbatim. goes into the prompt catalog.
     "when":  str,     # one line telling the model when to reach for it
     "layout": str,    # "tala" | "dagre"  — the flag actually passed to d2
     "accent": bool,   # does this pattern have a yellow node at all
     "gif":    bool,   # does it render an animated gif
     "d2":     str,    # the template source, verbatim
  }
}
```

`committee` renders `shape: sequence_diagram`, which is its own layout engine — the `--layout` flag
is ignored, `near:` does not work inside it, and there is **no node to fill yellow** (the emphasis
beat is `{style.bold: true}` on one message). `comic` is a grid — `grid-rows`/`grid-columns`
override the layout engine and a `direction:` line fights it. both still carry a `layout` value so
the renderer never has to branch.

the eleven templates, verbatim. these strings are what the model sees in the prompt and what the
mock backend returns.

| # | name | move | layout | accent | gif |
|---|---|---|---|---|---|
| 1 | `contrast` | messy thing vs clean thing | tala | yes | no |
| 2 | `collapse` | many options → one path | tala | yes (twice, one concept) | no |
| 3 | `test` | a yes/no that sorts the world | dagre | yes | no |
| 4 | `layers` | outer thing hides inner thing | tala | yes | no |
| 5 | `collage` | many inputs → one self | tala | yes | no |
| 6 | `loop-exit` | a cycle + the one exit | dagre | yes | no |
| 7 | `committee` | a dialogue with yourself | dagre¹ | **no** | no |
| 8 | `comic` | a diary sequence | dagre² | yes | no |
| 9 | `poster` | one line that carries a post | dagre | yes | no |
| 10 | `steps` | reveal one idea at a time | dagre | yes | **yes** |
| 11 | `taxonomy` | kinds of a thing, ranked | tala | yes (twice) | no |

¹ sequence_diagram supplies its own layout; the flag is inert.
² grid supplies its own layout; the flag is inert.

**`taxonomy` is new**, lifted from `examples/src/03-deadline-three-urgencies.d2`. it is the only
home for an essay that *enumerates kinds* of a thing rather than describing a flow; without it such
a post gets force-fitted into `contrast` or falls back to `poster`. it is also the pattern most
likely to overflow — three columns of 4–6 prose lines each is a lot of type — so the prompt caps
each column body at 6 lines.

**the one-yellow rule, stated correctly.** BRIEF says one yellow node per diagram. ohm's own
finished work breaks that literally and is right to: `examples/src/01` paints `me` yellow inside
**both** containers, and `examples/src/03` has two yellow fills. the rule is **one yellow
CONCEPT per diagram, which may appear in two places when it is literally the same concept.** a lint
that counted `#ffe8a3` occurrences and demanded exactly one would reject his best diagrams, so
there is no such lint — the constraint lives in the prompt only.

---

## 7. planner.py

### 7.0 exports — the lane contract

```python
clean_post(text)            -> (meta, body)          # meta = {"title","description"}
slugify(title)              -> str
select_backend(req="auto")  -> (name, reason)        # name in openrouter|claude-code|mock
plan(text, backend, title=None, model=None)
                            -> (plan_dict, meta)     # generate -> validate -> at most 1 re-prompt
validate_plan(plan)         -> (problems, warnings)  # both list[str]; problems == [] means valid
lint(src)                   -> (fixed_src, problems, notes)   # deterministic, never calls an llm
repair_d2(src, problems, errors, backend, model=None)
                            -> (src, meta)           # the ONE llm d2 repair
SYSTEM_PROMPT: str          CATALOG: str             PLAN_SCHEMA: dict
class PlannerError(Exception): ...   # .message is one lowercase line, safe to show ohm
```

`meta` from `plan()` and `repair_d2()` is
`{"backend","model","provider","generation_id","ms","calls","cost_usd"}` — `server.py` copies it
straight into the manifest. **it never contains the api key.**

### 7.1 postprep — `clean_post(text) -> (meta, body)`

`meta` = `{"title": str, "description": str}`, empty strings when absent.

1. if the text starts with `---`, split at the next line that is exactly `---`; parse `key: value`
   with a ~15-line hand scanner (quoted or bare values, `[a, b]` lists). keep `title` and
   `description`. drop the block.
2. drop a leading line matching `^!\[.*\]\(.*\)$` — every post opens with a hero image.
3. remove, **wherever they appear including mid-body**, matched on a normalised copy (stripped,
   whitespace collapsed) but deleted from the original:
   - `Thanks for reading! Subscribe for free to receive new posts and support my work.`
   - `Thanks for reading! This post is public so feel free to share it.`
   `snap-out-of-it.md` has the subscribe line **stranded in the middle of the body**. a
   "strip the tail" implementation is wrong and test 3 asserts this.
4. drop trailing lines matching `^\[Share\]\(<?https?://.*\)$`.
5. collapse 3+ blank lines to 2, strip.
6. **do not touch curly quotes.** `“ ” ’` must survive into labels — they are exactly what avoids
   escape trouble inside d2 strings, and ohm's own sources use them.
7. title: frontmatter → first `# ` heading → first non-empty line, truncated to 60 chars.
8. body over 24 000 chars (none of the 7 samples are; largest is 11 843) → keep the first 18 000 and
   the last 6 000 with `\n\n[…middle trimmed…]\n\n` between.

`slugify(title)`: **delete `'` and `’` first** so the slug matches the blog's own filenames
(`theres`, not `there-s`), then non-alphanumerics → `-`, collapse repeats, strip, truncate 60.
empty → `sketch-<YYYYMMDD-HHMMSS>`.

### 7.2 the system prompt — full text

`{{CATALOG}}` is rendered at import time from `patterns.PATTERNS`, so the prompt can never drift
from the code. everything else below is literal.

```
you are the diagram planner for "sketch", a tool that turns ohm's blog posts into
hand-drawn d2 diagrams. ohm writes lowercase diary prose about building things.

your job: read the post, find the 2 to 4 distinct MOVES it makes, pick one pattern
for each move, and write the d2 source for it by taking that pattern's template and
replacing its placeholder labels with OHM'S OWN SENTENCES.

VOICE RULES — these are the whole job, not decoration:
- every label is lowercase. no title case. no capital i. ever.
- use ohm's words VERBATIM. lift his phrases straight out of the post. cutting a
  sentence short is fine; rewriting it is not. do not summarise him, do not
  paraphrase him into clean english, do not add words he did not write. the
  diagram is a re-typesetting of his sentences, not a description of them.
- break every label into short lines with a literal \n inside the quoted string.
  2 to 6 words per line, under 34 characters per line, at most 4 lines per label.
  "plan how to\ndo the work" — never "plan how to do the work".
- keep his curly quotes “ ” ’ exactly as they appear in the post. they are safe
  inside d2 labels and they need no escaping.
- no emoji. no clip-art. no gradients. no marketing words. no exclamation marks
  he did not write himself.

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
  "title" - a short lowercase name for the diagram, 3-8 words.
  "move"  - ONE lowercase sentence naming the essay move this diagram carries.
            this is what ohm reads to decide whether you understood the post.

OUTPUT — one json object, nothing before it, nothing after it, no code fence:

{"diagrams":[{"slug":"...","title":"...","pattern":"<one of the names below>",
              "move":"...","d2":"<the full d2 source as one string>"}]}

the "d2" value is a json string, so every newline in the source is \n and every
quote inside it is \". 2 to 4 diagrams.

THE PATTERNS
{{CATALOG}}
```

`{{CATALOG}}` renders, for each of the eleven, this block — the `d2` field **verbatim**:

```
──────────────────────────────────────────────────────────────
pattern: contrast
move: messy thing vs clean thing
use when: the post sets a tidy or imagined version against the real, lumpy one.
layout: tala (the tool sets this; do not write a layout line)
template:
# contrast: the clean thing vs the messy thing (human-vs-LM)
direction: right
clean: "the tidy version" {
  in: "input"
  out: "glassy output"
  in -> out
}
messy: "the real version" {
  a: "start"
  b: "detour"
  c: "doubt"
  hub: "type" {shape: circle}
  done: "the thing\n(lumpy on purpose)" {shape: page; style.fill: "#ffe8a3"}
  a -> hub
  hub -> b
  b -> hub: "back again"
  hub -> c
  c -> hub: "leave it anyway"
  hub -> done
}
caption: "no friction = no fingerprints." {shape: text; style.italic: true; style.font-size: 22}
caption.near: bottom-center
notes: `done` is the accent — the thing that actually got made. 2 to 4 detours.
──────────────────────────────────────────────────────────────
pattern: collapse
move: many options → one path
use when: the post names a pile of choices and then the one thing that kills them all.
layout: tala (the tool sets this; do not write a layout line)
template:
# collapse: the open field (no edges → tala scatters) → one hallway
direction: down
field: "the open field" {
  style.stroke-dash: 5
  style.fill: transparent
  o1: "option"
  o2: "another option"
  o3: "the meta-option"
  o4: "the guilt"
  o5: "the question"
  o6: "the rabbit hole"
  me: "me" {shape: circle; style.fill: "#ffe8a3"}
}
hallway: "the hallway" {
  direction: right
  me: "me" {shape: circle; style.fill: "#ffe8a3"}
  task: "the task"
  end: "the clock" {shape: circle}
  me -> task -> end
}
field -> hallway: "the thing that collapses it" {style.bold: true}
notes: NEVER put an arrow inside `field`. the edgeless container is exactly what
makes tala scatter it into an open field. 4 to 8 options. `me` is one concept in
two places, so it is yellow in both. the field -> hallway edge label is the loudest
sentence in the diagram — give it his strongest clause about the collapsing force.
──────────────────────────────────────────────────────────────
pattern: test
move: a yes/no that sorts the world
use when: the post proposes one question that separates people or things.
layout: dagre (the tool sets this; do not write a layout line)
template:
# test: one question that sorts the world
direction: down
thing: "the thing" {shape: page}
q: "the question\nthat sorts it?" {shape: diamond}
no: "one answer."
yes: "the other answer." {style.fill: "#ffe8a3"}
thing -> q
q -> no: "yes"
q -> yes: "no"
notes: the accent goes on the answer the post is actually FOR, which is often the
one reached by "no". keep the question 2 to 4 lines and end it with a ?.
──────────────────────────────────────────────────────────────
pattern: layers
move: outer thing hides inner thing
use when: the post says what looks like the point is not the point.
layout: tala (the tool sets this; do not write a layout line)
template:
# layers: what people see wraps what actually matters
outer: "what people think it is" {
  style.stroke-dash: 5
  style.fill: transparent
  middle: "the visible layer" {
    style.fill: "#f4f4f4"
    core: "the real thing" {
      style.fill: "#ffe8a3"
      style.bold: true
      a: "detail one"
      b: "detail two"
      c: "detail three"
    }
  }
}
note: "takes years. invisible while forming." {shape: text; style.italic: true}
note -> outer.middle.core: {style.stroke-dash: 3}
notes: 3 to 5 details. the `#f4f4f4` on the middle layer is not the accent, leave it.
the note is optional; drop both its lines if the post has no aside.
──────────────────────────────────────────────────────────────
pattern: collage
move: many inputs → one self
use when: the post is about being assembled out of things you did not choose.
layout: tala (the tool sets this; do not write a layout line)
template:
# collage: many inputs → one self → one exit
direction: right
inputs: "things i didn't choose" {
  style.stroke-dash: 5
  style.fill: transparent
  i1: "input"
  i2: "input"
  i3: "input"
  i4: "input"
  i5: "input"
}
self: "“my” thing" {shape: cloud}
inputs.i1 -> self
inputs.i2 -> self
inputs.i3 -> self
inputs.i4 -> self
inputs.i5 -> self
strip: "strip the noise" {shape: hexagon}
free: "the real question?" {shape: circle; style.fill: "#ffe8a3"; style.bold: true}
self -> strip -> free
notes: 5 to 8 inputs, and one `inputs.iN -> self` line per input — add or remove
BOTH together. repeating a word across inputs is fine. `free` ends in a ?.
──────────────────────────────────────────────────────────────
pattern: loop-exit
move: a cycle + the one exit
use when: the post describes a loop he keeps running, and the thing that breaks it.
layout: dagre (the tool sets this; do not write a layout line)
template:
# loop-exit: the cycle, and the one edge that breaks it
direction: down
start: "the condition" {shape: oval}
s1: "step one"
s2: "step two"
s3: "step three"
s4: "feel bad about it"
start -> s1 -> s2 -> s3 -> s4
s4 -> s1: "again" {style.stroke-dash: 3}
exit: "the real consequence" {shape: hexagon; style.fill: "#ffe8a3"}
done: "execution mode."
s4 -> exit
exit -> done
note: "this isn't laziness. it's rational." {shape: text; style.italic: true}
note.near: bottom-center
notes: 3 to 5 steps; the LAST step is the felt cost, the thing that hurts. keep the
back-edge dashed. the note is optional and usually carries the reframe.
──────────────────────────────────────────────────────────────
pattern: committee
move: a dialogue with yourself
use when: the post quotes an internal argument.
layout: none — sequence_diagram is its own engine
template:
# committee: a dialogue with yourself (sequence diagram)
shape: sequence_diagram
me: "me"
voice: "the internal committee"
world: "the clock"
me -> voice: "should i start?"
voice -> me: "are you even ready?"
voice -> me: "which version though?"
me -> me: "reorganise notion instead"
world -> me: "12 hours left." {style.bold: true}
voice -> me: "(silence)"
me -> world: "one sitting. something decent."
notes: this pattern has NO yellow node and NO caption — `near:` does not work inside
a sequence diagram and there is no shape to fill. the emphasis beat is
{style.bold: true} on EXACTLY ONE message: the outside pressure landing. 5 to 10
messages. `me -> me` is self-talk and one beat should be it.
──────────────────────────────────────────────────────────────
pattern: comic
move: a diary sequence
use when: the post walks through a day or an episode in order.
layout: none — grid is its own engine
template:
# comic: a diary sequence as panels
grid-rows: 2
grid-columns: 3
grid-gap: 24
p1: "panel one.\nthe boring start." {width: 320; height: 240}
p2: "panel two.\nthe small mess." {width: 320; height: 240}
p3: "panel three.\nthe stall." {width: 320; height: 240}
p4: "panel four.\nthe avoidance." {width: 320; height: 240; style.fill-pattern: dots}
p5: "panel five.\nthe grind." {width: 320; height: 240}
p6: "panel six.\nthe thing." {width: 320; height: 240; style.fill: "#ffe8a3"; style.bold: true}
notes: NEVER write a `direction:` line here — it fights the grid. exactly 6 panels
(2 x 3); a different count leaves empty cells. keep width/height on every panel.
one middle panel may keep the dots fill as the avoidance beat. the LAST panel is
the accent. 2 to 4 short lines per panel.
──────────────────────────────────────────────────────────────
pattern: poster
move: one line that carries a post
use when: the post has no structure, only one great sentence. this is the fallback.
layout: dagre (the tool sets this; do not write a layout line)
template:
# poster: one line that carries a post, plus a tiny diagram
direction: down
title: "the line.\nthe second half of the line." {shape: text; style.font-size: 44; style.bold: true}
a: "this" {shape: oval}
b: "that" {shape: hexagon; style.fill: "#ffe8a3"}
you: "you" {shape: person}
a -> you: "carries"
b -> you: "compounds"
sig: "— ohm.quest" {shape: text; style.italic: true; style.font-size: 18}
title.near: top-center
sig.near: bottom-right
notes: the title is his verbatim line split over exactly 2 lines. font-size 44 and 18
are inside d2's 8..100 limit — do not raise them. `b` is the accent: the durable
force, the one that compounds. keep the signature as it is.
──────────────────────────────────────────────────────────────
pattern: steps
move: reveal one idea at a time
use when: the post builds an argument that only works in order. renders as a gif.
layout: dagre (the tool sets this; do not write a layout line)
template:
# steps: reveal one idea at a time → ./render steps.d2 gif  (also pdf, pptx)
direction: down
steps: {
  1: { start: "the condition" {shape: oval} }
  2: { s1: "step one"; start -> s1 }
  3: { s2: "step two"; s1 -> s2 }
  4: { s3: "feel bad about it"; s2 -> s3; s3 -> s1: "again" {style.stroke-dash: 3} }
  5: { exit: "the consequence" {shape: hexagon; style.fill: "#ffe8a3"}; done: "execution."; s3 -> exit -> done }
}
notes: board 1 introduces the root alone. each later board adds ONE node plus its
edge and refers to earlier keys by bare name. number the boards 1..N with no gaps —
the tool reads the highest number to render the finished still. 5 or 6 boards. the
LAST board carries the accent.
──────────────────────────────────────────────────────────────
pattern: taxonomy
move: kinds of a thing, ranked
use when: the post enumerates two or three KINDS of something and ranks them.
this is the only pattern for an essay that lists rather than flows.
layout: tala (the tool sets this; do not write a layout line)
template:
# three kinds of urgency (the reluctant taxonomy)
direction: right

imported: "imported urgency\n\nsomeone else sets the deadline.\nclient. boss. exam.\n\nefficient but fragile.\nif the structure disappears,\nso does the productivity."
manufactured: "manufactured urgency\n\nyou create the stakes.\nship in public. tell people.\nyour brain knows it's fake…\n\nbut this is how agency starts."
none: "no urgency at all\n\nbuild because it's interesting.\nwrite because you have\nsomething to say.\nno dopamine hit. no relief.\n\nthe slow, compounding 1%." {style.fill: "#ffe8a3"}

imported -> manufactured: "harder"
manufactured -> none: "hardest"

responsive: "responsive.\nsurvives." {shape: oval}
selfdirected: "self-directed.\nbuilds." {shape: oval; style.fill: "#ffe8a3"}
responsive -> selfdirected: "pressure borrows energy from the future.\ndiscipline builds it from systems."
notes: exactly 3 kinds. each column is a title line, a blank line (\n\n), then 3 to 6
short lines of his prose — no more, it overflows. the THIRD kind is the accent and
so is the second summary oval: one concept, ranked and then named. the two edge
labels are single comparative words.
──────────────────────────────────────────────────────────────
```

### 7.3 user template

```
post title: {title}
post description: {description}

--- POST ---
{body}
--- END POST ---

plan the diagrams. 2 to 4. return the json object and nothing else.
```

### 7.4 the json schema

sent as text inside the system prompt, and enforced locally by `validate_plan`. every field is a
string and `pattern` is a hard enum, so no provider has to support anything exotic.

```json
{"type":"object","additionalProperties":false,"required":["diagrams"],
 "properties":{"diagrams":{"type":"array","minItems":2,"maxItems":4,
   "items":{"type":"object","additionalProperties":false,
     "required":["slug","title","pattern","move","d2"],
     "properties":{
       "slug":{"type":"string","maxLength":60},
       "title":{"type":"string","maxLength":120},
       "pattern":{"type":"string","enum":["contrast","collapse","test","layers","collage",
                  "loop-exit","committee","comic","poster","steps","taxonomy"]},
       "move":{"type":"string","maxLength":200},
       "d2":{"type":"string","minLength":20}}}}}}
```

`pattern` is an enum because the free models are not strong enough to be trusted with an
open-ended choice, and "invents a pattern name" is the worst failure to catch late.

### 7.5 `validate_plan(plan) -> list[str]`

pure, no network, no subprocess. returns human-readable problems; `[]` means valid. the same
function backs the re-prompt and the tests.

- `diagrams` present, `2 <= len <= 4` (more → truncate to 4 with a warning; fewer than 2 → problem)
- each item has all five keys and no others; all five are strings
- `pattern` ∈ the eleven; **no duplicate pattern** in one plan
- `slug` matches `^[a-z0-9][a-z0-9-]{0,59}$` and is unique in the plan; a collision or a bad slug is
  rewritten to `<NN>-<pattern>` rather than rejected
- `d2` is non-empty and contains at least one `:` (i.e. is plausibly d2, not prose)
- soft warnings, returned separately and never blocking: a label line over 34 chars, two diagrams
  whose `move` sentences are identical

### 7.6 `lint(src) -> (fixed_src, problems)` — deterministic, free, runs before any compile

this is the layer that makes llm-written d2 safe. it never calls a model.

**auto-fixed silently, recorded as a note:**
- `style.font-size: N` outside 8..100 → clamped to the nearest bound
- any line containing `icon:` → deleted. icons are d2's only network dependency, and a failed
  fetch writes a **partial output file alongside a nonzero exit**, so a "file exists" success check
  would lie. deleting them keeps the tool provably offline.
- a `|md … |` / `|yaml … |` / `|<lang> … |` label → converted to a quoted `"…"` string
- any `vars: { d2-config: … }` map → stripped. cli flags beat it anyway (verified: an explicit
  `--theme=0` overrides an in-file `theme-id: 300` even though 0 is d2's own default), so stripping
  is cheaper than arguing.
- a trailing unclosed `{` at EOF → one `}` appended

**reported as a problem, not fixed** (the model or ohm must resolve it):
- a key containing an unquoted `.` or `:` — the two silent misparses. reported as
  `line 7: key "a.b" contains an unquoted "." — d2 will silently make a container. quote it or rename it.`
- a `near:` line inside a `shape: sequence_diagram` source
- a `direction:` line in a source containing `grid-rows:`
- unbalanced braces that one append cannot fix

`lint` returns the fixed source **always**; problems are advisory input to the repair prompt.

### 7.7 backends

all three expose `generate(system, user) -> (text, meta)` where
`meta = {"backend","model","ms","provider","generation_id","cost_usd"}`.

**mock** — no network, no subprocess, deterministic. picks 2 or 3 of the eleven pattern templates
by `sha256(body).digest()[0] % …`, returns them **verbatim** as the `d2` values with slugs/titles
derived from the post title and `move` set to the pattern's `move` string. same input → identical
bytes, always. because the templates are real house sources, every mock plan lints clean, compiles
clean and renders — it is a working end-to-end fixture, not a stub. `SKETCH_MOCK_FAIL=compile`
injects `style.font-size: 0` into one diagram so the repair path is exercised by tests rather than
by luck.

**claude-code** — no api key, uses the existing login.

```python
cmd = [CLAUDE_BIN, "-p", user,
       "--system-prompt", SYSTEM_PROMPT,
       "--model", CLAUDE_MODEL,
       "--tools", "",
       "--output-format", "json"]
env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}   # nested-claude fix
r = subprocess.run(cmd, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT, cwd=ROOT, env=env)
```

- **strip `CLAUDECODE` from the env.** this is the proven fix from `~/projects/post-cooker/cook.py`
  for invoking claude from inside a claude session; without it the nested call misbehaves.
- `--tools ""` disables every built-in tool so `-p` cannot wander into Read/Bash. there is **no
  `--max-turns`** in this build; the tool lockout is the containment.
- **never `--bare`** — its help text says anthropic auth becomes strictly
  `ANTHROPIC_API_KEY`/`apiKeyHelper` and OAuth/keychain are never read, which kills the entire point
  of this backend.
- pin `cwd=ROOT`: `claude` discovers `CLAUDE.md` and memory from where it runs.
- envelope: `{"type":"result","subtype":"success","is_error":false,"result":"<text>",
  "duration_ms":…,"total_cost_usd":…}`. `is_error` true or `subtype != "success"` → transient.
- **the `result` is fence-wrapped in practice** even when the prompt forbids it. fence stripping is
  mandatory, not defensive.
- record `total_cost_usd` into the manifest. **this backend is not free.**

**openrouter** — `urllib.request`, non-streaming always, key from `config.load_env()`.

```python
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
           **OPENROUTER_HEADERS}
body = {"model": model,
        "messages": [{"role":"system","content":system},{"role":"user","content":user}],
        "max_tokens": 8000, "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "plugins": [{"id": "response-healing"}]}
```

all three chained models support `response_format`, so there is **one** request shape. walk
`OPENROUTER_CHAIN` in order. per hop:

| outcome | action |
|---|---|
| 200 | take `choices[0].message.content` **or, if that is null/empty, `choices[0].message.reasoning`** — reasoning-default models put the text there. strip a leading `<think>…</think>`. strip fences. log `X-Generation-Id` and `X-Provider-Name` from the response headers into the manifest — the only way to know which upstream actually served a free request. |
| `finish_reason == "length"` | retry the **same** model once at `max_tokens * 2`. **do not hop** — healing explicitly cannot repair a max_tokens truncation and a bigger budget is the fix. |
| 400 any message | retry the same model once with a **minimal body** (`model`, `messages`, `max_tokens` only — drop `response_format` and `plugins`), then hop |
| 401 | **stop the chain.** `"openrouter rejected the key. check .env"` |
| 402 | **stop.** `"openrouter says insufficient credits — a negative balance blocks even free models"` |
| 403 | **stop.** surface `metadata.reasons` and `metadata.flagged_input`. never retry the same input. |
| 408 | retry same model once, then hop |
| 429 | read `Retry-After`; if ≤5s sleep and retry once. if `error.metadata.provider_code == "rate_limited"` it is an upstream provider limit → **hop**. otherwise it is the account daily cap → **stop**: `"openrouter free daily cap hit (50/day under $10 lifetime spend, 1000 after). switch the backend to claude-code."` hopping models never resets an account-wide cap. |
| 502 / 503 | hop immediately (503 usually means no provider matched the parameters sent) |
| chain exhausted | `PlannerError("every free model failed: " + last_error)` |

parse the error envelope defensively: `{"error":{"code":int,"message":str,"metadata":{…}}}` — there
is **no** top-level `type` field and often no `metadata` key at all.

a module-level **token bucket**, 18 requests per rolling 60 s on a `time.monotonic()` deque, shared
by plan and repair calls. it sleeps rather than erroring, keeping us under the 20 rpm ceiling.

**the key is never logged, never returned by a route, never written into a manifest.** the
`Authorization` header is redacted in any debug dump.

### 7.8 the repair loops

three tiers, each with a hard cap, and **a failure never takes down more than the diagram it
belongs to.** `MAX_LLM_CALLS_PER_RUN = 4` is the ceiling across all of them, because the openrouter
free tier is 50 calls a day and the repair budget is the scarcest thing in this tool.

| tier | trigger | fix | on second failure |
|---|---|---|---|
| **plan** | json unparseable, or `validate_plan` returns problems | one re-prompt: same messages + `your last answer was not valid. these are the problems: <list>. return the corrected json object, nothing else.` | `PlannerError` → the run fails; there is nothing to render |
| **source, generated** | `lint` problems, or preflight rc≠0 | `lint` auto-fixes first (free, deterministic) → re-preflight → then **one** llm repair with the numbered source, the lint problems and the `line:col: msg` errors → re-preflight | diagram `status: "failed"` with its errors. the `.d2` is still written so ohm can fix it by hand. **the other diagrams render normally.** |
| **source, hand-edited** | preflight rc≠0 on a source posted from the gallery | **none.** the compiler's `line:col: msg` goes straight back to the editor. | same. a hand edit gets the raw message, never a silent rewrite. |

the d2-repair system prompt:

```
you fix d2 v0.9.0 source. return ONLY the corrected d2, no code fence, no prose,
no explanation. change as little as possible. never change any label TEXT — only
the syntax around it. keep the "#ffe8a3" fill exactly where it is.
```

user: the source with 1-indexed line numbers prefixed, then `problems:` (lint), then `errors:` with
one `line:col: msg` per line.

`repairs` is counted per diagram (0, 1) and shown in the gallery meta line, so a pattern that always
needs repair becomes visible rather than invisible.

---

## 8. renderer.py

### 8.0 exports — the lane contract

```python
D2_VERSION: str                                  # one `d2 --version` at import
layout_for(pattern, mode)   -> str               # "tala" | "dagre"
target_for(src)             -> str | None        # "steps.<N>" for a multiboard source
apply_mode(src, mode)       -> str
parse_errors(stderr)        -> list[dict]        # [{"line":int,"col":int,"msg":str}] ASCENDING
preflight(src, layout)      -> list[dict]        # [] means ok. applies target_for internally.
render(src, pattern, mode, fmt) -> bytes         # raises RenderError(errors=list[dict])
render_all(jobs)            -> list[dict]        # results in INPUT ORDER
cache_clear()               -> int               # bytes freed

job    = {"id": str, "src": str, "pattern": str, "mode": str, "fmt": "png"|"svg"|"gif"}
result = {**job, "ok": bool, "bytes": bytes|None, "ms": int, "cached": bool, "errors": list[dict]}
```

`render()` and `render_all()` take the **canonical** source and call `apply_mode` themselves, so no
caller ever holds seven recoloured copies of a diagram.

everything is stdin → stdout. **the renderer never touches disk for input**; `server.py` writes the
bytes it returns.

```python
def _run(args, src, timeout):
    p = subprocess.run([config.D2_BIN, *args, "-", "-"],
                       input=src.encode("utf-8"), capture_output=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")
```

**check `returncode` only.** `success: successfully compiled … in 46ms` is printed to **stderr on a
successful run**; any "stderr is non-empty means failure" logic reports every good render as broken.

### 8.1 layout resolution

```python
def layout_for(pattern, mode):
    p = patterns.PATTERNS.get(pattern)
    return p["layout"] if p else presets.MODES[mode]["layout_default"]
```

the pattern wins when it is known. `mode.layout_default` is the fallback for a hand-edited
free-form source whose pattern the tool no longer recognises. `committee` and `comic` supply their
own engine and the flag is inert; they still carry `"dagre"` so no caller has to branch.

### 8.2 the multiboard target rule — the one thing to get right

**measured, and none of the obvious approaches survive it.** a source containing `steps:` is a
multiboard source, and:

```
$ d2 --layout=dagre --stdout-format png - -  < patterns/steps.d2
err: failed to compile -: multiboard output cannot be written to stdout      rc=1, 0 bytes

$ d2 --layout=dagre --stdout-format ascii - - < patterns/steps.d2
err: failed to compile -: multiboard output cannot be written to stdout      rc=1
```

**the preflight fails too.** without the target rule, every `steps` diagram would be reported broken
before it was ever rendered. so:

```python
STEP_BOARD = re.compile(r"^\s*(\d+)\s*:\s*\{", re.M)

def target_for(src):
    """None, or 'steps.<N>' where N is the highest board number in the steps block."""
    if "steps:" not in src:
        return None
    ns = [int(m.group(1)) for m in STEP_BOARD.finditer(src)]
    return "steps.%d" % max(ns) if ns else None
```

- `--target 'steps.<max>'` is added to **preflight, png and svg**. verified: rc=0 on a good source,
  and an error planted in board 2 is still caught when targeting board 3 (boards are cumulative).
- **`--target ''` is wrong.** it compiles only the root board, returns rc=0 on that same broken
  source, and would render a near-empty image that looks like success.
- **gif takes no target** — multiboard to stdout is fine for gif (verified, rc=0, `GIF89a`).
- because the model writes the d2, N must be **parsed from the source**, never assumed. a `steps`
  source the model wrote with 6 boards and one with 5 both work.
- if the regex finds `steps:` but no board numbers, treat the source as single-board (no target) and
  let the compiler speak.

### 8.3 mode substitution

one canonical `.d2` per diagram, recoloured at render time by a single regex. this is why editing
one source updates all seven modes, and why the templates in the prompt stay verbatim.

```python
ACCENT_RE = re.compile(r'style\.fill:\s*"#ffe8a3"', re.I)

def apply_mode(src, mode):
    a = presets.MODES[mode]["accent"]
    return ACCENT_RE.sub('style.fill: "%s"; style.font-color: "%s"' % (a["fill"], a["font"]), src)
```

- `replace all`, deliberately — `collapse` and `taxonomy` legitimately carry the same concept twice.
- verified: `style.fill: "#X"; style.font-color: "#Y"` on one line compiles both inline in a brace
  body and as a standalone line inside a nested block.
- `paper` is **not** the identity (it adds the font-color), and that is correct: the explicit ink is
  a no-op on theme 1 and mandatory on theme 200, so emitting it uniformly means one code path.
- `style.fill: "#f4f4f4"` (the `layers` middle band) is untouched, because the regex pins the hex.
- **the known cost:** a hand edit that changes the accent hex away from `#ffe8a3` silently opts that
  diagram out of mode switching — it will render, just always in paper's yellow. the source editor
  shows an inline hint (`accent found: 2`) so a drop to 0 is visible.

### 8.4 the exact command lines

base flags, always passed explicitly on every call — flags beat any in-file `vars.d2-config` even
when the flag equals d2's own default, so the tool owns the render and no model-emitted config
block can hijack it:

```
--layout=<L> --sketch=<true|false> --theme=<N> --pad 40
```

**preflight** (~37 ms, stdout discarded, `PREFLIGHT_TIMEOUT` 15 s):
```
d2 --layout=<L> [--target steps.<N>] --stdout-format ascii - -
```

**png** — `--scale 1`. png is already 2× the svg viewBox, so `--scale 1` *is* the retina asset
(1556×2472 / 506 KB / 0.39 s on the biggest real example); `--scale 2` gives 4× / 1.2 MB / 1.02 s.
the existing `./render` script's `--scale 2` is over-scaled; do not copy it.
```
d2 --layout=<L> --sketch=<S> --theme=<T> --pad 40 --scale 1 [--target steps.<N>] --stdout-format png - -
```

**svg**:
```
d2 --layout=<L> --sketch=<S> --theme=<T> [--dark-theme=<D>] --pad 40 --no-xml-tag --salt <SALT> [--target steps.<N>] --stdout-format svg - -
```
`--no-xml-tag` for direct html embedding. `--dark-theme` only when the mode sets one. **`SALT` is
`sha256(canonical_src)[:8]`, never a run id** — salt changes the output bytes (verified: AAA and BBB
gave different md5s), so a run-scoped salt would make every cache hit return differently-salted
bytes than the ones its key was computed from.

**gif** — only when the source contains `steps:`. a `.gif` target on a single-board file renders a
silent 1-frame gif rather than erroring, so gate on the source, never on the exit code. never pass
`--animate-interval` with a png target — it aborts with `bad usage:` whose last stderr line is the
useless `Run with --help to see usage.`
```
d2 --layout=dagre --sketch=<S> --theme=<T> --pad 40 --animate-interval 1200 --stdout-format gif - -
```

### 8.5 error parsing

d2 emits four shapes and one regex covers all of them: validate's first line (with the
`github.com/d2lang/d2/d2cli.validateCmd:` prefix), validate's subsequent bare lines,
`failed to compile <file>:`, and `failed to compile -: -:`.

```python
def parse_errors(stderr):
    out = []
    for line in stderr.splitlines():
        if not line.startswith("err:"):
            continue
        ms = list(re.finditer(r"(\d+):(\d+):\s*(.*)$", line))
        if ms:
            m = ms[-1]                       # take the LAST match on the line
            out.append({"line": int(m.group(1)), "col": int(m.group(2)), "msg": m.group(3)})
        else:
            out.append({"line": 0, "col": 0, "msg": line[4:].strip()})
    out.sort(key=lambda e: (e["line"] == 0, e["line"], e["col"]))     # ASCENDING
    return out
```

**sort ascending.** d2 emits multiple parse errors in *descending* line order (4:1, then 3:6, then
2:11), so the first `err:` line is not the first error in the file. line and col are both 1-indexed
and map straight onto the source that went in on stdin, which is what makes the gutter highlight in
the source editor honest. keep the raw stderr alongside — the `bad usage:` and missing-file cases
carry no line:col.

### 8.6 cache

```python
key  = sha256(("\x00".join([canonical_src, mode, fmt, layout, D2_VERSION])).encode()).hexdigest()
path = .cache/renders/<key[:2]>/<key>.<ext>
```

`D2_VERSION` comes from one `d2 --version` at boot, so a d2 upgrade invalidates everything. hit →
hardlink (fall back to copy) into the run's `out/<mode>/`, mark the cell `cached: true, ms: 0`.
miss → render, write to a temp file in the same directory, `os.replace` into place, then link.
png/svg/gif output is deterministic for a fixed source + flags + version (verified: 4 parallel
renders byte-identical to serial), so re-running the same post is nearly free — which is what makes
"change one word, re-render all seven modes" feel instant. `POST /api/cache/clear` and a `no_cache`
flag on the run request exist for debugging.

### 8.7 concurrency

module-level `ThreadPoolExecutor(max_workers=4)`. verified safe and worthwhile: 4 parallel png
renders were byte-identical to serial and 2.4× faster (2.41 s → 1.02 s); 4 parallel gifs finished in
1.71 s wall. there is no chrome to contend over in v0.9.0.
`render_all(jobs) -> list[dict]` returns results in input order; one job raising never cancels the
others. `subprocess.TimeoutExpired` at 60 s becomes a **cell** error, never a run error.

---

## 9. server.py — the http api

`http.server.ThreadingHTTPServer` (the stdlib class; post-cooker hand-rolls a subclass and does not
need to) bound to `127.0.0.1:8788` explicitly, never `0.0.0.0`. one `_send(code, obj_or_bytes,
ctype)` helper. `log_message` overridden to a `[sketch] ` stderr prefix. every handler wrapped in
try/except → `500 {"ok": false, "error": str(e)}`, traceback to stderr only. no CORS headers —
same-origin by design.

**boot checks, before binding the port:** `d2` present at `D2_BIN` (else exit 1 with
`d2 not found at <path>. brew install d2, or set SKETCH_D2.`), `d2 --version` cached, `runs/` and
`.cache/renders/` created, and a sweep that rewrites any manifest still in `planning`/`rendering` to
`error: "interrupted — the server restarted"` so the ui never shows a permanently spinning run.

### routes

| method | route | body / query | → |
|---|---|---|---|
| GET | `/` `/index.html` | — | `ui/index.html`, `text/html; charset=utf-8` |
| GET | `/api/health` | — | see below |
| GET | `/api/posts` | — | `{"ok":true,"posts":[{"file","slug","title","bytes","date"}]}` newest first. missing `POSTS_DIR` → `{"ok":true,"posts":[]}`, never a 500. |
| GET | `/api/post` | `?file=<basename>` | `{"ok":true,"title","description","raw","clean"}`. `file` must match `^[A-Za-z0-9._-]+\.md$` — anything with `/` or `..` → 400. |
| GET | `/api/modes` | — | `{"ok":true,"modes":[…§5…],"order":[…],"patterns":{…},"backends":["openrouter","claude-code","mock"],"default_backend":"openrouter","chain":[…OPENROUTER_CHAIN…],"claude_model":"sonnet"}` — the ui renders chips, the backend select **and the model select** from this, never from hardcoded html |
| POST | `/api/run` | `{"text"?,"post_file"?,"title"?,"modes":[…],"backend":"auto","model"?,"formats":["png","svg"],"no_cache":false}` | **202** `{"ok":true,"slug":"…"}` in milliseconds |
| GET | `/api/status` | `?slug=<slug>` | the full run manifest. **this is the poll endpoint.** |
| GET | `/api/runs` | `?limit=20` | `{"ok":true,"runs":[{"slug","title","created","state","n_diagrams","modes","thumb"}]}` newest first |
| GET | `/api/source` | `?slug=&id=` | `{"ok":true,"d2":"…","sha":"…","edited":false,"accents":2}` |
| PUT | `/api/source` | `{"slug","id","d2"}` | 200 `{"ok":true,"preflight":{"ok":bool,"errors":[…]},"rerendering":bool}`. the source is **written either way**; `preflight.ok` reports the compile separately. saving broken d2 is allowed — the text stays in the box and the errors show under it. **never calls the llm.** |
| POST | `/api/revert` | `{"slug","id"}` | rewrites the source from `plan.json` (which is never mutated), re-preflights, re-renders that row |
| POST | `/api/rerender` | `{"slug","id"?,"modes"?,"formats"?}` | 202, the named cells reset to `pending`. `formats` is what the per-row **gif** button uses: `{"slug","id","formats":["gif"]}`. |
| GET | `/runs/<slug>/<relpath>` | — | the asset. see the guard below. |
| POST | `/api/open` | `{"slug"}` | `subprocess.run(["open", "-R", <first png or the out dir>])`, same guard. failure is `200 {"ok":false}`, never fatal — the terminal cannot show ohm an image, so this button matters. |
| POST | `/api/cache/clear` | — | `{"ok":true,"freed_bytes":…}` |
| * | anything else | — | `404 {"ok":false,"error":"not found"}` |

`/api/health`:
```json
{"ok": true, "state": "ready",
 "d2": "v0.9.0",
 "backend": "openrouter",
 "backend_reason": "OPENROUTER_API_KEY found in .env",
 "backends": {"openrouter": "ready", "claude-code": "ready", "mock": "ready"},
 "warnings": []}
```
`state` is `"degraded"` and `backend` is `"mock"` when neither a key nor `claude` exists. the ui
turns the whole header line amber in that case — **ohm can never be shown a mock run that looks
real.**

### the static guard

`GET /runs/<slug>/<relpath>`: `os.path.realpath(os.path.join(RUNS_DIR, slug, relpath))` must start
with `os.path.realpath(RUNS_DIR) + os.sep`, else **403**. that one check covers `..`, absolute
paths and symlink escapes. reject any path containing a null byte. `slug` is separately validated
against `^[a-z0-9][a-z0-9-]{0,79}$`. extension map:
`.png image/png · .svg image/svg+xml · .gif image/gif · .d2 text/plain; charset=utf-8 ·
.json application/json · .md text/plain; charset=utf-8`. **anything unmapped is 403, not
`octet-stream`.** `?dl=1` adds `Content-Disposition: attachment; filename="<basename>"`.

### the job

`POST /api/run` returns immediately; a worker thread does the work and the ui polls
`/api/status`. **no streaming, no websockets, no SSE** — polling every 1000 ms is boring and cannot
half-fail, which is the point.

```
queued → planning → assembling → rendering → done
   ↘ error   (at any step; whatever completed stays on disk)
```

- `planning` — postprep, one llm call, plan validation, at most one re-prompt
- `assembling` — per diagram: `lint` → preflight → at most one llm d2-repair → preflight. write
  `src/<id>.d2`. a diagram that still fails is marked `failed` and the job carries on.
- `rendering` — fan `diagrams × modes × formats` into the render pool. **a cell error never fails
  the run.** each cell updates its own manifest row, so the gallery fills in progressively.

### runs on disk

```
runs/<slug>/
├── post.md              the raw text exactly as received
├── post.clean.txt       what the planner actually saw
├── plan.json            the raw validated plan. NEVER mutated after write.
├── run.json             the manifest served by /api/status
├── src/01-collapse.d2   editable truth. overwritten by PUT /api/source.
└── out/
    ├── paper/01-collapse.png   01-collapse.svg
    ├── midnight/01-collapse.png  01-collapse.svg
    └── paper/04-steps.gif
```

- diagram id: `<NN>-<pattern>`, 1-based, zero-padded, unique by construction.
- **re-run collision:** planning the same slug again creates `<slug>-2`, `<slug>-3`, … it never
  overwrites. runs are a few MB; losing yesterday's gallery to a mis-click is not acceptable. the
  ui says which slug it got.
- **the progress log.** every state transition, every repair, every finished cell appends one
  `{"t": iso, "msg": str}` to `run.json["log"]`, capped at the last 200 entries. this is the
  "progress log" the ui shows: a scrolling monospace list under the status line, newest last, so
  ohm can watch a slow plan and see exactly which model answered and which diagram needed fixing.
  it is the only progress channel — there is no second one.
- `run.json` is rewritten on **every** state transition including each cell going
  `pending → rendering → done`: serialise → write `run.json.tmp` in the same directory → `fsync` →
  `os.replace`, under a per-slug `threading.Lock`. a `kill -9` mid-run leaves a valid earlier state,
  never a truncated file. a disk-full write fails at the `.tmp` stage and the previous manifest
  survives intact.
- every `path` in the manifest is **relative to `RUNS_DIR`** (`<slug>/out/paper/01-collapse.png`),
  because `/runs/…` joins onto `RUNS_DIR` — the ui just prefixes `/runs/`.
- nothing is ever deleted.

### run.json

```json
{"slug": "why-i-only-work-when-theres-a-deadline",
 "title": "why i only work when there's a deadline",
 "created": "2026-09-08T21:47:03",
 "state": "done",
 "error": null,
 "modes": ["paper", "midnight"],
 "formats": ["png", "svg"],
 "log": [{"t":"2026-09-08T21:47:03","msg":"planning · openrouter · google/gemma-4-31b-it:free"},
          {"t":"2026-09-08T21:47:17","msg":"plan back in 14.3s · 3 diagrams"},
          {"t":"2026-09-08T21:47:18","msg":"02-loop-exit repaired (font-size clamped)"},
          {"t":"2026-09-08T21:47:19","msg":"paper/01-collapse.png done in 388ms"}],
 "planner": {"backend": "openrouter", "model": "google/gemma-4-31b-it:free",
             "provider": "Google AI Studio", "generation_id": "gen-abc123",
             "ms": 14320, "calls": 2, "cost_usd": null},
 "diagrams": [
   {"id": "01-collapse", "slug": "field-vs-hallway", "pattern": "collapse",
    "title": "the field collapses into a hallway",
    "move": "no deadline is an open field of options; a due date collapses it into a hallway",
    "layout": "tala", "gif": false,
    "src_path": "why-i-only-work.../src/01-collapse.d2",
    "src_sha": "9f2c1ab4", "edited": false, "repairs": 1,
    "status": "ok", "errors": [], "lint_notes": ["clamped style.font-size 0 -> 8 on line 12"],
    "cells": [
      {"mode":"paper","fmt":"png","state":"done","cached":false,"ms":388,"bytes":506123,
       "path":"why-i-only-work.../out/paper/01-collapse.png","errors":[]},
      {"mode":"paper","fmt":"svg","state":"done","cached":true,"ms":0,"bytes":22140,
       "path":"why-i-only-work.../out/paper/01-collapse.svg","errors":[]}]}],
 "warnings": ["diagram 3 dropped: pattern \"timeline\" is not in the catalog"]}
```

`state` ∈ `queued|planning|assembling|rendering|done|error`.
diagram `status` ∈ `ok|failed`. cell `state` ∈ `pending|rendering|done|error`.

---

## 10. ui/index.html

one file. no framework, no build, no CDN — **a CDN would break the offline guarantee**, and this
tool renders without a network. post-cooker's house style: `ui-monospace, "SF Mono", Menlo`
throughout, 14 px / 1.6, black on white, 2 px rules, `box-shadow: 3px 3px 0 #111` on input focus, a
solid black button that goes grey + `cursor: wait` when disabled, and a complete
`@media (prefers-color-scheme: dark)` block that inverts everything. the column widens from
post-cooker's 720 px to **1100 px** because diagrams are wide. **anything the user or the model
typed goes in with `textContent`, never `innerHTML`.**

### layout, top to bottom

**header** (sticky, 2 px bottom rule) — `sketch studio` at 15 px/700 on the left; on the right a
live grey 11 px line from `/api/health`: `d2 v0.9.0 · openrouter (gemma-4-31b)`. when the backend
resolved to `mock` the whole line turns amber and reads `mock plans — no api key, no claude`. a
`reveal in finder` button appears once a run exists.

**left rail** (240 px, sticky, its own scroll) —
- **posts**, from `/api/posts`: filename, title, byte count. click loads it into the box. a
  `paste instead` link clears and focuses the textarea.
- **recent runs**, from `/api/runs`: title, date, `3 diagrams`, a 40 px png thumb. click reloads
  that gallery from `/api/status` **with zero llm cost**. this list is the reason the tool gets
  reused tomorrow.

**compose** (main column) —
- a title input, auto-filled and editable
- a 14-row monospace textarea, `white-space: pre-wrap`, accepting a dropped `.md` file. under it,
  a collapsed `<details>` showing the *cleaned* body so the boilerplate stripping is auditable.
- **mode chips** in `MODE_ORDER`, built from `/api/modes`. each chip is a 12 px rounded square split
  diagonally into `swatch` and `accent.fill`, then the name. selected = black fill, white text,
  3 px offset shadow; unselected = 2 px outline. hover shows the mode's `note`. `paper` on by
  default; the selection persists in `localStorage["sketch.modes"]`.
- a format row: `png` (locked on), `svg`, `gif — steps patterns only` (greyed with a tooltip when
  the plan has no `steps` diagram)
- a **backend** `<select>`: `auto` / `openrouter` / `claude-code` / `mock`, showing what `auto`
  resolved to, and next to it a **model** `<select>` populated from `/api/modes` → `chain` (plus a
  first `auto — walk the chain` option). picking one pins that single model and skips the fallback
  hops; for `claude-code` it overrides `CLAUDE_MODEL`. research is explicit that a pinned model is
  the only way to compare two runs honestly, so this control is not optional. both remembered in
  localStorage.
- **the progress log**: a 6-line scrolling monospace box, grey 11 px, fed from `run.json["log"]` on
  every poll. it is empty when idle and is the only place slow work explains itself.
- the button: **`sketch it → 3 diagrams × 2 modes`**, the count a guess (3) until a plan exists and
  exact after. an 11 px grey hint under it: `planning takes 15–90s. rendering is parallel and
  cached — re-running the same post is instant.`

**the gallery — rows are diagrams, columns are modes.** this is the whole comparison affordance.
a sticky column-header strip names the modes. each row:
- **row header** (left, 200 px, sticky): a pattern badge (`collapse`, small caps, 2 px outline),
  the diagram title in bold lowercase, then the planner's `move` sentence in grey italic — *this is
  what ohm reads to judge whether the model understood the post.*
- **cells**: one per selected mode, equal width, the png at `max-width:100%; height:auto` on a 1 px
  hairline. under each, `png · svg` (`· gif`) as `<a download href="/runs/…?dl=1">` links and the
  render time in 10 px grey (`cached` when it was a cache hit).
- **row footer**: `source ▸` · `copy .d2` · `revert` · `re-render row` · **`gif`** — the gif button
  is present **only on a `steps` row** (`diagram.gif == true`) and posts
  `/api/rerender {"slug","id","formats":["gif"]}`. on every other row it is absent, not disabled:
  a gif of a single-board source renders a silent 1-frame file, so the affordance must not exist.

**the lightbox** — click a cell → full-viewport overlay, image contained, dark scrim, corner label
`01-collapse · midnight · 1556×2472`. `←`/`→` cycle **the modes of that same diagram**, flipping in
place, because flipping in place is what makes a mode difference visible while side-by-side is for
the overview. `↑`/`↓` walk diagrams holding the mode. `esc` or a scrim click closes.

**the source editor** — `source ▸` unfolds a full-width monospace textarea under the row, pre-filled
from the manifest, with line numbers in a gutter and an `accent found: 2` hint.
- `⌘↵` → `PUT /api/source`, then re-render every mode in that row. cells drop to skeleton and refill
  in about a second.
- `esc` collapses without saving.
- a compile error highlights the offending gutter line and prints `line 12 · col 7 · msg` under the
  box, sorted ascending, each clickable to put the cursor there. **the text stays; nothing is lost.**
- `revert` → `POST /api/revert`. `plan.json` is never mutated, so revert always has somewhere to go.

### states

| state | what the screen does |
|---|---|
| **idle** | compose live, gallery shows the last run if there is one, button reads `sketch it` |
| **planning** | button disabled and grey. a `.planning` block replaces the gallery: a blinking `reading the post… choosing the moves…` (post-cooker's `@keyframes blink`, `step-start`), the backend and model name, and a live `0:12` elapsed counter. **no fake progress bar.** |
| **assembling** | the line becomes `checking the d2…`; a repair appends `· repaired 1` in amber |
| **rendering** | the **full gallery frame appears the instant the plan lands** — every row header real, every cell a grey shimmering skeleton. cells swap to `<img>` as their poll reports `done`. a header line reads `rendered 4 of 6`. |
| **done** | `collapse, loop-exit, poster · 3 diagrams × 2 modes · planned 14.3s · rendered 2.1s (5 cached) · repaired 1` in grey, and the run path `runs/<slug>/` as selectable text |
| **error (run)** | a red-ruled block with the one-line reason; for a quota error, a one-line suggestion `switch the backend to claude-code — it needs no key and no quota` with a button that does exactly that. the form re-enables with everything still filled in. any diagram that did render stays visible. |
| **error (cell)** | that tile goes red with `⚠ line 12 · col 7` and the message, plus `open source` which unfolds that row's editor scrolled to line 12, and a `retry` button. **one bad cell never blocks the others.** |
| **stale** | a run that was `rendering` when the server restarted shows `interrupted — the server restarted` with a `re-run` button that reuses `plan.json` and **skips the llm entirely** |

**reopening a run:** the columns shown are the modes already on disk ∪ the currently-ticked chips.
a column rendered yesterday paints instantly from disk; a newly-ticked chip appears as skeletons and
fills in. `run.json.modes` records what the run was originally built for, so the chips restore to
yesterday's selection with one click.

javascript is ~250 lines of vanilla `fetch`. a tiny `pool(tasks, 4)` promise pool is not needed —
the server owns the render fan-out and the browser only polls. all state lives in one `RUN` object
and the gallery re-renders from it.

---

## 11. error handling — the whole table

| where | condition | behaviour |
|---|---|---|
| boot | `d2` missing at `D2_BIN` | print the fix, exit 1, before binding the port |
| boot | port 8788 busy | `SO_REUSEADDR`, then `already running? → http://127.0.0.1:8788` |
| boot | a manifest left in `planning`/`rendering` | rewritten to `error: interrupted — the server restarted` |
| `/api/post` | filename with `/` or `..` | 400 `bad filename` |
| `/api/run` | empty text | 400 `empty post` |
| `/api/run` | backend openrouter, no key | 400 `no OPENROUTER_API_KEY in .env — add it, or switch the backend to claude-code` |
| planning | 401 / 402 / 403 | run → `error` with the mapped message from §7.7. **no retry, no hop.** 403 also surfaces `metadata.reasons` and `flagged_input`. |
| planning | daily-cap 429 | run → `error`, `openrouter free daily cap hit (50/day under $10 lifetime spend). switch to claude-code.` **no model hop** — the cap is account-wide. |
| planning | provider 429 / 502 / 503 | hop to the next model silently; surface only when the chain is exhausted |
| planning | `finish_reason == "length"` | retry the **same** model at 2× `max_tokens`, once. not a hop. |
| planning | `content` null, text in `reasoning` | read both fields, strip `<think>` blocks, then parse |
| planning | unparseable json | fence-strip → outermost-brace extract → one re-ask → run `error` with the first 300 chars |
| planning | valid json, wrong shape | one re-prompt with the exact `validate_plan` problems; then keep the valid diagrams, list the rest in `warnings` |
| planning | `claude` not on PATH | backend unavailable; auto-select falls through to mock |
| planning | `claude -p` timeout (180 s) | run → `error` with the elapsed time. **not retried — a second run costs real money.** |
| planning | `claude -p` `is_error: true` | one retry, then run `error` |
| assembling | pattern not in the catalog | drop that diagram, add a `warnings` entry, carry on |
| assembling | lint problems or preflight rc≠0 | autofix → one llm repair → still failing → diagram `failed`, source still written and editable, **other diagrams unaffected** |
| assembling | zero diagrams survive | run → `error` with the collected messages |
| rendering | d2 rc≠0 | that **cell** errors with the parsed `line:col:msg`; the run continues |
| rendering | timeout (60 s) | cell error `{"line":0,"col":0,"msg":"d2 timed out after 60s"}` |
| rendering | multiboard without a target | **cannot happen** — `target_for()` derives it from the source. if it ever does, the cell shows `multiboard output cannot be written to stdout` verbatim. |
| rendering | gif on a non-steps source | the cell is **skipped**, not errored: `gif needs a steps pattern` |
| `PUT /api/source` | hand-edited d2 fails to compile | 200 with `preflight.ok:false` and the errors. the file is written, the previous good renders stay on disk, **no llm is called.** |
| `/runs/…` | realpath escapes `RUNS_DIR`, or an unmapped extension | 403 |
| `/api/open` | `open` fails | 200 `{"ok":false}`, a toast, nothing breaks |
| anywhere | uncaught | 500 `{"ok":false,"error":str(e)}`, traceback to stderr only |

**standing rules, baked in.** bound to `127.0.0.1` only, never `0.0.0.0`. the api key comes only
from `.env`, is never logged, never echoed to the browser, never written into a manifest. nothing
is written outside `runs/` and `.cache/`. **nothing is ever emailed. no artifact is ever
published.** no network is needed at render time — `icon:` is stripped by lint, and every other d2
feature was verified working under a `(deny network*)` sandbox.

---

## 12. tests.py — the exact test plan

`python3 tests.py` (or `python3 -m unittest tests -v`). stdlib `unittest`. **no network, no api key,
no tokens, no `claude` invocation** — every llm path uses `backend="mock"` or a monkeypatched
`urlopen`. d2 is a **real subprocess**; that is the point. every test writes only into a
`tempfile.TemporaryDirectory` with `config.RUNS_DIR` and `config.CACHE_DIR` monkeypatched. d2 cases
are `skipUnless(os.path.exists(config.D2_BIN))`.

**postprep**
1. `test_clean_post_all_seven` — over the real 7 files in
   `~/projects/chaos-to-order/content/posts/` (skip if absent): frontmatter gone, the leading
   `![](…)` hero gone, no `[Share](…)` tail, curly `“ ” ’` still present, title non-empty,
   `len(clean) < len(raw)` for all 7.
2. `test_slugify_apostrophes` — `"why i only work when there's a deadline"` →
   `why-i-only-work-when-theres-a-deadline`, matching the blog's own filename. not `there-s`.
3. `test_substack_line_stripped_mid_body` — the `snap-out-of-it` post has a subscribe line
   **stranded in the middle**; assert zero occurrences of `Thanks for reading!` in the output.
   a "strip the tail" implementation fails here and must.

**patterns and lint**
4. `test_all_eleven_templates_compile` — every `PATTERNS[n]["d2"]` preflights rc=0 at its own
   layout, with `target_for()` applied. **eleven green compiles is the single most important test
   in the suite** — it proves the prompt hands the model a working starting shape.
5. `test_all_eleven_render_in_all_seven_modes` — `apply_mode` + png render, 11 × 7 = 77 real
   renders, every one rc=0 and starting `\x89PNG`. this is the only thing that catches a typo in a
   `presets.MODES` theme id, since preflight never sees a theme.
6. `test_existing_sources_still_valid` — the 34 committed `.d2` files in `patterns/`,
   `examples/src/` and `examples/variations/src/` all preflight rc=0, so a d2 upgrade that breaks
   the house style is caught here rather than in the gallery.
7. `test_lint_catches_misparse_keys` — `a.b: hello` and `a:b: hello` are both **reported**, and a
   companion assertion proves d2 accepts both **silently at rc=0**, so the guard is load-bearing
   rather than decorative.
8. `test_lint_autofixes` — `style.font-size: 0` → 8 and `: 200` → 100; an `icon: https://…` line is
   deleted; a `|md … |` label becomes a quoted string; an injected `vars: {d2-config: …}` is
   stripped; the result compiles in every case.
9. `test_lint_pattern_guards` — a `near:` line inside a `shape: sequence_diagram` source is
   reported; a `direction:` line in a `grid-rows:` source is reported.

**modes and accent**
10. `test_apply_mode_pairs` — `paper` produces `style.fill: "#ffe8a3"; style.font-color: "#111111"`;
    `toast` produces `#ffd166`/`#312102`; `#f4f4f4` (the `layers` middle band) is **untouched** in
    every mode.
11. `test_midnight_accent_is_legible` — render the `test` pattern in `midnight` to **svg** and
    assert `#111111` appears; render it **without** the font-color and assert it does not. this is
    the exact bug the accent pair exists to prevent.
12. `test_collapse_keeps_two_accents` — `apply_mode` on `collapse` and `taxonomy` replaces **both**
    occurrences. a one-shot replace would half-recolour ohm's own best diagrams.

**the target rule**
13. `test_multiboard_needs_target` — the `steps` template to png on stdout **without** a target
    returns rc=1 with `multiboard output cannot be written to stdout` and zero bytes; **with**
    `--target steps.<N>` returns rc=0 and `\x89PNG`. this test proves the mandatory rule rather
    than assuming it.
14. `test_preflight_also_needs_target` — the same source through the **ascii preflight** without a
    target returns rc≠0; with the target, rc=0. *the case none of the designs caught.*
15. `test_target_for_parses_board_count` — a hand-written 6-board steps source yields `steps.6`; a
    5-board one yields `steps.5`; a source with no `steps:` yields `None`; a `steps:` block with no
    numbered boards yields `None`.
16. `test_target_last_board_catches_earlier_error` — plant `style.font-size: 0` in board 2, target
    the last board, assert rc≠0 with the right line. then assert `--target ''` returns rc=0 on the
    same source, which is why `''` is never used.
17. `test_gif_needs_no_target` — the `steps` template to gif on stdout, no target, rc=0, magic
    `GIF89a`. and no png argv anywhere contains `--animate-interval` (regression guard for the
    `bad usage` abort).

**renderer**
18. `test_preflight_catches_what_validate_misses` — `style.font-size: 0`, `shape: blob`,
    `near: nowhere`, `style.fill: notacolor`: `d2 validate` rc=0 on all four, `preflight` rc≠0 on
    all four. **the test that justifies the §0 override.**
19. `test_no_validate_in_modules` — grep `config.py`, `presets.py`, `patterns.py`, `planner.py`,
    `renderer.py` and `server.py` for `"validate"` appearing inside a d2 argv list; assert zero.
    **`tests.py` is excluded** — test 18 invokes `d2 validate` on purpose to prove the contrast.
    a regression guard against anyone swapping it back into the pipeline.
20. `test_success_stderr_is_not_failure` — a good render has non-empty stderr containing
    `success: successfully compiled` and rc=0, and is reported `ok`.
21. `test_parse_errors_all_shapes` — the four literal stderr strings (validate first line with the
    `d2cli.validateCmd:` prefix, validate subsequent bare line, `failed to compile <file>:`,
    `failed to compile -: -:`) each yield `{line,col,msg}`; the multi-error descending case
    `4:1 / 3:6 / 2:11` comes back **ascending**; `err: bad usage: …` yields `line 0` with the
    message intact.
22. `test_render_all_parallel_identical` — 8 jobs return in input order, all `ok`, and each png is
    **byte-identical** to the same job rendered serially.
23. `test_timeout_becomes_cell_error` — a stubbed `subprocess.run` raising `TimeoutExpired` yields a
    cell error, never a run error.
24. `test_salt_is_source_scoped` — two svg renders of the same source+mode are byte-identical (so a
    cache hit is honest); two different sources produce different element-id prefixes.
25. `test_svg_has_no_xml_decl` — svg output starts with `<svg`, confirming `--no-xml-tag` is applied.

**cache**
26. `test_cache_hit_skips_subprocess` — a call counter on `subprocess.run` asserts **0** calls on
    the second render of the same (src, mode, fmt, layout); the bytes on disk are real and identical.
27. `test_cache_key_dimensions` — a changed source, a changed mode, a changed format, a changed
    layout and a changed `D2_VERSION` each produce a miss.

**planner**
28. `test_validate_plan` — rejects: 1 diagram, 5 diagrams, an unknown pattern name, a duplicate
    pattern, a missing `move`, a non-string `d2`, a `d2` that is prose. accepts the mock plan.
29. `test_mock_is_deterministic` — the same body twice yields byte-identical json across 100 runs;
    every mock plan validates, lints clean, preflights rc=0 and renders.
30. `test_mock_fail_exercises_repair` — `SKETCH_MOCK_FAIL=compile` produces a plan that fails
    preflight, and the assembling stage marks exactly that diagram `failed` while the others stay
    `ok`.
31. `test_openrouter_branches` — a monkeypatched `urllib.request.urlopen` returning fixture bodies:
    200; `finish_reason: "length"` → **same model** at 2× `max_tokens`, no hop; `content: null` with
    the text in `reasoning` → parses; a 400 → same model retried with the minimal body (no
    `response_format`, no `plugins`) then hops; 429 with `provider_code == "rate_limited"` → hops;
    429 **without** it → **stops** and does not touch model 2; 401 → stops; 402 → stops with the
    negative-balance message; 502 → hops.
32. `test_openrouter_never_logs_key` — capture stderr across a full faked planning call and assert
    the key string appears nowhere; assert it is absent from `run.json`.
33. `test_claude_envelope_parsing` — the envelope with a **fence-wrapped** `result` parses (this is
    the shape actually observed, despite a prompt forbidding fences); `is_error: true` and an empty
    `result` are transient; a `FileNotFoundError` on the binary marks the backend unavailable; the
    built argv contains `--tools ""` and **not** `--bare`, and the env passed to `subprocess.run`
    has **no `CLAUDECODE` key**.
34. `test_prompt_catalog_matches_patterns` — the rendered `{{CATALOG}}` enumerates exactly
    `patterns.PATTERNS.keys()` and embeds each `d2` template **byte-identically**. the drift guard
    between the prompt and the code.
35. `test_env_parser` — a temp `.env` with a comment, a blank line, a quoted value and an `=` inside
    the value parses correctly, and returns `None` for a missing key and a missing file.

**server** — `http.client` against a `ThreadingHTTPServer` on port 0, `backend=mock`
36. `test_health_and_modes` — `/api/health` returns a d2 version and a resolved backend;
    `/api/modes` returns all 7 modes and all 11 patterns.
37. `test_run_returns_202_fast` — `POST /api/run` responds in under 100 ms.
38. `test_full_loop` — poll `/api/status` through `queued → planning → assembling → rendering →
    done` on the real craft post (`2026-03-12-the-ones-who-respect-the-craft-are-the-ones-wholl-make-it.md`) with
    `modes=["paper","midnight"]`, `formats=["png","svg"]`.
    assert `runs/<slug>/` holds `post.md`, `post.clean.txt`, `plan.json`, `run.json`, one `.d2` per
    diagram, and `n × 2 × 2` files under `out/<mode>/`; every advertised `path` exists on disk and
    is non-empty; the manifest is valid json at **every intermediate poll**.
39. `test_source_edit_roundtrip` — `PUT /api/source` with a deliberate `style.font-size: 0` returns
    `preflight.ok == false` with line and col; the file **is** written; the previous good png is
    still on disk; `POST /api/revert` restores it, preflights clean, and `plan.json`'s mtime is
    unchanged.
40. `test_slug_dedupe` — running the same post twice yields `<slug>` and `<slug>-2`; the first
    directory is untouched.
41. `test_file_route_security` — `/runs/../../../etc/passwd`, `/runs/<slug>/../../config.py`, a
    url-encoded `%2e%2e%2f` variant and an absolute path all **403**;
    `/runs/<slug>/run.json.bak` (unmapped extension) → 403; a real png → 200 `image/png`; `?dl=1`
    adds `Content-Disposition`. `/api/post?file=../../../../etc/passwd` → 400.
42. `test_progress_log` — after a mock run, `run.json["log"]` is a non-empty list of
    `{"t","msg"}`, is capped at 200 entries, contains at least one planning line, one per-cell
    line, and **never contains the api key**.
43. `test_interrupted_sweep` — a manifest hand-written in state `rendering` is rewritten to
    `error: interrupted` at boot.

**manual acceptance — not automated, and required before anything is shown to ohm**
44. run against the **craft** post, `2026-03-12-the-ones-who-respect-the-craft-are-the-ones-wholl-make-it.md`
    — never the deadline post, see below — in `paper` + `midnight`, on a real backend. then
    `open runs/<slug>/out/paper/` and **look at every png**: labels legible, nothing clipped, the
    yellow reading as the one special box, the accent readable in `midnight`. the terminal cannot
    display images, and a diagram nobody looked at is not a finished diagram.
45. then run the same post through `claude-code` and compare the two plans side by side in the
    gallery. that comparison is the honest answer to "is the free model good enough for this", and
    the answer may be that claude-code is the real default.

**why not the deadline post:** `examples/src/01` and `examples/src/03` (the `collapse` and
`taxonomy` templates) are both drawn from it. any evaluation on that post measures **recitation,
not capability**. use the craft post for every quality judgement.

---

## 13. build order

1. **together, first, then frozen (~45 min, one agent):** `config.py`, `presets.py`, `patterns.py`,
   and the plan/manifest json shapes in §7.4 and §9. nothing else starts until these exist — every
   lane imports them and nothing else crosses a boundary.
2. **also in this first pass:** write `.gitignore` **before** `git init` with anchored paths
   (`/runs/`, `/.cache/`, never a bare `out/`), write `.env.example` with the key name only, **do
   not create `.env`** (ohm supplies the key), delete the stray `.DS_Store` files, fix `BRIEF.md`
   line 30 and `REFERENCE.md`'s theme list.
3. **then fully parallel:** A `planner.py` · B `renderer.py` · C `server.py` · D `ui/index.html`.
   B unblocks fastest — tests 4–27 are self-contained and testable against the committed
   `patterns/*.d2` from minute one. D builds entirely against `backend=mock` and needs nothing from
   A at all.
4. **integration is `python3 tests.py` green.** tests 4 (eleven compiles), 5 (77 mode renders),
   14 (the preflight target rule) and 38 (end-to-end on mock) are the four that actually prove the
   seams line up.
5. one live `claude-code` plan on the craft post. **look at every png.**
6. one live `openrouter` plan on the same post. compare them in the gallery.

---

## 14. known risks, stated plainly

- **no successful openrouter completion has ever been live-tested** — `.env` does not exist yet.
  the `/api/v1/models` catalog and the 401 envelope are curl-verified; everything about a 200
  response is doc-derived. the first real call may contradict the client.
- **the free tier is 50 requests/DAY** unless $10 of credit has ever been purchased (a lifetime
  threshold, not a balance), which raises it to 1000. an afternoon of iterating on the 7 posts
  exhausts 50. `MAX_LLM_CALLS_PER_RUN = 4` exists because of this; the real fix is the $10 purchase,
  and it is the single highest-leverage thing to do before building.
- **the daily cap is assumed account-wide.** the docs never say. if it is per-model, the chain is
  more useful than this spec claims; either way hopping is never treated as a cure for it.
- **`reasoning: {"enabled": false}` is not sent** — it is unverified whether an unsupported
  `reasoning` parameter hard-errors the way `response_format` provably does. all three chained
  models are `response_format`-capable non-reasoning-default models, and the `content or reasoning`
  read plus the `<think>` strip covers the rest. the generic 400 → minimal-body retry is the guard.
- **`nvidia/nemotron-3-super-120b-a12b:free` is the flakiest hop** (endpoint status −2, 93.95 %
  30-min uptime, 92.43 % 1-day) while every other candidate reports status 0. it is third in the
  chain, never first, and that placement is deliberate.
- **the free roster churns** — 19 of 429 models are $0 today and the docs warn endpoint support
  changes over time. `OPENROUTER_CHAIN` is a hand-maintained hint; when every hop fails the tool
  must say `every free model failed` clearly rather than crash.
- **`claude -p` loads roughly 22k tokens of default context per invocation** regardless of
  `--system-prompt`, so this backend costs real money per run. pinning `cwd` changes but does not
  eliminate the injected memory.
- **diagram quality is the real unknown.** the best free model scores AA intelligence 26.1 against
  52.8 for the paid flagship in the same catalog. this spec makes broken d2 nearly impossible; it
  guarantees nothing about whether the model picks the right pattern for an essay or lifts genuinely
  verbatim lines instead of paraphrasing. steps 5 and 6 of §13 are the honest test.
- **the tinted modes weaken the accent.** on `toast` (105) and `grape` (7) d2 tints nodes by nesting
  level, so the single yellow stops reading as the one special box. `toast` compensates with
  `#ffd166`; `grape` does not. accepted, documented in the chip note, caught by no test.
- **`taxonomy` is the pattern most likely to overflow** — three columns of 4–6 prose lines is a lot
  of type, and it has exactly one finished-work precedent. the prompt caps the body at 6 lines;
  looking at the png is the only real check.
- **hand-edited d2 can reintroduce the silent misparses.** lint runs on save and reports them, but
  `a.b: x` compiles clean, so a source ohm edits by hand can render something subtly wrong with a
  green check. there is no defence beyond looking at the image.
- **the interrupted-manifest sweep assumes one server process.** two instances over the same
  `runs/` would each mark the other's live runs interrupted. the fixed port makes this unlikely.
