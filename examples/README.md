# ohm.quest article sketches (D2 + TALA, sketch mode)

Source: the 7 posts in ~/projects/chaos-to-order/content/posts
Tool:   d2 v0.9.0 (brew), layout engine TALA (bundled, MPL-2.0 since v0.9.0), --sketch hand-drawn mode

final/   the picks (PNG @2x for social/blog, SVG for the site — SVG scales and stays crisp)
src/     the .d2 sources — edit text, re-run, done
tala/    TALA renders     dagre/  same sources through dagre, for comparison

## regenerate one
d2 --layout=tala --sketch --theme=1 --pad 40 --scale 2 src/04-craft-test.d2 final/04-craft-test.png

## regenerate all
for f in src/*.d2; do b=$(basename "$f" .d2); d2 --layout=tala --sketch --theme=1 --pad 40 --scale 2 "$f" "final/$b.png"; done

## which diagram goes with which post
01, 02, 03  why i only work when there's a deadline   (field vs hallway / meta-work loop / three urgencies)
04, 05, 06  the ones who respect the craft            (the craft test / skills vs ways moat / shiny = avoidance)
07          hey man, are my thoughts real             (the collage of things i didn't choose)
08          this article is written by a human being  (LM pipeline vs my morning)
09          what/why this newsletter exists           (motion without direction vs the pause)
10          how this blog works                       (the actual publish flow)
11          snap out of it                            (body vs mind / grind-rest cycle)

## other layouts
--layout=dagre  for anything that is a flow/cycle (top-to-bottom, predictable)
--layout=elk    for big nested boxes
--layout=tala   for whiteboard-style boxes-in-boxes; add --tala-seeds 1,2,3,4,5,6 to try more layouts and keep the best
