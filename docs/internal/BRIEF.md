# sketch brief — how Ohm's article visuals are made

## voice
- lowercase labels. his sentences, verbatim, cut to 2–4 words per line with `\n`.
- one yellow node per diagram: `style.fill: "#ffe8a3"` on the payoff. everything else default grey.
- captions in `shape: text` + `style.italic: true`, pinned with `near: bottom-center`.
- no clip-art, no emoji, no gradients. the hand-drawn line is the whole aesthetic.

## defaults
`./render file.d2` → tala + sketch + theme 1 + 2x png. svg for the site (`./render f.d2 svg`).

## pick the layout by the essay's move
| the essay does…              | pattern                | layout |
|------------------------------|------------------------|--------|
| messy thing vs clean thing   | patterns/contrast.d2   | tala   |
| many options → one path      | patterns/collapse.d2   | tala   |
| a yes/no that sorts the world| patterns/test.d2       | dagre  |
| outer thing hides inner thing| patterns/layers.d2     | tala   |
| many inputs → one self       | patterns/collage.d2    | tala   |
| a cycle + the one exit       | patterns/loop-exit.d2  | dagre  |
| a dialogue with yourself     | patterns/committee.d2  | dagre  |
| a diary sequence             | patterns/comic.d2      | tala   |
| one line that carries a post | patterns/poster.d2     | dagre  |
| reveal one idea at a time    | patterns/steps.d2 → gif| dagre  |

## rules learned the hard way
- `|md ...|` labels render borderless and wide. use `"line\nline"` strings.
- tala scatters a container with NO edges nicely (= "the open field"). cycles read better in dagre.
- `direction:` inside a container mixes vertical and horizontal in one diagram.
- png uses d2's native rasterizer: no chrome, works offline, and is already 2x the svg box, so `--scale 1` is the retina asset. gif needs `steps:`/`scenarios:` + `--animate-interval`.
- keys with `:` or `.` need quoting; curly quotes “ ” avoid escape trouble inside labels.
- 2–4 diagrams per post, never more. one per distinct move the essay makes.
