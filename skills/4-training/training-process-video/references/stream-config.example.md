# stream-config.md — example (shape only)

`training-process-video` finds each training stream by the `stream-config.md` in its folder under `<your-training-design-root>/`, and reads it once you pick the stream (Step 0). This file shows the shape, with blanks only.

The real files live in those stream folders, **outside this repository**. They hold the ids of live Drive folders, Docs and Sheets, so never commit one here (`.gitignore` ignores the name). A value left as `TODO` skips the step that needs it.

## Stream

- `course_outline`: `<file name of the course outline in this folder>`
- `chapter_prefix`: `<prefix of the chapter files>` — the chapter files are `<chapter_prefix>-ch1.md` to `<chapter_prefix>-ch<chapter_count>.md`
- `chapter_count`: `<number of chapter files>`
- `recap_folder_id`: `<Drive folder id for course recaps>` or `TODO` (skips the upload)
- `roster_folder_id`: `<Drive folder id for participant roster Sheets>` or `TODO` (skips Gate F)
- `roster_input_folder_id`: `<Drive folder id where a shortcut to each roster is made>` or `TODO` (skips the shortcut)
- `kit_tag_prefix`: `<Kit tag prefix for this stream>` or `TODO` (skips Gate F.5)

## Google Workspace Sync Map

After you approve a gate, the skill pushes the change: each Doc is overwritten with its local file, and the Content Matrix Sheet gets the new rows appended. `TODO` skips that sync.

| local file | Google document | id |
|---|---|---|
| `knowledge-base/qa-master.md` | QA Master KB (Doc) | `<doc id>` or `TODO` |
| `<course_outline>` | course outline (Doc) | `<doc id>` or `TODO` |
| `<chapter_prefix>-ch1.md` | chapter 1 (Doc) | `<doc id>` or `TODO` |
| one row per chapter, through `ch<chapter_count>` | | |
| `content-matrix/_matrix.md` and `content-matrix/_sourcing-log.md` | Content Matrix (Sheet, tabs `matrix` and `sourcing-log`) | `<sheet id>` or `TODO` |

## kb_taxonomy

One entry per chapter, `ch1` to `ch<chapter_count>`, each saying what that chapter covers. The QA agent files each Q&A entry under one of them, as a category named `ch<N>-<short-label>`, or under `general` when none fits.

- `ch1`: `<what chapter 1 covers>`
- `ch2`: `<what chapter 2 covers>`
- one line per chapter, through `ch<chapter_count>`
