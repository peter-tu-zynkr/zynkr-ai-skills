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

It also keeps every beat out of the owner's private weekly-insights folder (SKB-070). The runner sets
ZYNKR_OPS_WEEKLY_PRIVATE_DIR when that folder is configured; the agenda reads only the copy of
meeting.json the runner makes, never the digest or report beside it. A call is refused, reads
included and in every beat, when its path fields, Glob pattern or Bash command name the folder in any
spelling (full path, ~/…, $HOME/…), use an ancestor up to the home folder as a search root or cd
target or with a wildcard just below it, or search (Grep, Glob) from the folder, inside it or above
it. A Doc or a mail that merely mentions the folder is not a read of it and passes. See
private_reason() for what a guard can and cannot promise.

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


def private_dir():
    """The owner's private weekly-insights folder (SKB-070), absolute, or '' when not set."""
    folder = os.environ.get("ZYNKR_OPS_WEEKLY_PRIVATE_DIR", "").strip()
    return os.path.normpath(os.path.expanduser(folder)) if folder else ""


def spellings(path, home):
    """The ways a tool input may write a path that sits under the home folder."""
    out = [path]
    if path == home or path.startswith(home + os.sep):
        rest = path[len(home):]
        out += ["~" + rest, "$HOME" + rest, "${HOME}" + rest]
    return out


START = r"(?:^|(?<=[\s\"'=:(<>]))"     # a path starts the input, or follows a space, quote, = : ( < >
ENDS = r"(?=$|[\s\"';&|)<>])"           # ... and ends right there
GLOB_BELOW = r"/[^\s/\"']*[*?\[]"       # ... or the next part of it is a wildcard
# Fields that name a file or a place, at any depth: file_path, path, fileUrl (a Drive upload takes a
# file:// URL), attachments, folder… A Doc's text, a mail body or a Write's content is never one.
PATHISH = re.compile(r"(?:path|file|url|uri|dir|folder|attach)", re.I)


def pathish_values(node, under=False):
    """Every string that sits in a path-like field of a tool input, at any depth."""
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            out += pathish_values(value, under or (isinstance(key, str) and bool(PATHISH.search(key))))
    elif isinstance(node, list):
        for value in node:
            out += pathish_values(value, under)
    elif isinstance(node, str) and under:
        out.append(node)
    return out


def resolved(text):
    """A path as the file system will see it: file:// and ~ and $HOME unwrapped, .. folded."""
    text = re.sub(r"^file://", "", text.strip())
    if text.startswith(("/", "~", "$")):
        return os.path.normpath(os.path.expandvars(os.path.expanduser(text)))
    return text


def glob_root(pattern):
    """The folder an absolute Glob pattern searches: its parts up to the first wildcard."""
    p = resolved(pattern) if isinstance(pattern, str) else ""
    if not p.startswith("/"):
        return ""
    fixed = []
    for part in p.split("/"):
        if any(c in part for c in "*?[{"):
            break
        fixed.append(part)
    return "/".join(fixed) or "/"


def private_reason(event):
    """None to allow, or the reason for refusing a call that reaches into the private folder.

    Only where a call says what it opens counts: the path fields of any tool (an MCP upload or
    attachment names its file there too), a Glob pattern and a Bash command. What a Write or a Doc
    says is never a read, so a tracker row that mentions the folder still passes. Three ways in are
    refused:
    1. the folder itself, or anything below it, in any spelling;
    2. an ancestor up to the home folder (~/.claude, ~) used as a whole path, which is a search
       root or a cd target, or with a wildcard just below it (`~/.claude/weekly-insight?`);
    3. a Grep or Glob whose search root, its path or else the working folder, is the folder,
       inside it, or above it: a search from / or from ~ walks into it.
    A guard cannot read intent: a command that hides the path from it still gets through. It
    catches the honest mistakes; the agenda's instruction to read only the copy is the rule.
    """
    folder = private_dir()
    tool = event.get("tool_name") or ""
    if not folder:
        return None
    home = os.path.normpath(os.path.expanduser("~"))
    args = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    paths = pathish_values(args)
    said = paths + [resolved(p) for p in paths]
    if tool == "Bash":
        said.append(args.get("command"))
    if tool == "Glob":
        said += [args.get("pattern"), resolved(args.get("pattern") or "")]
    blob = "\n".join(s for s in said if isinstance(s, str))
    refuse = ("zynkr-ops-weekly guard: %s is the owner's private weekly-insights folder, and this call "
              "reaches into it. Read only the copy the prompt names (insights=...); search from a "
              "folder that does not contain it. Do not retry another way." % folder)
    for s in spellings(folder, home):
        if re.search(START + re.escape(s) + r"(?:" + ENDS + "|/)", blob):
            return refuse
    above = os.path.dirname(folder)
    while above and (above == home or above.startswith(home + os.sep)):
        for s in spellings(above, home):
            if re.search(START + re.escape(s) + r"(?:" + ENDS + "|/" + ENDS + "|" + GLOB_BELOW + ")", blob):
                return refuse
        if above == home:
            break
        above = os.path.dirname(above)
    if tool in ("Grep", "Glob"):
        root = args.get("path") or (tool == "Glob" and glob_root(args.get("pattern"))) or event.get("cwd") or ""
        root = resolved(root) if isinstance(root, str) and root else ""
        if root and (root == folder or root.startswith(folder + os.sep)
                     or folder.startswith(root.rstrip(os.sep) + os.sep)):
            return refuse
    return None


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
    # The private folder is checked first: it needs no config, so a broken config cannot open it.
    try:
        preason = private_reason(event)
    except Exception as e:
        preason = "zynkr-ops-weekly guard: %s while checking the private folder; refusing the call." % type(e).__name__
    if preason:
        print(preason, file=sys.stderr)
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


# The owner's private folder (SKB-070), under a made-up home so every spelling can be tested.
HOME = "/home/selftest"
PRIVATE = HOME + "/.claude/weekly-insights"
PRIVATE_CASES = [
    # (name, mode, tool, input, expected exit code[, working folder]) — run with the private folder set;
    # the working folder defaults to HOME/work, which is not above the private folder
    ("a Read in the private folder", "agenda", "Read", {"file_path": PRIVATE + "/2026-W42/report.md"}, 2),
    ("Bash cat by its ~ spelling", "agenda", "Bash", {"command": "cat ~/.claude/weekly-insights/2026-W42/digest.md"}, 2),
    ("Bash cd to an ancestor, then a relative path", "agenda", "Bash",
     {"command": "cd ~/.claude && cat weekly-insights/2026-W42/report.json"}, 2),
    ("Grep by its $HOME spelling", "agenda", "Grep", {"pattern": "Atlas", "path": "$HOME/.claude/weekly-insights"}, 2),
    ("a Glob listing the folder", "tidy", "Glob", {"pattern": "**/*.json", "path": PRIVATE}, 2),
    ("a Glob pattern into the folder", "agenda", "Glob", {"pattern": "~/.claude/weekly-insights/**/*.md"}, 2),
    ("Bash grep -r from an ancestor", "agenda", "Bash", {"command": "grep -r Atlas ~/.claude"}, 2),
    ("Bash with a wildcard for the name", "agenda", "Bash",
     {"command": "cat ~/.claude/weekly-insight?/2026-W42/report.md"}, 2),
    ("Bash ls with a trailing wildcard", "agenda", "Bash", {"command": "ls ~/.claude/weekly-insights*"}, 2),
    ("Grep rooted above the folder", "agenda", "Grep", {"pattern": "Atlas", "path": HOME + "/.claude"}, 2),
    ("a pathless Grep from /", "agenda", "Grep", {"pattern": "Atlas"}, 2, "/"),
    ("the runner's copy is allowed", "agenda", "Read",
     {"file_path": HOME + "/.local/state/zynkr/ops-weekly/2026-W42.meeting.json"}, 0),
    ("the weekly-insights skill folder is allowed", "agenda", "Read",
     {"file_path": HOME + "/.claude/skills/weekly-insights/SKILL.md"}, 0),
    ("a Grep for the name in the skills is allowed", "agenda", "Grep",
     {"pattern": "weekly-insights", "path": HOME + "/.claude/skills/zynkr-ops-weekly"}, 0),
    ("a pathless Grep from a work folder", "agenda", "Grep", {"pattern": "Atlas"}, 0),
    ("an ordinary Bash call is allowed", "agenda", "Bash",
     {"command": "python3 -I carryover.py --section 'Oct 15, 2026' --input /tmp/ow/doc.md"}, 0),
    ("Bash reading the config under $HOME", "agenda", "Bash",
     {"command": 'cat "${ZYNKR_OPS_WEEKLY_CONFIG:-$HOME/.config/zynkr/ops-weekly.json}"'}, 0),
    ("a saved row that names the folder is no read", "snapshot", "Write",
     {"file_path": "/tmp/run/rows.json", "content": "3.22 weekly-insights keeps its week in ~/.claude/weekly-insights"}, 0),
    ("a Doc that mentions the folder is no read", "agenda", GW + "batch_update_doc",
     {"document_id": "1DOC", "operations": [{"text": PRIVATE}]}, 0),
    ("a Drive upload by file:// URL", "agenda", GW + "create_drive_file",
     {"fileUrl": "file://" + PRIVATE + "/2026-W42/digest.md", "folder_id": "1FOLDER", "file_name": "x.md"}, 2),
    ("a mail attachment from the folder", "decisions", GW + "send_gmail_message",
     {"to": "team@example.com", "subject": "週報", "body": "x", "attachments": [{"path": PRIVATE + "/2026-W42/report.md"}]}, 2),
    ("a path that walks back into the folder", "agenda", "Read",
     {"file_path": HOME + "/.claude/skills/../weekly-insights/2026-W42/report.md"}, 2),
    ("rollup's Glob of its own scripts, from /", "rollup", "Glob",
     {"pattern": HOME + "/.claude/skills/zynkr-ops-weekly/scripts/*"}, 0, "/"),
    ("an absolute Glob from above the folder", "agenda", "Glob", {"pattern": HOME + "/.claude/**/report.md"}, 2, "/"),
]


def run_hook(event, mode, tid=TID, config=None, raw=None, private=None):
    import subprocess
    env = dict(os.environ)
    env.pop("ZYNKR_TRACKER_GUARD_ID", None)
    env.pop("ZYNKR_OPS_WEEKLY_PRIVATE_DIR", None)
    env["ZYNKR_OPS_WEEKLY_MODE"] = mode
    if tid:
        env["ZYNKR_TRACKER_GUARD_ID"] = tid
    if config:
        env["ZYNKR_OPS_WEEKLY_CONFIG"] = config
    if private:
        env["ZYNKR_OPS_WEEKLY_PRIVATE_DIR"] = private
        env["HOME"] = HOME
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
        ("private folder, without the setting", run_hook(
            {"tool_name": "Read", "tool_input": {"file_path": PRIVATE + "/2026-W42/report.md"}}, "agenda"), 0),
        ("private folder, config unreadable", run_hook(
            {"tool_name": "Read", "tool_input": {"file_path": PRIVATE + "/x"}}, "agenda",
            tid=None, config=missing, private=PRIVATE), 2),
    ]
    for case in PRIVATE_CASES:
        name, mode, tool, args, want = case[:5]
        cwd = case[5] if len(case) > 5 else HOME + "/work"
        extra.append((name, run_hook({"tool_name": tool, "tool_input": args, "cwd": cwd}, mode, private=PRIVATE), want))
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
    ("private folder not checked", [
        ("    if not folder:\n        return None\n    home", "    return None\n    home")]),
    ("only the full path is spelled", [
        ('        out += ["~" + rest, "$HOME" + rest, "${HOME}" + rest]', "        pass")]),
    ("ancestors not checked", [
        ("    while above and (above == home or above.startswith(home + os.sep)):", "    while False:")]),
    ("a wildcard below an ancestor allowed", [
        (' + "|" + GLOB_BELOW + ")"', ' + ")"')]),
    ("search roots not checked", [
        ('    if tool in ("Grep", "Glob"):', "    if False:")]),
    ("a pathless search ignores cwd", [
        (' or event.get("cwd") or ""', ' or ""')]),
    ("private: payload fields checked too", [
        ('    blob = "\\n".join(s for s in said if isinstance(s, str))', "    blob = json.dumps(args, ensure_ascii=False)")]),
    ("file:// URLs not unwrapped", [
        ('    text = re.sub(r"^file://", "", text.strip())', "    text = text.strip()")]),
    ("lists under a path field skipped", [
        ("    elif isinstance(node, list):", "    elif False:")]),
    (".. not folded", [
        ("        return os.path.normpath(os.path.expandvars(os.path.expanduser(text)))",
         "        return os.path.expandvars(os.path.expanduser(text))")]),
    ("an absolute Glob searches from cwd", [
        ('(tool == "Glob" and glob_root(args.get("pattern")))', "False")]),
    ("MCP calls not checked", [
        ("    if not folder:\n        return None\n    home", '    if not folder or tool.startswith("mcp__"):\n        return None\n    home')]),
    ("a private refusal exits 0", [
        ("        print(preason, file=sys.stderr)\n        return 2", "        print(preason, file=sys.stderr)\n        return 0")]),
    ("private check after the config", [
        ("    try:\n        preason = private_reason(event)", "    tracker_id()\n    try:\n        preason = private_reason(event)")]),
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
