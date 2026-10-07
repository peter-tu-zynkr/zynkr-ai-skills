#!/usr/bin/env python3
"""extract_newest_block.py — pull the newest N weekly blocks out of the 營運每週彙報 markdown dump.

Input: a markdown file produced by `get_doc_as_markdown` on the weekly ops log
(newest week on TOP). Weekly blocks start with a level-2 date heading such as
`## Aug 13, 2026`. A block ends at the next date heading OR at any level-1
heading (`# ...`, i.e. the next tab of the doc). Non-date `##` lines inside a
block (e.g. `## **Claude Code 課程**`) are treated as sections, not boundaries.

Default output: the newest N blocks verbatim (nothing stripped).
--json: [{date_iso, heading, line_start, line_end, body, sections:[{heading, level, text, owners}]}]
"Metrics" pseudo-heading lines (a line that is just `Metrics` / `Metrics:`) become level-5 sections.

--heading TEXT (SKB-068): any other big doc, one section at a time. Emits the section under the first
heading whose text contains TEXT (case-insensitive; markdown escapes such as `0\\.`, bold markers, links
and HTML entities ignored), up to the next heading of the same or a higher level. This is how the skills
Knowledge Map is read one category at a time (`--heading "0. Strategy"`, `--heading "The Skill Map"`),
and the VMS / plan docs one dated block at a time (`--heading "H2 2026 alignment"`, `--heading "2026-08-06 Refresh"`,
`--heading "2026-07-28 Refresh"`). Name the dated heading: a bare "Refresh" also matches the Integrated Refresh doc's
own title, and a level-1 title's section is the whole doc.
Exit 1, listing the doc's top headings, when nothing matches. With --json: {heading, level, line_start,
line_end, body}.

The input is the markdown, or the file a harness saves an oversize tool result to: that is JSON
({"result": "…"}), and is unwrapped first — read raw, it is one line with no heading in it.

Python 3 stdlib only.
"""
import argparse
import html
import json
import re
import sys

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
# `## Aug 13, 2026`   `## Thu Aug 13, 2026`   `## Thu, Aug 13, 2026`   `## August 13, 2026`
DATE_HEADING = re.compile(
    r"^##\s+(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),\s*(\d{4})\s*$"
)
H1 = re.compile(r"^#\s+\S")
ANY_HEADING = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")
METRICS_LINE = re.compile(r"^\s*\**Metrics\**:?\s*$")
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
MAILTO_LINK = re.compile(r"\[([^\]]+)\]\(mailto:[^)]*\)")


def parse_date_heading(line):
    m = DATE_HEADING.match(line)
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower()[:4]) or MONTHS.get(m.group(1).lower()[:3])
    if not mon:
        return None
    day, year = int(m.group(2)), int(m.group(3))
    if not (1 <= day <= 31):
        return None
    return f"{year:04d}-{mon:02d}-{day:02d}"


def clean_heading(text):
    """Strip markdown links (keep link text), bold markers and stray whitespace."""
    text = MD_LINK.sub(lambda m: m.group(1), text)
    text = text.replace("**", "").replace("~~", "")
    return re.sub(r"\s+", " ", text).strip()


def owners_in(text):
    return [m.group(1).strip() for m in MAILTO_LINK.finditer(text)]


HEADING_LINE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def heading_key(text):
    """A heading's text as a reader means it: `## 0\\. Strategy &amp; Leadership` → '0. strategy & leadership'."""
    text = html.unescape(clean_heading(text))
    text = re.sub(r"\\(.)", r"\1", text)          # Docs' markdown export escapes `0.` as `0\.`
    return re.sub(r"\s+", " ", text.replace("__", "")).strip().casefold()


def doc_lines(text):
    """Lines as grep and sed count them. Not splitlines(): a Doc's in-paragraph breaks export as \\x0b, which
    splitlines() also splits on, so its line numbers drift from the file's (397 of them in the skills KB)."""
    return [ln.rstrip("\r") for ln in text.split("\n")]


def extract_heading(text, needle):
    """The section under the first heading whose text contains `needle`, up to the next heading of the
    same or a higher level. None when no heading matches."""
    lines = doc_lines(text)
    want = heading_key(needle)
    for i, line in enumerate(lines):
        m = HEADING_LINE.match(line)
        if not (m and want in heading_key(m.group(2))):
            continue
        level, end = len(m.group(1)), len(lines)
        for j in range(i + 1, len(lines)):
            n = HEADING_LINE.match(lines[j])
            if n and len(n.group(1)) <= level:
                end = j
                break
        return {"heading": line, "level": level, "line_start": i + 1, "line_end": end,
                "body": "\n".join(lines[i + 1:end]).strip("\n")}
    return None


def top_headings(text, max_level=2):
    return [line for line in doc_lines(text)
            if (m := HEADING_LINE.match(line)) and len(m.group(1)) <= max_level]


def unwrap(text):
    """The doc's markdown. A harness that saves an oversize tool result to a file wraps it as JSON —
    {"result": "..."} or [{"type": "text", "text": "..."}] — so the whole doc sits on one line and no
    heading is found. Unwrap that; anything else (a doc may itself start with `[`) is used as is."""
    s = text.lstrip()
    if not s.startswith(("{", "[")):
        return text
    try:
        obj = json.loads(s)
    except ValueError:
        return text
    if isinstance(obj, dict) and isinstance(obj.get("result"), str):
        return obj["result"]
    if isinstance(obj, list):
        parts = [x["text"] for x in obj if isinstance(x, dict) and isinstance(x.get("text"), str)]
        if parts:
            return "\n".join(parts)
    return text


def split_blocks(lines):
    """Return list of (date_iso, heading_line, start_idx, end_idx_exclusive) in file order."""
    starts = []
    for i, line in enumerate(lines):
        d = parse_date_heading(line)
        if d:
            starts.append((i, d))
    blocks = []
    for n, (start, d) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        # a level-1 heading (next tab) also terminates the block
        for j in range(start + 1, end):
            if H1.match(lines[j]):
                end = j
                break
        blocks.append((d, lines[start].rstrip("\n"), start, end))
    return blocks


def sectionise(body_lines):
    sections = []
    cur = None

    def flush():
        if cur is not None:
            cur["text"] = "\n".join(cur["_lines"]).strip("\n")
            del cur["_lines"]
            sections.append(cur)

    for line in body_lines:
        h = ANY_HEADING.match(line)
        if h:
            flush()
            cur = {"heading": clean_heading(h.group(2)), "level": len(h.group(1)),
                   "owners": owners_in(h.group(2)), "_lines": []}
            continue
        if METRICS_LINE.match(line):
            flush()
            cur = {"heading": "Metrics", "level": 5, "owners": [], "_lines": []}
            continue
        if cur is None:
            if not line.strip():
                continue
            cur = {"heading": "", "level": 0, "owners": [], "_lines": []}
        cur["_lines"].append(line.rstrip("\n"))
    flush()
    return sections


def extract(text, n=1):
    # split on "\n" only (not str.splitlines) so line numbers match grep/sed/awk
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    blocks = split_blocks(lines)
    out = []
    for d, heading, start, end in blocks[:max(n, 0)]:
        body_lines = lines[start + 1:end]
        out.append({
            "date_iso": d,
            "heading": heading,
            "line_start": start + 1,
            "line_end": end,
            "body": "\n".join(body_lines).strip("\n"),
            "sections": sectionise(body_lines),
        })
    return out, len(blocks)


SAMPLE = """# 每週事項 2026

# Meeting Note

## Aug 13, 2026

### #Team update

- Start of week update, what is the focus of the week

### #Demand Marketing ([Website](https://example.com/))([Brand guide](https://example.com/bg)) [Alex T](mailto:alex@example.com)

#### ##Branding [Alex T](mailto:alex@example.com)

- Zynkr website newsletter drip

#### ##Establish SOP

- Run data report
Metrics

- Monthly Impression #
- CPM, CPC, CTR, Conversion rate, ROAS

### #Operation [Bea L](mailto:bea@example.com)

#### ##Operation BAU & event

- 8/19(三) Vibe coding   報名人數25人
Metrics

- Sign up #

### # [Knowledge product (Course design＋Deliver)](https://example.com/kp) [Cleo L](mailto:cleo@example.com)

## **Claude Code 課程**

Current progress

- [ ] 課程剪輯
Metrics

- Course preparation %

## Aug 6, 2026

### #Team update

- older item

### #Operation [Bea L](mailto:bea@example.com)

- 8/15(六) 直播 報名人數72人
Metrics

- Sign up #

## Jul 30, 2026

### #Team update

- oldest

# 每週事項 2025

# Notes

## Dec 25, 2025

### #Overall

- should not leak into Jul 30 block
"""


def selftest():
    blocks, total = extract(SAMPLE, n=10)
    assert total == 4, total
    assert [b["date_iso"] for b in blocks] == ["2026-08-13", "2026-08-06", "2026-07-30", "2025-12-25"], blocks
    newest = blocks[0]
    assert newest["heading"] == "## Aug 13, 2026"
    heads = [(s["level"], s["heading"]) for s in newest["sections"]]
    assert (3, "#Team update") in heads, heads
    assert (2, "Claude Code 課程") in heads, heads  # non-date ## is a section, not a boundary
    assert sum(1 for l, h in heads if h == "Metrics" and l == 5) == 3, heads
    dm = next(s for s in newest["sections"] if s["heading"].startswith("#Demand Marketing"))
    assert dm["heading"] == "#Demand Marketing (Website)(Brand guide) Alex T", dm["heading"]
    assert dm["owners"] == ["Alex T"], dm
    ops = next(s for s in newest["sections"] if s["heading"].startswith("##Operation BAU"))
    assert ops["level"] == 4 and "報名人數25人" in ops["text"], ops
    # Jul 30 block must stop at the `# 每週事項 2025` H1, not swallow Dec 25
    jul30 = blocks[2]
    assert "should not leak" not in jul30["body"] and jul30["body"].strip().endswith("- oldest"), jul30["body"]
    # default N=1 verbatim
    one, _ = extract(SAMPLE, n=1)
    assert len(one) == 1 and one[0]["date_iso"] == "2026-08-13"
    assert one[0]["line_start"] == 5
    # heading variants
    assert parse_date_heading("## Thu Aug 13, 2026") == "2026-08-13"
    assert parse_date_heading("## Thu, Aug 13, 2026") == "2026-08-13"
    assert parse_date_heading("## August 13, 2026") == "2026-08-13"
    assert parse_date_heading("## Sept 5, 2026") == "2026-09-05"
    assert parse_date_heading("## **Claude Code 課程**") is None
    assert parse_date_heading("### Aug 13, 2026") is None
    # --heading: the skills Knowledge Map, one category at a time, in the shapes the Docs export writes
    kb = KB_SAMPLE
    s0 = extract_heading(kb, "0. Strategy")
    assert s0 and s0["level"] == 2 and "zynkr-gm (0.02)" in s0["body"], s0
    assert "Brand" not in s0["body"] and "content-idea" not in s0["body"], s0["body"]
    assert "### planning-prework-pack (0.03)" in s0["body"], "a ### skill heading stays inside its category"
    s1 = extract_heading(kb, "1. brand & marketing")
    assert s1 and "zynkr-content-writer" in s1["body"] and "Appendix" not in s1["body"], s1
    sm = extract_heading(kb, "The Skill Map")
    assert sm and "Engagement — 41" in sm["body"] and "zynkr-gm" not in sm["body"], sm
    assert extract_heading(kb, "At a glance")["body"].startswith("| Skills covered"), "first section"
    one = extract_heading(kb, "zynkr-gm (0.02)")
    assert one and one["level"] == 3 and "planning-prework-pack" not in one["body"], one
    assert extract_heading(kb, "9. Legal") is None
    assert extract_heading("## **H2 2026 alignment** (2026-08-06)\nnew\n## Body\nold", "H2 2026 alignment")["body"] == "new"
    assert top_headings(kb)[:2] == ["# Zynkr Skills — Knowledge Map", "## At a glance"], top_headings(kb)
    # a dump the harness saved as JSON is unwrapped; a doc that merely starts with `[` is left alone
    assert unwrap(json.dumps({"result": kb})) == kb
    assert unwrap(json.dumps([{"type": "text", "text": SAMPLE}])) == SAMPLE
    linked = "[⤴ back](https://example.com)\n\n" + kb
    assert unwrap(linked) == linked
    assert extract(unwrap(json.dumps({"result": SAMPLE})), n=1)[0][0]["date_iso"] == "2026-08-13"
    # line numbers are the file's: a Doc's in-paragraph break (\x0b) does not start a new line
    vt = "## A\none\x0btwo\x0bthree\n## B\nb"
    sb = extract_heading(vt, "B")
    assert (sb["line_start"], sb["line_end"]) == (3, 4), sb
    assert vt.split("\n")[sb["line_start"] - 1] == "## B"
    print("extract_newest_block selftest OK")
    return 0


KB_SAMPLE = """# Zynkr Skills — Knowledge Map

## At a glance

| Skills covered | 138 index rows: 105 skills and 33 sub-agents |

## The Skill Map — six pages

- Index — all 138
- Engagement — 41: Sales 12 · Consult 6

## 0\\. Strategy &amp; Leadership 策略與領導

### [zynkr-gm (0.02)](https://example.com/zynkr-gm)

Reads the company source-of-record chain.
Skill Map: Company teams · Leadership

### planning-prework-pack (0.03)

- ⟳ planning-sources.md

## 1\\. Brand & Marketing 品牌與行銷

### zynkr-content-writer (1.01)

Sub-agents (7): content-idea (1.02)

## Appendix A — sources that need attention

None.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="markdown dump of the weekly ops log (newest week on top)")
    ap.add_argument("--blocks", type=int, default=1, help="how many newest blocks to emit (default 1)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of verbatim markdown")
    ap.add_argument("--heading", metavar="TEXT",
                    help="emit the section under the first heading containing TEXT (any big doc), not weekly blocks")
    ap.add_argument("--selftest", action="store_true", help="run embedded sample and exit 0/1")
    args = ap.parse_args(argv)
    if args.selftest:
        try:
            return selftest()
        except AssertionError as e:
            print(f"SELFTEST FAILED: {e!r}", file=sys.stderr)
            return 1
    if not args.path:
        ap.error("path is required (or use --selftest)")
    with open(args.path, encoding="utf-8") as fh:
        text = unwrap(fh.read())
    if args.heading:
        sec = extract_heading(text, args.heading)
        if not sec:
            print(f"no heading contains {args.heading!r}; the doc's top headings are:", file=sys.stderr)
            for h in top_headings(text):
                print(f"  {h}", file=sys.stderr)
            return 1
        if args.json:
            json.dump(sec, sys.stdout, ensure_ascii=False, indent=2)
            print()
        else:
            print(sec["heading"])
            print()
            print(sec["body"])
        print(f"[extract_newest_block] section {sec['heading']!r}: lines {sec['line_start']}–{sec['line_end']}",
              file=sys.stderr)
        return 0
    blocks, total = extract(text, n=args.blocks)
    if not blocks:
        print("no `## <Mon DD, YYYY>` date heading found", file=sys.stderr)
        return 1
    if args.json:
        json.dump(blocks, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        for b in blocks:
            print(b["heading"])
            print()
            print(b["body"])
            print()
    print(f"[extract_newest_block] {len(blocks)}/{total} blocks emitted; newest={blocks[0]['date_iso']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
