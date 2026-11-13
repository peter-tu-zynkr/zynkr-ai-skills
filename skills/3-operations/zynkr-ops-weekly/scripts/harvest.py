#!/usr/bin/env python3
"""harvest.py — `collect` (SKB-091 AC-12): each person's week, from the Wednesday harvest
routine's files into the Weekly Ledger's `Harvest` tab, and one Chat line for a quiet week.

The routine (weekly-insights, SKB-094) closes the week on Wednesday 20:00 and writes, in the Drive
folder `harvest.output_folder_id` / `<WEEK>` (WEEK = that Wednesday, YYYY-MM-DD):
  harvest-<slug>.md   `# <name> · week closing WEEK (LABEL)`, then `## <workstream>` sections with
                      **Shipped** · **In motion** · **Waiting on you** lines, or exactly
                      `本週無資料 · no digest arrived this week.`
  run-<WEEK>.json     {"status": "ok" | "partial", "week", "label", "people": {slug: {...}}}, written last

Like ledger.py, this script computes and the model executes: every step prints the exact MCP calls,
each with a path to save the tool's result to, word for word.

    harvest.py start --week W [--config PATH]   -> the Weeks row, last week's Weeks row and the week
                                                   folder search
    harvest.py files --dir D                    -> already recorded, the routine not done, or the folder listing
    harvest.py read  --dir D                    -> the run file and every harvest file to fetch, and last
                                                   week's snapshot when the Ledger holds one
    harvest.py tags  --dir D                    -> the lines collect keeps and the tracker's open items:
                                                   the model ties each line to the item it moves and
                                                   saves that as tags.json (SKB-128)
    harvest.py check --dir D [--tags T.json]    -> rows.json for `ledger.py block start --tab Harvest`,
                                                   or "waiting" when the run file is missing or not ok.
                                                   Per person: a totals row (what the harvest held, by
                                                   kind), then at most 15 lines kept by kind, each with
                                                   the item its tag names when that item is in the
                                                   snapshot and still open (SKB-128)
    harvest.py chase --dir D                    -> the one Chat post for the people with a quiet week
    harvest.py chased --dir D                   -> records that it went out
    harvest.py --selftest | --mutate

Exit codes are ledger.py's: 2 config or arguments · 3 input refused · 5 too many rows.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from ledger import Refuse, load_result, save_run, load_run, emit  # noqa: E402
from recap import person_of, previous_week, read_block, snapshot_ok  # noqa: E402

FOLDER = "application/vnd.google-apps.folder"
H1 = re.compile(r"^# (.+?) · week closing (\d{4}-\d{2}-\d{2}) \((\d{4}-W\d{2})\)\s*$")
QUIET = "本週無資料"
KIND_OF = {"shipped": "shipped", "in motion": "moving", "waiting on you": "waiting"}
# A kind marker as the routine writes it (`**Shipped**`), and the shapes a model drifts to: a bullet before
# it, a colon or a count inside or after the bold, another case, a `###` heading, or the bare words on a
# line of their own. Text after a bold marker on the same line is that kind's first line. A plain line
# that merely starts with one of the words (`Shipped the newsletter`) is not a marker.
MARK = re.compile(r"^(?:[-*•]\s+)?\*\*\s*(shipped|in motion|waiting on you)\s*(?:\(\d+\))?\s*[:：]?\s*\*\*"
                  r"\s*(?:\(\d+\))?\s*[:：]?\s*(?:[—–-]\s*)?(.*)$", re.I)
MARK_BARE = re.compile(r"^(?:[-*•]\s+|#{3,6}\s*)?(shipped|in motion|waiting on you)\s*(?:\(\d+\))?\s*[:：]?$", re.I)
BULLET = re.compile(r"^[-*•]\s+")
LISTED = re.compile(r'^- Name: "(.*)" \(ID: ([\w-]+), Type: ([^,)]+)')
HARVEST_FILE = re.compile(r"^harvest-([a-z0-9][a-z0-9-]*)\.md$")
PER_PERSON = 15
# SKB-128: of a person's 15 lines, how many each kind may take, and who takes a share a kind leaves
# unused. Until then the waiting lines came first: in W46 13 of them left room for 2 of 27 shipped.
SHARE = (("waiting", 4), ("shipped", 8), ("moving", 3))
FILL = ("shipped", "waiting", "moving")
# A line that only says there is nothing to say is not an item: the routine wrote
# 「Nothing is waiting on you.」 under Waiting on you, and it reached the Doc as a blocker.
NOTHING = re.compile(r"^(?:nothing(?: is waiting on you| to report| this week)?|none|n/?a|[-—–])\.?$", re.I)
# SKB-128: a line is tied to the tracker item it moves, as last week's snapshot holds that item. A closed
# item takes no new line, and neither does a number the tracker holds twice.
TERMINAL = ("完成", "放棄")
NO_ITEM = ("", "-", "—", "none", "n/a", "不在 tracker", "不在tracker")     # a tag that says the tracker holds no item
SEEN_WEEKS = 12            # the weeks items-seen.json keeps: who harvested, and which items a line was tied to


def wednesday(week):
    """The Wednesday that closes the harvest week: in the same ISO week as the collect that reads it."""
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
    calls = [ledger.read_call(run, cfg["ledger"], "Weeks!A%d:T%d" % (r, r), "wr"),
             drive_call(run, "search_drive_files", {"query": q, "page_size": 5}, "folder")]
    if k >= 1:
        # SKB-128: last week's Weeks row says whether the Ledger holds a snapshot to tie lines to
        calls.append(ledger.read_call(run, cfg["ledger"], "Weeks!A%d:T%d" % (r - 1, r - 1), "wp"))
    return {"dir": d, "week": week, "wednesday": wed, "calls": calls}


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
    calls = [drive_call(run, "get_drive_file_content", {"file_id": runf[0][1]}, "run")]
    calls += [drive_call(run, "get_drive_file_content", {"file_id": fid}, "h-" + slug) for slug, fid in sorted(harvests.items())]
    pages, why = snapshot_pages(d, run)
    run.update(pages={"snap": pages} if pages else {}, snapshot=why)
    save_run(run)
    calls += [ledger.read_call(run, run["ledger"], rng, name) for name, rng in pages]
    return {"calls": calls, "snapshot": why}


def snapshot_pages(d, run):
    """([[name, range]], which week) for last week's snapshot block, or ([], why not). Tying lines to items
    is an extra: whatever goes wrong here, the harvest is still recorded, without items (SKB-128 AC-12)."""
    if run["k"] < 1:
        return [], "none: the Ledger's first week has no snapshot before it"
    r, prev = run["weeks_row"] - 1, previous_week(run["week"])
    try:
        wp = ledger.parse_values(load_result(os.path.join(d, "wp.txt")), run["ledger"], "Weeks!A%d:T%d" % (r, r))
    except Refuse as e:
        return [], "none: last week's Weeks row did not read (%s)" % e
    row = ledger.pad(wp[0], 20) if wp else [""] * 20
    if not snapshot_ok(row, prev, run["cycle"]):
        return [], "none: no committed snapshot for %s" % prev
    run["snap_row"] = row
    first, last = int(row[6]), int(row[7])
    return [["snap%d" % (i + 1), "Snapshot!A%d:P%d" % (a, min(a + ledger.PAGE - 1, last))]
            for i, a in enumerate(range(first, last + 1, ledger.PAGE))], prev


def tracker_items(d, run):
    """({#: item}, which week) from the snapshot pages `read` asked for, or (None, why not). An item holds
    its name, owner, helpers, priority and status; `twice` marks a number the tracker holds on two rows."""
    if not (run.get("pages") or {}).get("snap"):
        return None, run.get("snapshot") or "none: `read` asked for no snapshot"
    try:
        rows = read_block(dict(run, dir=d), "snap", run["snap_row"])
    except Refuse as e:
        return None, "none: the snapshot did not read (%s)" % e
    items, twice = {}, set()
    for r in rows:
        num = r[3].strip()
        if not num:
            continue
        if num in items:
            twice.add(num)
            continue
        items[num] = {"#": num, "項目": r[6].strip(), "Priority": r[9].strip(), "負責人": r[10].strip(),
                      "協助者": r[11].strip(), "狀態": r[14].strip()}
    for num in twice:
        items[num]["twice"] = True
    return items, run["snapshot"]


def parse_harvest(text, wed, week, skipped=None):
    """(name, quiet, [(workstream, kind, text)]) from one harvest file, checked against its week. A bullet
    set deeper than its list's first one is a detail of the line above it, and joins that line. `skipped`,
    when a list is given, gains every bullet under a workstream that belongs to no kind: lines the file's
    shape lost."""
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
    out, ws, kind, base, last = [], "", None, None, None
    for x in rest:
        s = x.strip()
        if s.startswith("## "):
            ws, kind, base, last = s[3:].strip(), None, None, None
            continue
        if not ws:
            continue                                   # the summary line under the title
        mark = MARK.match(s) or MARK_BARE.match(s)
        indent = len(x) - len(x.lstrip())
        if mark:
            kind, base, last = KIND_OF[mark.group(1).lower()], None, None
            s = (mark.group(2) if mark.re is MARK else "").strip()
            if not s:
                continue
            indent = None                              # a first line on the marker's own line sets no depth
        bullet = bool(BULLET.match(s))
        s = BULLET.sub("", s).strip()
        if kind is None:
            if bullet and s and skipped is not None:
                skipped.append(s)
            continue
        if not s or NOTHING.match(s):
            continue
        if bullet and indent is not None:
            if base is None:
                base = indent
            elif indent > base and last is not None:
                out[last] = (ws, kind, out[last][2] + "; " + s)
                continue
        out.append((ws, kind, s))
        last = len(out) - 1
    return name.strip(), False, out


def by_turn(lines):
    """One kind's lines with each workstream taking its turn: every workstream's first line, then every
    second one, and so on. The routine writes a harvest a workstream at a time, so the first lines of a
    long one would otherwise all come from the workstream it happened to start with."""
    groups = {}
    for x in lines:
        groups.setdefault(x[0], []).append(x)
    return [g[depth] for depth in range(max((len(g) for g in groups.values()), default=0))
            for g in groups.values() if len(g) > depth]


def keep(items, cap=PER_PERSON):
    """The lines `collect` records for one person, at most `cap`: each kind up to its share of the cap
    (4 waiting, 8 shipped and 3 moving of 15), then a share a kind left unused goes to shipped, to
    waiting and to moving, in that order. Returned as waiting, shipped, moving, and within a kind the
    workstreams take turns (`by_turn`), each in the routine's order."""
    by = {k: by_turn([x for x in items if x[1] == k]) for k, _ in SHARE}
    took = {k: by[k][:n * cap // PER_PERSON] for k, n in SHARE}
    left = cap - sum(len(v) for v in took.values())
    for k in FILL:
        more = by[k][len(took[k]):][:max(left, 0)]
        took[k] += more
        left -= len(more)
    return [x for k, _ in SHARE for x in took[k]]


def held(items):
    """How many lines of each kind a harvest held, before `keep`."""
    return {k: sum(1 for x in items if x[1] == k) for k in ledger.HARVEST_KINDS}


def fair_cap(counts, room):
    """The most lines each person may keep so that everyone's kept lines fit `room` rows: PER_PERSON when
    they do, else the largest cap that fits. A person who holds fewer lines than the cap leaves the rows
    they do not use to the others, so no line is dropped while the block has room. 0 when not even one
    line each fits."""
    for cap in range(PER_PERSON, 0, -1):
        if sum(min(n, cap) for n in counts) <= room:
            return cap
    return 0


def names_for(run, written):
    """{slug: the name each harvest is recorded under}, from the name each file was written with. A name the
    roster or the aliases hold is that person. A name that only shares its first word with one roster
    name is read as that person too (a file written `Peter`), but never when another file already is
    them: two harvests are not merged under one name, and the later one keeps the name it was written
    with, with its slug when that is taken as well. The nearer claim keeps the name: the roster's own
    spelling, then an alias, then a first word."""
    roster, aliases, taken, out = set(run.get("roster", [])), set(run.get("aliases", {})), set(), {}
    clean = {slug: " ".join(str(name or "").split()) for slug, name in written.items()}
    for slug in sorted(clean, key=lambda s: (clean[s] not in roster, clean[s] not in aliases, s)):
        who = person_of(run, clean[slug])
        if who in taken:
            who = clean[slug] if clean[slug] not in taken else "%s (%s)" % (clean[slug], slug)
        taken.add(who)
        out[slug] = who
    return out


def not_ready(d, run):
    """The `waiting` answer while the routine's run file is missing or not ok, else None. Refuses a run
    file of another week, or one that says ok for a person with no harvest file."""
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
    return None


def line_id(n, who, kind, text):
    """A kept line's id: its place among the week's kept lines and a hash of the line, so a tag written for
    one line never lands on another (a rerun, a harvest file that changed, a tags.json from another run)."""
    return "t%d-%s" % (n, hashlib.sha256(("%s\x1f%s\x1f%s" % (who, kind, text)).encode("utf-8")).hexdigest()[:6])


def kept_lines(d, run):
    """[(slug, who, quiet, items, [(id, workstream, kind, text)])] for every harvest file: what each person's
    harvest held and the lines `collect` keeps of it, each with its id. `tags` asks about exactly these
    lines and `check` records exactly these, so the model is never asked about a line that is not kept."""
    read, lost = {}, {}
    for slug in sorted(run["harvests"]):
        lost[slug] = []
        read[slug] = parse_harvest(content(os.path.join(d, "h-%s.txt" % slug)), run["wednesday"], run["week"], lost[slug])
    names = names_for(run, {slug: got[0] for slug, got in read.items()})
    for slug, (_, is_quiet, items) in read.items():
        # A file that holds bullets but no line under a kind is not a quiet week: its shape changed, and
        # recording it as 本週無資料 would drop a whole harvest without a word. Fail, so the owner hears.
        if not is_quiet and not items and lost[slug]:
            raise Refuse(3, "%s's harvest file holds %d lines but none under Shipped, In motion or Waiting on you: "
                            "its shape changed, so nothing is recorded" % (names[slug], len(lost[slug])))
    run["unread"] = {names[slug]: len(v) for slug, v in lost.items() if v}
    # a harvest that holds no line of any kind reads as a quiet week: the Doc says 本週無資料 for it
    parsed = [(slug, names[slug], is_quiet or not items, items) for slug, (_, is_quiet, items) in read.items()]
    size = ledger.BLOCKS["Harvest"][0]
    # The block always fits: a quiet week is one row, anyone else a totals row and their lines up to a
    # cap that a longer roster lowers, instead of failing the beat (SKB-128).
    cap = fair_cap([len(p[3]) for p in parsed if not p[2]], size - len(parsed))
    if cap < 1:
        raise Refuse(5, "%d people do not fit the %d-row Harvest block" % (len(parsed), size))
    out, n = [], 0
    for slug, who, is_quiet, items in parsed:
        kept = []
        for ws, kind, text in ([] if is_quiet else keep(items, cap)):
            n += 1
            kept.append((line_id(n, who, kind, text), ws, kind, text))
        out.append((slug, who, is_quiet, items, kept))
    return out


def h_tags(d):
    """The lines to tie to tracker items, and the items they may be tied to (SKB-128): the model writes
    {line id: item #} to `save`. With no snapshot to read there is nothing to tag, and `check` records
    every line without an item."""
    run = load_run(d)
    waiting = not_ready(d, run)
    if waiting:
        return waiting
    items, snapshot = tracker_items(d, run)
    if items is None:
        return {"tags": "none", "why": snapshot, "lines": [], "items": []}
    lines = [{"id": i, "who": who, "kind": kind, "workstream": ws, "text": text}
             for _, who, _, _, kept in kept_lines(d, run) for i, ws, kind, text in kept]
    return {"tags": "wanted" if lines else "none", "snapshot": snapshot, "lines": lines,
            "items": [{k: it[k] for k in ("#", "項目", "負責人", "狀態")}
                      for it in items.values() if it["狀態"] not in TERMINAL and not it.get("twice")],
            "save": os.path.join(d, "tags.json"),
            "format": '{"<line id>": "<the item\'s #, or an empty string when the tracker holds no item for the line>"}'}


def load_tags(path, wanted, items, snapshot):
    """({line id: item #}, report) for the kept lines' ids. A tag is used when it names an item of the
    snapshot that is still open and numbered once; an empty tag says the tracker holds no item for the
    line. Nothing here refuses (SKB-128 AC-12): no snapshot, no file, a file that does not parse, an
    unknown item or a closed one leaves the line without an item, and the report says which and why."""
    report = {"snapshot": snapshot, "given": False, "lines": len(wanted), "tagged": 0, "missing": [],
              "rejected": [], "unknown": []}
    if items is None:
        return {}, report
    if not path or not os.path.exists(path):
        report.update(missing=list(wanted), why="no tags file")
        return {}, report
    try:
        got = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        report.update(missing=list(wanted), why="the tags file does not parse (%s)" % e)
        return {}, report
    if not isinstance(got, dict):
        report.update(missing=list(wanted), why="the tags file is not an object of {line id: item #}")
        return {}, report
    ok, missing, rejected = {}, [], []
    for i in wanted:
        if i not in got:
            missing.append(i)
            continue
        tag = got[i]
        if not isinstance(tag, str):
            rejected.append({"id": i, "why": "not text"})
            continue
        num = tag.strip().lstrip("#").strip()
        if num.lower() in NO_ITEM:
            continue
        it = items.get(num)
        why = ("no item #%s in the snapshot" % num[:20] if not it
               else "#%s is on two rows of the tracker" % num if it.get("twice")
               else "#%s is %s" % (num, it["狀態"]) if it["狀態"] in TERMINAL else None)
        if why:
            rejected.append({"id": i, "why": why})
        else:
            ok[i] = num
    report.update(given=True, tagged=len(ok), missing=missing, rejected=rejected, unknown=sorted(set(got) - set(wanted)))
    return ok, report


def h_check(d, now=None, tags_path=None):
    run = load_run(d)
    waiting = not_ready(d, run)
    if waiting:
        return waiting
    at = ledger.stamp(ledger.parse_now(now))
    people = kept_lines(d, run)
    items, snapshot = tracker_items(d, run)
    tags, report = load_tags(tags_path, [i for p in people for i, _, _, _ in p[4]], items, snapshot)
    size = ledger.BLOCKS["Harvest"][0]
    rows, quiet, per, left_out = [], [], {}, {}
    for slug, who, is_quiet, held_items, kept in people:
        fname = "harvest-%s.md" % slug
        if is_quiet:
            quiet.append(who)
            rows.append([run["week"], at, slug, who, "", "quiet", QUIET, fname, ""])
            continue
        per[who] = len(kept)
        if len(kept) < len(held_items):
            left_out[who] = len(held_items) - len(kept)
        rows.append([run["week"], at, slug, who, "", ledger.HARVEST_TOTALS, ledger.totals_text(held(held_items)), fname, ""])
        rows += [[run["week"], at, slug, who, ws, kind, text, fname, tags.get(i, "")] for i, ws, kind, text in kept]
    if len(rows) > size:
        raise Refuse(5, "%d harvest lines do not fit the %d-row Harvest block" % (len(rows), size))
    path = os.path.join(d, "rows.json")
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(quiet, open(quiet_path(run["week"]), "w", encoding="utf-8"), ensure_ascii=False)
    if items is not None:
        # what `sections` names each item by, and what it reads a status from (SKB-128)
        json.dump({"week": run["week"], "snapshot": snapshot, "items": items},
                  open(items_path(run["week"]), "w", encoding="utf-8"), ensure_ascii=False)
        if report["given"]:
            remember(run["week"], [who for _, who, is_quiet, _, _ in people if not is_quiet], sorted(set(tags.values())))
    run.update(checked=True, quiet=quiet)
    save_run(run)
    return {"week": run["week"], "rows": len(rows), "rows_path": path, "people": per, "left_out": left_out,
            "quiet": quiet, "tags": report, "unread": run.get("unread", {})}


def items_path(week):
    """The snapshot's items as `collect` read them, for the week's `sections`."""
    return os.path.join(ledger.state_dir(), "%s.items.json" % week)


def seen_path():
    return os.path.join(ledger.state_dir(), "items-seen.json")


def load_seen():
    """{week: {"people": [...], "items": [...]}} for the weeks whose lines were tied to items; {} when the
    file is missing or does not read (it is rebuilt week by week, never trusted blindly)."""
    try:
        got = json.load(open(seen_path(), encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    weeks = got.get("weeks") if isinstance(got, dict) else None
    if not isinstance(weeks, dict):
        return {}

    def real(week):
        try:
            return bool(ledger.monday(week))           # a key shaped like a week that names none (W99)
        except (Refuse, ValueError, TypeError):
            return False

    def names(v):
        return isinstance(v, list) and all(isinstance(x, str) for x in v)

    return {w: v for w, v in weeks.items() if isinstance(w, str) and ledger.WEEK_RE.match(w) and real(w)
            and isinstance(v, dict) and names(v.get("people")) and names(v.get("items"))}


def remember(week, people, items):
    """Record who harvested this week and which items a line was tied to, keeping the last SEEN_WEEKS weeks.
    `sections` asks about an item only when its owner harvested for three such weeks and none tied a line
    to it. A rerun of the week replaces the week's entry."""
    weeks = load_seen()
    weeks[week] = {"people": sorted(set(people)), "items": items}
    keep_weeks = sorted(weeks, key=ledger.monday)[-SEEN_WEEKS:]
    json.dump({"weeks": {w: weeks[w] for w in keep_weeks}}, open(seen_path(), "w", encoding="utf-8"), ensure_ascii=False)


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
    text = ("%s 這週的 harvest 沒有資料，是比較安靜的一週嗎？有做的事在週四開會前回在這裡就好"
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
    for name in ("files", "read", "tags", "chase", "chased"):
        sub.add_parser(name).add_argument("--dir", required=True)
    c = sub.add_parser("check")
    c.add_argument("--dir", required=True)
    c.add_argument("--tags", help="the model's {line id: item #}, saved where `tags` said (SKB-128)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd == "start":
            emit(h_start(a.week, a.config))
        elif a.cmd == "check":
            emit(h_check(a.dir, tags_path=a.tags))
        elif a.cmd in ("files", "read", "tags", "chase", "chased"):
            emit({"files": h_files, "read": h_read, "tags": h_tags, "chase": h_chase, "chased": h_chased}[a.cmd](a.dir))
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
    nothing = ("# Ann Lee · week closing 2026-11-04 (2026-W45)\n2 sessions\n\n## SEO\n**Shipped** — one article live\n"
               "**Waiting on you** — Nothing is waiting on you.\n- None\n- nothing blocks the sitemap now\n")
    check("a line that only says nothing waits is not an item; one that starts with the word is",
          parse_harvest(nothing, "2026-11-04", "2026-W45")[2],
          [("SEO", "shipped", "one article live"), ("SEO", "waiting", "nothing blocks the sitemap now")])

    # SKB-128: lines are kept by kind, so waiting lines no longer take the block first
    def lines(**n):
        return [("WS", k, "%s %d" % (k, i)) for k in ledger.HARVEST_KINDS for i in range(n.get(k, 0))]

    def kinds(items):
        return [sum(1 for x in items if x[1] == k) for k in ("waiting", "shipped", "moving")]

    w46 = keep(lines(waiting=13, shipped=27, moving=7))
    check("W46's shape: 13 waiting lines leave shipped its share", kinds(w46), [4, 8, 3])
    check("kept as waiting, shipped, moving, each in the routine's order", [x[2] for x in w46][:6],
          ["waiting 0", "waiting 1", "waiting 2", "waiting 3", "shipped 0", "shipped 1"])
    check("a share no kind uses goes to shipped first", kinds(keep(lines(shipped=19))), [0, 15, 0])
    check("then to waiting, then to moving", kinds(keep(lines(shipped=2, waiting=9, moving=9))), [9, 2, 4])
    check("a small harvest is kept whole", kinds(keep(lines(shipped=3, waiting=1, moving=1))), [1, 3, 1])
    check("a smaller cap scales the shares", kinds(keep(lines(waiting=13, shipped=27, moving=7), 12)), [3, 7, 2])
    check("what a harvest held, by kind", held(lines(waiting=13, shipped=27, moving=7)),
          {"shipped": 27, "moving": 7, "waiting": 13})
    check("the totals row's text, and back", ledger.parse_totals(ledger.totals_text({"shipped": 27, "moving": 7, "waiting": 13})),
          {"shipped": 27, "moving": 7, "waiting": 13})
    check("an item's text is no totals row", (ledger.parse_totals("shipped 3 articles"), ledger.parse_totals("")), (None, None))
    turn = [(ws, "shipped", "%s %d" % (ws, i)) for ws, n in (("A", 4), ("B", 1), ("C", 2)) for i in range(n)]
    check("within a kind the workstreams take turns, each in its own order",
          [x[2] for x in by_turn(turn)], ["A 0", "B 0", "C 0", "A 1", "C 1", "A 2", "A 3"])
    check("so a long first workstream does not take the kind's whole share",
          sorted({x[0] for x in keep(turn + [("A", "shipped", "A %d" % i) for i in range(4, 20)], 6) if x[1] == "shipped"}),
          ["A", "B", "C"])
    check("no lines to take turns over", by_turn([]), [])
    # the block's rows are shared by need: a person who holds few lines leaves theirs to the others
    check("five short harvests and a long one: nothing is dropped while the block has room", fair_cap([2] * 5 + [15], 74), 15)
    check("six long harvests: the largest cap that fits", (fair_cap([20] * 6, 73), fair_cap([20] * 5 + [3], 74)), (12, 14))
    check("no room for one line each", fair_cap([5] * 40, 39), 0)
    people = {"roster": ["Ann Lee", "Peter Tu"], "aliases": {"Annie": "Ann Lee"}}
    check("a file is recorded under the roster's name: as written, by an alias, or by its first word",
          names_for(people, {"a": "Annie", "p": "Peter"}), {"a": "Ann Lee", "p": "Peter Tu"})
    check("two harvests never merge under one name: a first word that is already someone keeps its own name",
          names_for(people, {"peterc": "Peter Chen", "peter": "Peter Tu", "ann": " Ann  Lee "}),
          {"peter": "Peter Tu", "ann": "Ann Lee", "peterc": "Peter Chen"})
    check("the roster's own spelling keeps the name over an alias for it, whichever slug sorts first",
          names_for({"roster": ["Peter Tu"], "aliases": {"Pete": "Peter Tu"}}, {"pete": "Pete", "peter-tu": "Peter Tu"}),
          {"peter-tu": "Peter Tu", "pete": "Pete"})
    check("and the same name written twice keeps the second apart by its slug",
          names_for(people, {"ann": "Ann Lee", "ann2": "Ann Lee", "x": "Zoe", "y": "Zoe"}),
          {"ann": "Ann Lee", "ann2": "Ann Lee (ann2)", "x": "Zoe", "y": "Zoe (y)"})
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

        def sheet(rng, rows):
            if not rows:
                return "No data found in range '%s' for x." % rng
            return ("Successfully read %d rows from range '%s' in spreadsheet LED for x:\n" % (len(rows), rng)
                    + "".join("Row %2d: %s\n" % (i + 1, r) for i, r in enumerate(rows)))

        # SKB-128: last week's snapshot, as the Ledger holds it: # · name · owner · helpers · status
        tracker = [("1.01", "官網改版", "Ann Lee", "", "進行中"), ("1.02", "SEO 文章", "Ann Lee", "Peter Tu", "未開始"),
                   ("1.03", "舊專案", "Ann Lee", "", "完成"), ("2.01", "Atlas 搜尋", "Peter Tu", "", "暫停"),
                   ("2.02", "重複的", "Peter Tu", "", "進行中"), ("2.02", "重複的（另一列）", "Peter Tu", "", "進行中"),
                   ("2.03", "不做了", "Peter Tu", "", "放棄")]
        snap_first = ledger.slot(K - 1)[0]
        snap = [["2026-W44", "2026-10-31T10:00:00+08:00", "2026H2", num, "主", "子", name, "", "", "P1", owner, helpers,
                 "", "", status, ""] for num, name, owner, helpers, status in tracker]
        prev_row = ["2026-W44", "ok", "2026-10-31T10:00:00+08:00", "2026H2", "TRK", str(len(snap)), str(snap_first),
                    str(snap_first + len(snap) - 1), ledger.digest([r[3:] for r in snap]), ledger.LAYOUT]

        def go(folder=1, run_body=None, files=None, weeks_row=None, harvests=None, snapshot=None, tags=None):
            """One collect run. `snapshot`: None (last week has none), "ok", "unread" (its Weeks row is never
            saved) or "changed" (a cell differs from the committed digest). `tags`: a function from `tags`'
            output to what tags.json holds (an object, or text written as it is)."""
            st = h_start("2026-W45", cfgp, "2026-11-05T09:05:00+08:00", base=os.path.join(tmp, "runs"))
            open(st["calls"][0]["save"], "w").write(weeks(weeks_row))
            one = '- Name: "2026-11-04" (ID: F%d, Type: %s)\n'
            open(st["calls"][1]["save"], "w").write(
                ("Found %d files for x matching 'q':\n" % folder + "".join(one % (i, FOLDER) for i in range(folder)))
                if folder else "No files found for 'q'.")
            if snapshot != "unread":
                open(st["calls"][2]["save"], "w").write(sheet(st["calls"][2]["args"]["range_name"], [prev_row] if snapshot else []))
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
                if key.startswith("snap"):
                    a, b = (int(x) for x in re.match(r"^Snapshot!A(\d+):P(\d+)$", c["args"]["range_name"]).groups())
                    page = [list(x) for x in snap[a - snap_first:b - snap_first + 1]]
                    if snapshot == "changed":
                        page[0][14] = "完成"
                    open(c["save"], "w", encoding="utf-8").write(sheet(c["args"]["range_name"], page))
                else:
                    open(c["save"], "w", encoding="utf-8").write(drive(key, bodies[key]))
            asked = h_tags(st["dir"])
            path = None
            if tags is not None:
                path, body = os.path.join(st["dir"], "tags.json"), tags(asked)
                open(path, "w", encoding="utf-8").write(body if isinstance(body, str) else json.dumps(body, ensure_ascii=False))
            out = h_check(st["dir"], "2026-11-05T09:06:00+08:00", path)
            return dict(out, dir=st["dir"], read=r, asked=asked) if "rows_path" in out else out

        ok = go()
        rows = json.load(open(ok["rows_path"], encoding="utf-8"))
        check("rows: a person's totals, then waiting, shipped (SEO and Atlas taking turns), moving; a quiet week "
              "is one row", [(r[3], r[5], r[6][:12]) for r in rows],
              [("Ann Lee", "totals", "shipped 3 · "), ("Ann Lee", "waiting", "needs input:"),
               ("Ann Lee", "shipped", "three articl"), ("Ann Lee", "shipped", "ATL-140 merg"),
               ("Ann Lee", "shipped", "the sitemap "), ("Ann Lee", "moving", "the FAQ page"),
               ("Peter Tu", "quiet", QUIET)])
        check("rows are the Harvest block's width", {len(r) for r in rows}, {len(ledger.HARVEST_HEADER)})
        check("the quiet people", ok["quiet"], ["Peter Tu"])
        check("nothing was left out of a small harvest", ok["left_out"], {})
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

        # SKB-128: the block always fits, and a totals row says what each harvest held
        def big(name, n):
            return ("# %s · week closing 2026-11-04 (2026-W45)\n%d lines\n\n## Ops\n**Shipped**\n" % (name, n)
                    + "".join("- item %d\n" % i for i in range(n)))

        slugs = ["p%d" % i for i in range(1, 7)]
        many = go(files=["run-2026-11-04.json", "harvest-peter.md"] + ["harvest-%s.md" % s for s in slugs],
                  run_body=json.dumps({"status": "ok", "week": "2026-11-04", "people": dict.fromkeys(slugs + ["peter"], {})}),
                  harvests={"h-%s" % s: big("Person %s" % s, 20) for s in slugs})
        mrows = json.load(open(many["rows_path"], encoding="utf-8"))
        tot = [r[6] for r in mrows if r[5] == ledger.HARVEST_TOTALS]
        check("six people at 20 lines and a quiet one fit the block: 12 lines each, the rest named",
              (len(mrows), sorted(set(many["people"].values())), many["left_out"]["Person p1"]), (79, [12], 8))
        check("a totals row each, counting what the harvest held, not what was kept",
              (len(tot), tot[0]), (6, "shipped 20 · moving 0 · waiting 0"))
        bare = go(harvests={"h-ann": "# Ann Lee · week closing 2026-11-04 (2026-W45)\n1 session\n\n## SEO\n"
                                     "**Waiting on you** — Nothing is waiting on you.\n"})
        check("a harvest with no line of any kind is a quiet week",
              (bare["quiet"], [r[5] for r in json.load(open(bare["rows_path"], encoding="utf-8"))]),
              (["Ann Lee", "Peter Tu"], ["quiet", "quiet"]))
        # the kind markers as a model drifts to write them: a bullet before the marker, a colon or a count
        # in or after the bold, another case, a heading, the bare words. All read as the same three kinds.
        head = "# Ann Lee · week closing 2026-11-04 (2026-W45)\n3 sessions\n\n## SEO\n"

        def kinds(body):
            return [(k, t) for _, k, t in parse_harvest(head + body, "2026-11-04", "2026-W45")[2]]

        want3 = [("shipped", "one"), ("moving", "two"), ("waiting", "three")]
        for shape, body in (("a bullet before the marker", "- **Shipped**\n  - one\n- **In motion**\n  - two\n- **Waiting on you**\n  - three\n"),
                            ("a colon inside the bold", "**Shipped:**\n- one\n**In motion:**\n- two\n**Waiting on you:**\n- three\n"),
                            ("a colon after the bold", "**Shipped**:\n- one\n**In motion**:\n- two\n**Waiting on you**:\n- three\n"),
                            ("a count in the marker", "**Shipped (1)**\n- one\n**In motion** (1)\n- two\n**Waiting on you (1):**\n- three\n"),
                            ("another case", "**shipped**\n- one\n**IN MOTION**\n- two\n**Waiting On You**\n- three\n"),
                            ("headings", "### Shipped\n- one\n### In motion\n- two\n### Waiting on you\n- three\n"),
                            ("the bare words", "Shipped:\n- one\nIn motion\n- two\nWaiting on you:\n- three\n"),
                            ("blank lines between", "**Shipped**\n\n- one\n\n**In motion**\n\n- two\n\n**Waiting on you**\n\n- three\n"),
                            ("the first line on the marker's line", "**Shipped** — one\n**In motion**: two\n**Waiting on you** - three\n")):
            check("a marker written with %s is read" % shape, kinds(body), want3)
        check("a line that only starts with a kind's word is a line, not a marker",
              kinds("**In motion**\n- Shipped the first half, the rest is drafted\n- Waiting on you is the wrong name for this\n"),
              [("moving", "Shipped the first half, the rest is drafted"), ("moving", "Waiting on you is the wrong name for this")])
        check("a bullet set deeper than its list is a detail of the line above, not a line of its own",
              kinds("**Waiting on you**\n- send the draft to Jane\n  - it unblocks her review\n  - and the launch\n- say merge 12\n"),
              [("waiting", "send the draft to Jane; it unblocks her review; and the launch"), ("waiting", "say merge 12")])
        check("a list indented as a whole is still one line a bullet",
              kinds("**Shipped**\n  - one\n  - two\n**In motion**\n    - three\n"), [("shipped", "one"), ("shipped", "two"), ("moving", "three")])
        # a file whose shape no marker fits is not a quiet week: nothing is recorded and the beat fails loudly
        lost = "# Ann Lee · week closing 2026-11-04 (2026-W45)\n3 sessions\n\n## SEO\nDone this week\n- three articles live\n- the sitemap fixed\n"
        refuses("a harvest file that holds bullets under no kind is refused, not read as a quiet week", 3,
                lambda: go(harvests={"h-ann": lost}))
        note = go(harvests={"h-ann": "# Ann Lee · week closing 2026-11-04 (2026-W45)\n0 sessions\n\n## SEO\nNothing to report here.\n"})
        check("a note with no bullet under a workstream is still a quiet week", note["quiet"], ["Ann Lee", "Peter Tu"])
        part = go(harvests={"h-ann": "# Ann Lee · week closing 2026-11-04 (2026-W45)\n2 sessions\n\n## SEO\n- a stray bullet\n- another\n"
                                     "**Shipped**\n- three articles live\n"})
        check("bullets before a workstream's first marker are counted as unread, and the rest is recorded",
              (part["unread"], part["people"]), ({"Ann Lee": 2}, {"Ann Lee": 1}))
        check("a week with nothing unread says so", bare["unread"], {})
        uneven = go(files=["run-2026-11-04.json", "harvest-peter.md"] + ["harvest-%s.md" % s for s in slugs],
                    run_body=json.dumps({"status": "ok", "week": "2026-11-04", "people": dict.fromkeys(slugs + ["peter"], {})}),
                    harvests=dict({"h-%s" % s: big("Person %s" % s, 2) for s in slugs[:5]}, **{"h-p6": big("Person p6", 15)}))
        check("five short harvests and a long one: the long one keeps all fifteen", (uneven["people"]["Person p6"], uneven["left_out"]),
              (15, {}))
        twin = go(files=["run-2026-11-04.json", "harvest-ann.md", "harvest-peter.md", "harvest-peterc.md"],
                  run_body=json.dumps({"status": "ok", "week": "2026-11-04", "people": {"ann": {}, "peter": {}, "peterc": {}}}),
                  harvests={"h-peter": big("Peter Tu", 2), "h-peterc": big("Peter Chen", 3)})
        trows = json.load(open(twin["rows_path"], encoding="utf-8"))
        check("a harvest whose name only shares a first word with someone who has their own is not merged into theirs",
              ([(r[3], r[6]) for r in trows if r[5] == ledger.HARVEST_TOTALS], twin["people"]),
              ([("Ann Lee", "shipped 3 · moving 1 · waiting 1"), ("Peter Tu", "shipped 2 · moving 0 · waiting 0"),
                ("Peter Chen", "shipped 3 · moving 0 · waiting 0")], {"Ann Lee": 5, "Peter Tu": 2, "Peter Chen": 3}))

        # SKB-128: each kept line is tied to the tracker item it moves, as last week's snapshot holds it
        state = os.environ["ZYNKR_OPS_WEEKLY_STATE"]

        def by_text(asked):
            return {x["text"][:12]: x["id"] for x in asked["lines"]}

        def items_of(out):
            return [(r[6][:12], r[8]) for r in json.load(open(out["rows_path"], encoding="utf-8")) if r[5] in ledger.HARVEST_KINDS]

        def first(asked):
            ids = by_text(asked)
            return {ids["three articl"]: "1.02", ids["the sitemap "]: " #1.01 ", ids["ATL-140 merg"]: "2.01",
                    ids["the FAQ page"]: "1.03", ids["needs input:"]: "9.99", "t9-000000": "1.01"}

        ta = go(snapshot="ok", tags=first)
        check("read asks for last week's snapshot, by the rows its Weeks row names",
              ([c["args"]["range_name"] for c in ta["read"]["calls"] if c["tool"].endswith("read_sheet_values")], ta["read"]["snapshot"]),
              (["Snapshot!A%d:P%d" % (snap_first, snap_first + len(snap) - 1)], "2026-W44"))
        check("tags lists the kept lines, never a quiet person's, with ids that are a place and a hash",
              ([(x["who"], x["kind"], x["text"][:12]) for x in ta["asked"]["lines"]],
               all(re.fullmatch(r"t\d+-[0-9a-f]{6}", x["id"]) for x in ta["asked"]["lines"])),
              ([("Ann Lee", "waiting", "needs input:"), ("Ann Lee", "shipped", "three articl"), ("Ann Lee", "shipped", "ATL-140 merg"),
                ("Ann Lee", "shipped", "the sitemap "), ("Ann Lee", "moving", "the FAQ page")], True))
        check("tags offers the open items only: not a closed one, not a number on two rows",
              [(x["#"], x["狀態"]) for x in ta["asked"]["items"]], [("1.01", "進行中"), ("1.02", "未開始"), ("2.01", "暫停")])
        check("tags says where to save", (ta["asked"]["tags"], ta["asked"]["save"]), ("wanted", os.path.join(ta["dir"], "tags.json")))
        check("a tag for an open item is recorded, `#` and spaces or not; a closed or unknown item is not",
              items_of(ta), [("needs input:", ""), ("three articl", "1.02"), ("ATL-140 merg", "2.01"),
                             ("the sitemap ", "1.01"), ("the FAQ page", "")])
        ids = by_text(ta["asked"])
        check("the report: tagged, rejected with why, and an id of another run as unknown",
              ta["tags"], {"snapshot": "2026-W44", "given": True, "lines": 5, "tagged": 3, "missing": [],
                           "rejected": [{"id": ids["needs input:"], "why": "no item #9.99 in the snapshot"},
                                        {"id": ids["the FAQ page"], "why": "#1.03 is 完成"}],
                           "unknown": ["t9-000000"]})
        check("the totals and quiet rows carry no item", [r[8] for r in json.load(open(ta["rows_path"], encoding="utf-8")) if r[5] in ("totals", "quiet")], ["", ""])
        check("the week's items are kept for sections, as the snapshot held them",
              {n: (it["項目"], it["負責人"], it["狀態"], bool(it.get("twice"))) for n, it in
               json.load(open(os.path.join(state, "2026-W45.items.json"), encoding="utf-8"))["items"].items() if n in ("1.02", "2.02")},
              {"1.02": ("SEO 文章", "Ann Lee", "未開始", False), "2.02": ("重複的", "Peter Tu", "進行中", True)})
        check("who harvested and which items were touched is remembered for the week",
              load_seen(), {"2026-W45": {"people": ["Ann Lee"], "items": ["1.01", "1.02", "2.01"]}})

        def second(asked):
            ids = by_text(asked)
            return {ids["three articl"]: "2.02", ids["the sitemap "]: "2.03", ids["ATL-140 merg"]: "不在 Tracker",
                    ids["the FAQ page"]: 7}

        tb = go(snapshot="ok", tags=second)
        ids = by_text(tb["asked"])
        check("a number on two rows, an abandoned item and a tag that is not text are not recorded; an empty "
              "tag says the tracker holds no item; a line with no tag is named",
              (items_of(tb), tb["tags"]["rejected"], tb["tags"]["missing"], tb["tags"]["tagged"]),
              ([("needs input:", ""), ("three articl", ""), ("ATL-140 merg", ""), ("the sitemap ", ""), ("the FAQ page", "")],
               [{"id": ids["three articl"], "why": "#2.02 is on two rows of the tracker"},
                {"id": ids["the sitemap "], "why": "#2.03 is 放棄"}, {"id": ids["the FAQ page"], "why": "not text"}],
               [ids["needs input:"]], 0))
        check("a rerun of the week replaces what was remembered", load_seen()["2026-W45"]["items"], [])
        # a tags.json written for another run's lines: the line in the same place changed, so its tag does not fit
        stale = first(ta["asked"])
        other = go(snapshot="ok", harvests={"h-ann": full.replace("three articles live (abc1234)", "the pricing page redone (def5678)")},
                   tags=lambda asked: stale)
        check("a tag written for a line that changed since never lands on the line now in its place",
              (dict(items_of(other))["the pricing "], dict(items_of(other))["the sitemap "],
               by_text(ta["asked"])["three articl"] in other["tags"]["unknown"]), ("", "1.01", True))
        # AC-12: tying lines to items never fails the beat
        os.remove(os.path.join(state, "2026-W45.items.json"))
        os.remove(seen_path())
        none = go(tags=lambda asked: {"t1-000000": "1.01"})
        check("no committed snapshot: nothing to tag, every line recorded without an item, nothing remembered",
              (none["asked"]["tags"], none["asked"]["lines"], none["tags"]["snapshot"], {i for _, i in items_of(none)},
               os.path.exists(os.path.join(state, "2026-W45.items.json")), load_seen()),
              ("none", [], "none: no committed snapshot for 2026-W44", {""}, False, {}))
        unread = go(snapshot="unread", tags=lambda asked: {"t1-000000": "1.01"})
        check("last week's Weeks row never saved: the same",
              (unread["tags"]["snapshot"].startswith("none: last week's Weeks row did not read"), {i for _, i in items_of(unread)}),
              (True, {""}))
        changed = go(snapshot="changed", tags=lambda asked: {"t1-000000": "1.01"})
        check("a snapshot that does not match its committed digest is not used",
              (changed["asked"]["tags"], changed["tags"]["snapshot"].startswith("none: the snapshot did not read"),
               {i for _, i in items_of(changed)}),
              ("none", True, {""}))
        for body, why in (("{not json", "does not parse"), ("[1, 2]", "is not an object")):
            bad = go(snapshot="ok", tags=lambda asked, body=body: body)
            check("a tags file that %s: every line recorded without an item, and the report says why" % why,
                  (why in bad["tags"]["why"], bad["tags"]["given"], {i for _, i in items_of(bad)}, len(bad["tags"]["missing"])),
                  (True, False, {""}, 5))
        nofile = go(snapshot="ok")
        check("no tags file: the same, and the week is not remembered as tagged",
              (nofile["tags"]["why"], nofile["tags"]["given"], load_seen()), ("no tags file", False, {}))
        check("but the week's items are still kept for sections",
              os.path.exists(os.path.join(state, "2026-W45.items.json")), True)
        for i in range(SEEN_WEEKS + 3):
            remember("2026-W%02d" % (20 + i), ["Ann Lee", "Ann Lee"], ["1.01"])
        check("only the last weeks are remembered, a person once",
              (len(load_seen()), min(load_seen()), load_seen()["2026-W%02d" % (22 + SEEN_WEEKS)]["people"]),
              (SEEN_WEEKS, "2026-W23", ["Ann Lee"]))
        open(seen_path(), "w").write("{broken")
        check("a remembered file that does not read is started over", load_seen(), {})
        json.dump({"weeks": {"2026-W99": {"people": [], "items": []}, "2026-W44": {"people": ["Ann Lee"], "items": [["x"]]},
                             "2026-W43": {"people": [3], "items": []}, "2026-W42": {"people": ["Ann Lee"], "items": ["1.01"]},
                             "W42": {"people": [], "items": []}}}, open(seen_path(), "w"))
        check("a remembered week that names no week, or holds anything but names, is dropped", list(load_seen()), ["2026-W42"])
        try:
            remember("2026-W45", ["Ann Lee"], ["1.02"])
            check("…so remembering this week goes on", sorted(load_seen()), ["2026-W42", "2026-W45"])
        except Refuse as e:
            check("…so remembering this week goes on", "refused: %s" % e, "recorded")
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
    ("waiting lines take the block first again", [("    took = {k: by[k][:n * cap // PER_PERSON] for k, n in SHARE}",
                                                   "    took = {k: by[k][:cap if k == \"waiting\" else 0] for k, n in SHARE}")]),
    ("a share no kind uses is lost", [("        took[k] += more\n", "        pass\n")]),
    ("lines come back in the file's order", [("    return [x for k, _ in SHARE for x in took[k]]",
                                              "    return [x for x in items if any(x in v for v in took.values())]")]),
    ("no totals row", [("        rows.append([run[\"week\"], at, slug, who, \"\", ledger.HARVEST_TOTALS, ledger.totals_text(held(held_items)), fname, \"\"])\n",
                        "")]),
    ("the totals count what was kept", [("ledger.totals_text(held(held_items))",
                                         "ledger.totals_text(held([x[1:] for x in kept]))")]),
    ("the cap ignores the block's size", [("    cap = fair_cap([len(p[3]) for p in parsed if not p[2]], size - len(parsed))",
                                           "    cap = PER_PERSON")]),
    ("everyone gets the same share, used or not", [("        if sum(min(n, cap) for n in counts) <= room:",
                                                    "        if cap * len(counts) <= room:")]),
    ("a workstream's lines come all at once", [("    by = {k: by_turn([x for x in items if x[1] == k]) for k, _ in SHARE}",
                                                "    by = {k: [x for x in items if x[1] == k] for k, _ in SHARE}")]),
    ("two harvests merge under one name", [("        if who in taken:\n", "        if False:\n")]),
    ("a first word wins over the roster's own name", [
        ("    for slug in sorted(clean, key=lambda s: (clean[s] not in roster, clean[s] not in aliases, s)):",
         "    for slug in sorted(clean, reverse=True):")]),
    ("an alias wins over the roster's own name", [
        ("    for slug in sorted(clean, key=lambda s: (clean[s] not in roster, clean[s] not in aliases, s)):",
         "    for slug in sorted(clean, key=lambda s: (clean[s] not in roster | aliases, s)):")]),
    ("a line that says nothing is an item", [("        if not s or NOTHING.match(s):\n            continue\n        if bullet and indent is not None:",
                                              "        if not s:\n            continue\n        if bullet and indent is not None:")]),
    ("a bullet before a marker hides the marker", [('MARK = re.compile(r"^(?:[-*•]\\s+)?\\*\\*\\s*(shipped', 'MARK = re.compile(r"^\\*\\*\\s*(shipped')]),
    ("a colon inside the bold hides the marker", [
        ('(shipped|in motion|waiting on you)\\s*(?:\\(\\d+\\))?\\s*[:：]?\\s*\\*\\*"\n',
         '(shipped|in motion|waiting on you)\\s*(?:\\(\\d+\\))?\\s*\\*\\*"\n')]),
    ("a heading or the bare words are no marker", [("        mark = MARK.match(s) or MARK_BARE.match(s)", "        mark = MARK.match(s)")]),
    ("a line that starts with a kind's word is a marker", [
        ('MARK_BARE = re.compile(r"^(?:[-*•]\\s+|#{3,6}\\s*)?(shipped|in motion|waiting on you)\\s*(?:\\(\\d+\\))?\\s*[:：]?$", re.I)',
         'MARK_BARE = re.compile(r"^(?:[-*•]\\s+|#{3,6}\\s*)?(shipped|in motion|waiting on you)\\b", re.I)')]),
    ("a nested bullet is a line of its own", [("            elif indent > base and last is not None:", "            elif False:")]),
    ("a list indented as a whole is one line", [("            if base is None:\n                base = indent\n", "            if base is None:\n                base = -1\n")]),
    ("an unreadable harvest reads as a quiet week", [("        if not is_quiet and not items and lost[slug]:", "        if False:")]),
    ("a note under a workstream fails the beat", [("            if bullet and s and skipped is not None:", "            if s and skipped is not None:")]),
    ("the unread bullets go unreported", [('"quiet": quiet, "tags": report, "unread": run.get("unread", {})}', '"quiet": quiet, "tags": report, "unread": {}}')]),
    ("a remembered week that names no week is kept", [("if isinstance(w, str) and ledger.WEEK_RE.match(w) and real(w)", "if isinstance(w, str) and ledger.WEEK_RE.match(w)")]),
    ("a remembered week holding anything but names is kept", [("and isinstance(v, dict) and names(v.get(\"people\")) and names(v.get(\"items\"))}",
                                                             "and isinstance(v, dict) and isinstance(v.get(\"people\"), list) and isinstance(v.get(\"items\"), list)}")]),
    ("a harvest with no lines is not quiet", [("names[slug], is_quiet or not items, items) for slug", "names[slug], is_quiet, items) for slug")]),
    # SKB-128: tying lines to items
    ("a tag for a closed item is recorded", [('               else "#%s is %s" % (num, it["狀態"]) if it["狀態"] in TERMINAL else None)',
                                              "               else None)")]),
    ("a tag for an unknown item is recorded", [("        it = items.get(num)\n", '        it = items.get(num) or {"狀態": "進行中"}\n')]),
    ("a number on two rows is tagged", [('               else "#%s is on two rows of the tracker" % num if it.get("twice")\n', "")]),
    ("a closed item is offered for tagging", [('for it in items.values() if it["狀態"] not in TERMINAL and not it.get("twice")]',
                                               'for it in items.values() if not it.get("twice")]')]),
    ("a number on two rows is offered for tagging", [('for it in items.values() if it["狀態"] not in TERMINAL and not it.get("twice")]',
                                                      'for it in items.values() if it["狀態"] not in TERMINAL]')]),
    ("the item is left out of the row", [('fname, tags.get(i, "")] for i, ws, kind, text in kept]',
                                          'fname, ""] for i, ws, kind, text in kept]')]),
    ("an id is only the line's place", [('    return "t%d-%s" % (n, hashlib.sha256(("%s\\x1f%s\\x1f%s" % (who, kind, text)).encode("utf-8")).hexdigest()[:6])',
                                         '    return "t%d-000000" % n')]),
    ("a snapshot that does not read fails the beat", [
        ('    try:\n        rows = read_block(dict(run, dir=d), "snap", run["snap_row"])\n    except Refuse as e:\n'
         '        return None, "none: the snapshot did not read (%s)" % e\n',
         '    rows = read_block(dict(run, dir=d), "snap", run["snap_row"])\n')]),
    ("a tags file that does not parse fails the beat", [("    except (OSError, ValueError) as e:\n        report.update(missing=list(wanted), why=\"the tags file does not parse",
                                                         "    except OSError as e:\n        report.update(missing=list(wanted), why=\"the tags file does not parse")]),
    ("a tags file that is not an object is used", [("    if not isinstance(got, dict):\n        report.update(missing=list(wanted), why=\"the tags file is not an object",
                                                    "    if False:\n        report.update(missing=list(wanted), why=\"the tags file is not an object")]),
    ("a week with no tags is remembered as tagged", [('        if report["given"]:\n            remember(', "        if True:\n            remember(")]),
    ("a quiet person is remembered as harvesting", [("[who for _, who, is_quiet, _, _ in people if not is_quiet]",
                                                     "[who for _, who, is_quiet, _, _ in people]")]),
    ("every remembered week is kept", [("    keep_weeks = sorted(weeks, key=ledger.monday)[-SEEN_WEEKS:]", "    keep_weeks = sorted(weeks, key=ledger.monday)")]),
    ("an empty tag is refused", [("        if num.lower() in NO_ITEM:\n            continue\n", "")]),
    ("the snapshot is taken from this week's row", [("    r, prev = run[\"weeks_row\"] - 1, previous_week(run[\"week\"])", "    r, prev = run[\"weeks_row\"] - 1, run[\"week\"]")]),
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
    for f in ("ledger.py", "recap.py", "skills.py"):      # recap imports skills (SKB-110)
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
