# modes

A mode is surface only. It decides what a diagram looks like, never what it
says or how it is arranged. There are seven, defined in `presets.py`.

Four things come from a mode:

- **theme** — the d2 theme id passed as `--theme=N`.
- **sketch** — `--sketch=true|false`. True is the hand-drawn wobble.
- **accent** — a pair, `fill` plus `font`, not a single colour. The renderer
  replaces every `style.fill: "#ffe8a3"` in the source with that fill *and* a
  matching `style.font-color`. It has to be a pair: theme 200 paints label ink
  `#CDD6F4`, so yellow under white is unreadable without the font colour.
- **dark_theme** — `--dark-theme=N`, applied to **SVG only**. That flag writes a
  `prefers-color-scheme` block into the SVG so the image follows the reader's
  system theme. A PNG bakes exactly one palette, so it is never passed there.

Only `midnight` sets a dark theme.

`layout_default` is a fallback, not a setting. When the pattern is one of the
eleven, **the pattern's layout wins** and the mode cannot override it. The
mode's default is used only for a free-form source whose pattern is unknown —
a diagram you hand-edited in the web UI, for instance. See
`renderer.layout_for()`.

`swatch` is the mode's own paper colour. It is never passed to d2 — the web UI
uses it to draw the little mode chip, as a diagonal split between the swatch and
the accent fill, and as the background of the mode's tab.

## the seven

| mode | theme | sketch | layout default | accent fill | accent font | swatch |
|---|---|---|---|---|---|---|
| `paper` | 1 | on | `tala` | `#ffe8a3` | `#111111` | `#ffffff` |
| `blueprint` | 0 | **off** | `dagre` | `#ffe8a3` | `#111111` | `#ffffff` |
| `newsprint` | 300 | on | `dagre` | `#ffe8a3` | `#111111` | `#000410` |
| `toast` | 105 | on | `tala` | `#ffd166` | `#312102` | `#fff8ec` |
| `grape` | 7 | on | `tala` | `#ffe8a3` | `#170034` | `#f6f2fb` |
| `midnight` | 200 | on | `tala` | `#ffe8a3` | `#111111` | `#1e1e2e` |
| `origami` | 302 | on | `tala` | `#ffe8a3` | `#170206` | `#faf7f2` |

`midnight` is the only mode with a dark theme: `--dark-theme=200`, SVG only.

`paper` is the default. `inkpost post.md` with no `-m` renders `paper` and
nothing else.

---

## paper

theme 1 · sketch on · layout default `tala` · accent `#ffe8a3` on `#111111`

> the house look. grey ink, one yellow. all 11 finished diagrams are this.

Grey ink on white with a single yellow accent. This is what everything in
`examples/final/` was rendered in. Reach for it first and only leave it when you
have a reason.

## blueprint

theme 0 · sketch **off** · layout default `dagre` · accent `#ffe8a3` on `#111111`

> clean lines, no wobble. for a flow that should look precise.

The only mode with sketch off, so the lines are straight and the corners are
sharp. Use it when the diagram is a real pipeline or architecture and the
hand-drawn wobble would read as imprecision rather than warmth.

## newsprint

theme 300 · sketch on · layout default `dagre` · accent `#ffe8a3` on `#111111`

> terminal theme. black and white. closest to the printed paper.

d2's terminal theme. Black and white, monospaced. The one to use if the diagram
is going to be printed, or set next to code.

## toast

theme 105 · sketch on · layout default `tala` · accent `#ffd166` on `#312102`

> warm and tinted. deeper yellow because the theme already tints nodes.

Warm cream. This is the only mode whose accent differs from the house yellow:
theme 105 already tints every node, so `#ffe8a3` would not stand out against
it and the accent is deepened to `#ffd166` with dark brown text.

## grape

theme 7 · sketch on · layout default `tala` · accent `#ffe8a3` on `#170034`

> aubergine. the most designed light mode. good for a poster.

Aubergine. The most designed of the light modes, and the one that holds up
largest — pair it with the `poster` pattern when a single line is carrying the
whole image.

## midnight

theme 200 · sketch on · layout default `tala` · accent `#ffe8a3` on `#111111`
· dark theme 200 (SVG only)

> dark mauve. the accent font colour is mandatory here or the label vanishes.

The dark mode. Theme 200 paints label ink `#CDD6F4`, which is nearly white, so
the accent's near-black font colour is not optional — without it the text on the
yellow node disappears. This is the whole reason `accent` is a pair.

Because it also sets `dark_theme`, its SVG output carries a
`prefers-color-scheme` block and follows the reader's system setting. Its PNG
does not — a PNG is one fixed palette.

## origami

theme 302 · sketch on · layout default `tala` · accent `#ffe8a3` on `#170206`

> soft paper-fold palette. the gentlest light mode.

A soft paper-fold palette. The quietest of the seven. Good when the diagram has
a lot of text and you want nothing competing with it.

## adding one

See [CONTRIBUTING.md](../CONTRIBUTING.md). A mode is one dict in `presets.py`
plus its name in `MODE_ORDER`. Theme ids must be in `config.VALID_THEMES`; there
is no theme 2.
