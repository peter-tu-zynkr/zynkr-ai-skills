# zynkr-ops-weekly private config

- **Private. Never commit.** The real file holds a Doc id, a Chat space id, six permanent Google
  user ids and everyone's email. This repo is public, so only the placeholder
  `config.example.json` lives here.
- Location: `~/.config/zynkr/ops-weekly.json` (override with `ZYNKR_OPS_WEEKLY_CONFIG`). Create
  it by copying the example and filling every `<...>`.
- Loaded at Step 1 of **every** run. A missing or still-placeholder value → **fail loud**
  (`config: doc.id unset`). Never guess an id: a wrong Doc id writes a bot block into somebody
  else's file, and a wrong space id posts a nudge to the wrong room.
- `space.id` **must** carry the `spaces/` prefix. A bare id is rejected by `get_messages` with a
  pattern error — this is the first thing to check when a sweep returns nothing.
- `doc.archive_tab_id` must be a **tab in the same Doc**, not another file. `carryover.py` reads
  every tab as one stream to compute `↻N週`; moving history to a separate document resets every
  streak to zero and silently blinds the Thursday agenda. Verified 2026-09-15 by simulating
  3 live + 31 archived sections: 46 sections compared, **0 streaks changed**. Unset → `tidy`
  fails loud rather than deleting blocks it cannot archive.
- `sources.weekly_insights` (SKB-070) is optional. With it, Thursday's `agenda` waits until
  `wait_until` for the owner's weekly-insights recap of the same ISO week and reads the
  work-only `meeting.json` the runner copies out of `dir`. Every beat's guard then refuses any
  other read in that folder, so keep `dir` pointing at the weekly-insights `out_dir` and nowhere
  broader. Without it the agenda runs as before, on the posts and the tracker alone.
- `routine.notice_from` (SKB-070) switches on the missed-beat mail to the owner from that ISO
  week. Set it to the week you install: an earlier week holds beats that predate their own code
  (the Weekly Ledger beats did not exist before 2026-W40) and each would be reported as missed.
- `chat_ids` is the only hardcoded map, by necessity: Chat exposes **no email field at all**, the
  Doc exposes email with no user id, and the People API resolves the id but returns no name or
  email for domain profiles. Everything else — which department belongs to whom, who receives the
  recap mail — is read from the Doc's owner chips at run time.
- **Two key forms, and you need both.** The MCP renders a sender as a **display name** when that
  person is in the account's personal Contacts, and as `users/<21-digit id>` when they are not.
  So the same space yields a mix — verified 2026-08-24, where three of six reporters came back as
  names and three as ids. Key each person by the form their messages actually arrive as; keeping
  both entries is harmless and means nothing breaks the day somebody is added to Contacts.
- To pin an unknown id: find where someone **@-mentions a name in a thread** and see which id
  replies in that same thread. @-mentions render as names even when the sender does not.
- Adding a person: add their `chat_ids` row **and** put their chip on a Doc heading. Only the
  first is a code change; the second is what actually routes them.
- Removing a person: drop them from `reporters` so `chase` stops naming them. Old Doc sections
  keep their chips — that is history, leave it.
- Rotate: when the Doc is renamed or moved, or a trigger is recreated, edit only this file. No
  skill file changes.
- `sources.ledger.id` is the machine-owned Weekly Ledger (`SKB-044`, `ledger.md`). It must never
  equal `sources.main_tracker.id`; `ledger.py` refuses when it does. `sources.ledger.epoch_week`
  is the ISO week of the first snapshot, and **it never changes afterwards**: every week's rows in
  the Ledger are computed from it.
- `sources.main_tracker.cycle` (e.g. `2026H2`) labels whose item numbers these are. When the next
  half-year's tracker reuses `1.03`, a new cycle keeps the two apart in the Ledger.
- `routine.recap_audience` decides who receives the Monday recap: `owner` (the account alone) or
  `team` (every address in `reporters`). A missing or unknown value means `owner`, so the team only
  ever receives a recap the owner switched on.
- `routine.recap_team_from` (`YYYY-MM-DD`, optional) sets that switch ahead of time: with
  `recap_audience: team`, recaps before that Monday still go to the owner alone, and the team gets
  the recap of that Monday onward. A date that cannot be read keeps the recap with the owner.
- `routine.apply_mode` decides what `apply` does with an approved change: `shadow` records the
  decision in the Ledger and writes nothing to the Main Tracker; only the exact value `live` writes
  (Phase 3b, refused until it ships). Anything else, or nothing, means `shadow`.
- Rehearsal: a copy of this file whose `sources.ledger.id` points at a throwaway Ledger, passed
  with `ZYNKR_OPS_WEEKLY_CONFIG`. Delete both afterwards.
