# d2 reference — every knob (rendered examples in examples/variations)

SHEET-1-themes.png      one diagram, 16 themes (light, dark, terminal, origami, C4), sketch vs clean
SHEET-2-features.png    shapes · styles · arrows · comic grid · sequence diagram · quote poster · icons · table · markdown/code · links
out/loop-steps.gif      the meta-work loop revealed one step at a time (steps: {} + --animate-interval)
out/scenarios.gif       same diagram, two states: open field vs deadline (scenarios: {})
out/loop-steps.pdf      one page per step         out/loop-steps.pptx  one slide per step
out/interactive.svg     hover = tooltip, click = link to the post (svg only, for the site)
src/                    every source; edit + re-run

## knobs
--theme=N          0 neutral · 1 grey · 3 flagship · 4 cool · 5 mixed berry blue · 6 grape · 7 aubergine · 8 colorblind clear · 100 vanilla · 101 creamsicle · 102 shirley temple · 103 earth · 104 everglade green · 105 toast · 200/201 dark · 300 terminal · 301 terminal grayscale · 302 origami · 303 C4   (there is no theme 2)
--dark-theme=200   svg switches palette with the viewer's dark mode
--sketch           hand-drawn.  --sketch=false for clean
--layout           tala (whiteboard) · dagre (flows) · elk (big nested)
--animate-interval 1200   for .gif / animated .svg from steps/layers/scenarios
--scale 2          retina png.   output ext picks format: .svg .png .pdf .pptx .gif
d2 --watch file.d2 live browser preview while editing

## in-file
vars: { d2-config: { theme-id: 1; sketch: true; layout-engine: tala } }   bake settings into the file
shape: page|document|cylinder|queue|package|step|callout|stored_data|person|diamond|oval|circle|hexagon|cloud|text|sequence_diagram|sql_table|class|image
style: 3d · multiple · double-border · shadow · fill-pattern: dots|lines|grain · stroke-dash · border-radius · stroke-width · opacity · font: mono · text-transform · font-size 8-100 · bold/italic/underline · animated (edges, svg)
arrowheads: target-arrowhead.shape: triangle|arrow|diamond|circle|box|cf-one|cf-many|cross ; <-> both ; -- none
grid-rows / grid-columns / grid-gap   comic panels, cards, tables of boxes
icon: https://icons.terrastruct.com/...   needs network at render
tooltip: / link:   interactive svg
|md ... |  |yaml ... |  |go ... |   markdown / code blocks as labels
steps / layers / scenarios   multi-board → gif, pdf, pptx
near: top-center | bottom-right   pin captions and titles
