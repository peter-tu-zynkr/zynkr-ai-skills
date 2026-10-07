#!/usr/bin/env python3
"""beats.py — which zynkr-ops-weekly beat is due now, in Taipei time (SKB-070).

run_ops_weekly.sh calls it on every launchd heartbeat (:05 and :35) and reads back exactly one line:

    beats.py select --state <dir> --config <file> [--mode <beat>] [--now <ISO time with offset>]
    -> <mode>|<ISO week>|<why>

  mode empty      nothing runs this tick; why says so, or names the beat that is held
  mode = a beat   run that beat
  mode = notice   mail the owner about this week's beats that did not run (SKB-070); why lists
                  them as beat:code,beat:code with code gaveup · failed-<n> · never-ran

    beats.py insights --config <file> --week <ISO week>
    -> <status><TAB><dir>   status: off (not configured) · missing · ready (delivered.json and
                            meeting.json are both in <dir>/<week>/)

    beats.py --selftest | --mutate

Until SKB-070 this was a python heredoc inside the runner. It moved here so it can be tested: the beat
table, the Thursday hold for the owner's weekly insights and the missed-beat notices each have
selftest cases, and every one-line breakage listed in MUTATIONS must turn the selftest red. Standard
library only, and Python 3.9 safe: the runner uses whichever python3 comes first on its PATH.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Taipei")
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
HM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
NOTICE_SPACING = 7200      # a failed notice is tried again two hours later at the earliest

# mode, ISO weekday, window open, window close, prerequisite beat. Order matters: the first due beat wins.
# `recap` (SKB-044) comes first: one beat runs per tick and nudge has hung for hours, so the Monday mail
# must not queue behind it. It reads only the Ledger and is limited to 30 minutes.
BEATS = [("recap",     1, "09:00", "20:00", None),
         ("nudge",     1, "09:00", "20:00", None),
         ("rollup",    2, "09:00", "20:00", None),
         ("chase",     2, "09:30", "20:00", "rollup"),
         # `agenda` (SKB-070) runs on the meeting day itself, after the owner's weekly insights closed at
         # Wed 20:00. It waits for that recap until `sources.weekly_insights.wait_until` (13:00), then
         # runs without it. Until 2026-10-14 it ran Wed 17:00-23:00.
         ("agenda",    4, "09:00", "20:00", None),
         ("decisions", 4, "22:00", "23:59", None),
         # `tidy` is Friday because that is the first morning AFTER the Thursday 23:00 scaffold. The
         # scaffold copies the week section forward verbatim, stacked auto blocks and all, so Friday is
         # the moment the duplicates exist and nobody has read them yet.
         ("tidy",      5, "09:00", "20:00", None),
         # `propose` (SKB-044 Phase 3) mails the owner the suggested tracker changes for the week. It
         # comes after tidy, reads the Ledger and the tracker, and writes only the Ledger.
         ("propose",   5, "10:00", "17:30", None),
         # `snapshot` (SKB-044) copies the Main Tracker into the Weekly Ledger once per ISO week.
         # Saturday and Sunday catch up a closed lid on Friday evening. Sunday stops at 23:00 so no run
         # is still going when the ISO week (and with it the rows the Ledger uses) changes at Monday
         # 00:00 Taipei.
         ("snapshot",  5, "18:00", "23:59", None),
         ("snapshot",  6, "00:00", "23:59", None),
         ("snapshot",  7, "00:00", "23:00", None),
         # `apply` records the owner's reply to that mail. Listed after snapshot so the week is captured
         # first. No prerequisite: it reads this week's Ledger row itself, so a propose that recorded and
         # mailed but then gave up still has its answer read.
         ("apply",     5, "18:00", "23:59", None),
         ("apply",     6, "00:00", "23:59", None),
         ("apply",     7, "00:00", "23:00", None)]
MODES = list(dict.fromkeys(row[0] for row in BEATS))


def stamp(state, week, mode, kind):
    return os.path.join(state, "%s.%s.%s" % (week, mode, kind))


def has(state, week, mode, kind):
    return os.path.exists(stamp(state, week, mode, kind))


def waiting(state, week, mode, now):
    """`apply` waits for the owner to answer the approval mail. A waiting receipt stamps nothing, so
    without this the beat would start Claude every 30 minutes all weekend; it looks again 2 hours after
    the stamp was last written (its mtime). The mail promises that a reply before Sunday 22:00 counts,
    so from Sunday 21:00 every tick looks: the last looks are 22:05 and 22:35, before 23:00."""
    p = stamp(state, week, mode, "waiting")
    if not os.path.exists(p) or (now.isoweekday() == 7 and now.strftime("%H:%M") >= "21:00"):
        return False
    return now.timestamp() - os.path.getmtime(p) < 7200


def insights_cfg(cfg):
    """The owner's weekly-insights folder and how long `agenda` waits for it, or None when not set.
    Raises ValueError when it is set to something that is not a folder: `~/…`, `$HOME/…` and absolute
    paths are folders; a relative path would point somewhere new on every run."""
    src = (cfg.get("sources") or {}).get("weekly_insights") if isinstance(cfg.get("sources"), dict) else None
    if not isinstance(src, dict):
        return None
    folder = src.get("dir")
    if folder is None or (isinstance(folder, str) and not folder.strip()):
        return None
    if not isinstance(folder, str):
        raise ValueError("sources.weekly_insights.dir is not a path")
    path = os.path.normpath(os.path.expandvars(os.path.expanduser(folder.strip())))
    if not os.path.isabs(path):
        raise ValueError("sources.weekly_insights.dir must be absolute or start with ~ (it reads %r)" % folder)
    until = src.get("wait_until")
    if not (isinstance(until, str) and HM_RE.match(until)):
        until = "13:00"
    return {"dir": path, "wait_until": until}


def wb_label(week):
    """The week as the team reads it: `WB m/d`, the Monday that opens the ISO week."""
    monday = dt.date.fromisocalendar(int(week[:4]), int(week[6:]), 1)
    return "WB %d/%d" % (monday.month, monday.day)


def insights_hold(mode, week, hm, cfg):
    """Why `agenda` should wait this tick, or None. Waiting starts no Claude run: it costs nothing."""
    if mode != "agenda":
        return None
    try:
        wi = insights_cfg(cfg)
    except ValueError:
        return None                               # a broken setting never holds the agenda back
    if not wi:
        return None
    until = wi["wait_until"]
    if hm >= until:
        return None
    if os.path.exists(os.path.join(wi["dir"], week, "delivered.json")):
        return None
    return "agenda held: weekly insights for %s not delivered yet, waits until %s" % (week, until)


def last_close(mode, year, weeknum):
    """The first minute after the beat's last window of that ISO week (windows include their last minute)."""
    day, end = max((d, e) for m, d, _s, e, _r in BEATS if m == mode)
    hh, mm = (int(x) for x in end.split(":"))
    at = dt.datetime.combine(dt.date.fromisocalendar(year, weeknum, day), dt.time(hh, mm), TZ)
    return at + dt.timedelta(minutes=1)


def prerequisite(mode):
    return next((r for m, _d, _s, _e, r in BEATS if m == mode and r), None)


def attempts(state, week, mode):
    try:
        with open(stamp(state, week, mode, "attempts")) as f:
            return int(f.read().strip() or 0)
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        return 1


def missed(now, state, week):
    """Beats of `week` that did not run and nobody has been told about, as (mode, code) pairs."""
    year, weeknum = int(week[:4]), int(week[6:])
    out = []
    for mode in MODES:
        if has(state, week, mode, "done") or has(state, week, mode, "noticed"):
            continue
        if has(state, week, mode, "gaveup"):
            out.append((mode, "gaveup"))          # final: say so now, not when the window closes
            continue
        if now < last_close(mode, year, weeknum):
            continue                              # its window is still open, or not reached yet
        req = prerequisite(mode)
        if req and not has(state, week, req, "done"):
            continue                              # one cause, one line: the prerequisite is reported
        if mode == "apply" and has(state, week, mode, "waiting"):
            continue                              # the owner has not replied; that is not a failure
        n = attempts(state, week, mode)
        out.append((mode, "failed-%d" % n if n else "never-ran"))
    return out


def notices(now, state, cfg):
    """(week, [(mode, code), ...]) for the first week, this one then the last, with beats to report."""
    routine = cfg.get("routine") if isinstance(cfg.get("routine"), dict) else {}
    since = routine.get("notice_from")
    if not (isinstance(since, str) and WEEK_RE.match(since)):
        return None                               # not configured, or not a week: notices are off
    for t in (now, now - dt.timedelta(days=7)):
        y, w, _ = t.isocalendar()
        week = "%d-W%02d" % (y, w)
        if week < since:
            continue
        p = os.path.join(state, "%s.notice.attempts" % week)
        if os.path.exists(p) and now.timestamp() - os.path.getmtime(p) < NOTICE_SPACING:
            continue
        found = missed(now, state, week)
        if found:
            return week, found
    return None


def select(now, state, cfg, force=""):
    y, w, dow = now.isocalendar()
    week = "%d-W%02d" % (y, w)
    if force:
        return "%s|%s|forced (--mode)" % (force, week)
    hm = now.strftime("%H:%M")

    def done(m):
        return has(state, week, m, "done")

    # Settled = succeeded OR exhausted its retries, so a broken beat stops being selected. The
    # prerequisite check accepts ONLY a real .done: `chase` must never run off the back of a `rollup`
    # that gave up, or it will name people whose posts were never parsed at all.
    def settled(m):
        return done(m) or has(state, week, m, "gaveup")

    def notice_line():
        found = notices(now, state, cfg)
        return "notice|%s|%s" % (found[0], ",".join("%s:%s" % pair for pair in found[1])) if found else None

    for mode, d, s, e, req in BEATS:
        if dow != d or not (s <= hm <= e) or settled(mode) or waiting(state, week, mode, now):
            continue
        if req and not done(req):
            held = "%s held: %s has not run this week" % (mode, req)
        else:
            held = insights_hold(mode, week, hm, cfg)
        if held:
            # A held beat runs nothing this tick, so a missed-beat notice may: a rollup that gave up at
            # 09:30 must not wait for chase's window to close at 20:00 before anyone hears of it.
            return notice_line() or "|%s|%s" % (week, held)
        return "%s|%s|%s Taipei, window %s-%s" % (mode, week, now.strftime("%a %H:%M"), s, e)
    return notice_line() or "|%s|nothing due at %s Taipei" % (week, now.strftime("%a %H:%M"))


def insights(cfg, week):
    wi = insights_cfg(cfg)
    if not wi:
        return "off\t"
    base = os.path.join(wi["dir"], week)
    ready = os.path.exists(os.path.join(base, "delivered.json")) and os.path.exists(os.path.join(base, "meeting.json"))
    return "%s\t%s" % ("ready" if ready else "missing", wi["dir"])


def load_cfg(path, strict=False):
    """The config as a dict. For `select` an unreadable config only switches the insights hold and
    the notices off: the beats themselves fail loud on it. For `insights` (strict) it is an error,
    because the runner exports the private folder from that answer, and a guess of "off" would leave
    the folder unguarded."""
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("the config is not a JSON object")
    except Exception as e:  # noqa: BLE001
        if strict:
            raise SystemExit("beats.py: config unreadable (%s: %s)" % (type(e).__name__, e))
        print("beats.py: config unreadable (%s); the insights hold and notices are off" % type(e).__name__,
              file=sys.stderr)
        return {}
    return cfg


def parse_now(text):
    if not text:
        return dt.datetime.now(TZ)
    t = dt.datetime.fromisoformat(text)
    if t.tzinfo is None:
        raise SystemExit("beats.py: --now needs a UTC offset, e.g. 2026-10-15T09:05:00+08:00")
    return t.astimezone(TZ)


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--mutate" in argv:
        return mutate()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("select")
    s.add_argument("--state", required=True)
    s.add_argument("--config", required=True)
    s.add_argument("--mode", default="")
    s.add_argument("--now", default="")
    i = sub.add_parser("insights")
    i.add_argument("--config", required=True)
    i.add_argument("--week", required=True)
    lb = sub.add_parser("label")
    lb.add_argument("--week", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "select":
        print(select(parse_now(a.now), a.state, load_cfg(a.config), a.mode))
        return 0
    if a.cmd in ("insights", "label") and not WEEK_RE.match(a.week):
        raise SystemExit("beats.py: --week must look like 2026-W42")
    if a.cmd == "insights":
        try:
            print(insights(load_cfg(a.config, strict=True), a.week))
        except ValueError as e:
            raise SystemExit("beats.py: %s" % e)
        return 0
    if a.cmd == "label":
        print(wb_label(a.week))
        return 0
    ap.print_usage(sys.stderr)
    return 2


# ── selftest ─────────────────────────────────────────────────────────────────
def selftest():
    import shutil
    import tempfile
    fails = []
    tmp = tempfile.mkdtemp(prefix="beats-selftest-")

    def at(day, hm):                       # 2026-W42: Mon 12 Oct .. Sun 18 Oct 2026
        h, m = (int(x) for x in hm.split(":"))
        return dt.datetime(2026, 10, 11 + day, h, m, tzinfo=TZ)

    def fresh(*stamps, cfg=None, insights_ready=False, mtimes=None):
        state = tempfile.mkdtemp(dir=tmp)
        for name in stamps:
            week, mode, kind = name.split(".", 2) if name.count(".") >= 2 else ("2026-W42",) + tuple(name.split("."))
            content = "2" if kind == "attempts" else "x"
            with open(os.path.join(state, "%s.%s.%s" % (week, mode, kind)), "w") as f:
                f.write(content)
        for name, age in (mtimes or {}).items():
            p = os.path.join(state, name)
            t = at(*age[0]).timestamp() - age[1]
            os.utime(p, (t, t))
        c = dict(cfg or {})
        if insights_ready is not None and "sources" in c:
            folder = c["sources"]["weekly_insights"]["dir"]
            week_dir = os.path.join(folder, "2026-W42")
            shutil.rmtree(folder, ignore_errors=True)
            if insights_ready:
                os.makedirs(week_dir)
                for f in ("delivered.json", "meeting.json"):
                    open(os.path.join(week_dir, f), "w").write("{}")
        return state, c

    wi_dir = os.path.join(tmp, "weekly-insights")
    WI = {"sources": {"weekly_insights": {"dir": wi_dir, "wait_until": "13:00"}}}
    NO = {"routine": {"notice_from": "2026-W42"}}
    MON_DONE = ["recap.done", "nudge.done"]
    TUE_DONE = MON_DONE + ["rollup.done", "chase.done"]
    THU_DONE = TUE_DONE + ["agenda.done"]

    def check(name, now, want, stamps=(), cfg=None, force="", insights_ready=None, mtimes=None):
        state, c = fresh(*stamps, cfg=cfg, insights_ready=insights_ready, mtimes=mtimes)
        got = select(now, state, c, force)
        if got != want:
            fails.append("%s\n      got  %s\n      want %s" % (name, got, want))

    # the beats, exactly as the old runner chose them
    check("Monday 09:05: recap first", at(1, "09:05"), "recap|2026-W42|Mon 09:05 Taipei, window 09:00-20:00")
    check("Monday: nudge after recap", at(1, "09:05"), "nudge|2026-W42|Mon 09:05 Taipei, window 09:00-20:00",
          ["recap.done"])
    check("Tuesday 09:35: rollup before chase", at(2, "09:35"), "rollup|2026-W42|Tue 09:35 Taipei, window 09:00-20:00",
          MON_DONE)
    check("chase held when rollup gave up", at(2, "09:35"), "|2026-W42|chase held: rollup has not run this week",
          MON_DONE + ["rollup.gaveup"])
    check("chase after rollup", at(2, "10:05"), "chase|2026-W42|Tue 10:05 Taipei, window 09:30-20:00",
          MON_DONE + ["rollup.done"])
    check("Wednesday 17:05: agenda no longer runs", at(3, "17:05"), "|2026-W42|nothing due at Wed 17:05 Taipei",
          TUE_DONE)
    check("Thursday 09:05: agenda without insights configured", at(4, "09:05"),
          "agenda|2026-W42|Thu 09:05 Taipei, window 09:00-20:00", TUE_DONE)
    check("agenda waits for the insights", at(4, "09:05"),
          "|2026-W42|agenda held: weekly insights for 2026-W42 not delivered yet, waits until 13:00",
          TUE_DONE, cfg=WI, insights_ready=False)
    check("agenda runs once they arrive", at(4, "09:35"), "agenda|2026-W42|Thu 09:35 Taipei, window 09:00-20:00",
          TUE_DONE, cfg=WI, insights_ready=True)
    check("agenda stops waiting at 13:00", at(4, "13:05"), "agenda|2026-W42|Thu 13:05 Taipei, window 09:00-20:00",
          TUE_DONE, cfg=WI, insights_ready=False)
    check("decisions on Thursday night", at(4, "22:05"), "decisions|2026-W42|Thu 22:05 Taipei, window 22:00-23:59",
          THU_DONE)
    check("tidy before propose", at(5, "10:05"), "tidy|2026-W42|Fri 10:05 Taipei, window 09:00-20:00",
          THU_DONE + ["decisions.done"])
    check("propose after tidy", at(5, "10:05"), "propose|2026-W42|Fri 10:05 Taipei, window 10:00-17:30",
          THU_DONE + ["decisions.done", "tidy.done"])
    check("snapshot before apply", at(5, "18:05"), "snapshot|2026-W42|Fri 18:05 Taipei, window 18:00-23:59",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done"])
    check("apply after snapshot", at(6, "10:05"), "apply|2026-W42|Sat 10:05 Taipei, window 00:00-23:59",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done"])
    check("apply waits two hours", at(6, "10:05"), "|2026-W42|nothing due at Sat 10:05 Taipei",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done", "apply.waiting"],
          mtimes={"2026-W42.apply.waiting": ((6, "10:05"), 1800)})
    check("apply looks again after two hours", at(6, "12:35"), "apply|2026-W42|Sat 12:35 Taipei, window 00:00-23:59",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done", "apply.waiting"],
          mtimes={"2026-W42.apply.waiting": ((6, "12:35"), 9000)})
    check("from Sunday 21:00 apply looks every tick", at(7, "21:05"), "apply|2026-W42|Sun 21:05 Taipei, window 00:00-23:00",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done", "apply.waiting"],
          mtimes={"2026-W42.apply.waiting": ((7, "21:05"), 600)})
    check("a forced mode skips every check", at(3, "03:00"), "status|2026-W42|forced (--mode)", force="status")
    check("a window includes its last minute", at(4, "23:59"), "decisions|2026-W42|Thu 23:59 Taipei, window 22:00-23:59",
          THU_DONE)

    # notices: only from notice_from on, once per beat, after the last window closes
    check("notices are off without notice_from", at(4, "20:05"), "|2026-W42|nothing due at Thu 20:05 Taipei",
          TUE_DONE + ["agenda.gaveup"])
    check("a gave-up beat is reported at once", at(4, "14:05"), "notice|2026-W42|agenda:gaveup",
          TUE_DONE + ["agenda.gaveup"], cfg=NO)
    check("a failed beat waits for its window to close", at(4, "19:35"),
          "agenda|2026-W42|Thu 19:35 Taipei, window 09:00-20:00", TUE_DONE + ["agenda.attempts"], cfg=NO)
    check("then it is reported with its attempts", at(4, "20:05"), "notice|2026-W42|agenda:failed-2",
          TUE_DONE + ["agenda.attempts"], cfg=NO)
    check("a beat that never ran", at(2, "20:05"), "notice|2026-W42|rollup:never-ran",
          MON_DONE, cfg=NO)
    check("every missed beat of the week in one notice", at(2, "20:05"), "notice|2026-W42|recap:never-ran,nudge:never-ran,rollup:never-ran",
          [], cfg=NO)
    check("a noticed beat is not reported again", at(4, "20:05"), "|2026-W42|nothing due at Thu 20:05 Taipei",
          TUE_DONE + ["agenda.gaveup", "agenda.noticed"], cfg=NO)
    check("snapshot's last window is Sunday", at(6, "00:05"), "snapshot|2026-W42|Sat 00:05 Taipei, window 00:00-23:59",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done"], cfg=NO)
    check("snapshot is reported after Sunday 23:00", at(7, "23:05"), "notice|2026-W42|snapshot:never-ran",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "apply.done"], cfg=NO)
    check("apply still waiting on the owner is no failure", at(7, "23:35"), "|2026-W42|nothing due at Sun 23:35 Taipei",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done", "apply.waiting"], cfg=NO)
    check("on Monday the last week is checked", at(8, "00:05"), "notice|2026-W42|apply:never-ran",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done"], cfg=NO)
    check("weeks before notice_from are not reported", at(8, "00:05"), "|2026-W43|nothing due at Mon 00:05 Taipei",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done"],
          cfg={"routine": {"notice_from": "2026-W43"}})
    check("a notice_from that is not a week turns notices off", at(4, "14:05"), "|2026-W42|nothing due at Thu 14:05 Taipei",
          TUE_DONE + ["agenda.gaveup"], cfg={"routine": {"notice_from": "W42"}})
    check("a failed notice waits two hours", at(4, "14:35"), "|2026-W42|nothing due at Thu 14:35 Taipei",
          TUE_DONE + ["agenda.gaveup", "2026-W42.notice.attempts"], cfg=NO,
          mtimes={"2026-W42.notice.attempts": ((4, "14:35"), 1800)})
    check("then it is tried again", at(4, "16:35"), "notice|2026-W42|agenda:gaveup",
          TUE_DONE + ["agenda.gaveup", "2026-W42.notice.attempts"], cfg=NO,
          mtimes={"2026-W42.notice.attempts": ((4, "16:35"), 7300)})
    check("a held chase is not reported twice", at(2, "20:05"), "notice|2026-W42|rollup:gaveup",
          MON_DONE + ["rollup.gaveup"], cfg=NO)
    check("a notice goes out while chase is held", at(2, "10:05"), "notice|2026-W42|rollup:gaveup",
          MON_DONE + ["rollup.gaveup"], cfg=NO)
    check("and while agenda waits for the insights", at(4, "09:35"), "notice|2026-W41|apply:never-ran",
          TUE_DONE + ["2026-W41.recap.done", "2026-W41.nudge.done", "2026-W41.rollup.done", "2026-W41.chase.done",
                      "2026-W41.agenda.done", "2026-W41.decisions.done", "2026-W41.tidy.done", "2026-W41.propose.done",
                      "2026-W41.snapshot.done"],
          cfg={"routine": {"notice_from": "2026-W41"}, **WI}, insights_ready=False)
    check("a due beat goes before a notice", at(5, "09:05"), "tidy|2026-W42|Fri 09:05 Taipei, window 09:00-20:00",
          TUE_DONE + ["agenda.gaveup"], cfg=NO)
    check("a finished week has nothing to report", at(5, "20:05"), "|2026-W42|nothing due at Fri 20:05 Taipei",
          THU_DONE + ["decisions.done", "tidy.done", "propose.done", "snapshot.done", "apply.done"], cfg=NO)
    # A beat with several windows is reported only after its last one; select() cannot show it, because
    # snapshot and apply are due in every tick of their windows, so check the boundary itself.
    for mode, want in (("snapshot", dt.datetime(2026, 10, 18, 23, 1, tzinfo=TZ)),
                       ("decisions", dt.datetime(2026, 10, 16, 0, 0, tzinfo=TZ))):
        if last_close(mode, 2026, 42) != want:
            fails.append("last_close(%s) = %s, want %s" % (mode, last_close(mode, 2026, 42), want))

    # the insights status the runner reads before agenda
    _, c = fresh(cfg=WI, insights_ready=True)
    got = insights(c, "2026-W42")
    if got != "ready\t" + wi_dir:
        fails.append("insights ready: got %r" % got)
    os.remove(os.path.join(wi_dir, "2026-W42", "meeting.json"))
    if insights(c, "2026-W42") != "missing\t" + wi_dir:
        fails.append("insights without meeting.json must be missing")
    if insights({}, "2026-W42") != "off\t":
        fails.append("insights without config must be off")
    try:
        parse_now("2026-10-15T09:05:00")
        fails.append("a --now without an offset was accepted")
    except SystemExit:
        pass
    broken = os.path.join(tmp, "broken.json")
    with open(broken, "w") as f:
        f.write('{"sources": ')
    try:
        load_cfg(broken, strict=True)
        fails.append("insights read a broken config as 'off', which would leave the private folder unguarded")
    except SystemExit:
        pass
    import contextlib
    import io
    with contextlib.redirect_stderr(io.StringIO()):
        if load_cfg(broken) != {}:
            fails.append("select must read a broken config as {} and keep the beats running")
    for bad in ("weekly-insights", "./x", 7):
        try:
            insights_cfg({"sources": {"weekly_insights": {"dir": bad}}})
            fails.append("a weekly_insights.dir of %r was accepted" % (bad,))
        except ValueError:
            pass
        if insights_hold("agenda", "2026-W42", "09:05", {"sources": {"weekly_insights": {"dir": bad}}}) is not None:
            fails.append("a broken weekly_insights.dir held the agenda")
    wi_home = insights_cfg({"sources": {"weekly_insights": {"dir": "$HOME/.claude/weekly-insights"}}})
    if not (wi_home and os.path.isabs(wi_home["dir"]) and "$" not in wi_home["dir"]):
        fails.append("$HOME in weekly_insights.dir was not expanded: %r" % (wi_home,))
    for week, want in (("2026-W42", "WB 10/12"), ("2027-W01", "WB 1/4"), ("2026-W53", "WB 12/28")):
        if wb_label(week) != want:
            fails.append("wb_label(%s) = %s, want %s" % (week, wb_label(week), want))

    shutil.rmtree(tmp, ignore_errors=True)
    for f in fails:
        print("FAIL " + f)
    print("beats.py selftest: %s" % ("%d FAILED" % len(fails) if fails else "all checks passed"))
    return 1 if fails else 0


# ── mutation check: each one-line breakage must turn the selftest red ────────
MUTATIONS = [
    # (name, [(old, new), ...]) — every pair is applied; each old text must occur exactly once
    ("agenda back on Wednesday", [
        ('("agenda",    4, "09:00", "20:00", None)', '("agenda",    3, "17:00", "23:00", None)')]),
    ("hold ignores delivered.json", [
        ('if os.path.exists(os.path.join(wi["dir"], week, "delivered.json")):', "if False:")]),
    ("hold never ends", [
        ("    if hm >= until:\n        return None", "    if False:\n        return None")]),
    ("prerequisite ignored", [
        ("        if req and not done(req):", "        if False:")]),
    ("a gave-up beat is selected again", [
        ('return done(m) or has(state, week, m, "gaveup")', "return done(m)")]),
    ("waiting ignored", [
        ("or settled(mode) or waiting(state, week, mode, now):", "or settled(mode):")]),
    ("Sunday 21:00 rule removed", [
        ('(now.isoweekday() == 7 and now.strftime("%H:%M") >= "21:00")', "False")]),
    ("notice before the window closes", [
        ("        if now < last_close(mode, year, weeknum):", "        if False:")]),
    ("notice_from ignored", [
        ("        if week < since:", "        if False:")]),
    ("apply reported while the owner thinks", [
        ('if mode == "apply" and has(state, week, mode, "waiting"):', "if False:")]),
    ("a held beat reported twice", [
        ('if req and not has(state, week, req, "done"):', "if False:")]),
    ("no spacing between notices", [
        ("now.timestamp() - os.path.getmtime(p) < NOTICE_SPACING:", "False:")]),
    ("last week not checked", [
        ("for t in (now, now - dt.timedelta(days=7)):", "for t in (now,):")]),
    ("noticed beats reported again", [
        ('if has(state, week, mode, "done") or has(state, week, mode, "noticed"):',
         'if has(state, week, mode, "done"):')]),
    ("the first window counts as the last", [
        ("day, end = max((d, e) for m, d, _s, e, _r in BEATS if m == mode)",
         "day, end = min((d, e) for m, d, _s, e, _r in BEATS if m == mode)")]),
    ("a gave-up beat waits for its window", [
        ('            out.append((mode, "gaveup"))          # final: say so now, not when the window closes\n            continue',
         "            pass")]),
    ("window excludes its last minute", [
        ("return at + dt.timedelta(minutes=1)", "return at")]),
    ("--now without an offset accepted", [
        ("    if t.tzinfo is None:\n", "    if False:\n")]),
    ("insights ready without meeting.json", [
        (' and os.path.exists(os.path.join(base, "meeting.json"))', "")]),
    ("a hold hides notices", [
        ('            return notice_line() or "|%s|%s" % (week, held)', '            return "|%s|%s" % (week, held)')]),
    ("insights fails open on a broken config", [
        ("        if strict:\n            raise SystemExit(", "        if False:\n            raise SystemExit(")]),
    ("a relative folder accepted", [
        ("    if not os.path.isabs(path):\n        raise ValueError(", "    if False:\n        raise ValueError(")]),
    ("$HOME not expanded", [
        ("path = os.path.normpath(os.path.expandvars(os.path.expanduser(folder.strip())))",
         "path = os.path.normpath(os.path.expanduser(folder.strip()))")]),
    ("the WB label is the Sunday", [
        ("monday = dt.date.fromisocalendar(int(week[:4]), int(week[6:]), 1)",
         "monday = dt.date.fromisocalendar(int(week[:4]), int(week[6:]), 7)")]),
    ("a broken folder holds the agenda", [
        ("    except ValueError:\n        return None                               # a broken setting",
         "    except ValueError:\n        return \"held\"                               # a broken setting")]),
]


def mutate():
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")   # never mutate the list itself
    tmpd = tempfile.mkdtemp(prefix="beats-mutate-")
    ok = True

    def run(text):
        p = os.path.join(tmpd, "beats_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    for name, pairs in MUTATIONS:
        bad = [old for old, _ in pairs if code.count(old) != 1]
        if bad:
            print("mutate: %-38s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = code
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        rc = run(mutated + marker + rest)
        print("mutate: %-38s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
