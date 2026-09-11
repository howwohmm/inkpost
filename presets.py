"""the seven named aesthetic modes. SPEC.md section 5.

a preset is SURFACE ONLY: theme, sketch, dark theme, accent pair, and a
`layout_default` that is the fallback for a source whose pattern is unknown (a
hand-edited free-form diagram). when the pattern is one of the eleven, THE
PATTERN'S LAYOUT WINS — see renderer.layout_for(). a mode may not override it.

`accent` is a PAIR, not one hex (SPEC section 0, override 2): theme 200 paints
label ink #CDD6F4, so yellow-under-white is unreadable without the font colour.

`dark_theme` is applied to SVG ONLY — --dark-theme writes a prefers-color-scheme
block and a png bakes exactly one palette.
"""

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
MODE_ORDER    = ["paper", "blueprint", "newsprint", "toast", "grape", "midnight", "origami"]
DEFAULT_MODES = ["paper"]
