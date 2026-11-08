#!/usr/bin/env python3
"""capture.py — the runner's PostToolUse hook: it saves each printed call's result for the model (SKB-118).

Every step of the weekly loop prints the calls the model must make, each with a path to save the
tool's result to, and the next step parses those files strictly. Saving by hand meant the model
retyping the result into a Write, and on 7 Nov that went wrong three ways in one weekend: a narrow
no-break space (U+202F, which Gmail writes in "2:01 PM") came out as a plain space, an 18 KB thread
came out cut at 2 KB, and a sheet read's escaped line breaks came out as real ones, which the run then
"repaired" with inline Python before the checks.

Under the runner, `ledger.emit` registers each printed call in the folder named by
ZYNKR_OPS_WEEKLY_CAPTURE (one file per call, named by `ledger.call_key`, holding its save paths), and
this hook runs after every MCP call. When the call is one that was printed, made with the same tool
and the same args, the hook writes the result to each of its save paths exactly as Claude Code hands
it over (for an MCP tool, the JSON text of what the tool returned, which every loader already reads),
and tells the model it is saved. Any other call is left alone. The guard (ops-weekly-tracker's
tracker_guard.py) refuses a Write or an Edit to a saved path, or to the capture folder.

It writes only inside the state folder's run folders (runs/, where every step's run folder lives), and
notes the sha256 of each file it saves in <capture>/saved/. Every loader checks it before it reads
(ledger.check_saved): a saved result changed afterwards, by whatever tool, is refused.

Exit 0 always, except when a printed call's result could not be written: then exit 2, and stderr
goes back to the model, which receipts the failure rather than save the result by hand.

    capture.py                  # hook mode: the PostToolUse event JSON on stdin
    capture.py --selftest | --mutate

Standard library only, and Python 3.9 safe.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ledger import CAPTURE_ENV, call_key, mark_folder, saved_record, state_dir, write_atomic  # noqa: E402


def result_text(resp):
    """The result as text, as the tool gave it. Claude Code hands an MCP result to the hook as the JSON
    text of what the tool returned; a list of text blocks is the text they hold; anything else is
    written as JSON."""
    if isinstance(resp, str):
        try:
            blocks = json.loads(resp) if resp.lstrip().startswith("[") else None
        except ValueError:
            blocks = None
        if text_blocks(blocks):
            return "\n".join(b["text"] for b in blocks)
        return resp
    if text_blocks(resp):
        return "\n".join(b["text"] for b in resp)
    return json.dumps(resp, ensure_ascii=False)


def text_blocks(x):
    return isinstance(x, list) and bool(x) and all(
        isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str) for b in x)


def save(event, cap):
    """The paths this call's result was written to, or [] when it is not a printed call."""
    tool, args = event.get("tool_name"), event.get("tool_input")
    if not isinstance(tool, str) or not isinstance(args, dict):
        return []
    wish = os.path.join(cap, call_key(tool, args) + ".json")
    if not os.path.exists(wish):
        return []
    with open(wish, encoding="utf-8") as f:
        paths = json.load(f)["save"]
    runs = os.path.realpath(os.path.join(state_dir(), "runs"))
    real = [os.path.realpath(p) for p in paths]
    for path, r in zip(paths, real):
        if not r.startswith(runs + os.sep):
            raise ValueError("%s is outside the run folders (%s)" % (path, runs))
    data = result_text(event.get("tool_response")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    for path, r in zip(paths, real):
        mark_folder(os.path.dirname(r), cap)
        write_atomic(r, data)
        record(cap, path, digest, tool)
    return paths


def record(cap, path, digest, tool):
    """Note what was saved at `path`, for ledger.check_saved."""
    rec = saved_record(cap, path)
    os.makedirs(os.path.dirname(rec), exist_ok=True)
    write_atomic(rec, json.dumps({"path": os.path.realpath(path), "sha256": digest, "tool": tool}).encode("utf-8"))


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--mutate" in sys.argv:
        return mutate()
    cap = os.environ.get(CAPTURE_ENV, "").strip()
    if not cap or not os.path.isdir(cap):
        return 0
    try:
        event = json.load(sys.stdin)
        paths = save(event, cap) if isinstance(event, dict) else []
    except Exception as e:  # noqa: BLE001 - every failure is the model's to report, never to work around
        print("zynkr-ops-weekly capture: the runner could not save this result (%s: %s). Do not save it "
              "yourself; receipt status=failed delivered=capture-failed." % (type(e).__name__, e), file=sys.stderr)
        return 2
    if paths:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "The runner saved this result, exactly as returned, to %s. Do not save it "
                                 "yourself; run the next step." % " and ".join(paths)}}, ensure_ascii=False))
    return 0


# ── selftest: run the hook exactly as Claude Code does, one subprocess per case ──
def run_hook(event, cap, raw=None):
    import subprocess
    env = dict(os.environ)
    env.pop(CAPTURE_ENV, None)
    if cap:
        env[CAPTURE_ENV] = cap
    p = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env, capture_output=True, text=True,
                       input=raw if raw is not None else json.dumps(event, ensure_ascii=False))
    return p.returncode, p.stdout, p.stderr


def selftest():
    import shutil
    import tempfile
    import ledger as L
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (name, got, want))

    tmp = tempfile.mkdtemp(prefix="capture-selftest-")
    old_state = os.environ.get("ZYNKR_OPS_WEEKLY_STATE")
    os.environ["ZYNKR_OPS_WEEKLY_STATE"] = tmp            # the hook's subprocesses inherit it

    def under_runner(fn, *a):
        """fn(*a) with the capture folder set in this process too, as a step under the runner has it."""
        os.environ[L.CAPTURE_ENV] = cap
        try:
            return fn(*a)
        finally:
            os.environ.pop(L.CAPTURE_ENV, None)

    def refused(fn, *a):
        try:
            fn(*a)
            return None
        except L.Refuse as e:
            return e.code, str(e)

    def refusal(fn, *a):
        return under_runner(refused, fn, *a)

    try:
        cap, run = os.path.join(tmp, "capture"), os.path.join(tmp, "runs", "2026-W45-apply-1")
        os.makedirs(cap)
        os.makedirs(run)
        gw = "mcp__google-workspace__"
        read = L.read_call({"account": "owner@example.com", "dir": run}, "1LEDGER", "Weeks!A7:R7", "wr")
        thread = {"tool": gw + "get_gmail_thread_content", "args": {"user_google_email": "owner@example.com",
                  "thread_id": "1a2b", "include_analysis": True}, "save": os.path.join(run, "thread.txt")}
        out = {"calls": [read, thread, {"tool": gw + "send_gmail_message", "args": {"to": "x"}}]}
        L.register_calls(out, cap)
        check("printed calls marked", [c.get("saved_by") for c in out["calls"]], ["runner", "runner", None])
        check("one file per printed call", sorted(os.listdir(cap)), sorted(
            L.call_key(c["tool"], c["args"]) + ".json" for c in (read, thread)))
        check("printing a call marks its folder with the capture folder", L.run_mark(os.path.join(run, "x")),
              os.path.realpath(cap))
        victim = os.path.join(tmp, "victim.txt")
        open(victim, "w", encoding="utf-8").write("keep")
        os.symlink(victim, os.path.join(run, "atomic.txt.tmp"))
        L.write_atomic(os.path.join(run, "atomic.txt"), b"new")
        check("a link at a temp name is never written through",
              (open(victim).read(), open(os.path.join(run, "atomic.txt")).read()), ("keep", "new"))
        os.symlink(victim, read["save"] + ".capture-tmp")       # where the hook used to write its temp copy

        # the tool's result, byte for byte: U+202F and an escaped line break inside a cell survive
        sheet = json.dumps({"result": "Successfully read 1 rows from range 'Weeks!A7:R7' in spreadsheet 1LEDGER "
                                      "for owner@example.com:\nRow  1: ['2026-W45', 'a\\nb', '2:01 PM']"},
                           ensure_ascii=False)
        args = dict(reversed(list(read["args"].items())))             # the model may order the keys its own way
        rc, so, se = run_hook({"tool_name": read["tool"], "tool_input": args, "tool_response": sheet}, cap)
        check("a printed call: exit", rc, 0)
        check("a printed call: saved exactly", open(read["save"], encoding="utf-8").read(), sheet)
        check("a printed call: saved as a file of its own, through no link",
              (os.path.islink(read["save"]), open(victim).read()), (False, "keep"))
        check("a printed call: the model is told", "saved this result" in so and read["save"] in so, True)
        rows = L.parse_values(under_runner(L.load_result, read["save"]), "1LEDGER", "Weeks!A7:R7")
        check("the saved read parses, the cell's line break and U+202F intact", rows, [["2026-W45", "a\nb", "2:01 PM"]])

        rec = json.load(open(L.saved_record(cap, read["save"]), encoding="utf-8"))
        check("the record holds the saved file's sha256", rec["sha256"],
              hashlib.sha256(open(read["save"], "rb").read()).hexdigest())

        # a saved result changed afterwards, by whatever tool, is refused where it is read
        with open(read["save"], "a", encoding="utf-8") as f:
            f.write(" ")
        got = refusal(L.load_result, read["save"]) or (0, "")
        check("a changed result: refused, and says so", (got[0], "changed after the runner saved it" in got[1]), (3, True))
        alias = os.path.join(tmp, "alias")
        os.symlink(run, alias)
        got = refusal(L.load_result, os.path.join(alias, os.path.basename(read["save"]))) or (0, "")
        check("a changed result read through a link to its folder: refused", got[0], 3)
        got = refused(L.load_result, read["save"]) or (0, "")
        check("outside the runner, a folder the runner saves into: refused, and says so",
              (got[0], "cannot see the runner's record" in got[1]), (3, True))
        os.environ[L.CAPTURE_ENV] = os.path.join(tmp, "runs")        # a folder, but not the runner's
        try:
            got = refused(L.load_result, read["save"]) or (0, "")
        finally:
            os.environ.pop(L.CAPTURE_ENV, None)
        check("another capture folder named: refused", got[0], 3)
        plain = os.path.join(tmp, "plain")
        os.makedirs(plain)
        open(os.path.join(plain, "x.txt"), "w", encoding="utf-8").write("x")
        check("a folder the runner never saved into: read", L.load_result(os.path.join(plain, "x.txt")), "x")
        # a file at a printed save path that the runner never saved is refused too
        never = dict(read, args=dict(read["args"], range_name="Weeks!A20:R20"), save=os.path.join(run, "never.txt"))
        L.register_calls({"calls": [never]}, cap)
        open(never["save"], "w", encoding="utf-8").write("Row  1: ['typed']")
        got = refusal(L.load_result, never["save"]) or (0, "")
        check("never saved by the runner: refused, and says so", (got[0], "never saved" in got[1]), (3, True))
        own = os.path.join(run, "notes.txt")
        open(own, "w", encoding="utf-8").write("x")
        check("a file no printed call names: read", under_runner(L.load_result, own), "x")

        # the same read made with one arg changed is another call: nothing saved, nothing said
        os.remove(read["save"])
        moved = dict(read["args"], range_name="Weeks!A8:R8")
        rc, so, se = run_hook({"tool_name": read["tool"], "tool_input": moved, "tool_response": sheet}, cap)
        check("a changed arg: nothing saved", (rc, so, os.path.exists(read["save"])), (0, "", False))
        # another tool with the same args is another call too
        rc, so, se = run_hook({"tool_name": gw + "get_spreadsheet_info", "tool_input": read["args"],
                               "tool_response": sheet}, cap)
        check("another tool: nothing saved", os.path.exists(read["save"]), False)
        # outside the runner the hook does nothing
        rc, so, se = run_hook({"tool_name": read["tool"], "tool_input": read["args"], "tool_response": sheet}, None)
        check("no capture folder: nothing saved", (rc, os.path.exists(read["save"])), (0, False))

        # a structured result is the tool's JSON text; a list of text blocks is its text
        rc, so, se = run_hook({"tool_name": thread["tool"], "tool_input": thread["args"],
                               "tool_response": {"result": {"content": "Thread ID: 1a2b", "analysis": {}}}}, cap)
        check("a dict result: written as JSON", json.load(open(thread["save"], encoding="utf-8")),
              {"result": {"content": "Thread ID: 1a2b", "analysis": {}}})
        blocks = [{"type": "text", "text": "No data found in range 'Weeks!A7:R7'"}]
        for resp in (blocks, json.dumps(blocks)):
            run_hook({"tool_name": read["tool"], "tool_input": read["args"], "tool_response": resp}, cap)
            check("text blocks: their text (%s)" % type(resp).__name__, open(read["save"], encoding="utf-8").read(),
                  "No data found in range 'Weeks!A7:R7'")
        listing = json.dumps([{"id": "t1", "title": "週會"}], ensure_ascii=False)
        run_hook({"tool_name": read["tool"], "tool_input": read["args"], "tool_response": listing}, cap)
        check("a JSON list that is not text blocks: as is", open(read["save"], encoding="utf-8").read(), listing)

        # a later step that prints the same call again names its own path; the earlier file is kept
        again = dict(thread, save=os.path.join(run, "thread-2.txt"))
        L.register_calls({"then": [again]}, cap)
        first = open(thread["save"], encoding="utf-8").read()
        run_hook({"tool_name": thread["tool"], "tool_input": thread["args"], "tool_response": "{\"result\": 2}"}, cap)
        check("a re-read: the new path", open(again["save"], encoding="utf-8").read(), "{\"result\": 2}")
        check("a re-read: the first file kept", open(thread["save"], encoding="utf-8").read(), first)
        # the same call printed twice in one step goes to both paths
        twins = [dict(read, save=os.path.join(run, "a.txt")), dict(read, save=os.path.join(run, "b.txt"))]
        L.register_calls({"calls": twins}, cap)
        run_hook({"tool_name": read["tool"], "tool_input": read["args"], "tool_response": "x"}, cap)
        check("twins: both saved", [open(t["save"]).read() for t in twins], ["x", "x"])
        # a call printed again before it is made: the result goes to the newest path, and the first, which
        # no result was saved to, is refused when typed by hand (code review of #131)
        plan_a = dict(read, args=dict(read["args"], range_name="Weeks!A30:R30"), save=os.path.join(run, "plan-a.txt"))
        plan_b = dict(plan_a, save=os.path.join(run, "plan-b.txt"))
        L.register_calls({"calls": [plan_a]}, cap)
        L.register_calls({"calls": [plan_b]}, cap)
        run_hook({"tool_name": plan_a["tool"], "tool_input": plan_a["args"], "tool_response": "Row  1: ['real']"}, cap)
        check("printed again: saved to the newest path only",
              (os.path.exists(plan_b["save"]), os.path.exists(plan_a["save"])), (True, False))
        open(plan_a["save"], "w", encoding="utf-8").write("Row  1: ['typed']")
        got = refusal(L.load_result, plan_a["save"]) or (0, "")
        check("printed again: the first path, typed by hand, refused", (got[0], "never saved" in got[1]), (3, True))

        # a result that cannot be written goes back to the model as a failure, never silently
        gone = dict(read, args=dict(read["args"], range_name="Weeks!A9:R9"),
                    save=os.path.join(tmp, "runs", "no-such-folder", "x.txt"))
        L.register_calls({"calls": [gone]}, cap)
        rc, so, se = run_hook({"tool_name": gone["tool"], "tool_input": gone["args"], "tool_response": "x"}, cap)
        check("an unwritable path: exit 2", rc, 2)
        check("an unwritable path: says not to save by hand", "Do not save it yourself" in se, True)
        os.makedirs(os.path.dirname(gone["save"]))
        rc, so, se = run_hook({"tool_name": gone["tool"], "tool_input": gone["args"], "tool_response": "x"}, cap)
        check("a folder made after the call was printed: saved, and marked", (rc, L.run_mark(gone["save"])),
              (0, os.path.realpath(cap)))
        rc, so, se = run_hook(None, cap, raw="not json")
        check("unreadable hook input: exit 2", rc, 2)
        # it writes only inside the run folders: not beside them, and not through a link out of them
        elsewhere = os.path.join(tmp, "elsewhere")
        os.makedirs(elsewhere)
        os.symlink(elsewhere, os.path.join(run, "link"))
        for name, path in (("beside the run folders", os.path.join(tmp, "x.txt")),
                           ("through a link out of them", os.path.join(run, "link", "x.txt"))):
            out_call = dict(read, args=dict(read["args"], range_name="Weeks!A1:A%d" % len(name)), save=path)
            L.register_calls({"calls": [out_call]}, cap)
            rc, so, se = run_hook({"tool_name": out_call["tool"], "tool_input": out_call["args"], "tool_response": "x"}, cap)
            check("a path %s: refused" % name, (rc, "outside the run folders" in se), (2, True))
            check("a path %s: nothing written" % name, os.listdir(elsewhere) + [p for p in [path] if os.path.exists(path)], [])

        # emit registers only under the runner: without the folder a printed call is left as it was
        import contextlib
        import io
        for env_cap, want in ((None, False), (cap, True)):
            old = os.environ.pop(L.CAPTURE_ENV, None)
            if env_cap:
                os.environ[L.CAPTURE_ENV] = env_cap
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                L.emit({"calls": [L.read_call({"account": "o@example.com", "dir": run}, "1L", "Weeks!A1:T1", "wh")]})
            os.environ.pop(L.CAPTURE_ENV, None)
            if old is not None:
                os.environ[L.CAPTURE_ENV] = old
            check("emit %s the folder" % ("with" if want else "without"),
                  json.loads(buf.getvalue())["calls"][0].get("saved_by") == "runner", want)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop(L.CAPTURE_ENV, None)
        if old_state is None:
            os.environ.pop("ZYNKR_OPS_WEEKLY_STATE", None)
        else:
            os.environ["ZYNKR_OPS_WEEKLY_STATE"] = old_state
    if fails:
        print("capture.py selftest: %d failed" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("capture.py selftest: all checks passed")
    return 0


# ── mutation check: each one-line breakage must turn the selftest red ────────
MUTATIONS = [
    # (name, [(old, new), ...]) — every pair is applied; each old text must occur exactly once
    ("any call is saved", [("    if not os.path.exists(wish):\n        return []", "    if False:\n        return []")]),
    ("only the first path is saved", [("    for path, r in zip(paths, real):\n        mark_folder", "    for path, r in zip(paths[:1], real):\n        mark_folder")]),
    ("text blocks kept as JSON", [("        if text_blocks(blocks):", "        if False:")]),
    ("a dict result unwrapped", [("    return json.dumps(resp, ensure_ascii=False)", "    return str(resp)")]),
    ("a failure passes silently", [("        return 2\n    if paths:", "        return 0\n    if paths:")]),
    ("the model is not told", [("    if paths:\n        print(", "    if False:\n        print(")]),
    ("no record of what was saved", [("        write_atomic(r, data)\n        record(cap, path, digest, tool)",
                                      "        write_atomic(r, data)")]),
    ("anywhere may be written", [("        if not r.startswith(runs + os.sep):", "        if False:")]),
    ("a link out of the run folders followed", [
        ('    runs = os.path.realpath(os.path.join(state_dir(), "runs"))', '    runs = os.path.abspath(os.path.join(state_dir(), "runs"))'),
        ("    real = [os.path.realpath(p) for p in paths]", "    real = [os.path.abspath(p) for p in paths]")]),
    ("the folder not marked when saved", [("        mark_folder(os.path.dirname(r), cap)\n", "")]),
    ("the temp copy written through a link", [("        write_atomic(r, data)\n",
                                                 "        with open(path + \".capture-tmp\", \"wb\") as f:\n            f.write(data)\n"
                                                 "        os.replace(path + \".capture-tmp\", r)\n")]),
]
# ledger.check_saved is this hook's other half: these break a copy of ledger.py, which the unchanged
# selftest then imports
LEDGER_MUTATIONS = [
    ("a changed result read", [("        if got != want:\n            raise Refuse(3, \"%s changed after",
                                "        if False:\n            raise Refuse(3, \"%s changed after")]),
    ("a never-saved result read", [("        if p in {os.path.realpath(s) for s in saves}:", "        if False:")]),
    ("an earlier printed path forgotten", [('"printed": list(dict.fromkeys(before + saves))', '"printed": saves')]),
    ("check_saved reads only the newest path", [("                saves = printed_saves(json.load(f))",
                                                 "                saves = json.load(f).get(\"save\") or []")]),
    ("a link's spelling misses the record", [("    p = os.path.realpath(path)\n    rec = saved_record(cap, p)",
                                              "    p = os.path.abspath(path)\n    rec = saved_record(cap, p)"),
                                             ("    return hashlib.sha256(os.path.realpath(path)", "    return hashlib.sha256(os.path.abspath(path)")]),
    ("load_result checks nothing", [("    check_saved(path)\n    text = open(path", "    text = open(path")]),
    ("a folder the runner saves into read without it", [
        ("    if mark is not None and not (cap and os.path.realpath(cap) == mark):", "    if False:")]),
    ("another capture folder accepted", [
        ("    if mark is not None and not (cap and os.path.realpath(cap) == mark):", "    if mark is not None and not cap:")]),
    ("the folder not marked when printed", [("        if folder.startswith(runs + os.sep) and os.path.isdir(folder):\n            mark_folder(folder, cap)",
                                              "        if False:\n            mark_folder(folder, cap)")]),
    ("a folder marked through a link", [("        if folder.startswith(runs + os.sep) and os.path.isdir(folder):",
                                          "        if os.path.isdir(folder):")]),
    ("a temp name a link can sit at", [
        ('    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(os.path.abspath(path)))\n    try:\n        with os.fdopen(fd, "wb") as f:',
         '    tmp = path + ".tmp"\n    try:\n        with open(tmp, "wb") as f:')]),
]


def mutate():
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")   # never mutate the list itself
    tmpd = tempfile.mkdtemp(prefix="capture-mutate-")
    ok = True

    def run(text):
        p = os.path.join(tmpd, "capture_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        env = dict(os.environ, PYTHONPATH=HERE)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True, env=env).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    lsrc = open(os.path.join(HERE, "ledger.py"), encoding="utf-8").read()
    lcode, lmarker, lrest = lsrc.partition("\nMUTATIONS = [")
    for target, name, pairs in [("capture", n, p) for n, p in MUTATIONS] + [("ledger", n, p) for n, p in LEDGER_MUTATIONS]:
        base = code if target == "capture" else lcode
        bad = [old for old, _ in pairs if base.count(old) != 1]
        if bad:
            print("mutate: %-40s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = base
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        copy = os.path.join(tmpd, "ledger.py")      # found before PYTHONPATH: the copy sits beside capture_mut.py
        if target == "ledger":
            open(copy, "w", encoding="utf-8").write(mutated + lmarker + lrest)
            rc = run(src)
            os.remove(copy)
        else:
            rc = run(mutated + marker + rest)
        print("mutate: %-40s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
