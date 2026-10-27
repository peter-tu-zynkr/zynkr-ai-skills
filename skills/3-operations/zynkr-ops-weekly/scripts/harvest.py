#!/usr/bin/env python3
"""harvest.py — Thursday's collect (SKB-091 AC-12): each person's week, from the Wednesday harvest
routine's files into the Weekly Ledger's `Harvest` tab, and one Chat line for a quiet week.

The routine (weekly-insights, SKB-094) closes the week on Wednesday 20:00 and writes, in the Drive
folder `harvest.output_folder_id` / `<WEEK>` (WEEK = that Wednesday, YYYY-MM-DD):
  harvest-<slug>.md   `# <name> · week closing WEEK (LABEL)`, then `## <workstream>` sections with
                      **Shipped** · **In motion** · **Waiting on you** lines, or exactly
                      `本週無資料 · no digest arrived this week.`
  run-<WEEK>.json     {"status": "ok" | "partial", "week", "label", "people": {slug: {...}}}, written last

Like ledger.py, this script computes and the model executes: every step prints the exact MCP calls,
each with a path to save the tool's result to, word for word.

    harvest.py start --week W [--config PATH]   -> the Weeks row and the week folder search
    harvest.py files --dir D                    -> already recorded, the routine not done, or the folder listing
    harvest.py read  --dir D                    -> the run file and every harvest file to fetch
    harvest.py check --dir D                    -> rows.json for `ledger.py block start --tab Harvest`,
                                                   or "waiting" when the run file is missing or not ok
    harvest.py chase --dir D                    -> the one Chat post for the people with a quiet week
    harvest.py chased --dir D                   -> records that it went out
    harvest.py --selftest | --mutate

Exit codes are ledger.py's: 2 config or arguments · 3 input refused · 5 too many rows.
"""
import argparse
import json
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from ledger import Refuse, load_result, save_run, load_run, emit  # noqa: E402
from recap import person_of  # noqa: E402

FOLDER = "application/vnd.google-apps.folder"
H1 = re.compile(r"^# (.+?) · week closing (\d{4}-\d{2}-\d{2}) \((\d{4}-W\d{2})\)\s*$")
QUIET = "本週無資料"
KINDS = (("**Shipped**", "shipped"), ("**In motion**", "moving"), ("**Waiting on you**", "waiting"))
LISTED = re.compile(r'^- Name: "(.*)" \(ID: ([\w-]+), Type: ([^,)]+)')
HARVEST_FILE = re.compile(r"^harvest-([a-z0-9][a-z0-9-]*)\.md$")
PER_PERSON = 15


def wednesday(week):
    """The Wednesday that closes the harvest week: in the same ISO week as Thursday's collect."""
    return (ledger.monday(week) + timedelta(days=2)).isoformat()


def load_cfg(path=None):
    cfg = ledger.load_config(path)
    raw = json.load(open(cfg["path"], encoding="utf-8"))
    out = str((raw.get("harvest") or {}).get("output_folder_id") or "").strip()
    if not out or "<" in out:
        raise Refuse(2, "config has no harvest.output_folder_id (the routine's 'Weekly harvests' folder)")
    space = str((raw.get("space") or {}).get("id") or "")
    ids = {k: v for k, v in (raw.get("chat_ids") or {}).items() if not k.startswith("$") and isinstance(v, str)}
    roster = [k for k in ids if not k.startswith("users/")]
    aliases = {k: v for k, v in ((raw.get("routine") or {}).get("name_aliases") or {}).items()
               if not k.startswith("$") and isinstance(v, str)}
    cfg.update(out_folder=out, space=space if space.startswith("spaces/") else "", chat_ids=ids, roster=roster,
               aliases=aliases)
    return cfg


def drive_call(run, tool, args, name):
    return ledger.call(tool, dict({"user_google_email": run["account"]}, **args), os.path.join(run["dir"], name + ".txt"))


def listed(text):
    """[(name, id, type)] from a search_drive_files result; refuses anything else."""
    first = text.strip().split("\n", 1)[0]
    if first.startswith("No files found"):
        return []
    if not (first.startswith("Found ") and " files " in first):
        raise Refuse(3, "not a search_drive_files result: %r" % first[:120])
    return [m.groups() for m in (LISTED.match(x.strip()) for x in text.split("\n")) if m]


def content(path):
    """The body of a get_drive_file_content result, after its `--- CONTENT ---` line."""
    text = load_result(path)
    head, sep, body = text.partition("--- CONTENT ---\n")
    if not sep:
        raise Refuse(3, "not a get_drive_file_content result: %s" % os.path.basename(path))
    return body


# ── the steps ────────────────────────────────────────────────────────────────
def h_start(week, config=None, now=None, base=None):
    cfg = load_cfg(config)
    k = ledger.week_index(week, cfg["epoch"])
    now = ledger.parse_now(now)
    d = os.path.join(base or os.path.join(ledger.state_dir(), "runs"),
                     "%s-collect-%s" % (week, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    wed = wednesday(week)
    r = ledger.weeks_row(k)
    run = dict(cfg, dir=d, week=week, k=k, wednesday=wed, weeks_row=r)
    save_run(run)
    q = "'%s' in parents and name = '%s' and mimeType = '%s' and trashed = false" % (cfg["out_folder"], wed, FOLDER)
    return {"dir": d, "week": week, "wednesday": wed,
            "calls": [ledger.read_call(run, cfg["ledger"], "Weeks!A%d:T%d" % (r, r), "wr"),
                      drive_call(run, "search_drive_files", {"query": q, "page_size": 5}, "folder")]}


def h_files(d):
    run = load_run(d)
    r = run["weeks_row"]
    wr = ledger.parse_values(load_result(os.path.join(d, "wr.txt")), run["ledger"], "Weeks!A%d:T%d" % (r, r))
    row = ledger.pad(wr[0], 20) if wr else [""] * 20
    if row[0] not in ("", run["week"]):
        raise Refuse(4, "Weeks row %d belongs to %s, not %s" % (r, row[0], run["week"]))
    if row[18] == "ok":
        return {"already": True, "delivered": "already-collected;Weeks!S%d" % r}
    hits = [x for x in listed(load_result(os.path.join(d, "folder.txt"))) if x[0] == run["wednesday"] and x[2] == FOLDER]
    if not hits:
        return {"waiting": True, "delivered": "harvest-not-ready;no-%s-folder" % run["wednesday"]}
    if len(hits) > 1:
        raise Refuse(3, "two %s folders in the harvest output folder; the routine reuses one" % run["wednesday"])
    run["folder"] = hits[0][1]
    save_run(run)
    q = "'%s' in parents and trashed = false" % run["folder"]
    return {"calls": [drive_call(run, "search_drive_files", {"query": q, "page_size": 50}, "files")]}


def h_read(d):
    run = load_run(d)
    if not run.get("folder"):
        raise Refuse(2, "run `harvest.py files` first")
    files = listed(load_result(os.path.join(d, "files.txt")))
    names = [f[0] for f in files]
    dup = sorted({x for x in names if names.count(x) > 1})
    if dup:
        raise Refuse(3, "the week folder holds %s twice" % dup[0])
    want = "run-%s.json" % run["wednesday"]
    runf = [f for f in files if f[0] == want]
    if not runf:
        return {"waiting": True, "delivered": "harvest-not-ready;no-%s" % want}
    harvests = {HARVEST_FILE.match(f[0]).group(1): f[1] for f in files if HARVEST_FILE.match(f[0])}
    run["harvests"] = harvests
    save_run(run)
    calls = [drive_call(run, "get_drive_file_content", {"file_id": runf[0][1]}, "run")]
    calls += [drive_call(run, "get_drive_file_content", {"file_id": fid}, "h-" + slug) for slug, fid in sorted(harvests.items())]
    return {"calls": calls}


def parse_harvest(text, wed, week):
    """(name, quiet, [(workstream, kind, text)]) from one harvest file, checked against its week."""
    lines = [x.rstrip() for x in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    m = H1.match(lines[0]) if lines else None
    if not m:
        raise Refuse(3, "a harvest file does not open with `# <name> · week closing <WEEK> (<LABEL>)`")
    name, w, label = m.groups()
    if (w, label) != (wed, week):
        raise Refuse(3, "%s's harvest is for %s (%s), not %s (%s)" % (name, w, label, wed, week))
    rest = [x for x in lines[1:] if x.strip()]
    if rest and rest[0].strip().startswith(QUIET):
        return name.strip(), True, []
    out, ws, kind = [], "", None
    for x in rest:
        s = x.strip()
        if s.startswith("## "):
            ws, kind = s[3:].strip(), None
            continue
        if not ws:
            continue                                   # the summary line under the title
        mark = next(((tag, k) for tag, k in KINDS if s.startswith(tag)), None)
        if mark:
            kind = mark[1]
            s = s[len(mark[0]):].lstrip(" —–:-").strip()
            if not s:
                continue
        if kind is None:
            continue
        s = re.sub(r"^[-*•]\s+", "", s).strip()
        if s:
            out.append((ws, kind, s))
    return name.strip(), False, out


def h_check(d, now=None):
    run = load_run(d)
    if "harvests" not in run:
        raise Refuse(2, "run `harvest.py read` first")
    try:
        meta = json.loads(content(os.path.join(d, "run.txt")))
    except ValueError:
        return {"waiting": True, "delivered": "harvest-not-ready;run-file-unreadable"}
    status = meta.get("status") if isinstance(meta, dict) else None
    if status != "ok":
        return {"waiting": True, "delivered": "harvest-not-ready;run-%s" % (status or "unknown")}
    if meta.get("week") != run["wednesday"]:
        raise Refuse(3, "the run file is for %r, not %s" % (meta.get("week"), run["wednesday"]))
    people = sorted((meta.get("people") or {}).keys())
    missing = [p for p in people if p not in run["harvests"]]
    if missing:
        raise Refuse(3, "the run file says ok but %s has no harvest file" % missing[0])
    at = ledger.stamp(ledger.parse_now(now))
    rows, quiet, per = [], [], {}
    for slug in sorted(run["harvests"]):
        fname = "harvest-%s.md" % slug
        name, is_quiet, items = parse_harvest(content(os.path.join(d, "h-%s.txt" % slug)), run["wednesday"], run["week"])
        who = person_of(run, name)
        if is_quiet:
            quiet.append(who)
            rows.append([run["week"], at, slug, who, "", "quiet", QUIET, fname])
            continue
        order = {"waiting": 0, "shipped": 1, "moving": 2}
        items = sorted(items, key=lambda x: order[x[1]])[:PER_PERSON]
        per[who] = len(items)
        rows += [[run["week"], at, slug, who, ws, kind, text, fname] for ws, kind, text in items]
    if len(rows) > ledger.BLOCKS["Harvest"][0]:
        raise Refuse(5, "%d harvest lines do not fit the %d-row Harvest block" % (len(rows), ledger.BLOCKS["Harvest"][0]))
    path = os.path.join(d, "rows.json")
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(quiet, open(quiet_path(run["week"]), "w", encoding="utf-8"), ensure_ascii=False)
    run.update(checked=True, quiet=quiet)
    save_run(run)
    return {"week": run["week"], "rows": len(rows), "rows_path": path, "people": per, "quiet": quiet}


def quiet_path(week):
    return os.path.join(ledger.state_dir(), "%s.harvest-quiet.json" % week)


def chased_path(week):
    return os.path.join(ledger.state_dir(), "%s.harvest-chased" % week)


def mention(run, who):
    """`<users/ID>` when the config knows this person's Chat id, else their name: Chat only links an id."""
    email = run["chat_ids"].get(who, "")
    ids = [k for k, v in run["chat_ids"].items() if k.startswith("users/") and email and v == email]
    return "<%s>" % ids[0] if len(ids) == 1 else "@" + who


def h_chase(d):
    run = load_run(d)
    week = run["week"]
    if os.path.exists(chased_path(week)):
        return {"chase": "already"}
    if not os.path.exists(quiet_path(week)):
        raise Refuse(2, "run `harvest.py check` first")
    quiet = [q for q in json.load(open(quiet_path(week), encoding="utf-8")) if q in run["roster"]]
    if not quiet:
        open(chased_path(week), "w").write("none\n")
        return {"chase": "none"}
    if not run["space"]:
        raise Refuse(2, "config has no space.id (spaces/…) to post the chase to")
    text = ("%s 這週的 harvest 沒有資料，是比較安靜的一週嗎？有做的事在今天下午一點前回在這裡就好"
            % " ".join(mention(run, q) for q in quiet))
    return {"chase": "send", "quiet": quiet,
            "call": ledger.call("send_message", {"user_google_email": run["account"], "space_id": run["space"],
                                                 "message_text": text})}


def h_chased(d):
    run = load_run(d)
    open(chased_path(run["week"]), "w").write(ledger.stamp(ledger.parse_now()) + "\n")
    return {"chased": True}


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("start")
    s.add_argument("--week", required=True)
    s.add_argument("--config")
    for name in ("files", "read", "check", "chase", "chased"):
        sub.add_parser(name).add_argument("--dir", required=True)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd == "start":
            emit(h_start(a.week, a.config))
        elif a.cmd in ("files", "read", "check", "chase", "chased"):
            emit({"files": h_files, "read": h_read, "check": h_check, "chase": h_chase, "chased": h_chased}[a.cmd](a.dir))
        else:
            ap.print_help()
            return 2
    except Refuse as e:
        print("harvest.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


# ── selftest: the routine's exact file shapes ────────────────────────────────
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
        except Refuse as e:
            if e.code != code:
                fails.append("%s: exit %d, want %d (%s)" % (name, e.code, code, e))
            return
        fails.append("%s: did not refuse (want exit %d)" % (name, code))

    check("the Wednesday of the week", wednesday("2026-W45"), "2026-11-04")
    full = ("# Ann Lee · week closing 2026-11-04 (2026-W45)\n4 sessions across SEO, Atlas\n\n"
            "## SEO\n**Shipped** — three articles live (abc1234)\n- the sitemap fixed (zynkr-website#12)\n"
            "**In motion**\n- the FAQ page, draft (2026-11-03)\n**Waiting on you**\n- needs input: which keyword first (2026-11-02)\n\n"
            "## Atlas\n**Shipped**\n* ATL-140 merged (atlas#83)\n")
    name, quiet, items = parse_harvest(full, "2026-11-04", "2026-W45")
    check("a full harvest", (name, quiet, items),
          ("Ann Lee", False, [("SEO", "shipped", "three articles live (abc1234)"),
                              ("SEO", "shipped", "the sitemap fixed (zynkr-website#12)"),
                              ("SEO", "moving", "the FAQ page, draft (2026-11-03)"),
                              ("SEO", "waiting", "needs input: which keyword first (2026-11-02)"),
                              ("Atlas", "shipped", "ATL-140 merged (atlas#83)")]))
    empty = "# Peter Tu · week closing 2026-11-04 (2026-W45)\n本週無資料 · no digest arrived this week.\n"
    check("本週無資料", parse_harvest(empty, "2026-11-04", "2026-W45"), ("Peter Tu", True, []))
    refuses("a harvest of another week", 3, parse_harvest, empty.replace("2026-11-04", "2026-10-28"), "2026-11-04", "2026-W45")
    refuses("a file that is not a harvest", 3, parse_harvest, "hello", "2026-11-04", "2026-W45")
    lst = ('Found 2 files for x@example.com matching \'q\':\n'
           '- Name: "2026-11-04" (ID: F1, Type: application/vnd.google-apps.folder, Created: x) Link: y\n'
           '- Name: "harvest-ann.md" (ID: H1, Type: text/markdown, Size: 9) Link: y\n')
    check("a Drive listing", listed(lst), [("2026-11-04", "F1", FOLDER), ("harvest-ann.md", "H1", "text/markdown")])
    refuses("an error is not a listing", 3, listed, "Error: invalid_grant")

    tmp = tempfile.mkdtemp(prefix="harvest-selftest-")
    os.environ["ZYNKR_OPS_WEEKLY_STATE"] = os.path.join(tmp, "state")
    os.makedirs(os.environ["ZYNKR_OPS_WEEKLY_STATE"])
    try:
        cfgp = os.path.join(tmp, "cfg.json")
        json.dump({"google_account": "owner@example.com", "space": {"id": "spaces/S1"},
                   "chat_ids": {"Ann Lee": "ann@example.com", "users/111": "ann@example.com", "Peter Tu": "p@example.com"},
                   "sources": {"main_tracker": {"id": "TRK", "tab": "T", "cycle": "2026H2"},
                               "ledger": {"id": "LED", "epoch_week": "2026-W40"}},
                   "harvest": {"output_folder_id": "OUT"}}, open(cfgp, "w"), ensure_ascii=False)
        K = ledger.week_index("2026-W45", "2026-W40")

        def weeks(row=None):
            r = row or []
            rng = "Weeks!A%d:T%d" % (ledger.weeks_row(K), ledger.weeks_row(K))
            if not r:
                return "No data found in range '%s' for x." % rng
            return "Successfully read 1 rows from range '%s' in spreadsheet LED for x:\nRow  1: %s" % (rng, r)

        def drive(name, body):
            return 'File: "%s" (ID: x, Type: y)\nLink: z\n\n--- CONTENT ---\n%s' % (name, body)

        def go(folder=1, run_body=None, files=None, weeks_row=None, harvests=None):
            st = h_start("2026-W45", cfgp, "2026-11-05T09:05:00+08:00", base=os.path.join(tmp, "runs"))
            open(st["calls"][0]["save"], "w").write(weeks(weeks_row))
            one = '- Name: "2026-11-04" (ID: F%d, Type: %s)\n'
            open(st["calls"][1]["save"], "w").write(
                ("Found %d files for x matching 'q':\n" % folder + "".join(one % (i, FOLDER) for i in range(folder)))
                if folder else "No files found for 'q'.")
            f = h_files(st["dir"])
            if "calls" not in f:
                return f
            names = files if files is not None else ["run-2026-11-04.json", "harvest-ann.md", "harvest-peter.md"]
            open(f["calls"][0]["save"], "w").write("Found %d files for x matching 'q':\n" % len(names) + "".join(
                '- Name: "%s" (ID: id-%s, Type: text/markdown)\n' % (n, re.sub(r"\W", "-", n)) for n in names))
            r = h_read(st["dir"])
            if "calls" not in r:
                return r
            bodies = dict({"run": run_body if run_body is not None else json.dumps(
                {"status": "ok", "week": "2026-11-04", "label": "2026-W45", "people": {"ann": {}, "peter": {}}}),
                "h-ann": full, "h-peter": empty}, **(harvests or {}))
            for c in r["calls"]:
                key = os.path.basename(c["save"])[:-4]
                open(c["save"], "w", encoding="utf-8").write(drive(key, bodies[key]))
            return dict(h_check(st["dir"], "2026-11-05T09:06:00+08:00"), dir=st["dir"])

        ok = go()
        rows = json.load(open(ok["rows_path"], encoding="utf-8"))
        check("rows: waiting first, then shipped, then moving; a quiet week is one row",
              [(r[3], r[5], r[6][:12]) for r in rows],
              [("Ann Lee", "waiting", "needs input:"), ("Ann Lee", "shipped", "three articl"),
               ("Ann Lee", "shipped", "the sitemap "), ("Ann Lee", "shipped", "ATL-140 merg"),
               ("Ann Lee", "moving", "the FAQ page"), ("Peter Tu", "quiet", QUIET)])
        check("rows are the Harvest block's width", {len(r) for r in rows}, {len(ledger.HARVEST_HEADER)})
        check("the quiet people", ok["quiet"], ["Peter Tu"])
        ch = h_chase(ok["dir"])
        check("the chase: one post, a live mention where the id is known",
              (ch["chase"], ch["call"]["args"]["space_id"], ch["call"]["args"]["message_text"].split(" ")[0]),
              ("send", "spaces/S1", "@Peter"))
        h_chased(ok["dir"])
        check("the chase goes once", h_chase(ok["dir"]), {"chase": "already"})
        check("an id-known name is mentioned live", mention(load_run(ok["dir"]), "Ann Lee"), "<users/111>")
        refuses("two week folders", 3, go, 2)
        check("no week folder yet: wait", go(folder=0)["delivered"], "harvest-not-ready;no-2026-11-04-folder")
        check("no run file yet: wait", go(files=["harvest-ann.md"])["delivered"], "harvest-not-ready;no-run-2026-11-04.json")
        check("a partial run: wait", go(run_body=json.dumps({"status": "partial", "week": "2026-11-04", "people": {}}))["delivered"],
              "harvest-not-ready;run-partial")
        refuses("a run file that says ok but lacks a person's file", 3, go, 1,
                json.dumps({"status": "ok", "week": "2026-11-04", "people": {"ann": {}, "bob": {}}}))
        wk = ["2026-W45"] + [""] * 17 + ["ok", "2026-11-05T09:30:00+08:00"]
        check("recorded already", go(weeks_row=wk)["delivered"], "already-collected;Weeks!S%d" % ledger.weeks_row(K))
        refuses("the same file twice", 3, go, 1, None, ["run-2026-11-04.json", "harvest-ann.md", "harvest-ann.md"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("harvest.py selftest: %d FAILED" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("harvest.py selftest: all checks passed")
    return 0


MUTATIONS = [
    ("a harvest of another week is read", [("    if (w, label) != (wed, week):\n", "    if False:\n")]),
    ("a partial run is recorded", [('    if status != "ok":\n', '    if status not in ("ok", "partial"):\n')]),
    ("a missing person's file passes", [("    if missing:\n", "    if False:\n")]),
    ("an inline Shipped line is lost", [("            if not s:\n                continue\n", "            continue\n")]),
    ("lines keep the routine's order", [("        items = sorted(items, key=lambda x: order[x[1]])[:PER_PERSON]",
                                         "        items = items[:PER_PERSON]")]),
    ("the chase repeats", [("    if os.path.exists(chased_path(week)):\n", "    if False:\n")]),
    ("a recorded week is collected again", [('    if row[18] == "ok":\n', "    if False:\n")]),
    ("the Wednesday is the Monday", [("timedelta(days=2)", "timedelta(days=0)")]),
    ("two week folders pass", [("    if len(hits) > 1:\n", "    if False:\n")]),
]


def mutate():
    import shutil
    import subprocess
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")
    tmpd = tempfile.mkdtemp(prefix="harvest-mutate-")
    for f in ("ledger.py", "recap.py"):
        shutil.copy2(os.path.join(here, f), os.path.join(tmpd, f))

    def run(text):
        p = os.path.join(tmpd, "harvest_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    ok = True
    for name, pairs in MUTATIONS:
        bad = [old for old, _ in pairs if code.count(old) != 1]
        if bad:
            print("mutate: %-40s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = code
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        rc = run(mutated + marker + rest)
        print("mutate: %-40s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    shutil.rmtree(tmpd, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
