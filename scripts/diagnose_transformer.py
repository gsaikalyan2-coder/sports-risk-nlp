#!/usr/bin/env python
"""Isolate where the Phase 14 fine-tune dies.

    python scripts/diagnose_transformer.py
    python scripts/diagnose_transformer.py --base-model roberta-base

Why this script exists
----------------------
On 2026-08-11 both `run_transformer.py --epochs 1` and `--sweep` exited on the
owner's Windows machine immediately after the weight-load report, printing no
macro-F1, no traceback, and no error. A Python exception would have printed a
stack trace, so the process was terminated below the Python level -- a native
crash, an OS kill, or an `abort()` from a C extension. None of those produce a
message Python can catch and report.

The training loop cannot diagnose itself in that situation, because the
diagnostic output dies with the process. So this script walks the same sequence
in the smallest possible steps, flushing after every one. Whatever the last line
printed is, the next step is the one that killed it.

The steps, in order, matching what `TransformerBaseline.fit` actually does:

    1. import torch                     (native library load -- OpenMP conflicts show here)
    2. import transformers
    3. environment report               (versions, threads, RAM)
    4. load tokenizer                   (DeBERTa-v3 = sentencepiece; needs protobuf)
    5. tokenize a few records           (conversion failures show here)
    6. load model + head
    7. one forward pass                 (batch of 2)
    8. one backward pass                (batch of 2)
    9. one forward+backward at full batch size and length  <- most likely OOM point
   10. tokenize the whole training set  <- the other likely memory point

Every step is wrapped so a *Python-level* failure is reported with its traceback
rather than ending the run. A step that ends the process with no output at all is
a native crash, and the script says so explicitly at the end.

This script trains nothing and writes nothing. It is safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STEP = 0


def step(label: str) -> None:
    """Announce a step *before* attempting it, and flush.

    The flush is the entire point. Python buffers stdout when it is not a
    terminal, and a native crash discards the buffer -- which is how a run
    produces no output at all despite having printed. Without `flush=True` this
    script would reproduce the very problem it exists to diagnose.
    """
    global STEP
    STEP += 1
    print(f"\n[{STEP:2d}] {label} ...", flush=True)


def ok(detail: str = "") -> None:
    print(f"     OK{'  ' + detail if detail else ''}", flush=True)


def fail(exc: BaseException) -> None:
    print(f"     FAILED: {type(exc).__name__}: {exc}", flush=True)
    traceback.print_exc()
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 14 crash isolator")
    parser.add_argument("--base-model", default="microsoft/deberta-v3-base")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--source", default="synth_precomp_v1")
    args = parser.parse_args(argv)

    print("Phase 14 crash isolator", flush=True)
    print(f"base model : {args.base_model}", flush=True)
    print(f"batch/len  : {args.batch_size} / {args.max_length}", flush=True)
    print(
        "\nIf this script stops with no further output and no traceback, the step\n"
        "named on the last line is a NATIVE crash (not a Python error). The most\n"
        "common cause on Windows is a duplicate OpenMP runtime -- see the end of\n"
        "this script's output for the workaround.",
        flush=True,
    )

    step("import torch")
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok(f"torch {torch.__version__}")

    step("import transformers")
    try:
        import transformers
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok(f"transformers {transformers.__version__}")

    step("environment report")
    print(f"     python        : {platform.python_version()} ({platform.machine()})", flush=True)
    print(f"     platform      : {platform.platform()}", flush=True)
    print(f"     torch threads : {torch.get_num_threads()}", flush=True)
    print(f"     cuda          : {torch.cuda.is_available()}", flush=True)
    for var in ("KMP_DUPLICATE_LIB_OK", "OMP_NUM_THREADS", "HF_HOME", "HF_HUB_OFFLINE"):
        print(f"     {var:<14}: {os.environ.get(var, '(unset)')}", flush=True)
    try:
        import psutil  # type: ignore

        total = psutil.virtual_memory().total / 1e9
        available = psutil.virtual_memory().available / 1e9
        print(f"     RAM           : {available:.1f} GB free of {total:.1f} GB", flush=True)
    except ModuleNotFoundError:
        print("     RAM           : (install psutil for a reading)", flush=True)
    ok()

    step("load the corpus")
    try:
        from src.models.dataset import load_planted

        dataset = load_planted(args.source)
        texts = [r.text for r in dataset.records[:64]]
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok(f"{len(dataset)} records")

    step(f"load tokenizer for {args.base_model}")
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained(args.base_model)
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        print(
            "\n     DeBERTa-v3 uses a sentencepiece tokenizer and needs `sentencepiece`\n"
            "     and `protobuf` installed. Either install them, or switch:\n"
            "         python scripts/diagnose_transformer.py --base-model roberta-base",
            flush=True,
        )
        return 2
    ok(type(tokenizer).__name__)

    step("tokenize 64 records")
    try:
        encoded = tokenizer(
            texts, truncation=True, padding=True, max_length=args.max_length, return_tensors="pt"
        )
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok(f"shape {tuple(encoded['input_ids'].shape)}")

    step("report real token lengths (is max_length wasteful?)")
    lengths = encoded["attention_mask"].sum(dim=1)
    longest = int(lengths.max())
    print(
        f"     longest of these 64: {longest} tokens; mean {float(lengths.float().mean()):.0f}",
        flush=True,
    )
    if longest * 2 < args.max_length:
        print(
            f"     NOTE: max_length={args.max_length} is at least 2x the longest real\n"
            f"     record. With fixed padding that is wasted compute on every batch.",
            flush=True,
        )
    ok()

    step(f"load model + 10-label head ({args.base_model})")
    try:
        model = transformers.AutoModelForSequenceClassification.from_pretrained(
            args.base_model, num_labels=10, problem_type="multi_label_classification"
        )
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    params = sum(p.numel() for p in model.parameters()) / 1e6
    ok(f"{params:.0f}M parameters")

    step("one FORWARD pass, batch of 2")
    try:
        small = {k: v[:2] for k, v in encoded.items()}
        out = model(**small)
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok(f"logits {tuple(out.logits.shape)}")

    step("one BACKWARD pass, batch of 2")
    try:
        targets = torch.zeros_like(out.logits)
        loss = torch.nn.BCEWithLogitsLoss()(out.logits, targets)
        loss.backward()
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok(f"loss {float(loss):.4f}")

    step(
        f"one FORWARD+BACKWARD at full size "
        f"(batch {args.batch_size} x {args.max_length} tokens) -- likeliest OOM point"
    )
    try:
        model.zero_grad()
        padded = tokenizer(
            texts[: args.batch_size],
            truncation=True,
            padding="max_length",
            max_length=args.max_length,
            return_tensors="pt",
        )
        out = model(**padded)
        loss = torch.nn.BCEWithLogitsLoss()(out.logits, torch.zeros_like(out.logits))
        loss.backward()
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok("survived a full-size training step")

    step("tokenize the ENTIRE training set at once -- the other memory point")
    try:
        every = tokenizer(
            [r.text for r in dataset.records],
            truncation=True,
            padding="max_length",
            max_length=args.max_length,
            return_tensors="pt",
        )
        megabytes = every["input_ids"].element_size() * every["input_ids"].nelement() * 2 / 1e6
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    ok(f"shape {tuple(every['input_ids'].shape)}, ~{megabytes:.0f} MB")

    step("time 5 training steps to project the full run")
    try:
        import time

        optimiser = torch.optim.AdamW(model.parameters(), lr=2e-5)
        started = time.time()
        for _ in range(5):
            optimiser.zero_grad()
            out = model(**padded)
            loss = torch.nn.BCEWithLogitsLoss()(out.logits, torch.zeros_like(out.logits))
            loss.backward()
            optimiser.step()
        per_step = (time.time() - started) / 5
    except Exception as exc:  # noqa: BLE001
        fail(exc)
        return 2
    steps_per_epoch = 2591 // args.batch_size
    ok(f"{per_step:.2f}s per step")
    print(
        f"\n     PROJECTION at batch {args.batch_size}, length {args.max_length}:\n"
        f"       1 epoch  ({steps_per_epoch} steps) : "
        f"{per_step * steps_per_epoch / 60:.0f} min\n"
        f"       4 epochs                        : "
        f"{per_step * steps_per_epoch * 4 / 60:.0f} min\n"
        f"       full --sweep (6 configs, 2 splits, ~4 epochs) : "
        f"{per_step * steps_per_epoch * 4 * 6 * 2 / 3600:.1f} hours",
        flush=True,
    )

    print(
        "\n"
        "=====================================================================\n"
        "ALL STEPS PASSED. Nothing here reproduces the silent exit.\n"
        "=====================================================================\n"
        "\n"
        "That points at something the full run does and this script does not:\n"
        "the DataLoader, or sustained memory pressure over thousands of steps.\n"
        "Re-run the real gate with a single small configuration and watch it:\n"
        "\n"
        "    python scripts/run_transformer.py --base-model roberta-base \\\n"
        "        --epochs 1 --max-length 128 --batch-size 8\n"
        "\n"
        "If a step above ended the process with NO traceback, that step is a\n"
        "native crash. Most common cause on Windows is two OpenMP runtimes\n"
        "(torch's and scikit-learn/numpy's MKL) loaded together. Try:\n"
        "\n"
        "    $env:KMP_DUPLICATE_LIB_OK='TRUE'\n"
        "    $env:OMP_NUM_THREADS='4'\n"
        "\n"
        "then re-run this script. If that fixes it, put both in your shell\n"
        "profile and record it in docs/setup.md.\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
