#!/usr/bin/env python3
"""The meeting's minutes (SKB-091 AC-14): find the Thursday meeting's transcript by its calendar title and
date, then check what the model read out of it before anything is written.

Like ledger.py, this script computes and never talks to Google or Fireflies. Each step prints the
exact calls to make, with a path to save each result to word for word; the next step reads them back.

    minutes.py start --week W [--config PATH] [--now ISO]
        -> a run folder, the Fireflies listing call for the meeting day and the tracker's size
    minutes.py find  --dir D
        -> the tracker reads (#, 項目) and the one transcript titled `meeting.calendar_title` on that
           Thursday (Taipei) with the call that fetches it; or "found": false: read the meeting's Doc
           section as edited instead
    minutes.py items --dir D --open open.json
        -> SKB-151: the meeting section's open bullets (open_items.py's output, kept as D/open.json) and
           Wednesday's 會後收掉 candidates (<week>.closing.json, kept as D/candidates.json), to hold the
           transcript against
    minutes.py check --dir D --input minutes.json [--now ISO]
        -> refuses an owner off the roster, an item # the tracker lacks, a date that is not a date;
           writes rows.json (the Ledger's Decisions block), block.json (the Doc's 會議紀錄 block, for
           render_block.py ops), fill.json (each person's 下一步 and 待討論, for tidy) and closures.json
           (the bullets tidy removes from next week's section, SKB-151)

minutes.json, written by the model from the transcript (or the Doc) and nothing else:

    {"source": "fireflies" | "doc",
     "decisions": [{"text", "item"?}],
     "actions":   [{"what", "owner": name | [names] | "", "due": "YYYY-MM-DD" | "", "item"?, "new"?: true}],
     "blockers":  [{"text", "owner"?, "item"?, "since"?: "YYYY-MM-DD"}],
     "topics":    [{"text", "owner"?}],
     "dropped":   [{"item", "text"}],
     "progress":  [{"item", "text", "state"?}],
     "closed":    [{"bullet", "how": "done" | "drop", "quote"}],
     "kept":      [{"bullet", "quote"}]}

An owner is a roster name exactly as the tracker writes it (the config's `chat_ids` display names) or
`All`. An action with no owner or no date stays open (狀態 待定). A blocker first seen more than seven
days before the meeting is a risk (類型 風險).

`closed` and `kept` (SKB-151) name bullets by the ids `items` listed. `closed` is a bullet of the Doc the
meeting said is finished or dropped, with the words that said so; only a transcript can say it. `kept` is a
會後收掉 candidate someone said is not done. Every other candidate still in the section as Wednesday read
it closes: the meeting saw it listed and let it stand. With the Doc as the source no candidate closes,
since nothing shows what was said; they are asked again next Wednesday. The closures are recorded in the
會議紀錄 block's 收掉 lines and in closures.json, not in the Ledger: Monday's recap reads any kind it does
not know as an open question.

Exit codes are ledger.py's: 2 config or arguments · 3 input refused · 4 no transcript.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta

LEDGER_API = 4   # SKB-128: the Harvest tab gained `item`; the three skills move together (3 = SKB-118: check_saved)


def core_dir():
    """zynkr-ops-weekly's scripts folder, which holds ledger.py (SKB-091: the Ledger code stays in the
    core and the other skills read it there, never a copy). ZYNKR_OPS_WEEKLY_SCRIPTS overrides it."""
    here = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.get("ZYNKR_OPS_WEEKLY_SCRIPTS")
    tried = ([env] if env else []) + [here, os.path.normpath(os.path.join(here, "..", "..", "zynkr-ops-weekly", "scripts"))]
    for d in tried:
        if os.path.exists(os.path.join(d, "ledger.py")):
            return d
    raise SystemExit("minutes.py: zynkr-ops-weekly's ledger.py not found (looked in %s). Install zynkr-ops-weekly, "
                     "or set ZYNKR_OPS_WEEKLY_SCRIPTS to its scripts folder." % ", ".join(tried))


sys.path.insert(0, core_dir())
import ledger as L  # noqa: E402
if getattr(L, "API", 1) != LEDGER_API:
    raise SystemExit("minutes.py: zynkr-ops-weekly's ledger.py speaks API %s, this script needs %s; install both "
                     "skills at the same version" % (getattr(L, "API", 1), LEDGER_API))

BLOCK_ROWS = L.BLOCKS["Decisions"][0]
ITEM_RE = re.compile(r"^\d{1,2}\.\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VOCAB = ("未開始", "進行中", "暫停", "完成", "放棄")
RISK_DAYS = 7
MAX_TEXT = 200
TITLE = "會議紀錄"                     # the block's title after its stamp, like the old 本週會議議程


# ── the week ─────────────────────────────────────────────────────────────────
def meeting_day(week):
    return L.monday(week) + timedelta(days=3)


def wb_label(week):
    m = L.monday(week)
    return "WB %d/%d" % (m.month, m.day)


def md(d):
    return "%d/%d" % (d.month, d.day)


def load_settings(path):
    raw = json.load(open(path, encoding="utf-8"))
    title = str((raw.get("meeting") or {}).get("calendar_title") or "").strip()
    if not title or title.startswith("<"):
        raise L.Refuse(2, "config %s has no meeting.calendar_title" % path)
    names = [k for k in (raw.get("chat_ids") or {}) if not k.startswith("$") and not k.startswith("users/")]
    if not names:
        raise L.Refuse(2, "config %s: chat_ids holds no display names, so there is no roster" % path)
    return {"title": title, "roster": names + ["All"]}


def doc_heading(d):
    """The week section's heading as the scaffold writes it: `Nov 5, 2026`, the day never zero-padded
    (`MONTHS[m] + ' ' + getDate()` in scaffold.gs). strftime's %d would give `Nov 05, 2026`, a heading
    the Doc never holds (W45 review, 10-31)."""
    return "%s %d, %d" % (d.strftime("%b"), d.day, d.year)


# ── start ────────────────────────────────────────────────────────────────────
def m_start(week, config=None, now=None, base=None):
    cfg = L.load_config(config)
    st = load_settings(cfg["path"])
    now = L.parse_now(now)
    thu = meeting_day(week)
    d = os.path.join(base or os.path.join(L.state_dir(), "runs"), "%s-minutes-%s" % (week, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    run = dict(cfg, dir=d, week=week, meeting=thu.isoformat(), title=st["title"], roster=st["roster"],
               heading=doc_heading(thu))
    L.save_run(run)
    listing = {"tool": "mcp__fireflies__fireflies_get_transcripts",
               "args": {"fromDate": (thu - timedelta(days=1)).isoformat(), "toDate": (thu + timedelta(days=1)).isoformat(),
                        "keyword": st["title"], "scope": "title", "format": "json", "limit": 10},
               "save": os.path.join(d, "listing.json")}
    calls = [listing, L.info_call(run, cfg["tracker"], "ti")]
    return {"dir": d, "week": week, "meeting": thu.isoformat(), "calls": calls}


# ── find ─────────────────────────────────────────────────────────────────────
def taipei_date(s):
    if not s:
        return None             # parse_now(None) means "now": an entry with no date is never today's
    try:
        return L.parse_now(s).date()
    except (ValueError, TypeError):
        return None


def pick(listing, title, thu):
    """The transcripts titled `title` held on `thu` (Taipei). Never "the latest": a recording on another
    day or under another title is not this meeting, whatever its date."""
    if isinstance(listing, dict) and isinstance(listing.get("result"), str):
        listing = json.loads(listing["result"])
    if not isinstance(listing, list):
        raise L.Refuse(3, "the Fireflies listing is not a JSON list (was it saved with format json?)")
    found = [t for t in listing if isinstance(t, dict) and str(t.get("title") or "").strip() == title
             and taipei_date(t.get("dateString")) == thu]
    return sorted(found, key=lambda t: -(t.get("duration") or 0))


def tracker_pages(run):
    """Columns A–D of the tracker tab in 50-row reads, as far as its grid goes: a read past the grid
    is an API error, not an empty page."""
    tabs = L.parse_info(L.load_result(os.path.join(run["dir"], "ti.txt")), run["tracker"])
    if run["tab"] not in tabs:
        raise L.Refuse(4, "the tracker has no tab %r (has %s)" % (run["tab"], ", ".join(sorted(tabs))))
    grid = tabs[run["tab"]][0]
    return [(a, min(a + L.PAGE - 1, grid), "%s!A%d:D%d" % (L.quote_tab(run["tab"]), a, min(a + L.PAGE - 1, grid)))
            for a in range(1, grid + 1, L.PAGE)]


def m_find(d):
    run = L.load_run(d)
    run["pages"] = tracker_pages(run)
    reads = [L.read_call(run, run["tracker"], rng, "t%d" % (i + 1)) for i, (_, _, rng) in enumerate(run["pages"])]
    p = os.path.join(d, "listing.json")
    if not os.path.exists(p):
        raise L.Refuse(3, "missing saved result: %s" % p)
    L.check_saved(p)
    try:
        listing = json.load(open(p, encoding="utf-8"))
    except ValueError as e:
        raise L.Refuse(3, "the Fireflies listing is not JSON (%s)" % e)
    found = pick(listing, run["title"], date.fromisoformat(run["meeting"]))
    if not found:
        run["source"] = "doc"
        L.save_run(run)
        return {"found": False, "meeting": run["meeting"], "heading": run["heading"], "calls": reads,
                "next": "read the %s section of the Doc as edited (get_doc_as_markdown) and say the minutes come from the Doc" % run["heading"]}
    t = found[0]
    run["source"], run["transcript"] = "fireflies", t["id"]
    L.save_run(run)
    out = {"found": True, "id": t["id"], "date": t.get("dateString"), "meeting": run["meeting"],
           "calls": [{"tool": "mcp__fireflies__fireflies_get_transcript", "args": {"transcriptId": t["id"]},
                      "save": os.path.join(d, "transcript.txt")}] + reads}
    if len(found) > 1:
        out["warning"] = "%d recordings of this meeting; took the longest (%s), the others: %s" % (
            len(found), t["id"], ", ".join(x["id"] for x in found[1:]))
    return out


# ── check ────────────────────────────────────────────────────────────────────
def tracker_index(run):
    """# -> 項目 from the paged read of columns A–D."""
    by_row = {}
    for i, (a, b, rng) in enumerate(run["pages"]):
        rows = L.parse_values(L.load_result(os.path.join(run["dir"], "t%d.txt" % (i + 1))), run["tracker"], rng)
        for j, cells in enumerate(rows):
            by_row[a + j] = L.pad(cells, 4)
    if [c.strip() for c in by_row.get(1, [])] != L.TRACKER_HEADER[:4]:
        raise L.Refuse(4, "tracker header changed: %r" % (by_row.get(1),))
    return {c[0].strip(): c[3].strip() for r, c in by_row.items()
            if r >= 2 and ITEM_RE.match(c[0].strip()) and c[3].strip()}


def text_of(x, key, where):
    v = x.get(key) if isinstance(x, dict) else None
    if not isinstance(v, str) or not v.strip():
        raise L.Refuse(3, "%s has no %s" % (where, key))
    v = re.sub(r"\s+", " ", v).strip()
    if len(v) > MAX_TEXT:
        raise L.Refuse(3, "%s: %s is longer than %d characters; say it shorter" % (where, key, MAX_TEXT))
    return v


def owners_of(x, roster, where, required=False):
    v = x.get("owner", "")
    names = [v] if isinstance(v, str) else v
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise L.Refuse(3, "%s: owner must be a name or a list of names" % where)
    names = [n.strip() for n in names if n.strip()]
    bad = [n for n in names if n not in roster]
    if bad:
        raise L.Refuse(3, "%s: %s is not on the roster (%s)" % (where, ", ".join(bad), ", ".join(roster)))
    if required and not names:
        raise L.Refuse(3, "%s has no owner" % where)
    return names


def date_of(x, key, where):
    v = str(x.get(key) or "").strip()
    if not v:
        return None
    if not DATE_RE.match(v):
        raise L.Refuse(3, "%s: %s %r is not a full date (YYYY-MM-DD)" % (where, key, v))
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise L.Refuse(3, "%s: %s %r is no such date" % (where, key, v))


def item_of(x, items, where, required=False, new_ok=False):
    v = str(x.get("item") or "").strip().lstrip("#")
    if new_ok and x.get("new") is True:
        if v:
            raise L.Refuse(3, "%s is marked new but names #%s" % (where, v))
        return "新"
    if not v:
        if required:
            raise L.Refuse(3, "%s names no item #" % where)
        return ""
    if v not in items:
        raise L.Refuse(3, "%s: #%s is not in the tracker%s" % (where, v, " (mark it new if it is new work)" if new_ok else ""))
    return v


def entries(data, key):
    v = data.get(key, [])
    if not isinstance(v, list):
        raise L.Refuse(3, "%s must be a list" % key)
    return v


# ── items (SKB-151) ──────────────────────────────────────────────────────────
def closing_path(week):
    """Wednesday's 會後收掉 candidates, written by sections.py render (the same path)."""
    return os.path.join(L.state_dir(), "%s.closing.json" % week)


def m_items(d, open_path):
    """Keep the meeting section's open bullets and Wednesday's candidates in the run folder, and list both."""
    run = L.load_run(d)
    try:
        opened = json.load(open(open_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise L.Refuse(3, "cannot read %s (%s)" % (open_path, e))
    if not isinstance(opened, dict) or not isinstance(opened.get("items"), list):
        raise L.Refuse(3, "%s is not open_items.py's output" % open_path)
    if opened.get("section") != run["heading"]:
        raise L.Refuse(3, "%s lists %r, not the meeting's section %r" % (open_path, opened.get("section"), run["heading"]))
    cands, why = [], None
    p = closing_path(run["week"])
    if os.path.exists(p):
        try:
            got = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise L.Refuse(3, "cannot read %s (%s): re-run sections' confirm, or remove it to ask no "
                              "candidates this week" % (p, e))
        if not isinstance(got, dict) or not isinstance(got.get("candidates", []), list):
            raise L.Refuse(3, "%s is not a closing list" % p)
        if got.get("section") == run["heading"]:
            cands = got.get("candidates", [])
        else:
            why = "%s is for %r, not %r" % (p, got.get("section"), run["heading"])
    else:
        why = "no 會後收掉 list this week (sections did not run, or listed none)"
    json.dump(opened, open(os.path.join(d, "open.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cands, open(os.path.join(d, "candidates.json"), "w", encoding="utf-8"), ensure_ascii=False)
    here = {it["id"] for it in opened["items"]}
    return {"section": run["heading"],
            "open": [{"id": it["id"], "person": it.get("person"), "label": it["label"], "since": it.get("since"),
                      "open_sub_items": it.get("open_sub_items") or []}
                     for it in opened["items"]],
            "candidates": [{"id": c["id"], "person": c.get("person"), "label": c["label"], "harvest": c.get("harvest"),
                            "still_open": c["id"] in here} for c in cands],
            "candidates_note": why,
            "rule": "closed: a bullet the meeting said is done or dropped, with the words. kept: a candidate someone said "
                    "is not done. Every other candidate still open closes. Name bullets only by these ids."}


def _ns(s):
    return re.sub(r"\s+", "", s or "")


def closures_of(data, run, opened, cands):
    """(closures, kept, left) from minutes.json's closed and kept: what tidy removes, and why."""
    closed_in, kept_in = entries(data, "closed"), entries(data, "kept")
    if opened is None:
        if closed_in or kept_in:
            raise L.Refuse(3, "closed and kept name bullets of the Doc: run `items` first")
        return [], [], []
    if closed_in and data.get("source") != "fireflies":
        raise L.Refuse(3, "closed: only the meeting's transcript can close a bullet; the Doc's own chips already do")
    by_id = {it["id"]: it for it in opened["items"]}
    cand = {c["id"]: c for c in cands}
    out, said, kept = [], set(), set()
    for i, x in enumerate(closed_in + kept_in):
        if not isinstance(x, dict):
            raise L.Refuse(3, "%s %d must be an object {bullet, quote}, not %r"
                           % ("closed" if i < len(closed_in) else "kept", 1 + (i if i < len(closed_in) else i - len(closed_in)), x))
    for i, x in enumerate(closed_in):
        w = "closed %d" % (i + 1)
        bid = str((x or {}).get("bullet") or "").strip()
        if bid not in by_id:
            raise L.Refuse(3, "%s: bullet %r is not an open bullet of %s (use the ids `items` listed)" % (w, bid, run["heading"]))
        if bid in said:
            raise L.Refuse(3, "%s: bullet %s is closed twice" % (w, bid))
        how = str(x.get("how") or "done").strip()
        if how not in ("done", "drop"):
            raise L.Refuse(3, "%s: how must be done or drop, not %r" % (w, how))
        said.add(bid)
        out.append(dict(by_id[bid], how=how, why="meeting", quote=text_of(x, "quote", w)))
    for i, x in enumerate(kept_in):
        w = "kept %d" % (i + 1)
        bid = str((x or {}).get("bullet") or "").strip()
        if bid not in cand:
            raise L.Refuse(3, "%s: %r is not one of Wednesday's 會後收掉 candidates" % (w, bid))
        if bid in said:
            raise L.Refuse(3, "%s: bullet %s is both closed and kept" % (w, bid))
        text_of(x, "quote", w)
        kept.add(bid)
    left = []
    for c in cands:
        if c["id"] in said or c["id"] in kept:
            continue
        if c["id"] not in by_id:
            left.append({"id": c["id"], "label": c["label"], "why": "edited or closed since Wednesday"})
        elif data.get("source") != "fireflies":
            left.append({"id": c["id"], "label": c["label"], "why": "no transcript: asked again next Wednesday"})
        else:
            out.append(dict(by_id[c["id"]], how="done", why="harvest", harvest=c.get("harvest") or ""))
    # tidy removes a bullet only with every open sub-item under it closed too: a close the Doc cannot carry
    # out is never recorded as one. Said in the meeting, it is refused; a silent candidate waits.
    listed = {(_ns(it["heading"]), _ns(it["text"])) for it in opened["items"]}
    while True:
        shut = {(_ns(c["heading"]), _ns(c["text"])) for c in out}
        bad = next((c for c in out if any((_ns(c["heading"]), _ns(k)) not in shut
                                          for k in c.get("open_sub_items") or [])), None)
        if bad is None:
            break
        loose = next(k for k in bad["open_sub_items"] if (_ns(bad["heading"]), _ns(k)) not in shut)
        if bad["why"] == "meeting" and (_ns(bad["heading"]), _ns(loose)) in listed:
            raise L.Refuse(3, "closed: bullet %s (%s) has an open sub-item %r: close that too, or leave the "
                              "bullet open" % (bad["id"], bad["label"], loose))
        out.remove(bad)
        left.append({"id": bad["id"], "label": bad["label"],
                     "why": ("an open sub-item: %s" % loose) if bad["why"] == "harvest" or
                            (_ns(bad["heading"]), _ns(loose)) in listed else
                            "said closed, but its sub-item %s has no id (written twice, or a Metrics row): set a "
                            "chip on it in the Doc" % loose})
    return out, sorted(kept), left


def closure_line(c):
    who = " — %s" % c["person"] if c.get("person") else ""
    if c["why"] == "harvest":
        return "%s%s · 收成已完成（%s），會上無異議" % (c["label"], who, c.get("harvest", "")[:40])
    return "%s%s · 會上說%s" % (c["label"], who, "已完成" if c["how"] == "done" else "放棄")


def check(data, run, items, now, bullets=None, cands=()):
    if not isinstance(data, dict):
        raise L.Refuse(3, "minutes.json must be an object")
    src = data.get("source")
    if src not in ("fireflies", "doc"):
        raise L.Refuse(3, "source must be fireflies or doc")
    if src != run.get("source"):
        raise L.Refuse(3, "source says %s but find chose %s" % (src, run.get("source") or "nothing (run find)"))
    roster, thu, week = run["roster"], date.fromisoformat(run["meeting"]), run["week"]
    source = "Fireflies %s" % run["transcript"] if src == "fireflies" else "Doc %s" % run["heading"]
    rows, prog, warnings = [], [], []
    doc = {"決議": [], "待辦": [], "卡關": [], "待討論": [], "放棄": [], "收掉": []}
    fill = {n: {"下一步": [], "待討論": []} for n in roster if n != "All"}
    cite = "〔%s 會議〕" % md(thu)
    opened, risks, unrouted = [], [], []

    def to_fill(names, label, line):
        targets = [n for n in roster if n != "All"] if "All" in names else names
        if not targets:
            unrouted.append(line)
        for n in targets:
            fill[n][label].append(line + cite)

    def row(kind, content, owner="", due="", item="", state=""):
        rows.append([week, run["meeting"], kind, content, owner, due, item, source, state])

    for i, x in enumerate(entries(data, "decisions")):
        w = "decision %d" % (i + 1)
        t, it = text_of(x, "text", w), item_of(x, items, w)
        row("決議", t, item=it)
        doc["決議"].append(t + (" · #%s" % it if it else ""))
    for i, x in enumerate(entries(data, "dropped")):
        w = "dropped %d" % (i + 1)
        it, t = item_of(x, items, w, required=True), text_of(x, "text", w)
        row("放棄", t, item=it)
        doc["放棄"].append("#%s %s — %s" % (it, items[it], t))
    for i, x in enumerate(entries(data, "actions")):
        w = "action %d" % (i + 1)
        t, names = text_of(x, "what", w), owners_of(x, roster, w)
        due, it = date_of(x, "due", w), item_of(x, items, w, new_ok=True)
        if due and due < thu:
            warnings.append("%s is due %s, before the meeting" % (w, due.isoformat()))
        state = "已排定" if names and due else "待定"
        row("行動", t, "、".join(names), due.isoformat() if due else "", it, state)
        line = "%s — %s · %s%s" % (t, "、".join(names) or "負責人未定", md(due) if due else "日期未定",
                                   " · #%s" % it if it and it != "新" else (" · 新項目" if it == "新" else ""))
        doc["待辦"].append(line)
        if state == "待定":
            opened.append(line)
        to_fill(names, "下一步", "%s%s" % (t, "（%s 前）" % md(due) if due else ""))
    for i, x in enumerate(entries(data, "blockers")):
        w = "blocker %d" % (i + 1)
        t, names = text_of(x, "text", w), owners_of(x, roster, w)
        it, since = item_of(x, items, w), date_of(x, "since", w)
        if since and since > thu:
            raise L.Refuse(3, "%s: since %s is after the meeting" % (w, since.isoformat()))
        age = (thu - since).days if since else 0
        kind = "風險" if age > RISK_DAYS else "卡關"
        row(kind, t + ("（自 %s）" % md(since) if since else ""), "、".join(names), "", it)
        line = t + (" — %s" % "、".join(names) if names else "") + (" · 已卡 %d 天，列為風險" % age if kind == "風險" else "")
        doc["卡關"].append(line)
        if kind == "風險":
            risks.append(line)
        to_fill(names, "待討論", t)
    for i, x in enumerate(entries(data, "topics")):
        w = "topic %d" % (i + 1)
        t, names = text_of(x, "text", w), owners_of(x, roster, w)
        row("待討論", t, "、".join(names))
        doc["待討論"].append(t + (" — %s" % "、".join(names) if names else ""))
        to_fill(names, "待討論", t)
    for i, x in enumerate(entries(data, "progress")):
        w = "progress %d" % (i + 1)
        it, t = item_of(x, items, w, required=True), text_of(x, "text", w)
        state = str(x.get("state") or "").strip()
        if state and state not in VOCAB:
            raise L.Refuse(3, "%s: state %r is not a 狀態 (%s)" % (w, state, " / ".join(VOCAB)))
        prog.append([week, run["meeting"], "進度", t, "", "", it, source, state])

    closures, kept, left = closures_of(data, run, bullets, list(cands or ()))
    doc["收掉"] = [closure_line(c) for c in closures]

    if len(rows) > BLOCK_ROWS:
        raise L.Refuse(3, "%d decisions, actions, blockers and topics do not fit the %d-row block; merge the smallest"
                       % (len(rows), BLOCK_ROWS))
    room = BLOCK_ROWS - len(rows)
    if len(prog) > room:
        warnings.append("%d progress lines left out of the Ledger: the block holds %d rows" % (len(prog) - room, BLOCK_ROWS))
    rows += prog[:room]

    sections = [(k, v) for k, v in doc.items() if v]
    if not sections:
        sections = [("決議", ["這次會議沒有談定的事"])]
    stamp_line = "〔自動彙整 %s · %s〕%s" % (wb_label(week), now.strftime("%m-%d %H:%M"), TITLE)
    body = "\n".join(sum(([k] + ["\t" + s for s in v] for k, v in sections), []))
    block = {"heading": run["heading"], "stamp_line": stamp_line, "body": body, "text": stamp_line + "\n" + body}
    decided = len(doc["決議"]) + len(doc["待辦"]) + len(doc["放棄"])
    return {"rows": rows, "block": block, "fill": {n: v for n, v in fill.items() if v["下一步"] or v["待討論"]},
            "closures": {"week": week, "section": run["heading"], "items": closures},
            "summary": {"source": src, "transcript": run.get("transcript"), "rows": len(rows),
                        "decisions": len(doc["決議"]), "actions": len(doc["待辦"]), "open_actions": opened,
                        "blockers": len(doc["卡關"]), "risks": risks, "topics": len(doc["待討論"]),
                        "dropped": len(doc["放棄"]), "progress": min(len(prog), room), "unrouted": unrouted,
                        "closed": {"meeting": sum(1 for c in closures if c["why"] == "meeting"),
                                   "harvest": sum(1 for c in closures if c["why"] == "harvest"),
                                   "kept": kept, "left": left, "open_read": bullets is not None},
                        "warnings": warnings,
                        "doc_key": {"starts": "〔自動彙整 %s · " % wb_label(week), "ends": "〕" + TITLE},
                        "delivered": ("no-decisions;" if not decided else "%d-decided;" % decided)
                                     + ("transcript-found" if src == "fireflies" else "doc-fallback")
                                     + (";%d-closed" % len(closures) if closures else "")}}


def m_check(d, input_path, now=None):
    run = L.load_run(d)
    if "source" not in run:
        raise L.Refuse(2, "run `find` first")
    try:
        data = json.load(open(input_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise L.Refuse(3, "cannot read %s (%s)" % (input_path, e))
    op, cp = os.path.join(d, "open.json"), os.path.join(d, "candidates.json")
    opened = json.load(open(op, encoding="utf-8")) if os.path.exists(op) else None
    cands = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else []
    res = check(data, run, tracker_index(run), L.parse_now(now), opened, cands)
    for name, obj in (("rows.json", res["rows"]), ("block.json", {"blocks": [res["block"]]}), ("fill.json", res["fill"]),
                      ("closures.json", res["closures"])):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    return dict(res["summary"], dir=d, block=res["block"]["text"],
                files={"rows": os.path.join(d, "rows.json"), "block": os.path.join(d, "block.json"),
                       "fill": os.path.join(d, "fill.json"), "closures": os.path.join(d, "closures.json")})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("start")
    s.add_argument("--week", required=True)
    s.add_argument("--config")
    s.add_argument("--now")
    f = sub.add_parser("find")
    f.add_argument("--dir", required=True)
    it = sub.add_parser("items")
    it.add_argument("--dir", required=True)
    it.add_argument("--open", required=True, help="open_items.py's output for the meeting's section")
    c = sub.add_parser("check")
    c.add_argument("--dir", required=True)
    c.add_argument("--input", required=True)
    c.add_argument("--now")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd == "start":
            L.emit(m_start(a.week, a.config, a.now))
        elif a.cmd == "find":
            res = m_find(a.dir)
            L.emit(res)
            return 0 if res["found"] else 4
        elif a.cmd == "items":
            L.emit(m_items(a.dir, a.open))
        elif a.cmd == "check":
            L.emit(m_check(a.dir, a.input, a.now))
        else:
            ap.print_help()
            return 2
    except L.Refuse as e:
        print("minutes.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


# ── selftest ─────────────────────────────────────────────────────────────────
def selftest():
    import shutil
    import tempfile
    fails = []

    def ok(name, cond, got=None):
        if not cond:
            fails.append("%s%s" % (name, "" if got is None else ": got %r" % (got,)))

    def refuses(name, fn, *args):
        try:
            fn(*args)
        except L.Refuse:
            return
        fails.append("%s: did not refuse" % name)

    tmp = tempfile.mkdtemp(prefix="minutes-selftest-")
    try:
        cfg = os.path.join(tmp, "cfg.json")
        json.dump({"google_account": "ops@example.com",
                   "sources": {"main_tracker": {"id": "TRK", "tab": "H2 項目", "cycle": "2026H2"},
                               "ledger": {"id": "LED", "epoch_week": "2026-W40"}},
                   "chat_ids": {"$note": "x", "Ann Lee": "ann@x", "Ben Wu": "ben@x", "users/123": "cy@x"},
                   "meeting": {"calendar_title": "Team Weekly Meeting"}}, open(cfg, "w"))
        st = m_start("2026-W43", cfg, "2026-10-23T08:05:00+08:00", base=tmp)
        d = st["dir"]
        ok("start: meeting is Thursday", st["meeting"] == "2026-10-22", st["meeting"])
        ok("start: listing call for the day around it", st["calls"][0]["args"]["fromDate"] == "2026-10-21"
           and st["calls"][0]["args"]["toDate"] == "2026-10-23" and st["calls"][0]["args"]["format"] == "json")
        ok("start: the tracker's size", st["calls"][1]["tool"].endswith("get_spreadsheet_info") and len(st["calls"]) == 2)
        open(os.path.join(d, "ti.txt"), "w").write('Spreadsheet: "T" (ID: TRK)\n  - "Other" (ID: 1) | Size: 900x5\n'
                                                  '  - "H2 項目" (ID: 2) | Size: 72x13\n')
        run = L.load_run(d)
        ok("start: roster is the display names plus All", run["roster"] == ["Ann Lee", "Ben Wu", "All"], run["roster"])
        ok("start: heading in the Doc's format", run["heading"] == "Oct 22, 2026", run["heading"])
        ok("heading: a single-digit day is not zero-padded, as the scaffold writes it",
           doc_heading(meeting_day("2026-W45")) == "Nov 5, 2026", doc_heading(meeting_day("2026-W45")))

        def listing(*ts):
            json.dump([{"id": i, "title": ti, "dateString": ds, "duration": du} for i, ti, ds, du in ts],
                      open(os.path.join(d, "listing.json"), "w"))
        listing(("A", "Team Weekly Meeting", "2026-10-22T13:00:00.000Z", 33.4),
                ("B", "Team Weekly Meeting", "2026-10-15T13:00:00.000Z", 25.5),
                ("C", "Sales sync", "2026-10-22T05:00:00.000Z", 40))
        r = m_find(d)
        ok("find: the meeting's transcript", r["found"] and r["id"] == "A", r)
        ok("find: the fetch call", r["calls"][0]["args"] == {"transcriptId": "A"})
        ok("find: tracker reads stop at the grid", [c["args"]["range_name"] for c in r["calls"][1:]]
           == ["'H2 項目'!A1:D50", "'H2 項目'!A51:D72"], r["calls"][1:])
        listing(("A", "Team Weekly Meeting", "2026-10-21T17:00:00.000Z", 9))     # 01:00 Thu Taipei, 22 Oct
        ok("find: the date is Taipei's", m_find(d).get("id") == "A")
        ok("find: an entry with no date is never today's", taipei_date(None) is None and taipei_date("") is None)
        listing(("A", "Team Weekly Meeting", "2026-10-21T15:00:00.000Z", 9))     # 23:00 Wed Taipei
        ok("find: another day is not the meeting", m_find(d)["found"] is False)
        listing(("A", "Team weekly meeting", "2026-10-22T13:00:00.000Z", 9))
        ok("find: another title is not the meeting", m_find(d)["found"] is False)
        listing(("A", "Team Weekly Meeting", "2026-10-22T13:00:00.000Z", 9),
                ("B", "Team Weekly Meeting", "2026-10-22T13:20:00.000Z", 30))
        r = m_find(d)
        ok("find: two recordings take the longer, and say so", r["id"] == "B" and "warning" in r, r)
        json.dump({"result": json.dumps([{"id": "A", "title": "Team Weekly Meeting",
                                          "dateString": "2026-10-22T13:00:00.000Z"}])},
                  open(os.path.join(d, "listing.json"), "w"))
        ok("find: a wrapped result reads too", m_find(d).get("id") == "A")
        # SKB-118: under the runner, a listing at the printed save path that the runner never saved is
        # refused here, and one it saved reads
        import hashlib
        lp, cap = os.path.join(d, "listing.json"), os.path.join(tmp, "capture-find")
        os.makedirs(cap)
        L.register_calls({"calls": [{"tool": "mcp__fireflies__fireflies_get_transcripts", "args": {}, "save": lp}]}, cap)
        os.environ[L.CAPTURE_ENV] = cap
        try:
            try:
                m_find(d)
                ok("find: a listing the runner never saved is refused", False)
            except L.Refuse as e:
                ok("find: a listing the runner never saved is refused", e.code == 3 and "never saved" in str(e), str(e))
            rec = L.saved_record(cap, lp)
            os.makedirs(os.path.dirname(rec))
            with open(rec, "w", encoding="utf-8") as f:
                json.dump({"path": lp, "sha256": hashlib.sha256(open(lp, "rb").read()).hexdigest(), "tool": "x"}, f)
            ok("find: a listing the runner saved reads", m_find(d).get("id") == "A")
        finally:
            os.environ.pop(L.CAPTURE_ENV, None)

        rows = [["#", "主類別", "子類別", "項目（正規化）"], ["1.0", "1.0 Marketing", "", ""],
                ["1.08", "1.0 Marketing", "1.3 名單", "電子報"], ["2.01", "2.0 Sales", "2.1", "業務流程"],
                ["1.04", "1.0 Marketing", "1.1", "短影音"]]

        def save_pages(rows):
            for i, (a, b, rng) in enumerate(run["pages"]):
                part = rows[a - 1:b]
                body = "\n".join("Row %2d: %r" % (j + 1, c) for j, c in enumerate(part))
                text = ("Successfully read %d rows from range '%s' in spreadsheet TRK for ops@example.com:\n%s"
                        % (len(part), rng, body)) if part else "No data found in range '%s'." % rng
                open(os.path.join(d, "t%d.txt" % (i + 1)), "w").write(json.dumps({"result": text}))
        run = L.load_run(d)
        save_pages(rows)
        items = tracker_index(run)
        ok("tracker: items by #, category rows left out", items == {"1.08": "電子報", "2.01": "業務流程", "1.04": "短影音"}, items)
        open(os.path.join(d, "t2.txt"), "w").write("Successfully read 1 rows from range 'Other!A51:D72' in spreadsheet TRK for x:\nRow  1: ['9.01', '', '', 'x']")
        refuses("tracker: a read of another range is refused", tracker_index, run)
        save_pages([["#", "主類", "子類別", "項目"]] + rows[1:])
        refuses("tracker: a changed header is refused", tracker_index, run)
        save_pages(rows)

        now = L.parse_now("2026-10-23T08:20:00+08:00")
        base = {"source": "fireflies",
                "decisions": [{"text": "電子報 11/3 起跑 sweep", "item": "1.08"}],
                "actions": [{"what": "寄送 Skills 連結", "owner": "Ann Lee", "due": "2026-10-24"},
                            {"what": "安裝 Skillsync", "owner": "All", "due": ""},
                            {"what": "製作銷售講座素材", "owner": ["Ann Lee", "Ben Wu"], "due": "2026-10-30", "item": "2.01"},
                            {"what": "建立回報管道", "owner": "", "due": "2026-10-30", "new": True}],
                "blockers": [{"text": "名單匯入卡在 Kit 方案", "owner": "Ben Wu", "since": "2026-10-08"},
                             {"text": "時區設定抓 local", "since": "2026-10-20"}],
                "topics": [{"text": "相容性檢查技能", "owner": "Ann Lee"}],
                "dropped": [{"item": "1.04", "text": "短影音不做了"}],
                "progress": [{"item": "1.08", "text": "冷名單重新確認信已寄", "state": "進行中"}]}
        res = check(base, run, items, now)
        R = res["rows"]
        ok("rows: nine columns each", all(len(r) == len(L.DECISIONS_HEADER) == 9 for r in R))
        ok("rows: kinds in order", [r[2] for r in R] == ["決議", "放棄", "行動", "行動", "行動", "行動", "風險", "卡關", "待討論", "進度"],
           [r[2] for r in R])
        ok("rows: a dated owned action is scheduled", R[2][4:9] == ["Ann Lee", "2026-10-24", "", "Fireflies A", "已排定"], R[2])
        ok("rows: an undated action stays open", R[3][8] == "待定" and R[3][4] == "All", R[3])
        ok("rows: joint owners", R[4][4] == "Ann Lee、Ben Wu" and R[4][6] == "2.01", R[4])
        ok("rows: an ownerless action stays open, new item", R[5][8] == "待定" and R[5][6] == "新", R[5])
        ok("rows: a blocker 14 days old is a risk", R[6][2] == "風險" and R[6][3].endswith("（自 10/8）"), R[6])
        ok("rows: a blocker 2 days old is not", R[7][2] == "卡關")
        ok("rows: progress carries its state", R[9][6:9] == ["1.08", "Fireflies A", "進行中"], R[9])
        ok("rows: week and meeting", R[0][:2] == ["2026-W43", "2026-10-22"])
        b = res["block"]
        ok("block: stamp names the week and its title", b["stamp_line"] == "〔自動彙整 WB 10/19 · 10-23 08:20〕會議紀錄", b["stamp_line"])
        ok("block: under the meeting's heading", b["heading"] == "Oct 22, 2026")
        ok("block: labels in order", [l for l in b["body"].split("\n") if not l.startswith("\t")] == ["決議", "待辦", "卡關", "待討論", "放棄"])
        ok("block: an undated action says so", "\t安裝 Skillsync — All · 日期未定" in b["body"].split("\n"), b["body"])
        ok("block: a risk says how long", "已卡 14 天，列為風險" in b["body"])
        ok("block: a dropped item names it", "\t#1.04 短影音 — 短影音不做了" in b["body"].split("\n"))
        ok("block: progress stays out of the Doc", "冷名單" not in b["body"])
        F = res["fill"]
        ok("fill: All reaches everyone", "安裝 Skillsync〔10/22 會議〕" in F["Ann Lee"]["下一步"]
           and "安裝 Skillsync〔10/22 會議〕" in F["Ben Wu"]["下一步"], F)
        ok("fill: a dated action says by when", "寄送 Skills 連結（10/24 前）〔10/22 會議〕" in F["Ann Lee"]["下一步"], F["Ann Lee"])
        ok("fill: joint owners each get it", sum("銷售講座" in x for x in F["Ben Wu"]["下一步"]) == 1)
        ok("fill: blockers and topics are 待討論", F["Ben Wu"]["待討論"] == ["名單匯入卡在 Kit 方案〔10/22 會議〕"]
           and F["Ann Lee"]["待討論"] == ["相容性檢查技能〔10/22 會議〕"], F)
        S = res["summary"]
        ok("summary: unrouted lines named", S["unrouted"] == ["建立回報管道（10/30 前）", "時區設定抓 local"], S["unrouted"])
        ok("summary: open actions", len(S["open_actions"]) == 2, S["open_actions"])
        ok("summary: delivered", S["delivered"] == "6-decided;transcript-found", S["delivered"])
        ok("summary: the idempotency key", S["doc_key"] == {"starts": "〔自動彙整 WB 10/19 · ", "ends": "〕會議紀錄"})

        def variant(**kw):
            v = json.loads(json.dumps(base))
            for k, val in kw.items():
                v[k] = val
            return v
        refuses("owner off the roster", check, variant(actions=[{"what": "x", "owner": "Peter", "due": ""}]), run, items, now)
        refuses("a users/ key is no roster name", check, variant(actions=[{"what": "x", "owner": "users/123"}]), run, items, now)
        refuses("an unknown item", check, variant(decisions=[{"text": "x", "item": "9.99"}]), run, items, now)
        refuses("an unknown item on an action", check, variant(actions=[{"what": "x", "item": "9.99"}]), run, items, now)
        refuses("new with a number", check, variant(actions=[{"what": "x", "item": "1.08", "new": True}]), run, items, now)
        refuses("a partial date", check, variant(actions=[{"what": "x", "due": "10/30"}]), run, items, now)
        refuses("a compact date", check, variant(actions=[{"what": "x", "due": "20261030"}]), run, items, now)
        refuses("no such date", check, variant(actions=[{"what": "x", "due": "2026-02-30"}]), run, items, now)
        refuses("a blocker from the future", check, variant(blockers=[{"text": "x", "since": "2026-10-23"}]), run, items, now)
        refuses("dropped without an item", check, variant(dropped=[{"text": "x"}]), run, items, now)
        refuses("progress with a made-up state", check, variant(progress=[{"item": "1.08", "text": "x", "state": "done"}]), run, items, now)
        refuses("an action without words", check, variant(actions=[{"what": " ", "owner": "Ann Lee"}]), run, items, now)
        refuses("a line too long", check, variant(topics=[{"text": "長" * 201}]), run, items, now)
        refuses("a source find did not choose", check, variant(source="doc"), run, items, now)
        refuses("too many rows", check, variant(topics=[{"text": "t%d" % i} for i in range(BLOCK_ROWS)]), run, items, now)
        res = check(variant(progress=[{"item": "1.08", "text": "p%d" % i} for i in range(BLOCK_ROWS)]), run, items, now)
        ok("progress past the block is left out, and said", len(res["rows"]) == BLOCK_ROWS and res["summary"]["warnings"], res["summary"])
        res = check({"source": "fireflies"}, run, items, now)
        ok("no decisions: one line and the receipt word", res["block"]["body"] == "決議\n\t這次會議沒有談定的事"
           and res["summary"]["delivered"] == "no-decisions;transcript-found", res["block"])
        res = check(variant(actions=[{"what": "x", "owner": "Ann Lee", "due": "2026-10-20"}]), run, items, now)
        ok("a due date before the meeting is warned", any("before the meeting" in w for w in res["summary"]["warnings"]))

        listing(("A", "Other", "2026-10-22T13:00:00.000Z", 9))
        ok("doc fallback: find says so", m_find(d)["found"] is False)
        run = L.load_run(d)
        res = check({"source": "doc", "decisions": [{"text": "x"}]}, run, items, now)
        ok("doc fallback: rows cite the Doc", res["rows"][0][7] == "Doc Oct 22, 2026" and res["summary"]["delivered"] == "1-decided;doc-fallback",
           res["rows"][0])
        json.dump({"source": "doc", "topics": [{"text": "x", "owner": "Ben Wu"}]}, open(os.path.join(d, "in.json"), "w"))
        out = m_check(d, os.path.join(d, "in.json"), "2026-10-23T08:30:00+08:00")
        ok("check writes its four files", all(os.path.exists(p) for p in out["files"].values()) and len(out["files"]) == 4)
        ok("block.json is render_block's shape", json.load(open(out["files"]["block"]))["blocks"][0]["heading"] == "Oct 22, 2026")
        ok("without items no bullet closes", json.load(open(out["files"]["closures"]))["items"] == []
           and out["closed"]["open_read"] is False, out["closed"])

        # ── SKB-151: the meeting closes Doc bullets ──
        old_state = os.environ.get("ZYNKR_OPS_WEEKLY_STATE")
        os.environ["ZYNKR_OPS_WEEKLY_STATE"] = os.path.join(tmp, "state")
        os.makedirs(os.path.join(tmp, "state"), exist_ok=True)
        listing(("A", "Team Weekly Meeting", "2026-10-22T13:00:00.000Z", 33.4))
        m_find(d)
        run = L.load_run(d)

        def bullet(i, label):
            return {"id": "b%d" % i, "heading": "#Sales Ann Lee", "text": "%s〔WB 10/5 起〕" % label, "label": label,
                    "person": "Ann Lee"}
        opened = {"section": "Oct 22, 2026", "items": [bullet(1, "甲件事"), bullet(2, "乙件事"), bullet(3, "丙件事"),
                                                       bullet(4, "丁件事")]}
        cands = [dict(bullet(2, "乙件事"), harvest="乙 已上線"), dict(bullet(3, "丙件事"), harvest="丙 shipped"),
                 dict(bullet(9, "舊的寫法"), harvest="x")]
        json.dump({"week": "2026-W43", "section": "Oct 22, 2026", "candidates": cands},
                  open(closing_path("2026-W43"), "w"))
        op = os.path.join(tmp, "open.json")
        json.dump(opened, open(op, "w"))
        r = m_items(d, op)
        ok("items: the open bullets and the candidates, each candidate said open or not",
           len(r["open"]) == 4 and [c["still_open"] for c in r["candidates"]] == [True, True, False], r)
        json.dump(dict(opened, section="Oct 15, 2026"), open(op, "w"))
        refuses("items: another week's section", m_items, d, op)

        said = {"source": "fireflies", "closed": [{"bullet": "b1", "how": "drop", "quote": "甲不做了"}],
                "kept": [{"bullet": "b3", "quote": "丙還沒，下週"}]}
        res = check(said, run, items, now, opened, cands)
        got = [(c["id"], c["why"], c["how"]) for c in res["closures"]["items"]]
        ok("closed by the meeting, and the unopposed candidate; the objected one and the bullet nobody named stay",
           got == [("b1", "meeting", "drop"), ("b2", "harvest", "done")], got)
        ok("a candidate edited since Wednesday is reported, not closed",
           [x["id"] for x in res["summary"]["closed"]["left"]] == ["b9"], res["summary"]["closed"])
        ok("the 會議紀錄 block says what closed and why",
           "收掉\n\t甲件事 — Ann Lee · 會上說放棄\n\t乙件事 — Ann Lee · 收成已完成（乙 已上線），會上無異議" in res["block"]["body"],
           res["block"]["body"])
        ok("closures name the meeting's section, with heading and text for tidy",
           res["closures"]["section"] == "Oct 22, 2026" and res["closures"]["items"][0]["heading"] == "#Sales Ann Lee")
        ok("the receipt counts them", res["summary"]["delivered"].endswith(";2-closed"), res["summary"]["delivered"])
        ok("no closure row reaches the Ledger", all(r[2] != "收掉" for r in res["rows"]))
        refuses("closed: an id items did not list", check, dict(said, closed=[{"bullet": "b7", "quote": "x"}]), run, items, now, opened, cands)
        refuses("closed: no words", check, dict(said, closed=[{"bullet": "b1", "quote": " "}]), run, items, now, opened, cands)
        refuses("closed: how is done or drop", check, dict(said, closed=[{"bullet": "b1", "how": "maybe", "quote": "x"}]),
                run, items, now, opened, cands)
        refuses("closed twice", check, dict(said, closed=[{"bullet": "b1", "quote": "x"}, {"bullet": "b1", "quote": "y"}]),
                run, items, now, opened, cands)
        refuses("kept: not a candidate", check, dict(said, kept=[{"bullet": "b4", "quote": "x"}]), run, items, now, opened, cands)
        refuses("both closed and kept", check, dict(said, kept=[{"bullet": "b1", "quote": "x"}],
                                                     closed=[{"bullet": "b1", "quote": "y"}]), run, items, now, opened,
                [dict(bullet(1, "甲件事"))])
        refuses("closed without the open bullets read", check, said, run, items, now)
        doc_run = dict(run, source="doc")
        refuses("closed from the Doc", check, dict(said, source="doc"), doc_run, items, now, opened, cands)
        res = check({"source": "doc"}, doc_run, items, now, opened, cands)
        ok("no transcript: no candidate closes, each is asked again",
           res["closures"]["items"] == [] and len(res["summary"]["closed"]["left"]) == 3, res["summary"]["closed"])
        kid = dict(bullet(5, "子項"), text="子項")
        parent = dict(bullet(2, "乙件事"), open_sub_items=["子項"])
        nested = dict(opened, items=[bullet(1, "甲件事"), parent, kid])
        res = check({"source": "fireflies"}, run, items, now, nested, [dict(parent, harvest="乙 已上線")])
        ok("a candidate with an open sub-item waits: tidy could not remove it",
           res["closures"]["items"] == [] and res["summary"]["closed"]["left"][0]["why"] == "an open sub-item: 子項",
           res["summary"]["closed"])
        refuses("closed: a bullet with an open sub-item", check,
                {"source": "fireflies", "closed": [{"bullet": "b2", "quote": "乙做完了"}]}, run, items, now, nested, [])
        res = check({"source": "fireflies", "closed": [{"bullet": "b2", "quote": "乙做完了"},
                                                       {"bullet": "b5", "quote": "子項也好了"}]}, run, items, now, nested, [])
        ok("... closed with its sub-item, both close", [c["id"] for c in res["closures"]["items"]] == ["b2", "b5"],
           res["closures"])
        twin = dict(opened, items=[bullet(1, "甲件事"), parent])        # 子項 not listed: written twice
        res = check({"source": "fireflies", "closed": [{"bullet": "b2", "quote": "乙做完了"}]}, run, items, now, twin, [])
        ok("said closed, its sub-item has no id: held back with the reason, not refused",
           res["closures"]["items"] == [] and "no id" in res["summary"]["closed"]["left"][0]["why"],
           res["summary"]["closed"])
        refuses("closed: an entry that is not an object", check, {"source": "fireflies", "closed": ["b1"]},
                run, items, now, opened, cands)
        refuses("kept: an entry that is not an object", check, {"source": "fireflies", "kept": ["b2"]},
                run, items, now, opened, cands)
        open(closing_path("2026-W43"), "w").write('{"section": "Oct 22')
        json.dump(opened, open(op, "w"))
        refuses("items: a half-written closing list", m_items, d, op)
        json.dump({"week": "2026-W43", "section": "Oct 22, 2026", "candidates": cands},
                  open(closing_path("2026-W43"), "w"))
        m_items(d, op)
        json.dump(said, open(os.path.join(d, "in.json"), "w"))
        out = m_check(d, os.path.join(d, "in.json"), "2026-10-23T08:30:00+08:00")
        ok("check reads what items kept and writes closures.json",
           [c["id"] for c in json.load(open(out["files"]["closures"]))["items"]] == ["b1", "b2"], out["closed"])
        if old_state is None:
            os.environ.pop("ZYNKR_OPS_WEEKLY_STATE", None)
        else:
            os.environ["ZYNKR_OPS_WEEKLY_STATE"] = old_state
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("minutes.py selftest: %d failed" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("minutes.py selftest: all checks passed")
    return 0


def mutate():
    import shutil
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")
    tmpd = tempfile.mkdtemp(prefix="minutes-mutate-")
    shutil.copy2(os.path.join(core_dir(), "ledger.py"), os.path.join(tmpd, "ledger.py"))

    def run(text):
        p = os.path.join(tmpd, "minutes_mut.py")
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


MUTATIONS = [
    ("the latest transcript, whatever its day", [("             and taipei_date(t.get(\"dateString\")) == thu]", "]")]),
    ("any title", [("str(t.get(\"title\") or \"\").strip() == title", "True")]),
    ("UTC date, not Taipei's", [("        return L.parse_now(s).date()", "        return datetime.fromisoformat(s.replace('Z', '+00:00')).date()")]),
    ("the first recording, not the longest", [("key=lambda t: -(t.get(\"duration\") or 0)", "key=lambda t: 0")]),
    ("roster check lost", [("    bad = [n for n in names if n not in roster]", "    bad = []")]),
    ("users/ keys on the roster", [("and not k.startswith(\"users/\")]", "]")]),
    ("item check lost", [("    if v not in items:\n", "    if False:\n")]),
    ("new items numbered anyway", [("        if v:\n            raise L.Refuse(3, \"%s is marked new", "        if False:\n            raise L.Refuse(3, \"%s is marked new")]),
    ("partial dates pass", [("    if not DATE_RE.match(v):", "    if False:")]),
    ("risk threshold off by one", [("kind = \"風險\" if age > RISK_DAYS else", "kind = \"風險\" if age >= RISK_DAYS - 5 else")]),
    ("undated actions scheduled", [("state = \"已排定\" if names and due else \"待定\"", "state = \"已排定\" if names else \"待定\"")]),
    ("All not expanded", [("targets = [n for n in roster if n != \"All\"] if \"All\" in names else names", "targets = names")]),
    ("the meeting date not cited", [("            fill[n][label].append(line + cite)", "            fill[n][label].append(line)")]),
    ("block overflow not refused", [("    if len(rows) > BLOCK_ROWS:", "    if False:")]),
    ("progress overflow kept", [("    rows += prog[:room]", "    rows += prog")]),
    ("progress written to the Doc", [("        prog.append([week, run[\"meeting\"], \"進度\", t, \"\", \"\", it, source, state])",
                                      "        prog.append([week, run[\"meeting\"], \"進度\", t, \"\", \"\", it, source, state]); doc[\"決議\"].append(t)")]),
    ("the block's title lost", [("    stamp_line = \"〔自動彙整 %s · %s〕%s\" % (wb_label(week), now.strftime(\"%m-%d %H:%M\"), TITLE)",
                                 "    stamp_line = \"〔自動彙整 %s · %s〕\" % (wb_label(week), now.strftime(\"%m-%d %H:%M\"))")]),
    ("reads past the grid", [("(L.quote_tab(run[\"tab\"]), a, min(a + L.PAGE - 1, grid)))", "(L.quote_tab(run[\"tab\"]), a, a + L.PAGE - 1))")]),
    ("source mismatch accepted", [("    if src != run.get(\"source\"):", "    if False:")]),
    ("no-decisions never said", [("(\"no-decisions;\" if not decided else", "(\"0-decided;\" if not decided else")]),
    ("future blockers accepted", [("        if since and since > thu:", "        if False:")]),
    ("the heading zero-padded", [("    return \"%s %d, %d\" % (d.strftime(\"%b\"), d.day, d.year)", "    return d.strftime(\"%b %d, %Y\")")]),
    ("an undated entry is today's", [("    if not s:\n        return None", "    if False:\n        return None")]),
    ("the listing read unchecked", [("    L.check_saved(p)\n    try:\n        listing = json.load", "    try:\n        listing = json.load")]),
    # SKB-151
    ("an objection does not keep a candidate", [("        if c[\"id\"] in said or c[\"id\"] in kept:", "        if c[\"id\"] in said:")]),
    ("an edited candidate closes anyway", [("        if c[\"id\"] not in by_id:\n            left.append",
                                             "        if False:\n            left.append")]),
    ("candidates close without a transcript", [("        elif data.get(\"source\") != \"fireflies\":\n            left.append",
                                                 "        elif False:\n            left.append")]),
    ("the Doc closes bullets", [("    if closed_in and data.get(\"source\") != \"fireflies\":", "    if False:")]),
    ("closed takes any id", [("        if bid not in by_id:\n            raise L.Refuse(3, \"%s: bullet %r is not an open bullet",
                               "        if False:\n            raise L.Refuse(3, \"%s: bullet %r is not an open bullet")]),
    ("kept takes any id", [("        if bid not in cand:", "        if False:")]),
    ("closures left out of the Doc block", [("    doc[\"收掉\"] = [closure_line(c) for c in closures]", "    pass")]),
    ("another week's open bullets accepted", [("    if opened.get(\"section\") != run[\"heading\"]:", "    if False:")]),
    ("a non-object entry reaches .get", [("        if not isinstance(x, dict):\n            raise L.Refuse(3, \"%s %d must be",
                                          "        if False:\n            raise L.Refuse(3, \"%s %d must be")]),
    ("a said close with an unlisted sub-item is refused", [("        if bad[\"why\"] == \"meeting\" and (_ns(bad[\"heading\"]), _ns(loose)) in listed:",
                                                             "        if bad[\"why\"] == \"meeting\":")]),
    ("an open sub-item does not hold its parent", [("        if bad is None:\n", "        if True:\n")]),
    ("a half-written closing list crashes", [("        except (OSError, ValueError) as e:\n            raise L.Refuse(3, \"cannot read %s (%s): re-run",
                                               "        except KeyError as e:\n            raise L.Refuse(3, \"cannot read %s (%s): re-run")]),
    ("closures.json not written", [("                      (\"closures.json\", res[\"closures\"])):", "):")]),
]

if __name__ == "__main__":
    sys.exit(main())
