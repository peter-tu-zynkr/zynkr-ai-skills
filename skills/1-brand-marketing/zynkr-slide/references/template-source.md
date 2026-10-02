# Template Source (configuration, not built in)

> **This skill does not ship with any templates.** Templates (fixed-layout Slides files) live in the Drive template library, not in this skill repo.
> This file does three things: (1) points to your **template library** (the SOT template folder); (2) explains how templates are **tagged to a use-case**; (3) gives the **field manifest** schema for each template.
> The **template-fill branch** of `zynkr-slide` reads this file in Step 1/2 to detect "which template is this", and in Step 4-T to fetch the field mapping.

> **Division-of-labor reminder**: only the **template-fill branch** (SKILL.md Step 4-T) uses this file; the three-relay branch does not touch it. This file only decides "which Drive template library to go to, which template to use, which fields to fill"; the actual brand colors are still loaded at runtime by each relay's `brand-source.md` (template-fill's visual handling is covered in Step 4-T, step 6).

---

## 1 · Template library location (configuration)

```
TEMPLATE_LIBRARY = 1j0lubFMtZ6lFW-ZTOQcvZ2O4r_ix70yF
```

- **Drive folder**: "Slide template" — https://drive.google.com/drive/folders/1j0lubFMtZ6lFW-ZTOQcvZ2O4r_ix70yF
- **Template format**: **native Google Slides** (one Slides file per template). template-fill will `copy_drive_file` to copy → `get_drive_file_download_url(export_format="slide-pptx")` to export → use python-pptx to fill precisely by shape index.
- A link-gated Drive folder ID is low-sensitivity **configuration** and may be written here (same convention as the repo's existing `inbound-sales-config.md` / `seo-pipeline-config.md`); **the template content itself stays in Drive and never enters the repo.**

**When not found / not configured** → template-fill falls back to a neutral default: **ask the user to paste the template link directly**, do not auto-search the library; the rest of the flow is unchanged.

---

## 2 · How templates are tagged to a use-case

Two layers, with **`TEMPLATE-INDEX` as authoritative**:

- **`TEMPLATE-INDEX` (authoritative)**: put a Google Sheet `TEMPLATE-INDEX` in the root of the template library, one row per template:

  | Template name | file_id | use-case key | One-line purpose | Visual-treatment default | Field manifest |
  |---|---|---|---|---|---|
  | Project Charter | `<slides file id>` | `charter` | Single-page project charter (problem → objective → milestones → RAPID/RACI → KPI → roll-out) | keep (this template is already Zynkr-branded) | see §3 example below |

  The **Visual-treatment default** column = that template's default `visual-treatment` (`recolor` / `keep` / `hybrid`); template-fill reads this column directly to decide whether to recolor (SKILL.md Step 4-T, step 6). External / un-indexed templates always default to `recolor`.

- **Filename prefix (soft hint)**: template filenames begin with the use-case key, e.g. `charter — Project Charter (Zynkr)`, `qbr-onepager — …`. Used only as a fallback when there is no `TEMPLATE-INDEX`.

> A template's use-case key (`charter` / `qbr-onepager` / `one-pager` …) is **independent of** the 9 narrative use-cases in `use-case-playbooks.md`: those 9 are for the three-relay branch, these are for template-fill's fixed layouts.

---

## 3 · Field manifest (schema) per template

One field manifest per template (placed in `TEMPLATE-INDEX` or next to the template). Fields are located by the **shape index after slide-pptx export** (the most stable; the Slides API cannot locate shapes one by one). Schema:

| Field | shape index | Type | Source hint | Required |
|---|---|---|---|---|
| `<field name>` | `<int, slide-pptx export order>` | text / table / date / checkbox | `<where to extract from the source document>` | yes / no |

When a manifest is missing a shape index, the runtime uses `~/.claude/skills/slide-pptx/.venv/bin/python` + python-pptx to list shapes (index + type + existing text) and fill it in on the spot.

### Example: `charter` (Project Charter) field manifest

| Field | shape index | Type | Source hint |
|---|---|---|---|
| Title | 0 | text | Document H1 / project name |
| Program / Vertical | 17 | text | Project track / domain |
| Project Lead | 50 | text | Owner |
| Objective | 20 | text | Solution → outcome → benefit, in one sentence |
| What's not working | 52 | text | Observation → problem → business impact |
| Deliverables (M1/M2/M3) | 14 | text | End-point of each milestone |
| Latest Update | 5 | text | Current status / open items |
| KPIs | 51 | text | Metrics (or "baseline TBD") |
| Phase chevrons 1–5 | 25,4,3,2,1 | text | Short name of each phase |
| Milestone table (5×3) | 6 | table | phase / deliverable / week |
| Start / Completion | 31 / 28 | date | start / end date |
| Roll-out checks (US&C/LatAm/EMEA/APAC) | 54,58,59,60 | checkbox | Selected markets |
| RAPID names (R/A/P/I/D) | 32,34,36,38,40 | text | Decision roles |
| RACI names (R/A/C/I) | 42,44,46,48 | text | Task roles |

> This charter template is **already in Zynkr brand colors** → visual-treatment default `keep` (no recolor needed).

---

## 4 · Detection & selection flow (how template-fill uses this file)

1. Step 1 detects template-fill + use-case key.
2. The user **brings their own template link → use it directly**, skip the library lookup.
3. Otherwise: load `TEMPLATE_LIBRARY` → read `TEMPLATE-INDEX` → match by use-case key → **offer 1–2 candidates for the user to confirm**.
4. On a match → fetch that template's field manifest and proceed to Step 4-T.
5. On no match → ask the user to paste a link, or fall back to the three-relay branch.

---

## 5 · Neutral default (when not configured / template library unreadable)

- Do not guess any Drive location; **ask the user to paste the template link directly**.
- Still hold to: **copy without modifying the master**, **mark "TBD" for anything that can't be extracted**, **external templates default to recolor**.
