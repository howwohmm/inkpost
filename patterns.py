"""the eleven house patterns, as data. SPEC.md section 6.

each template `d2` string is BYTE-IDENTICAL to its file on disk
(patterns/<name>.d2, and examples/src/03-deadline-three-urgencies.d2 for
taxonomy). the runtime copies live here as strings so the tool has no
filesystem dependency at plan time (SPEC section 3) — the files stay as test
oracles. tests.py case 34 is the drift guard between these strings, the files
and the {{CATALOG}} block the planner renders.

PATTERNS[name] keys:
  move   str   the BRIEF row, verbatim. goes into the prompt catalog.
  when   str   one line telling the model when to reach for it
  layout str   "tala" | "dagre" — the flag actually passed to d2
  accent bool  does this pattern have a yellow node at all
  gif    bool  does it render an animated gif (steps only)
  d2     str   the template source, verbatim

two additive fields, so planner.CATALOG can be rendered from data alone and can
never drift from the code:
  notes       str  the per-pattern `notes:` line of the catalog block
  layout_note str  the catalog's `layout:` display line

committee renders `shape: sequence_diagram` and comic renders a grid — both
supply their own layout engine and the --layout flag is inert, but they still
carry a layout value so the renderer never has to branch.
"""

import json

PATTERNS = {
  'contrast': {
    "move": 'messy thing vs clean thing',
    "when": 'the post sets a tidy or imagined version against the real, lumpy one.',
    "layout": 'tala',
    "accent": True,
    "gif": False,
    "notes": '`done` is the accent — the thing that actually got made. 2 to 4 detours.',
    "layout_note": 'tala (the tool sets this; do not write a layout line)',
    "d2": '# contrast: the clean thing vs the messy thing (human-vs-LM)\ndirection: right\nclean: "the tidy version" {\n  in: "input"\n  out: "glassy output"\n  in -> out\n}\nmessy: "the real version" {\n  a: "start"\n  b: "detour"\n  c: "doubt"\n  hub: "type" {shape: circle}\n  done: "the thing\\n(lumpy on purpose)" {shape: page; style.fill: "#ffe8a3"}\n  a -> hub\n  hub -> b\n  b -> hub: "back again"\n  hub -> c\n  c -> hub: "leave it anyway"\n  hub -> done\n}\ncaption: "no friction = no fingerprints." {shape: text; style.italic: true; style.font-size: 22}\ncaption.near: bottom-center\n',
  },
  'collapse': {
    "move": 'many options → one path',
    "when": 'the post names a pile of choices and then the one thing that kills them all.',
    "layout": 'tala',
    "accent": True,
    "gif": False,
    "notes": 'NEVER put an arrow inside `field`. the edgeless container is exactly what makes tala scatter it into an open field. 4 to 8 options. `me` is one concept in two places, so it is yellow in both. the field -> hallway edge label is the loudest sentence in the diagram — give it the strongest clause the post has about the collapsing force.',
    "layout_note": 'tala (the tool sets this; do not write a layout line)',
    "d2": '# collapse: the open field (no edges → tala scatters) → one hallway\ndirection: down\nfield: "the open field" {\n  style.stroke-dash: 5\n  style.fill: transparent\n  o1: "option"\n  o2: "another option"\n  o3: "the meta-option"\n  o4: "the guilt"\n  o5: "the question"\n  o6: "the rabbit hole"\n  me: "me" {shape: circle; style.fill: "#ffe8a3"}\n}\nhallway: "the hallway" {\n  direction: right\n  me: "me" {shape: circle; style.fill: "#ffe8a3"}\n  task: "the task"\n  end: "the clock" {shape: circle}\n  me -> task -> end\n}\nfield -> hallway: "the thing that collapses it" {style.bold: true}\n',
  },
  'test': {
    "move": 'a yes/no that sorts the world',
    "when": 'the post proposes one question that separates people or things.',
    "layout": 'dagre',
    "accent": True,
    "gif": False,
    "notes": 'the accent goes on the answer the post is actually FOR, which is often the one reached by "no". keep the question 2 to 4 lines and end it with a ?.',
    "layout_note": 'dagre (the tool sets this; do not write a layout line)',
    "d2": '# test: one question that sorts the world\ndirection: down\nthing: "the thing" {shape: page}\nq: "the question\\nthat sorts it?" {shape: diamond}\nno: "one answer."\nyes: "the other answer." {style.fill: "#ffe8a3"}\nthing -> q\nq -> no: "yes"\nq -> yes: "no"\n',
  },
  'layers': {
    "move": 'outer thing hides inner thing',
    "when": 'the post says what looks like the point is not the point.',
    "layout": 'tala',
    "accent": True,
    "gif": False,
    "notes": '3 to 5 details. the `#f4f4f4` on the middle layer is not the accent, leave it. the note is optional; drop both its lines if the post has no aside.',
    "layout_note": 'tala (the tool sets this; do not write a layout line)',
    "d2": '# layers: what people see wraps what actually matters\nouter: "what people think it is" {\n  style.stroke-dash: 5\n  style.fill: transparent\n  middle: "the visible layer" {\n    style.fill: "#f4f4f4"\n    core: "the real thing" {\n      style.fill: "#ffe8a3"\n      style.bold: true\n      a: "detail one"\n      b: "detail two"\n      c: "detail three"\n    }\n  }\n}\nnote: "takes years. invisible while forming." {shape: text; style.italic: true}\nnote -> outer.middle.core: {style.stroke-dash: 3}\n',
  },
  'collage': {
    "move": 'many inputs → one self',
    "when": 'the post is about being assembled out of things you did not choose.',
    "layout": 'tala',
    "accent": True,
    "gif": False,
    "notes": '5 to 8 inputs, and one `inputs.iN -> self` line per input — add or remove BOTH together. repeating a word across inputs is fine. `free` ends in a ?.',
    "layout_note": 'tala (the tool sets this; do not write a layout line)',
    "d2": '# collage: many inputs → one self → one exit\ndirection: right\ninputs: "things i didn\'t choose" {\n  style.stroke-dash: 5\n  style.fill: transparent\n  i1: "input"\n  i2: "input"\n  i3: "input"\n  i4: "input"\n  i5: "input"\n}\nself: "“my” thing" {shape: cloud}\ninputs.i1 -> self\ninputs.i2 -> self\ninputs.i3 -> self\ninputs.i4 -> self\ninputs.i5 -> self\nstrip: "strip the noise" {shape: hexagon}\nfree: "the real question?" {shape: circle; style.fill: "#ffe8a3"; style.bold: true}\nself -> strip -> free\n',
  },
  'loop-exit': {
    "move": 'a cycle + the one exit',
    "when": 'the post describes a loop the author keeps running, and the thing that breaks it.',
    "layout": 'dagre',
    "accent": True,
    "gif": False,
    "notes": '3 to 5 steps; the LAST step is the felt cost, the thing that hurts. keep the back-edge dashed. the note is optional and usually carries the reframe.',
    "layout_note": 'dagre (the tool sets this; do not write a layout line)',
    "d2": '# loop-exit: the cycle, and the one edge that breaks it\ndirection: down\nstart: "the condition" {shape: oval}\ns1: "step one"\ns2: "step two"\ns3: "step three"\ns4: "feel bad about it"\nstart -> s1 -> s2 -> s3 -> s4\ns4 -> s1: "again" {style.stroke-dash: 3}\nexit: "the real consequence" {shape: hexagon; style.fill: "#ffe8a3"}\ndone: "execution mode."\ns4 -> exit\nexit -> done\nnote: "this isn\'t laziness. it\'s rational." {shape: text; style.italic: true}\nnote.near: bottom-center\n',
  },
  'committee': {
    "move": 'a dialogue with yourself',
    "when": 'the post quotes an internal argument.',
    "layout": 'dagre',
    "accent": False,
    "gif": False,
    "notes": 'this pattern has NO yellow node and NO caption — `near:` does not work inside a sequence diagram and there is no shape to fill. the emphasis beat is {style.bold: true} on EXACTLY ONE message: the outside pressure landing. 5 to 10 messages. `me -> me` is self-talk and one beat should be it.',
    "layout_note": 'none — sequence_diagram is its own engine',
    "d2": '# committee: a dialogue with yourself (sequence diagram)\nshape: sequence_diagram\nme: "me"\nvoice: "the internal committee"\nworld: "the clock"\nme -> voice: "should i start?"\nvoice -> me: "are you even ready?"\nvoice -> me: "which version though?"\nme -> me: "reorganise notion instead"\nworld -> me: "12 hours left." {style.bold: true}\nvoice -> me: "(silence)"\nme -> world: "one sitting. something decent."\n',
  },
  'comic': {
    "move": 'a diary sequence',
    "when": 'the post walks through a day or an episode in order.',
    "layout": 'dagre',
    "accent": True,
    "gif": False,
    "notes": 'NEVER write a `direction:` line here — it fights the grid. exactly 6 panels (2 x 3); a different count leaves empty cells. keep width/height on every panel. one middle panel may keep the dots fill as the avoidance beat. the LAST panel is the accent. 2 to 4 short lines per panel.',
    "layout_note": 'none — grid is its own engine',
    "d2": '# comic: a diary sequence as panels\ngrid-rows: 2\ngrid-columns: 3\ngrid-gap: 24\np1: "panel one.\\nthe boring start." {width: 320; height: 240}\np2: "panel two.\\nthe small mess." {width: 320; height: 240}\np3: "panel three.\\nthe stall." {width: 320; height: 240}\np4: "panel four.\\nthe avoidance." {width: 320; height: 240; style.fill-pattern: dots}\np5: "panel five.\\nthe grind." {width: 320; height: 240}\np6: "panel six.\\nthe thing." {width: 320; height: 240; style.fill: "#ffe8a3"; style.bold: true}\n',
  },
  'poster': {
    "move": 'one line that carries a post',
    "when": 'the post has no structure, only one great sentence. this is the fallback.',
    "layout": 'dagre',
    "accent": True,
    "gif": False,
    "notes": "the title is the author's verbatim line split over exactly 2 lines. font-size 44 and 18 are inside d2's 8..100 limit — do not raise them. `b` is the accent: the durable force, the one that compounds. the `sig` node is a placeholder signature — put the author's own site or name there if the post gives you one, otherwise leave the node exactly as it is.",
    "layout_note": 'dagre (the tool sets this; do not write a layout line)',
    "d2": '# poster: one line that carries a post, plus a tiny diagram\ndirection: down\ntitle: "the line.\\nthe second half of the line." {shape: text; style.font-size: 44; style.bold: true}\na: "this" {shape: oval}\nb: "that" {shape: hexagon; style.fill: "#ffe8a3"}\nyou: "you" {shape: person}\na -> you: "carries"\nb -> you: "compounds"\nsig: "— yoursite.com" {shape: text; style.italic: true; style.font-size: 18}\ntitle.near: top-center\nsig.near: bottom-right\n',
  },
  'steps': {
    "move": 'reveal one idea at a time',
    "when": 'the post builds an argument that only works in order. renders as a gif.',
    "layout": 'dagre',
    "accent": True,
    "gif": True,
    "notes": 'board 1 introduces the root alone. each later board adds ONE node plus its edge and refers to earlier keys by bare name. number the boards 1..N with no gaps — the tool reads the highest number to render the finished still. 5 or 6 boards. the LAST board carries the accent.',
    "layout_note": 'dagre (the tool sets this; do not write a layout line)',
    "d2": '# steps: reveal one idea at a time → ./render steps.d2 gif  (also pdf, pptx)\ndirection: down\nsteps: {\n  1: { start: "the condition" {shape: oval} }\n  2: { s1: "step one"; start -> s1 }\n  3: { s2: "step two"; s1 -> s2 }\n  4: { s3: "feel bad about it"; s2 -> s3; s3 -> s1: "again" {style.stroke-dash: 3} }\n  5: { exit: "the consequence" {shape: hexagon; style.fill: "#ffe8a3"}; done: "execution."; s3 -> exit -> done }\n}\n',
  },
  'taxonomy': {
    "move": 'kinds of a thing, ranked',
    "when": 'the post enumerates two or three KINDS of something and ranks them.\nthis is the only pattern for an essay that lists rather than flows.',
    "layout": 'tala',
    "accent": True,
    "gif": False,
    "notes": 'exactly 3 kinds. each column is a title line, a blank line (\\n\\n), then 3 to 6 short lines of their prose — no more, it overflows. the THIRD kind is the accent and so is the second summary oval: one concept, ranked and then named. the two edge labels are single comparative words.',
    "layout_note": 'tala (the tool sets this; do not write a layout line)',
    "d2": '# three kinds of urgency (the reluctant taxonomy)\ndirection: right\n\nimported: "imported urgency\\n\\nsomeone else sets the deadline.\\nclient. boss. exam.\\n\\nefficient but fragile.\\nif the structure disappears,\\nso does the productivity."\nmanufactured: "manufactured urgency\\n\\nyou create the stakes.\\nship in public. tell people.\\nyour brain knows it\'s fake…\\n\\nbut this is how agency starts."\nnone: "no urgency at all\\n\\nbuild because it\'s interesting.\\nwrite because you have\\nsomething to say.\\nno dopamine hit. no relief.\\n\\nthe slow, compounding 1%." {style.fill: "#ffe8a3"}\n\nimported -> manufactured: "harder"\nmanufactured -> none: "hardest"\n\nresponsive: "responsive.\\nsurvives." {shape: oval}\nselfdirected: "self-directed.\\nbuilds." {shape: oval; style.fill: "#ffe8a3"}\nresponsive -> selfdirected: "pressure borrows energy from the future.\\ndiscipline builds it from systems."\n',
  },
}

PATTERN_ORDER = list(PATTERNS)

# ---------------------------------------------------------------- slot filling
# small/free models cannot reliably author d2, but they CAN choose a pattern and
# supply the words. so we expose each template's quoted labels as named slots and
# do the substitution in code — the structure can then never break.

import re as _re

_LABEL_RE = _re.compile(r'"((?:[^"\\]|\\.)*)"')


def slots(name):
    """the template's quoted labels, in order, deduped. these are the slot keys."""
    tpl = PATTERNS[name]["d2"]
    out, seen = [], set()
    for m in _LABEL_RE.finditer(tpl):
        lab = m.group(1)
        if not lab or lab in seen:
            continue
        # a quoted string is a STYLE VALUE (not a label) only when the text just
        # before it is a style/attr assignment. everything else is a real label,
        # including short words like "option" or "me".
        before = tpl[:m.start()].rsplit("\n", 1)[-1]
        if _re.search(r"(style\.[a-z0-9.-]+|icon|link|tooltip|shape|font|"
                      r"fill|stroke|near|direction)\s*:\s*$", before):
            continue
        if lab.startswith("#"):
            continue
        seen.add(lab)
        out.append(lab)
    return out


def _clean(val):
    """make any model string safe to sit inside a d2 double-quoted label."""
    s = str(val or "").replace("\r", "")
    s = s.replace("\\", "")                      # no stray escapes
    s = s.replace('"', "\u201c")                  # real quotes -> curly, never bare "
    s = _re.sub(r"[ \t]+", " ", s)
    s = "\n".join(ln.strip() for ln in s.split("\n") if ln.strip())
    return s.replace("\n", "\\n")               # d2 wants a literal \n in the label


def fill(name, labels):
    """substitute {slot: text} into the template. unknown keys ignored, missing
    slots keep their placeholder. returns valid d2 by construction."""
    tpl = PATTERNS[name]["d2"]

    def norm(k):
        return str(k or "").replace("\\n", "\n").replace("\n", " ").strip().lower()

    by_norm = {norm(k): k for k in slots(name)}
    sub = {}
    for k, v in (labels or {}).items():
        if not str(v or "").strip():
            continue
        real = by_norm.get(norm(k))
        if real is not None:
            sub[real] = _clean(v)
    if not sub:
        return tpl

    def rep(m):
        lab = m.group(1)
        return '"%s"' % sub.get(lab, lab)

    return _LABEL_RE.sub(rep, tpl)


def slot_block():
    """the per-pattern slot listing for the planner prompt."""
    lines = []
    for name in sorted(PATTERNS):
        e = PATTERNS[name]
        lines.append("- %s  (%s)" % (name, e["move"]))
        lines.append("    when: %s" % e["when"])
        lines.append("    labels: %s" % json.dumps(slots(name), ensure_ascii=False))
    return "\n".join(lines)
