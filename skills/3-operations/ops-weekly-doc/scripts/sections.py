#!/usr/bin/env python3
"""sections.py — the team blocks for Thursday's meeting (SKB-091 AC-13): under each team heading of this
Thursday's section, one 〔自動彙整〕 block with 進度 · 卡關 · 下一步 · 待討論, from the Ledger's Harvest rows (collect,
just before) and Monday's recap facts (the tracker as of last week, the meeting's actions, the Pulse).

    sections.py start --week W [--config PATH]              -> the Weeks row and the Harvest block to read
    sections.py items --dir D --routing R                   -> the harvest items the blocks show, to say
                                                               again short in zh-TW, and where to save
                                                               them (SKB-127)
    sections.py render --dir D --routing R --stamp "11-05 09:40" [--short short.json]
                                                            -> blocks in render_block's shape, for
                                                               `render_block.py ops`
    sections.py --selftest | --mutate

What goes where, per person (the heading's owner chip, named through chat_ids):
  進度    the stretch the harvest covers and how many lines of each kind it held (SKB-128), its shipped
          (完成) and moving (進行中) items, at most six, how many more it does not list, then the
          Pulse's sales steps; 「本週無資料」 when there is no harvest for them
  卡關    the harvest's waiting lines, at most four, how many more wait, then items overdue as of Monday
  下一步  last week's meeting actions, only when last week's tidy did not already fill them into the
          kept block (`<last week>.tidy.done`), so the team never reads the same action twice
  待討論  at most three keep / hand over / drop choices (paused items), then the sure gaps: items the
          state rules say look done but are not marked 完成
In a week whose harvest lines `collect` tied to tracker items (SKB-128), 進度 is written by item: one
line per item the person moved (`#6.10 <item>｜完成 2、進行中 1：…`, naming the item's owner when the
person is neither owner nor helper), then each line the tracker holds no open item for (`不在 Tracker｜…`).
待討論 then opens by asking about every item the week's work overtook (the tracker still reads 未開始 or
暫停), and ends with at most two of the person's own 進行中 items that no line was tied to for three
recorded weeks. render keeps the lines it wrote in `<week>.progress.json` for Monday's recap. A week with
no item list, or no tied line, is written by kind as above.
Each harvest item is written as the model's own short zh-TW line from short.json (SKB-127): a harvest
is English and runs to 300 characters, and cut at 80 it stopped mid-word in a zh-TW Doc. A line that is
missing, too long, more than one line or mostly English is not used: the item falls back to its harvest
text cut at 80, at a space, and the output names it, so the receipt can say how many fell back.
It writes nothing and reads nothing itself: the model makes the printed calls, as with ledger.py.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import timedelta

LEDGER_API = 4   # SKB-128: Harvest rows are nine cells wide, `item` in column I (3 = SKB-118: load_result refuses a changed result)
HERE = os.path.dirname(os.path.abspath(__file__))


def core_dir():
    """zynkr-ops-weekly's scripts folder (ledger.py, recap.py); ZYNKR_OPS_WEEKLY_SCRIPTS overrides it."""
    env = os.environ.get("ZYNKR_OPS_WEEKLY_SCRIPTS")
    tried = ([env] if env else []) + [HERE, os.path.normpath(os.path.join(HERE, "..", "..", "zynkr-ops-weekly", "scripts"))]
    for d in tried:
        if os.path.exists(os.path.join(d, "ledger.py")):
            return d
    raise SystemExit("sections.py: zynkr-ops-weekly's ledger.py not found (looked in %s). Install zynkr-ops-weekly, "
                     "or set ZYNKR_OPS_WEEKLY_SCRIPTS to its scripts folder." % ", ".join(tried))


sys.path.insert(0, HERE)
sys.path.insert(1, core_dir())
import ledger as L  # noqa: E402
import recap as R  # noqa: E402
import harvest as H  # noqa: E402  (collect's own: where it keeps the week's items and who harvested)
from render_block import STAMP, body_text  # noqa: E402
if getattr(L, "API", 1) != LEDGER_API or "Harvest" not in L.BLOCKS:
    raise SystemExit("sections.py: zynkr-ops-weekly's ledger.py speaks API %s, this script needs %s; install both "
                     "skills at the same version" % (getattr(L, "API", 1), LEDGER_API))

QUIET = "本週無資料"
CHOICES = 3
CAP = {"進度": 6, "卡關": 4, "下一步": 5}
CLIP = 80        # the safety net: a harvest item with no usable short line is cut here
SHORT_MAX = 60   # a short line longer than this is not short; the step asks for about 40 字
CJK = re.compile(r"[\u3400-\u9fff]")
WORD = re.compile(r"(?<![\w#@./-])[A-Za-z]{2,}(?![\w#@./-])")   # an English word, never part of an id or a name like zynkr-learn#19
LABEL = re.compile(r"^(完成|進行中|卡關)\s*[：:]\s*")
# SKB-128: the block by tracker item
KIND_ZH = {"shipped": "完成", "moving": "進行中"}
UNTRACKED = "不在 Tracker"     # a line the tracker holds no open item for, in a week whose lines were tied to items
STALE = ("未開始", "暫停")       # a status the week's shipped or moving work has overtaken
SILENT_WEEKS = 3               # an item nobody tied a line to for this many recorded weeks is asked about
SILENT_MAX = 2                 # at most this many such questions per person
PAREN_TAIL = re.compile(r"\s*[（(][^（()）]*[）)]\s*$")     # an item name's closing bracketed note


def load_cfg(path=None):
    cfg = L.load_config(path)
    raw = json.load(open(cfg["path"], encoding="utf-8"))
    ids = {k: v for k, v in (raw.get("chat_ids") or {}).items() if not k.startswith("$") and isinstance(v, str)}
    aliases = {k: v for k, v in ((raw.get("routine") or {}).get("name_aliases") or {}).items()
               if not k.startswith("$") and isinstance(v, str)}
    cfg.update(roster=[k for k in ids if not k.startswith("users/")], aliases=aliases,
               names={v: k for k, v in ids.items() if not k.startswith("users/")})
    return cfg


def s_start(week, config=None, now=None, base=None):
    cfg = load_cfg(config)
    k = L.week_index(week, cfg["epoch"])
    now = L.parse_now(now)
    d = os.path.join(base or os.path.join(L.state_dir(), "runs"), "%s-sections-%s" % (week, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    r = L.weeks_row(k)
    first, last = L.block_slot("Harvest", k)
    # the block is 80 rows and a read shows at most 50 (L.PAGE): one read per page, or the read is refused
    pages = [[a, min(a + L.PAGE - 1, last)] for a in range(first, last + 1, L.PAGE)]
    run = dict(cfg, dir=d, week=week, k=k, weeks_row=r, harvest_pages=pages)
    L.save_run(run)
    return {"dir": d, "week": week, "label": R.wb_label(week),
            "calls": [L.read_call(run, cfg["ledger"], "Weeks!A%d:T%d" % (r, r), "wr")]
            + [L.read_call(run, cfg["ledger"], "Harvest!A%d:I%d" % (a, b), "harvest" if i == 0 else "harvest%d" % (i + 1))
               for i, (a, b) in enumerate(pages)]}


def latest_facts(week):
    """Monday's recap facts: the recap of last week, run this week. None when it never built."""
    hits = sorted(glob.glob(os.path.join(L.state_dir(), "runs", "%s-recap-*" % R.previous_week(week), "facts.json")))
    return hits[-1] if hits else None


def mine(run, who, entries, field="負責人", everyone=False):
    """The entries `who` owns. With `everyone`, an `All` one (recap reads it as 全體) is everyone's: a
    meeting action for the whole team goes to every team's 下一步, as tidy's fill writes it (W45
    review). A tracker item owned by 全體 is no team's here: it would fill every team's 卡關 and take
    one of each team's three 待討論 choices (review round 2, 10-31)."""
    out = []
    for e in entries:
        owners = R.owners_of(run, e.get(field))
        if who in owners or (everyone and "全體" in owners):
            out.append(e)
    return out


def item_id(i, r):
    """A harvest item's id: its place among this week's rows and a hash of the item, so a line written for
    one item never lands on another (a rerun, a harvest that grew, a short.json from another run)."""
    h = hashlib.sha256(("%s\x1f%s\x1f%s" % (r[3], r[5], r[6])).encode("utf-8")).hexdigest()[:6]
    return "h%d-%s" % (i + 1, h)


def by_person(harvest, people=None):
    """{name: [(id, row)]} of the week's Harvest rows, each with its id, for the people named (or everyone)."""
    by = {}
    for i, r in enumerate(harvest):
        if people is None or r[3] in people:
            by.setdefault(r[3], []).append((item_id(i, r), r))
    return by


def shown(harvest, people=None, items=None):
    """[unit] of what the blocks show, in their order: per person the units under 進度, then the waiting
    lines under 卡關. `items` asks the model for exactly these and render writes exactly these, so the model
    is never asked for a line the Doc drops, and the receipt counts only lines it shows."""
    out = []
    for rows in by_person(harvest, people).values():
        progress, blocked = picked(rows, items)
        out += progress + blocked
    return out


def picked(rows, items=None):
    """(progress, blocked) of one person's [(id, row)], as units {"id", "item", "rows"}: what `shown` asks
    for and `parts_for` writes. One rule, so the two cannot drift.

    Without `items` (a week whose lines were not tied to tracker items): every shipped line, then every
    moving one, each a unit of its own. With `items` (SKB-128): one unit per tracker item the person moved,
    holding its shipped lines then its moving ones, in the order the items first come up; then each line
    the tracker holds no item for, on its own. 進度 lists at most six units and 卡關 four waiting lines.
    A row with no text is no line."""
    rows = [x for x in rows if x[1][6].strip()]
    lines = [x for x in rows if x[1][5] == "shipped"] + [x for x in rows if x[1][5] == "moving"]
    progress = []
    if items:
        groups = {}
        for i, r in lines:
            if r[8] in items:
                groups.setdefault(r[8], []).append((i, r))
        for num, members in groups.items():
            h = hashlib.sha256("\x1f".join([members[0][1][3], num] + [r[6] for _, r in members]).encode("utf-8")).hexdigest()[:6]
            progress.append({"id": "g%s-%s" % (members[0][0].split("-")[0][1:], h), "item": num, "rows": [r for _, r in members]})
        lines = [x for x in lines if x[1][8] not in items]
    progress += [{"id": i, "item": "", "rows": [r]} for i, r in lines]
    blocked = [{"id": i, "item": r[8] if items and r[8] in items else "", "rows": [r]} for i, r in rows if r[5] == "waiting"]
    return progress[:CAP["進度"]], blocked[:CAP["卡關"]]


def totals_for(rows):
    """{kind: n} from a person's totals row (SKB-128): what their harvest held, before `collect` kept its
    share. None for a week recorded before then: the block is then written as it was. More than one row
    for a name (the Ledger edited by hand) adds up, so a count line never understates."""
    found = [t for t in (L.parse_totals(r[6]) for _, r in rows if r[5] == L.HARVEST_TOTALS) if t]
    return {k: sum(t[k] for t in found) for k in L.HARVEST_KINDS} if found else None


def load_items(week):
    """{#: item} as the week's `collect` read them from last week's snapshot (name, owner, helpers, status),
    or None when it kept none: no snapshot that week, or a `collect` from before SKB-128. A file that is
    not in the shape `collect` writes (every item its own number, with text fields) is not used either:
    the block is then written by kind, which needs no item."""
    try:
        got = json.load(open(H.items_path(week), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    items = got.get("items") if isinstance(got, dict) and got.get("week") == week else None
    if not isinstance(items, dict):
        return None

    def sound(num, it):
        return (isinstance(it, dict) and it.get("#") == num
                and all(isinstance(it.get(k), str) for k in ("項目", "狀態"))
                and all(isinstance(it.get(k, ""), str) for k in ("負責人", "協助者", "Priority")))

    return items if all(sound(num, it) for num, it in items.items()) else None


def silent(run, who, items, seen, week):
    """The items `who` owns that read 進行中 and that no harvest line was tied to in the last SILENT_WEEKS
    recorded weeks, this one among them, while `who` harvested in every one of them (SKB-128 AC-16). Fewer
    recorded weeks, or a week `who` did not harvest, and nothing is asked: silence is only worth a question
    where a line would have shown up. P0 and P1 first, at most SILENT_MAX."""
    weeks = sorted((w for w in seen if L.monday(w) <= L.monday(week)), key=L.monday)[-SILENT_WEEKS:]
    if len(weeks) < SILENT_WEEKS or weeks[-1] != week or not all(who in seen[w]["people"] for w in weeks):
        return []
    touched = {n for w in weeks for n in seen[w]["items"]}
    quiet = [it for num, it in items.items() if it.get("狀態") == "進行中" and not it.get("twice") and num not in touched
             and who in R.owners_of(run, it.get("負責人"))]
    return sorted(quiet, key=lambda it: (it.get("Priority") or "P9", it["#"]))[:SILENT_MAX]


def span(week):
    """The stretch a week's harvest covers, `11/4–11/11`: it closes on the week's Wednesday at 20:00, and
    opens where the one before it closed."""
    end = L.monday(week) + timedelta(days=2)
    return "%s–%s" % (R.md(end - timedelta(days=7)), R.md(end))


def fallback(text, n=CLIP):
    """The safety net: the harvest text, cut at a space when there is one in its last quarter."""
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    head = text[:n - 1]
    sp = head.rfind(" ")
    return (head[:sp] if sp >= n * 3 // 4 else head).rstrip(" ,;:—-") + "…"


def item_name(it, n=24):
    """An item's name as a line carries it: without a closing bracketed note (a site, a date, who it is for),
    then cut at `n`. `Future Builders 營隊講座（清華分會，2027/1/23）` reads `Future Builders 營隊講座`."""
    name = " ".join(str(it.get("項目") or "").split())
    return R.clip(PAREN_TAIL.sub("", name) or name, n)


def kinds_label(rows):
    """What a unit's lines are: 完成 or 進行中 for one line, and how many of each for several (完成 4、進行中 2)."""
    if len(rows) == 1:
        return KIND_ZH[rows[0][5]]
    return "、".join("%s %d" % (KIND_ZH[k], n) for k, n in ((k, sum(1 for r in rows if r[5] == k)) for k in ("shipped", "moving")) if n)


def parts_for(run, who, harvest, facts, filled, short=None, items=None, seen=None, note=None):
    """[(label, [items])] for one person, in the frozen label order; 進度 is always there. `short` maps a
    unit's id to its accepted zh-TW line; a unit without one keeps its harvest text, cut at CLIP. `items` is
    the week's tracker items when its lines were tied to them (SKB-128): 進度 is then written by item, and
    待討論 asks about a status the week's work has overtaken. `seen` is what `collect` remembers of the
    weeks before. `note`, when given, is filled with what Monday's recap repeats of this block."""
    short = short or {}
    rows = [(item_id(i, r), r) for i, r in enumerate(harvest) if r[3] == who]

    def said(u):
        if u["id"] in short:
            return short[u["id"]]
        return fallback(u["rows"][0][6]) + ("；另 %d 件" % (len(u["rows"]) - 1) if len(u["rows"]) > 1 else "")

    def progress_line(u):
        what = "%s：%s" % (kinds_label(u["rows"]), said(u))
        if not items:
            return what
        if not u["item"]:
            return "%s｜%s" % (UNTRACKED, what)
        it = items[u["item"]]
        own = R.owners_of(run, it.get("負責人")) + R.owners_of(run, it.get("協助者"))
        theirs = "" if who in own or "全體" in own or not (it.get("負責人") or "").strip() else "（負責人 %s）" % R.clip(it["負責人"], 16)
        return "#%s %s%s｜%s" % (u["item"], item_name(it), theirs, what)

    out = {"進度": [], "卡關": [], "下一步": [], "待討論": []}
    if not rows or all(r[5] == "quiet" for _, r in rows):
        out["進度"].append(QUIET)
    progress, blocked = picked(rows, items)
    tot = totals_for(rows)
    if tot:
        # SKB-128: what the harvest covers and held, so a block of six lines no longer reads as the week
        week = run.get("week")
        out["進度"].append("收成%s：完成 %d · 進行中 %d · 在等 %d"
                           % (" %s（週三 20:00 截止）" % span(week) if week else "", tot["shipped"], tot["moving"], tot["waiting"]))
    lines = [progress_line(u) for u in progress]
    waits = [("#%s " % u["item"] if u["item"] else "") + said(u) for u in blocked]
    out["進度"] += lines
    out["卡關"] += waits
    left = {}
    if tot:
        left = {k: tot[k] - sum(1 for u in progress for r in u["rows"] if r[5] == k) for k in ("shipped", "moving")}
        left["waiting"] = tot["waiting"] - len(blocked)
        more = ["%d 件%s" % (left[k], KIND_ZH[k]) for k in ("shipped", "moving") if left[k] > 0]
        if more:
            out["進度"].append("另有 %s沒列出，見收成檔" % "、".join(more))
        if left["waiting"] > 0:
            out["卡關"].append("另有 %d 件在等，見收成檔" % left["waiting"])
    # what the week's work has overtaken (SKB-128 AC-15): every item the person shipped or moved work on,
    # listed in 進度 or not, that the tracker still reads as not started or paused
    moved = list(dict.fromkeys(r[8] for _, r in rows if items and r[5] in ("shipped", "moving") and r[8] in items))
    stale = [n for n in moved if items[n].get("狀態") in STALE]
    if facts:
        # the caps are the harvest's own (six and four): the Pulse's steps and the overdue items come after
        # them, where a full block used to cut them off
        for p in facts.get("plan", []):
            if p["who"] == who:
                out["進度"] += [line for line in p["lines"] if line.startswith("業務：")]
        out["卡關"] += ["#%s %s — %s" % (x["#"], R.clip(x["項目"], 30), x["why"])
                       for x in mine(run, who, facts.get("overdue", []))][:CAP["卡關"]]
        if not filled:
            for a in mine(run, who, facts.get("decisions", {}).get("actions", []), everyone=True):
                due = R.as_date(L.norm_date(a["期限"]) or a["期限"])
                out["下一步"].append("%s%s%s" % ("#%s " % a["#"] if a["#"] else "", R.clip(a["內容"], 50),
                                                 "（%s 前）" % R.md(due) if due else ""))
        out["下一步"] = out["下一步"][:CAP["下一步"]]
    out["待討論"] = ["#%s %s：本週有進度，Tracker 還是「%s」，要改狀態嗎？" % (n, item_name(items[n], 30), items[n]["狀態"])
                   for n in stale]
    if facts:
        # a paused item the week's work already moved is asked about above, not offered for dropping too
        out["待討論"] += ["#%s %s：留著、交給別人，還是放棄？" % (x["#"], R.clip(x["項目"], 30))
                        for x in mine(run, who, facts.get("paused", [])) if x["#"] not in stale][:CHOICES]
        out["待討論"] += ["#%s %s — %s，要標 完成 嗎？" % (x["#"], R.clip(x["項目"], 30), x["why"])
                        for x in mine(run, who, facts.get("propose_done", []))]
    if items and seen and run.get("week"):
        out["待討論"] += ["#%s %s：三週沒有收成紀錄，還在進行嗎？" % (it["#"], item_name(it, 30))
                        for it in silent(run, who, items, seen, run["week"])]
    if note is not None:
        note.update(totals=tot, lines=lines, waiting=waits, left=left,
                    moving=[n for n in moved if any(r[8] == n and r[5] == "moving" for _, r in rows)])
    return [(label, lines_) for label, lines_ in out.items() if lines_]


def read_harvest(d):
    """(run, harvested, this week's Harvest rows), from the results start's calls saved."""
    run = L.load_run(d)
    r = run["weeks_row"]
    wr = L.parse_values(L.load_result(os.path.join(d, "wr.txt")), run["ledger"], "Weeks!A%d:T%d" % (r, r))
    row = L.pad(wr[0], 20) if wr else [""] * 20
    if row[0] not in ("", run["week"]):
        raise L.Refuse(4, "Weeks row %d belongs to %s, not %s" % (r, row[0], run["week"]))
    harvested = row[18] == "ok"
    harvest = []
    if harvested:
        got = []
        for i, (a, b) in enumerate(run["harvest_pages"]):
            got += L.parse_values(L.load_result(os.path.join(d, "harvest.txt" if i == 0 else "harvest%d.txt" % (i + 1))),
                                  run["ledger"], "Harvest!A%d:I%d" % (a, b))
        harvest = [L.pad(x, 9) for x in got if L.pad(x, 9)[0] == run["week"]]
    return run, harvested, harvest


def routed_people(run, routing):
    """The people a block is written for: each primary heading's owner that chat_ids names."""
    return {run["names"][h["owner_email"]] for h in routing["headings"]
            if not (h.get("grouped_with_previous") or not h.get("primary", True)) and run["names"].get(h["owner_email"])}


def tracked(run, harvest):
    """The week's tracker items when its harvest lines were tied to them, else None: `collect` kept the
    items it read from last week's snapshot, and at least one row of the week names one (SKB-128 AC-17). A
    week without both is written by kind, as before."""
    items = load_items(run["week"])
    return items if items and any(r[8] in items for r in harvest) else None


def s_items(d, routing_path):
    """What the model says again, each as one short zh-TW line, saved as {id: line} to `save`: a harvest
    line (`text`), or every line a person has on one tracker item (`item` and `lines`, SKB-128)."""
    run, harvested, harvest = read_harvest(d)
    routing = json.load(open(routing_path, encoding="utf-8"))
    items = tracked(run, harvest)
    asked = []
    for u in shown(harvest, routed_people(run, routing), items):
        rows = u["rows"]
        if u["item"] and rows[0][5] != "waiting":
            asked.append({"id": u["id"], "who": rows[0][3], "kind": "item",
                          "item": "#%s %s" % (u["item"], items[u["item"]].get("項目") or ""),
                          "lines": [{"kind": r[5], "text": r[6]} for r in rows]})
        else:
            asked.append({"id": u["id"], "who": rows[0][3], "kind": rows[0][5], "text": rows[0][6]})
    return {"harvest": "recorded" if harvested else "not-recorded", "by_item": items is not None, "items": asked,
            "save": os.path.join(d, "short.json"), "max_chars": SHORT_MAX}


def check_line(v):
    """(line, None) when a short line can be used, else (None, why). A leading 完成：/進行中：/卡關： is
    dropped, since the block adds its own label."""
    if not isinstance(v, str):
        return None, "not text"
    line = LABEL.sub("", v.strip()).strip()
    cjk, words = len(CJK.findall(line)), len(WORD.findall(line))
    why = ("empty" if not line
           else "more than one line" if "\n" in line
           else "%d characters, over %d" % (len(line), SHORT_MAX) if len(line) > SHORT_MAX
           else "no Chinese" if not cjk
           else "mostly English (%d words, %d 字)" % (words, cjk) if words * 3 > cjk else None)
    return (None, why) if why else (line, None)


def load_short(path, wanted):
    """({id: line} that passed, report), for the ids `wanted` (shown()'s). A line passes when it is one
    zh-TW line of at most SHORT_MAX characters; anything else falls back to the harvest text and is named in
    the report. No path, or no file at it (a week with nothing to say), means every item falls back."""
    report = {"given": False, "items": len(wanted), "used": 0, "missing": list(wanted), "rejected": [], "unknown": []}
    if not path or not os.path.exists(path):
        return {}, report
    try:
        got = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise L.Refuse(3, "%s does not parse: %s" % (path, e))
    if not isinstance(got, dict):
        raise L.Refuse(3, "%s must be an object of {item id: line}" % path)
    ok, missing, rejected = {}, [], []
    for i in wanted:
        if i not in got:
            missing.append(i)
            continue
        line, why = check_line(got[i])
        if why:
            rejected.append({"id": i, "why": why})
        else:
            ok[i] = line
    report.update(given=True, used=len(ok), missing=missing, rejected=rejected, unknown=sorted(set(got) - set(wanted)))
    return ok, report


def s_render(d, routing_path, stamp, facts_path=None, short_path=None):
    run, harvested, harvest = read_harvest(d)
    routing = json.load(open(routing_path, encoding="utf-8"))
    items = tracked(run, harvest)
    seen = H.load_seen() if items else {}
    short, short_report = load_short(short_path, [u["id"] for u in shown(harvest, routed_people(run, routing), items)])
    facts_path = facts_path or latest_facts(run["week"])
    facts = json.load(open(facts_path, encoding="utf-8")) if facts_path else None
    filled = os.path.exists(os.path.join(L.state_dir(), "%s.tidy.done" % R.previous_week(run["week"])))
    label = R.wb_label(run["week"])
    header = STAMP.format(week=label, stamp=stamp)
    blocks, nameless, routed, people = [], [], set(), {}
    for h in routing["headings"]:
        if h.get("grouped_with_previous") or not h.get("primary", True):
            continue
        who = run["names"].get(h["owner_email"])
        if not who:
            nameless.append({"heading": h["heading"], "owner_email": h["owner_email"]})
            continue
        routed.add(who)
        note = {}
        body = body_text(parts_for(run, who, harvest, facts, filled, short, items, seen, note))
        if note.get("lines") or note.get("waiting"):
            people[who] = note
        blocks.append({"heading": h["heading"], "owner_email": h["owner_email"], "owner_name": who,
                       "stamp_line": header, "body": body, "text": header + "\n" + body,
                       "lines": 1 + len(body.split("\n"))})
    if harvested:
        # what Monday's recap repeats as 上週進度 (SKB-128 AC-22): the lines as the blocks say them. A later
        # render of the week writes it again, so it holds what the last one wrote.
        json.dump({"week": run["week"], "label": label, "span": span(run["week"]), "by_item": items is not None,
                   "people": people}, open(progress_path(run["week"]), "w", encoding="utf-8"), ensure_ascii=False)
    return {"week": label, "stamp": header, "idempotency_key": "〔自動彙整 %s" % label, "blocks": blocks,
            "harvest": "recorded" if harvested else "not-recorded", "by_item": items is not None,
            "facts": facts_path, "next_steps_filled": filled, "owners_without_name": nameless,
            "harvest_without_heading": sorted({x[3] for x in harvest} - routed), "short": short_report,
            "counts": {"blocks": len(blocks), "quiet": sum(1 for b in blocks if QUIET in b["body"])}}


def progress_path(week):
    """The harvest lines the week's blocks wrote, kept for Monday's recap (`recap.py` reads the same path)."""
    return os.path.join(L.state_dir(), "%s.progress.json" % week)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("start")
    s.add_argument("--week", required=True)
    s.add_argument("--config")
    it = sub.add_parser("items")
    it.add_argument("--dir", required=True)
    it.add_argument("--routing", required=True, help="parse_routing.py's output, as render takes it")
    r = sub.add_parser("render")
    r.add_argument("--dir", required=True)
    r.add_argument("--routing", required=True, help="parse_routing.py's output, saved as a file")
    r.add_argument("--stamp", required=True, help='the time shown in the stamp, e.g. "11-05 09:40"')
    r.add_argument("--facts", help="a recap facts.json other than Monday's (by hand only)")
    r.add_argument("--short", help="the model's {item id: short zh-TW line}, saved where `items` said")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd == "start":
            L.emit(s_start(a.week, a.config))
        elif a.cmd == "items":
            L.emit(s_items(a.dir, a.routing))
        elif a.cmd == "render":
            L.emit(s_render(a.dir, a.routing, a.stamp, a.facts, a.short))
        else:
            ap.print_help()
            return 2
    except L.Refuse as e:
        print("sections.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


def selftest():
    import shutil
    import tempfile
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s:\n    got  %r\n    want %r" % (name, got, want))

    tmp = tempfile.mkdtemp(prefix="sections-selftest-")
    os.environ["ZYNKR_OPS_WEEKLY_STATE"] = state = os.path.join(tmp, "state")
    os.makedirs(state)
    try:
        cfgp = os.path.join(tmp, "cfg.json")
        json.dump({"google_account": "owner@example.com",
                   "chat_ids": {"Ann Lee": "ann@example.com", "users/1": "ann@example.com", "Bob Wu": "bob@example.com",
                                "Cat Ho": "cat@example.com"},
                   "routine": {"name_aliases": {"Bobby": "Bob Wu"}},
                   "sources": {"main_tracker": {"id": "TRK", "tab": "T", "cycle": "2026H2"},
                               "ledger": {"id": "LED", "epoch_week": "2026-W40"}}}, open(cfgp, "w"))
        W = "2026-W45"
        k = L.week_index(W, "2026-W40")
        st = s_start(W, cfgp, "2026-11-05T09:35:00+08:00", base=os.path.join(tmp, "runs"))

        def sheet(rng, rows):
            if not rows:
                return "No data found in range '%s' for x." % rng
            return ("Successfully read %d rows from range '%s' in spreadsheet LED for x:\n" % (len(rows), rng)
                    + "".join("Row %2d: %s\n" % (i + 1, r) for i, r in enumerate(rows[:50]))
                    + ("... and %d more rows\n" % (len(rows) - 50) if len(rows) > 50 else ""))

        rr = L.weeks_row(k)
        weeks = [W] + [""] * 17 + ["ok", "2026-11-05T09:20:00+08:00"]
        at = "2026-11-05T09:20:00+08:00"
        harvest = [[W, at, "ann", "Ann Lee", "SEO", "waiting", "needs input: which keyword first", "harvest-ann.md"],
                   [W, at, "ann", "Ann Lee", "SEO", "shipped", "three articles live (abc1234)", "harvest-ann.md"],
                   [W, at, "ann", "Ann Lee", "SEO", "moving", "the FAQ page", "harvest-ann.md"],
                   [W, at, "bob", "Bob Wu", "", "quiet", QUIET, "harvest-bob.md"],
                   [W, at, "dan", "Dan Yu", "Ops", "shipped", "a thing", "harvest-dan.md"],
                   ["2026-W44", at, "ann", "Ann Lee", "SEO", "shipped", "last week's work", "harvest-ann.md"]]
        open(st["calls"][0]["save"], "w").write(sheet("Weeks!A%d:T%d" % (rr, rr), [weeks]))
        first = L.block_slot("Harvest", k)[0]
        grid = (harvest + [["2026-W44", at, "zed", "Zed", "", "shipped", "a row of another week", "harvest-zed.md"]] * 44
                + [[W, at, "cat", "Cat Ho", "財務", "shipped", "books closed", "harvest-cat.md"]])
        for c in st["calls"][1:]:
            a, b = (int(x) for x in re.match(r"^Harvest!A(\d+):I(\d+)$", c["args"]["range_name"]).groups())
            open(c["save"], "w").write(sheet(c["args"]["range_name"], grid[a - first:b - first + 1]))
        facts = {"plan": [{"who": "Ann Lee", "lines": ["#1.02 官網 — 已逾期", "業務：call Acme back"]}],
                 # a tracker item owned by All / 全體 is no team's: it must not fill each 卡關 or take a choice
                 "overdue": [{"#": "9.01", "項目": "全公司盤點", "負責人": "All", "why": "10/28 到期"},
                             {"#": "1.02", "項目": "官網改版", "負責人": "Ann Lee", "why": "10/30 到期"}],
                 "paused": [{"#": "9.02", "項目": "公司活動", "負責人": "全體", "why": ""}]
                 + [{"#": "2.0%d" % i, "項目": "項目%d" % i, "負責人": "Ann Lee、Bob Wu", "why": ""} for i in range(1, 6)],
                 "propose_done": [{"#": "1.05", "項目": "名單匯入", "負責人": "Bobby", "why": "harvest 說上線了"}],
                 "decisions": {"actions": [{"#": "1.03", "內容": "寄提案", "負責人": "Ann Lee", "期限": "2026-11-06", "狀態": "已排定"},
                                           {"#": "", "內容": "整理名單", "負責人": "Bob Wu", "期限": "", "狀態": "待定"},
                                           {"#": "", "內容": "全員填問卷", "負責人": "All", "期限": "", "狀態": "待定"}]}}
        rdir = os.path.join(state, "runs", "2026-W44-recap-20261102T100500")
        os.makedirs(rdir)
        json.dump(facts, open(os.path.join(rdir, "facts.json"), "w"), ensure_ascii=False)
        routing = os.path.join(tmp, "routing.json")
        json.dump({"headings": [{"heading": "行銷", "owner_email": "ann@example.com"},
                                {"heading": "行銷 · SEO", "owner_email": "ann@example.com", "grouped_with_previous": True},
                                {"heading": "業務", "owner_email": "bob@example.com"},
                                {"heading": "財務", "owner_email": "cat@example.com"},
                                {"heading": "外包", "owner_email": "eve@example.com"}]}, open(routing, "w"), ensure_ascii=False)
        out = s_render(st["dir"], routing, "11-05 09:40")
        by = {b["heading"]: b for b in out["blocks"]}
        check("one block per primary heading with a known owner, in the Doc's order",
              [b["heading"] for b in out["blocks"]], ["行銷", "業務", "財務"])
        check("Ann: the four parts, in order", by["行銷"]["body"].split("\n"),
              ["進度", "\t完成：three articles live (abc1234)", "\t進行中：the FAQ page", "\t業務：call Acme back",
               "卡關", "\tneeds input: which keyword first", "\t#1.02 官網改版 — 10/30 到期",
               "下一步", "\t#1.03 寄提案（11/6 前）", "\t全員填問卷",
               "待討論", "\t#2.01 項目1：留著、交給別人，還是放棄？", "\t#2.02 項目2：留著、交給別人，還是放棄？",
               "\t#2.03 項目3：留著、交給別人，還是放棄？"])
        check("Bob: a quiet week, an alias's sure gap past the three choices",
              by["業務"]["body"].split("\n"),
              ["進度", "\t" + QUIET, "下一步", "\t整理名單", "\t全員填問卷",
               "待討論", "\t#2.01 項目1：留著、交給別人，還是放棄？", "\t#2.02 項目2：留著、交給別人，還是放棄？",
               "\t#2.03 項目3：留著、交給別人，還是放棄？", "\t#1.05 名單匯入 — harvest 說上線了，要標 完成 嗎？"])
        check("Cat: a row on the Harvest block's second page is read, and an All action is everyone's",
              by["財務"]["body"], "進度\n\t完成：books closed\n下一步\n\t全員填問卷")
        check("the stamp is this week's", by["行銷"]["stamp_line"], "〔自動彙整 WB 11/2 · 11-05 09:40〕")
        check("diagnostics", (out["owners_without_name"], out["harvest_without_heading"]),
              ([{"heading": "外包", "owner_email": "eve@example.com"}], ["Dan Yu"]))
        check("without --short, every shown item is named as missing, and the report keeps its shape",
              out["short"], {"given": False, "items": 4, "used": 0, "rejected": [], "unknown": [],
                             "missing": [x["id"] for x in s_items(st["dir"], routing)["items"]]})
        # SKB-127: the model's short zh-TW lines replace the harvest text; a bad one falls back and is named
        it = s_items(st["dir"], routing)
        ids = {x["text"]: x["id"] for x in it["items"]}
        check("items: the rows a block shows, per person shipped, moving, waiting; never a quiet row or a "
              "person with no heading", [(x["who"], x["kind"], x["text"]) for x in it["items"]],
              [("Ann Lee", "shipped", "three articles live (abc1234)"), ("Ann Lee", "moving", "the FAQ page"),
               ("Ann Lee", "waiting", "needs input: which keyword first"), ("Cat Ho", "shipped", "books closed")])
        check("items: an id is the row's place and a hash of the item",
              re.fullmatch(r"h\d+-[0-9a-f]{6}", ids["the FAQ page"]) is not None, True)
        check("items: saved in the run's own folder", it["save"], os.path.join(st["dir"], "short.json"))
        a1, a2, a3, c1 = (ids[t] for t in ("needs input: which keyword first", "three articles live (abc1234)",
                                            "the FAQ page", "books closed"))
        stale = "h3-000000"
        json.dump({a1: "  要先決定先做哪個關鍵字 ", a2: "完成：三篇文章上線了（abc1234）", a3: "常" * (SHORT_MAX + 1),
                   stale: "這一行屬於另一次的 harvest"}, open(it["save"], "w"), ensure_ascii=False)
        out = s_render(st["dir"], routing, "11-05 09:40", short_path=it["save"])
        by = {b["heading"]: b for b in out["blocks"]}
        check("a short line replaces its item, its own label dropped; one too long keeps the harvest text",
              by["行銷"]["body"].split("\n")[:6],
              ["進度", "\t完成：三篇文章上線了（abc1234）", "\t進行中：the FAQ page", "\t業務：call Acme back",
               "卡關", "\t要先決定先做哪個關鍵字"])
        check("a missing line keeps the harvest text", by["財務"]["body"].split("\n")[:2], ["進度", "\t完成：books closed"])
        check("the report: used, missing, rejected with why, and a stale id as unknown",
              out["short"], {"given": True, "items": 4, "used": 2, "missing": [c1], "unknown": [stale],
                             "rejected": [{"id": a3, "why": "%d characters, over %d" % (SHORT_MAX + 1, SHORT_MAX)}]})
        json.dump({a1: "第一行\n第二行", a2: "", a3: 3, c1: "Shipped the FAQ page 了"}, open(it["save"], "w"),
                  ensure_ascii=False)
        check("more than one line, empty, not text and mostly English are all rejected",
              s_render(st["dir"], routing, "11-05 09:40", short_path=it["save"])["short"]["rejected"],
              [{"id": a2, "why": "empty"}, {"id": a3, "why": "not text"}, {"id": a1, "why": "more than one line"},
               {"id": c1, "why": "mostly English (4 words, 1 字)"}])
        check("ids, names and a few English words in a Chinese line are fine",
              check_line("zynkr-ai-platform#75 等你說 merge 75；merge 76、38、98 也還沒確認（11/8）")[1], None)
        check("a line with no Chinese at all", check_line("All done")[1], "no Chinese")
        os.remove(it["save"])
        check("no short.json at all (a week with nothing to say) is every item falling back, not a failure",
              s_render(st["dir"], routing, "11-05 09:40", short_path=it["save"])["short"]["given"], False)
        open(it["save"], "w").write("[1, 2]")
        try:
            s_render(st["dir"], routing, "11-05 09:40", short_path=it["save"])
            check("a short.json that is not an object is refused", "no refusal", "refused")
        except L.Refuse:
            pass
        os.remove(it["save"])
        many = [[W, at, "xu", "Xu", "", "shipped", "item %d" % n, ""] for n in range(8)]
        many += [[W, at, "xu", "Xu", "", "waiting", "wait %d" % n, ""] for n in range(5)]
        check("only what a block shows is asked for: 進度's 6, 卡關's 4",
              [u["rows"][0][6] for u in shown(many)], ["item %d" % n for n in range(6)] + ["wait %d" % n for n in range(4)])
        # SKB-128: a totals row says what the harvest held, so the block names its span and what it leaves out
        full = ([[W, at, "xu", "Xu", "", "totals", "shipped 27 · moving 7 · waiting 13", ""]]
                + [[W, at, "xu", "Xu", "", "waiting", "wait %d" % n, ""] for n in range(4)]
                + [[W, at, "xu", "Xu", "", "shipped", "item %d" % n, ""] for n in range(8)]
                + [[W, at, "xu", "Xu", "", "moving", "move %d" % n, ""] for n in range(3)])
        xfacts = {"plan": [{"who": "Xu", "lines": ["業務：call Acme back"]}],
                  "overdue": [{"#": "1.02", "項目": "官網改版", "負責人": "Xu", "why": "10/30 到期"}]}
        got = dict(parts_for({"week": W}, "Xu", full, xfacts, True))
        check("進度 opens with the span and the counts, lists six, names the rest, and keeps the Pulse",
              got["進度"], ["收成 10/28–11/4（週三 20:00 截止）：完成 27 · 進行中 7 · 在等 13"]
              + ["完成：item %d" % n for n in range(6)] + ["另有 21 件完成、7 件進行中沒列出，見收成檔", "業務：call Acme back"])
        check("卡關 lists four, names how many more wait, and keeps the overdue item",
              got["卡關"], ["wait %d" % n for n in range(4)] + ["另有 9 件在等，見收成檔", "#1.02 官網改版 — 10/30 到期"])
        check("the totals row is never an item to say again", [u["rows"][0][5] for u in shown(full)],
              ["shipped"] * 6 + ["waiting"] * 4)
        blank = ([[W, at, "xu", "Xu", "", "totals", "shipped 0 · moving 0 · waiting 3", ""]]
                 + [[W, at, "xu", "Xu", "", "waiting", t, ""] for t in ("wait a", "  ", "wait b")])
        check("a waiting row with no text is not a listed line: the count of the rest stays right",
              parts_for({"week": W}, "Xu", blank, None, True)[1], ("卡關", ["wait a", "wait b", "另有 1 件在等，見收成檔"]))
        twice = ([[W, at, "xu", "Xu", "", "totals", "shipped 2 · moving 0 · waiting 0", ""],
                  [W, at, "xu2", "Xu", "", "totals", "shipped 10 · moving 0 · waiting 6", ""]]
                 + [[W, at, "xu", "Xu", "", "shipped", "item %d" % n, ""] for n in range(7)])
        check("two totals rows under one name add up, so the count never understates",
              dict(parts_for({"week": W}, "Xu", twice, None, True))["進度"][-1], "另有 6 件完成沒列出，見收成檔")
        # the six and four are the harvest's own caps in every week, with a totals row or not: the Pulse's
        # steps and the overdue items follow them. Before SKB-128 a full block cut both off.
        old_week = dict(parts_for({"week": W}, "Xu", many, dict(xfacts, plan=[{"who": "Xu", "lines": ["業務：one", "業務：two"]}],
                                                                overdue=xfacts["overdue"] * 2), True))
        check("a week with no totals row: six harvest lines then the Pulse, four waiting lines then the overdue items",
              ([x[:3] for x in old_week["進度"]], [x[:5] for x in old_week["卡關"]]),
              (["完成："] * 6 + ["業務："] * 2, ["wait "] * 4 + ["#1.02"] * 2))
        small = ([[W, at, "xu", "Xu", "", "totals", "shipped 1 · moving 1 · waiting 1", ""]]
                 + [[W, at, "xu", "Xu", "", k, "one %s" % k, ""] for k in ("waiting", "shipped", "moving")])
        check("a block that lists everything names nothing more",
              parts_for({"week": W}, "Xu", small, None, True),
              [("進度", ["收成 10/28–11/4（週三 20:00 截止）：完成 1 · 進行中 1 · 在等 1", "完成：one shipped", "進行中：one moving"]),
               ("卡關", ["one waiting"])])
        check("only shipped lines left out: the other kind is not named",
              dict(parts_for({}, "Xu", [[W, at, "xu", "Xu", "", "totals", "shipped 9 · moving 0 · waiting 0", ""]]
                             + [[W, at, "xu", "Xu", "", "shipped", "item %d" % n, ""] for n in range(8)], None, True))["進度"][-1],
              "另有 3 件完成沒列出，見收成檔")
        check("without a totals row (a week recorded before SKB-128) the block is as it was",
              parts_for({"week": W}, "Xu", many, None, True),
              [("進度", ["完成：item %d" % n for n in range(6)]), ("卡關", ["wait %d" % n for n in range(4)])])
        check("a totals row that does not parse is no totals row",
              parts_for({"week": W}, "Xu", [[W, at, "xu", "Xu", "", "totals", "lots", ""],
                                           [W, at, "xu", "Xu", "", "shipped", "a thing", ""]], None, True),
              [("進度", ["完成：a thing"])])
        long_item = " ".join(["word"] * 30)
        got = parts_for({}, "Xu", [[W, at, "xu", "Xu", "", "shipped", long_item, ""]], None, False)
        check("the safety net: an item with no short line is cut at %d, at a space" % CLIP,
              got, [("進度", ["完成：" + long_item[:CLIP - 1].rsplit(" ", 1)[0] + "…"])])
        check("a fallback with no space near the end is cut at %d" % CLIP, len(fallback("x" * 200)), CLIP)

        # SKB-128 AC-14 to AC-17: 進度 by tracker item, when the week's lines were tied to items
        def it(num, name, owner, status, prio="P1"):
            return {"#": num, "項目": name, "Priority": prio, "負責人": owner, "協助者": "", "狀態": status}

        def hrow(kind, text, item=""):
            return [W, at, "xu", "Xu", "WS", kind, text, "", item]

        titems = {x["#"]: x for x in (it("1.01", "官網改版", "Xu", "進行中"), it("1.02", "SEO 文章", "Ann Lee", "未開始"),
                                       it("2.01", "Atlas 搜尋", "Xu", "暫停", "P0"), it("3.01", "年度規劃", "Xu", "進行中", "P2"),
                                       it("3.02", "客戶見證", "Xu", "進行中", "P0"), it("3.03", "內部訓練", "Xu、Ann Lee", "進行中"),
                                       it("3.04", "別人的事", "Ann Lee", "進行中", "P0"))}
        tagged = [hrow("totals", "shipped 9 · moving 3 · waiting 2"), hrow("waiting", "needs a call", "1.01"),
                  hrow("waiting", "which keyword"), hrow("shipped", "page live", "1.01"), hrow("shipped", "nav fixed", "1.01"),
                  hrow("shipped", "three articles", "1.02"), hrow("shipped", "inbox cleared"), hrow("shipped", "index rebuilt", "2.01"),
                  hrow("moving", "footer draft", "1.01"), hrow("moving", "notes")]
        trun = {"week": W, "roster": ["Xu", "Ann Lee"], "aliases": {}}
        tfacts = {"paused": [{"#": "2.01", "項目": "Atlas 搜尋", "負責人": "Xu", "why": ""},
                             {"#": "2.09", "項目": "舊案", "負責人": "Xu", "why": ""}]}
        note = {}
        got = dict(parts_for(trun, "Xu", tagged, tfacts, True, None, titems, None, note))
        check("進度 by item: an item's shipped and moving lines are one line, then the work the tracker does "
              "not hold, then what is not listed", got["進度"],
              ["收成 10/28–11/4（週三 20:00 截止）：完成 9 · 進行中 3 · 在等 2",
               "#1.01 官網改版｜完成 2、進行中 1：page live；另 2 件", "#1.02 SEO 文章（負責人 Ann Lee）｜完成：three articles",
               "#2.01 Atlas 搜尋｜完成：index rebuilt", "不在 Tracker｜完成：inbox cleared", "不在 Tracker｜進行中：notes",
               "另有 4 件完成、1 件進行中沒列出，見收成檔"])
        check("卡關 names the item a waiting line is tied to", got["卡關"], ["#1.01 needs a call", "which keyword"])
        check("待討論 asks about a status the week's work overtook, and does not also offer that paused item for dropping",
              got["待討論"], ["#1.02 SEO 文章：本週有進度，Tracker 還是「未開始」，要改狀態嗎？",
                             "#2.01 Atlas 搜尋：本週有進度，Tracker 還是「暫停」，要改狀態嗎？", "#2.09 舊案：留著、交給別人，還是放棄？"])
        check("what Monday's recap repeats: the lines, what is left, and the items still moving",
              (note["lines"][0][:13], len(note["lines"]), note["waiting"], note["left"], note["moving"], note["totals"]["shipped"]),
              ("#1.01 官網改版｜完成", 5, ["#1.01 needs a call", "which keyword"], {"shipped": 4, "moving": 1, "waiting": 0}, ["1.01"], 9))
        units = picked([(item_id(i, r), r) for i, r in enumerate(tagged)], titems)[0]
        gid = units[0]["id"]
        check("an item's unit has its own id: the place of its first line and a hash of all of them",
              (re.fullmatch(r"g\d+-[0-9a-f]{6}", gid) is not None, [u["item"] for u in units], len(units[0]["rows"])),
              (True, ["1.01", "1.02", "2.01", "", ""], 3))
        got = dict(parts_for(trun, "Xu", tagged, None, True, {gid: "首頁上線、導覽修好；頁尾草稿中"}, titems))
        check("the short line of an item's unit says all its lines at once", got["進度"][1],
              "#1.01 官網改版｜完成 2、進行中 1：首頁上線、導覽修好；頁尾草稿中")
        other = [r if r[6] != "nav fixed" else hrow("shipped", "nav rebuilt", "1.01") for r in tagged]
        check("a short line written for an item's unit does not fit once one of its lines changed",
              dict(parts_for(trun, "Xu", other, None, True, {gid: "首頁上線、導覽修好；頁尾草稿中"}, titems))["進度"][1],
              "#1.01 官網改版｜完成 2、進行中 1：page live；另 2 件")
        wide = [hrow("totals", "shipped 8 · moving 0 · waiting 0")] + [hrow("shipped", "work %d" % n, "9.%02d" % n) for n in range(8)]
        witems = {"9.%02d" % n: it("9.%02d" % n, "項目 %d" % n, "Xu", "進行中") for n in range(8)}
        check("at most six items are listed, and the rest are counted",
              [x[:5] for x in dict(parts_for(trun, "Xu", wide, None, True, None, witems))["進度"][1:]],
              ["#9.0%d" % n for n in range(6)] + ["另有 2 "])
        check("AC-17: lines tied to items but no item list for the week: the block by kind, as before",
              dict(parts_for(trun, "Xu", tagged, None, True))["進度"][1:4], ["完成：page live", "完成：nav fixed", "完成：three articles"])
        check("an item's name loses its closing bracketed note, never one in the middle, and is cut",
              [item_name({"項目": x}) for x in ("Future Builders 營隊講座（清華分會，2027/1/23）", "業務流程（Operation）結構化",
                                              "（全部都是括號）", "很長的項目名稱" * 5)],
              ["Future Builders 營隊講座", "業務流程（Operation）結構化", "（全部都是括號）", ("很長的項目名稱" * 5)[:23] + "…"])
        check("a tag for an item the week's list does not hold reads as no item",
              dict(parts_for(trun, "Xu", [hrow("shipped", "odd one", "8.88")], None, True, None, titems))["進度"],
              ["不在 Tracker｜完成：odd one"])
        # AC-16: an item its owner harvested around for three recorded weeks without a line on it
        wk = [R.previous_week(R.previous_week(W)), R.previous_week(W), W]
        seen3 = {wk[0]: {"people": ["Xu", "Ann Lee"], "items": ["1.01"]}, wk[1]: {"people": ["Xu"], "items": []},
                 wk[2]: {"people": ["Xu"], "items": ["1.01", "1.02", "2.01"]}}
        ask = "：三週沒有收成紀錄，還在進行嗎？"
        check("silent items: the owner's own, 進行中, untouched for three recorded weeks, P0 first, two at most",
              dict(parts_for(trun, "Xu", tagged, None, True, None, titems, seen3))["待討論"][2:],
              ["#3.02 客戶見證" + ask, "#3.03 內部訓練" + ask])
        for name, seen_x in (("two recorded weeks", {w: seen3[w] for w in wk[1:]}),
                             ("a week the owner did not harvest", dict(seen3, **{wk[1]: {"people": ["Ann Lee"], "items": []}})),
                             ("this week not recorded", {w: seen3[w] for w in wk[:2]}),
                             ("three recorded weeks, none of them this one",
                              {R.previous_week(wk[0]): seen3[wk[0]], wk[0]: seen3[wk[1]], wk[1]: seen3[wk[1]]})):
            check("silent items: %s, and nothing is asked" % name,
                  len(dict(parts_for(trun, "Xu", tagged, None, True, None, titems, seen_x))["待討論"]), 2)
        check("silent items: an item someone touched in those weeks is not asked about",
              [x for x in dict(parts_for(trun, "Xu", tagged, None, True, None, titems,
                                         dict(seen3, **{wk[0]: {"people": ["Xu"], "items": ["3.02", "3.03", "3.01"]}})))["待討論"] if ask in x], [])
        # the whole beat on a week tied to items: `collect` kept the items, the Ledger rows carry them
        st2 = s_start(W, cfgp, "2026-11-05T09:50:00+08:00", base=os.path.join(tmp, "runs"))
        open(st2["calls"][0]["save"], "w").write(sheet("Weeks!A%d:T%d" % (rr, rr), [weeks]))
        arows = [[W, at, "ann", "Ann Lee", "", "totals", "shipped 2 · moving 1 · waiting 0", "harvest-ann.md", ""],
                 [W, at, "ann", "Ann Lee", "SEO", "shipped", "three articles live (abc1234)", "harvest-ann.md", "1.02"],
                 [W, at, "ann", "Ann Lee", "SEO", "shipped", "the sitemap fixed", "harvest-ann.md", ""],
                 [W, at, "ann", "Ann Lee", "SEO", "moving", "the FAQ page", "harvest-ann.md", "1.02"]]
        for c in st2["calls"][1:]:
            a, b = (int(x) for x in re.match(r"^Harvest!A(\d+):I(\d+)$", c["args"]["range_name"]).groups())
            open(c["save"], "w").write(sheet(c["args"]["range_name"], arows[a - first:b - first + 1]))
        check("no item list kept for the week: asked line by line, and nothing says 不在 Tracker",
              (s_items(st2["dir"], routing)["by_item"], [x["kind"] for x in s_items(st2["dir"], routing)["items"]],
               UNTRACKED in s_render(st2["dir"], routing, "11-05 09:55")["blocks"][0]["body"]),
              (False, ["shipped", "shipped", "moving"], False))
        json.dump({"week": W, "snapshot": R.previous_week(W), "items": titems}, open(H.items_path(W), "w"), ensure_ascii=False)
        check("an item list is kept, but no row of the week is tied to an item: the block by kind",
              (s_items(st["dir"], routing)["by_item"], UNTRACKED in s_render(st["dir"], routing, "11-05 09:40")["blocks"][0]["body"]),
              (False, False))
        it2 = s_items(st2["dir"], routing)
        check("items: an item's lines are asked for as one, with the item named and each line's kind",
              (it2["by_item"], [(x["kind"], x.get("item"), [y["kind"] for y in x.get("lines", [])]) for x in it2["items"]]),
              (True, [("item", "#1.02 SEO 文章", ["shipped", "moving"]), ("shipped", None, [])]))
        json.dump({it2["items"][0]["id"]: "三篇文章上線，FAQ 頁草稿中", it2["items"][1]["id"]: "sitemap 修好了"},
                  open(it2["save"], "w"), ensure_ascii=False)
        out2 = s_render(st2["dir"], routing, "11-05 09:55", short_path=it2["save"])
        check("render: the block by item, with the model's lines",
              (out2["by_item"], out2["short"]["used"], out2["blocks"][0]["body"].split("\n")[:5]),
              (True, 2, ["進度", "\t收成 10/28–11/4（週三 20:00 截止）：完成 2 · 進行中 1 · 在等 0",
                         "\t#1.02 SEO 文章｜完成 1、進行中 1：三篇文章上線，FAQ 頁草稿中", "\t不在 Tracker｜完成：sitemap 修好了",
                         "\t業務：call Acme back"]))
        kept = json.load(open(progress_path(W), encoding="utf-8"))
        check("render keeps the week's lines for Monday's recap",
              (kept["week"], kept["span"], kept["by_item"], list(kept["people"]), kept["people"]["Ann Lee"]["lines"][0][:12],
               kept["people"]["Ann Lee"]["moving"]),
              (W, "10/28–11/4", True, ["Ann Lee"], "#1.02 SEO 文章", ["1.02"]))
        json.dump({"week": "2026-W01", "items": titems}, open(H.items_path(W), "w"), ensure_ascii=False)
        check("an item list kept for another week is not used", s_items(st2["dir"], routing)["by_item"], False)
        for what, bad in (("an owner that is not text", dict(titems, **{"1.02": dict(titems["1.02"], 負責人=7)})),
                          ("an item with no number", dict(titems, **{"1.02": {k: v for k, v in titems["1.02"].items() if k != "#"}})),
                          ("an item filed under another number", dict(titems, **{"9.99": titems["1.02"]})),
                          ("an item that is not an object", dict(titems, **{"1.02": "SEO"})),
                          ("a status that is not text", dict(titems, **{"1.02": dict(titems["1.02"], 狀態=None)}))):
            json.dump({"week": W, "items": bad}, open(H.items_path(W), "w"), ensure_ascii=False)
            check("an item list with %s is not used: the block is written by kind" % what,
                  (load_items(W), s_items(st2["dir"], routing)["by_item"]), (None, False))
        json.dump({"weeks": {"2026-W99": {"people": ["Ann Lee"], "items": []}, W: {"people": ["Ann Lee"], "items": [["x"]]}}},
                  open(H.seen_path(), "w"))
        json.dump({"week": W, "items": titems}, open(H.items_path(W), "w"), ensure_ascii=False)
        try:
            check("remembered weeks that do not read cost the silence question, not the block",
                  s_render(st2["dir"], routing, "11-05 09:56", short_path=it2["save"])["by_item"], True)
        except (L.Refuse, TypeError, KeyError, AttributeError) as e:
            check("remembered weeks that do not read cost the silence question, not the block", "crashed: %r" % e, "rendered")
        os.remove(H.seen_path())
        os.remove(H.items_path(W))
        os.remove(progress_path(W))
        open(os.path.join(state, "2026-W44.tidy.done"), "w").write("x")
        out = s_render(st["dir"], routing, "11-05 09:40")
        check("after tidy's fill, 下一步 is not written twice",
              [b["heading"] for b in out["blocks"] if "下一步" in b["body"]], [])
        open(st["calls"][0]["save"], "w").write(sheet("Weeks!A%d:T%d" % (rr, rr), [[W]]))
        out = s_render(st["dir"], routing, "11-05 13:05")
        check("without collect, everyone is 本週無資料", (out["harvest"], out["counts"]["quiet"]), ("not-recorded", 3))
        shutil.rmtree(rdir)
        out = s_render(st["dir"], routing, "11-05 13:05")
        by = {b["heading"]: b for b in out["blocks"]}
        check("without Monday's facts, the harvest alone", (out["facts"], by["財務"]["body"]), (None, "進度\n\t" + QUIET))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("sections.py selftest: %d FAILED" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("sections.py selftest: all checks passed")
    return 0


MUTATIONS = [
    ("the Harvest read stops at its first page", [("for a in range(first, last + 1, L.PAGE)]",
                                                   "for a in range(first, first + 1, L.PAGE)]")]),
    ("a quiet week reads as progress", [('    if not rows or all(r[5] == "quiet" for _, r in rows):\n', "    if not rows:\n")]),
    ("no cap on the choices", [("for x in mine(run, who, facts.get(\"paused\", [])) if x[\"#\"] not in stale][:CHOICES]",
                                "for x in mine(run, who, facts.get(\"paused\", [])) if x[\"#\"] not in stale]")]),
    ("下一步 written twice", [("        if not filled:\n", "        if True:\n")]),
    ("an All action reaches nobody", [('        if who in owners or (everyone and "全體" in owners):', '        if who in owners:')]),
    ("a 全體 tracker item fills every team", [('        if who in owners or (everyone and "全體" in owners):',
                                              '        if who in owners or "全體" in owners:')]),
    ("grouped headings get a block", [('        if h.get("grouped_with_previous") or not h.get("primary", True):',
                                       '        if not h.get("primary", True):')]),
    ("an unknown owner gets a block", [("        if not who:\n            nameless.append", "        if False:\n            nameless.append")]),
    ("an unharvested week is read", [('    harvested = row[18] == "ok"', "    harvested = True")]),
    ("other weeks' harvest rows count", [("if L.pad(x, 9)[0] == run[\"week\"]]", "]")]),
    ("aliases ignored", [("        owners = R.owners_of(run, e.get(field))",
                          "        owners = [e.get(field)]")]),
    ("the short line is ignored", [('        if u["id"] in short:\n            return short[u["id"]]\n',
                                     '        if False:\n            return short[u["id"]]\n')]),
    ("the fallback is not cut", [('        return fallback(u["rows"][0][6]) + (', '        return u["rows"][0][6] + (')]),
    ("a line with no Chinese is used", [('           else "no Chinese" if not cjk\n', "")]),
    ("a mostly English line is used", [("if words * 3 > cjk else None)", "if False else None)")]),
    ("a long line is used", [("if len(line) > SHORT_MAX", "if False")]),
    ("its own label is kept", [('    line = LABEL.sub("", v.strip()).strip()', "    line = v.strip()")]),
    ("a missing line goes unreported", [("            missing.append(i)\n", "            pass\n")]),
    ("a missing file fails the beat", [("    if not path or not os.path.exists(path):", "    if not path:")]),
    ("past the caps is asked for", [('    return progress[:CAP["進度"]], blocked[:CAP["卡關"]]', "    return progress, blocked")]),
    ("the span and counts line is lost", [("    if tot:\n        # SKB-128: what the harvest covers", "    if False:\n        # SKB-128: what the harvest covers")]),
    ("what 進度 leaves out goes unnamed", [("        if more:\n", "        if False:\n")]),
    ("what 卡關 leaves out goes unnamed", [('        if left["waiting"] > 0:', "        if False:")]),
    ("the count left out is the harvest's total", [
        ('left = {k: tot[k] - sum(1 for u in progress for r in u["rows"] if r[5] == k) for k in ("shipped", "moving")}',
         'left = {k: tot[k] for k in ("shipped", "moving")}')]),
    ("a kind with nothing left out is named", [('for k in ("shipped", "moving") if left[k] > 0]', 'for k in ("shipped", "moving")]')]),
    ("the span is the calendar week", [("    end = L.monday(week) + timedelta(days=2)\n    return", "    end = L.monday(week) + timedelta(days=6)\n    return")]),
    ("a totals row that does not parse is used", [
        ("    found = [t for t in (L.parse_totals(r[6]) for _, r in rows if r[5] == L.HARVEST_TOTALS) if t]",
         "    found = [L.parse_totals(r[6]) or dict.fromkeys(L.HARVEST_KINDS, 0) for _, r in rows if r[5] == L.HARVEST_TOTALS]")]),
    ("a person with no heading is asked for", [('    for u in shown(harvest, routed_people(run, routing), items):\n        rows = u["rows"]',
                                                '    for u in shown(harvest, None, items):\n        rows = u["rows"]')]),
    # SKB-128: the block by tracker item
    ("an item's lines are listed one by one", [("    if items:\n        groups = {}\n", "    if False:\n        groups = {}\n")]),
    ("an item's unit id is only its place", [
        ('            h = hashlib.sha256("\\x1f".join([members[0][1][3], num] + [r[6] for _, r in members]).encode("utf-8")).hexdigest()[:6]',
         '            h = "000000"')]),
    ("an item's bracketed note stays in its name", [('    return R.clip(PAREN_TAIL.sub("", name) or name, n)', "    return R.clip(name, n)")]),
    ("an item's line says one kind only", [("    if len(rows) == 1:\n        return KIND_ZH[rows[0][5]]\n", "    if True:\n        return KIND_ZH[rows[0][5]]\n")]),
    ("someone else's item is not named as theirs", [('else "（負責人 %s）" % R.clip(it["負責人"], 16)', 'else ""')]),
    ("a week not tied to items says 不在 Tracker", [("        if not items:\n            return what\n", "        if False:\n            return what\n")]),
    ("a waiting line loses its item", [('    waits = [("#%s " % u["item"] if u["item"] else "") + said(u) for u in blocked]',
                                        "    waits = [said(u) for u in blocked]")]),
    ("a stale status is not asked about", [('    stale = [n for n in moved if items[n].get("狀態") in STALE]', "    stale = []")]),
    ("a paused item already asked about is offered for dropping too", [
        ("for x in mine(run, who, facts.get(\"paused\", [])) if x[\"#\"] not in stale][:CHOICES]",
         "for x in mine(run, who, facts.get(\"paused\", []))][:CHOICES]")]),
    ("silence is asked about after two recorded weeks", [("    if len(weeks) < SILENT_WEEKS or weeks[-1] != week or", "    if weeks[-1] != week or")]),
    ("silence is asked about in a week not recorded", [("    if len(weeks) < SILENT_WEEKS or weeks[-1] != week or", "    if len(weeks) < SILENT_WEEKS or")]),
    ("silence is asked about though the owner did not harvest", [
        (' or not all(who in seen[w]["people"] for w in weeks):', ":")]),
    ("an item someone touched is asked about", [(" and num not in touched\n", "\n")]),
    ("someone else's silent item is asked about", [('\n             and who in R.owners_of(run, it.get("負責人"))]', "]")]),
    ("no cap on the silent items", [('(it.get("Priority") or "P9", it["#"]))[:SILENT_MAX]', '(it.get("Priority") or "P9", it["#"]))')]),
    ("an item list of the wrong shape is used", [("    return items if all(sound(num, it) for num, it in items.items()) else None",
                                                  "    return items")]),
    ("an item list of another week is used", [('isinstance(got, dict) and got.get("week") == week else None', "isinstance(got, dict) else None")]),
    ("a week with no tied line is written by item", [("    return items if items and any(r[8] in items for r in harvest) else None",
                                                      "    return items or None")]),
    ("an item's lines are asked for one by one", [('        if u["item"] and rows[0][5] != "waiting":', "        if False:")]),
    ("the week's lines are not kept for the recap", [("    if harvested:\n        # what Monday's recap repeats", "    if False:\n        # what Monday's recap repeats")]),
    ("only the first totals row of a name counts", [
        ("    return {k: sum(t[k] for t in found) for k in L.HARVEST_KINDS} if found else None",
         "    return found[0] if found else None")]),
    ("a row with no text counts as a listed line", [("    rows = [x for x in rows if x[1][6].strip()]\n    lines = [x for x in rows",
                                                     "    lines = [x for x in rows")]),
    ("an id is only the row's place", [('    return "h%d-%s" % (i + 1, h)', '    return "h%d-000000" % (i + 1)')]),
    ("the Pulse lost", [('                out["進度"] += [line for line in p["lines"] if line.startswith("業務：")]',
                         "                pass")]),
    ("a full block cuts the Pulse and the overdue item off", [
        ("    return [(label, lines_) for label, lines_ in out.items() if lines_]",
         "    return [(label, lines_[:CAP.get(label, len(lines_))]) for label, lines_ in out.items() if lines_]")]),
]


def mutate():
    import shutil
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")
    tmpd = tempfile.mkdtemp(prefix="sections-mutate-")
    shutil.copy2(os.path.join(HERE, "render_block.py"), os.path.join(tmpd, "render_block.py"))
    env = dict(os.environ, ZYNKR_OPS_WEEKLY_SCRIPTS=core_dir())

    def run(text):
        p = os.path.join(tmpd, "sections_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True, env=env).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    ok = True
    for name, pairs in MUTATIONS:
        bad = [old for old, _ in pairs if code.count(old) != 1]
        if bad:
            print("mutate: %-36s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = code
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        rc = run(mutated + marker + rest)
        print("mutate: %-36s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    shutil.rmtree(tmpd, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
