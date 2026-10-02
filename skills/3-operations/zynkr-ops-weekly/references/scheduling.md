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
| `snapshot` | Fri → Sun | Fri 18:05 | Sun 23:00 | Saturday and Sunday catch up a closed lid. It stops at 23:00 so no run is still going when the ISO week changes at Monday 00:00 |

A window is a **catch-up range**, not a repeat: the beat runs at most once per ISO week. The
stamp (`~/.local/state/zynkr/ops-weekly/<ISO-week>.<beat>.done`) is written **only when the run's
receipt says `status=ok`** and `claude` exited 0. Any other run counts an attempt and is retried
on the next tick while its window is still open; after three attempts it writes `.gaveup` and
stops for the week. A missed beat is better than a beat that fires into the wrong day.

**Time limit.** `snapshot` runs under a 30-minute limit. When it is reached, the runner ends the
run and everything it started, logs `TIMEOUT`, and counts a failed attempt. Without a limit a hung
run blocks every later tick, because launchd never starts a second copy of the runner while one is
still going. The other beats get limits once their normal run times are measured (`SKB-044` Phase 2).

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

## Installing

```sh
cp scripts/run_ops_weekly.sh ~/.claude/skills/zynkr-ops-weekly/
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
