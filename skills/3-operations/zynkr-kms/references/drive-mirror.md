# Drive Mirror — the Google Workspace backup of the Atlas 知識庫

The 知識庫 in Zynkr Atlas — the published collection `kb`, browsable at
`https://atlas.zynkr.ai/w/<workspace-slug>/knowledge` — is the **source of truth**. The Google
Drive folder is its **backup mirror**.

## The arrow of truth is one-way

```
Atlas 知識庫 (collection kb)  ──(mirror)──▶  Google Drive Docs
   (SOT · drafts in 審核)                     (read-only backup)
```

- Atlas is **always right**. If Drive and Atlas disagree, Atlas wins.
- Nothing in Drive is ever read back into Atlas. There is no reverse sync, and you must never
  "reconcile" a Drive edit into a card.
- Every mirrored Doc opens with an **AUTO-GENERATED MIRROR — do not edit this Doc** banner naming
  Atlas as SOT. A human edit made in a mirrored Doc is destroyed on the next run.
- `/zynkr-support` and `/sales-inbound` read **Atlas**, never the mirror. The mirror exists so
  the knowledge survives an Atlas incident and stays readable in Drive, nothing more.
- It mirrors **published notes only** — never a draft, an archived note or a company fact
  (`company.*`). A draft zynkr-kms filed shows in the index's 「Waiting in 審核」 list by key and
  title, nothing more.

## Where it lives

| What | Where |
|---|---|
| Mirror folder | `客服知識庫 (KMS) · Atlas 鏡像 · 僅團隊` — ID in `~/.config/zynkr/kms.json` → `mirror_folder_id`, at the top of the owner's My Drive |
| Section Docs | one per section, `Zynkr Support KB — NN <title>` (see registry below) |
| Restore copy | `_KB-SNAPSHOT.json` — a new file every run, so found by name (the newest), never by ID |
| Run manifest | `_MANIFEST.json` — likewise |
| The script | `scripts/kb-drive-mirror.mjs` (v2) |
| Working folder | `~/.workspace-mcp/attachments/kb-mirror/` — kept between runs |

The **section Docs are for humans** (readable, searchable in Drive). The **JSON snapshot is the
restore copy** — it alone holds every note whole: key, kind, title, section (`part_of`), `cites`,
`body_md` and its `sha256`, and the dates. A restore always reads the snapshot, never the Docs.

The working folder sits under `~/.workspace-mcp/attachments/` because the `google-workspace` MCP
uploads only from there. Pass it to the tools as an absolute path. **Drive's `_MANIFEST.json` and
`_KB-SNAPSHOT.json` are the record, never the working folder's copies:** every run, on every
machine, first downloads both over the local ones (zynkr-kms Step 0), so a run on another Mac, or
after a run that stopped half-way, builds on what Drive holds. Each run writes the pair as new files
(Upload, below), so the run finds it by name in the folder, the newest file of each name.

## Who may read it

The mirror copies 僅團隊 (team-only) text out of Atlas, so the folder and every file in it must be
readable by **the workspace's members only** (`D-126`; ATL-114 F-2 and AC-23): no `anyone` link,
no domain grant (it reaches every account in the domain, members or not), no outside reader. The
skill checks this with `get_drive_file_permissions` before every write (Step 0); a folder or file
that reads wider gets nothing written, and Peter fixes its sharing.

**Why the folder stands on its own (since 2026-10-31).** Drive's sharing flows down: whoever can
read a folder can read everything inside it. The company's shared folder, which holds `[5.1]
客服與知識庫 (Support & KB)` (`1LpymoVhy4YrxDBi81Sw6CRQQbZAiSLQ6`, `[3.2] 客服知識庫 (KMS)` until 2026-11-03), is readable by more than the workspace
and stays that way, so no folder inside it can be members-only. The mirror lived in that folder until
then; it now has a folder of its own at the top of the owner's My Drive, outside the company
folder, shared by name with each member. Its files kept their IDs, so the Doc registry below
stands, and `[3.2]` keeps only the KMS building plan. When someone joins the Atlas workspace,
share the folder with them as a reader; when someone leaves, remove them from it, because a reader
who is no longer a member makes the next run write nothing.

## The token

The script reads Atlas with an **export token**: an 「MCP token」 the owner (or an admin) mints in
Atlas's 設定 with 「可以匯出知識（給鏡像用）」 and nothing else. Atlas refuses that box together
with 「可以建立草稿」, so it is never the token zynkr-kms drafts with. It lives in
`~/.config/zynkr/kb-mirror.env`:

```
ATLAS_MCP_TOKEN=zatl_…
```

- `chmod 600` — the script warns when the file is readable by others.
- It expires after 90 days; the owner mints the next one.
- **Never print it, paste it into chat, or pass it on a command line.** The script reads the
  file itself, sends the token only to Atlas, and never prints it: anything shaped like a token
  in a message it prints — a server's words, a mistyped argument — reads `zatl_[REDACTED]`. The
  JSON summary is data, so a key that happens to start `zatl_` comes out whole: only the token
  itself is taken out of it. It
  refuses to send the token to a local copy of Atlas through a proxy, or with TLS checks off
  (`NODE_TLS_REJECT_UNAUTHORIZED=0`).
- Each pull is logged in Atlas as one `export` row — a copy, never counted as a read.

## How a run goes

```bash
node scripts/kb-drive-mirror.mjs --out <working folder> [--full]
```

1. **List** — `list_knowledge(collection: "kb")`, paged, names every published note under `kb`:
   key, kind, title, section, cites and `updated_at`, no text.
2. **Diff** against the `_MANIFEST.json` downloaded from Drive: a note is carried over when its
   `updated_at` is the one the manifest holds and the snapshot's body still hashes to the
   manifest's `sha256`.
3. **Export** — `export_knowledge(collection: "kb", keys: …)` for the changed notes and the root
   `kb`, at most 100 keys a call, paged; `--full` exports everything. Every body's `sha256` is
   computed again and must equal the one Atlas served.
4. **Write**, only once every check has passed: the section Docs that changed, `00-index.md`,
   `_KB-SNAPSHOT.json`, then `_MANIFEST.json` last.
5. **Print** a JSON summary: `mode` (and the reason for a full run), the counts, `upload[]` (the
   files to upload, in order), `pending_published`, `removed`, `removed_sections`, `orphans` and
   `calls`.

It makes at most 50 calls a minute — Atlas counts each tool call twice against its 120 a minute —
and waits once for a minute if Atlas still answers `rate_limited`. Card bodies stay on disk and
never enter context.

**A run is full** with `--full` (`/zynkr-kms mirror`), and by itself when the pair is not one v2
run's: the first run after the move from the CRM (the v1 manifest still maps each section's
number), a v1 file beside a v2 one (the first v2 upload stopped part-way), or a manifest and a
snapshot whose `mirrored_at` differ, because an upload stopped between the two. A full run renders
every Doc and lists each in `upload[]`, and keeps the manifest's `pending[]` and section numbers.
**Half a pair stops the run** before any call — a manifest without its snapshot, a snapshot
without a manifest, or a file that does not parse: a run on it would forget `pending[]` and the
section numbers, or the record of removed notes, and upload that over Drive's. Download both
again.

**Exit codes:** `0` written · `1` refused or failed · `2` bad arguments. On `1` the line it prints
says why, and the upload is skipped:

- **Refused, nothing rewritten:** the token is unset, malformed, expired or revoked (the line
  names `ATLAS_MCP_TOKEN`); the token cannot export; a body did not match its `sha256`; a note the
  list named did not come back in the export; half a pair; a proxy or TLS setting the token must
  not travel through.
- **A write failed** part-way: the working folder may hold a mix of runs, so upload nothing; the
  next run downloads Drive's pair over it and starts again.

Report it either way.

## Upload (Docs in place by ID, the JSON pair as new files)

Upload in `upload[]`'s order, one at a time, and **stop at the first file that fails or is
skipped**: never upload `_KB-SNAPSHOT.json` or `_MANIFEST.json` after a file before them failed,
so Drive's pair never claims a Doc it does not hold. The next run starts from Drive's older pair
and renders those Docs again. For each entry:

- **a section Doc** — `mcp__google-workspace__update_drive_file` with `file_id` from the registry,
  found **by the entry's section key** (never by the number in its file name), `file_path` (its
  absolute path in the working folder), `source_format: "md"` — Drive converts Markdown → native
  Doc, **keeping the Doc ID**, so links, comments and sharing all survive — and `name` set to the
  entry's `doc_title`, so the Doc's name follows its section's title in Atlas;
- **`00-index.md`** — the same way, to the 00 Doc;
- **`_KB-SNAPSHOT.json` and `_MANIFEST.json`** — plain JSON files (`mime_type: "application/json"`),
  which must **never** be converted to Docs. `update_drive_file` rewrites only Google Docs, Sheets
  and Slides, so each is written as a **new file**: `mcp__google-workspace__create_drive_file`
  with `file_name` its name, `folder_id` the mirror folder, the MIME type above and
  `fileUrl: "file://<its absolute path in the working folder>"` — never `content`, which would put
  the snapshot's text into context. A new file takes the folder's readers; check them once it is
  written.

**Then bin the pair they replace.** Once both new files are written, move the pair the run
downloaded, and every older copy of either name, to Drive's bin: `update_drive_file` with
`trashed: true`. Nothing else is ever binned — not a Doc, not `_KB-SNAPSHOT-CRM-<date>.json`. If
either new file failed, bin nothing: the next run downloads the newest of each name, and a manifest
and a snapshot from two runs make that run full by itself (above). The bin keeps a file for 30
days, so the last month's snapshots can still be restored from it. A manifest written again later
in the run (zynkr-kms Steps 6 and 7) is a new file too, and bins the one it replaces.

A section with no Doc yet: `mcp__google-workspace__import_to_google_doc` (`file_name` = its
`doc_title`, `file_path`, `source_format: "md"`, `folder_id` = the mirror folder), then add its ID
to the registry below; until that row lands, find the Doc in the folder by its name. A key in
`removed_sections` — a section no longer published — keeps its Doc: tell Peter, never delete it.

## Doc registry (update in place — never create a second Doc for a section)

| nn | section key | Doc ID |
|---|---|---|
| 00 | _index_ | `1YeOBZqoX98IHENN_rW7rvrqgHjFwZETXjRPShHBE-EE` |
| 01 | `kb.core-facts` | `1R8JoTiIihh4h7Yk3P2GlIgOIzbgSWMNkIzFcmWOzvb0` |
| 02 | `kb.pricing-quoting` | `1iYncrIpUWci2sfPnLDgLm2UHETX5ZXpO93t886ab2EI` |
| 03 | `kb.course-content` | `1Gs2TOjdEOT891TIp9Y69sSfMU5lYyJeExpaIEhO0eTI` |
| 04 | `kb.scheduling-logistics` | `1To4umb0OTVnF9w2yTQox4MG7vquMzOgguLLK7ZWz78w` |
| 05 | `kb.team-training-enterprise` | `1d-DBf57d9FXA6YGPM6KetYpaaNN5vUJDy6OBjri4pGE` |
| 06 | `kb.technical-howto` | `1zdi2gvu_kyPOv2nYQ-56p8UTapnD6DtpBPv4Pp-ZtCQ` |
| 07 | `kb.access-account` | `1j-mHGvFhtWT3Lf6YQIS1Uj4ozqf6uD1TD4N4wCJxiSo` |
| 08 | `kb.refund-policy` | `1WZ6BpuE-zuGUIMANU70VIrvLuaNR-ZHq_RPSMDMPOMg` |
| 09 | `kb.other` | `1ybCHI2afBDuD4qwF8y8QKnH8pryxlSdUG4d04BbLVkY` |
| 10 | `kb.instructor-profile` | `1UaLcJrCa2lzn1j3xoUyhBDpIRKqQUCCFzShL4xirrys` |
| 11 | `kb.brand-product-vision` | `1_rc1go2pqTILElBi-DKbDwOU7xg3ODarh535cc7N6BE` |
| 12 | `kb.ai-workflow-architecture` | `1WukW2HHv6r1TvOR2W0yJYEbtVJONT97kbW6Y24cagAA` |
| 13 | `kb.tone-style` | `1srAumHBnBgKqy3-pSnef-gKRJiXcShLO7vK-6mah7qE` |
| 14 | `kb.gov-subsidy` | `1lTylt4LZB2IyKRGdQwrHIiXGzB5kcXTHr2felmePy_8` |

A new section (Step 5d) gains a Doc — see `new-section-playbook.md` — and a row here.

## `pending[]` — drafts waiting in 審核

`_MANIFEST.json` carries `pending[]`: the drafts zynkr-kms has filed, each
`{key, collection, title, drafted_at}` and the Gmail `thread` it came from. zynkr-kms adds one
right after `draft_note` answers (Step 5). **A key stays in the list until `pending-drop` takes it
out.** Once `list_knowledge` lists it, every run names it in `pending_published` — the index no
longer shows it as waiting — until zynkr-kms has labelled its thread and dropped it (Step 7), so a
run that stops in between loses nothing. A draft Peter rejected is never published, so it is
dropped by hand, and the manifest written again (Step 6):

```bash
node scripts/kb-drive-mirror.mjs pending-drop --out <working folder> --key <key>
```

## Verifying a run

- `counts.cards` must equal the cards the walk lists (`list_knowledge(collection: "kb")`, every
  kind but `collection`), and `counts.sections` the sections it lists (**14** at the move).
- `orphans` must be `0` — a non-zero value means a card is filed under `kb` itself, or under a
  collection no section holds.
- No body is missing: `jq '[.notes[] | select(.body_md == null)] | length' _KB-SNAPSHOT.json` → `0`.
- Spot-check one Doc you just wrote: its `Mirrored:` line should carry this run's time.
- The folder holds one `_MANIFEST.json` and one `_KB-SNAPSHOT.json`, both written by this run and
  both naming its `mirrored_at`, besides the CRM era's file.
- The first run after the move is compared key by key with the import's read-back (ATL-114
  AC-22): `jq -r '.notes[] | [.key, .sha256] | @tsv' _KB-SNAPSHOT.json | sort` must equal it line
  for line.

## Restoring from the mirror

Read the folder's newest `_KB-SNAPSHOT.json` — not the Docs (older ones wait in Drive's bin for
30 days). Every note in it is whole, and each `body_md` must still
hash to its `sha256`. Re-create the collections first (`kb`, then the sections), then the facts,
then the reference cards, so every `part_of` and `cites` resolves, and keep each key exactly. A
restore is an operator's job in Atlas, never this skill's through `draft_note`.

The snapshot's `removed[]` names, by key and title only, the notes that stopped being published
since the mirror began reading Atlas — never their text.

> **History:** until ATL-114 the mirror (v1) read the CRM's 知識庫 tables directly and had to be
> scoped to one workspace by hand; that script is in git history. v2 reads Atlas through MCP,
> where the token's own workspace is the only one it can see. After the move the folder also
> holds `_KB-SNAPSHOT-CRM-<date>.json`, the CRM era's last snapshot: kept as it is, never
> rewritten or binned. v2's first text told the run to rewrite the JSON pair in place, which the
> Drive tool refuses for a JSON file, so the pair written on 26 Aug was never updated; each run
> now writes the pair as new files.
