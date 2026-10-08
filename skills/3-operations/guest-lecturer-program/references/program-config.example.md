# program-config.md — example (shape only)

`guest-lecturer-program` reads a local `program-config.md` at the start of every run (see the skill's Configuration section). This file shows the shape, with blanks only.

Every value in the real file is a negotiated commercial term or the id of a live document, so the real file lives **outside this repository** and is never committed here or to any other repo (`.gitignore` ignores the name). If the file is missing, the skill stops and asks for it; it never assumes a number.

Nothing below is a default or a recommendation. Each `<…>` is yours to fill.

## revenue_split

Per plan, the lecturer's share by registration source.

| plan | registration source | lecturer share |
|---|---|---|
| `<plan name>` | `<registration source>` | `<ratio>` |

## hourly_revenue_floor

`<gross ticket revenue per course-hour, in NT$>`. The skill turns it into each event's minimum attendance: ⌈(floor × course hours) ÷ ticket price⌉.

## cancellation_terms

| scenario | timing | compensation cap |
|---|---|---|
| `<who cancels or postpones>` | `<how long before the event>` | `<cap>` |

## quality_thresholds

- **rating floor** — `<the post-event rating below which a session is flagged>`
- **escalation** — `<what happens on a miss>`
- **termination** — `<when the collaboration ends>`

## Live documents (Google Workspace ids)

- `tracker_sheet_id`: `<your-tracker-sheet-id>`
- `intake_form_id`: `<your-intake-form-id>`
- `feedback_form_id`: `<your-feedback-form-id>`
- `contract_template_ids`: one per plan — `<plan>` → `<your-contract-template-doc-id>`
- `settlement_template_ids`: one per plan — `<plan>` → `<your-settlement-template-doc-id>`

The contract and settlement templates are your own documents, reviewed by a lawyer. List their ids here, never their text.
