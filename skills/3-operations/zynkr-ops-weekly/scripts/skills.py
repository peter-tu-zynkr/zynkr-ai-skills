#!/usr/bin/env python3
"""Skill updates for the weekly loop (SKB-110): which version of each workbench skill Atlas approved.

The Wednesday `collect` records Atlas's `list_installs` (the zynkr-atlas MCP tool) as the week's
`Skills` block in the Weekly Ledger; Monday's `recap` compares that block with the week before's and
names, under 技能更新, each skill whose approved version moved, came in or left, with the title of
the pull request that carried it. Like ledger.py, this script computes and the model executes.

    skills.py rows --week W --list installs.txt --out rows.json [--now ISO]
                                   -> the Skills rows for `ledger.py block start --tab Skills`
    skills.py --selftest

Nothing in the list is trusted: a slug, a 40-hex commit, a folder under skills/ and an `owner/name`
repository, or the run stops; a version of any other shape than a short semver-like word is kept as "". Exit codes are ledger.py's (3 input refused).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from ledger import Refuse, emit, load_result  # noqa: E402

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")             # Atlas's own slug rule
VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]{0,39}$")  # anything else is kept as "", never refused
HEX40 = re.compile(r"^[0-9a-f]{40}$")
FOLDER = re.compile(r"^skills(/[A-Za-z0-9._-]+)+$")
REPO = re.compile(r"^[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$")
FENCE = re.compile(r"```json\n(.*?)\n```", re.S)
SHOWN = 12                                                  # the mail's lines; the rest are counted


def parse_installs(text):
    """A saved list_installs result -> (repository, [{slug, version, commit, folder}]). The tool's text
    carries the list as one fenced JSON block; a saved structuredContent object is read as it is."""
    text = (text or "").strip()
    data = None
    m = FENCE.search(text)
    try:
        data = json.loads(m.group(1)) if m else json.loads(text)
    except ValueError:
        raise Refuse(3, "the list_installs result holds no readable list")
    if isinstance(data, dict) and isinstance(data.get("structuredContent"), dict):
        data = data["structuredContent"]
    if not isinstance(data, dict) or "folders" not in data:
        raise Refuse(3, "the list_installs result holds no folders")
    repo = data.get("repository")
    if repo is None:
        return None, []
    if not isinstance(repo, str) or not REPO.match(repo):
        raise Refuse(3, "the list names a bad repository: %r" % (repo,))
    if not isinstance(data["folders"], list):
        raise Refuse(3, "the list's folders are not a list")
    out, seen = [], set()
    for i, f in enumerate(data["folders"]):
        if not isinstance(f, dict):
            raise Refuse(3, "folders[%d] is not an object" % i)
        slug, version, commit, folder = (str(f.get(k) or "") for k in ("slug", "version", "commit", "folder"))
        if not SLUG.match(slug) or slug in seen:
            raise Refuse(3, "folders[%d]: bad or repeated slug %r" % (i, slug))
        if not VERSION.match(version):
            version = ""
        if not HEX40.match(commit):
            raise Refuse(3, "folders[%d] (%s): bad commit" % (i, slug))
        if not FOLDER.match(folder) or any(s in (".", "..") for s in folder.split("/")):
            raise Refuse(3, "folders[%d] (%s): bad folder" % (i, slug))
        seen.add(slug)
        out.append({"slug": slug, "version": version, "commit": commit, "folder": folder})
    if len(out) > ledger.BLOCKS["Skills"][0]:
        raise Refuse(5, "%d skills do not fit the %d-row Skills block" % (len(out), ledger.BLOCKS["Skills"][0]))
    return repo, sorted(out, key=lambda x: x["slug"])


def rows_for(week, taken_at, repo, folders):
    return [[week, taken_at, f["slug"], f["version"], f["commit"], f["folder"], repo] for f in folders]


def r_rows(week, list_path, out, now=None):
    ledger.monday(week)
    repo, folders = parse_installs(load_result(list_path))
    if repo is None:
        raise Refuse(3, "no workbench serves this workspace: nothing to record")
    rows = rows_for(week, ledger.stamp(ledger.parse_now(now)), repo, folders)
    json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    return {"week": week, "skills": len(rows), "repo": repo, "rows_path": out}


def from_rows(rows, week):
    """Skills block rows (as read back) -> {slug: {version, commit, repo}} for that week alone."""
    got = {}
    for r in (ledger.pad(x, 7) for x in rows):
        if r[0] != week or not SLUG.match(r[2]) or not HEX40.match(r[4]) or not REPO.match(r[6]):
            continue
        got[r[2]] = {"version": r[3], "commit": r[4], "repo": r[6]}
    return got


def diff(prev, cur):
    """Two weeks' {slug: …} -> moved (another commit), new, gone; each sorted by slug."""
    moved = [{"slug": s, "old": prev[s]["version"], "new": cur[s]["version"], "commit": cur[s]["commit"],
              "repo": cur[s]["repo"]}
             for s in sorted(cur) if s in prev and prev[s]["commit"] != cur[s]["commit"]]
    new = [{"slug": s, "new": cur[s]["version"], "commit": cur[s]["commit"], "repo": cur[s]["repo"]}
           for s in sorted(cur) if s not in prev]
    gone = [{"slug": s, "old": prev[s]["version"]} for s in sorted(prev) if s not in cur]
    return {"moved": moved, "new": new, "gone": gone}


def pr_calls(changes, d):
    """One `gh api` per commit that moved or came in: the pull request that merged it, if any."""
    calls, seen = [], set()
    for c in changes["moved"] + changes["new"]:
        if c["commit"] in seen:
            continue
        seen.add(c["commit"])
        calls.append({"bash": "gh api repos/%s/commits/%s/pulls --jq '[.[] | {number, title, html_url}]'"
                              % (c["repo"], c["commit"]),
                      "save": os.path.join(d, "pr-%s.txt" % c["commit"][:12])})
    return calls


def read_pr(d, commit):
    """The saved `gh api` answer for this commit -> {number, title, url}, or None (no PR, or unreadable)."""
    p = os.path.join(d, "pr-%s.txt" % commit[:12])
    try:
        got = json.loads(open(p, encoding="utf-8").read().strip() or "[]")
    except (OSError, ValueError):
        return None
    for x in got if isinstance(got, list) else []:
        if not isinstance(x, dict):
            continue
        n, t, u = x.get("number"), x.get("title"), x.get("html_url")
        if isinstance(n, int) and isinstance(t, str) and isinstance(u, str) and u.startswith("https://github.com/"):
            return {"number": n, "title": " ".join(t.split())[:120], "url": u}
    return None


def lines_for(changes, d):
    """The 技能更新 lines, in order: moved, new, gone. Each {text, url, number}."""
    out = []
    for c in changes["moved"] + changes["new"]:
        pr = read_pr(d, c["commit"])
        if "old" not in c:
            head = "%s %s（新技能）" % (c["slug"], c["new"] or "?")
        elif c["old"] == c["new"]:
            head = "%s %s（重新核准）" % (c["slug"], c["new"] or "?")     # another commit at the same version
        else:
            head = "%s %s → %s" % (c["slug"], c["old"] or "?", c["new"] or "?")
        out.append({"text": head + (" · " + pr["title"] if pr else ""), "url": pr["url"] if pr else "",
                    "number": pr["number"] if pr else None})
    for c in changes["gone"]:
        out.append({"text": "%s %s（下架）" % (c["slug"], c["old"] or "?"), "url": "", "number": None})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("rows")
    r.add_argument("--week", required=True)
    r.add_argument("--list", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--now")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.cmd == "rows":
            emit(r_rows(a.week, a.list, a.out, a.now))
        else:
            ap.print_help()
            return 2
    except Refuse as e:
        print("skills.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


def selftest():
    import shutil
    import tempfile
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (name, got, want))

    def refuses(name, code, fn, *args):
        try:
            fn(*args)
            fails.append("%s: did not refuse" % name)
        except Refuse as e:
            check(name, e.code, code)

    c1, c2, c3 = "1" * 40, "2" * 40, "3" * 40
    lst = {"repository": "owner/workbench", "project_agents": [],
           "folders": [{"slug": "beta", "version": "1.2.0", "commit": c2, "folder": "skills/6-engineer/beta", "tree": c3},
                       {"slug": "alpha", "version": "1.0.0", "commit": c1, "folder": "skills/1-x/alpha", "tree": c3}]}
    text = "2 skill folder(s)…\n\n```json\n%s\n```" % json.dumps(lst)
    repo, fs = parse_installs(text)
    check("the fenced block is read", (repo, [f["slug"] for f in fs]), ("owner/workbench", ["alpha", "beta"]))
    check("a saved structuredContent reads the same", parse_installs(json.dumps({"structuredContent": lst})), (repo, fs))
    check("no workbench", parse_installs(json.dumps({"repository": None, "folders": []})), (None, []))
    check("an odd version is kept, an unsafe one blanked; the list still reads",
          [f["version"] for f in parse_installs(json.dumps(dict(lst, folders=[dict(lst["folders"][0], version="v1"),
                                                                              dict(lst["folders"][1], version="<b>1</b>")])))[1]],
          ["", "v1"])
    for name, bad in (("bad slug", {"slug": "Bad Slug"}),
                      ("bad commit", {"commit": "abc"}), ("bad folder", {"folder": "skills/../etc"}),
                      ("folder outside skills/", {"folder": "docs/x"})):
        f = dict(lst["folders"][0], **bad)
        refuses(name, 3, parse_installs, json.dumps(dict(lst, folders=[f])))
    refuses("a repeated slug", 3, parse_installs, json.dumps(dict(lst, folders=lst["folders"] + lst["folders"][:1])))
    refuses("a bad repository", 3, parse_installs, json.dumps(dict(lst, repository="not a repo")))
    refuses("garbage", 3, parse_installs, "no list here")
    rows = rows_for("2026-W45", "2026-11-05T09:00:00+08:00", repo, fs)
    check("rows", rows[0], ["2026-W45", "2026-11-05T09:00:00+08:00", "alpha", "1.0.0", c1, "skills/1-x/alpha", "owner/workbench"])
    check("rows fit the header", len(rows[0]), len(ledger.SKILLS_HEADER))

    prev = from_rows([["2026-W44", "", "alpha", "0.9.0", c3, "", "owner/workbench"],
                      ["2026-W44", "", "beta", "1.2.0", c2, "", "owner/workbench"],
                      ["2026-W44", "", "gone-one", "2.0.0", c3, "", "owner/workbench"],
                      ["2026-W43", "", "stray", "1.0.0", c3, "", "owner/workbench"]], "2026-W44")
    check("another week's row is not read", sorted(prev), ["alpha", "beta", "gone-one"])
    cur = from_rows(rows + [["2026-W45", "", "gamma", "1.0.0", c3, "", "owner/workbench"]], "2026-W45")
    ch = diff(prev, cur)
    check("moved", [(x["slug"], x["old"], x["new"]) for x in ch["moved"]], [("alpha", "0.9.0", "1.0.0")])
    check("unchanged beta is not listed", any(x["slug"] == "beta" for x in ch["moved"]), False)
    check("new", [x["slug"] for x in ch["new"]], ["gamma"])
    check("gone", [x["slug"] for x in ch["gone"]], ["gone-one"])
    check("nothing moved", diff(cur, cur), {"moved": [], "new": [], "gone": []})

    tmp = tempfile.mkdtemp(prefix="skills-selftest-")
    try:
        calls = pr_calls(ch, tmp)
        check("one gh call per commit", len(calls), 2)
        check("the gh call names the repo and the commit", calls[0]["bash"].startswith("gh api repos/owner/workbench/commits/%s/pulls" % c1), True)
        open(calls[0]["save"], "w").write(json.dumps([{"number": 111, "title": "feat: the  thing\n", "html_url": "https://github.com/owner/workbench/pull/111"}]))
        open(calls[1]["save"], "w").write("[]")
        ls = lines_for(ch, tmp)
        check("lines", [x["text"] for x in ls], ["alpha 0.9.0 → 1.0.0 · feat: the thing", "gamma 1.0.0（新技能）", "gone-one 2.0.0（下架）"])
        check("the PR link", (ls[0]["url"], ls[0]["number"]), ("https://github.com/owner/workbench/pull/111", 111))
        open(calls[0]["save"], "w").write(json.dumps([{"number": 1, "title": "x", "html_url": "javascript:alert(1)"}]))
        check("a link that is not GitHub's is dropped", lines_for(ch, tmp)[0]["url"], "")
        open(calls[0]["save"], "w").write(json.dumps([7, None, "x", {"number": 2, "title": "ok", "html_url": "https://github.com/o/r/pull/2"}]))
        check("non-object entries are skipped", lines_for(ch, tmp)[0]["number"], 2)
        open(calls[0]["save"], "w").write(json.dumps({"message": "Not Found"}))
        check("an error object reads as no PR", lines_for(ch, tmp)[0]["url"], "")
        same = diff({"alpha": {"version": "1.0.0", "commit": c1, "repo": "o/r"}}, {"alpha": {"version": "1.0.0", "commit": c2, "repo": "o/r"}})
        check("another commit at the same version is a re-approval", lines_for(same, tmp)[0]["text"], "alpha 1.0.0（重新核准）")
        os.remove(calls[1]["save"])
        check("a missing answer leaves the version line", lines_for(ch, tmp)[1]["text"], "gamma 1.0.0（新技能）")
        lp = os.path.join(tmp, "installs.txt")
        open(lp, "w", encoding="utf-8").write(text)
        out = os.path.join(tmp, "rows.json")
        res = r_rows("2026-W45", lp, out, "2026-11-05T09:00:00+08:00")
        check("rows CLI", (res["skills"], json.load(open(out))[1][2]), (2, "beta"))
        refuses("a bad week", 2, r_rows, "2026-45", lp, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("skills.py selftest: %d failure(s)" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("skills.py selftest: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
