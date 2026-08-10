"""Generate a Potato annotation project from `config/taxonomy.yaml`.

Potato (`davidjurgens/potato`, "the portable annotation tool") is the
annotation UI for Phase 11. **It is not vendored.** This module emits a project
directory -- a `config.yaml` plus data files -- that a separately-installed
Potato serves. `src/annotation/ingest.py` reads its output back.

## Why generate the config instead of writing it by hand

The rubric is `config/taxonomy.yaml`, which is locked at v2 and frozen at Phase
12. A hand-written annotation UI is a second copy of it that drifts: someone
edits an edge case in the taxonomy, the UI still shows the old label set, and
the resulting gold set is annotated against a rubric that no longer exists.
Generating means the taxonomy stays the single source of truth, and a test
asserts every construct reaches the screen.

## The layout, and the two decisions inside it

**A `span` scheme carries construct identity; `radio` schemes carry intensity.**
Potato spans do not hold a magnitude, so the two halves of a label are captured
by two mechanisms. Span labels are `construct` for the six graded constructs and
`construct:pole` for the four categorical ones, which is what makes the
categorical pole span-anchored -- guidelines sec.2b requires a span for *each*
pole when `mixed` is used, and that is unrepresentable with a single label per
construct.

**Context is a `pure_display` scheme, not the annotated text.** The target
utterance is Potato's `text`, so span offsets land on the utterance and stay
comparable with `InterimRecord.char_start/char_end`, with
`SilverLabel.evidence_spans`, and with whatever Phase 16 highlights. The parent
record is displayed read-only above it. This is the fix for the defect described
in `src/annotation/context.py`: the annotator can follow guidelines sec.3 step 1
without the unit of annotation changing.

## Annotation burden, stated up front because it is a real risk

Ten constructs means ten intensity questions plus a span pass, per item, per
annotator. Over 400 `gold_eval` items that is a large ask, and `CLAUDE.md` sec.3
schedules exactly this check: *"FINAL CONSTRUCT SET IS FROZEN AT PHASE 12, after
checking annotation burden and inter-annotator agreement."*

The generator therefore supports `--graded-only` and a `constructs` filter so
the burden can be **measured on `gold_dev` first** and the taxonomy trimmed with
evidence rather than by feel. Do not guess the burden; time the calibration pass.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from .context import AnnotationItem

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_ROOT = REPO_ROOT / "annotation"

#: Potato's config validator requires exactly these top-level keys, plus one of
#: `data_files` / `data_directory` / `data_sources`. Read from
#: `potato/server_utils/config_module.py` in potato-annotation 2.7.1 rather than
#: inferred from a tutorial, because a config that fails validation fails at
#: launch, in front of the annotator.
REQUIRED_CONFIG_KEYS = (
    "item_properties",
    "task_dir",
    "output_annotation_dir",
    "annotation_task_name",
)

#: Pinned. Potato is a research tool under active development and its scheme
#: registry changes; `docs/annotation_tooling.md` records why reproducing the
#: annotation environment matters for the artifact.
POTATO_VERSION = "2.7.1"

INTENSITY_LABELS = ["0 none", "1 mild", "2 moderate", "3 strong"]


def _graded(spec: dict[str, Any]) -> bool:
    return not spec.get("labels")


def span_labels(taxonomy: dict[str, Any], constructs: Sequence[str] | None = None) -> list[dict]:
    """Span label set: one entry per graded construct, one per categorical pole.

    `mixed` and `none` are deliberately absent from the span labels. `mixed` is
    recorded by marking a span for each pole, which is what guidelines sec.2b
    actually asks for; a `mixed` span would let an annotator assert co-presence
    without evidencing either side. `none` is the absence of a span.
    """
    out: list[dict] = []
    for name, spec in (taxonomy.get("constructs") or {}).items():
        if constructs and name not in constructs:
            continue
        if _graded(spec):
            out.append({"name": name, "tooltip": _tooltip(spec)})
        else:
            for pole in spec.get("labels", []):
                if pole in ("none", "mixed"):
                    continue
                out.append({"name": f"{name}:{pole}", "tooltip": _tooltip(spec)})
    return out


def _tooltip(spec: dict[str, Any]) -> str:
    return " ".join(str(spec.get("definition", "")).split())[:240]


def build_config(
    *,
    task_name: str,
    data_file: str,
    output_dir: str,
    task_dir: str,
    taxonomy: dict[str, Any],
    port: int = 8000,
    constructs: Sequence[str] | None = None,
    annotators: Sequence[str] = (),
) -> dict[str, Any]:
    """Assemble a validated Potato config for one batch."""
    schemes: list[dict[str, Any]] = [
        {
            "annotation_type": "pure_display",
            "name": "context",
            "description": (
                "FULL RECORD (read this first -- guidelines sec.3 step 1). "
                "The highlighted sentence is the one you are labelling. "
                "Do not label the rest; it is context only."
            ),
            "label_requirement": {"required": False},
            "allow_html": True,
        },
        {
            "annotation_type": "span",
            "name": "evidence",
            "description": (
                "Mark the MINIMAL span that carries the evidence, then pick its "
                "construct. Spans may overlap and one span may carry several "
                "constructs. Leave empty if nothing is expressed."
            ),
            "labels": span_labels(taxonomy, constructs),
            "show_span_labels": True,
            "bad_text_label": {
                "label_content": (
                    "ESCALATE -- unreadable, off-topic, not pre-competition, or "
                    "identifying information survived de-identification"
                )
            },
        },
    ]

    for name, spec in (taxonomy.get("constructs") or {}).items():
        if constructs and name not in constructs:
            continue
        schemes.append(
            {
                "annotation_type": "radio",
                "name": f"intensity_{name}",
                "description": f"{name} -- intensity of the strongest evidence present",
                "labels": INTENSITY_LABELS,
                "label_requirement": {"required": False},
                "horizontal": True,
                "tooltip": _tooltip(spec),
            }
        )

    schemes.extend(
        [
            {
                "annotation_type": "radio",
                "name": "interpretation_modifier",
                "description": (
                    "ONLY if cognitive_anxiety or somatic_anxiety is >= 1: does the "
                    "athlete read the arousal as helpful or harmful? Default unclear."
                ),
                "labels": ["facilitative", "debilitative", "unclear"],
                "label_requirement": {"required": False},
                "horizontal": True,
            },
            {
                "annotation_type": "multiselect",
                "name": "flags",
                "description": "Flags (guidelines sec.2d and sec.7)",
                "labels": [
                    "low_resilience_explicit -- text states fragility ('one mistake and I'm done')",
                    "uncertain -- I labelled it but would not defend it",
                ],
                "label_requirement": {"required": False},
            },
            {
                "annotation_type": "text",
                "name": "note",
                "description": (
                    "Optional note. Describe the LANGUAGE, never the person -- no "
                    "clinical terms (guidelines sec.0 rule 2)."
                ),
                "textarea": {"rows": 2, "cols": 60},
                "label_requirement": {"required": False},
            },
        ]
    )

    config: dict[str, Any] = {
        "annotation_task_name": task_name,
        "port": port,
        "task_dir": task_dir,
        "data_files": [data_file],
        "item_properties": {
            "id_key": "id",
            "text_key": "text",
        },
        "list_as_text": {"text_list_prefix_type": None},
        "annotation_schemes": schemes,
        "output_annotation_dir": output_dir,
        "output_annotation_format": "jsonl",
        "annotation_codebook_url": "docs/annotation_guidelines.md",
        "user_config": {
            # Closed roster, not open sign-up. Agreement is a property of a
            # known pair of people; an unexpected third login would silently
            # add a third annotator with a partial pass.
            "allow_all_users": False,
            "users": list(annotators),
        },
        "alert_time_each_instance": 10000000,
        # No `html_layout` key. An earlier draft set one, and Potato 2.7.1's own
        # validator rejected it as unrecognised ("did you mean 'task_layout'?").
        # It was a carry-over from an older Potato API, pointing at a template
        # this project does not ship. The default layout renders every scheme we
        # use, so the right fix was to delete the key rather than invent a
        # template to justify it -- and running `python -m potato.validate_cli`
        # is how it was found, which is why `scripts/run_annotation.py --build`
        # tells you to run it.
        "surveyflow": {"on": False},
    }

    missing = [k for k in REQUIRED_CONFIG_KEYS if k not in config]
    if missing:  # pragma: no cover - guards against an edit above
        raise ValueError(f"generated config is missing required Potato keys: {missing}")
    return config


def write_project(
    items: Sequence[AnnotationItem],
    *,
    batch: str,
    taxonomy: dict[str, Any],
    root: Path | None = None,
    port: int = 8000,
    constructs: Sequence[str] | None = None,
    annotators: Sequence[str] = (),
) -> dict[str, Path]:
    """Write a runnable Potato project for one batch. Returns the paths written.

    The data file is written **once and shared by both annotators**. Potato
    keys its output by user, so two people annotating the same file produce two
    independent output directories over an identical item set -- which is
    exactly the 100% double annotation the kappa needs. Splitting the data per
    annotator would produce two disjoint passes and no agreement at all.
    """
    project_root = (root or DEFAULT_PROJECT_ROOT) / batch
    (project_root / "data").mkdir(parents=True, exist_ok=True)
    (project_root / "annotation_output").mkdir(parents=True, exist_ok=True)

    data_path = project_root / "data" / f"{batch}.jsonl"
    with data_path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item.to_potato_row(), ensure_ascii=False) + "\n")

    config = build_config(
        task_name=f"sports-risk-nlp {batch}",
        data_file=f"data/{batch}.jsonl",
        output_dir="annotation_output/",
        task_dir=str(project_root),
        taxonomy=taxonomy,
        port=port,
        constructs=constructs,
        annotators=annotators,
    )
    config_path = project_root / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    readme_path = project_root / "README.md"
    readme_path.write_text(_readme(batch, len(items), port), encoding="utf-8")

    return {"config": config_path, "data": data_path, "readme": readme_path}


def _readme(batch: str, count: int, port: int) -> str:
    return f"""\
# Potato annotation project -- `{batch}`

Generated from `config/taxonomy.yaml` by `scripts/run_annotation.py --build`.
**Do not edit this directory by hand** -- regenerate it. It is derived from the
taxonomy, and a hand-edit is a second copy of the rubric that will drift.

{count} items. Every annotator labels **all** of them: 100% double annotation is
what makes a per-construct kappa computable.

## Run it

```bash
pip install potato-annotation=={POTATO_VERSION}
potato start config.yaml -p {port}
```

Open <http://localhost:{port}>, log in with **your own annotator id** from
`config/annotators.yaml`, and keep `docs/annotation_guidelines.md` open beside
you. Do not annotate from memory.

## The two rules that make this worth doing

1. **Do not discuss specific records with the other annotator until both passes
   are finished.** Guidelines sec.7. Discussing them inflates agreement and
   makes the statistic worthless -- and it cannot be undone afterwards.
2. **Do `gold_dev` first, argue about the rubric, amend
   `docs/annotation_guidelines.md`, and only then start `gold_eval`.**
   `gold_dev` is drawn from training-side templates precisely so that burning it
   on rubric arguments costs zero evaluation power.

## When you are done

```bash
python scripts/run_annotation.py --ingest --batch {batch} --annotator <your-id>
```

That validates every span against its utterance and writes your pass to
`data/gold/{batch}/<your-id>.jsonl`. It refuses to overwrite an existing pass.
"""
