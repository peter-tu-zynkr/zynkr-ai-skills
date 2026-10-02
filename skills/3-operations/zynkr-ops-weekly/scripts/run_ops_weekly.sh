#!/bin/bash
# Zynkr — 營運每週彙報 scheduled runner (the skill half; the Apps Script scaffold is separate).
#
# WHY A TICK INSTEAD OF FIVE TIMED JOBS
#   The five beats are anchored to Asia/Taipei (the company's clock) but this Mac is not:
#   it is currently Europe/Amsterdam, six hours behind. launchd's StartCalendarInterval has
#   no timezone field — it always fires in MACHINE local time — so a plist that says 22:00
#   would put `decisions` at 04:00 Friday Taipei: after the 23:00 scaffold, into the wrong
#   week, and it MAILS THE WHOLE TEAM. So launchd only supplies a heartbeat (:05 and :35 every
#   hour) and this script decides, in Taipei time, whether a beat is due. Fly home to Taipei
#   and nothing needs changing.
#
# WHY IT IS SAFE TO RUN 48x A DAY
#   No beat due => exits in milliseconds without starting Claude. A beat runs at most once per
#   ISO week (stamp files in STATE_DIR). The stamp is written only when the run RECEIPTS itself
#   as ok, so a failed run retries on the next tick while its window is still open, and gives up
#   after MAX_ATTEMPTS so a permanently-broken beat cannot burn an invocation every 30 minutes.
#
# WHY THE EXIT CODE IS NOT TRUSTED
#   `claude -p` exits 0 even when its answer is "I could not do this". On 2026-08-31 the nudge
#   hit an MCP connection timeout, said so in plain English, and was stamped done 33 minutes
#   later with its window still wide open -- so it never retried and the team got no Monday
#   post. On 2026-09-02 the agenda wrote the Doc, failed its Chat post with a 404, and was also
#   stamped done. Both were recorded as successes. The beat therefore has to say, in a line this
#   script can parse, what it actually delivered; see SKILL.md Step 5.
#
# Usage: run_ops_weekly.sh [--dry-run] [--mode=recap|nudge|rollup|chase|agenda|decisions|tidy|propose|snapshot|apply|status]
#
# Rehearsal overrides: ZYNKR_OPS_WEEKLY_CONFIG, ZYNKR_OPS_WEEKLY_STATE, ZYNKR_OPS_WEEKLY_LOG, and
# ZYNKR_OPS_WEEKLY_NOW (an ISO time the beat selector uses instead of the clock). Never force a
# beat against the real state folder before that week's unforced run: an ok receipt stamps the week.
set -uo pipefail
export PATH="/Users/petertu/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/petertu"

STATE_DIR="${ZYNKR_OPS_WEEKLY_STATE:-$HOME/.local/state/zynkr/ops-weekly}"
LOG="${ZYNKR_OPS_WEEKLY_LOG:-$HOME/Library/Logs/zynkr-ops-weekly.log}"
CFG="${ZYNKR_OPS_WEEKLY_CONFIG:-$HOME/.config/zynkr/ops-weekly.json}"
MAX_ATTEMPTS=3        # give up after this many non-ok runs in one window
mkdir -p "$STATE_DIR" "$(dirname "$LOG")"

DRY=0; FORCE=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --mode=*)  FORCE="${a#--mode=}" ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$LOG"; }

[ -f "$CFG" ] || { log "FATAL config missing: $CFG"; exit 1; }

# ── Which beat, if any, is due right now in Taipei? ──────────────────────────
SEL="$(python3 - "$FORCE" "$STATE_DIR" "${ZYNKR_OPS_WEEKLY_NOW:-}" <<'PY'
import sys, os, datetime, zoneinfo
force, state, fixed = sys.argv[1], sys.argv[2], sys.argv[3]
tz = zoneinfo.ZoneInfo("Asia/Taipei")
now = datetime.datetime.fromisoformat(fixed).astimezone(tz) if fixed else datetime.datetime.now(tz)
y, w, dow = now.isocalendar()
week = f"{y}-W{w:02d}"
done    = lambda m: os.path.exists(os.path.join(state, f"{week}.{m}.done"))
gaveup  = lambda m: os.path.exists(os.path.join(state, f"{week}.{m}.gaveup"))
# Settled = succeeded OR exhausted its retries, so a broken beat stops being selected.
# The prerequisite check below accepts ONLY a real .done: `chase` must never run off
# the back of a `rollup` that gave up, or it will name people whose posts were never
# parsed at all.
settled = lambda m: done(m) or gaveup(m)
# `apply` waits for the owner to answer the approval mail. A waiting receipt stamps nothing, so
# without this the beat would start Claude every 30 minutes all weekend; it looks again 2 hours after
# the stamp was last written (its mtime). The mail promises that a reply before Sunday 22:00 counts,
# so from Sunday 21:00 every tick looks: the last looks are 22:05 and 22:35, before 23:00.
def waiting(m):
    p = os.path.join(state, f"{week}.{m}.waiting")
    if not os.path.exists(p) or (dow == 7 and now.strftime("%H:%M") >= "21:00"):
        return False
    return now.timestamp() - os.path.getmtime(p) < 7200
if force:
    print(f"{force}|{week}|forced (--mode)"); raise SystemExit
hm = now.strftime("%H:%M")
# mode, ISO weekday, window open, window close, prerequisite beat
# `recap` (SKB-044) comes first: one beat runs per tick and nudge has hung for hours, so the
# Monday mail must not queue behind it. It reads only the Ledger and is limited to 30 minutes.
BEATS = [("recap",     1, "09:00", "20:00", None),
         ("nudge",     1, "09:00", "20:00", None),
         ("rollup",    2, "09:00", "20:00", None),
         ("chase",     2, "09:30", "20:00", "rollup"),
         ("agenda",    3, "17:00", "23:00", None),
         ("decisions", 4, "22:00", "23:59", None),
         # `tidy` is Friday because that is the first morning AFTER the Thursday 23:00 scaffold.
         # The scaffold copies the week section forward verbatim, stacked auto blocks and all,
         # so Friday is the moment the duplicates exist and nobody has read them yet. Trimming
         # on Tuesday instead would leave the section fat across the whole weekend and the
         # Monday nudge. It needs no prerequisite: it reads the Doc, not the space.
         ("tidy",      5, "09:00", "20:00", None),
         # `snapshot` (SKB-044) copies the Main Tracker into the Weekly Ledger once per ISO week.
         # Saturday and Sunday catch up a closed lid on Friday evening. Sunday stops at 23:00 so
         # no run is still going when the ISO week (and with it the rows the Ledger uses) changes
         # at Monday 00:00 Taipei. NO APOSTROPHES in this heredoc: bash 3.2 then fails to parse.
         # `propose` (SKB-044 Phase 3) mails the owner the suggested tracker changes for the week. It
         # comes after tidy, reads the Ledger and the tracker, and writes only the Ledger.
         ("propose",   5, "10:00", "17:30", None),
         ("snapshot",  5, "18:00", "23:59", None),
         ("snapshot",  6, "00:00", "23:59", None),
         ("snapshot",  7, "00:00", "23:00", None),
         # `apply` records the owner reply to that mail. Listed after snapshot so the week is captured
         # first. No prerequisite: it reads the Ledger for this week (Weeks column O) itself, so a
         # propose that recorded and mailed but then gave up still has its answer read. In shadow
         # mode it writes nothing to the tracker.
         ("apply",     5, "18:00", "23:59", None),
         ("apply",     6, "00:00", "23:59", None),
         ("apply",     7, "00:00", "23:00", None)]
for mode, d, s, e, req in BEATS:
    if dow != d or not (s <= hm <= e) or settled(mode) or waiting(mode):
        continue
    if req and not done(req):
        print(f"|{week}|{mode} held: {req} has not run this week"); raise SystemExit
    print(f"{mode}|{week}|{now:%a %H:%M} Taipei, window {s}-{e}"); raise SystemExit
print(f"|{week}|nothing due at {now:%a %H:%M} Taipei")
PY
)"
MODE="${SEL%%|*}"; REST="${SEL#*|}"; WEEK="${REST%%|*}"; WHY="${REST#*|}"

if [ -z "$MODE" ]; then
  [ "$DRY" = 1 ] && echo "no beat due — $WHY"
  exit 0
fi

# ── Least privilege: each beat gets only the tools it actually needs ─────────
READ_CORE="Read,Grep,Glob,mcp__google-workspace__list_spaces,mcp__google-workspace__get_messages,mcp__google-workspace__search_messages,mcp__google-workspace__get_doc_as_markdown,mcp__google-workspace__inspect_doc_structure,mcp__google-workspace__read_sheet_values,mcp__google-workspace__get_spreadsheet_info"
CHAT_WRITE="mcp__google-workspace__send_message"
DOC_WRITE="mcp__google-workspace__batch_update_doc,mcp__google-workspace__insert_doc_elements,mcp__google-workspace__modify_doc_text,mcp__google-workspace__find_and_replace_doc,mcp__google-workspace__update_paragraph_style"
MAIL="mcp__google-workspace__send_gmail_message,mcp__google-workspace__search_gmail_messages,mcp__google-workspace__get_gmail_message_content"
# `snapshot` reads the tracker, writes only the Ledger, and saves each tool result to a file for
# scripts/ledger.py. Under the `auto` permission mode an allowlist only pre-approves, so it also
# gets a deny list: every other write tool, and every other MCP server.
SNAP_TOOLS="Read,Write,Bash(python3:*),mcp__google-workspace__read_sheet_values,mcp__google-workspace__get_spreadsheet_info,mcp__google-workspace__modify_sheet_values"
DENY_OTHERS="mcp__google-workspace__draft_gmail_message,mcp__google-workspace__create_spreadsheet,mcp__google-workspace__create_sheet,mcp__google-workspace__resize_sheet_dimensions,mcp__google-workspace__format_sheet_range,mcp__google-workspace__manage_conditional_formatting,mcp__google-workspace__move_sheet_rows,mcp__google-workspace__append_table_rows,mcp__google-workspace__create_drive_file,mcp__google-workspace__update_drive_file,mcp__google-workspace__copy_drive_file,mcp__google-workspace__trash_file,mcp__google-workspace__manage_drive_access,mcp__google-workspace__set_drive_file_permissions,mcp__google-workspace__create_doc,mcp__claude_ai_Gmail,mcp__claude_ai_Google_Drive,mcp__claude_ai_Google_Calendar,mcp__claude_ai_Notion,mcp__claude_ai_Canva,mcp__claude_ai_Lucid,mcp__claude_ai_Claude_Docs,mcp__gmail,mcp__notion,mcp__lucid,mcp__supabase,mcp__vercel,mcp__cms,mcp__zynkr,mcp__zynkr-atlas,mcp__fireflies,mcp__kit,mcp__plugin_playwright_playwright"
SNAP_DENY="Edit,NotebookEdit,Agent,$CHAT_WRITE,$DOC_WRITE,$MAIL,$DENY_OTHERS"
# `rollup` and `decisions` also record what they read in the Ledger (SKB-044 2.2, 2.3), so each
# gains one Sheets write and a deny list without the tools it needs.
LEDGER_WRITE="Write,Bash(python3:*),mcp__google-workspace__modify_sheet_values"
ROLLUP_DENY="Edit,NotebookEdit,Agent,$CHAT_WRITE,$MAIL,$DENY_OTHERS"
DECISIONS_DENY="Edit,NotebookEdit,Agent,$DENY_OTHERS"
# `recap` reads the Ledger and sends one mail. It writes nothing, so even the Sheets write is denied.
RECAP_TOOLS="Read,Write,Bash(python3:*),mcp__google-workspace__read_sheet_values,mcp__google-workspace__get_spreadsheet_info,mcp__google-workspace__send_gmail_message,mcp__google-workspace__search_gmail_messages,mcp__google-workspace__get_gmail_message_content"
RECAP_DENY="Edit,NotebookEdit,Agent,$CHAT_WRITE,$DOC_WRITE,mcp__google-workspace__modify_sheet_values,$DENY_OTHERS"
# `propose` and `apply` (SKB-044 Phase 3) read the tracker and the Ledger, write only Ledger blocks the
# scripts plan, and mail only the owner: the approval mail, and in apply one restate request when a
# reply cannot be read. Neither may post to Chat or touch the Doc.
P3_TOOLS="Read,Write,Bash(python3:*),mcp__google-workspace__read_sheet_values,mcp__google-workspace__get_spreadsheet_info,mcp__google-workspace__modify_sheet_values,mcp__google-workspace__send_gmail_message,mcp__google-workspace__search_gmail_messages,mcp__google-workspace__get_gmail_thread_content"
P3_DENY="Edit,NotebookEdit,Agent,$CHAT_WRITE,$DOC_WRITE,$DENY_OTHERS"

LIMIT=0; DENY=""; PROMPT="/zynkr-ops-weekly $MODE"

# Time limits (SKB-044 2.6a, set 2026-10-02 from the runs logged since August). A normal run takes
# minutes: nudge 5, chase 4, agenda up to 17, decisions 6, tidy up to 15. The long runs were hangs:
# a nudge stuck 174 minutes on a Docs API timeout, a decisions run stuck 176 minutes on a network
# error, a decisions run that only had to confirm an earlier one took 68. The retry after each
# finished in minutes. So each limit is two to four times the longest normal run, and a run that
# reaches it is retried on the next tick like any other failure. decisions gets 20 minutes so three
# attempts still fit between 22:00 and 23:59. rollup has none yet: every Doc read pulls all 331k
# characters and its successful runs have taken hours (SKB-044 2.6).
case "$MODE" in
  nudge)       TOOLS="$READ_CORE,$CHAT_WRITE"; LIMIT=1200 ;;
  chase)       TOOLS="$READ_CORE,$CHAT_WRITE"; LIMIT=900 ;;
  rollup)      TOOLS="$READ_CORE,$DOC_WRITE,$LEDGER_WRITE"; DENY="$ROLLUP_DENY" ;;
  agenda)      TOOLS="$READ_CORE,$CHAT_WRITE,$DOC_WRITE"; LIMIT=2400 ;;
  decisions)   TOOLS="$READ_CORE,$CHAT_WRITE,$DOC_WRITE,$MAIL,$LEDGER_WRITE"; DENY="$DECISIONS_DENY"; LIMIT=1200 ;;   # the only beat that may mail
  # Doc only: it never posts and never mails. The Drive export is the one read that renders the
  # Done/Drop status chips its step 7 needs (SKB-039).
  tidy)        TOOLS="$READ_CORE,$DOC_WRITE,mcp__google-workspace__get_drive_file_content"; LIMIT=2700 ;;
  # The week is passed in, never recomputed mid-run; a non-default config is passed on so a
  # rehearsal writes to the rehearsal Ledger. 30 minutes: a normal run takes a few.
  snapshot)    TOOLS="$SNAP_TOOLS"; DENY="$SNAP_DENY"; LIMIT=1800
               PROMPT="/zynkr-ops-weekly snapshot week=$WEEK"
               [ -n "${ZYNKR_OPS_WEEKLY_CONFIG:-}" ] && PROMPT="$PROMPT config=$CFG" ;;
  recap)       TOOLS="$RECAP_TOOLS"; DENY="$RECAP_DENY"; LIMIT=1800
               PROMPT="/zynkr-ops-weekly recap week=$WEEK"
               [ -n "${ZYNKR_OPS_WEEKLY_CONFIG:-}" ] && PROMPT="$PROMPT config=$CFG" ;;
  propose)     TOOLS="$P3_TOOLS"; DENY="$P3_DENY"; LIMIT=1800
               PROMPT="/zynkr-ops-weekly propose week=$WEEK"
               [ -n "${ZYNKR_OPS_WEEKLY_CONFIG:-}" ] && PROMPT="$PROMPT config=$CFG" ;;
  apply)       TOOLS="$P3_TOOLS"; DENY="$P3_DENY"; LIMIT=1200
               PROMPT="/zynkr-ops-weekly apply week=$WEEK"
               [ -n "${ZYNKR_OPS_WEEKLY_CONFIG:-}" ] && PROMPT="$PROMPT config=$CFG" ;;
  status)      TOOLS="$READ_CORE" ;;
  *) log "FATAL unknown mode: $MODE"; exit 2 ;;
esac

MODEL="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('routine',{}).get('model') or 'sonnet')" "$CFG" 2>/dev/null || echo sonnet)"

if [ "$DRY" = 1 ]; then
  echo "WOULD RUN  mode=$MODE  week=$WEEK  model=$MODEL"
  echo "  why    : $WHY"
  echo "  prompt : $PROMPT"
  echo "  tools  : $TOOLS"
  echo "  deny   : ${DENY:-(none)}"
  echo "  limit  : $([ "$LIMIT" -gt 0 ] && echo "${LIMIT}s" || echo none)"
  echo "  state  : $STATE_DIR"
  exit 0
fi

# Run a command, ending it and everything it started once LIMIT seconds pass (0 = no limit).
# launchd never starts a second runner while one is still going, so one hung run would block
# every later tick. Killing the whole process group also stops the MCP servers it spawned.
run_limited() {
  if [ "$LIMIT" -gt 0 ]; then
    python3 -c '
import os, signal, subprocess, sys
limit, argv = int(sys.argv[1]), sys.argv[2:]
p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, start_new_session=True)
try:
    sys.exit(p.wait(timeout=limit))
except subprocess.TimeoutExpired:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            break
        try:
            p.wait(timeout=15)
            break
        except subprocess.TimeoutExpired:
            pass
    sys.exit(124)
' "$LIMIT" "$@"
  else
    "$@"
  fi
}

log "START mode=$MODE week=$WEEK model=$MODEL ($WHY)"
OUT="$(mktemp -t zynkr-ops-weekly.XXXXXX)"
if [ -n "$DENY" ]; then
  run_limited claude -p "$PROMPT" --model "$MODEL" --allowedTools "$TOOLS" --disallowedTools "$DENY" >"$OUT" 2>&1
else
  run_limited claude -p "$PROMPT" --model "$MODEL" --allowedTools "$TOOLS" >"$OUT" 2>&1
fi
STATUS=$?
[ "$LIMIT" -gt 0 ] && [ "$STATUS" -eq 124 ] && log "TIMEOUT mode=$MODE week=$WEEK after ${LIMIT}s"
cat "$OUT" >> "$LOG"

# ── Assert the side effect; do not trust the exit code ───────────────────────
# The beat ends its report with a machine-readable receipt (SKILL.md Step 5):
#   ZYNKR-OPS-WEEKLY-RESULT: mode=<mode> week=<week> status=ok|partial|failed delivered=<what>
# Only status=ok stamps. A missing receipt is a failure too: it means the run never got far
# enough to report, which is exactly the case the old exit-code check waved through.
RECEIPT="$(grep -a -o 'ZYNKR-OPS-WEEKLY-RESULT:.*' "$OUT" | tail -1)"
rm -f "$OUT"

case "$RECEIPT" in
  *status=ok*) VERDICT="ok" ;;
  *status=waiting*) VERDICT="waiting" ;;
  "")          VERDICT="no-receipt (claude exit=$STATUS)" ;;
  *)           VERDICT="receipt not ok: $RECEIPT" ;;
esac
# `snapshot`, `recap`, `propose` and `apply` must receipt the very week they were given, so a run about
# another week can never stamp this one done.
case "$MODE" in
  snapshot|recap|propose|apply)
    if [ "$VERDICT" = "ok" ] || [ "$VERDICT" = "waiting" ]; then
      case "$RECEIPT" in
        *"mode=$MODE week=$WEEK status=$VERDICT"*) ;;
        *) VERDICT="receipt names another mode or week: $RECEIPT" ;;
      esac
    fi ;;
esac
# Only `apply` may wait (for the owner reply). Waiting stamps nothing and burns no attempt; the
# selector looks again two hours later. Any other beat that says waiting has simply not delivered.
# A waiting run also clears the attempt count: it reached the thread and read it, so failures before
# it say nothing about the next look, and three passing glitches across a weekend must not end it.
if [ "$VERDICT" = "waiting" ]; then
  if [ "$MODE" = "apply" ] && [ $STATUS -eq 0 ]; then
    date '+%Y-%m-%dT%H:%M:%S%z' > "$STATE_DIR/$WEEK.$MODE.waiting"
    rm -f "$STATE_DIR/$WEEK.$MODE.attempts"
    log "WAIT  mode=$MODE week=$WEEK  $RECEIPT (looks again in 2 hours)"
    exit 0
  fi
  VERDICT="receipt not ok: $RECEIPT"
fi

if [ "$VERDICT" = "ok" ] && [ $STATUS -eq 0 ]; then
  date '+%Y-%m-%dT%H:%M:%S%z' > "$STATE_DIR/$WEEK.$MODE.done"
  rm -f "$STATE_DIR/$WEEK.$MODE.attempts" "$STATE_DIR/$WEEK.$MODE.waiting"
  log "OK    mode=$MODE week=$WEEK  $RECEIPT"
  exit 0
fi

ATT="$STATE_DIR/$WEEK.$MODE.attempts"
N=$(( $(cat "$ATT" 2>/dev/null || echo 0) + 1 ))
echo "$N" > "$ATT"

if [ "$N" -ge "$MAX_ATTEMPTS" ]; then
  printf 'gave up after %s attempts: %s\n' "$N" "$VERDICT" > "$STATE_DIR/$WEEK.$MODE.gaveup"
  log "GIVEUP mode=$MODE week=$WEEK attempts=$N — $VERDICT (no further retries this week)"
else
  log "FAIL  mode=$MODE week=$WEEK attempt=$N/$MAX_ATTEMPTS — $VERDICT (retry next tick inside the window)"
fi
exit 1
