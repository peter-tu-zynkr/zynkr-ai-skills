#!/usr/bin/env python3
"""check_manifest.py — holds split-manifest.json to this skill's folder (SKB-091 Phase 0, AC-1).

zynkr-ops-weekly splits into four skills by the store each part writes (D13, D14). The manifest says
where every file, every mode and every heading of a split file goes. This check fails when the folder
and the manifest disagree, so nothing is left behind or moved twice when Phase 1 moves the files:

    check_manifest.py [--root <skill folder>] [--summary]   -> ok: <n> files, <m> modes, 4 homes
    check_manifest.py --mutate                              -> breaks a copy eight ways; each must fail

A manifest value is one of:
  "<home>"                             the file moves to that skill
  "each"                               every skill writes its own version
  {"home": "<home>", "readers": [...]} it stays in <home>, and the readers use it there
  {"split": {"<heading>": <value>}}    divided by its ## and ### headings (never "split" again)

Standard library only, and Python 3.9 safe.
"""
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = "scripts/split-manifest.json"
HEADING_RE = re.compile(r"^(#{2,3}) (.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MODE_RE = re.compile(r"^4\.\d+ `([a-z]+)`")
SKIP_DIRS = {"__pycache__"}


def headings(path):
    """The ## and ### headings of a Markdown file, outside code fences, in order."""
    out, fenced = [], False
    with open(path, encoding="utf-8") as f:
        for line in f:
            if FENCE_RE.match(line):
                fenced = not fenced
                continue
            m = None if fenced else HEADING_RE.match(line)
            if m:
                out.append(m.group(2))
    return out


def folder_files(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        for name in files:
            if name.startswith(".") or name.endswith(".pyc"):
                continue
            out.append(os.path.relpath(os.path.join(d, name), root).replace(os.sep, "/"))
    return sorted(out)


def check_value(where, value, homes, problems, allow_split):
    if isinstance(value, str):
        if value != "each" and value not in homes:
            problems.append("%s: %r is not a home (homes: %s, or each)" % (where, value, ", ".join(homes)))
        return
    if isinstance(value, dict) and set(value) == {"home", "readers"}:
        home, readers = value["home"], value["readers"]
        if home not in homes:
            problems.append("%s: home %r is not a home" % (where, home))
        if not (isinstance(readers, list) and readers):
            problems.append("%s: readers must be a non-empty list" % where)
            return
        for r in readers:
            if r not in homes:
                problems.append("%s: reader %r is not a home" % (where, r))
        if home in readers:
            problems.append("%s: %s reads its own file" % (where, home))
        if len(set(readers)) != len(readers):
            problems.append("%s: a reader is listed twice" % where)
        return
    if allow_split and isinstance(value, dict) and set(value) == {"split"} and isinstance(value["split"], dict):
        return
    problems.append("%s: not a home, each, {home, readers}%s" % (where, " or {split}" if allow_split else ""))


def home_of(value):
    return value if isinstance(value, str) else value.get("home")


def check(root):
    """Every disagreement between the folder and its manifest, as plain lines. Empty means ok."""
    problems = []
    try:
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError) as e:
        return ["%s unreadable: %s" % (MANIFEST, e)], None
    homes = man.get("homes")
    if not (isinstance(homes, list) and len(homes) == 4 and len(set(homes)) == 4):
        return ["homes must list four different skills"], None
    if "each" in homes:
        return ["a home cannot be called each"], None

    files = man.get("files") or {}
    present = folder_files(root)
    for path in present:
        if path not in files:
            problems.append("%s: in the folder, not in the manifest" % path)
    for path in sorted(files):
        if path not in present:
            problems.append("%s: in the manifest, not in the folder" % path)
            continue
        value = files[path]
        check_value(path, value, homes, problems, allow_split=True)
        if isinstance(value, dict) and "split" in value:
            if not path.endswith(".md"):
                problems.append("%s: only Markdown can be split by heading" % path)
                continue
            found = headings(os.path.join(root, path))
            dupes = sorted({h for h in found if found.count(h) > 1})
            for h in dupes:
                problems.append("%s: heading %r appears twice, so it cannot have one home" % (path, h))
            for h in found:
                if h not in value["split"]:
                    problems.append("%s: heading %r has no home" % (path, h))
            for h in value["split"]:
                if h not in found:
                    problems.append("%s: heading %r is in the manifest, not in the file" % (path, h))
            for h, v in value["split"].items():
                check_value("%s › %s" % (path, h), v, homes, problems, allow_split=False)

    modes = man.get("modes") or {}
    skill = os.path.join(root, "SKILL.md")
    found_modes = []
    if os.path.exists(skill):
        for h in headings(skill):
            m = MODE_RE.match(h)
            if m:
                found_modes.append(m.group(1))
                split = (files.get("SKILL.md") or {}).get("split") if isinstance(files.get("SKILL.md"), dict) else None
                if split and h in split and m.group(1) in modes and home_of(split[h]) != modes[m.group(1)]:
                    problems.append("mode %s: its SKILL.md section goes to %s, the mode to %s"
                                    % (m.group(1), home_of(split[h]), modes[m.group(1)]))
    for mode in found_modes:
        if mode not in modes:
            problems.append("mode %s: in SKILL.md, not in the manifest" % mode)
    for mode, home in modes.items():
        if mode not in found_modes:
            problems.append("mode %s: in the manifest, not in SKILL.md" % mode)
        if home not in homes:
            problems.append("mode %s: %r is not a home" % (mode, home))
    return problems, {"files": len(present), "modes": len(found_modes), "homes": homes, "man": man}


def summary(info):
    man, lines = info["man"], []
    for home in info["homes"]:
        moves = [p for p, v in sorted(man["files"].items()) if isinstance(v, str) and v == home]
        keeps = [p for p, v in sorted(man["files"].items()) if isinstance(v, dict) and v.get("home") == home]
        reads = [p for p, v in sorted(man["files"].items()) if isinstance(v, dict) and home in (v.get("readers") or [])]
        modes = [m for m, h in man["modes"].items() if h == home]
        lines.append("%s\n  modes: %s\n  files: %s\n  shared from here: %s\n  reads from the core: %s" % (
            home, " · ".join(modes) or "-", " · ".join(moves) or "-", " · ".join(keeps) or "-", " · ".join(reads) or "-"))
    return "\n".join(lines)


def mutate():
    """Break a copy of the folder eight ways; the check must fail on each, and pass on the control."""
    src = os.path.dirname(HERE)
    base = tempfile.mkdtemp(prefix="check-manifest-")

    def copy():
        dst = tempfile.mkdtemp(dir=base)
        shutil.copytree(src, os.path.join(dst, "skill"), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return os.path.join(dst, "skill")

    def edit_manifest(root, fn):
        p = os.path.join(root, MANIFEST)
        man = json.load(open(p, encoding="utf-8"))
        fn(man)
        json.dump(man, open(p, "w", encoding="utf-8"), ensure_ascii=False)

    def append(root, rel, text):
        with open(os.path.join(root, rel), "a", encoding="utf-8") as f:
            f.write(text)

    breaks = [
        ("an entry dropped", lambda r: edit_manifest(r, lambda m: m["files"].pop("scripts/recap.py"))),
        ("a stray file", lambda r: append(r, "references/stray.md", "# stray\n")),
        ("a new mode", lambda r: append(r, "SKILL.md", "\n### 4.13 `harvest` (Thu 09:00)\n")),
        ("a new mode, its section mapped", lambda r: (
            append(r, "SKILL.md", "\n### 4.13 `harvest` (Thu 09:00)\n"),
            edit_manifest(r, lambda m: m["files"]["SKILL.md"]["split"].update({"4.13 `harvest` (Thu 09:00)": "ops-weekly-doc"})))),
        ("a heading with no home", lambda r: append(r, "references/message-templates.md", "\n## `harvest` — Wed 20:00\n")),
        ("a file gone", lambda r: os.remove(os.path.join(r, "scripts/carryover.py"))),
        ("a mode and its section apart", lambda r: edit_manifest(r, lambda m: m["modes"].update(tidy="ops-weekly-tracker"))),
        ("a home misspelled", lambda r: edit_manifest(r, lambda m: m["files"].update({"scripts/beats.py": "project-manger"}))),
    ]
    ok = True
    control, _ = check(copy())
    if control:
        print("mutate: the unmodified copy fails: %s" % control[0])
        ok = False
    for name, breakit in breaks:
        root = copy()
        breakit(root)
        problems, _ = check(root)
        print("mutate: %-30s %s" % (name, "caught: " + problems[0] if problems else "MISSED"))
        ok = ok and bool(problems)
    shutil.rmtree(base, ignore_errors=True)
    return 0 if ok else 1


def main(argv):
    if "--mutate" in argv:
        return mutate()
    root = os.path.dirname(HERE)
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    problems, info = check(root)
    if problems:
        for p in problems:
            print("FAIL " + p)
        print("check_manifest: %d problem(s)" % len(problems))
        return 1
    print("ok: %d files, %d modes, %d homes" % (info["files"], info["modes"], len(info["homes"])))
    if "--summary" in argv:
        print(summary(info))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
