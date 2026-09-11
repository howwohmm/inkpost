# inkpost

Turn a blog post into hand-drawn diagrams.

You point inkpost at a markdown post. A language model reads it, picks 2 to 4
visual patterns that match the moves the essay actually makes, and fills each
pattern's labels with sentences lifted verbatim out of your own writing. The
diagrams render through [d2](https://d2lang.com) with the TALA layout engine in
hand-drawn sketch mode, in any of seven aesthetic modes. Output is PNG, SVG and
GIF, written to a folder on your disk. There is a CLI and a small local web UI.

Nothing is published anywhere and there is no telemetry. The only thing that
leaves your machine is the cleaned post itself, sent to whichever model backend
you picked — OpenRouter, or Anthropic through the `claude` CLI. The `mock`
backend sends nothing at all.

## see it

The repo ships the finished diagrams that came out of it.

Start with `examples/showcase/`:

- `examples/showcase/01-deadline-field-vs-hallway.png` — a scattered field of
  options collapsing into one hallway (the `collapse` pattern)
- `examples/showcase/04-craft-test.png` — one yes/no question that sorts the
  world (`test`)
- `examples/showcase/05-craft-moat.png` — what people think the thing is,
  wrapped around what it actually is (`layers`)
- `examples/showcase/08-human-vs-ai.png` — the tidy version against the messy
  one (`contrast`)
- `examples/showcase/10-how-this-blog-works.png` — an actual publishing pipeline
- `examples/showcase/all-modes.png` — one diagram rendered in all seven modes,
  side by side and labelled. `examples/showcase/mode-<name>.png` is each one on
  its own.

`examples/final/` has eleven diagrams drawn from seven real posts as SVG, which
is what you want on a website — it scales and stays crisp. `examples/src/` has
the d2 source for every one of them, so you can change the words and re-render.

`patterns/preview/` has a rendered thumbnail of every pattern template,
including `patterns/preview/steps.gif`, which is the only animated one.

`examples/variations/` is a reference gallery of what else d2 can draw, with
sources in `examples/variations/src/` and `examples/variations/out/loop-steps.gif`
showing a multi-board source animated.

## requirements

- Python 3.9 or newer. Standard library only. The core install has no
  dependencies.
- `d2` on your PATH. TALA ships inside d2 from v0.9.0 onward, so you do not
  install it separately.

  ```
  brew install d2
  # or
  curl -fsSL https://d2lang.com/install.sh | sh -s --
  ```

- Optional: the `claude` CLI, if you want the best label wording.
- Optional: an OpenRouter API key, if you want the fast free-model backend.

You need at least one of those two optional things to get real output. Without
either, inkpost falls back to the `mock` backend, which picks patterns by
keyword and is only useful for testing the rendering path.

## quick start

```
git clone <repo> inkpost && cd inkpost
pip install ".[pretty]"      # or just `pip install .` — see below
```

That installs two commands: `inkpost` and `inkpost-serve`. `[pretty]` adds
clypi, which gives the CLI boxes and spinners; without it the output is plain
ANSI and everything else is the same. Once the package is on PyPI,
`pip install inkpost` does the same thing without the clone.

```
inkpost --list          # your posts, the seven modes, which backends are ready
inkpost your-post.md    # draw it
```

From a checkout you can also skip installing entirely. The modules are flat at
the repo root and import each other directly, and the `./sketch` launcher runs
the same CLI:

```
./sketch --list
./sketch posts/2026-01-15-the-tuesday-problem.md
```

`posts/` in the checkout holds two short sample posts, so the picker has
something to show before you point it at your own writing.

### where output lands

Output goes to `runs/<slug>/`, where `<slug>` comes from the post title:

```
runs/<slug>/
  post.md              the cleaned post the model was given
  src/<name>.d2        one d2 source per diagram
  out/<mode>/<name>.png
  out/<mode>/<name>.svg
```

In a checkout that is `runs/` next to the code. An installed copy cannot write
into site-packages, so it puts `runs/`, the render cache and a fallback `.env`
under `~/.inkpost` instead. Move that with `$INKPOST_HOME`. A `.env` in your
current directory still wins.

On macOS the CLI opens the output folder in Finder when it finishes. Pass
`--no-open` to stop it, which is what you want on Linux — the opener shells out
to macOS `open` and does nothing useful elsewhere.

Re-running the same post writes into the same `runs/<slug>/` folder and
overwrites files with the same name. The web UI behaves differently: it makes
`<slug>-2`, `<slug>-3` and so on, so a re-run never destroys the previous one.

## the cli

```
inkpost                                pick a post from a list
inkpost snap-out-of-it                 a slug, or a fragment of one
inkpost path/to/post.md                any markdown file
inkpost post.md -m paper,midnight      choose modes
inkpost post.md -m all                 every mode
inkpost post.md -f png,svg,gif         choose formats
inkpost post.md -b openrouter          choose a backend
inkpost --list                         posts, modes, backends
inkpost --runs                         what you have made
inkpost --open snap-out-of-it          reopen a finished run
```

| flag | default | what it does |
|---|---|---|
| `post` | — | a `.md` path, a filename, a slug, or a fragment of a slug. With no argument you get an interactive picker. An ambiguous fragment prints the matches and exits. |
| `-m`, `--modes` | `paper` | comma separated mode names, or `all` |
| `-f`, `--formats` | `png,svg` | any of `png`, `svg`, `gif` |
| `-b`, `--backend` | `auto` | `auto`, `claude-code`, `openrouter`, `mock` |
| `--model` | backend default | override the model name passed to the backend |
| `--posts-dir DIR` | see configuration | the folder of `.md` posts to pick from, for this run only |
| `--list` | — | posts, modes and backend readiness, then exit |
| `--runs` | — | list previous runs and their modes, then exit |
| `--open SLUG` | — | open a finished run's `out/` folder, then exit |
| `--no-open` | off | do not open a file browser at the end |
| `--version` | — | print the version and exit |

`gif` is only produced for the `steps` pattern. For every other pattern that job
is skipped silently, because there is nothing to animate.

The CLI calls the planner and renderer directly. No server has to be running.
Terminal styling comes from [clypi](https://github.com/danimelchor/clypi) if it
is importable; if it is not, the CLI falls back to plain ANSI and works the
same.

## the web ui

```
inkpost-serve
# or, from a checkout:
python3 server.py

# http://localhost:8788
```

It binds `127.0.0.1` only, never `0.0.0.0`. Paste or pick a post, tick the modes
you want, and watch the gallery fill in. Click a cell for the large view, edit
the d2 by hand, change the layout, re-render, revert to the planned source, or
download the file.

The server writes two extra files per run that the CLI does not: `plan.json`,
the model's plan, which is never mutated so revert always has somewhere to go,
and `run.json`, the manifest it polls for progress. Both live in
`runs/<slug>/`. Nothing is written outside `runs/` and the render cache.

## backends

| backend | needs | measured | how it plans |
|---|---|---|---|
| `claude-code` | the `claude` CLI on your PATH | ~2 min per post | writes the d2 source directly |
| `openrouter` | a free key in `.env` | 12–25 s per post | fills pattern slots |
| `mock` | nothing | instant | keyword heuristics, no model |

`auto` prefers `claude-code` when the `claude` binary exists, then `openrouter`
when a key exists, then `mock`. Quality first, not speed first.

The tradeoff is the wording, and it is not small. Claude on Opus lifts whole
sentences out of the post, so a box reads "if i'm not productive every minute,
i'm falling behind." The free models write "internal conflict" in the same box.
They pick patterns well and they are fast; they are blunter writers. Use
`-b openrouter` when you want the shape quickly and `-b claude-code` when you
want the words.

**Slot mode.** Free models cannot reliably author valid d2. So on OpenRouter the
model never writes code at all. It picks a pattern and returns a dictionary of
label text, and inkpost substitutes those labels into the template itself. The
structure is therefore correct by construction. A diagram is thrown away if
fewer than 70% of its labels came back filled.

Free models share an upstream pool and return 429 often, so `openrouter` walks a
chain instead of trusting one model. Benchmarked 11 Sep 2026, wall clock to a
valid plan:

| model | time |
|---|---|
| `poolside/laguna-xs-2.1:free` | ~14 s |
| `inclusionai/ling-3.0-flash-fin:free` | ~19 s |
| `poolside/laguna-s-2.1:free` | ~21 s |
| `dots-studio/dots-3-note-preview:free` | ~45 s, last resort |

The chain lives in `OPENROUTER_CHAIN` in `config.py`. Requests are throttled to
18 per minute, under OpenRouter's documented ceiling of 20.

`claude-code` defaults to Opus. `--model sonnet` is cheaper and faster and still
writes real sentences.

`--model` is also honoured on `openrouter`, where it replaces the whole fallback
chain with the one model you named. That is how you try a paid model — and the
only way to spend money with this tool.

## configuration

Two things are per-user rather than per-install: where your posts live, and what
your writing sounds like. Both resolve from an environment variable, then
`~/.config/inkpost/config.json`, then a default. Neither can fail; a missing or
malformed config file is simply ignored.

### where your posts live

Resolution order for the post picker:

1. `--posts-dir` on the command line
2. `$INKPOST_POSTS_DIR`
3. `"posts_dir"` in `~/.config/inkpost/config.json`
4. `./posts`, relative to where you ran the command
5. a `posts/` directory shipped inside the package, if there is one

The environment variable and the config file win even if the directory does not
exist yet, because they are explicit intent. A missing directory is never fatal
— the picker is just empty, and you can always pass a file path instead.

### voice

The planner builds its prompts from a voice. The craft rules — lift the
author's words verbatim, keep lines short, one accent node per diagram — are
generic and live in `planner.py`. Only three things are yours:

| key | env var | meaning |
|---|---|---|
| `author` | `INKPOST_AUTHOR` | the name the prompt uses for you |
| `style` | `INKPOST_VOICE_STYLE` | one line describing your register |
| `lowercase` | `INKPOST_VOICE_LOWERCASE` | demand lowercase labels |

`{author}` inside a style string is replaced with the resolved author name, so a
style can be written once and named per-user.

The default voice is `generic`: no name, no register, no lowercase demand. It
tells the model it has never read you before and must therefore match whatever
register the post in front of it actually has. That is the right default and
usually good enough.

`lowercase-diary` is the built-in preset the tool was originally written for:

```
INKPOST_VOICE=lowercase-diary INKPOST_AUTHOR="your name" inkpost post.md
```

You can also define your own preset as JSON at
`~/.config/inkpost/voices/<name>.json` with the same three keys, and select it
with `INKPOST_VOICE=<name>`.

### the config file

`~/.config/inkpost/config.json` is entirely optional. Move it with
`$INKPOST_CONFIG_DIR`.

```json
{
  "posts_dir": "~/writing/posts",
  "voice": "lowercase-diary",
  "author": "your name",
  "lowercase": true
}
```

`voice` may be a preset name or an inline object with `author`, `style` and
`lowercase`. Top-level `author` / `style` / `lowercase` override whatever the
preset said, and the environment variables override those.

### the api key

```
cp .env.example .env
# OPENROUTER_API_KEY=sk-or-...
```

`.env` is gitignored. Get a key at <https://openrouter.ai/keys>. Every model in
the default chain ends in `:free`, so a normal run costs nothing. `--model` is
passed straight through, so naming a paid model there will bill your key.

### other knobs

| variable | what it overrides |
|---|---|
| `INKPOST_HOME` | where an installed copy writes `runs/`, the cache and a fallback `.env`. Default `~/.inkpost`. Ignored in a checkout. |
| `INKPOST_D2` | path to the `d2` binary |
| `INKPOST_CLAUDE` | path to the `claude` binary |
| `INKPOST_CLAUDE_MODEL` | the Claude model, default `opus` |
| `INKPOST_BACKEND` | the default backend |

Everything else — padding, PNG scale, GIF frame interval, timeouts, worker
count, the diagram count range — is a named constant at the top of `config.py`.

## how it works

1. **Clean the post.** Frontmatter is parsed for a title and description, then
   dropped. A leading hero image goes. Newsletter boilerplate and `[Share](...)`
   lines are removed wherever they appear, not just at the end. A post longer
   than 24,000 characters keeps its first 18,000 and last 6,000 with the middle
   marked as trimmed. Curly quotes are left alone.

2. **Plan.** The model gets the cleaned post plus a catalog of the eleven
   patterns — the move each one draws, when to reach for it, and its exact label
   keys. It returns 2 to 4 diagrams. On `claude-code` it writes the d2 source. On
   `openrouter` it returns label text and inkpost fills the template.

3. **Validate and repair.** Every source goes through a real d2 compile, not
   `d2 validate`. The gate runs `d2 --layout=... --stdout-format ascii` and checks
   the return code, because `d2 validate` is parse-only and will happily wave
   through `font-size: 0`, `shape: blob` and `fill: notacolor`. A source that
   fails goes back to the model once with the parsed error list attached. If it
   still fails, that diagram is skipped and the rest of the run continues. The
   whole run is capped at four model calls: one plan, one plan repair, and up to
   two source repairs.

4. **Render across modes.** Each surviving source renders once per mode per
   format. A mode supplies the d2 theme, sketch on or off, and an accent colour
   pair that is substituted into the template's yellow fill. The layout engine
   comes from the pattern, not the mode. Results are cached by a hash of the
   source, mode, format, layout and d2 version, so re-renders are free.

5. **Save.** Everything lands under `runs/<slug>/` as described above.

## the eleven patterns

Each pattern is a d2 template with named slots. Full slot lists and the notes
that govern each one are in [docs/PATTERNS.md](docs/PATTERNS.md).

| pattern | the essay move it fits |
|---|---|
| `contrast` | messy thing vs clean thing |
| `collapse` | many options → one path |
| `test` | a yes/no that sorts the world |
| `layers` | outer thing hides inner thing |
| `collage` | many inputs → one self |
| `loop-exit` | a cycle + the one exit |
| `committee` | a dialogue with yourself |
| `comic` | a diary sequence |
| `poster` | one line that carries a post |
| `steps` | reveal one idea at a time |
| `taxonomy` | kinds of a thing, ranked |

`poster` is the fallback for a post with no structure, only one great sentence.
`steps` is the only pattern that renders a GIF. `committee` is the only one with
no accent colour, because a d2 sequence diagram has no shape to fill.

## the seven modes

Full values are in [docs/MODES.md](docs/MODES.md).

| mode | note |
|---|---|
| `paper` | the house look. grey ink, one yellow. all 11 finished diagrams are this. |
| `blueprint` | clean lines, no wobble. for a flow that should look precise. |
| `newsprint` | terminal theme. black and white. closest to the printed paper. |
| `toast` | warm and tinted. deeper yellow because the theme already tints nodes. |
| `grape` | aubergine. the most designed light mode. good for a poster. |
| `midnight` | dark mauve. the accent font colour is mandatory here or the label vanishes. |
| `origami` | soft paper-fold palette. the gentlest light mode. |

Pick as many as you want. Each diagram renders once per mode, so you can compare
the same idea in every look side by side.

## troubleshooting

**`d2 not found`.** The server refuses to start and the renderer fails on every
job. Install it with `brew install d2` or the install script above. If d2 is
somewhere unusual, set `INKPOST_D2` to its full path — the error message names
the variable.

**No backend.** `inkpost --list` prints readiness for all three. If both
`claude-code` and `openrouter` say `unavailable`, you have no `claude` binary and
no key, and every run will quietly use `mock`, which produces keyword-matched
placeholder text rather than your sentences. Install one or the other.

**OpenRouter 429s.** Free models sit on a shared upstream pool and rate-limit
often. This is expected. inkpost throttles itself to 18 requests a minute and
hops down the chain in `OPENROUTER_CHAIN` on a 429. If the whole chain is
saturated, wait a few minutes or switch to `-b claude-code`. A key that is
missing or wrong fails differently and says so.

**`claude -p` is slow.** Two minutes a post is normal for Opus. It is the
quality setting. `--model sonnet` is cheaper and faster. `-b openrouter` takes it
under half a minute at the cost of the wording. The Claude call has a 420 second
timeout, and the planner as a whole has 480.

**Stopping the server on macOS.** `pkill -f "python3 server.py"` does not match,
because the command line carries the full interpreter path, not the literal
string `python3`. Use:

```
pkill -f server.py
```

**Port 8788 already in use.** The server says so and exits rather than binding
somewhere else. That almost always means it is already running — open
<http://localhost:8788>.

**A GIF failed but the PNG and SVG rendered.** If the error mentions
`even-odd clip work ... exceeds limit`, you hit a limit in d2's own GIF
rasteriser. It depends on the theme, not on your diagram: as of d2 v0.9.0 the
`steps` template renders as a GIF in `paper`, `blueprint`, `newsprint` and
`grape`, and fails in `toast`, `midnight` and `origami`. The limit scales with
rasterised area, so a large diagram with long labels can trip it in the other
modes too. Render the GIF in one of the modes that works, or take the still — the
PNG and SVG are fine in all seven.

**A diagram was skipped.** The run prints `✗ <name> did not compile — skipped`.
The model wrote d2 that failed the compile gate twice. The other diagrams still
render. It is worth re-running; it is usually not deterministic.

## license and credits

MIT. See [LICENSE](LICENSE).

Rendering and layout are [d2](https://d2lang.com) and the TALA layout engine, by
[Terrastruct](https://terrastruct.com), licensed MPL-2.0. TALA has been bundled
with d2 since v0.9.0. inkpost shells out to the `d2` binary and does not vendor
any of it.

Terminal styling is [clypi](https://github.com/danimelchor/clypi), used if
present and optional.
