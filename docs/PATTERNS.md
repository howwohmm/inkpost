# patterns

There are eleven patterns. Each one is a d2 template that draws one essay move.
The planner picks 2 to 4 of them per post and fills their labels with the
author's own sentences.

A pattern's **slots** are the quoted labels in its template, in source order,
deduped. `patterns.slots(name)` derives them from the template — there is no
separate slot list to keep in sync. Style values like `"#ffe8a3"` are skipped,
so only real labels are exposed. Print them yourself:

```
python3 -c "import patterns; print(patterns.slots('collapse'))"
```

Slot keys are matched loosely. `patterns.fill()` lowercases them, strips
whitespace and turns `\n` into a space before comparing, so a model that returns
`"The Open Field"` still lands in the `the open field` slot. Unknown keys are
ignored. A slot nobody filled keeps its placeholder text.

`\n` inside a slot key or value is a literal backslash-n, which is how d2 writes
a line break inside a label.

Ten templates also exist as files in `patterns/`, byte-identical to the strings
in `patterns.py`. `taxonomy` is the exception: its template file is
`examples/src/03-deadline-three-urgencies.d2`.

Every pattern except `committee` carries an accent — the yellow fill. It marks
the point of the diagram, and the renderer recolours it per mode. Usually there
is exactly one accent node; `collapse` and `taxonomy` deliberately use the fill
twice, because one concept appears in two places.

---

## contrast

**move** — messy thing vs clean thing
**when** — the post sets a tidy or imagined version against the real, lumpy one.
**layout** `tala` · **accent** yes · **gif** no

Two containers side by side. The left one is a straight line from input to
output. The right one is a hub with detours looping back into it, ending at the
thing that actually got made.

**notes** — `done` is the accent — the thing that actually got made. 2 to 4
detours.

**slots**

```
"the tidy version"
"input"
"glassy output"
"the real version"
"start"
"detour"
"doubt"
"type"
"the thing\n(lumpy on purpose)"
"back again"
"leave it anyway"
"no friction = no fingerprints."
```

`"back again"` and `"leave it anyway"` are edge labels. The last slot is the
caption pinned bottom-centre.

---

## collapse

**move** — many options → one path
**when** — the post names a pile of choices and then the one thing that kills
them all.
**layout** `tala` · **accent** yes · **gif** no

An edgeless container of options above a single-file hallway below, with one
loud edge between them.

**notes** — NEVER put an arrow inside `field`. the edgeless container is exactly
what makes tala scatter it into an open field. 4 to 8 options. `me` is one
concept in two places, so it is yellow in both. the field -> hallway edge label
is the loudest sentence in the diagram — give it the strongest clause the post
has about the collapsing force.

**slots**

```
"the open field"
"option"
"another option"
"the meta-option"
"the guilt"
"the question"
"the rabbit hole"
"me"
"the hallway"
"the task"
"the clock"
"the thing that collapses it"
```

`"me"` appears in both containers and is one slot, so filling it changes both.
`"the thing that collapses it"` is the edge label between the two.

---

## test

**move** — a yes/no that sorts the world
**when** — the post proposes one question that separates people or things.
**layout** `dagre` · **accent** yes · **gif** no

A thing, a diamond, two answers.

**notes** — the accent goes on the answer the post is actually FOR, which is
often the one reached by "no". keep the question 2 to 4 lines and end it with a
?.

**slots**

```
"the thing"
"the question\nthat sorts it?"
"one answer."
"the other answer."
"yes"
"no"
```

`"the other answer."` is the accent node. `"yes"` and `"no"` are the two edge
labels and are usually left alone.

---

## layers

**move** — outer thing hides inner thing
**when** — the post says what looks like the point is not the point.
**layout** `tala` · **accent** yes · **gif** no

Three nested boxes with the real thing innermost, plus an optional dashed aside.

**notes** — 3 to 5 details. the `#f4f4f4` on the middle layer is not the accent,
leave it. the note is optional; drop both its lines if the post has no aside.

**slots**

```
"what people think it is"
"the visible layer"
"the real thing"
"detail one"
"detail two"
"detail three"
"takes years. invisible while forming."
```

---

## collage

**move** — many inputs → one self
**when** — the post is about being assembled out of things you did not choose.
**layout** `tala` · **accent** yes · **gif** no

A scatter of inputs feeding a cloud, which narrows through a filter to one
question.

**notes** — 5 to 8 inputs, and one `inputs.iN -> self` line per input — add or
remove BOTH together. repeating a word across inputs is fine. `free` ends in a
?.

**slots**

```
"things i didn't choose"
"input"
"“my” thing"
"strip the noise"
"the real question?"
```

Only five slots for a template with five input nodes, because `slots()` dedupes
and all five inputs share the label `"input"`. Filling `"input"` therefore sets
all of them to the same text. To give each input its own words you have to edit
the template or the generated source — which is exactly what the `claude-code`
backend does, since it writes the d2 itself rather than filling slots.

---

## loop-exit

**move** — a cycle + the one exit
**when** — the post describes a loop the author keeps running, and the thing
that breaks it.
**layout** `dagre` · **accent** yes · **gif** no

A chain of steps with a dashed back-edge, plus one hexagon that leaves the loop.

**notes** — 3 to 5 steps; the LAST step is the felt cost, the thing that hurts.
keep the back-edge dashed. the note is optional and usually carries the reframe.

**slots**

```
"the condition"
"step one"
"step two"
"step three"
"feel bad about it"
"again"
"the real consequence"
"execution mode."
"this isn't laziness. it's rational."
```

`"again"` is the back-edge label. The last slot is the italic note.

---

## committee

**move** — a dialogue with yourself
**when** — the post quotes an internal argument.
**layout** `dagre` (inert) · **accent** no · **gif** no

A d2 sequence diagram between you, the voice in your head, and the outside
pressure. `shape: sequence_diagram` brings its own layout engine, so the
`--layout` flag does nothing here.

**notes** — this pattern has NO yellow node and NO caption — `near:` does not
work inside a sequence diagram and there is no shape to fill. the emphasis beat
is `{style.bold: true}` on EXACTLY ONE message: the outside pressure landing. 5
to 10 messages. `me -> me` is self-talk and one beat should be it.

**slots**

```
"me"
"the internal committee"
"the clock"
"should i start?"
"are you even ready?"
"which version though?"
"reorganise notion instead"
"12 hours left."
"(silence)"
"one sitting. something decent."
```

The first three are the actors. The rest are messages in order.

---

## comic

**move** — a diary sequence
**when** — the post walks through a day or an episode in order.
**layout** `dagre` (inert) · **accent** yes · **gif** no

Six panels in a 2×3 grid. `grid-rows` / `grid-columns` is its own engine, so the
`--layout` flag does nothing here either.

**notes** — NEVER write a `direction:` line here — it fights the grid. exactly 6
panels (2 x 3); a different count leaves empty cells. keep width/height on every
panel. one middle panel may keep the dots fill as the avoidance beat. the LAST
panel is the accent. 2 to 4 short lines per panel.

**slots**

```
"panel one.\nthe boring start."
"panel two.\nthe small mess."
"panel three.\nthe stall."
"panel four.\nthe avoidance."
"panel five.\nthe grind."
"panel six.\nthe thing."
```

---

## poster

**move** — one line that carries a post
**when** — the post has no structure, only one great sentence. this is the
fallback.
**layout** `dagre` · **accent** yes · **gif** no

A big two-line quote over a three-node diagram, with a signature bottom right.

**notes** — the title is the author's verbatim line split over exactly 2 lines.
font-size 44 and 18 are inside d2's 8..100 limit — do not raise them. `b` is the
accent: the durable force, the one that compounds. the `sig` node is a
placeholder signature — put the author's own site or name there if the post gives
you one, otherwise leave the node exactly as it is.

**slots**

```
"the line.\nthe second half of the line."
"this"
"that"
"you"
"carries"
"compounds"
"— yoursite.com"
```

`"carries"` and `"compounds"` are edge labels. Fill the signature slot with your
own name or site, or edit the template so you do not have to think about it.

---

## steps

**move** — reveal one idea at a time
**when** — the post builds an argument that only works in order. renders as a
gif.
**layout** `dagre` · **accent** yes · **gif** **yes**

A multi-board source. Board 1 holds the root alone; each later board adds one
node. `d2 --animate-interval` turns that into a GIF. This is the only pattern
with `gif: True`, and asking for `-f gif` on any other pattern silently skips
the job.

Multi-board sources need `--target steps.<N>` for a still image, where `N` is
the highest board number. The renderer parses that out of the source rather than
assuming it, and the GIF export takes no target at all.

**notes** — board 1 introduces the root alone. each later board adds ONE node
plus its edge and refers to earlier keys by bare name. number the boards 1..N
with no gaps — the tool reads the highest number to render the finished still. 5
or 6 boards. the LAST board carries the accent.

**slots**

```
"the condition"
"step one"
"step two"
"feel bad about it"
"again"
"the consequence"
"execution."
```

---

## taxonomy

**move** — kinds of a thing, ranked
**when** — the post enumerates two or three KINDS of something and ranks them.
this is the only pattern for an essay that lists rather than flows.
**layout** `tala` · **accent** yes · **gif** no

Three columns of prose, ranked left to right, with a two-oval summary underneath.
This is the only pattern for an essay that lists instead of flowing.

**notes** — exactly 3 kinds. each column is a title line, a blank line (`\n\n`),
then 3 to 6 short lines of their prose — no more, it overflows. the THIRD kind is
the accent and so is the second summary oval: one concept, ranked and then
named. the two edge labels are single comparative words.

**slots**

Unlike the other ten templates, taxonomy's placeholders are not generic — they
are the full verbatim text of the essay it was cut from. They read as finished
prose because they are. A run replaces all of them.

```
"imported urgency\n\nsomeone else sets the deadline.\nclient. boss. exam.\n\nefficient but fragile.\nif the structure disappears,\nso does the productivity."
"manufactured urgency\n\nyou create the stakes.\nship in public. tell people.\nyour brain knows it's fake…\n\nbut this is how agency starts."
"no urgency at all\n\nbuild because it's interesting.\nwrite because you have\nsomething to say.\nno dopamine hit. no relief.\n\nthe slow, compounding 1%."
"harder"
"hardest"
"responsive.\nsurvives."
"self-directed.\nbuilds."
"pressure borrows energy from the future.\ndiscipline builds it from systems."
```

The first three are the columns. `"harder"` and `"hardest"` are the edge labels
between them. The last three are the summary ovals and the edge between them.
