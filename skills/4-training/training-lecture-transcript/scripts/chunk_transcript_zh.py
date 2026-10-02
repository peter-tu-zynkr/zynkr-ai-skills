#!/usr/bin/env python3
"""Chunk Chinese transcript text and validate sequential batch status gating."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

HAN_RE = re.compile(r"[\u4e00-\u9fff]")
SPLIT_RE = re.compile(r"([^。！？!?\n]*[。！？!?]?\n?)")
BATCH_RE = re.compile(r"^### Batch (\d{3})$")
STATUS_RE = re.compile(r"^- Status: (PENDING|IN_PROGRESS|DONE)$")


def count_han(text: str) -> int:
    return len(HAN_RE.findall(text))


def split_units(text: str) -> List[str]:
    units = [u for u in SPLIT_RE.findall(text) if u]
    if not units:
        return [text]
    return units


def hard_split(text: str, max_chars: int) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    han = 0
    for ch in text:
        add = 1 if HAN_RE.match(ch) else 0
        if han + add > max_chars and current:
            chunks.append("".join(current))
            current = []
            han = 0
        current.append(ch)
        han += add
    if current:
        chunks.append("".join(current))
    return chunks


def chunk_text(text: str, max_chars: int) -> List[str]:
    units = split_units(text)
    chunks: List[str] = []
    cur: List[str] = []
    cur_han = 0

    for unit in units:
        unit_han = count_han(unit)
        if unit_han > max_chars:
            if cur:
                chunks.append("".join(cur).strip())
                cur = []
                cur_han = 0
            chunks.extend([c.strip() for c in hard_split(unit, max_chars) if c.strip()])
            continue

        if cur and cur_han + unit_han > max_chars:
            chunks.append("".join(cur).strip())
            cur = [unit]
            cur_han = unit_han
        else:
            cur.append(unit)
            cur_han += unit_han

    if cur:
        chunks.append("".join(cur).strip())

    return [c for c in chunks if c]


def render_batches(chunks: List[str]) -> str:
    out: List[str] = []
    out.append("# Transcript Batches\n")
    out.append("- Rule: Process one batch at a time in numeric order.\n")
    out.append("- Gate: Do not start next batch until current batch is DONE.\n")
    out.append("\n")

    for i, chunk in enumerate(chunks, start=1):
        idx = f"{i:03d}"
        out.append(f"### Batch {idx}\n")
        out.append("- Status: PENDING\n")
        out.append(f"- Source length: {len(chunk)} chars\n")
        out.append(f"- Han count: {count_han(chunk)}\n\n")
        out.append("```text\n")
        out.append(chunk.rstrip() + "\n")
        out.append("```\n\n")
    return "".join(out)


def parse_batch_status(text: str) -> List[Tuple[int, str]]:
    rows: List[Tuple[int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = BATCH_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        batch_id = int(m.group(1))
        status = None
        j = i + 1
        while j < len(lines):
            if BATCH_RE.match(lines[j].strip()):
                break
            sm = STATUS_RE.match(lines[j].strip())
            if sm:
                status = sm.group(1)
                break
            j += 1
        if status is None:
            raise ValueError(f"Batch {batch_id:03d} missing '- Status: ...' line")
        rows.append((batch_id, status))
        i = j + 1
    return rows


def validate_batches(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    rows = parse_batch_status(text)
    if not rows:
        print("ERROR: No batches found.")
        return 1

    for expected, (batch_id, _) in enumerate(rows, start=1):
        if batch_id != expected:
            print(
                f"ERROR: Batch order broken. Expected {expected:03d}, found {batch_id:03d}."
            )
            return 1

    status_order = {"DONE": 0, "IN_PROGRESS": 1, "PENDING": 2}
    prev = -1
    for batch_id, status in rows:
        cur = status_order[status]
        if cur < prev:
            print(
                f"ERROR: Gate violation at batch {batch_id:03d}. "
                "Statuses must be contiguous: DONE* then optional IN_PROGRESS then PENDING*."
            )
            return 1
        prev = cur

    in_progress_count = sum(1 for _, s in rows if s == "IN_PROGRESS")
    if in_progress_count > 1:
        print("ERROR: More than one IN_PROGRESS batch found.")
        return 1

    print("OK: Batch order and status gate are valid.")
    done = sum(1 for _, s in rows if s == "DONE")
    print(f"Progress: {done}/{len(rows)} DONE")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk Chinese transcripts and validate batch gating.")
    parser.add_argument("input", nargs="?", help="Path to transcript text file")
    parser.add_argument("--max-chars", type=int, default=700, help="Max Han chars per batch (default: 700)")
    parser.add_argument("--out", help="Output markdown path for batches")
    parser.add_argument("--validate", help="Validate an existing batches markdown file")
    args = parser.parse_args()

    if args.validate:
        return validate_batches(Path(args.validate))

    if not args.input:
        parser.error("input is required unless --validate is used")

    in_path = Path(args.input)
    text = in_path.read_text(encoding="utf-8")
    chunks = chunk_text(text, args.max_chars)
    rendered = render_batches(chunks)

    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
