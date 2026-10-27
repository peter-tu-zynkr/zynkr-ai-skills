# references

The core's references, which the whole weekly loop reads (SKB-091): `ops-weekly-doc` and
`ops-weekly-tracker` read them here, as `<core>/references/…`, and keep no copy.

| File | What it settles |
|---|---|
| `config.example.json` · `config.README.md` | The private runtime config — schema, placeholders, rotation |
| `routing.md` | Reading owner person-chips out of the Doc; the Monday→Thursday off-by-one |
| `message-templates.md` | The recap mail, the approval mail, and the in-run failure notice |
| `wording.md` | The house voice for every zh-TW line the team reads, and the frozen strings |
| `ledger.md` | The Weekly Ledger (`SKB-044`): tabs, the fixed-row layout, the commit order, setup |

Moved in SKB-091: `doc-write-rules.md` and `scaffold.md` to `ops-weekly-doc`, `proposal-rules.md` to
`ops-weekly-tracker`, `scheduling.md` to `project-manager`. `post-format.md` (the `#週報` four-line
format) retired with the Tuesday rollup.

Nothing in this folder contains a real identifier. Real ids live in
`~/.config/zynkr/ops-weekly.json`, which is never committed.
