"""Phase 33 cartographer -- regenerates `docs/PROJECT_MAP.md` from the repo itself.

    python scripts/build_project_map.py
    python scripts/build_project_map.py --out docs/PROJECT_MAP.md
    python scripts/build_project_map.py --json reports/project_map.json

Structural only: stdlib `ast` plus literal path matching. No LLM, no network, no
subagents. Every edge it draws is one a reader can verify by grep, which is the
property that makes the isolated-file list safe to act on.

Unlike the `run_*.py` runners there is no `src/` counterpart, deliberately. This
measures the repository rather than the project's subject matter, so putting the
logic under `src/` would make the shipped package depend on the shape of its own
checkout. The consequence is that it carries no unit test; its output is checked
by reading it.

WHAT AN EDGE MEANS HERE. A -> B means file A names file B, by import or by path.
It does NOT mean B is unused if nothing points at it: a file referenced only by
its *directory* (`reports/predictions/`) or read by an external tool (a `.gitkeep`,
an IDE setting, a deploy script) has zero inbound edges and is still load-bearing.
That is why `classify()` sorts the isolated set by KIND and refuses to call
anything junk.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TEXTUAL = {
    ".md",
    ".txt",
    ".py",
    ".yaml",
    ".yml",
    ".toml",
    ".html",
    ".json",
    ".ps1",
    ".ipynb",
    ".cfg",
    ".train",
    ".bib",
}
# Basenames too common to attribute a reference to one file.
AMBIGUOUS = {"__init__.py", "README.md", ".gitkeep", "conftest.py", "settings.yaml"}
MIN_BASENAME = 5


def tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=REPO, text=True)
    return [line for line in out.splitlines() if line]


def read(path: str) -> str | None:
    full = REPO / path
    if not full.is_file():
        return None
    try:
        return full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def module_index(files: list[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for f in files:
        if f.endswith(".py"):
            mod = f[:-3].replace("/", ".")
            index[mod] = f
            if mod.endswith(".__init__"):
                index[mod.removesuffix(".__init__")] = f
    return index


def resolve(dotted: str, index: dict[str, str]) -> str | None:
    """Longest-prefix match of a dotted import onto a tracked module."""
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        hit = index.get(".".join(parts[:i]))
        if hit:
            return hit
    return None


def python_imports(f: str, text: str, index: dict[str, str]) -> set[tuple[str, str]]:
    """Intra-repo import edges. Covers test->src and page->src.dashboard."""
    try:
        tree = ast.parse(text, filename=f)
    except SyntaxError:
        return set()
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hit = resolve(alias.name, index)
                if hit:
                    found.add((hit, "py-import"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = os.path.dirname(f).replace("/", ".")
                if node.level > 1:
                    base = ".".join(base.split(".")[: -(node.level - 1)])
                stem = f"{base}.{node.module}" if node.module else base
            else:
                stem = node.module or ""
            hit = resolve(stem, index)
            if hit:
                found.add((hit, "py-import"))
            for alias in node.names:
                hit = resolve(f"{stem}.{alias.name}", index)
                if hit:
                    found.add((hit, "py-import"))
    return found


def kind_of(src: str, dst: str) -> str:
    sext, dext = Path(src).suffix, Path(dst).suffix
    if sext == ".py":
        if dext in (".yaml", ".yml"):
            return "code-config"
        if dext == ".jsonl":
            return "code-data"
        if src.startswith("scripts/") and dst.startswith("reports/"):
            return "script-report"
        return "code-ref"
    if sext in (".md", ".txt"):
        return "doc-ref"
    return "manifest-ref"


def build_edges(files: list[str], exclude_sources: frozenset[str]) -> set[tuple[str, str, str]]:
    """Every A -> B where A names B.

    `exclude_sources` keeps this script's own output out of the graph. Without
    it the map destroys the measurement it reports: the previous run listed
    every isolated file by name, so the next run reads that listing as an
    inbound edge and finds almost nothing isolated. A catalogue of files is not
    a consumer of them.
    """
    index = module_index(files)
    by_basename: dict[str, list[str]] = defaultdict(list)
    for f in files:
        by_basename[os.path.basename(f)].append(f)

    texts: dict[str, str] = {}
    for f in files:
        if f in exclude_sources:
            continue
        if Path(f).suffix in TEXTUAL or Path(f).name.startswith("Dockerfile"):
            text = read(f)
            if text is not None:
                texts[f] = text

    edges: set[tuple[str, str, str]] = set()
    for f, text in texts.items():
        if f.endswith(".py"):
            for dst, kind in python_imports(f, text, index):
                if dst != f:
                    edges.add((f, dst, kind))
        # literal repo-relative path, the least ambiguous signal
        for dst in files:
            if "/" in dst and dst != f and dst in text:
                edges.add((f, dst, kind_of(f, dst)))
        # distinctive basename
        for base, candidates in by_basename.items():
            if base in AMBIGUOUS or len(base) < MIN_BASENAME or base not in text:
                continue
            for dst in candidates:
                if dst != f:
                    edges.add((f, dst, kind_of(f, dst)))
    return edges


def classify(path: str) -> tuple[str, str]:
    """(kind, verdict) for a file with no inbound edge. Verdict is never 'delete'."""
    name = os.path.basename(path)
    if name == ".gitkeep":
        return (
            "directory placeholder",
            "keep -- zero-degree by design; it is what puts the directory in a clone",
        )
    if name.startswith(".fuse_hidden"):
        return (
            "editor crash artifact",
            "remove -- a stale snapshot of a live file; gitignored since Phase 33",
        )
    if (
        re.match(r"^(handover_|phase\d)", name)
        or path.startswith(".claude/PRPs/")
        or re.match(r"^docs/phase\d", path)
    ):
        return (
            "provenance / audit trail",
            "keep -- nothing imports the record of what was decided and why",
        )
    if path.startswith("reports/predictions/"):
        return (
            "committed reproducibility cache",
            "keep -- tier B of docs/reproducibility.md; referenced by directory, never by name",
        )
    if path in ("README.md", "src/__init__.py") or path.startswith(".vscode/"):
        return ("entry point", "keep -- read from outside the graph, not from inside it")
    if path.startswith("scripts/"):
        # None of the runners are imported; they are invoked by a person or a
        # runbook. A scripts/ file being isolated says nothing about whether it
        # is used -- see the sync-dashboard.ps1 caution in the generated map.
        return (
            "operator tooling",
            "keep -- run by a human, never imported; see the cautions above",
        )
    return ("unclassified", "ASK -- no rule explains this one; a human should look")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/PROJECT_MAP.md")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    files = tracked_files()
    generated = frozenset(p for p in (args.out, args.json_out) if p)
    edges = build_edges(files, generated)

    inbound: dict[str, set[str]] = {f: set() for f in files}
    outbound: dict[str, set[str]] = {f: set() for f in files}
    for s, d, _ in edges:
        inbound[d].add(s)
        outbound[s].add(d)

    by_kind: dict[str, int] = defaultdict(int)
    for _, _, k in edges:
        by_kind[k] += 1

    isolated = sorted(f for f in files if not inbound[f])
    groups: dict[str, list[str]] = defaultdict(list)
    verdicts: dict[str, str] = {}
    for f in isolated:
        kind, verdict = classify(f)
        groups[kind].append(f)
        verdicts[kind] = verdict

    hubs = sorted(files, key=lambda f: len(inbound[f]), reverse=True)[:15]
    areas: dict[str, int] = defaultdict(int)
    for f in files:
        areas[f.split("/")[0] if "/" in f else "(repo root)"] += 1

    lines: list[str] = []
    w = lines.append
    w("# Project map")
    w("")
    w(
        f"**Generated {date.today().isoformat()} by `scripts/build_project_map.py`.** "
        f"{len(files)} tracked files, {len(edges)} edges, "
        f"{len(isolated)} with no inbound edge."
    )
    w("")
    w("## Regenerating this file")
    w("")
    w("```bash")
    w("python scripts/build_project_map.py")
    w("```")
    w("")
    w(
        "Structural only -- stdlib `ast` plus literal path matching. No LLM, no network, "
        "no subagents, so it is free to re-run and its every edge is grep-checkable. "
        "Re-run it after any change that adds, deletes or renames a tracked file; the "
        "counts above are the file's own freshness check."
    )
    w("")
    w("## What an edge means, and what it does not")
    w("")
    w(
        "`A -> B` means **file A names file B**, by Python import or by path. It does "
        "*not* follow that B is unused when nothing names it. Three kinds of live file "
        "carry zero inbound edges by construction:"
    )
    w("")
    w("* files referenced by **directory** rather than by name -- `reports/predictions/*.json`;")
    w(
        "* files read by something **outside the repo** -- a `.gitkeep`, an IDE setting, "
        "a deploy script;"
    )
    w("* the **record of decisions** -- handovers, phase prompts, plans. Nothing imports history.")
    w("")
    w(
        "An isolated-file sweep that ignored this would delete the project's audit trail "
        "and its reviewer-facing reproducibility cache. That is why the table below sorts "
        "by kind, and why `classify()` cannot return a delete verdict."
    )
    w("")
    w("## Edges by kind")
    w("")
    w("| Kind | Count | Meaning |")
    w("|---|---:|---|")
    meanings = {
        "py-import": "Python import between tracked modules "
        "(includes test->src, page->src.dashboard)",
        "doc-ref": "a doc or handover naming another tracked file",
        "code-ref": "Python naming a tracked non-config file",
        "manifest-ref": "packaging or config file naming a tracked path",
        "code-config": "Python naming a tracked `*.yaml`",
        "code-data": "Python naming a tracked `*.jsonl`",
        "script-report": "a `scripts/` runner naming its output under `reports/`",
    }
    for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        w(f"| `{k}` | {n} | {meanings.get(k, '')} |")
    w("")
    w("## Areas")
    w("")
    w("| Area | Tracked files |")
    w("|---|---:|")
    for a, n in sorted(areas.items(), key=lambda kv: -kv[1]):
        w(f"| `{a}` | {n} |")
    w("")
    w("## Most-referenced files")
    w("")
    w("The repo's structural hubs -- change one and the blast radius is the count beside it.")
    w("")
    w("| File | Inbound | Outbound |")
    w("|---|---:|---:|")
    for f in hubs:
        w(f"| `{f}` | {len(inbound[f])} | {len(outbound[f])} |")
    w("")
    w("## Two standing cautions")
    w("")
    w(
        "These are written here rather than derived, because neither is visible in the "
        "edge counts and both were found by reading. Keep them in this file; a hand-edit "
        "elsewhere would be erased by the next regeneration."
    )
    w("")
    w("### `scripts/sync-dashboard.ps1` is load-bearing, not dead")
    w("")
    w(
        "It has zero inbound edges *and* no mention anywhere in the repo, which is the "
        "signature of dead code. It is the opposite. It is the deployment mechanism: it "
        "copies a named subset of this repo into the public `srn-dashboard` repo that "
        "feeds Streamlit Community Cloud, then commits and pushes. Its comments are the "
        "**only** written record of two things:"
    )
    w("")
    w(
        "* **What is deliberately public.** Mirroring all of `src/` was quietly "
        "publishing the whole research tree -- `src/agents` (the OpenRouter routing "
        "layer), `src/annotation`, `src/labeling`, `src/reproducibility`, `src/security`, "
        "`src/taxonomy` -- into a public repository. Found by reading a dry run on "
        "2026-09-15. The named-package list is the fix."
    )
    w(
        "* **Why `packages.txt` is required.** Dropping it from a sync breaks the photo "
        "path *silently*: the app starts healthy, shows the uploader, and refuses every "
        "photo. Correct behaviour, indistinguishable from the feature being broken."
    )
    w("")
    w(
        "Deleting it would delete the public/private boundary along with it. The real "
        "defect is that nothing documents it -- fix that, not the file."
    )
    w("")
    w("### `.claude.md` and `CLAUDE.md` both claim to be the single source of truth")
    w("")
    w(
        "Both are tracked. Both open with the same sentence. `.claude.md` was last "
        "updated at Phase 21 (`aee3711`); `CLAUDE.md` is current through Phase 30 and "
        "beyond. They are roughly 600 lines apart, and the string `.claude.md` appears "
        "in about twenty files including `src/dashboard/theme.py`, "
        "`tests/test_dashboard_pages.py` and three dashboard pages."
    )
    w("")
    w(
        "An agent told to read the single source of truth can land on the Phase-21 copy "
        "-- including its stale sec.11.3 flag default, which `CLAUDE.md` has since "
        "corrected. No file is being changed on the strength of this note; it is recorded "
        "so the next reader does not have to rediscover it."
    )
    w("")
    w("## Files with no inbound edge")
    w("")
    if not isolated:
        w("None.")
        w("")
    for kind in sorted(groups):
        w(f"### {kind} -- {len(groups[kind])} file(s)")
        w("")
        w(f"*{verdicts[kind]}*")
        w("")
        for f in groups[kind]:
            w(f"* `{f}`")
        w("")

    # Exactly one trailing newline. The sections above each end with a blank
    # line for readability, which leaves a stray one at the end; pre-commit's
    # end-of-file-fixer would strip it and fail the commit on every regeneration.
    while lines and not lines[-1]:
        lines.pop()

    out_path = REPO / args.out
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(files)} files, {len(edges)} edges, {len(isolated)} isolated")

    if args.json_out:
        payload = {
            "generated": date.today().isoformat(),
            "tracked": len(files),
            "edges_by_kind": dict(by_kind),
            "isolated": dict(groups),
            "inbound_counts": {f: len(inbound[f]) for f in files},
        }
        (REPO / args.json_out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
