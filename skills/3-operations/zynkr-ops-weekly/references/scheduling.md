# Scheduling the seven beats

The skill half runs on **launchd**, on Peter's Mac. The Apps Script `scaffold` half is separate
and documented in `scaffold.md`.

## Why not a claude.ai cloud routine

The obvious home for a weekly job is a cloud routine (`/schedule`), the way `zynkr-gm` runs. It
does not work here, for three independent reasons — any one of them is fatal:

1. **There is no Google Chat connector.** The available connectors are Lucid, Google Drive,
   Canva, Gmail and Google Calendar. Four of the six beats *post to the space* and `rollup`
   *reads* it. Chat exists only in the local `google-workspace` MCP server. (`tidy` and
   `snapshot` touch neither Chat nor mail: `tidy` only writes the Doc, `snapshot` only the Ledger.)
2. **The cloud sandbox cannot read the private config.** Every identifier lives in
   `~/.config/zynkr/ops-weekly.json` on disk, precisely because this repo is public. A cloud
   agent has no local filesystem, and the skill fails loud on a missing config rather than guess.
3. **The Drive connector cannot do the Doc writes.** `rollup` inserts a marked block into one
   section of a tabbed Doc without disturbing the owner person-chips. The Drive connector reads
   files and creates files; it does not expose the Docs structural API.

`zynkr-gm` is not a counter-example: it only ever *reads* Drive and *sends* Gmail, both of which
have connectors.

## Why a heartbeat instead of seven timed jobs

The beats are anchored to **Asia/Taipei** — the company's clock. The Mac is not: it is
currently Europe/Amsterdam, six hours behind. `StartCalendarInterval` has **no timezone field**;
it always fires in machine-local time. A plist that said `Hour 22` for `decisions` would fire at
**04:00 Friday Taipei** — after the 23:00 scaffold, against the wrong week, and `decisions`
*mails every owner-chip address*. That is a wrong email to the whole team, not a stale line.

So launchd supplies only a heartbeat — `:05` and `:35` every hour — and
`scripts/run_ops_weekly.sh` decides in Taipei time whether a beat is due. Fly home and nothing
needs re-timing. With no beat due the script exits in milliseconds without starting Claude.

## The beat windows

| Beat | Day (Taipei) | Fires | Window closes | Notes |
|---|---|---|---|---|
| `recap` | Mon | 09:05 | 20:00 | Listed first, so it never queues behind a slow `nudge`. 30-minute limit |
| `nudge` | Mon | 09:05 | 20:00 | Also asserts last Thursday's scaffold landed |
| `rollup` | Tue | 09:05 | 20:00 | |
| `chase` | Tue | 09:35 | 20:00 | Never selected until `rollup` is stamped |
| `agenda` | Wed | 17:05 | 23:00 | |
| `decisions` | Thu | 22:05 | 23:59 | After the 21:00 meeting, before the 23:00 scaffold |
| `tidy` | Fri | 09:05 | 20:00 | The first morning after the Thursday scaffold |
| `propose` | Fri | 10:05 | 17:30 | After `tidy`, which comes first in the list. 30-minute limit |
| `snapshot` | Fri → Sun | Fri 18:05 | Sun 23:00 | Saturday and Sunday catch up a closed lid. It stops at 23:00 so no run is still going when the ISO week changes at Monday 00:00 |
| `apply` | Fri → Sun | Fri 18:05 | Sun 23:00 | After `snapshot`. No prerequisite: it reads this week's `Weeks` row itself, so a `propose` that recorded and mailed but then gave up still has its answer read. Waits for the owner reply: a `waiting` receipt stamps nothing and clears the attempt count (a run that read the thread proves the beat works, so failures before it do not add up to giving up); the next look is two hours after the `.waiting` stamp was last written (its mtime), and from Sunday 21:00 every tick looks, because the mail promises that replies before 22:00 count. 20-minute limit |

A window is a **catch-up range**, not a repeat: the beat runs at most once per ISO week. The
stamp (`~/.local/state/zynkr/ops-weekly/<ISO-week>.<beat>.done`) is written **only when the run's
receipt says `status=ok`** and `claude` exited 0. Any other run counts an attempt and is retried
on the next tick while its window is still open; after three attempts it writes `.gaveup` and
stops for the week. A missed beat is better than a beat that fires into the wrong day.

**Time limits.** Every beat but `rollup` runs under a limit: `recap`, `snapshot` and `propose` 30 minutes, `apply` 20,
`nudge` and `decisions` 20, `chase` 15, `agenda` 40, `tidy` 45. When one is reached, the runner
ends the run and everything it started, logs `TIMEOUT`, and counts a failed attempt, so the next
tick retries it. Without a limit a hung run blocks every later tick, because launchd never starts
a second copy of the runner while one is still going.

They were set on 2026-10-02 (`SKB-044` 2.6a) from the runs logged since August. A normal run takes
minutes: `nudge` 5, `chase` 4, `agenda` up to 17, `decisions` 6, `tidy` up to 15. The long runs
were hangs: a `nudge` stuck 174 minutes on a Docs API timeout, a `decisions` run stuck 176 minutes
on a network error, and the retry after each finished in minutes. Each limit is two to four times
the longest normal run. `decisions` gets 20 minutes so three attempts still fit between 22:00 and
23:59. `rollup` gets none until its Doc reads stop pulling all 331k characters (`SKB-044` 2.6):
its successful runs have taken hours.

## Least privilege

Each beat is invoked with only the tools it needs. `decisions` is the **only** beat given
`send_gmail_message`; `rollup` cannot post to the space; `status` is read-only. An unattended
agent that can post to a team space should not also be able to mail the team.

**An allowlist pre-approves; it does not forbid.** With Claude Code's permission mode set to
`auto`, `--allowedTools` only saves the run from asking. Any other tool can still be used if the
automatic check lets it through. So `snapshot`, the first beat that writes a Sheet, also gets a
`--disallowedTools` list: every Chat, Doc, mail and Drive write tool, and every other MCP
server. `rollup` and `decisions`, which now also write their weekly block into the Ledger, get the
same list minus the tools each one needs (`rollup` keeps the Doc writes; `decisions` keeps Chat,
Doc and mail). Hardening the remaining beats is `SKB-044` step 2.6.

**The tracker guard (`SKB-044` AC-3.5, since 2026-10-04).** Every beat also runs with a PreToolUse
hook, `scripts/tracker_guard.py`, passed through `--settings`, so the owner's own settings and hooks
still apply. It refuses any tool call aimed at the Main Tracker, meaning the tracker id in a
`spreadsheet_id`, `fileId` or other id field, or anywhere in a Bash command, unless the call only
reads or the beat is `apply` calling `modify_sheet_values`. A link to the tracker inside a mail body,
a Doc or a Ledger row is not a target, so it passes. A hook refusal holds in every permission mode,
which the lists above cannot promise. An error inside the guard refuses every call but a read, and a
missing guard stops the runner before the beat starts.

## Installing

```sh
cp scripts/run_ops_weekly.sh scripts/tracker_guard.py ~/.claude/skills/zynkr-ops-weekly/
chmod +x ~/.claude/skills/zynkr-ops-weekly/run_ops_weekly.sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.zynkr.ops-weekly.plist
```

Verify without side effects — `run_ops_weekly.sh --dry-run` prints the beat that is due now (or
nothing), and `--dry-run --mode=<beat>` prints the exact tool allowlist that beat would get, its
deny list, time limit and prompt.

**Never force a beat (`--mode=<beat>`) before that week's unforced run.** A forced run that
receipts `ok` stamps the week, so the scheduled run never fires and the wiring is never proven.
To rehearse, point the runner somewhere else: `ZYNKR_OPS_WEEKLY_CONFIG`, `ZYNKR_OPS_WEEKLY_STATE`
and `ZYNKR_OPS_WEEKLY_LOG` override the config, the stamp folder and the log. For `snapshot`, a
non-default config is also passed on to the skill as `config=<path>`, so the rehearsal writes to
the rehearsal Ledger.

**Installing mid-week:** seal the current week first, or the next open window fires a beat against
a week that never had a `rollup`:

```sh
W=$(TZ=Asia/Taipei python3 -c "import datetime,zoneinfo;y,w,_=datetime.datetime.now(zoneinfo.ZoneInfo('Asia/Taipei')).isocalendar();print(f'{y}-W{w:02d}')")
for m in nudge rollup chase agenda decisions; do echo skipped > ~/.local/state/zynkr/ops-weekly/$W.$m.done; done
```

Never add `snapshot` to that loop. A snapshot taken mid-week is still a true copy of the tracker,
and sealing it would leave the week with no snapshot at all.

`decisions` carries its own guard for this case (it refuses to recap a week with no `〔自動彙整〕`
stamp), but the seal is what keeps `agenda` from posting an agenda built from nothing.
