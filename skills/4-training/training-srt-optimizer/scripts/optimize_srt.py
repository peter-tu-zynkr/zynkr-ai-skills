#!/usr/bin/env python3
"""Inspect, export, rebuild, and validate subtitle SRT files."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

TIME_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}$"
)
WORKSHEET_RE = re.compile(
    r"### Cue (?P<index>\d+)\n"
    r"TIME: (?P<time>[^\n]+)\n"
    r"SOURCE:\n```text\n(?P<source>.*?)\n```\n"
    r"TARGET:\n```text\n(?P<target>.*?)\n```",
    re.DOTALL,
)
PUNCTUATION = set("，。！？、；：「」『』（）［］【】〈〉《》…—,.!?;:'\"()[]{}<>`~@#$%^&*_+=|\\/")
PUNCT_RE = re.compile(r"[，。！？、；：「」『』（）［］【】〈〉《》…—,.!?;:'\"()\[\]{}<>`~@#$%^&*_+=|\\/]+")
ZH_EN_RE_1 = re.compile(r"([\u4e00-\u9fff])([A-Za-z0-9])")
ZH_EN_RE_2 = re.compile(r"([A-Za-z0-9])([\u4e00-\u9fff])")
MULTISPACE_RE = re.compile(r"\s+")
FILLER_REPEATED_RE = re.compile(r"\b([A-Za-z0-9\u4e00-\u9fff]+)(?:\s+\1\b)+")
EDGE_FILLERS = (
    "那",
    "欸",
    "哈哈哈",
    "對吧",
    "嘛",
    "然後",
    "就是",
    "嗯",
    "呃",
)
STT_REPLACEMENTS: Sequence[Tuple[str, str]] = (
    ("Cloud 公司", "Claude 公司"),
    ("cloud upper", "Claude Opus"),
    ("克制", "客製"),
    ("AI 寫作客", "AI 寫作課"),
    ("見徑式", "漸進式"),
    ("antropic", "Anthropic"),
    ("jammernike", "Gemini"),
    ("大於模型", "大語模型"),
    ("prump", "prompt"),
    ("gbt", "GPT"),
    ("中端", "終端"),
    ("Cloud Code", "Claude Code"),
    ("Cloud的", "Claude 的"),
    ("Cloud ", "Claude "),
    ("Cloud", "Claude"),
    ("no 選", "Notion"),
    ("antropec", "Anthropic"),
    ("entronope", "Anthropic"),
    ("get hub", "GitHub"),
)


@dataclass
class Cue:
    index: int
    timecode: str
    lines: List[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def parse_srt(text: str) -> List[Cue]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if not blocks:
        raise ValueError("Input file is empty.")
    if len(blocks) == 1 and not TIME_RE.search(text):
        raise ValueError(
            "Input is not a valid SRT file: no cue timestamps were found. "
            "This looks like a plain transcript saved with a .srt extension."
        )
    cues: List[Cue] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if len(lines) < 3:
            raise ValueError(f"Invalid cue block:\n{block}")
        try:
            index = int(lines[0].strip())
        except ValueError as exc:
            raise ValueError(f"Invalid cue index in block:\n{block}") from exc
        timecode = lines[1].strip()
        if not TIME_RE.match(timecode):
            raise ValueError(f"Invalid timecode for cue {index}: {timecode}")
        text_lines = [line.strip() for line in lines[2:] if line.strip()]
        if not text_lines:
            raise ValueError(f"Cue {index} has empty text")
        cues.append(Cue(index=index, timecode=timecode, lines=text_lines))
    return cues


def render_srt(cues: Sequence[Cue]) -> str:
    parts: List[str] = []
    for cue in cues:
        parts.append(str(cue.index))
        parts.append(cue.timecode)
        parts.extend(cue.lines)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def visual_width(text: str) -> float:
    width = 0.0
    for ch in text:
        if ch in {" ", "\t"}:
            continue
        width += 1.0 if unicodedata.east_asian_width(ch) in {"W", "F", "A"} else 0.5
    return width


def count_punctuation(text: str) -> int:
    return sum(1 for ch in text if ch in PUNCTUATION)


def normalize_spacing(text: str) -> str:
    text = ZH_EN_RE_1.sub(r"\1 \2", text)
    text = ZH_EN_RE_2.sub(r"\1 \2", text)
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def strip_edge_fillers(text: str) -> str:
    changed = True
    while changed and text:
        changed = False
        for filler in EDGE_FILLERS:
            for candidate in (f"{filler} ", f"{filler}　"):
                if text.startswith(candidate):
                    text = text[len(candidate):].strip()
                    changed = True
            if text == filler:
                text = ""
                changed = True
            if text.endswith(f" {filler}"):
                text = text[: -(len(filler) + 1)].strip()
                changed = True
    return text


def apply_stt_replacements(text: str) -> str:
    for src, dst in STT_REPLACEMENTS:
        text = text.replace(src, dst)
    return text


def minimal_cleanup(text: str) -> str:
    text = apply_stt_replacements(text)
    text = PUNCT_RE.sub(" ", text)
    text = normalize_spacing(text)
    text = strip_edge_fillers(text)
    text = FILLER_REPEATED_RE.sub(r"\1", text)
    text = normalize_spacing(text)
    return text


def split_line(text: str, max_line_width: float, max_lines: int) -> List[str]:
    if not text:
        return [text]
    if visual_width(text) <= max_line_width:
        return [text]

    tokens = text.split(" ")
    if len(tokens) == 1:
        chars = list(text)
    else:
        chars = tokens

    lines: List[str] = []
    current: List[str] = []
    for token in chars:
        candidate_parts = current + [token]
        candidate = "".join(candidate_parts) if len(tokens) == 1 else " ".join(candidate_parts)
        if current and visual_width(candidate) > max_line_width:
            lines.append("".join(current) if len(tokens) == 1 else " ".join(current))
            current = [token]
        else:
            current.append(token)

    if current:
        lines.append("".join(current) if len(tokens) == 1 else " ".join(current))

    if len(lines) <= max_lines:
        return [normalize_spacing(line) for line in lines if line.strip()]

    merged = lines[: max_lines - 1]
    tail = " ".join(lines[max_lines - 1:]) if len(tokens) > 1 else "".join(lines[max_lines - 1:])
    merged.append(normalize_spacing(tail))
    return [line for line in merged if line.strip()]


def optimize_cue(cue: Cue, max_line_width: float, max_lines: int) -> Cue:
    cleaned = minimal_cleanup(" ".join(cue.lines))
    if not cleaned:
        cleaned = normalize_spacing(" ".join(cue.lines))
    lines = split_line(cleaned, max_line_width=max_line_width, max_lines=max_lines)
    return Cue(index=cue.index, timecode=cue.timecode, lines=lines)


def chunk_cues(cues: Sequence[Cue], max_batch_width: float) -> List[List[Cue]]:
    batches: List[List[Cue]] = []
    current: List[Cue] = []
    current_width = 0.0

    for cue in cues:
        cue_width = sum(visual_width(line) for line in cue.lines)
        if current and current_width + cue_width > max_batch_width:
            batches.append(current)
            current = [cue]
            current_width = cue_width
        else:
            current.append(cue)
            current_width += cue_width

    if current:
        batches.append(current)
    return batches


def render_worksheet(cues: Sequence[Cue], max_batch_width: float) -> str:
    batches = chunk_cues(cues, max_batch_width=max_batch_width)
    out: List[str] = []
    out.append("# SRT Rewrite Worksheet\n\n")
    out.append("- Fill only the `TARGET` blocks.\n")
    out.append("- Keep cue order and `TIME:` unchanged.\n")
    out.append("- `TARGET` is prefilled with source text. Edit in place with minimal changes only.\n")
    out.append("- Only remove filler words, fix obvious STT mistakes, and adjust line breaks or spacing.\n")
    out.append("- Do not paraphrase, summarize, or compress meaning.\n\n")

    for batch_idx, batch in enumerate(batches, start=1):
        out.append(f"## Batch {batch_idx:03d}\n\n")
        for cue in batch:
            out.append(f"### Cue {cue.index}\n")
            out.append(f"TIME: {cue.timecode}\n")
            out.append("SOURCE:\n```text\n")
            out.append(cue.text)
            out.append("\n```\n")
            out.append("TARGET:\n```text\n")
            out.append(cue.text)
            out.append("\n```\n\n")
    return "".join(out)


def parse_worksheet(path: Path) -> Dict[int, Cue]:
    text = read_text(path)
    parsed: Dict[int, Cue] = {}
    for match in WORKSHEET_RE.finditer(text):
        index = int(match.group("index"))
        timecode = match.group("time").strip()
        target = match.group("target").strip()
        source = match.group("source").strip()
        final_text = target if target else source
        lines = [line.strip() for line in final_text.splitlines() if line.strip()]
        parsed[index] = Cue(index=index, timecode=timecode, lines=lines)
    if not parsed:
        raise ValueError(f"No cues found in worksheet: {path}")
    return parsed


def inspect(cues: Sequence[Cue], max_line_width: float) -> int:
    longest = 0.0
    longest_label = ""
    over_limit = 0
    punctuation_hits = 0

    for cue in cues:
        for line in cue.lines:
            width = visual_width(line)
            if width > longest:
                longest = width
                longest_label = f"Cue {cue.index}: {line}"
            if width > max_line_width:
                over_limit += 1
            punctuation_hits += count_punctuation(line)

    print(f"Cues: {len(cues)}")
    print(f"Time range: {cues[0].timecode.split(' --> ')[0]} -> {cues[-1].timecode.split(' --> ')[1]}")
    print(f"Longest line width: {longest:.1f}")
    if longest_label:
        print(f"Longest line sample: {longest_label}")
    print(f"Lines over width {max_line_width:.1f}: {over_limit}")
    print(f"Punctuation chars found: {punctuation_hits}")
    return 0


def validate(cues: Sequence[Cue], max_line_width: float, max_lines: int) -> int:
    errors: List[str] = []
    for expected, cue in enumerate(cues, start=1):
        if cue.index != expected:
            errors.append(f"Cue numbering broken at {cue.index}, expected {expected}")
        if len(cue.lines) > max_lines:
            errors.append(f"Cue {cue.index} has {len(cue.lines)} lines, limit is {max_lines}")
        for line in cue.lines:
            width = visual_width(line)
            if width > max_line_width:
                errors.append(
                    f"Cue {cue.index} line too wide ({width:.1f} > {max_line_width:.1f}): {line}"
                )
            punct = count_punctuation(line)
            if punct:
                errors.append(f"Cue {cue.index} contains punctuation ({punct} chars): {line}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        print(f"Validation failed with {len(errors)} issue(s).")
        return 1

    print("OK: Subtitle file passed validation.")
    print(f"Cues checked: {len(cues)}")
    return 0


def rebuild(original_cues: Sequence[Cue], worksheet_cues: Dict[int, Cue]) -> List[Cue]:
    rebuilt: List[Cue] = []
    missing: List[int] = []
    changed_timecodes = 0

    for cue in original_cues:
        updated = worksheet_cues.get(cue.index)
        if updated is None:
            missing.append(cue.index)
            rebuilt.append(cue)
            continue
        if updated.timecode != cue.timecode:
            changed_timecodes += 1
        rebuilt.append(Cue(index=cue.index, timecode=cue.timecode, lines=updated.lines))

    if missing:
        raise ValueError(f"Worksheet missing cues: {', '.join(str(i) for i in missing[:20])}")
    if changed_timecodes:
        print(
            f"WARNING: Worksheet attempted to change {changed_timecodes} timecode(s); original times were preserved.",
            file=sys.stderr,
        )
    return rebuilt


def cmd_inspect(args: argparse.Namespace) -> int:
    cues = parse_srt(read_text(Path(args.input)))
    return inspect(cues, max_line_width=args.max_line_width)


def cmd_export(args: argparse.Namespace) -> int:
    cues = parse_srt(read_text(Path(args.input)))
    worksheet = render_worksheet(cues, max_batch_width=args.max_batch_width)
    output = Path(args.out)
    output.write_text(worksheet, encoding="utf-8")
    print(f"Wrote worksheet: {output}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    original = parse_srt(read_text(Path(args.input)))
    worksheet_cues = parse_worksheet(Path(args.worksheet))
    rebuilt = rebuild(original, worksheet_cues)
    output = Path(args.out)
    output.write_text(render_srt(rebuilt), encoding="utf-8")
    print(f"Wrote rebuilt SRT: {output}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cues = parse_srt(read_text(Path(args.input)))
    return validate(cues, max_line_width=args.max_line_width, max_lines=args.max_lines)


def cmd_optimize(args: argparse.Namespace) -> int:
    source = Path(args.input)
    cues = parse_srt(read_text(source))
    optimized = [
        optimize_cue(cue, max_line_width=args.max_line_width, max_lines=args.max_lines)
        for cue in cues
    ]
    output = Path(args.out) if args.out else source.with_name(f"{source.stem}.optimized.srt")
    output.write_text(render_srt(optimized), encoding="utf-8")
    changed = sum(1 for before, after in zip(cues, optimized) if before.lines != after.lines)
    print(f"Wrote optimized SRT: {output}")
    print(f"Changed cues: {changed}/{len(cues)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Helper utilities for subtitle SRT cleanup workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Summarize an SRT file")
    inspect_parser.add_argument("input", help="Path to input .srt")
    inspect_parser.add_argument("--max-line-width", type=float, default=18.0)
    inspect_parser.set_defaults(func=cmd_inspect)

    export_parser = subparsers.add_parser("export", help="Export an editable markdown worksheet")
    export_parser.add_argument("input", help="Path to input .srt")
    export_parser.add_argument("--out", required=True, help="Path to output worksheet markdown")
    export_parser.add_argument("--max-batch-width", type=float, default=1200.0)
    export_parser.set_defaults(func=cmd_export)

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild SRT from worksheet targets")
    rebuild_parser.add_argument("input", help="Path to original .srt")
    rebuild_parser.add_argument("worksheet", help="Path to edited worksheet markdown")
    rebuild_parser.add_argument("--out", required=True, help="Path to rebuilt .srt")
    rebuild_parser.set_defaults(func=cmd_rebuild)

    validate_parser = subparsers.add_parser("validate", help="Validate a rebuilt SRT")
    validate_parser.add_argument("input", help="Path to .srt")
    validate_parser.add_argument("--max-line-width", type=float, default=18.0)
    validate_parser.add_argument("--max-lines", type=int, default=2)
    validate_parser.set_defaults(func=cmd_validate)

    optimize_parser = subparsers.add_parser("optimize", help="Apply conservative automatic cleanup")
    optimize_parser.add_argument("input", help="Path to input .srt")
    optimize_parser.add_argument("--out", help="Path to optimized .srt")
    optimize_parser.add_argument("--max-line-width", type=float, default=18.0)
    optimize_parser.add_argument("--max-lines", type=int, default=2)
    optimize_parser.set_defaults(func=cmd_optimize)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
