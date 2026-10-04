#!/usr/bin/env python3
"""tracker_guard.py — the runner's PreToolUse hook: only `apply` may write the Main Tracker (SKB-044 AC-3.5).

Every scheduled beat runs `claude -p` with this script as a PreToolUse hook (run_ops_weekly.sh passes
it through --settings and exports ZYNKR_OPS_WEEKLY_MODE). Claude Code sends the pending tool call on
stdin; exit 0 lets it run, exit 2 refuses it and hands stderr back to the model. A refusal holds in
every permission mode, which an --allowedTools list does not: under `auto` that list only
pre-approves.

A call targets the tracker when the tracker id appears in one of its id fields (spreadsheet_id,
fileId, any key that ends in id/ids, at any depth) or anywhere in a Bash command. Payload fields such
as values, body and text are not checked, so a Ledger row or a mail that merely links the tracker
still passes. A targeting call is allowed only when it reads (get_ / read_ / list_ / search_ … tools)
or when the apply beat calls modify_sheet_values. An error inside the guard refuses every call but a
read, because a hook that crashes lets the call through.

    tracker_guard.py              # hook mode: event JSON on stdin
    tracker_guard.py --selftest | --mutate
"""
import json
import os
import re
import sys

READ_PREFIXES = ("get_", "read_", "list_", "search_", "check_", "query_", "fetch_",
                 "inspect_", "debug_", "download_")
APPLY_TOOL = "mcp__google-workspace__modify_sheet_values"
ID_KEY = re.compile(r"(?:^|_)ids?$", re.I)
CAMEL_ID_KEY = re.compile(r"[a-z]Ids?$")


def config_path():
    return os.environ.get("ZYNKR_OPS_WEEKLY_CONFIG") or os.path.expanduser("~/.config/zynkr/ops-weekly.json")


def tracker_id():
    # ZYNKR_TRACKER_GUARD_ID is for the selftest and the wiring proof only; the runner never sets it.
    override = os.environ.get("ZYNKR_TRACKER_GUARD_ID")
    if override:
        return override
    with open(config_path(), encoding="utf-8") as f:
        tid = json.load(f)["sources"]["main_tracker"]["id"]
    if not isinstance(tid, str) or len(tid) < 20:
        raise ValueError("sources.main_tracker.id is not a spreadsheet id")
    return tid


def is_read(tool):
    return tool.rsplit("__", 1)[-1].startswith(READ_PREFIXES)


def targets(node, tid):
    """True when the tracker id sits in an id field anywhere inside the tool input."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and (ID_KEY.search(key) or CAMEL_ID_KEY.search(key)) \
                    and tid in json.dumps(value, ensure_ascii=False):
                return True
            if isinstance(value, (dict, list)) and targets(value, tid):
                return True
        return False
    if isinstance(node, list):
        return any(targets(v, tid) for v in node)
    return False


def decide(event, tid, mode):
    """None to allow, or the reason for refusing."""
    tool = event.get("tool_name") or ""
    args = event.get("tool_input") or {}
    if tool == "Bash":
        hit = tid in json.dumps(args, ensure_ascii=False)
    else:
        hit = targets(args, tid)
    if not hit or is_read(tool):
        return None
    if mode == "apply" and tool == APPLY_TOOL:
        return None
    return ("zynkr-ops-weekly tracker guard: the %s beat may not call %s on the Main Tracker. "
            "Only apply writes it (SKB-044 AC-3.5). Do not retry; report it in the receipt."
            % (mode or "(no mode)", tool))


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--mutate" in sys.argv:
        return mutate()
    mode = os.environ.get("ZYNKR_OPS_WEEKLY_MODE", "")
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook input is not an object")
    except Exception:
        print("zynkr-ops-weekly tracker guard: unreadable hook input; refusing the call.", file=sys.stderr)
        return 2
    try:
        reason = decide(event, tracker_id(), mode)
    except Exception as e:
        tool = event.get("tool_name") or ""
        if tool and is_read(tool):
            return 0
        print("zynkr-ops-weekly tracker guard: %s (%s); refusing %s until the config is fixed."
              % (type(e).__name__, e, tool or "the call"), file=sys.stderr)
        return 2
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


# ── selftest: run the hook exactly as Claude Code does, one subprocess per case ──
TID = "1TRACKERguardSELFTEST0000000000000000000000"
LEDGER = "1LEDGERguardSELFTEST00000000000000000000000"
GW = "mcp__google-workspace__"
CASES = [
    # (name, mode, tool, input, expected exit code)
    ("snapshot writes the tracker", "snapshot", GW + "modify_sheet_values",
     {"spreadsheet_id": TID, "range_name": "A1", "values": [["x"]]}, 2),
    ("snapshot writes the Ledger", "snapshot", GW + "modify_sheet_values",
     {"spreadsheet_id": LEDGER, "range_name": "A1", "values": [["x"]]}, 0),
    ("apply writes the tracker", "apply", GW + "modify_sheet_values",
     {"spreadsheet_id": TID, "range_name": "H5", "values": [["完成"]]}, 0),
    ("apply formats the tracker", "apply", GW + "format_sheet_range",
     {"spreadsheet_id": TID, "range_name": "A1", "bold": True}, 2),
    ("recap reads the tracker", "recap", GW + "read_sheet_values",
     {"spreadsheet_id": TID, "range_name": "A1:M60"}, 0),
    ("a Ledger row that quotes the tracker id", "snapshot", GW + "modify_sheet_values",
     {"spreadsheet_id": LEDGER, "values": [["see https://docs.google.com/spreadsheets/d/" + TID]]}, 0),
    ("Bash naming the tracker, even in apply", "apply", "Bash",
     {"command": "curl -X PUT https://sheets.googleapis.com/v4/spreadsheets/" + TID}, 2),
    ("Bash without the tracker", "snapshot", "Bash",
     {"command": "python3 scripts/ledger.py snapshot pages --week 2026-W41"}, 0),
    ("a Drive update by camelCase fileId", "propose", "mcp__claude_ai_Google_Drive__update_file",
     {"fileId": TID, "title": "x"}, 2),
    ("no mode set", "", GW + "modify_sheet_values", {"spreadsheet_id": TID, "values": [["x"]]}, 2),
    ("an id nested in a request list", "propose", GW + "batch_update_spreadsheet",
     {"requests": [{"spreadsheetId": TID}]}, 2),
    ("a Doc link to the tracker", "agenda", GW + "batch_update_doc",
     {"document_id": "1DOC", "operations": [{"text": "tracker", "url": "https://docs.google.com/spreadsheets/d/" + TID}]}, 0),
    ("a saved tool result that quotes the id", "snapshot", "Write",
     {"file_path": "/tmp/pages.json", "content": "read 55 rows in spreadsheet " + TID}, 0),
    ("the tracker given as a URL", "snapshot", GW + "modify_sheet_values",
     {"spreadsheet_id": "https://docs.google.com/spreadsheets/d/" + TID + "/edit", "values": [["x"]]}, 2),
    ("a mail that links the tracker", "recap", GW + "send_gmail_message",
     {"to": "team@example.com", "subject": "週報", "body": "https://docs.google.com/spreadsheets/d/" + TID}, 0),
]


def run_hook(event, mode, tid=TID, config=None, raw=None):
    import subprocess
    env = dict(os.environ)
    env.pop("ZYNKR_TRACKER_GUARD_ID", None)
    env["ZYNKR_OPS_WEEKLY_MODE"] = mode
    if tid:
        env["ZYNKR_TRACKER_GUARD_ID"] = tid
    if config:
        env["ZYNKR_OPS_WEEKLY_CONFIG"] = config
    data = raw if raw is not None else json.dumps(event)
    p = subprocess.run([sys.executable, os.path.abspath(__file__)], input=data, env=env,
                       capture_output=True, text=True)
    return p.returncode


def selftest():
    fails = 0
    for name, mode, tool, args, want in CASES:
        got = run_hook({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": args}, mode)
        if got != want:
            fails += 1
            print("FAIL %-44s exit %s, want %s" % (name, got, want))
    missing = "/nonexistent/zynkr-ops-weekly-selftest.json"
    extra = [
        ("config unreadable: a Ledger write", run_hook(
            {"tool_name": GW + "modify_sheet_values", "tool_input": {"spreadsheet_id": LEDGER}},
            "snapshot", tid=None, config=missing), 2),
        ("config unreadable: a read", run_hook(
            {"tool_name": GW + "read_sheet_values", "tool_input": {"spreadsheet_id": LEDGER}},
            "snapshot", tid=None, config=missing), 0),
        ("unreadable hook input", run_hook(None, "snapshot", raw="not json"), 2),
    ]
    for name, got, want in extra:
        if got != want:
            fails += 1
            print("FAIL %-44s exit %s, want %s" % (name, got, want))
    total = len(CASES) + len(extra)
    print("selftest: %d/%d passed" % (total - fails, total))
    return 1 if fails else 0


# ── mutation check: each one-line breakage must turn the selftest red ────────
MUTATIONS = [
    # (name, [(old, new), ...]) — every pair is applied; each old text must occur exactly once
    ("apply may call any tool", [
        ('if mode == "apply" and tool == APPLY_TOOL:', 'if mode == "apply":')]),
    ("reads no longer exempt", [
        ("if not hit or is_read(tool):", "if not hit:")]),
    ("Bash not checked", [
        ("hit = tid in json.dumps(args, ensure_ascii=False)", "hit = False")]),
    ("payload fields checked too", [
        ("if isinstance(key, str) and (ID_KEY.search(key) or CAMEL_ID_KEY.search(key)) \\",
         "if isinstance(key, str) \\")]),
    ("camelCase ids ignored", [
        ("(ID_KEY.search(key) or CAMEL_ID_KEY.search(key))", "(ID_KEY.search(key))")]),
    ("nested inputs not walked", [
        ("if isinstance(value, (dict, list)) and targets(value, tid):", "if False:")]),
    ("config error fails open", [
        ('        print("zynkr-ops-weekly tracker guard: %s (%s); refusing %s until the config is fixed."',
         '        return 0\n        print("zynkr-ops-weekly tracker guard: %s (%s); refusing %s until the config is fixed."')]),
    ("bad hook input fails open", [
        ('        print("zynkr-ops-weekly tracker guard: unreadable hook input; refusing the call.", file=sys.stderr)\n        return 2',
         '        return 0')]),
    ("a refusal exits 0", [
        ("        print(reason, file=sys.stderr)\n        return 2", "        print(reason, file=sys.stderr)\n        return 0")]),
]


def mutate():
    import subprocess
    import tempfile
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    code, marker, rest = src.partition("\nMUTATIONS = [")   # never mutate the list itself
    tmpd = tempfile.mkdtemp(prefix="tracker-guard-mutate-")
    ok = True

    def run(text):
        p = os.path.join(tmpd, "tracker_guard_mut.py")
        open(p, "w", encoding="utf-8").write(text)
        return subprocess.run([sys.executable, p, "--selftest"], capture_output=True, text=True).returncode

    if run(src) != 0:
        print("mutate: the unmodified control copy fails its selftest")
        return 1
    for name, pairs in MUTATIONS:
        bad = [old for old, _ in pairs if code.count(old) != 1]
        if bad:
            print("mutate: %-32s SETUP ERROR (pattern not unique: %r)" % (name, bad[0][:40]))
            ok = False
            continue
        mutated = code
        for old, new in pairs:
            mutated = mutated.replace(old, new)
        rc = run(mutated + marker + rest)
        print("mutate: %-32s %s" % (name, "caught" if rc != 0 else "MISSED"))
        ok = ok and rc != 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
