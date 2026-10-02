#!/usr/bin/env python3
"""The Friday proposals (SKB-044 Phase 3): what `propose` suggests, the owner's sign-off by reply,
and what `apply` makes of it.

Like ledger.py, this script computes and never talks to Google. Each step prints the exact MCP
calls to make, with a path to save each result to word for word; the next step reads them back.

  propose (Fri 10:00)
    proposals.py start   --week W [--config PATH] [--now ISO]   -> run folder + the first reads
    proposals.py pages   --dir D        -> already proposed this week, or the tracker page reads
    proposals.py context --dir D        -> the items and this week's evidence, for the model
    proposals.py check   --dir D --input proposals.json [--now ISO]
                                        -> refuses anything outside the rules; writes rows.json
                                           (the Proposals block) and the approval mail
    proposals.py sent    --dir D        -> after the Ledger write: is the mail in Sent? Not yet ->
                                           send it, search again, run `sent` again. Found -> it must
                                           be exactly the mail `check` wrote; its thread is recorded.
    proposals.py sent    --dir D --send-failed
                                        -> the send returned an error: a later attempt may send

  The Ledger record always comes first and the mail second. A retry whose week already holds
  proposals but no recorded mail (`pages` says "resume") mails exactly those rows.

  apply (Fri 18:00 → Sun 23:00)
    proposals.py apply-start  --week W [--config PATH] [--now ISO]
    proposals.py apply-thread --dir D   -> when no thread was recorded: the search found it
    proposals.py apply-decide --dir D [--now ISO]
        status ok       -> nothing to decide, or only the Updates block left to write
        status waiting  -> no decision yet; at most one `send` (a restate request or a draft note)
        status failed   -> the approval mail is missing or is not the mail that was checked
        status recheck  -> write the Proposals block, make the `then` reads, run apply-decide again
        status confirm  -> send the confirmation in the thread, then write the Updates block
    proposals.py apply-sent --dir D     -> after a restate request or draft note went through

  The owner's newest reply decides until apply's confirmation is in the thread; after it, replies
  change nothing. apply writes the decision to the Proposals block, reads that block and the thread
  again, confirms, and only then writes the Updates block, which stamps Weeks Q: "applied" always
  means confirmed. A reply sent while apply writes replaces the one it was writing.

    proposals.py parse --text TEXT --count N      the reply grammar alone
    proposals.py --selftest | --mutate

Phase 3a builds `apply` in shadow mode only: it records each decision and writes nothing to the
Main Tracker. `routine.apply_mode: live` is refused, by `propose` and `apply` alike, until Phase 3b
ships the live write.

Exit codes as ledger.py: 0 ok · 2 config or arguments · 3 input refused · 4 structure changed ·
5 out of space · 6 check failed · 7 confirm failed.
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import date
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger as L  # noqa: E402  the Ledger's layout, reads and tracker parse live there

FIELDS = ("狀態", "結束", "備註")
VOCAB = ("未開始", "進行中", "暫停", "完成", "放棄")
TERMINAL = ("完成", "放棄")
CONFIDENCE = ("高", "中", "低")
MAX_ROWS = L.BLOCKS["Proposals"][0]
MAX_REFS = 3
# The approval mail as the Gmail tools hand it back (its text/plain part). Every reply quotes it,
# and the thread apply reads has to fit one tool result, so the mail stays small.
MAIL_TEXT_MAX = 6000
MARKER = "〔zynkr-ops-weekly〕"
CONFIRM_HEAD = MARKER + " 已記下"
RESTATE_HEAD = MARKER + " 這封回覆我讀不懂"
MAX_LOOKS = 3                  # apply's reads of the thread in one run: the decision, and two re-reads
DRAFT_NOTE_AFTER = 7200        # a draft still open after two hours gets one note in the thread
RESEND_AFTER = 2400            # a send no later attempt can find in Sent for 40 minutes may go again;
                               # propose's attempts come 30 minutes apart, so the third one may resend
# What this file has always refused, plus what zynkr-gm's derive_state.py reads as done
# (完成|shipped|done|上線|已上線): a 備註 holding any of them makes the recap flag the item as done.
DONE_WORDS = re.compile(r"完成|做完|結案|上線|shipped|done", re.I)
NOTE_LINE = re.compile(r"^(\d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2}) \S")
GRAMMAR = "「全部核准」、「核准 1 3」、「退回 2」或「全部核准 退回 2」"
LIVE_REFUSED = ("routine.apply_mode is live, but the live write is Phase 3b and not built; "
                "set it back to shadow")


# ── small helpers ─────────────────────────────────────────────────────────────
def wb_label(week):
    m = L.monday(week)
    return "WB %d/%d" % (m.month, m.day)


def subject_for(week, n):
    return "【待核准】%s 那週 · %d 件（%s）" % (wb_label(week), n, week)


def raw_config(path):
    path = os.path.expanduser(path or os.environ.get("ZYNKR_OPS_WEEKLY_CONFIG") or "~/.config/zynkr/ops-weekly.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise L.Refuse(2, "config unreadable: %s (%s)" % (path, e))


def apply_mode(raw):
    """`live` only when the owner wrote exactly that; anything else is shadow (writes nothing)."""
    return "live" if raw.get("routine", {}).get("apply_mode") == "live" else "shadow"


def new_run(cfg, week, kind, now, base):
    now = L.parse_now(now)
    d = os.path.join(base or os.path.join(L.state_dir(), "runs"), "%s-%s-%s" % (week, kind, now.strftime("%Y%m%dT%H%M%S")))
    n = 1
    while os.path.exists(d + ("" if n == 1 else "-%d" % n)):
        n += 1
    d = d + ("" if n == 1 else "-%d" % n)
    os.makedirs(d)
    k = L.week_index(week, cfg["epoch"])
    return dict(cfg, dir=d, week=week, k=k, weeks_row=L.weeks_row(k))


def block_range(tab, k):
    first, last = L.block_slot(tab, k)
    return first, last, "%s!A%d:%s%d" % (tab, first, L.COLS[tab], last)


def read_block(run, tab, name):
    first, last, rng = block_range(tab, run["k"])
    rows = L.parse_values(L.load_result(os.path.join(run["dir"], name + ".txt")), run["ledger"], rng)
    width = len(L.BLOCKS[tab][1])
    out = []
    for i, r in enumerate(rows):
        r = L.pad(r, width)
        if any(c.strip() for c in r):
            if r[0] != run["week"]:
                raise L.Refuse(3, "%s row %d belongs to %r, not %s" % (tab, first + i, r[0], run["week"]))
            out.append((first + i, r))
    return out


def weeks_cells(run, name="wr"):
    r = run["weeks_row"]
    wr = L.parse_values(L.load_result(os.path.join(run["dir"], name + ".txt")), run["ledger"], "Weeks!A%d:R%d" % (r, r))
    row = L.pad(wr[0], 18) if wr else [""] * 18
    if row[0] not in ("", run["week"]):
        raise L.Refuse(4, "Weeks row %d belongs to %s, not %s" % (r, row[0], run["week"]))
    return dict(zip(L.WEEKS_FULL, row))


def num_key(num):
    """Item numbers sort by their parts, numbers before text, so 1.9 < 1.10 and nothing compares int to str."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in num.split(".")]


def write_rows(path, rows):
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return path


def clip(s, n):
    return s if len(s) <= n else s[:n - 1] + "…"


def state_file(week, what):
    return os.path.join(L.state_dir(), "%s.%s" % (week, what))


def write_state(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rows_sha(rows):
    """The proposal cells (A–L) of a week's rows: what the owner was asked about, decisions aside."""
    return sha(json.dumps([list(r[:12]) for r in rows], ensure_ascii=False))


def read_list(path):
    try:
        got = json.load(open(path, encoding="utf-8"))
        return got if isinstance(got, list) else []
    except (OSError, ValueError):
        return []


class _Flat(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.out = []

    def handle_data(self, data):
        self.out.append(data)


def flat_text(markup):
    """The mail as the Gmail tools return it. Sending HTML adds a text/plain part made by joining the
    HTML's text with no separators and collapsing whitespace, and a thread read prefers that part."""
    p = _Flat()
    p.feed(markup)
    p.close()
    return " ".join("".join(p.out).split())


# ── propose ──────────────────────────────────────────────────────────────────
def p_start(week, config=None, now=None, base=None):
    cfg = L.load_config(config)
    mode = apply_mode(raw_config(config))
    if mode == "live":
        raise L.Refuse(2, LIVE_REFUSED)
    run = new_run(cfg, week, "propose", now, base)
    run["mode"] = mode
    L.save_run(run)
    r = run["weeks_row"]
    calls = [L.info_call(run, cfg["tracker"], "ti"), L.info_call(run, cfg["ledger"], "li"),
             L.read_call(run, cfg["ledger"], "Weeks!A%d:R%d" % (r, r), "wr"),
             L.read_call(run, cfg["ledger"], block_range("Decisions", run["k"])[2], "dc"),
             L.read_call(run, cfg["ledger"], block_range("Reports", run["k"])[2], "rp"),
             L.read_call(run, cfg["ledger"], block_range("Proposals", run["k"])[2], "pp")]
    return {"dir": run["dir"], "week": week, "mode": run["mode"], "calls": calls}


def p_pages(d):
    run = L.load_run(d)
    ti = L.parse_info(L.load_result(os.path.join(d, "ti.txt")), run["tracker"])
    li = L.parse_info(L.load_result(os.path.join(d, "li.txt")), run["ledger"])
    if run["tab"] not in ti:
        raise L.Refuse(4, "the tracker has no tab %r" % run["tab"])
    if "Proposals" not in li:
        raise L.Refuse(4, "the Ledger has no Proposals tab; run the Phase 3 setup")
    for name in li:
        if name in ti and name in ("Weeks", "Proposals", "Updates"):
            raise L.Refuse(4, "the tracker also has a tab named %s; a misdirected write could land there" % name)
    w = weeks_cells(run)
    if w["proposals"] == "ok":
        rows = [c for _, c in read_block(run, "Proposals", "pp")]
        if not rows or os.path.exists(thread_state_path(run["week"])):
            return {"already": True, "week": run["week"], "delivered": "already-proposed;Weeks!O%d" % run["weeks_row"]}
        # recorded, but the mail never went out (or was never recorded): mail exactly those rows
        run["evidence"] = {x["ref"]: x for x in evidence_rows(run)}
        out = write_mail(run, rows)
        return dict(out, already=False, resume=True)
    warnings = []
    if w["decisions"] != "ok":
        warnings.append("this week's decisions were not recorded in the Ledger: propose from the reports alone")
    if w["reports"] != "ok":
        warnings.append("this week's #週報 posts were not recorded in the Ledger")
    grid_rows, grid_cols = ti[run["tab"]]
    if grid_cols < 13:
        raise L.Refuse(4, "tracker tab is only %d columns wide" % grid_cols)
    pages = L.tracker_pages(run["tab"], grid_rows)
    run.update(grid=[grid_rows, grid_cols], pages=pages, warnings=warnings)
    L.save_run(run)
    calls = [L.read_call(run, run["tracker"], rng, "t%d" % (i + 1)) for i, (_, _, rng) in enumerate(pages)]
    return {"already": False, "week": run["week"], "calls": calls, "warnings": warnings}


def evidence_rows(run):
    return ([{"ref": "Decisions!A%d" % r, "類型": c[2], "內容": c[3], "負責人": c[4], "期限": c[5], "關聯 #": c[6]}
             for r, c in read_block(run, "Decisions", "dc")]
            + [{"ref": "Reports!A%d" % r, "owner": c[2], "部門": c[3], "上週": c[4], "本週": c[5], "卡關": c[7]}
               for r, c in read_block(run, "Reports", "rp")])


def item_dict(cells):
    return dict(zip(L.TRACKER_HEADER, [c.strip() for c in cells]))


def p_context(d):
    run = L.load_run(d)
    if "pages" not in run:
        raise L.Refuse(2, "run `pages` first")
    items, warnings = L.tracker_items(L.read_tracker(run, "t"))
    by_num, dup = {}, set()
    for cells in items:
        it = item_dict(cells)
        if it["#"] in by_num:
            dup.add(it["#"])
        by_num[it["#"]] = it
    ev = evidence_rows(run)
    decisions = [e for e in ev if e["ref"].startswith("Decisions!")]
    reports = [e for e in ev if e["ref"].startswith("Reports!")]
    ctx = {"week": run["week"], "mode": run["mode"],
           "items": [{k: by_num[n][k] for k in ("#", "項目（正規化）", "Priority", "負責人", "開始", "結束", "狀態", "備註")}
                     for n in by_num],
           "decisions": decisions, "reports": reports, "ambiguous_items": sorted(dup),
           "warnings": run.get("warnings", []) + warnings}
    json.dump(ctx, open(os.path.join(d, "context.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    run.update(items=by_num, ambiguous=sorted(dup), evidence={x["ref"]: x for x in decisions + reports},
               digest=L.digest(items))
    L.save_run(run)
    return ctx


def date_norm(v):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", (v or "").strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def check_one(p, i, run):
    """One proposal against the rules; returns the cells of its row (n is filled in later)."""
    where = "proposal %d" % (i + 1)
    if not isinstance(p, dict):
        raise L.Refuse(3, "%s is not an object" % where)
    num, field = str(p.get("#") or "").strip(), str(p.get("欄位") or "").strip()
    new, why = str(p.get("建議值") if p.get("建議值") is not None else "").strip(), str(p.get("原因") or "").strip()
    conf, refs = str(p.get("信心") or "").strip(), p.get("證據")
    items, evidence = run["items"], run["evidence"]
    if num not in items:
        raise L.Refuse(3, "%s: no item #%s in the tracker" % (where, num))
    if num in run["ambiguous"]:
        raise L.Refuse(3, "%s: #%s appears twice in the tracker; it cannot be changed by number" % (where, num))
    it = items[num]
    if it["狀態"] in TERMINAL:
        raise L.Refuse(3, "%s: #%s is %s; a closed item is not proposed on" % (where, num, it["狀態"]))
    if field not in FIELDS:
        raise L.Refuse(3, "%s: field %r is not one of %s" % (where, field, "/".join(FIELDS)))
    if conf not in CONFIDENCE:
        raise L.Refuse(3, "%s: confidence %r is not 高/中/低" % (where, conf))
    if not why or len(why) > 160 or "\n" in why or "\r" in why:
        raise L.Refuse(3, "%s: the reason must be one line of at most 160 characters" % where)
    if not isinstance(refs, list) or not refs:
        raise L.Refuse(3, "%s: every proposal names its evidence rows" % where)
    if len(refs) > MAX_REFS:
        raise L.Refuse(3, "%s: at most %d evidence rows per proposal" % (where, MAX_REFS))
    rows = []
    for ref in refs:
        if not isinstance(ref, str) or ref not in evidence:
            raise L.Refuse(3, "%s: evidence %r is not one of this week's Decisions or Reports rows" % (where, ref))
        rows.append(evidence[ref])
    meeting = [e for e in rows if e["ref"].startswith("Decisions!")]
    for e in meeting:
        # a 待決 row is not a resolution, and a decision about another item is no evidence about this one
        if e["類型"] != "決議":
            raise L.Refuse(3, "%s: %s is %s, not a resolution" % (where, e["ref"], e["類型"] or "untyped"))
        if e["關聯 #"] != num:
            raise L.Refuse(3, "%s: %s is about #%s, not #%s" % (where, e["ref"], e["關聯 #"] or "?", num))
    if not meeting and conf != "低":
        raise L.Refuse(3, "%s: a change argued from a self-report alone is 低" % where)
    cur = it[field]
    if field == "狀態":
        if new not in VOCAB:
            raise L.Refuse(3, "%s: %r is not a 狀態 value (%s)" % (where, new, " / ".join(VOCAB)))
        if new == "完成" and not meeting:
            raise L.Refuse(3, "%s: 完成 needs a meeting record of the delivery, not a self-report" % where)
    elif field == "結束":
        if not date_norm(new):
            raise L.Refuse(3, "%s: 結束 must be a real YYYY-MM-DD date, got %r" % (where, new))
        if not any(L.norm_date(e["期限"]) == date_norm(new) for e in meeting):
            raise L.Refuse(3, "%s: a new 結束 needs a decision for #%s with that full date as its 期限" % (where, num))
    else:
        if not meeting:
            raise L.Refuse(3, "%s: 備註 lines cite a decision" % where)
        if cur:
            if not new.startswith(cur + "\n"):
                raise L.Refuse(3, "%s: 備註 only gains a line; the current text must stay exactly as it is" % where)
            added = new[len(cur) + 1:]
        else:
            added = new
        if not added or "\n" in added or added != added.strip() or not NOTE_LINE.match(added):
            raise L.Refuse(3, "%s: 備註 gains exactly one line starting with its date (M/D or YYYY-MM-DD)" % where)
        if DONE_WORDS.search(added):
            raise L.Refuse(3, "%s: done-words in 備註 make the state rules read the item as done — propose 狀態 instead" % where)
    if (L.norm_date(new) or new) == (L.norm_date(cur) or cur):
        raise L.Refuse(3, "%s: #%s %s is already %r" % (where, num, field, cur))
    source = "會議" if meeting else "自述"
    return [num, it["項目（正規化）"], field, cur, new, why, "、".join(refs), source, conf]


def evidence_text(e, ref):
    if e is None:
        return ref                              # the row changed since it was cited; the reference stands
    if e["ref"].startswith("Decisions!"):
        t = "會議%s：%s" % (e.get("類型") or "決議", e.get("內容") or "")
        if e.get("期限"):
            t += "（%s，%s）" % (e.get("負責人") or "沒有負責人", e["期限"])
    else:
        t = "%s 的週報：%s" % (e.get("owner") or "?", (e.get("本週") or e.get("上週") or "").replace("\n", " · "))
    return clip(t, 80)


def note_line(cur, new):
    """What a 備註 proposal adds: its one new line."""
    return new[len(cur) + 1:] if cur else new


def render_mail(run, rows):
    esc = html.escape
    o = ["<p>這週的總表變更提案，共 %d 件。直接回覆這封信就好：%s。</p>" % (len(rows), esc(GRAMMAR)),
         "<p>回覆只寫核准、退回和編號，後面加句謝謝沒關係；要排除幾件就寫「核准 1 3」，不要寫「除了 2 都核准」。"
         "核准的回覆裡有問句或其他的話，我會請你重寫。記下後我會在這封信下面回信確認；確認前可以再回一封完整的"
         "取代前一封，確認後就不再改。週日晚上 10 點前回覆都來得及；沒寫到的編號不會套用，週一的週報會列出來。</p>"]
    if run["mode"] == "shadow":
        o.append("<p><b>試行中</b>：這幾週核准的不會寫進總表，只記錄下來，週一的週報會列出「如果套用會改什麼」。</p>")
    o.append("<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse:collapse\">"
             "<tr><th>編號</th><th>項目</th><th>欄位</th><th>現在 → 建議</th><th>為什麼</th><th>證據</th><th>把握</th></tr>")
    for r in rows:
        n, num, name, field, cur, new, why, refs, conf = r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[11]
        if field == "備註":
            change = "加一行：%s" % esc(note_line(cur, new))
        else:
            change = "%s → %s" % (esc(cur or "（空白）"), esc(new))
        ev = "<br>".join(esc(evidence_text(run["evidence"].get(x), x)) for x in refs.split("、"))
        o.append("<tr><td>%s</td><td>#%s %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                 % (esc(n), esc(num), esc(clip(name, 30)), esc(field), change, esc(why), ev, esc(conf)))
    o.append("</table>")
    o.append("<p style=\"color:#777\">%s 待核准 %s · 提案是機器依本週的會議決議和週報整理的，"
             "寫進總表前一定會先等你回覆。</p>" % (esc(MARKER), esc(run["week"])))
    return "\n".join(o)


def p_check(d, input_path, now=None):
    run = L.load_run(d)
    if "items" not in run:
        raise L.Refuse(2, "run `context` first")
    try:
        props = json.load(open(input_path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise L.Refuse(3, "cannot read proposals from %s (%s)" % (input_path, e))
    if not isinstance(props, list):
        raise L.Refuse(3, "proposals must be a JSON list")
    if len(props) > MAX_ROWS:
        raise L.Refuse(5, "%d proposals do not fit the %d-row Proposals block" % (len(props), MAX_ROWS))
    cells, seen = [], set()
    for i, p in enumerate(props):
        c = check_one(p, i, run)
        if (c[0], c[2]) in seen:
            raise L.Refuse(3, "two proposals change #%s %s" % (c[0], c[2]))
        seen.add((c[0], c[2]))
        cells.append(c)
    cells.sort(key=lambda c: (num_key(c[0]), FIELDS.index(c[2])))
    at = L.stamp(L.parse_now(now))
    rows = [[run["week"], at, str(i + 1)] + c + ["", "", ""] for i, c in enumerate(cells)]
    out = {"week": run["week"], "rows": len(rows), "mode": run["mode"]}
    if rows:
        out.update(write_mail(run, rows))       # refuses a mail too long to read back, before anything is saved
    else:
        run.update(checked=True, rows=0, subject=None)
        L.save_run(run)
    out["rows_path"] = write_rows(os.path.join(d, "rows.json"), rows)
    return out


def write_mail(run, rows):
    """The approval mail for these rows, and the Sent search that guards and confirms its send."""
    d = run["dir"]
    markup = render_mail(run, rows)
    flat = flat_text(markup)
    if len(flat) > MAIL_TEXT_MAX:
        raise L.Refuse(5, "the approval mail would be %d characters, over %d: every reply quotes it and the "
                          "thread apply reads must fit one tool result — propose fewer rows" % (len(flat), MAIL_TEXT_MAX))
    body = os.path.join(d, "mail.html")
    open(body, "w", encoding="utf-8").write(markup)
    mail = {"to": run["account"], "subject": subject_for(run["week"], len(rows)), "body_path": body,
            "body_format": "html", "include_signature": False}
    json.dump(mail, open(os.path.join(d, "mail.json"), "w", encoding="utf-8"), ensure_ascii=False)
    query = 'in:sent subject:待核准 "%s" newer_than:1d' % run["week"]
    run.update(checked=True, rows=len(rows), subject=mail["subject"], row_keys=[[r[2], r[3]] for r in rows],
               mail_flat=flat, rows_sha=rows_sha(rows), sent_query=query, send_instructed=False)
    L.save_run(run)
    return {"week": run["week"], "rows": len(rows), "mail": mail,
            "sent_search": L.call("search_gmail_messages", {"user_google_email": run["account"], "page_size": 5,
                                                            "query": query}, os.path.join(d, "sent-search.txt"))}


# ── reading Gmail results ────────────────────────────────────────────────────
THREAD_HEAD = re.compile(r"^Thread ID: (\S+)\nSubject: (.*)\nMessages: (\d+)\n", re.M)
MSG_SPLIT = re.compile(r"^=== Message (\d+) ===$", re.M)
SEARCH_THREAD = re.compile(r"Thread ID: ([0-9a-f]+)")
SEARCH_FOUND = re.compile(r"^Found (\d+) messages matching '(.*)':$")


def thread_ids(search_text):
    seen = []
    for t in SEARCH_THREAD.findall(search_text):
        if t not in seen:
            seen.append(t)
    return seen


def search_ids(text, query):
    """Thread ids from a search_gmail_messages result for exactly `query`. Anything else — an error,
    a truncated save, a result for another query — is refused, never read as "not found"."""
    first = text.split("\n", 1)[0].strip()
    if first == "No messages found for query: '%s'" % query:
        return []
    m = SEARCH_FOUND.match(first)
    if not m or m.group(2) != query:
        raise L.Refuse(3, "not a search_gmail_messages result for %r: %r" % (query, first[:120]))
    ids = thread_ids(text)
    if int(m.group(1)) and not ids:
        raise L.Refuse(3, "the search found %s messages but no thread ids were saved" % m.group(1))
    return ids


def load_thread(path):
    """A saved get_gmail_thread_content result -> (thread text, analysis or None). With
    include_analysis the tool answers {"content", "analysis"}; the analysis counts drafts."""
    if not os.path.exists(path):
        raise L.Refuse(3, "missing saved result: %s" % path)
    raw = open(path, encoding="utf-8").read().strip()
    obj = None
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except ValueError:
            obj = None
    for _ in range(3):
        if isinstance(obj, dict) and isinstance(obj.get("content"), str):
            return obj["content"], obj.get("analysis") if isinstance(obj.get("analysis"), dict) else None
        if isinstance(obj, dict) and "result" in obj:
            obj = obj["result"]
            if isinstance(obj, str) and obj.lstrip().startswith("{"):
                try:
                    obj = json.loads(obj)
                except ValueError:
                    return obj, None
            continue
        break
    if isinstance(obj, str):
        return obj, None
    return L.load_result(path), None


def parse_thread(text):
    m = THREAD_HEAD.match(text)
    if not m:
        raise L.Refuse(3, "not a get_gmail_thread_content result")
    tid, subject, count = m.group(1), m.group(2).strip(), int(m.group(3))
    parts = MSG_SPLIT.split(text[m.end():])
    msgs = []
    for i in range(1, len(parts), 2):
        block = parts[i + 1].lstrip("\n")
        head, _, body = block.partition("\n\n")
        hdr = dict(line.split(": ", 1) for line in head.split("\n") if ": " in line)
        if "From" not in hdr:
            raise L.Refuse(3, "message %s has no From line" % parts[i])
        try:
            when = parsedate_to_datetime(hdr.get("Date", "")).astimezone(L.TPE)
        except (TypeError, ValueError):
            when = None                     # a draft can lack a Date: order is the thread's, not the clock's
        name, addr = parseaddr(hdr["From"])
        if "@" not in addr:
            found = re.search(r"[\w.+-]+@[\w.-]+", hdr["From"])
            addr = found.group(0) if found else ""
        body = body.replace("\r\n", "\n").replace("\r", "\n").split("\n--- ATTACHMENTS ---", 1)[0]
        msgs.append({"n": int(parts[i]), "from": addr.lower(), "name": name.strip(), "date": when,
                     "msgid": hdr.get("Message-ID", "").strip(), "body": body})
    if len(msgs) != count:
        raise L.Refuse(3, "thread says %d messages but %d were saved" % (count, len(msgs)))
    return tid, subject, msgs


def missing_rows(body, rows):
    """The (n, #) rows whose `n#…` cell pair the approval mail's text lacks: it went out short."""
    return ["%s#%s" % (n, num) for n, num in rows
            if not re.search(r"(?<![\d.])%s\s*#%s(?![\d.])" % (re.escape(n), re.escape(num)), body)]


QUOTE_HEAD = re.compile(r"(wrote:|寫道[:：])\s*$")
QUOTE_START = re.compile(r"^(-{2,}\s*Original Message|(From|寄件者|Sent|寄件日期)[:：]\s)")
# the first lines of an attribution Gmail wrapped before its 寫道： / wrote: line
ATTRIB_PART = re.compile(r"^On\s|<[^<>\s@]+@[^<>\s]+>|\d{4}\s*年\s*\d{1,2}\s*月")


def strip_quote(body):
    """The new text of a reply: everything above the quoted message."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        # Gmail wraps a long "On <date> <name> <address> wrote:" before "wrote:"
        wrapped = s.startswith("On ") and i + 1 < len(lines) and QUOTE_HEAD.search(lines[i + 1].strip())
        if wrapped or s.startswith(">") or QUOTE_HEAD.search(s) or QUOTE_START.match(s):
            j = i
            if not wrapped and QUOTE_HEAD.search(s):
                while j > 0 and i - j < 3 and ATTRIB_PART.search(lines[j - 1].strip()):
                    j -= 1
            return "\n".join(lines[:j]).strip()
    return body.strip()


# ── the reply grammar ────────────────────────────────────────────────────────
# Strict on purpose: recording an approval the owner withheld is the one outcome worse than asking
# twice. A sentence (split at line breaks and at ，。；！) that carries 核准, 退回, a digit or a
# Chinese-numeral item (第三 · 兩項) must be exactly a run of 全部核准 · 全部退回 · 核准 <numbers> ·
# 退回 <numbers>, with at most a polite tail. Any other sentence is talk. A reply that approves
# anything is read only when all of its talk is polite (thanks, greetings, the owner's own name, a
# phone's "Sent from" line), and no reply with a question mark is read at all. A reply that only
# rejects may carry its reasons.
DIGITS = str.maketrans("０１２３４５６７８９　～－", "0123456789 ~-")
CLAUSE = re.compile(r"[\n，。；;！!？?]+")
QUESTION = re.compile(r"[？?]")
KEYWORD = re.compile(r"核准|退回")
CN_NUM = re.compile(r"第\s*[一二三四五六七八九十兩]|[一二三四五六七八九十兩]\s*[項件號個]")
NUMS = r"第?\s*\d+(?:\s*(?:-|~|到|至)\s*\d+)?(?:\s*[項件號])?"     # never eats the space before the next number
SEG = re.compile(r"\s*(全部\s*核准|全部\s*退回|(核准|退回)\s*(%s(?:(?:\s*[,、和及與跟]\s*|\s+)%s)*))" % (NUMS, NUMS))
POLITE = re.compile(r"^(?:謝謝|感謝|多謝|謝啦|謝囉|thanks|thank you|thx|ok|okay|好的|好|收到|了解|知道了|辛苦了|麻煩了"
                    r"|嗨|hi|hello|hey|吧|喔|囉|啦|唷"
                    # a phone's sign-off names an ASCII device; \w would also take Chinese words
                    r"|sent from my [A-Za-z][A-Za-z0-9]*|從我的\s*[A-Za-z][A-Za-z0-9]*\s*傳送|get outlook for [A-Za-z][A-Za-z0-9]*"
                    r"|[~.…,、:)\s])*$", re.I)
ONE = re.compile(r"(\d+)(?:\s*(?:-|~|到|至)\s*(\d+))?")


class Unreadable(Exception):
    pass


def name_tokens(name):
    """The owner's display name and its words: a sign-off is not talk."""
    name = (name or "").strip().strip('"')
    return tuple(sorted({t for t in [name] + name.split() if len(t) >= 2}, key=len, reverse=True))


def polite(s, names=()):
    for t in names:
        s = re.sub(re.escape(t), " ", s, flags=re.I)
    return bool(POLITE.match(s))


def norm_reply(text):
    out = []
    for line in text.translate(DIGITS).split("\n"):
        if line == "-- ":
            break       # RFC 3676's signature line, exactly as Gmail writes it; a typed "--" is the owner's own text
        out.append(line)
    return "\n".join(out)


def has_instruction(text, names=()):
    """Thanks and greetings alone are no answer; anything else is read, and asked about once if it
    cannot be read."""
    t = norm_reply(text)
    return bool(QUESTION.search(t)) or any(c.strip() and not polite(c.strip(), names) for c in CLAUSE.split(t))


def parse_reply(text, count, names=()):
    """The owner's reply -> (approve, reject) as sorted lists of row numbers, or Unreadable with the
    reason in zh-TW."""
    t = norm_reply(text)
    if QUESTION.search(t):
        raise Unreadable("回覆裡有問句，我分不出這是決定還是問題")
    approve, reject, all_ok, all_no, said, talk = set(), set(), False, False, False, None
    for clause in CLAUSE.split(t):
        c = clause.strip()
        if not c:
            continue
        if not (KEYWORD.search(c) or re.search(r"\d", c) or CN_NUM.search(c)):
            if talk is None and not polite(c, names):
                talk = c
            continue
        pos = 0
        while True:
            m = SEG.match(c, pos)
            if not m:
                break
            word = re.sub(r"\s+", "", m.group(1))
            if word == "全部核准":
                all_ok = True
            elif word == "全部退回":
                all_no = True
            else:
                nums = set()
                for a, b in ONE.findall(m.group(3)):
                    lo, hi = int(a), int(b or a)
                    if hi < lo or hi - lo > MAX_ROWS:
                        raise Unreadable("「%s」的範圍看不懂" % m.group(1).strip())
                    nums.update(range(lo, hi + 1))
                bad = sorted(x for x in nums if not 1 <= x <= count)
                if bad:
                    raise Unreadable("編號 %s 不存在（這次只有 1–%d）" % ("、".join(map(str, bad)), count))
                (approve if m.group(2) == "核准" else reject).update(nums)
            pos = m.end()
        if pos == 0 or not polite(c[pos:], names):
            raise Unreadable("「%s」這句看不懂" % clip(c, 30))
        said = True
    if not said:
        raise Unreadable("回覆裡沒有「核准」或「退回」")
    if talk is not None and (approve or all_ok):
        raise Unreadable("除了核准和退回，還寫了「%s」，我不確定是不是有幾件要先排除" % clip(talk, 20))
    if all_ok and all_no:
        raise Unreadable("同時寫了「全部核准」和「全部退回」")
    both = sorted(approve & reject)
    if both:
        raise Unreadable("編號 %s 同時被核准又被退回" % "、".join(map(str, both)))
    every = set(range(1, count + 1))
    if all_ok:
        approve = every - reject
    if all_no:
        reject = every - approve
    return sorted(approve), sorted(reject)


# ── what apply writes in the thread ──────────────────────────────────────────
def restate_body(reason, count):
    return ("%s 這封回覆我讀不懂：%s。\n\n請再回覆一次，只寫核准、退回和編號，例如%s。編號是 1–%d，"
            "沒寫到的編號不會套用。" % (MARKER, reason, GRAMMAR, count))


def confirm_body(ok, no, pending, when):
    j = lambda xs: "、".join(map(str, xs)) or "無"  # noqa: E731
    said = "你 %d/%d %02d:%02d 的回覆" % (when.month, when.day, when.hour, when.minute) if when else "你的回覆"
    return ("%s%s（試行中，不會寫進總表）：\n核准：%s\n退回：%s\n沒寫到、這次不套用：%s\n\n"
            "之後的回覆不會再改這週的紀錄。" % (CONFIRM_HEAD, said, j(ok), j(no), j(pending)))


def draft_body():
    return ("%s 這封信下面有一份回覆草稿還沒寄出。草稿寄出或刪掉之前，我不會記下任何決定；"
            "週日晚上 10 點前處理都來得及。" % MARKER)


def reply_call(run, tid, subject, body, msgs, target):
    """A plain-text message in the thread, answering `target`. When that message printed no
    Message-ID, it answers the newest earlier one that did, so Gmail keeps it in the thread."""
    ids = [m["msgid"] for m in msgs if m["msgid"] and m["n"] <= target["n"]]
    args = {"user_google_email": run["account"], "to": run["account"],
            "subject": subject if subject.startswith("Re: ") else "Re: " + subject,
            "body": body, "body_format": "plain", "thread_id": tid, "include_signature": False}
    if ids:
        args.update(in_reply_to=target["msgid"] or ids[-1], references=" ".join(ids))
    return {"tool": "mcp__google-workspace__send_gmail_message", "args": args}


# ── sent and apply ───────────────────────────────────────────────────────────
def thread_state_path(week):
    return state_file(week, "approval.json")


def p_sent(d):
    """Run after the Ledger write, on the saved `sent_search` result. Three answers:
    {"found": false} -> the mail is not in Sent: send it, repeat the search (same save path), run
    `sent` again; {"calls": [...]} -> fetch that thread and run `sent` again; {"found": true} -> the
    mail in Sent is exactly the mail `check` wrote, under our subject, and its thread is recorded.
    "Send" is said once per run, and not again within 40 minutes of any attempt's send unless that
    send is known to have failed (`sent --send-failed`)."""
    run = L.load_run(d)
    if not run.get("subject"):
        raise L.Refuse(2, "nothing to mail in this run")
    sp, tp = os.path.join(d, "sent-search.txt"), os.path.join(d, "sent-thread.txt")
    if os.path.exists(tp) and os.path.getmtime(tp) >= os.path.getmtime(sp):
        text, _ = load_thread(tp)
        tid, subject, msgs = parse_thread(text)
        if subject != run["subject"]:
            raise L.Refuse(3, "the newest 待核准 thread is %r, not this run's %r" % (subject, run["subject"]))
        got = " ".join(msgs[0]["body"].split())
        if got != run["mail_flat"]:
            gone = missing_rows(got, run["row_keys"])
            raise L.Refuse(6, "the approval mail in Sent is not the mail `check` wrote (%s); it went out wrong"
                           % ("rows missing: " + "、".join(gone) if gone else "a value differs"))
        rec = {"week": run["week"], "thread_id": tid, "subject": subject, "rows": run["rows"],
               "mail_sha": sha(got), "rows_sha": run["rows_sha"],
               "sent_at": L.stamp(msgs[0]["date"]) if msgs[0]["date"] else ""}
        p = thread_state_path(run["week"])
        write_state(p, json.dumps(rec, ensure_ascii=False))
        return {"found": True, "delivered": "approval-mail;%d-rows;thread-%s" % (run["rows"], tid), "recorded": p}
    ids = search_ids(L.load_result(sp), run["sent_query"])
    if len(ids) > 1:
        raise L.Refuse(3, "%d approval mails for %s are in Sent; record by hand, in %s, the thread the owner "
                          "answers — this run writes nothing" % (len(ids), run["week"], thread_state_path(run["week"])))
    if not ids:
        if run.get("send_instructed"):
            raise L.Refuse(6, "the approval mail was sent but is not in Sent yet; stop here — the next attempt "
                              "looks again")
        mark = state_file(run["week"], "approval-send")
        if os.path.exists(mark) and time.time() - os.path.getmtime(mark) < RESEND_AFTER:
            raise L.Refuse(6, "an earlier attempt sent the approval mail %d minutes ago and Sent does not show it "
                              "yet; it is not sent again so soon" % ((time.time() - os.path.getmtime(mark)) // 60))
        write_state(mark, L.stamp(L.parse_now(None)))
        run["send_instructed"] = True
        L.save_run(run)
        return {"found": False}
    return {"found": None, "calls": [L.call("get_gmail_thread_content",
                                            {"user_google_email": run["account"], "thread_id": ids[0]}, tp)]}


def p_send_failed(d):
    """The send `sent` asked for returned an error: nothing went out, so a later attempt may send."""
    run = L.load_run(d)
    if not run.get("send_instructed"):
        raise L.Refuse(2, "this run was not told to send")
    mark = state_file(run["week"], "approval-send")
    if os.path.exists(mark):
        os.remove(mark)
    run["send_instructed"] = False
    L.save_run(run)
    return {"cleared": True}


def a_start(week, config=None, now=None, base=None):
    cfg = L.load_config(config)
    mode = apply_mode(raw_config(config))
    if mode == "live":
        raise L.Refuse(2, LIVE_REFUSED)
    run = new_run(cfg, week, "apply", now, base)
    run["mode"] = mode
    r = run["weeks_row"]
    calls = [L.read_call(run, cfg["ledger"], "Weeks!A%d:R%d" % (r, r), "wr"),
             L.read_call(run, cfg["ledger"], block_range("Proposals", run["k"])[2], "pp"),
             L.read_call(run, cfg["ledger"], block_range("Decisions", run["k"])[2], "dc"),
             L.read_call(run, cfg["ledger"], block_range("Reports", run["k"])[2], "rp")]
    rec_path = thread_state_path(week)
    if os.path.exists(rec_path):
        rec = json.load(open(rec_path, encoding="utf-8"))
        run.update(thread_id=rec["thread_id"], mail_sha=rec.get("mail_sha"), rows_sha=rec.get("rows_sha"))
        calls.append(L.call("get_gmail_thread_content", {"user_google_email": cfg["account"], "thread_id": rec["thread_id"],
                                                         "include_analysis": True},
                            os.path.join(run["dir"], "thread.txt")))
    else:
        run["search_query"] = 'in:sent subject:待核准 "%s" newer_than:5d' % week
        calls.append(L.call("search_gmail_messages", {"user_google_email": cfg["account"], "page_size": 5,
                                                      "query": run["search_query"]},
                            os.path.join(run["dir"], "search.txt")))
    L.save_run(run)
    return {"dir": run["dir"], "week": week, "mode": run["mode"], "calls": calls}


def a_thread(d):
    run = L.load_run(d)
    ids = search_ids(L.load_result(os.path.join(d, "search.txt")), run["search_query"])
    if len(ids) > 1:
        raise L.Refuse(3, "%d 待核准 threads for %s; record by hand, in %s, the thread the owner answers — "
                          "this run writes nothing" % (len(ids), run["week"], thread_state_path(run["week"])))
    if not ids:
        return {"found": False}
    run["thread_id"] = ids[0]
    L.save_run(run)
    return {"found": True, "calls": [L.call("get_gmail_thread_content",
                                            {"user_google_email": run["account"], "thread_id": ids[0],
                                             "include_analysis": True},
                                            os.path.join(d, "thread.txt"))]}


def reply_key(m):
    if m["msgid"]:
        return m["msgid"]
    return "n%d:%s" % (m["n"], sha(m["body"])[:12])


def confirmed_lists(body):
    """(approved, rejected) as our own confirmation states them."""
    got = []
    for label in ("核准", "退回"):
        m = re.search(r"^%s：(.*)$" % label, body, re.M)
        got.append([] if not m or m.group(1).strip() == "無" else [int(x) for x in m.group(1).split("、")])
    return got


def draft_wait(run, tid, subject, msgs, now):
    """A reply draft is open in the thread. Drafts print like sent mail, so nothing is read until it is
    sent or deleted; one still open two hours after it was first seen gets one note in the thread."""
    seen = state_file(run["week"], "draft-seen")
    t = L.parse_now(now)
    if not os.path.exists(seen):
        write_state(seen, L.stamp(t))
        return {"status": "waiting", "delivered": "draft-open"}
    first = L.parse_now(open(seen, encoding="utf-8").read().strip())
    if (t - first).total_seconds() >= DRAFT_NOTE_AFTER and not os.path.exists(state_file(run["week"], "draft-noted")):
        run["pending_send"] = {"kind": "draft-note"}
        L.save_run(run)
        return {"status": "waiting", "delivered": "draft-open;noted",
                "send": reply_call(run, tid, subject, draft_body(), msgs, msgs[0])}
    return {"status": "waiting", "delivered": "draft-open"}


def a_sent(d):
    """After a restate request or a draft note from `apply-decide` went through: remember it, so the
    next look does not send it again. Nothing is remembered for a send that failed."""
    run = L.load_run(d)
    p = run.get("pending_send")
    if not p:
        raise L.Refuse(2, "this run has no restate request or draft note waiting to be recorded")
    if p["kind"] == "restate":
        asked = state_file(run["week"], "restated.json")
        write_state(asked, json.dumps(read_list(asked) + [p["key"]], ensure_ascii=False))
    else:
        write_state(state_file(run["week"], "draft-noted"), L.stamp(L.parse_now(None)))
    run["pending_send"] = None
    L.save_run(run)
    return {"recorded": p["kind"]}


def updates_write(d):
    # shadow mode applies nothing, so the week's Updates block is empty; writing it stamps Weeks Q
    return {"tab": "Updates", "rows_path": write_rows(os.path.join(d, "decided-updates.json"), [])}


def a_decide(d, now=None):
    run = L.load_run(d)
    if run["mode"] == "live":
        raise L.Refuse(2, LIVE_REFUSED)
    look = run.get("look", 1)
    sfx = "" if look == 1 else "-%d" % look
    w = weeks_cells(run)
    r = run["weeks_row"]
    # Weeks Q is written last, and only once the confirmation is in the thread: it means "final"
    if w["applied"] == "ok":
        return {"status": "ok", "delivered": "already-applied;Weeks!Q%d" % r}
    if w["proposals"] != "ok":
        return {"status": "ok", "delivered": "nothing-proposed"}
    rows = [c for _, c in read_block(run, "Proposals", "pp")]
    if not rows:
        return {"status": "ok", "delivered": "no-proposals", "write": [updates_write(d)]}
    count = len(rows)
    tp = os.path.join(d, "thread%s.txt" % sfx)
    if not os.path.exists(tp):
        if look > 1:
            raise L.Refuse(3, "missing saved result: %s" % tp)
        return {"status": "failed", "delivered": "approval-mail-not-found"}
    text, analysis = load_thread(tp)
    tid, subject, msgs = parse_thread(text)
    if tid != run.get("thread_id"):
        raise L.Refuse(3, "the saved thread is %s, not the %s this run asked for" % (tid, run.get("thread_id")))
    want = subject_for(run["week"], count)
    if subject != want:
        raise L.Refuse(3, "the thread is %r, expected %r" % (subject, want))
    # the owner decides on the mail they read, and it must be the mail these Ledger rows made
    sent_flat = " ".join(msgs[0]["body"].split())
    if run.get("mail_sha") and run.get("rows_sha"):
        if sha(sent_flat) != run["mail_sha"]:
            return {"status": "failed", "delivered": "approval-mail-differs;not-the-mail-sent"}
        if rows_sha(rows) != run["rows_sha"]:
            return {"status": "failed", "delivered": "proposals-changed;Proposals-block-edited-after-the-mail"}
    else:
        run["evidence"] = {x["ref"]: x for x in evidence_rows(run)}
        if sent_flat != flat_text(render_mail(run, rows)):
            gone = missing_rows(sent_flat, [(c[2], c[3]) for c in rows])
            return {"status": "failed", "delivered": "approval-mail-differs;" + (",".join(gone) or "values")}
    if analysis is None:
        raise L.Refuse(3, "the thread was saved without its analysis; fetch it with include_analysis as printed")
    owner = run["account"].lower()
    replies, restates, confirms = [], [], []
    for m in msgs[1:]:                              # thread order, never the Date header's order
        body = strip_quote(m["body"])
        if body.startswith(CONFIRM_HEAD):
            confirms.append(body)
        elif body.startswith(RESTATE_HEAD):
            restates.append(m["n"])
        elif body.startswith(MARKER):
            continue
        elif m["from"] == owner:
            replies.append((m, body))
    if confirms:
        # final: the confirmation went out, and only the Updates write after it is missing
        ok, no = confirmed_lists(confirms[-1])
        if ([int(c[2]) for c in rows if c[12] == "核准"], [int(c[2]) for c in rows if c[12] == "退回"]) != (ok, no):
            return {"status": "failed", "delivered": "confirmation-disagrees-with-the-Proposals-block"}
        return {"status": "ok", "delivered": "confirmed;recording-applied", "write": [updates_write(d)]}
    if look > 1:
        written = [c for _, c in read_block(run, "Proposals", "pp" + sfx)]
        if [list(c[12:15]) for c in written] != run.get("decided_cells"):
            raise L.Refuse(6, "the Proposals block does not hold the decision just made; write it first")
    if int(analysis.get("excluded_drafts") or 0) > 0:
        return draft_wait(run, tid, subject, msgs, now)
    try:
        os.remove(state_file(run["week"], "draft-seen"))
    except OSError:
        pass
    instr = [(m, t) for m, t in replies if has_instruction(t, name_tokens(m["name"]))]
    if not instr:
        if look > 1:
            raise L.Refuse(6, "the reply that was decided is no longer in the thread")
        return {"status": "waiting", "delivered": "no-reply-yet"}
    m, body = instr[-1]
    key = reply_key(m)
    if (restates and max(restates) > m["n"]) or key in read_list(state_file(run["week"], "restated.json")):
        return {"status": "waiting", "delivered": "asked-to-restate"}
    try:
        ok, no = parse_reply(body, count, name_tokens(m["name"]))
    except Unreadable as e:
        run["pending_send"] = {"kind": "restate", "key": key}
        L.save_run(run)
        return {"status": "waiting", "delivered": "reply-unreadable",
                "send": reply_call(run, tid, subject, restate_body(str(e), count), msgs, m)}
    pending = [n for n in range(1, count + 1) if n not in ok and n not in no]
    delivered = "shadow;%d-approved;%d-rejected;%d-pending" % (len(ok), len(no), len(pending))
    decision = {"reply": key, "approved": ok, "rejected": no}
    if look > 1 and run.get("decided") == decision:
        return {"status": "confirm", "mode": "shadow", "approved": ok, "rejected": no, "pending": pending,
                "delivered": delivered,
                "send": reply_call(run, tid, subject, confirm_body(ok, no, pending, m["date"]), msgs, m),
                "write": [updates_write(d)]}
    if look >= MAX_LOOKS:
        raise L.Refuse(6, "the owner replied again while apply was writing; the next look decides")
    at = L.stamp(m["date"] or L.parse_now(now))
    out = []
    for c in rows:
        c = list(c)
        n = int(c[2])
        c[12] = "核准" if n in ok else ("退回" if n in no else "未回覆")
        c[13] = at if n in ok or n in no else ""
        c[14] = {"核准": "would-apply", "退回": "退回", "未回覆": "未回覆"}[c[12]]
        out.append(c)
    nsfx = "-%d" % (look + 1)
    run.update(look=look + 1, decided=decision, decided_cells=[c[12:15] for c in out])
    L.save_run(run)
    return {"status": "recheck", "mode": "shadow", "approved": ok, "rejected": no, "pending": pending,
            "delivered": delivered,
            "write": [{"tab": "Proposals", "rows_path": write_rows(os.path.join(d, "decided-proposals.json"), out)}],
            "then": [L.read_call(run, run["ledger"], block_range("Proposals", run["k"])[2], "pp" + nsfx),
                     L.call("get_gmail_thread_content", {"user_google_email": run["account"], "thread_id": tid,
                                                         "include_analysis": True},
                            os.path.join(d, "thread%s.txt" % nsfx))]}


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("cmd", nargs="?", choices=["start", "pages", "context", "check", "sent", "apply-start",
                                                "apply-thread", "apply-decide", "apply-sent", "parse"])
    ap.add_argument("--week")
    ap.add_argument("--config")
    ap.add_argument("--dir")
    ap.add_argument("--input")
    ap.add_argument("--now")
    ap.add_argument("--text")
    ap.add_argument("--count", type=int)
    ap.add_argument("--send-failed", action="store_true", help="with `sent`: the send it asked for returned an error")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if a.cmd in ("start", "apply-start"):
            if not a.week:
                raise L.Refuse(2, "%s needs --week" % a.cmd)
            L.monday(a.week)
            L.emit((p_start if a.cmd == "start" else a_start)(a.week, a.config, a.now))
        elif a.cmd == "parse":
            try:
                ok, no = parse_reply(a.text or "", a.count or 0)
                L.emit({"approve": ok, "reject": no})
            except Unreadable as e:
                L.emit({"unreadable": str(e)})
        elif a.cmd:
            if not a.dir:
                raise L.Refuse(2, "%s needs --dir" % a.cmd)
            if a.cmd == "check":
                if not a.input:
                    raise L.Refuse(2, "check needs --input")
                L.emit(p_check(a.dir, a.input, a.now))
            elif a.cmd == "apply-decide":
                L.emit(a_decide(a.dir, a.now))
            elif a.cmd == "sent" and a.send_failed:
                L.emit(p_send_failed(a.dir))
            else:
                L.emit({"pages": p_pages, "context": p_context, "sent": p_sent, "apply-thread": a_thread,
                        "apply-sent": a_sent}[a.cmd](a.dir))
        else:
            ap.print_help()
            return 2
    except L.Refuse as e:
        print("proposals.py: %s" % e, file=sys.stderr)
        return e.code
    return 0


# ── selftest ─────────────────────────────────────────────────────────────────
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
        except L.Refuse as e:
            if e.code != code:
                fails.append("%s: refused with %d (%s), want %d" % (name, e.code, e, code))

    def reads(name, text, count, want, names=()):
        try:
            check(name, parse_reply(text, count, names), want)
        except Unreadable as e:
            fails.append("%s: unreadable (%s)" % (name, e))

    def unreadable(name, text, count, names=()):
        try:
            got = parse_reply(text, count, names)
            fails.append("%s: was read as %r" % (name, got))
        except Unreadable:
            pass

    me = name_tokens("Peter Tu")
    # the grammar
    reads("全部核准", "全部核准", 3, ([1, 2, 3], []))
    reads("全部 核准", "全部 核准", 2, ([1, 2], []))
    reads("核准 1 3", "核准 1 3", 3, ([1, 3], []))
    reads("退回 2", "退回 2", 3, ([], [2]))
    reads("全部核准 退回 2", "全部核准 退回 2", 3, ([1, 3], [2]))
    reads("full-width digits and 、", "核准１、３", 3, ([1, 3], []))
    reads("an ASCII comma between numbers", "核准 1,3", 3, ([1, 3], []))
    reads("a range", "核准 1-3\n退回 4", 5, ([1, 2, 3], [4]))
    reads("greeting, thanks and the owner's name", "嗨\n全部核准，謝謝\n\nPeter", 2, ([1, 2], []), me)
    reads("a polite tail", "核准 1 3 謝謝", 3, ([1, 3], []))
    reads("a phone's sign-off", "全部核准\n\nSent from my iPhone", 2, ([1, 2], []))
    reads("a phone's sign-off in zh-TW", "全部核准\n\n從我的 iPhone 傳送", 2, ([1, 2], []))
    reads("a reason on a rejection", "退回 2，因為日期不對", 3, ([], [2]))
    reads("a hold on a rejection", "全部退回，先擱置", 3, ([], [1, 2, 3]))
    reads("全部退回 核准 1", "全部退回 核准 1", 3, ([1], [2, 3]))
    reads("核准第1項和第3項", "核准第1項和第3項", 3, ([1, 3], []))
    reads("the signature is cut", "全部核准\n-- \nPeter Tu\n0912 345 678", 2, ([1, 2], []))
    unreadable("no keyword", "我週末再看", 3)
    unreadable("核准 with no number", "核准", 3)
    unreadable("a number out of range", "核准 4", 3)
    unreadable("both ways", "核准 1 退回 1", 3)
    unreadable("全部 both ways", "全部核准\n全部退回", 3)
    unreadable("zero", "核准 0", 3)
    unreadable("a backwards range", "核准 3-1", 3)
    # each of these withholds something or asks something: reading any of them as an approval is the
    # failure that matters
    for name, text in (("but, after a comma", "全部核准，但 2 先不要"),
                       ("not this one, next line", "全部核准\n2 先不要"),
                       ("except, after", "核准 1 3 以外的"),
                       ("except, in front", "除了 2 都核准"),
                       ("a hold in English, glued on", "全部核准，訪談那件先hold"),
                       ("a hedge with no number", "全部核准，最後那件先等等"),
                       ("a Chinese numeral", "全部核准，二駁回"),
                       ("wait for someone", "全部核准\n訪談那件先等 Bob 回來"),
                       ("not sure", "全部核准，最後那件我不確定"),
                       ("shelved", "全部核准，訪談那件擱置"),
                       ("English on its own line", "全部核准\nreject the second one"),
                       ("numbers with no keyword", "全部核准\n2 和 3 交給 Ann"),
                       ("a number with no keyword, beside a rejection", "退回 2\n3 也是"),
                       ("Chinese numerals and no", "全部核准，第三項不行"),
                       ("a question", "全部核准？"),
                       ("a question after the numbers", "核准 2？你確定嗎"),
                       ("an ASCII question mark", "核准 1 3?"),
                       ("a made-up phone line", "從我的訪談不要傳送；核准 1-3"),
                       ("a made-up English phone line", "全部核准\nSent from my 訪談那件先不要"),
                       ("a typed dash line is not a signature", "全部核准\n--\n訪談那件先不要"),
                       ("an em dash line is not a signature", "全部核准\n—\n第 2 件先不要"),
                       ("a reason glued on", "退回 2 因為日期不對"),
                       ("an item number is not a row number", "核准 1.03"),
                       ("words before the keyword", "好 全部核准")):
        unreadable(name, text, 5, me)
    check("instruction: thanks alone is not", has_instruction("謝謝！\n\n-- \nPeter 0912", me), False)
    check("instruction: thanks and the owner's name is not", has_instruction("謝謝 Peter", me), False)
    check("instruction: a hedge is", has_instruction("等一下，先別套用"), True)
    check("instruction: English is", has_instruction("approve all"), True)
    check("instruction: a question is", has_instruction("這是什麼？"), True)
    check("item numbers sort by parts", sorted(["1.10", "2.01", "1.9", "1.a", "1.02"], key=num_key),
          ["1.02", "1.9", "1.10", "1.a", "2.01"])

    # quotes
    body = "核准 1 3\n\nOn Fri, Oct 16, 2026 at 10:05 AM Peter Tu <peter_tu@example.com>\nwrote:\n\n> 這週的總表變更提案\n> 全部核准"
    check("strip a wrapped English attribution", strip_quote(body), "核准 1 3")
    body_zh = "全部核准\n\nPeter Tu <peter_tu@example.com> 於 2026年10月16日 週五 上午10:05寫道：\n\n> 退回 2"
    check("strip a zh attribution", strip_quote(body_zh), "全部核准")
    wrap_zh = "核准 2\n\nPeter Tu <peter_tu@example.com>\n於 2026年10月16日 週五 上午10:05\n寫道：\n\n> 退回 2"
    check("strip a wrapped zh attribution", strip_quote(wrap_zh), "核准 2")
    check("strip > lines", strip_quote("退回 2\n> 核准 1"), "退回 2")
    check("no quote", strip_quote("全部核准\n"), "全部核准")

    # threads, in the layout get_gmail_thread_content prints
    T = "Thread ID: %s\nSubject: %s\nMessages: %d\n\n%s"

    def msg(n, frm, when, body, msgid=None, subject=None, attach=False):
        head = ["=== Message %d ===" % n, "From: %s" % frm, "Date: %s" % when]
        if msgid:
            head += ["Message-ID: %s" % msgid, "In-Reply-To: <p1@x>", "References: <p1@x>"]
        if subject:
            head.append("Subject: %s" % subject)
        out = "\n".join(head) + "\n\n" + body + "\n\n"
        if attach:
            out += "--- ATTACHMENTS ---\n1. a.pdf (application/pdf, 1.0 KB)\n   Attachment ID: x\n\n"
        return out

    subj = subject_for("2026-W42", 3)
    check("subject", subj, "【待核准】WB 10/12 那週 · 3 件（2026-W42）")
    t1 = T % ("abc123", subj, 2, msg(1, "peter_tu@example.com", "Fri, 16 Oct 2026 10:06:00 +0800", "提案 …")
              + msg(2, "Peter Tu <peter_tu@example.com>", "(unknown date)",
                    "全部核准 退回 2\r\n\r\nOn Fri, Oct 16 Peter wrote:\r\n> 提案", msgid="<r2@mail.gmail.com>",
                    subject="Re: " + subj, attach=True))
    tid, s, ms = parse_thread(t1)
    check("thread id", tid, "abc123")
    check("thread messages", [m["n"] for m in ms], [1, 2])
    check("thread from and name", (ms[1]["from"], ms[1]["name"]), ("peter_tu@example.com", "Peter Tu"))
    check("an undated message", ms[1]["date"], None)
    check("its Message-ID", ms[1]["msgid"], "<r2@mail.gmail.com>")
    check("attachments cut, CRLF folded", strip_quote(ms[1]["body"]), "全部核准 退回 2")
    refuses("thread count mismatch", 3, parse_thread,
            T % ("abc123", subj, 3, msg(1, "a@b.c", "Fri, 16 Oct 2026 10:06:00 +0800", "x")))

    # search results
    q5 = 'in:sent subject:待核准 "2026-W42" newer_than:5d'

    def found(q, *tids):
        return "\n".join(["Found %d messages matching '%s':" % (len(tids), q), "", "📧 MESSAGES:"]
                         + ["  %d. Message ID: m%d\n     Web Link: x\n     Thread ID: %s\n" % (i + 1, i, t)
                            for i, t in enumerate(tids)])

    check("search: one thread", search_ids(found(q5, "1a08", "1a08"), q5), ["1a08"])
    check("search: none", search_ids("No messages found for query: '%s'" % q5, q5), [])
    refuses("search: another query's result", 3, search_ids, found(q5.replace("W42", "W41"), "1a08"), q5)
    refuses("search: an error", 3, search_ids, "Error: invalid_grant", q5)

    # propose + apply end to end against saved results
    tmp = tempfile.mkdtemp(prefix="proposals-")
    try:
        os.environ["ZYNKR_OPS_WEEKLY_STATE"] = os.path.join(tmp, "state")
        cfgp = os.path.join(tmp, "cfg.json")

        def config(mode):
            json.dump({"google_account": "peter_tu@example.com",
                       "sources": {"main_tracker": {"id": "TRK", "tab": "H2", "cycle": "2026H2"},
                                   "ledger": {"id": "LED", "epoch_week": "2026-W40"}},
                       "routine": {"apply_mode": mode}}, open(cfgp, "w"))

        config("shadow")
        for name, raw in (("plain text", "Thread ID: x"), ("result-wrapped text", json.dumps({"result": "Thread ID: x"})),
                          ("with analysis", json.dumps({"content": "Thread ID: x", "analysis": {"excluded_drafts": 0}})),
                          ("result-wrapped analysis",
                           json.dumps({"result": json.dumps({"content": "Thread ID: x", "analysis": {"excluded_drafts": 0}})}))):
            lp = os.path.join(tmp, "lt.txt")
            open(lp, "w").write(raw)
            got = load_thread(lp)
            check("load_thread: " + name, (got[0], got[1] is not None), ("Thread ID: x", "analysis" in name))

        def fmt(sid, rng, rows):
            if not rows:
                return "No data found in range '%s' in spreadsheet %s." % (rng, sid)
            return "\n".join(["Successfully read %d rows from range '%s' in spreadsheet %s for peter_tu@example.com:"
                              % (len(rows), rng, sid)] + ["Row %2d: %r" % (i + 1, r) for i, r in enumerate(rows)])

        def info(sid, tabs):
            return "\n".join(['Spreadsheet: "x" (ID: %s) | Locale: en_US' % sid, "Sheets (%d):" % len(tabs)]
                             + ['  - "%s" (ID: %d) | Size: %dx%d' % (t, i, r, c) for i, (t, (r, c)) in enumerate(tabs.items())])

        def item(num, status, end="", note="", name=None):
            return [num, "1.0 M", "1.1 S", name or "item " + num, "", "", "P1", "Ann", "", "2026-09-01", end, status, note]

        tracker = [L.TRACKER_HEADER, item("1.01", "進行中", "2026-10-31"), item("1.02", "未開始", "2026/10/30"),
                   item("1.03", "進行中", note="跟 Ann 確認"), item("1.04", "完成"),
                   item("1.10", "未開始", name="訪談 <script>")]
        k = 2                                         # 2026-W42
        dfirst = L.block_slot("Decisions", k)[0]
        rfirst = L.block_slot("Reports", k)[0]
        decisions = [["2026-W42", "2026-10-15", "決議", "1.01 改到 11/15 交", "Ann", "2026-11-15", "1.01", "doc"],
                     ["2026-W42", "2026-10-15", "決議", "1.02 本週開工", "Ann", "2026-10-30", "1.02", "doc"],
                     ["2026-W42", "2026-10-15", "決議", "1.03 已交付給客戶", "Ann", "2026-10-15", "1.03", "doc"],
                     ["2026-W42", "2026-10-15", "決議", "1.04 重開", "Ann", "2026-10-30", "1.04", "doc"],
                     ["2026-W42", "2026-10-15", "待決", "1.02 要不要外包", "", "", "1.02", "doc"],
                     ["2026-W42", "2026-10-15", "決議", "1.01 最晚 11/20", "Ann", "2026/11/20", "1.01", "doc"]]
        reports = [["2026-W42", "2026-10-12T10:00:00+08:00", "bob@example.com", "Ops", "", "做 1.10 的訪談", "", "", "4-line"]]
        weeks_row = ["2026-W42", "ok", "", "2026H2", "TRK", "5", "", "", "", L.LAYOUT, "ok", "x", "ok", "y", "", "", "", ""]

        def feed(calls, sources):
            for c in calls:
                a = c["args"]
                if c["tool"].endswith("get_spreadsheet_info"):
                    sid = a["spreadsheet_id"]
                    tabs = {"H2": (60, 13)} if sid == "TRK" else {"Weeks": (100, 26), "Proposals": (2100, 15),
                                                                   "Updates": (2100, 14), "Decisions": (1000, 8),
                                                                   "Reports": (1000, 9)}
                    open(c["save"], "w").write(info(sid, tabs))
                elif c["tool"].endswith("read_sheet_values"):
                    rng = a["range_name"]
                    open(c["save"], "w", encoding="utf-8").write(fmt(a["spreadsheet_id"], rng, sources(rng)))

        def ledger_rows(rng, weeks=None, props=None):
            if rng.startswith("Weeks!"):
                return [weeks or weeks_row]
            if rng.startswith("Decisions!"):
                return decisions
            if rng.startswith("Reports!"):
                return reports
            if rng.startswith("Proposals!"):
                return props or []
            m = re.match(r"^'?H2'?!A(\d+):M(\d+)$", rng)
            a0, b0 = int(m.group(1)), int(m.group(2))
            return tracker[a0 - 1:b0]

        st = p_start("2026-W42", cfgp, "2026-10-16T10:05:00+08:00", os.path.join(tmp, "runs"))
        check("propose mode", st["mode"], "shadow")
        check("propose reads its own block too", st["calls"][-1]["args"]["range_name"], "Proposals!A82:O121")
        feed(st["calls"], ledger_rows)
        pg = p_pages(st["dir"])
        check("not yet proposed", pg["already"], False)
        feed(pg["calls"], ledger_rows)
        ctx = p_context(st["dir"])
        check("context items", [x["#"] for x in ctx["items"]], ["1.01", "1.02", "1.03", "1.04", "1.10"])
        dref = ["Decisions!A%d" % (dfirst + i) for i in range(len(decisions))]
        check("context decision refs", [x["ref"] for x in ctx["decisions"]], dref)
        rref = "Reports!A%d" % rfirst
        good = [{"#": "1.01", "欄位": "結束", "建議值": "2026-11-15", "原因": "週四會議改了交期", "證據": [dref[0]], "信心": "高"},
                {"#": "1.02", "欄位": "狀態", "建議值": "進行中", "原因": "會議決議本週開工", "證據": [dref[1]], "信心": "中"},
                {"#": "1.03", "欄位": "狀態", "建議值": "完成", "原因": "會議記錄已交付給客戶", "證據": [dref[2]], "信心": "高"},
                {"#": "1.10", "欄位": "狀態", "建議值": "進行中", "原因": "Bob 週報說已在做訪談", "證據": [rref], "信心": "低"},
                {"#": "1.03", "欄位": "備註", "建議值": "跟 Ann 確認\n10/15 會議：交付給客戶", "原因": "記下交付",
                 "證據": [dref[2]], "信心": "高"}]

        def try_one(name, code, p):
            pth = os.path.join(tmp, "one.json")
            json.dump([p], open(pth, "w"), ensure_ascii=False)
            refuses(name, code, p_check, st["dir"], pth)

        try_one("unknown item", 3, dict(good[0], **{"#": "9.99"}))
        try_one("a closed item", 3, {"#": "1.04", "欄位": "狀態", "建議值": "進行中", "原因": "x", "證據": [dref[3]], "信心": "高"})
        try_one("a field outside the three", 3, dict(good[1], **{"欄位": "負責人"}))
        try_one("a status outside the vocabulary", 3, dict(good[1], **{"建議值": "逾期"}))
        try_one("done from a self-report", 3, {"#": "1.10", "欄位": "狀態", "建議值": "完成", "原因": "x", "證據": [rref], "信心": "低"})
        try_one("a self-report above 低", 3, dict(good[3], **{"信心": "中"}))
        try_one("a 待決 row is no evidence", 3, dict(good[1], **{"證據": [dref[4]]}))
        try_one("another item's decision is no evidence", 3, dict(good[1], **{"證據": [dref[0]]}))
        try_one("an end date no decision set", 3, dict(good[0], **{"建議值": "2026-11-21"}))
        try_one("an end date that is not a date", 3, dict(good[0], **{"建議值": "11/15"}))
        try_one("evidence from another week", 3, dict(good[1], **{"證據": ["Decisions!A2"]}))
        try_one("no evidence", 3, dict(good[1], **{"證據": []}))
        try_one("too much evidence", 3, dict(good[1], **{"證據": [dref[1]] * 4}))
        try_one("a two-line reason", 3, dict(good[1], **{"原因": "會議決議\n本週開工"}))
        try_one("a no-op", 3, {"#": "1.03", "欄位": "狀態", "建議值": "進行中", "原因": "x", "證據": [dref[2]], "信心": "高"})
        try_one("a no-op across date formats", 3,
                {"#": "1.02", "欄位": "結束", "建議值": "2026-10-30", "原因": "x", "證據": [dref[1]], "信心": "高"})
        try_one("a note that rewrites the old text", 3, dict(good[4], **{"建議值": "跟 Bob 確認\n10/15 會議：交付給客戶"}))
        try_one("a note that gains two lines", 3, dict(good[4], **{"建議值": "跟 Ann 確認\n10/15 a\n10/15 b"}))
        try_one("a note line without its date", 3, dict(good[4], **{"建議值": "跟 Ann 確認\n會議：交付給客戶"}))
        try_one("a note with 完成", 3, dict(good[4], **{"建議值": "跟 Ann 確認\n10/15 已完成交付"}))
        try_one("a note with 上線", 3, dict(good[4], **{"建議值": "跟 Ann 確認\n10/15 網站上線"}))
        one = os.path.join(tmp, "one-ok.json")
        json.dump([{"#": "1.01", "欄位": "結束", "建議值": "2026-11-20", "原因": "最晚 11/20", "證據": [dref[5]], "信心": "高"},
                   {"#": "1.02", "欄位": "備註", "建議值": "10/15 會議：本週開工", "原因": "記下開工", "證據": [dref[1]], "信心": "高"}],
                  open(one, "w"), ensure_ascii=False)
        check("a slash-dated decision backs an end date; a first note line", p_check(st["dir"], one)["rows"], 2)
        dup = os.path.join(tmp, "dup.json")
        json.dump([good[1], good[1]], open(dup, "w"), ensure_ascii=False)
        refuses("two proposals for one cell", 3, p_check, st["dir"], dup)
        okp = os.path.join(tmp, "good.json")
        json.dump(good, open(okp, "w"), ensure_ascii=False)
        cap = globals()["MAIL_TEXT_MAX"]
        globals()["MAIL_TEXT_MAX"] = 200
        try:
            refuses("a mail too long to read back", 5, p_check, st["dir"], okp)
        finally:
            globals()["MAIL_TEXT_MAX"] = cap
        ck = p_check(st["dir"], okp, "2026-10-16T10:20:00+08:00")
        rows = json.load(open(ck["rows_path"], encoding="utf-8"))
        keys = [(r[2], r[3]) for r in rows]
        check("rows numbered in item order", [(r[2], r[3], r[5]) for r in rows],
              [("1", "1.01", "結束"), ("2", "1.02", "狀態"), ("3", "1.03", "狀態"), ("4", "1.03", "備註"), ("5", "1.10", "狀態")])
        check("row width", len(rows[0]), len(L.PROPOSALS_HEADER))
        check("current value recorded", rows[0][6], "2026-10-31")
        check("source from evidence", (rows[2][10], rows[4][10]), ("會議", "自述"))
        check("mail subject", ck["mail"]["subject"], "【待核准】WB 10/12 那週 · 5 件（2026-W42）")
        check("mail to the owner", ck["mail"]["to"], "peter_tu@example.com")
        mail = open(ck["mail"]["body_path"], encoding="utf-8").read()
        flat = flat_text(mail)
        check("mail shows the shadow banner", "試行中" in mail, True)
        check("mail escapes", ("<script>" in mail, "訪談 <script>" in flat), (False, True))
        check("mail carries the grammar", "全部核准 退回 2" in flat, True)
        check("a note shows only its new line", ("加一行：10/15 會議：交付給客戶" in flat, "跟 Ann 確認" in flat), (True, False))
        check("every row has its cell pair", missing_rows(flat, keys), [])
        check("a dropped row is caught", missing_rows(flat.replace("4#1.03", ""), keys), ["4#1.03"])

        # the sent loop: an error refuses; not in Sent -> send once; found -> fetch; exactly ours -> recorded
        sp = os.path.join(st["dir"], "sent-search.txt")
        q1 = ck["sent_search"]["args"]["query"]
        open(sp, "w").write("Error: invalid_grant")
        refuses("an error is not 'not found'", 3, p_sent, st["dir"])
        open(sp, "w").write(found(q1, "abc123", "def456"))
        refuses("two approval mails in Sent", 3, p_sent, st["dir"])
        open(sp, "w").write("No messages found for query: '%s'" % q1)
        check("not in Sent yet: send it", p_sent(st["dir"]), {"found": False})
        old = time.time() - RESEND_AFTER - 60
        os.utime(state_file("2026-W42", "approval-send"), (old, old))     # only the run's own memory can say no now
        refuses("still not in Sent after the send: stop, never send twice", 6, p_sent, st["dir"])
        time.sleep(0.01)
        open(sp, "w").write(found(q1, "abc123"))
        fetch = p_sent(st["dir"])
        check("found: fetch its thread", fetch["calls"][0]["args"]["thread_id"], "abc123")
        tpath = fetch["calls"][0]["save"]
        owner = "peter_tu@example.com"

        def sent_thread(body, s=ck["mail"]["subject"], tid="abc123"):
            # a mail sent through the API prints no Message-ID (Gmail names that header Message-Id)
            return T % (tid, s, 1, msg(1, owner, "Fri, 16 Oct 2026 10:21:00 +0800", body))

        time.sleep(0.01)
        open(tpath, "w", encoding="utf-8").write(sent_thread(flat, "【待核准】WB 10/12 那週 · 9 件（2026-W42）"))
        refuses("a thread with another subject is not ours", 3, p_sent, st["dir"])
        open(tpath, "w", encoding="utf-8").write(sent_thread(flat.replace("4#1.03", "")))
        refuses("a mail that went out short", 6, p_sent, st["dir"])
        open(tpath, "w", encoding="utf-8").write(sent_thread(flat.replace("2026-11-15", "2026-12-15")))
        refuses("a mail whose value changed on the way", 6, p_sent, st["dir"])
        open(tpath, "w", encoding="utf-8").write(sent_thread(flat))
        sent = p_sent(st["dir"])
        check("sent and recorded", (sent["found"], sent["delivered"]), (True, "approval-mail;5-rows;thread-abc123"))
        approval = json.load(open(thread_state_path("2026-W42"), encoding="utf-8"))
        check("thread and hashes recorded for apply",
              (approval["thread_id"], approval["mail_sha"] == sha(flat), approval["rows_sha"] == rows_sha(rows)),
              ("abc123", True, True))

        # a later attempt: an earlier send holds a resend for 40 minutes, unless it is known to have failed
        stx = p_start("2026-W42", cfgp, "2026-10-16T10:35:00+08:00", os.path.join(tmp, "runs"))
        done_row = list(weeks_row)
        done_row[14:16] = ["ok", "2026-10-16T10:25:00+08:00"]
        recorded = [r[:12] + ["", "", ""] for r in rows]
        os.remove(thread_state_path("2026-W42"))
        feed(stx["calls"], lambda rng: ledger_rows(rng, weeks=done_row, props=recorded))
        rx = p_pages(stx["dir"])
        open(rx["sent_search"]["save"], "w").write("No messages found for query: '%s'" % q1)
        os.utime(state_file("2026-W42", "approval-send"), None)          # the first attempt sent just now
        refuses("an earlier attempt sent minutes ago: not again so soon", 6, p_sent, stx["dir"])
        old = time.time() - RESEND_AFTER - 60
        os.utime(state_file("2026-W42", "approval-send"), (old, old))
        check("40 minutes on and still not in Sent: it may go again", p_sent(stx["dir"]), {"found": False})
        check("the send returned an error: say so", p_send_failed(stx["dir"]), {"cleared": True})
        check("a failed send leaves no guard", os.path.exists(state_file("2026-W42", "approval-send")), False)
        refuses("only a run told to send can report a failed send", 2, p_send_failed, stx["dir"])
        sty = p_start("2026-W42", cfgp, "2026-10-16T11:05:00+08:00", os.path.join(tmp, "runs"))
        feed(sty["calls"], lambda rng: ledger_rows(rng, weeks=done_row, props=recorded))
        ry = p_pages(sty["dir"])
        open(ry["sent_search"]["save"], "w").write("No messages found for query: '%s'" % q1)
        check("after a failed send the next attempt sends at once", p_sent(sty["dir"]), {"found": False})

        # rows recorded but the mail never recorded: resume and mail exactly those rows
        st3 = p_start("2026-W42", cfgp, "2026-10-16T11:35:00+08:00", os.path.join(tmp, "runs"))
        feed(st3["calls"], lambda rng: ledger_rows(rng, weeks=done_row, props=recorded))
        rs = p_pages(st3["dir"])
        check("resume the mail", (rs["already"], rs.get("resume"), rs["mail"]["subject"]),
              (False, True, ck["mail"]["subject"]))
        check("the resumed mail is the same mail", flat_text(open(rs["mail"]["body_path"], encoding="utf-8").read()), flat)
        # recorded and mailed: done; recorded with nothing proposed: done, no mail
        write_state(thread_state_path("2026-W42"), json.dumps(approval, ensure_ascii=False))
        st2 = p_start("2026-W42", cfgp, "2026-10-16T11:45:00+08:00", os.path.join(tmp, "runs"))
        feed(st2["calls"], lambda rng: ledger_rows(rng, weeks=done_row, props=recorded))
        check("already proposed", p_pages(st2["dir"])["already"], True)
        st4 = p_start("2026-W42", cfgp, "2026-10-16T11:55:00+08:00", os.path.join(tmp, "runs"))
        feed(st4["calls"], lambda rng: ledger_rows(rng, weeks=done_row, props=[]))
        check("nothing proposed: done", p_pages(st4["dir"])["already"], True)

        # apply
        prow = [r[:12] + ["", "", ""] for r in rows]
        applied_row = list(done_row)
        applied_row[16:18] = ["ok", "2026-10-17T09:05:00+08:00"]
        subj5 = subject_for("2026-W42", 5)
        first = msg(1, owner, "Fri, 16 Oct 2026 10:21:00 +0800", flat)

        def R(body, when="Sat, 17 Oct 2026 09:00:00 +0800", frm="Peter Tu <%s>" % owner, msgid=True):
            return (frm, when, body, msgid)

        def thread(*replies, **kw):
            return T % (kw.get("tid", "abc123"), subj5, 1 + len(replies), kw.get("first", first) + "".join(
                msg(i + 2, frm, when, body, msgid="<r%d@x>" % (i + 2) if mid else None, subject="Re: " + subj5)
                for i, (frm, when, body, mid) in enumerate(replies)))

        def clear():
            for what in ("restated.json", "draft-seen", "draft-noted"):
                try:
                    os.remove(state_file("2026-W42", what))
                except OSError:
                    pass

        def save_thread(path, text, analysis=None, raw=False):
            open(path, "w", encoding="utf-8").write(
                text if raw else json.dumps({"content": text, "analysis": analysis or {"excluded_drafts": 0}},
                                            ensure_ascii=False))

        def apply_with(text, weeks=None, analysis=None, search=None, props=None, raw=False, now="2026-10-17T10:05:00+08:00",
                       keep=False):
            if not keep:
                clear()
            a = a_start("2026-W42", cfgp, now, os.path.join(tmp, "runs"))
            for c in a["calls"]:
                if c["tool"].endswith("get_gmail_thread_content"):
                    save_thread(c["save"], text, analysis, raw)
                elif c["tool"].endswith("search_gmail_messages"):
                    open(c["save"], "w", encoding="utf-8").write(search)
                else:
                    feed([c], lambda x: ledger_rows(x, weeks=weeks or done_row, props=prow if props is None else props))
            if search is not None:
                for c in a_thread(a["dir"]).get("calls", []):
                    save_thread(c["save"], text, analysis, raw)
            out = a_decide(a["dir"], now)
            out["dir"] = a["dir"]
            return out

        def recheck(res, text, written=None, analysis=None, now="2026-10-17T10:06:00+08:00"):
            """The model writes the Proposals rows, makes the `then` reads, and decides again."""
            if written is None:
                written = json.load(open(res["write"][0]["rows_path"], encoding="utf-8"))
            for c in res["then"]:
                if c["tool"].endswith("get_gmail_thread_content"):
                    save_thread(c["save"], text, analysis)
                else:
                    feed([c], lambda x: ledger_rows(x, props=written))
            out = a_decide(res["dir"], now)
            out["dir"] = res["dir"]
            return out

        check("no reply yet waits", apply_with(thread())["delivered"], "no-reply-yet")
        # a draft is open: wait; still open two hours on: one note, remembered once it went out
        drafted = thread(R("核准 1", "(unknown date)"))
        d1 = apply_with(drafted, analysis={"excluded_drafts": 1})
        check("a draft open waits", (d1["status"], d1["delivered"], "send" in d1), ("waiting", "draft-open", False))
        d2 = apply_with(drafted, analysis={"excluded_drafts": 1}, now="2026-10-17T12:35:00+08:00", keep=True)
        da = d2["send"]["args"]
        check("a draft open two hours on: a note in the thread",
              (d2["delivered"], da["thread_id"], "in_reply_to" in da, da["body"].startswith(MARKER)),
              ("draft-open;noted", "abc123", False, True))
        d2b = apply_with(drafted, analysis={"excluded_drafts": 1}, now="2026-10-17T13:05:00+08:00", keep=True)
        check("a note that did not go out is offered again", d2b["delivered"], "draft-open;noted")
        check("a note that went out is remembered", a_sent(d2b["dir"]), {"recorded": "draft-note"})
        d3 = apply_with(drafted, analysis={"excluded_drafts": 1}, now="2026-10-17T14:35:00+08:00", keep=True)
        check("never a second note", (d3["delivered"], "send" in d3), ("draft-open", False))
        refuses("nothing to remember when nothing was offered", 2, a_sent, d3["dir"])
        refuses("a thread saved without its analysis", 3, lambda: apply_with(thread(R("全部核准")), raw=True))
        chat = apply_with(thread(R("好的，謝謝")))
        check("thanks alone is no answer", (chat["status"], chat["delivered"], "send" in chat), ("waiting", "no-reply-yet", False))
        unread = apply_with(thread(R("除了 2 都核准")))
        check("an unreadable reply waits", (unread["status"], unread["delivered"]), ("waiting", "reply-unreadable"))
        check("the restate request goes in the thread, answering that reply",
              (unread["send"]["args"]["thread_id"], unread["send"]["args"]["in_reply_to"]), ("abc123", "<r2@x>"))
        check("the restate request carries its head", unread["send"]["args"]["body"].startswith(RESTATE_HEAD), True)
        retry = apply_with(thread(R("除了 2 都核准")), keep=True)
        check("a restate request that did not go out is offered again", (retry["delivered"], "send" in retry),
              ("reply-unreadable", True))
        check("a restate request that went out is remembered", a_sent(retry["dir"]), {"recorded": "restate"})
        lost = apply_with(thread(R("除了 2 都核准")), keep=True)
        check("asked about that reply already, though the request is not in the thread",
              (lost["delivered"], "send" in lost), ("asked-to-restate", False))
        asked = R(restate_body("x", 5), "Sat, 17 Oct 2026 09:05:00 +0800", owner)
        again = apply_with(thread(R("除了 2 都核准"), asked))
        check("asked already: wait, do not ask again", (again["delivered"], "send" in again), ("asked-to-restate", False))
        no_id = apply_with(thread(R("核准 1"), R("除了 2 都核准", "Sat, 17 Oct 2026 09:10:00 +0800", msgid=False)))
        check("a reply with no Message-ID: answer the newest earlier one that has one",
              (no_id["send"]["args"]["in_reply_to"], no_id["send"]["args"]["references"]), ("<r2@x>", "<r2@x>"))
        fixed = apply_with(thread(R("除了 2 都核准"), asked, R("核准 1 3 4 5", "Sat, 17 Oct 2026 10:00:00 +0800")))
        check("a new reply after the request decides", (fixed["status"], fixed["approved"], fixed["pending"]),
              ("recheck", [1, 3, 4, 5], [2]))
        # the decision: write the Proposals block, read it and the thread again, confirm, then write Updates
        th = thread(R("全部核准 退回 2\n\nOn Fri, Oct 16, 2026 Peter Tu wrote:\n> 提案"))
        ok = apply_with(th)
        check("decided: the Proposals block is written first, and only it",
              (ok["status"], ok["approved"], ok["rejected"], ok["pending"], [w["tab"] for w in ok["write"]]),
              ("recheck", [1, 3, 4, 5], [2], [], ["Proposals"]))
        out = json.load(open(ok["write"][0]["rows_path"], encoding="utf-8"))
        check("decided rows", len(out), 5)
        check("decision cells", out[1][12:15], ["退回", "2026-10-17T09:00:00+08:00", "退回"])
        check("shadow result", out[0][14], "would-apply")
        check("then: read the Proposals block and the thread again", [c["save"].rsplit("/", 1)[-1] for c in ok["then"]],
              ["pp-2.txt", "thread-2.txt"])
        conf = recheck(ok, th)
        check("the same reply on the re-read: confirm, then write the Updates block",
              (conf["status"], conf["delivered"], [w["tab"] for w in conf["write"]]),
              ("confirm", "shadow;4-approved;1-rejected;0-pending", ["Updates"]))
        check("shadow writes no Updates rows", json.load(open(conf["write"][0]["rows_path"], encoding="utf-8")), [])
        ca = conf["send"]["args"]
        check("the confirmation goes in the thread", (ca["thread_id"], ca["in_reply_to"], ca["body"].startswith(CONFIRM_HEAD)),
              ("abc123", "<r2@x>", True))
        check("the confirmation says what was recorded",
              ("核准：1、3、4、5" in ca["body"], "退回：2" in ca["body"], "10/17 09:00" in ca["body"]), (True, True, True))
        check("our confirmation reads back", confirmed_lists(ca["body"]), [[1, 3, 4, 5], [2]])
        refuses("a re-read before the write landed", 6, lambda: recheck(apply_with(th), th, written=prow))
        stale = [list(r) for r in out]                # an older write: everything approved
        for c in stale:
            c[12:15] = ["核准", "2026-10-17T08:00:00+08:00", "would-apply"]
        refuses("a re-read that finds an older decision", 6,
                lambda: recheck(apply_with(thread(R("退回 2"))), thread(R("退回 2")), written=stale))
        late = R("退回 3", "Sat, 17 Oct 2026 10:05:30 +0800")
        moved = recheck(apply_with(th), thread(R("全部核准 退回 2"), late))
        check("a reply sent while apply wrote replaces the one it wrote", (moved["status"], moved["rejected"], moved["pending"]),
              ("recheck", [3], [1, 2, 4, 5]))
        check("and that one is confirmed after its own write",
              recheck(moved, thread(R("全部核准 退回 2"), late), now="2026-10-17T10:07:00+08:00")["status"], "confirm")
        later = R("退回 4", "Sat, 17 Oct 2026 10:06:30 +0800")
        refuses("a third answer inside one run: the next look decides", 6,
                lambda: recheck(moved, thread(R("全部核准 退回 2"), late, later), now="2026-10-17T10:07:00+08:00"))
        # written but never confirmed: Weeks Q stays empty, so nothing reads as applied
        redo = apply_with(th, props=out)
        check("written, not confirmed: the next look decides again", redo["status"], "recheck")
        unsure = apply_with(thread(R("全部核准 退回 2"), R("等一下，先別套用", "Sat, 17 Oct 2026 09:30:00 +0800")), props=out)
        check("a written decision the owner then questions stays unconfirmed, and unapplied",
              (unsure["status"], "write" in unsure), ("waiting", False))
        conf_msg = R(confirm_body([1, 3, 4, 5], [2], [], None), "Sat, 17 Oct 2026 09:10:00 +0800", owner)
        after = R("全部退回", "Sat, 17 Oct 2026 11:00:00 +0800")
        check("confirmed and applied: later replies change nothing",
              apply_with(thread(R("全部核准 退回 2"), conf_msg, after), weeks=applied_row, props=out)["delivered"],
              "already-applied;Weeks!Q4")
        finish = apply_with(thread(R("全部核准 退回 2"), conf_msg, after), props=out)
        check("confirmed, the Updates write missing: only that write is left",
              (finish["status"], [w["tab"] for w in finish["write"]]), ("ok", ["Updates"]))
        check("a confirmation the Proposals block disagrees with fails",
              apply_with(thread(R("全部核准 退回 2"), conf_msg))["delivered"], "confirmation-disagrees-with-the-Proposals-block")
        two = apply_with(thread(R("全部核准"), R("退回 2", "Sat, 17 Oct 2026 09:10:00 +0800")))
        check("before the confirmation, a newer reply replaces an older one",
              (two["approved"], two["rejected"], two["pending"]), ([], [2], [1, 3, 4, 5]))
        thanks = apply_with(thread(R("核准 1 3"), R("謝謝 Peter", "Sat, 17 Oct 2026 09:10:00 +0800")))
        check("thanks after a reply changes nothing", (thanks["status"], thanks["approved"]), ("recheck", [1, 3]))
        hedge = apply_with(thread(R("全部核准"), R("等一下，先別套用", "Sat, 17 Oct 2026 09:10:00 +0800")))
        check("a hedge after a reply is read, and asked about", hedge["delivered"], "reply-unreadable")
        # the reply quotes the approval mail, whose own grammar line holds 全部核准 and 退回 2
        quoted = ("核准 1\n\nOn Fri, Oct 16, 2026 at 10:21 AM Peter Tu <%s>\nwrote:\n\n"
                  "> 直接回覆這封信就好：「全部核准」、「核准 1 3」、「退回 2」或「全部核准 退回 2」。\n> %s 待核准 2026-W42" % (owner, MARKER))
        partial = apply_with(thread(R(quoted)))
        check("unmentioned rows stay pending", partial["pending"], [2, 3, 4, 5])
        check("an unmentioned row is written 未回覆",
              json.load(open(partial["write"][0]["rows_path"], encoding="utf-8"))[1][12:15], ["未回覆", "", "未回覆"])
        check("the quoted mail decides nothing", (partial["approved"], partial["rejected"]), ([1], []))
        undated = apply_with(thread(R("全部核准", "(unknown date)")))
        check("an undated reply takes the run's time",
              json.load(open(undated["write"][0]["rows_path"], encoding="utf-8"))[0][13], "2026-10-17T10:05:00+08:00")
        check("only the owner's reply counts",
              apply_with(thread(R("全部核准", frm="someone@else.example")))["delivered"], "no-reply-yet")
        check("nothing proposed", apply_with(thread(), weeks=weeks_row)["delivered"], "nothing-proposed")
        none = apply_with(thread(), props=[])
        check("no proposals: only the Updates block", (none["delivered"], [w["tab"] for w in none["write"]]),
              ("no-proposals", ["Updates"]))
        refuses("a thread for another subject", 3, lambda: apply_with(T % ("abc123", subject_for("2026-W41", 5), 1, first)))
        refuses("a saved thread that is another thread", 3, lambda: apply_with(thread(tid="fff999")))
        # the owner decides on the mail that was sent, about the rows it showed
        short = apply_with(thread(first=msg(1, owner, "Fri, 16 Oct 2026 10:21:00 +0800", flat.replace("4#1.03", ""))))
        check("a mail that is not the one sent fails", short["delivered"], "approval-mail-differs;not-the-mail-sent")
        edited = [list(r) for r in prow]
        edited[0][7] = "2026-12-31"
        check("a Proposals block edited after the mail fails", apply_with(thread(), props=edited)["delivered"],
              "proposals-changed;Proposals-block-edited-after-the-mail")
        decisions[0][3] = "1.01 改到 11/15 交（會後補充）"           # an evidence row edited after Friday
        check("an evidence row edited after the mail does not stop a recorded thread",
              apply_with(thread(R("核准 2")))["approved"], [2])
        # no thread recorded: the search finds it (the mail is then rendered again from the Ledger), none, or two
        os.remove(thread_state_path("2026-W42"))
        check("found by search after an evidence row changed: the rendered mail differs",
              apply_with(thread(R("核准 2")), search=found(q5, "abc123"))["delivered"], "approval-mail-differs;values")
        decisions[0][3] = "1.01 改到 11/15 交"
        check("no approval mail: apply fails",
              apply_with(thread(), search="No messages found for query: '%s'" % q5)["delivered"], "approval-mail-not-found")
        refuses("two candidate threads", 3, lambda: apply_with(thread(), search=found(q5, "aaa111", "bbb222")))
        check("found by search, then decided", apply_with(thread(R("核准 2")), search=found(q5, "abc123"))["approved"], [2])
        changed = apply_with(thread(first=msg(1, owner, "Fri, 16 Oct 2026 10:21:00 +0800",
                                              flat.replace("2026-11-15", "2026-12-15"))), search=found(q5, "abc123"))
        check("found by search, a value changed: fails", changed["delivered"], "approval-mail-differs;values")
        short2 = apply_with(thread(first=msg(1, owner, "Fri, 16 Oct 2026 10:21:00 +0800", flat.replace("4#1.03", ""))),
                            search=found(q5, "abc123"))
        check("found by search, a row missing: names it", short2["delivered"], "approval-mail-differs;4#1.03")
        # live mode is refused until 3b
        config("live")
        refuses("propose refuses live", 2, p_start, "2026-W42", cfgp, "2026-10-16T10:05:00+08:00", os.path.join(tmp, "runs"))
        refuses("apply refuses live", 2, a_start, "2026-W42", cfgp, "2026-10-16T18:05:00+08:00", os.path.join(tmp, "runs"))
        config("shadow")
        a = a_start("2026-W42", cfgp, "2026-10-16T18:05:00+08:00", os.path.join(tmp, "runs"))
        run = L.load_run(a["dir"])
        run["mode"] = "live"
        L.save_run(run)
        refuses("a run folder that says live", 2, a_decide, a["dir"])
        check("an unknown mode is shadow", apply_mode({"routine": {"apply_mode": "Live"}}), "shadow")
    finally:
        os.environ.pop("ZYNKR_OPS_WEEKLY_STATE", None)
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print("proposals.py selftest: %d FAILED" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("proposals.py selftest: all checks passed")
    return 0


MUTATIONS = [
    # (name, [(old, new), ...]) — every pair is applied; each old text must occur exactly once
    ("self-report treated as a meeting", [('meeting = [e for e in rows if e["ref"].startswith("Decisions!")]',
                                           'meeting = list(rows)')]),
    ("done allowed without a meeting record", [('if new == "完成" and not meeting:', 'if False:')]),
    ("end date without its decision", [('if not any(L.norm_date(e["期限"]) == date_norm(new) for e in meeting):',
                                        'if False:')]),
    ("note may be rewritten", [('if not new.startswith(cur + "\\n"):', "if False:")]),
    ("closed items proposed on", [('if it["狀態"] in TERMINAL:', 'if False:')]),
    ("a 待決 row as evidence", [('if e["類型"] != "決議":', 'if False:')]),
    ("another item's decision as evidence", [('if e["關聯 #"] != num:', 'if False:')]),
    ("a done-word slips into 備註", [('DONE_WORDS = re.compile(r"完成|做完|結案|上線|shipped|done", re.I)',
                                     'DONE_WORDS = re.compile(r"完成|做完|結案", re.I)')]),
    ("a multi-line reason", [('if not why or len(why) > 160 or "\\n" in why or "\\r" in why:',
                              'if not why or len(why) > 160:')]),
    ("too much evidence", [("if len(refs) > MAX_REFS:", "if False:")]),
    ("date formats compared as text", [("if (L.norm_date(new) or new) == (L.norm_date(cur) or cur):", "if new == cur:")]),
    ("a mail too long to read back", [("if len(flat) > MAIL_TEXT_MAX:", "if False:")]),
    ("unmentioned rows approved", [('c[12] = "核准" if n in ok else ("退回" if n in no else "未回覆")',
                                    'c[12] = "退回" if n in no else "核准"')]),
    ("contradiction accepted", [("both = sorted(approve & reject)", "both = []")]),
    ("out-of-range number accepted", [("bad = sorted(x for x in nums if not 1 <= x <= count)", "bad = []")]),
    ("talk beside an approval ignored", [("if talk is not None and (approve or all_ok):", "if False:")]),
    ("a phone line takes any words", [('從我的\\s*[A-Za-z][A-Za-z0-9]*\\s*傳送', '從我的\\s*\\S+\\s*傳送'),
                                      ('sent from my [A-Za-z][A-Za-z0-9]*', 'sent from my \\S+')]),
    ("a question read as an answer", [("if QUESTION.search(t):\n        raise Unreadable", "if False:\n        raise Unreadable")]),
    ("text after the numbers ignored", [("if pos == 0 or not polite(c[pos:], names):", "if pos == 0:")]),
    ("numbers without a keyword skipped", [('if not (KEYWORD.search(c) or re.search(r"\\d", c) or CN_NUM.search(c)):',
                                            "if not KEYWORD.search(c):")]),
    ("the signature read", [('if line == "-- ":', "if False:")]),
    ("any dash line taken for a signature", [('if line == "-- ":', 'if line.strip() in ("--", "—"):')]),
    ("a wrapped zh attribution kept", [("while j > 0 and i - j < 3 and ATTRIB_PART.search(lines[j - 1].strip()):",
                                        "while False:")]),
    ("quoted text parsed", [('body = strip_quote(m["body"])', 'body = m["body"]')]),
    ("a draft read as a reply", [('if int(analysis.get("excluded_drafts") or 0) > 0:', "if False:")]),
    ("a draft note every look", [('if (t - first).total_seconds() >= DRAFT_NOTE_AFTER and not os.path.exists(state_file(run["week"], "draft-noted")):',
                                  "if (t - first).total_seconds() >= DRAFT_NOTE_AFTER:")]),
    ("a sent draft note forgotten", [('write_state(state_file(run["week"], "draft-noted"), L.stamp(L.parse_now(None)))',
                                      "pass")]),
    ("a thread without its analysis", [("if analysis is None:", "if False:")]),
    ("the older reply wins", [("m, body = instr[-1]", "m, body = instr[0]")]),
    ("thanks read as an answer", [('instr = [(m, t) for m, t in replies if has_instruction(t, name_tokens(m["name"]))]',
                                   "instr = list(replies)")]),
    ("anyone's reply counts", [('elif m["from"] == owner:', "else:")]),
    ("restate asked again and again",
     [('if (restates and max(restates) > m["n"]) or key in read_list(state_file(run["week"], "restated.json")):',
       "if False:")]),
    ("asked again when the request left the thread",
     [('if (restates and max(restates) > m["n"]) or key in read_list(state_file(run["week"], "restated.json")):',
       'if restates and max(restates) > m["n"]:')]),
    ("a sent restate forgotten", [('write_state(asked, json.dumps(read_list(asked) + [p["key"]], ensure_ascii=False))',
                                   "pass")]),
    ("a reply with no Message-ID answers nothing", [('in_reply_to=target["msgid"] or ids[-1]', 'in_reply_to=target["msgid"]')]),
    ("applied before the confirmation", [('"write": [{"tab": "Proposals", "rows_path": write_rows(os.path.join(d, "decided-proposals.json"), out)}],',
                                          '"write": [{"tab": "Proposals", "rows_path": write_rows(os.path.join(d, "decided-proposals.json"), out)},'
                                          ' updates_write(d)],')]),
    ("decided twice", [('    if w["applied"] == "ok":\n        return {"status": "ok", "delivered": "already-applied',
                        '    if False:\n        return {"status": "ok", "delivered": "already-applied')]),
    ("a sent confirmation ignored", [("    if confirms:\n        # final:", "    if False:\n        # final:")]),
    ("a confirmation that disagrees accepted",
     [('if ([int(c[2]) for c in rows if c[12] == "核准"], [int(c[2]) for c in rows if c[12] == "退回"]) != (ok, no):',
       "if False:")]),
    ("confirmed without the re-read", [('if look > 1 and run.get("decided") == decision:',
                                        'if run.get("decided") == decision or look == 1:')]),
    ("a write never checked", [('if [list(c[12:15]) for c in written] != run.get("decided_cells"):', "if False:")]),
    ("rechecks without end", [("if look >= MAX_LOOKS:", "if False:")]),
    ("a live run decides", [('if run["mode"] == "live":', "if False:")]),
    ("propose runs live", [('if mode == "live":\n        raise L.Refuse(2, LIVE_REFUSED)\n    run = new_run(cfg, week, "propose"',
                            'if False:\n        raise L.Refuse(2, LIVE_REFUSED)\n    run = new_run(cfg, week, "propose"')]),
    ("apply runs live", [('if mode == "live":\n        raise L.Refuse(2, LIVE_REFUSED)\n    run = new_run(cfg, week, "apply"',
                          'if False:\n        raise L.Refuse(2, LIVE_REFUSED)\n    run = new_run(cfg, week, "apply"')]),
    ("any mode word means live", [('return "live" if raw.get("routine", {}).get("apply_mode") == "live" else "shadow"',
                                   'return "live" if str(raw.get("routine", {}).get("apply_mode", "")).lower() == "live" else "shadow"')]),
    ("subject not checked", [("if subject != want:", "if False:")]),
    ("another thread decided on", [('if tid != run.get("thread_id"):', "if False:")]),
    ("not the mail sent, decided on", [('if sha(sent_flat) != run["mail_sha"]:', "if False:")]),
    ("an edited Proposals block decided on", [('if rows_sha(rows) != run["rows_sha"]:', "if False:")]),
    ("evidence edits stop a recorded thread", [('if run.get("mail_sha") and run.get("rows_sha"):', "if False:")]),
    ("a changed mail decided on", [("if sent_flat != flat_text(render_mail(run, rows)):", "if False:")]),
    ("a changed mail recorded", [('if got != run["mail_flat"]:', "if False:")]),
    ("a stranger thread recorded as ours", [('if subject != run["subject"]:', "if False:")]),
    ("any search text read as a result", [("if not m or m.group(2) != query:", "if not m:")]),
    ("two approval mails: the first one taken", [("    if len(ids) > 1:\n        raise L.Refuse(3, \"%d approval mails",
                                                  "    if False:\n        raise L.Refuse(3, \"%d approval mails")]),
    ("sent twice in a run", [('if run.get("send_instructed"):', "if False:")]),
    ("sent again too soon", [("if os.path.exists(mark) and time.time() - os.path.getmtime(mark) < RESEND_AFTER:",
                              "if False:")]),
    ("a failed send still guards", [("    if os.path.exists(mark):\n        os.remove(mark)",
                                     "    if os.path.exists(mark):\n        pass")]),
    ("a retry re-proposes instead of resuming", [('if not rows or os.path.exists(thread_state_path(run["week"])):', 'if True:')]),
]


def mutate():
    import shutil
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    head, tail = src.split("\nMUTATIONS = [", 1)
    missed = 0
    for name, pairs in MUTATIONS:
        m = head
        for old, new in pairs:
            if m.count(old) != 1:
                print("mutate: %-46s PATTERN FOUND %d TIMES" % (name, m.count(old)))
                missed += 1
                break
            m = m.replace(old, new)
        else:
            d = tempfile.mkdtemp(prefix="proposals-mut-")
            open(os.path.join(d, "proposals.py"), "w", encoding="utf-8").write(m + "\nMUTATIONS = [" + tail)
            shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ledger.py"), d)
            r = subprocess.run([sys.executable, os.path.join(d, "proposals.py"), "--selftest"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            shutil.rmtree(d, ignore_errors=True)
            caught = r.returncode != 0
            print("mutate: %-46s %s" % (name, "caught" if caught else "MISSED"))
            missed += 0 if caught else 1
    print("mutate: %d of %d caught" % (len(MUTATIONS) - missed, len(MUTATIONS)))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
