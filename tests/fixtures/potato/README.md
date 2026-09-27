# Recorded Potato 2.7.1 output - test fixtures

**These are not gold labels and must never be treated as any.** They are a
*rehearsal*: five `gold_dev` items annotated by a script so that
`src/annotation/potato_output.py` and `src/annotation/ingest.py` can be tested
against Potato's real serialisation instead of an assumed one. The judgements
in them are arbitrary and psychologically meaningless.

## How they were produced, and why it matters that they were not hand-written

`user_state.json` was written by **Potato 2.7.1's own `UserState.save()`**,
against the real `annotation/gold_dev/data/gold_dev.jsonl` items, using
`potato.item_state_management.Label` and `SpanAnnotation`. `annotations.jsonl`
was produced by Potato's own `potato.export.cli.load_annotations_from_output_dir`
in the shape `potato.export.tabular_exporter.JSONLExporter` writes.

Nothing here was typed by hand. That is the whole point: OPEN-027 existed
because the parser had only ever been tested against fixtures written by the
same person who wrote the parser, which cannot detect a wrong assumption about
the tool. A recorded artifact from the real library can, and did - see
`docs/annotation_tooling.md` §8.

## Why record the artifact instead of depending on Potato in the test suite

`potato-annotation` pulls in a Flask server and a large dependency tree. Making
it a test dependency to generate three files on every run would slow the suite
and give CI a network-shaped failure mode, for no extra signal: the bytes are
what the parser has to survive, and the bytes are here. `POTATO_VERSION` in
`src/annotation/potato_project.py` pins the version these were recorded from.
**If that pin is raised, regenerate these fixtures** - the schema changed once
already between the version the parser was written against and 2.7.1.

## Contents

| Path | What |
|---|---|
| `annotation_output/A1/user_state.json` | annotator pass, Potato's authoritative artifact |
| `annotation_output/A2/user_state.json` | a second pass over the same items, deliberately disagreeing |
| `export/annotations.jsonl` | the same two passes via Potato's JSONL exporter |
| `items.jsonl` | the five `gold_dev` items the passes refer to |
