# contributing

## running it locally

You need `d2` on your PATH and Python 3.9 or newer. That is all — the core is
standard library only.

```
git clone <repo> inkpost && cd inkpost

./sketch --list                          # posts, modes, backend readiness
./sketch posts/2026-01-15-the-tuesday-problem.md -b mock --no-open
python3 server.py                        # http://127.0.0.1:8788
```

The modules sit flat at the repo root and import each other by bare name, so
nothing needs installing to hack on it. `./sketch` prefers a `.venv/bin/python`
if there is one and falls back to the system `python3`.

An editable install gives you the real command names:

```
pip install -e ".[pretty]"
inkpost --list
inkpost-serve
```

`[pretty]` pulls in clypi, which the CLI uses for boxes and spinners. Without
it the CLI drops to plain ANSI and behaves identically, so do not let a clypi
change break the fallback path.

Use `-b mock` while you work. It is instant, needs no key and no network, and
exercises the whole pipeline apart from the model call.

## module layout

| file | owns |
|---|---|
| `config.py` | every knob. paths, timeouts, the model chain, the posts directory, the voice. Written first, then frozen — every other module imports this and nothing else crosses a lane boundary. |
| `presets.py` | the seven aesthetic modes. Surface only: theme, sketch, dark theme, accent pair, layout fallback. |
| `patterns.py` | the eleven pattern templates as data, plus `slots()` and `fill()`. |
| `planner.py` | everything to do with the model. Cleaning a post, building the prompt, calling a backend, validating and repairing a plan, linting d2. |
| `renderer.py` | every `d2` subprocess call, and only those. Preflight, render, cache, accent substitution, error parsing. |
| `server.py` | the local HTTP server, the JSON API, the run manifest, the per-slug lock. |
| `cli.py` | the terminal interface. Calls planner and renderer directly; never talks to the server. |
| `inkpost/` | a thin console-script wrapper. Finds the flat modules, puts them on `sys.path`, and relocates `runs/` and the cache to `~/.inkpost` when it is running from an installed wheel. |
| `ui/index.html` | the whole web UI, one file. |
| `patterns/*.d2` | the template files. Test oracles for the strings in `patterns.py`. |
| `examples/` | the finished diagrams, their sources, and the layout comparison galleries. |

The lane rule is worth keeping: only `renderer.py` shells out to `d2`, and only
`planner.py` talks to a model. If you find yourself wanting a subprocess call in
`server.py`, you are in the wrong file.

`SPEC.md` is the original build specification and stays authoritative on the
hard-won details — which flags matter, why the preflight is a real compile,
which d2 behaviours are traps.

## adding a pattern

A pattern is two things: a `.d2` file and an entry in `PATTERNS`.

**1. Write the template.** Put it at `patterns/<name>.d2`. Every label you want
the model to be able to replace has to be a double-quoted string. Keep the
placeholder text short and generic — it is what a half-filled diagram falls back
to. Do not write a `layout:` line; the tool passes `--layout` explicitly and an
in-file directive will be ignored or will fight it.

Check it compiles for real before going further:

```
d2 --layout=tala --stdout-format ascii patterns/<name>.d2 -
```

**2. Add the entry.** In `patterns.py`, add a key to `PATTERNS` with eight
fields:

| field | type | meaning |
|---|---|---|
| `move` | str | the essay move it draws, in a few words. Goes into the prompt catalog verbatim. |
| `when` | str | one line telling the model when to reach for it. |
| `layout` | str | `"tala"` or `"dagre"` — the flag actually passed to d2. |
| `accent` | bool | does this pattern have a yellow node at all. |
| `gif` | bool | does it render an animated gif. Only `steps` is true. |
| `notes` | str | the per-pattern guidance line in the prompt catalog. Node counts, what must not change, which node is the accent. |
| `layout_note` | str | the catalog's display line for the layout, e.g. `"tala (the tool sets this; do not write a layout line)"`. |
| `d2` | str | the template source, byte-identical to the file. |

The `d2` string must match `patterns/<name>.d2` byte for byte. The runtime reads
the string, not the file, so the tool has no filesystem dependency at plan time
— but the file stays as the oracle. Check it:

```
python3 -c "
import patterns
n='<name>'
assert open('patterns/%s.d2'%n).read() == patterns.PATTERNS[n]['d2'], 'drift'
print('ok')
"
```

**You do not write a slot list.** `patterns.slots(name)` derives the slots from
the template by scanning its quoted strings, in source order, deduped. A quoted
string is treated as a style value and skipped when the text immediately before
it is a style or attribute assignment (`style.fill:`, `shape:`, `near:`,
`direction:` and friends), and anything starting with `#` is skipped as a colour.
Everything else is a real label, including one-word ones like `"option"` or
`"me"`.

Two consequences worth knowing before you write a template:

- Repeating a label makes it **one** slot. `collage` has five input nodes all
  labelled `"input"`, so a slot fill sets all five to the same text. Give nodes
  distinct placeholder text if you want them individually fillable.
- Style values must look like style values. If you write a bare quoted string in
  a position the regex does not recognise, it becomes a slot and the model can
  overwrite it.

Verify:

```
python3 -c "import patterns; print(patterns.slots('<name>'))"
python3 -c "import patterns; print(patterns.fill('<name>', {'the thing': 'a test'}))"
```

**3. Nothing else.** `PATTERN_ORDER` is derived from `PATTERNS`, and the prompt
catalog is rendered from the same data, so both pick the new pattern up
automatically. That is deliberate: the catalog can never drift from the code.

**4. Render a preview.** `patterns/preview/<name>.png` keeps the gallery
complete.

```
d2 --layout=tala --sketch --theme=1 --pad 40 --scale 2 \
   patterns/<name>.d2 patterns/preview/<name>.png
```

**5. Document it.** Add a section to `docs/PATTERNS.md` and a row to the pattern
table in `README.md`.

### a pattern with its own layout engine

`committee` uses `shape: sequence_diagram` and `comic` uses a grid. Both bring
their own engine and the `--layout` flag is inert for them. They still carry a
`layout` value so the renderer never has to branch. If you add one like this,
say so in `layout_note` and follow the same shape.

### a multi-board pattern

`steps` is the only one. A multi-board source needs `--target steps.<N>` for a
still image, where `N` is the highest board number, and no target at all for a
GIF. `renderer.target_for()` parses `N` out of the source; do not hardcode it.
`--target ''` is wrong — it compiles the root board only and returns 0 on a
source that is broken in board 2.

## adding an aesthetic mode

One dict in `presets.py`, plus the name in `MODE_ORDER`:

```python
"<name>": {
    "theme": 105,                # must be in config.VALID_THEMES. there is no theme 2.
    "sketch": True,              # --sketch=true|false
    "dark_theme": None,          # an int applies --dark-theme, SVG only
    "layout_default": "tala",    # fallback ONLY, for a source with no known pattern
    "accent": {"fill": "#ffd166", "font": "#312102"},
    "swatch": "#fff8ec",         # the web UI thumbnail background. not passed to d2.
    "note": "one line. shows up in --list and the mode picker.",
},
```

Four rules:

- **`accent` is a pair.** The renderer substitutes both `style.fill` and
  `style.font-color`. Pick the font colour against the theme's own label ink, not
  against white. Theme 200 paints labels `#CDD6F4`; a yellow fill with default
  ink is unreadable there.
- **`layout_default` is a fallback, not a setting.** When the pattern is known,
  the pattern's layout wins and your mode cannot override it. See
  `renderer.layout_for()`.
- **`dark_theme` is SVG only.** A PNG bakes exactly one palette, so the flag is
  never passed for PNG.
- **`theme` must be in `config.VALID_THEMES`.** d2 has no theme 2.

Then add a row to the table in `README.md` and a section in `docs/MODES.md`.

Check it across every pattern at once:

```
./sketch posts/2026-02-02-two-kinds-of-tired.md -b mock -m <name> --no-open
```

## testing

CI (`.github/workflows/ci.yml`) runs one smoke test on every push: Python 3.9
and 3.12 on Linux, install d2 from the official script, confirm TALA is in
`d2 layout`, `pip install -e .`, then a full mock run end to end with no API key
and a check that a PNG came out. That is the floor. There is no unit test runner,
so everything else is a check you run by hand.

**The mock backend is the main one.** It plans with keyword heuristics, takes no
key and no network, and returns instantly, so it exercises cleaning, planning,
slot filling, preflight, rendering and file writing end to end.

```
./sketch posts/2026-01-15-the-tuesday-problem.md -b mock -m all -f png,svg,gif --no-open
```

Run it with `-m all` before you ship a renderer or presets change. Every mode
× every planned pattern in one go, and any mode that produces an unreadable
accent shows up immediately.

**`d2 validate` is a quick syntax check, not the gate.**

```
d2 validate patterns/<name>.d2
```

It is fine for catching a typo while you edit a template, but it is parse-only.
It waves through `font-size: 0`, `shape: blob`, `near: nowhere` and
`fill: notacolor`. The tool's own gate is a real compile and you should use that
when you actually want to know:

```
d2 --layout=tala --stdout-format ascii patterns/<name>.d2 -
python3 -c "
import patterns, renderer
print(renderer.preflight(patterns.PATTERNS['<name>']['d2'], 'tala'))
"
```

An empty list means it compiled. Check the return code only — d2 prints
`success: successfully compiled ...` to **stderr** on a successful run, so
grepping stderr for trouble will mislead you.

**Other things worth running by hand:**

```
# every template still compiles, under its own layout
python3 -c "
import patterns, renderer
for n in patterns.PATTERN_ORDER:
    e = patterns.PATTERNS[n]
    print(n, renderer.preflight(e['d2'], e['layout']) or 'ok')
"

# the strings have not drifted from the files
python3 -c "
import os, patterns
for n in patterns.PATTERN_ORDER:
    p = os.path.join('patterns', n + '.d2')
    if os.path.exists(p):
        print(n, 'ok' if open(p).read() == patterns.PATTERNS[n]['d2'] else 'DRIFT')
"

# config resolves without a config file, without env vars, anywhere
python3 -c "import config; print(config.POSTS_DIR); print(config.VOICE)"
```

`config.user_config()` and `config.voice()` must never raise — a missing,
unreadable or malformed `~/.config/inkpost/config.json` has to come back as an
empty dict. If you touch either, check that case.

**The web UI** has no automated coverage. If you change `server.py` or
`ui/index.html`, run a real mock run through the browser: start a run, watch the
gallery fill, open a cell, edit the d2, re-render, revert, download.

Stopping the server on macOS: `pkill -f "python3 server.py"` does **not** match,
because the command line carries the full interpreter path. Use `pkill -f
server.py`.

## style

The code is plain, stdlib, and commented where a line encodes something that was
learned the hard way rather than chosen. Keep that. A comment explaining why a
flag is passed explicitly is worth more than a docstring restating the function
name.

Documentation is lowercase headings and short sentences. No marketing language.

If you change a benchmark number, a model id or a timing claim in the README,
measure it first and date it, the way `OPENROUTER_CHAIN` in `config.py` is
dated.
