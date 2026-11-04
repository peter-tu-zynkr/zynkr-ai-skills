#!/usr/bin/env python3
"""notes_append.py — appends one dated line to one 備註 cell of the Main Tracker and keeps its links
(SKB-091 AC-17; decision A, the owner, 2026-10-25).

Seven 備註 cells hold rich-text links, and any values write (modify_sheet_values) deletes them. So 備註 is
the one write that goes through the raw Sheets API: this script reads the cell with its text-format
runs, refuses unless the text is exactly what `proposals.py live-plan` saw, writes the old text plus
one line with every old run kept and a plain run for the new line, and reads the cell back.

    notes_append.py --job JOB.json      the job live-plan wrote: spreadsheet_id, tab, cell (column M),
                                        expect, line, account, config
    notes_append.py --selftest | --mutate

It runs only inside the apply beat (ZYNKR_OPS_WEEKLY_MODE=apply, which the runner exports). The tracker
guard allows exactly this command there and refuses it in every other beat.

Credentials: the authorized-user OAuth file the Google Workspace MCP server keeps for the account
(refresh_token, client_id, client_secret, token_uri), at `routine.sheets_credentials` in the config,
else ~/.google_workspace_mcp/credentials/<account>.json. Nothing from it is ever printed.

Exit codes: 0 written and read back · 2 setup (mode, job, credentials) · 3 the cell is not what the plan
saw (edited by hand, a formula, a number, an emoji) · 6 the write or its read-back failed.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://sheets.googleapis.com/v4/spreadsheets/"
TOKEN_URI = "https://oauth2.googleapis.com/token"
CELL_RE = re.compile(r"^M(\d+)$")              # 備註 is column M, and nothing else is written here
FIELDS = "sheets(properties(sheetId,title),data(rowData(values(userEnteredValue,textFormatRuns))))"


class Refuse(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class CannotAppend(Refuse):
    """Exit 3 for a cell that can never take a line as it is (a formula, a number, an emoji), as opposed
    to one edited since the plan: the next look must skip it, not plan it again."""


def quote_tab(tab):
    return "'%s'" % tab.replace("'", "''")


def parse_cell(grid):
    """(sheetId, text, runs) of the one cell a spreadsheets.get with grid data returned."""
    sheets = grid.get("sheets") or []
    if len(sheets) != 1:
        raise Refuse(3, "the read returned %d tabs, not one" % len(sheets))
    sid = sheets[0]["properties"]["sheetId"]
    rows = ((sheets[0].get("data") or [{}])[0].get("rowData")) or [{}]
    values = rows[0].get("values") or [{}]
    v = values[0] if values else {}
    uev = v.get("userEnteredValue") or {}
    other = sorted(set(uev) - {"stringValue"})       # formulaValue, numberValue, boolValue …
    if other:
        raise CannotAppend(3, "the cell holds a %s, not plain text; a line cannot be appended to it" % other[0])
    return sid, uev.get("stringValue", ""), v.get("textFormatRuns") or []


def appended(text, runs, line):
    """The new text and runs: every old run as it was, then a plain run for the new line."""
    if len(text.encode("utf-16-le")) // 2 != len(text):
        raise CannotAppend(3, "the cell holds a character outside the basic plane (an emoji), so run offsets "
                        "are ambiguous; append this line by hand")
    if not line.strip() or "\n" in line or "\r" in line:
        raise Refuse(2, "the job's line must be one non-empty line")
    new = text + "\n" + line if text else line
    out = [dict(r) for r in runs]
    if out:
        # a run lasts until the next one starts: without its own run the new line would take the last
        # run's format, its link included
        out.append({"startIndex": len(text) + 1, "format": {}})
    return new, out


def links(runs):
    return sorted({((r.get("format") or {}).get("link") or {}).get("uri") for r in runs} - {None})


def request(sid, row, text, runs):
    cell = {"userEnteredValue": {"stringValue": text}, "textFormatRuns": runs}
    return {"requests": [{"updateCells": {"rows": [{"values": [cell]}], "fields": "userEnteredValue,textFormatRuns",
                                          "start": {"sheetId": sid, "rowIndex": row - 1, "columnIndex": 12}}}]}


def leave_marker(job, e):
    """Where live-plan's next look finds it (the job's refused_path): the cell, the text it held and the
    line, so that look skips the line and names why while the cell is unchanged (SKB-091 review, 10-31)."""
    p = job.get("refused_path")
    if not p:
        return
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"cell": job["cell"], "expect": job["expect"], "line": job["line"], "why": str(e)}, f,
                  ensure_ascii=False)
    os.replace(tmp, p)


def run_job(job, fetch, post):
    """The whole append, with the two network calls passed in: fetch(range) -> grid, post(body). A cell
    that can never take the line leaves a marker for the next look, then refuses (exit 3)."""
    try:
        return append_job(job, fetch, post)
    except CannotAppend as e:
        try:
            leave_marker(job, e)
        except OSError as w:
            print("notes_append.py: the refusal could not be written down (%s)" % w, file=sys.stderr)
        raise


def append_job(job, fetch, post):
    for k in ("spreadsheet_id", "tab", "cell", "expect", "line"):
        if not isinstance(job.get(k), str):
            raise Refuse(2, "the job has no %s" % k)
    m = CELL_RE.match(job["cell"])
    if not m or int(m.group(1)) < 2:
        raise Refuse(2, "only a 備註 cell (column M, below the header) is appended to, not %r" % job["cell"])
    rng = "%s!%s" % (quote_tab(job["tab"]), job["cell"])
    sid, text, runs = parse_cell(fetch(rng))
    if text != job["expect"]:
        raise Refuse(3, "%s changed since the plan (%d characters now, %d planned on): edited by hand, so it is "
                        "skipped" % (job["cell"], len(text), len(job["expect"])))
    new, new_runs = appended(text, runs, job["line"])
    post(request(sid, int(m.group(1)), new, new_runs))
    _, got, got_runs = parse_cell(fetch(rng))
    if got != new:
        raise Refuse(6, "%s reads back differently after the write" % job["cell"])
    lost = [u for u in links(runs) if u not in links(got_runs)]
    if lost:
        raise Refuse(6, "%s lost %d link(s) in the write; restore it from Version history" % (job["cell"], len(lost)))
    return {"ok": True, "cell": job["cell"], "links_kept": len(links(runs))}


# ── the network, used only outside the selftest ─────────────────────────────
def http(url, token=None, body=None, form=None):
    data, headers = None, {}
    if form is not None:
        data, headers["Content-Type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    elif body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        what = "the token refresh" if form is not None else "the Sheets API"
        raise Refuse(2 if form is not None else 6, "%s returned HTTP %d" % (what, e.code))
    except urllib.error.URLError as e:
        raise Refuse(6, "the network failed: %s" % e.reason)


def access_token(job):
    path = None
    if job.get("config"):
        try:
            path = (json.load(open(os.path.expanduser(job["config"]), encoding="utf-8")).get("routine") or {}).get(
                "sheets_credentials")
        except (OSError, ValueError):
            raise Refuse(2, "the config named in the job cannot be read")
    path = os.path.expanduser(path or "~/.google_workspace_mcp/credentials/%s.json" % job.get("account", ""))
    try:
        cred = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        raise Refuse(2, "no readable credentials at %s; set routine.sheets_credentials" % path)
    need = [k for k in ("refresh_token", "client_id", "client_secret") if not cred.get(k)]
    if need:
        raise Refuse(2, "the credentials file has no %s" % ", ".join(need))
    got = http(cred.get("token_uri") or TOKEN_URI, form={"grant_type": "refresh_token", "refresh_token": cred["refresh_token"],
                                                         "client_id": cred["client_id"], "client_secret": cred["client_secret"]})
    if not got.get("access_token"):
        raise Refuse(2, "the token refresh returned no access token")
    return got["access_token"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--job")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return mutate()
    try:
        if os.environ.get("ZYNKR_OPS_WEEKLY_MODE") != "apply":
            raise Refuse(2, "notes_append.py writes the Main Tracker, which only the apply beat may do")
        if not a.job:
            raise Refuse(2, "--job is required")
        try:
            job = json.load(open(a.job, encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refuse(2, "cannot read the job (%s)" % e)
        token = access_token(job)
        sheet = API + urllib.parse.quote(job.get("spreadsheet_id", ""), safe="")
        out = run_job(job,
                      lambda rng: http(sheet + "?" + urllib.parse.urlencode(
                          {"ranges": rng, "includeGridData": "true", "fields": FIELDS}), token),
                      lambda body: http(sheet + ":batchUpdate", token, body=body))
        print(json.dumps(out, ensure_ascii=False))
        return 0
    except Refuse as e:
        print("notes_append.py: %s" % e, file=sys.stderr)
        return e.code


# ── selftest ─────────────────────────────────────────────────────────────────
def selftest():
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (name, got, want))

    def refuses(name, code, fn):
        try:
            fn()
            fails.append("%s: did not refuse" % name)
        except Refuse as e:
            if e.code != code:
                fails.append("%s: refused with %d (%s), want %d" % (name, e.code, e, code))

    def grid(value, runs=None, sid=7):
        v = {"userEnteredValue": value} if value is not None else {}
        if runs:
            v["textFormatRuns"] = runs
        return {"sheets": [{"properties": {"sheetId": sid, "title": "H2"}, "data": [{"rowData": [{"values": [v]}]}]}]}

    LINK = {"startIndex": 0, "format": {"link": {"uri": "https://example.com/a"}}}
    PLAIN = {"startIndex": 4, "format": {}}
    text = "看文件 說明"

    class Sheet:
        """A one-cell fake of the API: posts land in it, and the next fetch returns them."""
        def __init__(self, value, runs=None, drop_runs=False, mangle=False):
            self.value, self.runs, self.drop, self.mangle, self.posts = value, runs or [], drop_runs, mangle, []

        def fetch(self, rng):
            self.ranges = getattr(self, "ranges", []) + [rng]
            return grid(self.value, self.runs)

        def post(self, body):
            self.posts.append(body)
            cell = body["requests"][0]["updateCells"]["rows"][0]["values"][0]
            self.value = {"stringValue": cell["userEnteredValue"]["stringValue"] + " "} if self.mangle \
                else cell["userEnteredValue"]
            self.runs = [] if self.drop else cell["textFormatRuns"]

    job = {"spreadsheet_id": "TRK", "tab": "H2 項目", "cell": "M16", "expect": text, "line": "10/22 會議：改到下週"}
    s = Sheet({"stringValue": text}, [LINK, PLAIN])
    out = run_job(job, s.fetch, s.post)
    check("the line is appended under the old text", s.value, {"stringValue": text + "\n10/22 會議：改到下週"})
    check("every old run is kept, and the new line gets a plain run of its own",
          s.runs, [LINK, PLAIN, {"startIndex": len(text) + 1, "format": {}}])
    check("the report", out, {"ok": True, "cell": "M16", "links_kept": 1})
    up = s.posts[0]["requests"][0]["updateCells"]
    check("one cell, column M, its row, on the tab's own sheet id",
          (up["start"], up["fields"]), ({"sheetId": 7, "rowIndex": 15, "columnIndex": 12}, "userEnteredValue,textFormatRuns"))
    check("the range is quoted for a tab name with a space", s.ranges[0], "'H2 項目'!M16")
    check("read back after the write", len(s.ranges), 2)

    e = Sheet({}, [])
    run_job(dict(job, expect=""), e.fetch, e.post)
    check("an empty cell takes the line alone, with no runs", (e.value, e.runs), ({"stringValue": "10/22 會議：改到下週"}, []))
    p = Sheet({"stringValue": "純文字"})
    run_job(dict(job, expect="純文字"), p.fetch, p.post)
    check("a plain cell stays without runs", p.runs, [])

    edited = Sheet({"stringValue": text + "（手改）"}, [LINK])
    refuses("a cell edited since the plan", 3, lambda: run_job(job, edited.fetch, edited.post))
    check("…writes nothing", edited.posts, [])
    # a formula shows no stringValue, so a plan that read it as empty text must still be refused
    refuses("a formula, planned on as an empty cell", 3,
            lambda: run_job(dict(job, expect=""), *(lambda x: (x.fetch, x.post))(Sheet({"formulaValue": "=A1"}))))
    refuses("a number", 3, lambda: run_job(dict(job, expect="3"), *(lambda x: (x.fetch, x.post))(Sheet({"numberValue": 3}))))
    emoji = "完成 ✅🚀"
    refuses("an emoji makes run offsets ambiguous", 3,
            lambda: run_job(dict(job, expect=emoji), *(lambda x: (x.fetch, x.post))(Sheet({"stringValue": emoji}, [LINK]))))
    refuses("a two-line line", 2, lambda: run_job(dict(job, line="a\nb"), *(lambda x: (x.fetch, x.post))(Sheet({"stringValue": text}))))
    refuses("another column", 2, lambda: run_job(dict(job, cell="L16"), *(lambda x: (x.fetch, x.post))(Sheet({"stringValue": text}))))
    refuses("the header row", 2, lambda: run_job(dict(job, cell="M1"), *(lambda x: (x.fetch, x.post))(Sheet({"stringValue": text}))))
    refuses("a job missing its line", 2, lambda: run_job({k: v for k, v in job.items() if k != "line"}, None, None))
    lossy = Sheet({"stringValue": text}, [LINK, PLAIN], drop_runs=True)
    refuses("a write that lost the links is caught on the read-back", 6, lambda: run_job(job, lossy.fetch, lossy.post))
    bent = Sheet({"stringValue": text}, [LINK, PLAIN], mangle=True)
    refuses("a write that reads back as other text is caught", 6, lambda: run_job(job, bent.fetch, bent.post))

    import contextlib
    import io
    import tempfile
    # a cell that can never take the line leaves a marker for live-plan's next look; an edited one does not
    mdir = tempfile.mkdtemp(prefix="notes-mark-")
    for what, sheet_, expect in (("an emoji", Sheet({"stringValue": emoji}, [LINK]), emoji),
                                 ("a formula", Sheet({"formulaValue": "=A1"}), "")):
        mk = os.path.join(mdir, "m.json")
        refuses("%s refuses" % what, 3, lambda: run_job(dict(job, expect=expect, refused_path=mk), sheet_.fetch, sheet_.post))
        got = json.load(open(mk, encoding="utf-8")) if os.path.exists(mk) else {}
        check("%s leaves a marker naming the cell, its text and the line" % what,
              (got.get("cell"), got.get("expect"), got.get("line"), bool(got.get("why"))),
              (job["cell"], expect, job["line"], True))
        if os.path.exists(mk):
            os.remove(mk)
    edited = Sheet({"stringValue": text + "改"}, [LINK])
    refuses("an edited cell refuses", 3, lambda: run_job(dict(job, refused_path=mk), edited.fetch, edited.post))
    check("an edited cell leaves no marker: the next look sees the edit itself", os.path.exists(mk), False)
    jp = os.path.join(tempfile.mkdtemp(prefix="notes-"), "job.json")
    json.dump(dict(job, account="nobody@example.com"), open(jp, "w", encoding="utf-8"), ensure_ascii=False)
    for mode in (None, "tidy"):
        os.environ.pop("ZYNKR_OPS_WEEKLY_MODE", None)
        if mode:
            os.environ["ZYNKR_OPS_WEEKLY_MODE"] = mode
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["--job", jp])
        check("in the %s beat it refuses before reading anything" % (mode or "unset"),
              (code, "only the apply beat" in err.getvalue()), (2, True))
    os.environ.pop("ZYNKR_OPS_WEEKLY_MODE", None)

    if fails:
        print("notes_append.py selftest: %d FAILED" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("notes_append.py selftest: all checks passed")
    return 0


MUTATIONS = [
    ("the old runs are dropped", [("out = [dict(r) for r in runs]", "out = []")]),
    ("the new line takes the last run's link", [('out.append({"startIndex": len(text) + 1, "format": {}})', "pass")]),
    ("an edited cell is overwritten", [('if text != job["expect"]:', "if False:")]),
    ("a formula or a number is overwritten", [("    if other:\n", "    if False:\n")]),
    ("any column may be written", [('CELL_RE = re.compile(r"^M(\\d+)$")', 'CELL_RE = re.compile(r"^[A-Z](\\d+)$")')]),
    ("the read-back is skipped", [("    if got != new:\n", "    if False:\n")]),
    ("lost links pass", [("    if lost:\n", "    if False:\n")]),
    ("an emoji passes", [('if len(text.encode("utf-16-le")) // 2 != len(text):', "if False:")]),
    ("it runs in any beat", [('if os.environ.get("ZYNKR_OPS_WEEKLY_MODE") != "apply":', "if False:")]),
    ("the row is off by one", [('"rowIndex": row - 1', '"rowIndex": row')]),
    ("a cell that can never take the line leaves no marker", [("            leave_marker(job, e)\n", "            pass\n")]),
    ("an emoji is taken for an edit", [('        raise CannotAppend(3, "the cell holds a character', '        raise Refuse(3, "the cell holds a character')]),
    ("a formula is taken for an edit", [('        raise CannotAppend(3, "the cell holds a %s', '        raise Refuse(3, "the cell holds a %s')]),
    ("an edit leaves a marker", [('raise Refuse(3, "%s changed since the plan', 'raise CannotAppend(3, "%s changed since the plan')]),
]


def mutate():
    import shutil
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    head, tail = src.split("\nMUTATIONS = [", 1)
    control = tempfile.mkdtemp(prefix="notes-mut-")
    open(os.path.join(control, "notes_append.py"), "w", encoding="utf-8").write(src)
    ok = subprocess.run([sys.executable, os.path.join(control, "notes_append.py"), "--selftest"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0
    shutil.rmtree(control, ignore_errors=True)
    if not ok:
        print("mutate: the unmutated copy fails its selftest; nothing below would mean anything")
        return 1
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
            d = tempfile.mkdtemp(prefix="notes-mut-")
            open(os.path.join(d, "notes_append.py"), "w", encoding="utf-8").write(m + "\nMUTATIONS = [" + tail)
            r = subprocess.run([sys.executable, os.path.join(d, "notes_append.py"), "--selftest"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            shutil.rmtree(d, ignore_errors=True)
            caught = r.returncode != 0 and "SyntaxError" not in r.stderr and "IndentationError" not in r.stderr
            print("mutate: %-46s %s" % (name, "caught" if caught else "MISSED"))
            missed += 0 if caught else 1
    print("mutate: %d of %d caught" % (len(MUTATIONS) - missed, len(MUTATIONS)))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
