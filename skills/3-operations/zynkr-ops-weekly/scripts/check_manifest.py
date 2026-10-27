#!/usr/bin/env python3
"""check_manifest.py — holds the four weekly-loop skills to split-manifest.json (SKB-091, AC-1 and AC-6).

The weekly loop is split by the store each part writes (D13, D14) into zynkr-ops-weekly, ops-weekly-doc,
ops-weekly-tracker and project-manager. The manifest lists, per skill, every file it holds and the modes
its SKILL.md runs. This check fails when the folders and the manifest disagree, so nothing is left
behind, kept twice, or run by the wrong skill:

    check_manifest.py [--skills <folder holding the four skills>]   -> ok: <n> files, <m> modes, 4 homes
    check_manifest.py --mutate                                      -> breaks a copy six ways; each must fail

It checks that:
  - each skill folder holds exactly the files its home lists (no stray, no missing file);
  - no script or reference is in two homes (SKILL.md and README.md are each skill's own);
  - each SKILL.md has a `### \\`<mode>\\`` heading for every mode its home runs, and none for another's;
  - no SKILL.md runs a retired beat;
  - project-manager's beats.py hands every mode to the home that runs it.

Standard library only, and Python 3.9 safe.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.normpath(os.path.join(HERE, "..", ".."))
OWN = {"SKILL.md", "README.md"}
MODE_HEADING = re.compile(r"^### `([a-z]+)`")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SKIP_DIRS = {"__pycache__"}


def folder_files(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        for name in files:
            if name.startswith(".") or name.endswith(".pyc"):
                continue
            out.append(os.path.relpath(os.path.join(d, name), root).replace(os.sep, "/"))
    return sorted(out)


def mode_headings(path):
    out, fenced = [], False
    with open(path, encoding="utf-8") as f:
        for line in f:
            if FENCE_RE.match(line):
                fenced = not fenced
                continue
            m = None if fenced else MODE_HEADING.match(line)
            if m:
                out.append(m.group(1))
    return out


def owners(skills):
    """beats.py's OWNERS, read by running it: the selector is the runner's own source of truth."""
    beats = os.path.join(skills, "project-manager", "scripts", "beats.py")
    code = "import json,sys; sys.path.insert(0, sys.argv[1]); import beats; print(json.dumps(beats.OWNERS))"
    r = subprocess.run([sys.executable, "-c", code, os.path.dirname(beats)], capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError("beats.py did not load: %s" % r.stderr.strip()[-200:])
    return json.loads(r.stdout)


def check(skills):
    with open(os.path.join(skills, "zynkr-ops-weekly", "scripts", "split-manifest.json"), encoding="utf-8") as f:
        man = json.load(f)
    problems = []
    homes = man.get("homes") or {}
    if man.get("version") != 4 or sorted(homes) != sorted(["zynkr-ops-weekly", "ops-weekly-doc", "ops-weekly-tracker", "project-manager"]):
        return ["the manifest is not the v4 four-home manifest"], 0, 0
    seen = {}
    nfiles = nmodes = 0
    for home, spec in sorted(homes.items()):
        root = os.path.join(skills, home)
        want, have = sorted(spec["files"]), folder_files(root) if os.path.isdir(root) else []
        for p in sorted(set(want) - set(have)):
            problems.append("%s: %s is listed but missing" % (home, p))
        for p in sorted(set(have) - set(want)):
            problems.append("%s: %s is not in the manifest (a copy, or a file added without its line)" % (home, p))
        for p in want:
            name = os.path.basename(p)
            if name in OWN:
                continue
            if name in seen:
                problems.append("%s is in both %s and %s" % (name, seen[name], home))
            seen[name] = home
        nfiles += len(want)
        skill_md = os.path.join(root, "SKILL.md")
        runs = mode_headings(skill_md) if os.path.exists(skill_md) else []
        for m in spec["modes"]:
            if m not in runs:
                problems.append("%s: SKILL.md has no ### `%s` section" % (home, m))
        for m in runs:
            if m in man["retired"]:
                problems.append("%s: SKILL.md still runs the retired beat %s" % (home, m))
            elif m not in spec["modes"]:
                problems.append("%s: SKILL.md runs %s, which the manifest gives to another home" % (home, m))
        nmodes += len(spec["modes"])
    try:
        own = owners(skills)
        for home, spec in homes.items():
            for m in spec["modes"]:
                if own.get(m) != home:
                    problems.append("beats.py hands %s to %s, the manifest to %s" % (m, own.get(m), home))
        for m in man["retired"]:
            if m in own:
                problems.append("beats.py still schedules the retired beat %s" % m)
    except ValueError as e:
        problems.append(str(e))
    return problems, nfiles, nmodes


def mutate():
    tmp = tempfile.mkdtemp(prefix="check-manifest-")
    homes = ["zynkr-ops-weekly", "ops-weekly-doc", "ops-weekly-tracker", "project-manager"]

    def fresh():
        d = tempfile.mkdtemp(dir=tmp)
        for h in homes:
            shutil.copytree(os.path.join(SKILLS, h), os.path.join(d, h), ignore=shutil.ignore_patterns("__pycache__"))
        return d

    def edit(path, old, new):
        t = open(path, encoding="utf-8").read()
        assert t.count(old) >= 1, (path, old)
        open(path, "w", encoding="utf-8").write(t.replace(old, new, 1))

    def stray(d):
        shutil.copy(os.path.join(d, "zynkr-ops-weekly", "scripts", "ledger.py"), os.path.join(d, "ops-weekly-tracker", "scripts"))

    def gone(d):
        os.remove(os.path.join(d, "ops-weekly-doc", "scripts", "carryover.py"))

    def retired(d):
        with open(os.path.join(d, "zynkr-ops-weekly", "SKILL.md"), "a", encoding="utf-8") as f:
            f.write("\n### `nudge` (Mon 09:00)\n\nback from the dead\n")

    def lost_mode(d):
        edit(os.path.join(d, "ops-weekly-tracker", "SKILL.md"), "### `apply`", "### apply")

    def wrong_home(d):
        edit(os.path.join(d, "project-manager", "scripts", "beats.py"), '"minutes": "ops-weekly-doc"', '"minutes": "zynkr-ops-weekly"')

    def twice(d):
        p = os.path.join(d, "zynkr-ops-weekly", "scripts", "split-manifest.json")
        man = json.load(open(p, encoding="utf-8"))
        man["homes"]["project-manager"]["files"].append("scripts/parse_routing.py")
        json.dump(man, open(p, "w", encoding="utf-8"))
        shutil.copy(os.path.join(d, "zynkr-ops-weekly", "scripts", "parse_routing.py"), os.path.join(d, "project-manager", "scripts"))

    ok = True
    control, _, _ = check(fresh())
    if control:
        print("mutate: the unmodified copy fails: %s" % control[0])
        return 1
    for name, fn in (("a copy of ledger.py in the tracker", stray), ("a listed file deleted", gone),
                     ("a retired beat back", retired), ("a mode's section lost", lost_mode),
                     ("beats.py hands a mode elsewhere", wrong_home), ("one file listed in two homes", twice)):
        d = fresh()
        fn(d)
        problems, _, _ = check(d)
        print("mutate: %-36s %s" % (name, "caught" if problems else "MISSED"))
        ok = ok and bool(problems)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv):
    if "--mutate" in argv:
        return mutate()
    skills = SKILLS
    if "--skills" in argv:
        skills = argv[argv.index("--skills") + 1]
    problems, nfiles, nmodes = check(skills)
    for p in problems:
        print("FAIL " + p)
    if problems:
        return 1
    print("ok: %d files, %d modes, 4 homes" % (nfiles, nmodes))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
