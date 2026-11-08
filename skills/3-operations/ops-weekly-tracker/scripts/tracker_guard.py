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

SKB-091 adds apply's two other writes, each in one exact shape: resize_sheet_dimensions that only appends
1 to 40 rows (a 新增 on a full grid), and the 備註 append, `python3 <…>/ops-weekly-tracker/scripts/
notes_append.py --job <file>`, the one raw-API write (decision A). That script names no tracker id on its
command line, so the guard refuses any Bash call that mentions it outside apply, and any other shape of it
inside apply.

It also keeps every beat out of the owner's private weekly-insights folder (SKB-070). The runner sets
ZYNKR_OPS_WEEKLY_PRIVATE_DIR when that folder is configured. No beat reads anything there since v4
(SKB-091) retired the agenda, which read only a copy of meeting.json the runner made. A call is refused, reads
included and in every beat, when its path fields, Glob pattern or Bash command name the folder in any
spelling (full path, ~/…, $HOME/…), use an ancestor up to the home folder as a search root or cd
target or with a wildcard just below it, or search (Grep, Glob) from the folder, inside it or above
it. A Doc or a mail that merely mentions the folder is not a read of it and passes. See
private_reason() for what a guard can and cannot promise.

SKB-118: under the runner, the runner saves each printed call's result itself (zynkr-ops-weekly's
capture.py, which ZYNKR_OPS_WEEKLY_CAPTURE turns on), so a saved result is the tool's own text. The
guard keeps it that way: it refuses a Write or an Edit to a path the runner saved, and a Bash command
that runs inline Python (`python3 -c`, `python3 -`, a heredoc or a pipe into python3) on the loop's
state folder, where the saved results live. On 7 Nov a catch-up rewrote three saved sheet reads that
way before the checks read them. Inline Python elsewhere (a beat reading Claude Code's own
tool-results file) still runs, and without the capture folder nothing changes.

    tracker_guard.py              # hook mode: event JSON on stdin
    tracker_guard.py --selftest | --mutate
"""
import json
import os
import re
import shlex
import sys

READ_PREFIXES = ("get_", "read_", "list_", "search_", "check_", "query_", "fetch_",
                 "inspect_", "debug_", "download_")
APPLY_TOOL = "mcp__google-workspace__modify_sheet_values"
RESIZE_TOOL = "mcp__google-workspace__resize_sheet_dimensions"
RESIZE_KEYS = {"spreadsheet_id", "sheet_name", "user_google_email", "insert_rows"}
NOTES = "notes_append.py"
NOTES_PATH = re.compile(r"(^|/)ops-weekly-tracker/scripts/notes_append\.py$")
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
    return os.path.normpath(os.path.expandvars(os.path.expanduser(folder))) if folder else ""


# Fields that name a file or a place, at any depth: file_path, path, fileUrl (a Drive upload takes a
# file:// URL), attachments, folder… A Doc's text, a mail body or a Write's content is never one.
PATHISH = re.compile(r"(?:path|file|url|uri|dir|folder|attach)", re.I)
WILDCARD = "*?[{"


def pathish_values(node, under_path=False):
    """Every string that sits in a path-like field of a tool input, at any depth."""
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            out += pathish_values(value, under_path or (isinstance(key, str) and bool(PATHISH.search(key))))
    elif isinstance(node, list):
        for value in node:
            out += pathish_values(value, under_path)
    elif isinstance(node, str) and under_path:
        out.append(node)
    return out


ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'")


def _ansi_c(match):
    """bash's $'…' quoting, decoded the way bash decodes it (\\x77 is w), then quoted plainly."""
    try:
        text = match.group(1).encode("latin-1", "backslashreplace").decode("unicode_escape")
    except Exception:  # noqa: BLE001 - an undecodable escape stays as written
        text = match.group(1)
    return shlex.quote(text)


def shell_tokens(command, lines=False):
    """The words a shell would see in a command, in order: $'…' decoded, quotes and escapes undone,
    ; & | < > ( ) split off. With `lines`, a line break is a word of its own too, since it ends a command
    as ; does. An unbalanced quote falls back to spaces."""
    command = ANSI_C.sub(_ansi_c, command).replace('$"', '"')
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n" if lines else True)
        if lines:
            lex.whitespace = " \t\r"
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return command.split()


CMD_SEP = set(";&|()\n")
ASSIGN_WORD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Commands that only read their arguments: a word after one of them is text, never a program it runs.
DATA_COMMANDS = frozenset(("grep", "egrep", "fgrep", "echo", "printf", "cat", "head", "tail", "wc", "cut", "tr", "ls",
                           "stat", "file", "which", "type", "whereis", "basename", "dirname", "realpath", "readlink",
                           "jq", "diff", "cmp"))
# Commands that run text as a command: with one anywhere, no word of the command is only text.
RUNS_TEXT = frozenset(("sh", "bash", "zsh", "dash", "ksh", "fish", "eval", "source", "xargs", "parallel"))


def ends_command(word):
    """True for a word after which the shell starts a new command: ; && || | & ( ) or a line break, alone
    or run together (`&&\\n`, `);`), and <( or >( (a process substitution runs one)."""
    return bool(word) and (set(word) <= CMD_SEP or word.endswith("("))


def as_data(words, i):
    """True when words[i], from shell_tokens(lines=True), is an argument of a command in DATA_COMMANDS and
    nothing in the command runs text: no RUNS_TEXT word, and no backtick, whose command substitution the
    tokens do not mark (`grep -rn env -i f` and `which python3` run nothing)."""
    if any("`" in w for w in words):
        return False
    if any(os.path.basename(w) in RUNS_TEXT for w in words):
        return False
    j = i
    while j > 0 and not ends_command(words[j - 1]):
        j -= 1
    while j < i and ASSIGN_WORD.match(words[j]):
        j += 1
    return j < i and os.path.basename(words[j]) in DATA_COMMANDS


def shell_words(command):
    """shell_tokens, and the value of a --flag=value as a word of its own (after the rest)."""
    words = shell_tokens(command)
    return words + [w.split("=", 1)[1] for w in words if "=" in w]


def as_path(word, cwd):
    """A word as the file system would take it: file://, ~ and $HOME unwrapped, a relative word joined
    to the working folder, . and .. and doubled slashes folded, lower-cased because a macOS disk ignores
    case. '' when there is no telling where a relative word points."""
    w = re.sub(r"^file://", "", word.strip())
    if not w:
        return ""
    if cwd:                                   # ~+ and $PWD are the working folder, not the hook's own
        w = re.sub(r"^~\+(?=/|$)", lambda m: cwd, w)
        w = re.sub(r"\$\{PWD\}|\$PWD\b", lambda m: cwd, w)
    w = os.path.expandvars(os.path.expanduser(w))
    if not w.startswith("/"):
        if not cwd:
            return ""
        w = os.path.join(cwd, w)
    return os.path.normpath(re.sub(r"^/+", "/", w)).lower()


def fixed_part(path):
    """A path up to its first wildcard part: the folder a wildcard starts matching from."""
    fixed = []
    for part in path.split("/"):
        if any(c in part for c in WILDCARD):
            break
        fixed.append(part)
    return "/".join(fixed) or "/"


def under(path, folder):
    return path == folder or path.startswith(folder.rstrip("/") + "/")


# The raw-text view: a path can also sit inside a quoted string of code (python3 -c "open('…')"), where
# the shell sees one word that does not look like a path at all. So the text is searched too, case
# ignored, for the folder in each spelling, and for an ancestor inside home that ends right there or
# has a wildcard just below it.
START = r"(?:^|(?<=[\s\"'=:(<>,\[]))"   # a path starts the text, or follows a space, quote, = : ( < > , [
ENDS = r"(?=$|[\s\"';&|)<>,\]])"         # ... and ends right there
GLOB_BELOW = r"/[^\s/\"']*[*?\[]"        # ... or the next part of it is a wildcard


def spellings(path, home):
    """The ways a text may write a path that sits under the home folder."""
    out = [path]
    if path == home or path.startswith(home + "/"):
        rest = path[len(home):]
        out += ["~" + rest, "$HOME" + rest, "${HOME}" + rest]
    return out


def raw_hit(text, folder, home):
    for s in spellings(folder, home):
        if re.search(START + re.escape(s) + r"(?:" + ENDS + "|/)", text, re.I):
            return True
    above = os.path.dirname(folder)
    while above and under(above, home):
        for s in spellings(above, home):
            if re.search(START + re.escape(s) + r"(?:" + ENDS + "|/" + ENDS + "|" + GLOB_BELOW + ")", text, re.I):
                return True
        if above == home:
            break
        above = os.path.dirname(above)
    return False


def reaches(path, folder, home):
    """True when a resolved path opens the folder: the folder or anything in it, an ancestor of it
    inside the home folder (~ or ~/.claude: a search root or a cd target), or a wildcard that starts
    matching inside the folder or at such an ancestor. Ancestors above home (/, /Users) are left to
    the Grep and Glob rule: as Bash words they are mostly not paths at all, but code (`{`, `*`) that
    lands on / once joined to the launchd working folder."""
    if not path:
        return False
    if any(c in path for c in WILDCARD):
        start = fixed_part(path)
        return under(start, folder) or (under(folder, start) and under(start, home))
    if under(path, folder):
        return True
    return under(folder, path) and under(path, home)


def private_reason(event):
    """None to allow, or the reason for refusing a call that reaches into the private folder.

    Only where a call says what it opens counts: the path fields of any tool (an MCP upload or an
    attachment names its file there too), a Glob pattern, and the words of a Bash command. What a
    Write or a Doc says is never a read, so a tracker row that mentions the folder still saves.

    Every candidate is read the way the shell and the disk will read it, not as raw text: the
    command is split into words as a shell splits them (quotes and escapes undone, --flag=value
    split), ~, $HOME and file:// unwrapped, a relative word joined to the working folder, . .. and //
    folded, and case ignored, as it is on a macOS disk. A candidate is refused when it is the folder
    or inside it, an ancestor of it up to the home folder (~/.claude or ~, a search root or a cd
    target), or a wildcard that starts matching at or above it. A Grep is also refused when it
    searches from the folder or from anywhere above it, / included, which a pathless Grep from the
    launchd working folder does.

    A guard cannot read intent: a path built at run time (a variable, a command substitution, a
    symlink made earlier) still gets through. It catches the ways a beat might reach the folder by
    mistake; the agenda's instruction to read only the copy is the rule.
    """
    folder = private_dir().lower()
    if not folder:
        return None
    home = os.path.normpath(os.path.expanduser("~")).lower()
    tool = event.get("tool_name") or ""
    args = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else ""
    words = pathish_values(args)
    if tool == "Bash" and isinstance(args.get("command"), str):
        words += shell_words(args["command"])
    glob_at = ""
    if tool == "Glob" and isinstance(args.get("pattern"), str):
        pattern = args["pattern"]
        base = args.get("path") if isinstance(args.get("path"), str) and args.get("path") else cwd
        glob_at = pattern if pattern.startswith(("/", "~", "$")) or not base else os.path.join(base, pattern)
        words.append(glob_at)
    hit = any(reaches(as_path(w, cwd), folder, home) for w in words if isinstance(w, str))
    if not hit and tool == "Bash" and isinstance(args.get("command"), str):
        # Follow cd inside the command: `cd ~/.claude/skills && cd ../weekly-insights` moves the folder
        # the next relative word is read from. A bare cd goes home.
        here, said = cwd, shell_words(args["command"])
        for i, w in enumerate(said):
            if reaches(as_path(w, here), folder, home):
                hit = True
                break
            if w in ("cd", "pushd"):
                nxt = said[i + 1] if i + 1 < len(said) else ""
                here = home if not nxt or nxt in (";", "&&", "||", "|", "&") else (as_path(nxt, here) or here)
    if not hit:
        texts = pathish_values(args) + [args.get("command") if tool == "Bash" else None,
                                        args.get("pattern") if tool == "Glob" else None]
        hit = raw_hit("\n".join(t for t in texts if isinstance(t, str)), private_dir(),
                      os.path.normpath(os.path.expanduser("~")))
    if not hit and tool in ("Grep", "Glob"):
        # Grep and Glob walk a whole tree: refused from the folder, inside it, or anywhere above it, /
        # included, which is where a pathless search from the launchd working folder starts.
        if tool == "Grep":
            root = as_path(args.get("path") or cwd or "", cwd)
        else:
            root = fixed_part(as_path(glob_at, cwd)) if glob_at else ""
        hit = bool(root) and (under(root, folder) or under(folder, root))
    if hit:
        return ("zynkr-ops-weekly guard: %s is the owner's private weekly-insights folder, and this call "
                "reaches into it. Read only the copy the prompt names (insights=...); search from a "
                "folder that does not contain it. Do not retry another way." % private_dir())
    return None


# ── what the runner saved (SKB-118) ──────────────────────────────────────────
CAPTURE_ENV = "ZYNKR_OPS_WEEKLY_CAPTURE"
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
PYTHON_WORD = re.compile(r"^(?:\S*/)?python(?:3(?:\.\d+)?)?$")
PY_INFO = ("--version", "--help", "--help-env", "--help-xoptions", "--help-all")
PY_LONG_ARG = ("--check-hash-based-pycs",)
SHELL_STOPS = (";", "&&", "||", "|", "&", "<", "<<", "<<<", ")", "(")


def capture_dir():
    d = os.environ.get(CAPTURE_ENV, "").strip()
    return d if d and os.path.isdir(d) else ""


def state_folder():
    """The loop's state folder, absolute and lower-cased: the stamps, each run's saved results (runs/)
    and the capture folder. The same default as zynkr-ops-weekly's ledger.state_dir()."""
    d = os.environ.get("ZYNKR_OPS_WEEKLY_STATE") or "~/.local/state/zynkr/ops-weekly"
    return os.path.normpath(os.path.expandvars(os.path.expanduser(d))).lower()


def saved_paths(cap):
    """Every path a printed call names in this run, as as_path() spells it: where the runner saves its
    result, and every path a step printed for it before (ledger.register_calls)."""
    out = set()
    if not cap:
        return out
    for name in os.listdir(cap):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(cap, name), encoding="utf-8") as f:
                record = json.load(f)
        except (OSError, ValueError):
            continue
        for key in ("save", "printed"):
            saves = record.get(key) if isinstance(record, dict) else None
            for p in saves if isinstance(saves, list) else [saves]:
                if isinstance(p, str):
                    out.add(as_path(p, ""))
    return out


def inline_python(command):
    """True when the command runs Python code that is no script file, as Python reads its flags: -c on
    its own or anywhere in a run of joined flags (-Ic, and -cprint(1), whose code follows the c), `-`,
    a script under /dev or /proc (/dev/stdin with a heredoc), or no script at all (a heredoc or a pipe).
    -W, -X and --check-hash-based-pycs take an argument, so -Wc is a warning filter; -m runs a module;
    -V, -h and --version print and run nothing. A python3 that a reading command only names (`which
    python3`) is no Python run (as_data). The words are read in order, without shell_words' --flag=value
    extras, which would sit where a script goes."""
    words = shell_tokens(command, lines=True)
    for i, w in enumerate(words):
        if not PYTHON_WORD.match(w) or as_data(words, i):
            continue
        j, kind, info = i + 1, None, False
        while kind is None and j < len(words) and words[j].startswith("-") and words[j] != "-":
            flag, j = words[j], j + 1
            if flag == "--":
                break
            if flag.startswith("--"):
                info = info or flag in PY_INFO    # --version: Python prints it and runs nothing
                if flag in PY_LONG_ARG:
                    j += 1                        # its argument is the next word
                continue
            for k, ch in enumerate(flag[1:], 1):
                if ch in "cm":
                    kind = ch
                    break
                if ch in "WX":
                    if k == len(flag) - 1:
                        j += 1                    # its argument is the next word
                    break
                info = info or ch in "hV?"
        if kind == "c":
            return True
        if kind == "m" or info:
            continue
        nxt = words[j] if j < len(words) else ""
        if nxt in ("", "-") or ends_command(nxt) or nxt in SHELL_STOPS or re.match(r"^/(?:dev|proc)/", nxt):
            return True
    return False


def command_reaches(command, cwd, folder):
    """True when a Bash command names `folder` or a path inside it: as a word (relative words read from
    where a cd inside the command left off), or anywhere in its text in any spelling, quoted code too."""
    home = os.path.normpath(os.path.expanduser("~")).lower()
    here, said = cwd, shell_words(command)
    for i, w in enumerate(said):
        p = as_path(w, here)
        if p and under(p, folder):
            return True
        if w in ("cd", "pushd"):
            nxt = said[i + 1] if i + 1 < len(said) else ""
            here = home if not nxt or nxt in SHELL_STOPS else (as_path(nxt, here) or here)
    return any(re.search(START + re.escape(s) + r"(?:" + ENDS + "|/)", command, re.I) for s in spellings(folder, home))


LOOP_ENV = re.compile(r"ZYNKR_OPS_WEEKLY_(?:STATE|CAPTURE)\b")
RUN_MARK = ".runner-saves"     # ledger.py's note in each folder the runner saves into (the selftest checks)
ENV_WORD = re.compile(r"^(?:\S*/)?env$")


def clears_env(command):
    """True when the command runs something with the environment cleared or a variable removed: env -i,
    env -u NAME, env - (and the long forms), or exec -c. A step run that way would not see the runner's
    capture folder, and ledger.check_saved refuses that; this says why before it runs. An env that a
    reading command only names (`grep -rn env -i f`) runs nothing (as_data)."""
    words = shell_tokens(command, lines=True)
    for i, w in enumerate(words):
        is_env = bool(ENV_WORD.match(w))
        if not (is_env or w == "exec") or as_data(words, i):
            continue
        for f in words[i + 1:]:
            if f == "-" and is_env:
                return True
            if not f.startswith("-") or f == "--":
                break
            if f.startswith("--"):
                if is_env and f.split("=", 1)[0] in ("--ignore-environment", "--unset"):
                    return True
                continue
            if (is_env and ("i" in f[1:] or "u" in f[1:])) or (not is_env and "c" in f[1:]):
                return True
    return False


def capture_reason(event):
    """None to allow, or the reason for refusing a call that would replace or rewrite a saved result, or
    reach the runner's record of them (SKB-118). Only under the runner, which names the capture folder.

    It catches the ways a beat has gone about it, and the obvious next ones; a beat set on getting
    round it could (a script written through code that names no path). What holds whatever happens is
    the check where each result is read: every loader refuses a file that changed after the runner
    saved it (zynkr-ops-weekly's ledger.check_saved)."""
    cap = capture_dir()
    if not cap:
        return None
    capf = as_path(cap, "")
    tool = event.get("tool_name") or ""
    args = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else ""
    if tool in WRITE_TOOLS:
        fp = args.get("file_path") or args.get("notebook_path")
        p = as_path(fp, cwd) if isinstance(fp, str) else ""
        if p and p in saved_paths(cap):
            return ("zynkr-ops-weekly guard: the runner saved this call's result to %s exactly as the tool "
                    "returned it, so it is never written or edited by hand (SKB-118). If a step says it is "
                    "missing or does not parse, make that call again exactly as printed, then run the step "
                    "again." % fp)
        if p and under(p, capf):
            return ("zynkr-ops-weekly guard: %s is the runner's record of what it saved, and only the runner "
                    "writes there (SKB-118)." % fp)
        if p and os.path.basename(p) == RUN_MARK:
            return ("zynkr-ops-weekly guard: %s is the runner's note that it saves this folder's results, and "
                    "only the runner writes it (SKB-118)." % fp)
        name = p or (fp.strip().lower() if isinstance(fp, str) else "")
        if name.endswith(".py"):
            return ("zynkr-ops-weekly guard: a beat writes no Python (SKB-118). Run only the printed script "
                    "commands. If a step refuses a result, make that call again exactly as printed; if it "
                    "still refuses, receipt status=failed with the step's message.")
    if tool == "Bash" and isinstance(args.get("command"), str):
        command = args["command"]
        if command_reaches(command, cwd, capf):
            return ("zynkr-ops-weekly guard: this command reaches %s, the runner's record of what it saved; no "
                    "step reads or writes it (SKB-118)." % cap)
        if RUN_MARK in command:
            return ("zynkr-ops-weekly guard: this command names %s, the runner's note that it saves a run "
                    "folder's results; no step reads or writes it (SKB-118)." % RUN_MARK)
        if LOOP_ENV.search(command):
            return ("zynkr-ops-weekly guard: this command names the weekly loop's state or capture setting. "
                    "The runner sets both, and a step runs with them as they are: run the printed command "
                    "exactly as printed, with nothing added to it (SKB-118).")
        if clears_env(command):
            return ("zynkr-ops-weekly guard: this command runs something with the environment cleared or a "
                    "setting removed, so a step would not see the runner's settings. Run the printed command "
                    "exactly as printed, with nothing added to it (SKB-118).")
        if inline_python(command) and command_reaches(command, cwd, state_folder()):
            return ("zynkr-ops-weekly guard: this command runs inline Python on the weekly loop's state "
                    "folder, where each run's saved results are. They are the scripts' evidence: run only "
                    "the printed script commands on them, and never rewrite one (SKB-118). If a step "
                    "refuses a result, make that call again exactly as printed; if it still refuses, "
                    "receipt status=failed with the step's message.")
    return None


def notes_command(command):
    """True only for `python3 <…>/ops-weekly-tracker/scripts/notes_append.py --job <file>`, nothing else
    on the line: no second command, no redirection, no other flag."""
    if re.search(r"[;&|<>`$\n]", command):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    return (len(words) == 4 and words[0] in ("python3", "python") and bool(NOTES_PATH.search(words[1]))
            and words[2] == "--job" and not words[3].startswith("-"))


def decide(event, tid, mode):
    """None to allow, or the reason for refusing."""
    tool = event.get("tool_name") or ""
    args = event.get("tool_input") or {}
    if tool == "Bash" and NOTES in str(args.get("command", "")):
        if mode == "apply" and notes_command(str(args.get("command", ""))):
            return None
        return ("zynkr-ops-weekly tracker guard: notes_append.py writes the Main Tracker's 備註. Only the apply "
                "beat runs it, and only as `python3 <path>/notes_append.py --job <file>` with nothing else on the "
                "line (SKB-091). Do not retry in another shape; report it in the receipt.")
    if tool == "Bash":
        hit = tid in json.dumps(args, ensure_ascii=False)
    else:
        hit = targets(args, tid)
    if not hit or is_read(tool):
        return None
    if mode == "apply" and tool == APPLY_TOOL:
        return None
    if (mode == "apply" and tool == RESIZE_TOOL and set(args) <= RESIZE_KEYS
            and isinstance(args.get("insert_rows"), int) and not isinstance(args.get("insert_rows"), bool)
            and 1 <= args["insert_rows"] <= 40):
        return None                                  # a 新增 on a full grid: rows appended, nothing else
    if tool == "Bash":
        # W41 and W42: a read result saved through a heredoc carried the tracker id (the Weeks row holds
        # it), and "do not retry" ended three apply runs that had a safe way on.
        if capture_dir():
            # SKB-118: under the runner nothing is saved by hand, so the Write-tool retry is no way on
            return ("zynkr-ops-weekly tracker guard: this Bash command contains the Main Tracker's id, so it "
                    "was refused (SKB-044 AC-3.5). The runner saves every printed call's result itself: run "
                    "each script command on its own, with nothing else in it. Never touch the Main Tracker "
                    "from Bash.")
        return ("zynkr-ops-weekly tracker guard: this Bash command contains the Main Tracker's id, so it "
                "was refused (SKB-044 AC-3.5). A saved read result usually carries that id: save each "
                "result with the Write tool instead, then run the script command on its own, with "
                "nothing else in it. That retry is allowed. Never touch the Main Tracker from Bash.")
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
        creason = capture_reason(event)
    except Exception as e:
        # only a write or a command can replace a saved result: every other call goes on
        tool = event.get("tool_name") or ""
        creason = ("zynkr-ops-weekly guard: %s while checking the runner's saved results; refusing %s."
                   % (type(e).__name__, tool)) if tool in WRITE_TOOLS + ("Bash",) else None
    if creason:
        print(creason, file=sys.stderr)
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
    # SKB-091: apply's two other writes, each in exactly one shape
    ("apply appends rows for a 新增", "apply", GW + "resize_sheet_dimensions",
     {"user_google_email": "a@b.c", "spreadsheet_id": TID, "sheet_name": "H2", "insert_rows": 2}, 0),
    ("apply may not delete tracker rows", "apply", GW + "resize_sheet_dimensions",
     {"spreadsheet_id": TID, "sheet_name": "H2", "delete_rows": [5]}, 2),
    ("apply may not insert rows mid-sheet", "apply", GW + "resize_sheet_dimensions",
     {"spreadsheet_id": TID, "sheet_name": "H2", "insert_rows": 1, "insert_rows_at": 5}, 2),
    ("apply may not append a flood of rows", "apply", GW + "resize_sheet_dimensions",
     {"spreadsheet_id": TID, "sheet_name": "H2", "insert_rows": 500}, 2),
    ("propose may not resize the tracker", "propose", GW + "resize_sheet_dimensions",
     {"spreadsheet_id": TID, "sheet_name": "H2", "insert_rows": 1}, 2),
    ("apply runs the 備註 append", "apply", "Bash",
     {"command": "python3 '/Users/x/.claude/skills/ops-weekly-tracker/scripts/notes_append.py' --job "
                 "'/Users/x/.local/state/zynkr/ops-weekly/runs/2026-W45-apply-1/note-3.json'"}, 0),
    ("the 備註 append in any other beat", "tidy", "Bash",
     {"command": "python3 /Users/x/.claude/skills/ops-weekly-tracker/scripts/notes_append.py --job /tmp/j.json"}, 2),
    ("the 備註 append with a second command", "apply", "Bash",
     {"command": "python3 /Users/x/.claude/skills/ops-weekly-tracker/scripts/notes_append.py --job /tmp/j.json; rm -rf /tmp/x"}, 2),
    ("the 備註 append with a command hidden in its job path", "apply", "Bash",
     {"command": 'python3 /Users/x/.claude/skills/ops-weekly-tracker/scripts/notes_append.py --job "$(touch /tmp/p)"'}, 2),
    ("the 備註 append with another flag", "apply", "Bash",
     {"command": "python3 /Users/x/.claude/skills/ops-weekly-tracker/scripts/notes_append.py --job /tmp/j.json --force"}, 2),
    ("a look-alike script of the same name", "apply", "Bash",
     {"command": "python3 /tmp/notes_append.py --job /tmp/j.json"}, 2),
    ("its selftest outside apply is refused too", "recap", "Bash",
     {"command": "python3 /Users/x/.claude/skills/ops-weekly-tracker/scripts/notes_append.py --selftest"}, 2),
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
     {"file_path": "/tmp/run/rows.json", "content": "~/.claude/weekly-insights/2026-W42/report.md"}, 0),
    # the shell and the disk read a path differently from raw text: quotes, escapes, case, //, --flag=
    ("a quoted name", "agenda", "Bash", {"command": "cat ~/.claude/'weekly-insights'/2026-W42/report.md"}, 2),
    ("an escaped name", "agenda", "Bash", {"command": "cat ~/.claude/weekly\\-insights/2026-W42/report.md"}, 2),
    ("the name in another case", "agenda", "Read", {"file_path": HOME + "/.claude/Weekly-Insights/2026-W42/report.md"}, 2),
    ("doubled and dotted slashes", "agenda", "Bash",
     {"command": "cat //home/selftest/.claude/./weekly-insights//2026-W42/report.md"}, 2),
    ("a --flag=path", "agenda", "Bash",
     {"command": "python3 x.py --input=~/.claude/weekly-insights/2026-W42/digest.md"}, 2),
    ("a relative path from ~/.claude", "agenda", "Bash", {"command": "cat weekly-insights/2026-W42/report.md"}, 2,
     HOME + "/.claude"),
    ("ls / reads nothing of the folder", "agenda", "Bash", {"command": "ls /"}, 0),
    ("a Glob from / by its path", "agenda", "Glob", {"pattern": "**/*.md", "path": "/"}, 2),
    # cases only one view can catch: quotes break the raw text but not the shell's words, and a path
    # inside a string of code is no word of its own but is plain in the raw text
    ("quoted, in another case", "agenda", "Bash", {"command": "cat ~/.claude/'Weekly-Insights'/2026-W42/report.md"}, 2),
    ("a quoted --flag=path", "agenda", "Bash",
     {"command": "python3 x.py --input=~/.claude/'weekly-insights'/2026-W42/digest.md"}, 2),
    ("a quoted wildcard", "agenda", "Bash", {"command": "cat ~/.claude/'weekly-insight'?/2026-W42/report.md"}, 2),
    ("a quoted ancestor", "agenda", "Bash", {"command": "grep -r Atlas ~/'.claude'"}, 2),
    ("a quote mid-name, another case", "agenda", "Bash", {"command": "cat ~/.cl'aude'/Weekly-Insights/2026-W42/report.md"}, 2),
    ("a quote mid-name, --flag=path", "agenda", "Bash",
     {"command": "python3 x.py --input=~/.cl'aude'/weekly-insights/2026-W42/digest.md"}, 2),
    ("a quote mid-name, wildcard", "agenda", "Bash", {"command": "cat ~/.cl'aude'/weekly-insight?/2026-W42/report.md"}, 2),
    ("a quote mid-name, ancestor", "agenda", "Bash", {"command": "grep -r Atlas ~/.cl'aude'"}, 2),
    ("code that names the folder in another case", "agenda", "Bash",
     {"command": "python3 -c \"print(open('/HOME/SELFTEST/.claude/Weekly-Insights/x').read())\""}, 2),
    ("a cd chain that walks back in", "agenda", "Bash",
     {"command": "cd ~/.claude/skills && cd ../weekly-insights && cat 2026-W42/report.md"}, 2, "/"),
    ("a bare cd, then a relative path", "agenda", "Bash",
     {"command": "cd && cat .claude/weekly-insights/2026-W42/report.md"}, 2, "/"),
    ("a cd into the skill, then its files", "agenda", "Bash",
     {"command": "cd ~/.claude/skills/zynkr-ops-weekly/references; cat post-format.md routing.md"}, 0, "/"),
    ("bash $'…' quoting", "agenda", "Bash",
     {"command": "cat ~/.claude/$'\\x77eekly-insights'/2026-W42/report.md"}, 2),
    ("~+ from ~/.claude", "agenda", "Bash", {"command": "cat ~+/weekly-insights/2026-W42/report.md"}, 2, HOME + "/.claude"),
    ("$PWD from ~/.claude", "agenda", "Bash", {"command": "cat $PWD/weekly-insights/2026-W42/report.md"}, 2, HOME + "/.claude"),
    ("a path inside quoted code", "agenda", "Bash",
     {"command": "python3 -c \"print(open('" + PRIVATE + "/2026-W42/report.md').read())\""}, 2),
    ("an ancestor inside quoted code", "agenda", "Bash",
     {"command": "python3 -c \"import os; print(os.listdir(os.path.expanduser('~/.claude')))\""}, 2),
    ("code that opens its own tool results", "agenda", "Bash",
     {"command": "python3 -c \"import json; t=json.load(open('" + HOME + "/.claude/projects/-/abc/tool-results/x.txt'))\""}, 0, "/"),
    ("a pathless relative Glob from /", "agenda", "Glob", {"pattern": "**/report.md"}, 2, "/"),
    ("code with braces and stars from /", "decisions", "Bash",
     {"command": "python3 -c \"import json; d={'a': [1, 2]}; print(d['a'][0] * 2)\""}, 0, "/"),
    ("the config read from /", "rollup", "Bash",
     {"command": 'cat "${ZYNKR_OPS_WEEKLY_CONFIG:-$HOME/.config/zynkr/ops-weekly.json}"; ls ~/.claude/skills/zynkr-ops-weekly'},
     0, "/"),
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


# SKB-118: what the runner saved. Each case runs with a capture folder that names one saved result,
# <run>/lt1.txt, inside a state folder of its own; `{run}`, `{state}`, `{cap}` and `{home}` are filled in.
CAPTURE_CASES = [
    # the security review of 7 Nov: Python's own flag rules, and what the runner keeps
    ("-W takes an argument", "Bash", {"command": "python3 -W ignore -c \"open('{run}/lt1.txt', 'w')\""}, "/", 2),
    ("-X takes an argument", "Bash", {"command": "python3 -X utf8 -c \"open('{run}/lt1.txt', 'w')\""}, "/", 2),
    ("-c joined to its code", "Bash", {"command": "python3 \"-cimport sys; open(sys.argv[1], 'w')\" {run}/lt1.txt"}, "/", 2),
    ("/dev/stdin with a heredoc", "Bash",
     {"command": "python3 /dev/stdin <<'EOF'\nopen('{run}/lt1.txt', 'w').write('x')\nEOF"}, "/", 2),
    ("a --flag=value before the pipe", "Bash", {"command": "cat --x=1 {run}/lt1.txt | python3"}, "/", 2),
    ("-Wc is a warning filter, and -m a module", "Bash", {"command": "python3 -Wc -m json.tool {run}/decided.json"}, "/", 0),
    ("a Write into the capture folder", "Write", {"file_path": "{cap}/" + "1" * 32 + ".json", "content": "{}"}, "/", 2),
    ("a Write of Python", "Write", {"file_path": "/tmp/fix.py", "content": "print(1)"}, "/", 2),
    ("a command that reads the capture folder", "Bash", {"command": "python3 -m json.tool {cap}/" + "0" * 32 + ".json"}, "/", 2),
    ("inline Python on the loop's env", "Bash",
     {"command": "python3 -c \"import os; print(os.listdir(os.environ['ZYNKR_OPS_WEEKLY_STATE']))\""}, "/", 2),
    # the review's second round: a step run without the runner's settings, and the runner's note
    ("a step run with the capture setting removed", "Bash",
     {"command": "cd {home}/.claude/skills/ops-weekly-tracker && env -u ZYNKR_OPS_WEEKLY_CAPTURE python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("a step run with the state folder moved", "Bash",
     {"command": "ZYNKR_OPS_WEEKLY_STATE=/tmp/x python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("a step run with the environment cleared", "Bash",
     {"command": "cd {home}/.claude/skills/ops-weekly-tracker && /usr/bin/env -i PATH=/usr/bin python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("env -u on any setting", "Bash", {"command": "env -u HOME python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("env -, the short form", "Bash", {"command": "env - python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("env --unset", "Bash", {"command": "env --unset=HOME python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("exec -c", "Bash", {"command": "exec -c python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("env setting some other variable", "Bash", {"command": "env LC_ALL=C python3 -m json.tool {run}/decided.json"}, "/", 0),
    ("find -exec is not exec", "Bash", {"command": "find {run} -name '*.json' -exec ls {} +"}, "/", 0),
    # the code review of #131: words a reading command only reads, and Python that prints and runs nothing
    ("grep for the word env", "Bash", {"command": "grep -rn env -i {run}/decided.json"}, "/", 0),
    ("which python3 beside the run folder", "Bash", {"command": "ls {run}; which python3"}, "/", 0),
    ("python3 --version in the run folder", "Bash", {"command": "cd {run} && python3 --version"}, "/", 0),
    ("python3 -V in the run folder", "Bash", {"command": "cd {run} && python3 -V"}, "/", 0),
    ("a Write of Python named relative, with no cwd", "Write", {"file_path": "fix.py", "content": "print(1)"}, "", 2),
    # ... and the same words where something runs them
    ("env after a line break", "Bash", {"command": "grep x {run}/decided.json\nenv -u HOME python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("env after a reading command and &&", "Bash", {"command": "ls {run} &&\nenv -i python3 scripts/proposals.py live-plan --dir {run}"}, "/", 2),
    ("env in a process substitution", "Bash", {"command": "cat <(env -i python3 scripts/proposals.py live-plan --dir {run})"}, "/", 2),
    ("env in a command substitution", "Bash", {"command": "echo $(env -u HOME python3 scripts/proposals.py live-plan --dir {run})"}, "/", 2),
    ("env in backticks after echo", "Bash", {"command": "echo ` env -u HOME python3 scripts/proposals.py live-plan --dir {run}`"}, "/", 2),
    ("python3 in backticks after echo", "Bash", {"command": "echo ` python3 -c \"open('{run}/lt1.txt', 'w')\"`"}, "/", 2),
    ("echoed env piped into a shell", "Bash", {"command": "echo env -u HOME python3 scripts/proposals.py live-plan --dir {run} | sh"}, "/", 2),
    ("echoed python3 piped into xargs", "Bash", {"command": "echo python3 -c \"open('{run}/lt1.txt', 'w')\" | xargs -0 sh -c"}, "/", 2),
    ("--check-hash-based-pycs takes an argument", "Bash",
     {"command": "python3 --check-hash-based-pycs always - <<'EOF'\nopen('{run}/lt1.txt', 'w').write('x')\nEOF"}, "/", 2),
    ("--version does not hide a -c after it", "Bash", {"command": "python3 --version -c \"open('{run}/lt1.txt', 'w')\""}, "/", 2),
    ("the runner's note removed", "Bash", {"command": "rm {run}/.runner-saves"}, "/", 2),
    ("the runner's note written", "Write", {"file_path": "{run}/.runner-saves", "content": "/tmp/x"}, "/", 2),
    # (name, tool, input, cwd, expected exit code)
    ("a Write to a saved result", "Write", {"file_path": "{run}/lt1.txt", "content": "Row  1: ['x']"}, "/", 2),
    ("a Write to a path a step printed before", "Write", {"file_path": "{run}/lt0.txt", "content": "Row  1: ['x']"}, "/", 2),
    ("an Edit to a saved result", "Edit", {"file_path": "{run}/lt1.txt", "old_string": "a", "new_string": "b"}, "/", 2),
    ("a saved result named relative to the cwd", "Write", {"file_path": "lt1.txt", "content": "x"}, "{run}", 2),
    ("the model's own file in the run folder", "Write", {"file_path": "{run}/proposals.json", "content": "[]"}, "/", 0),
    ("the 7 Nov repair: a heredoc in the run folder", "Bash",
     {"command": "cd {run} && python3 -I - <<'EOF'\nfor f in (\"lt1.txt\",):\n    open(f, \"w\").write(\"x\")\nEOF\n"
                 "grep -c '^Row' lt1.txt"}, "/", 2),
    ("inline Python that names a saved result", "Bash",
     {"command": "python3 -c \"open('{run}/lt1.txt', 'w').write('x')\""}, "/", 2),
    ("joined flags on a stamp", "Bash", {"command": "python3 -Ic \"import os; os.remove('{state}/2026-W45.apply.done')\""}, "/", 2),
    ("a saved result piped into python3", "Bash", {"command": "cat {run}/lt1.txt | python3"}, "/", 2),
    ("a printed script command on the run folder", "Bash",
     {"command": "cd {home}/.claude/skills/ops-weekly-tracker && python3 scripts/proposals.py live-plan --dir {run}"}, "/", 0),
    ("a module that reads the run folder", "Bash", {"command": "python3 -m json.tool {run}/decided.json"}, "/", 0),
    ("inline Python on Claude Code's own tool results", "Bash",
     {"command": "python3 -c \"import json; t=json.load(open('{home}/.claude/projects/-/abc/tool-results/x.txt'))\""}, "/", 0),
]


def run_hook(event, mode, tid=TID, config=None, raw=None, private=None, capture=None, state=None):
    import subprocess
    env = dict(os.environ)
    env.pop("ZYNKR_TRACKER_GUARD_ID", None)
    env.pop("ZYNKR_OPS_WEEKLY_PRIVATE_DIR", None)
    env.pop(CAPTURE_ENV, None)
    env["ZYNKR_OPS_WEEKLY_MODE"] = mode
    if tid:
        env["ZYNKR_TRACKER_GUARD_ID"] = tid
    if config:
        env["ZYNKR_OPS_WEEKLY_CONFIG"] = config
    if capture:
        env[CAPTURE_ENV] = capture
    if state:
        env["ZYNKR_OPS_WEEKLY_STATE"] = state
    if private:
        env["ZYNKR_OPS_WEEKLY_PRIVATE_DIR"] = private
        env["HOME"] = HOME
    data = raw if raw is not None else json.dumps(event)
    p = subprocess.run([sys.executable, os.path.abspath(__file__)], input=data, env=env,
                       capture_output=True, text=True)
    return p.returncode


def capture_cases():
    """CAPTURE_CASES, each run with and without the capture folder: without it, nothing changes."""
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="guard-capture-")
    out = []
    try:
        state = os.path.join(tmp, "state")
        run, cap = os.path.join(state, "runs", "2026-W45-apply-1"), os.path.join(state, "capture")
        os.makedirs(run)
        os.makedirs(cap)
        with open(os.path.join(cap, "0" * 32 + ".json"), "w", encoding="utf-8") as f:
            json.dump({"tool": "mcp__google-workspace__read_sheet_values", "args": {},
                       "save": [os.path.join(run, "lt1.txt")],
                       "printed": [os.path.join(run, "lt0.txt"), os.path.join(run, "lt1.txt")]}, f)
        home = os.path.expanduser("~")

        def fill(x):
            if isinstance(x, dict):
                return {k: fill(v) for k, v in x.items()}
            return x.replace("{run}", run).replace("{state}", state).replace("{cap}", cap).replace("{home}", home)

        for name, tool, args, cwd, want in CAPTURE_CASES:
            event = {"tool_name": tool, "tool_input": fill(args), "cwd": fill(cwd)}
            out.append((name, run_hook(event, "apply", capture=cap, state=state), want))
            out.append((name + ", outside the runner", run_hook(event, "apply", state=state), 0))
        old = os.environ.get(CAPTURE_ENV)
        os.environ[CAPTURE_ENV] = cap
        try:
            said = decide({"tool_name": "Bash", "tool_input": {"command": "cat > wr.txt <<'X'\n" + TID + "\nX"}},
                          TID, "apply") or ""
        finally:
            if old is None:
                os.environ.pop(CAPTURE_ENV, None)
            else:
                os.environ[CAPTURE_ENV] = old
        out.append(("under the runner a Bash refusal offers no hand save", "Write tool" in said or "runner saves" not in said, False))
        set_state = os.environ.pop("ZYNKR_OPS_WEEKLY_STATE", None)
        try:
            default = state_folder()
        finally:
            if set_state is not None:
                os.environ["ZYNKR_OPS_WEEKLY_STATE"] = set_state
        out.append(("the guard's state folder is the scripts' default (ledger.state_dir)", default,
                    os.path.normpath(os.path.expanduser("~/.local/state/zynkr/ops-weekly")).lower()))
        # the names the guard shares with ledger.py, where both skills are installed side by side
        lp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "zynkr-ops-weekly", "scripts", "ledger.py")
        if os.path.exists(lp):
            lt = open(lp, encoding="utf-8").read()
            names = [re.search(r'^%s = "([^"]+)"' % n, lt, re.M) for n in ("CAPTURE_ENV", "RUN_MARK")]
            out.append(("the capture setting and the runner's note are named as ledger.py names them",
                        [m.group(1) if m else None for m in names], [CAPTURE_ENV, RUN_MARK]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


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
        ("a Bash refusal offers the Write-tool retry",
         "Write tool" in (decide({"tool_name": "Bash", "tool_input": {"command": "cat > wr.txt <<'X'\n" + TID + "\nX"}},
                                 TID, "apply") or ""), True),
        ("a tracker write refusal says do not retry",
         "Do not retry" in (decide({"tool_name": GW + "modify_sheet_values", "tool_input": {"spreadsheet_id": TID}},
                                   TID, "snapshot") or ""), True),
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
    extra += capture_cases()
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
    ("any number of rows passes in apply", [('and 1 <= args["insert_rows"] <= 40):', "):")]),
    ("resize keys not checked", [("set(args) <= RESIZE_KEYS", "True")]),
    ("the 備註 append runs in every beat", [('if mode == "apply" and notes_command(', 'if notes_command(')]),
    ("the 備註 append in any shape", [('if mode == "apply" and notes_command(str(args.get("command", ""))):',
                                       'if mode == "apply":')]),
    ("chained commands pass", [('if re.search(r"[;&|<>`$\\n]", command):', "if False:")]),
    ("a look-alike path passes", [('bool(NOTES_PATH.search(words[1]))', 'words[1].endswith("notes_append.py")')]),
    ("reads no longer exempt", [
        ("if not hit or is_read(tool):", "if not hit:")]),
    ("a Bash refusal says do not retry", [
        ('    if tool == "Bash":\n        # W41 and W42', '    if False:\n        # W41 and W42')]),
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
    ("case matters", [
        ('    return os.path.normpath(re.sub(r"^/+", "/", w)).lower()', '    return os.path.normpath(re.sub(r"^/+", "/", w))')]),
    (".. not folded", [
        ('    return os.path.normpath(re.sub(r"^/+", "/", w)).lower()', '    return re.sub(r"^/+", "/", w).lower()')]),
    ("doubled slashes kept", [
        ('os.path.normpath(re.sub(r"^/+", "/", w))', "os.path.normpath(w)")]),
    ("quotes not undone", [
        ("        return list(lex)", "        return command.split()")]),
    ("--flag=path not split", [
        ('    return words + [w.split("=", 1)[1] for w in words if "=" in w]', "    return words")]),
    ("relative words dropped", [
        ("        w = os.path.join(cwd, w)", '        return ""')]),
    ("wildcards ignored", [
        ("    if any(c in path for c in WILDCARD):\n        start = fixed_part(path)",
         "    if False:\n        start = fixed_part(path)")]),
    ("ancestors not checked", [
        ("    return under(folder, path) and under(path, home)", "    return False")]),
    ("ancestors outside home refused", [
        ("    return under(folder, path) and under(path, home)", "    return under(folder, path)")]),
    ("Grep and Glob roots not checked", [
        ('    if not hit and tool in ("Grep", "Glob"):', "    if False:")]),
    ("wildcard ancestors above home refused", [
        ("        return under(start, folder) or (under(folder, start) and under(start, home))",
         "        return under(start, folder) or under(folder, start)")]),
    ("a Glob root ignores its pattern", [
        ("            root = fixed_part(as_path(glob_at, cwd)) if glob_at else \"\"", '            root = ""')]),
    ("a pathless Grep ignores cwd", [
        ('root = as_path(args.get("path") or cwd or "", cwd)', 'root = as_path(args.get("path") or "", cwd)')]),
    ("a relative Glob ignores its path", [
        ('pattern if pattern.startswith(("/", "~", "$")) or not base else os.path.join(base, pattern)', "pattern")]),
    ("private: payload fields checked too", [
        ("    words = pathish_values(args)\n", "    words = pathish_values(args, True)\n")]),
    ("file:// URLs not unwrapped", [
        ('    w = re.sub(r"^file://", "", word.strip())', "    w = word.strip()")]),
    ("lists under a path field skipped", [
        ("    elif isinstance(node, list):", "    elif False:")]),
    ("$'…' not decoded", [
        ("    command = ANSI_C.sub(_ansi_c, command).replace('$\"', '\"')", "    pass")]),
    ("~+ not expanded", [
        ('        w = re.sub(r"^~\\+(?=/|$)", lambda m: cwd, w)', "        pass")]),
    ("$PWD not expanded", [
        ('        w = re.sub(r"\\$\\{PWD\\}|\\$PWD\\b", lambda m: cwd, w)', "        pass")]),
    ("cd not followed", [
        ('                here = home if not nxt or nxt in (";", "&&", "||", "|", "&") else (as_path(nxt, here) or here)',
         "                pass")]),
    ("a bare cd stays put", [
        ('here = home if not nxt or nxt in (";", "&&", "||", "|", "&") else (as_path(nxt, here) or here)',
         'here = here if not nxt or nxt in (";", "&&", "||", "|", "&") else (as_path(nxt, here) or here)')]),
    ("raw text not searched", [
        ("    if not hit:\n        texts = pathish_values(args)", "    if False:\n        texts = pathish_values(args)")]),
    ("raw text: ancestors not searched", [
        ("    above = os.path.dirname(folder)\n    while above and under(above, home):",
         "    above = os.path.dirname(folder)\n    while False:")]),
    ("raw text: case matters", [
        ('        if re.search(START + re.escape(s) + r"(?:" + ENDS + "|/)", text, re.I):',
         '        if re.search(START + re.escape(s) + r"(?:" + ENDS + "|/)", text):')]),
    ("MCP calls not checked", [
        ("    if not folder:\n        return None\n    home",
         '    if not folder or (event.get("tool_name") or "").startswith("mcp__"):\n        return None\n    home')]),
    ("a private refusal exits 0", [
        ("        print(preason, file=sys.stderr)\n        return 2", "        print(preason, file=sys.stderr)\n        return 0")]),
    ("private check after the config", [
        ("    try:\n        preason = private_reason(event)", "    tracker_id()\n    try:\n        preason = private_reason(event)")]),
    ("a path printed before may be written", [('        for key in ("save", "printed"):', '        for key in ("save",):')]),
    ("a saved result may be rewritten", [("        if p and p in saved_paths(cap):", "        if False:")]),
    ("a saved path read without the cwd", [('        p = as_path(fp, cwd) if isinstance(fp, str) else ""',
                                            '        p = as_path(fp, "") if isinstance(fp, str) else ""')]),
    ("the capture folder writable", [("        if p and under(p, capf):", "        if False:")]),
    ("Python may be written", [('        if name.endswith(".py"):', "        if False:")]),
    ("a relative .py with no cwd may be written", [('        name = p or (fp.strip().lower() if isinstance(fp, str) else "")', "        name = p")]),
    ("a reading command's words never data", [("    return j < i and os.path.basename(words[j]) in DATA_COMMANDS", "    return False")]),
    ("a backtick read as data", [('    if any("`" in w for w in words):\n        return False', '    if False:\n        return False')]),
    ("every word after a reading command data", [("    if any(os.path.basename(w) in RUNS_TEXT for w in words):\n        return False", "    if False:\n        return False")]),
    ("a line break joins two commands", [('punctuation_chars=";&|()<>\\n" if lines else True)', 'punctuation_chars=True)')]),
    ("a process substitution not a command", [(' or word.endswith("("))', ")")]),
    ("python3 --version read as code", [("        if kind == \"m\" or info:", "        if kind == \"m\":")]),
    ("--check-hash-based-pycs takes no argument", [("                if flag in PY_LONG_ARG:\n                    j += 1", "                if False:\n                    j += 1")]),
    ("the capture folder reachable from Bash", [("        if command_reaches(command, cwd, capf):", "        if False:")]),
    ("-c not seen", [('        if kind == "c":\n            return True', '        if False:\n            return True')]),
    ("-c seen only last among joined flags", [('                if ch in "cm":', '                if ch in "cm" and k == len(flag) - 1:')]),
    ("-W's argument taken for the script", [("                    if k == len(flag) - 1:\n                        j += 1",
                                              "                    if False:\n                        j += 1")]),
    ("a heredoc or a pipe not seen", [('        if nxt in ("", "-") or ends_command(nxt) or nxt in SHELL_STOPS or re.match(r"^/(?:dev|proc)/", nxt):\n            return True',
                                         "        if False:\n            return True")]),
    ("/dev/stdin taken for a script", [(' or re.match(r"^/(?:dev|proc)/", nxt):', ":")]),
    ("--flag=value extras read in order", [("    words = shell_tokens(command, lines=True)\n    for i, w in enumerate(words):\n        if not PYTHON_WORD",
                                            "    words = shell_words(command)\n    for i, w in enumerate(words):\n        if not PYTHON_WORD")]),
    ("inline Python anywhere refused", [("        if inline_python(command) and command_reaches(command, cwd, state_folder()):",
                                         "        if inline_python(command):")]),
    ("inline Python on the state folder runs", [("        if inline_python(command) and command_reaches(command, cwd, state_folder()):",
                                                 "        if False:")]),
    ("the loop's env vars not seen", [("        if LOOP_ENV.search(command):", "        if False:")]),
    ("a cleared environment not seen", [("        if clears_env(command):", "        if False:")]),
    ("env -u not seen", [('            if (is_env and ("i" in f[1:] or "u" in f[1:])) or', '            if (is_env and "i" in f[1:]) or')]),
    ("env - not seen", [('            if f == "-" and is_env:\n                return True', '            if False:\n                return True')]),
    ("exec -c not seen", [(' or (not is_env and "c" in f[1:]):', ':')]),
    ("--unset not seen", [('in ("--ignore-environment", "--unset"):', 'in ("--ignore-environment",):')]),
    ("the runner's note writable", [("        if p and os.path.basename(p) == RUN_MARK:", "        if False:")]),
    ("the runner's note reachable from Bash", [("        if RUN_MARK in command:", "        if False:")]),
    ("the rules apply outside the runner", [('    cap = capture_dir()\n    if not cap:\n        return None\n    capf = as_path(cap, "")',
                                             '    cap = capture_dir()\n    capf = as_path(cap, "") if cap else "/no-capture-folder"')]),
    ("a saved-result refusal exits 0", [("        print(creason, file=sys.stderr)\n        return 2",
                                         "        print(creason, file=sys.stderr)\n        return 0")]),
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
