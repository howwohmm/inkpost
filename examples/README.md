# examples

Finished output, kept so you can see what inkpost makes before you run it.

- `showcase/all-modes.png` — one diagram drawn in all seven modes.
- `showcase/*.png` — five diagrams, each from a different pattern.
- `final/*.svg` — eleven diagrams drawn from real blog posts.
- `src/*.d2` — the source for those eleven. Plain text, editable.
- `variations/src/*.d2` — sources that show other things d2 can draw. Shapes,
  styles, arrow types, a comic grid, a sequence diagram and a quote poster.

To draw one of the sources again:

```bash
d2 --layout=tala --sketch --theme=1 --pad 40 src/04-craft-test.d2 out.png
```
