-- sales-outbound · lead-insert.sql
-- Atomic: resolve the claimer + workspace + pipeline → the pick-up gate (an open deal on a
-- contact with this email stops everything) → find-or-create company → find-or-create
-- contact (by email or secondary_email) → new deal owned by the claimer → conversation
-- note + follow-up task. Returns the ids and whether the company/contact already existed,
-- or blocked = true plus the existing open deal and writes nothing (SKB-105).
--
-- The gate runs on the zynkr MCP first (SKILL.md step 4); the open_deal guard below is
-- the same rule inside the statement. What it guarantees: a deal saved before this statement
-- started is seen, so a claim made between the MCP check and this insert still stops it. It
-- takes no lock, so two claims running at the same instant can both pass; that true race is
-- caught afterwards by /sales-manager REVIEW's 重複認領 check.
--
-- Run via: mcp__supabase__execute_sql(project_id="uomieoqlkazknjgmfdda", query=<this>)
--
-- PLACEHOLDERS — replace each {{...}} with a SQL LITERAL (quote text, double any
-- single quote, or write NULL). For "no company", set {{COMPANY_NAME}} to ''.
--   {{COMPANY_NAME}}     e.g. '範例顧問 Example.Marketing'   ('' = no company)
--   {{COMPANY_DOMAIN}}   e.g. 'example.com'                 (or NULL)
--   {{COMPANY_INDUSTRY}} e.g. '品牌策略 / 行銷顧問'        (or NULL)
--   {{COMPANY_COUNTRY}}  e.g. '台灣'                      (or NULL)
--   {{COMPANY_DESC}}     e.g. '個人品牌與行銷策略顧問…'     (or NULL)
--   {{FIRST_NAME}}       e.g. '王小明'                    (the whole name as they write it, or NULL;
--                        last_name stays empty, sales.crm-data-standards §3)
--   {{EMAIL}}            e.g. 'prospect@example.com'    (find-or-create key; matched trimmed, case-insensitive)
--   {{TITLE}}            e.g. '品牌策略行銷顧問'           (or NULL)
--   {{PHONE}}            e.g. '0912-345-678'              (as the signal gave it, or NULL)
--   {{CONTACT_LIFECYCLE}} e.g. 'sql'                      (lifecycle_stage enum)
--
-- BAKED IN (not a placeholder): legal_basis = 'consent'.
--   PDPA requires a lawful basis for holding a person's data, and the MCP
--   create_contact tool makes it a REQUIRED field for exactly that reason — but
--   the column is nullable at the DB level, so raw SQL that omits it silently
--   writes NULL (231 of 410 contacts are NULL today, all from this path).
--   Every contact a skill or a person files is 'consent': forms, replies and
--   outbound lists alike (sales.crm-data-standards §3, owner, 2026-11-07).
--   Only NEW contacts get this — the existing_contact branch returns matched rows
--   untouched, so the 231 pre-existing NULLs need a separate backfill decision.
--   {{DEAL_NAME}}        e.g. '小明 — Zynkr CRM Beta'
--   {{STAGE}}            e.g. 'contacted'                 (deal_stage enum; never 'qualified', see Inference defaults)
--   {{LEAD_SOURCE}}      e.g. 'outbound'                  (lead_source enum)
--   {{PRIORITY}}         e.g. 'medium'                    (deal_priority enum)
--   {{DEAL_NOTES}}       e.g. 'Threads DM 邀請加入 Beta…'  (or NULL)
--   {{NOTE_SUBJECT}}     e.g. 'Threads 初次接觸 — 同意 demo'
--   {{NOTE_BODY}}        e.g. '來源：Threads…\n\n對話重點：…'  (verbatim thread + who they are)
--   {{TASK_SUBJECT}}     e.g. '安排 30 分鐘 Demo + 開通 Beta'
--   {{TASK_BODY}}        e.g. '已擬好邀約草稿，待回覆時段後寄出'  (or NULL)
--   {{TASK_DUE_DAYS}}    from the follow-up rhythm in Atlas company.sales-pipeline-rules (SKILL.md, Inference defaults)
--   {{SOURCE_META}}      e.g. '{"source":"threads","handle":"@example.marketing"}'  (jsonb literal, or '{}')
--   {{OWNER_EMAIL}}      e.g. 'claimer@example.com'      (the claimer: the email whoami gives
--                                                         for the person running the skill)
--   {{WORKSPACE_ID}}     e.g. '00000000-0000-0000-0000-000000000000'  (the workspace_id whoami
--                                                         gives — the workspace the claim lands in)

-- OWNER = THE CLAIMER (SKB-105): {{OWNER_EMAIL}} is the email of the person running the skill
-- (whoami), never company.contact-email when the claimer is someone else. The workspace is
-- {{WORKSPACE_ID}}, the workspace_id whoami gives — never derived here — and the claimer resolves
-- only if they belong to it (its owner, or an active member). An email that matches no user, or
-- a user outside that workspace, gives zero rows: owner and workspace stay NULL and every insert
-- below fails with a NOT NULL error. Never a guess. Exactly one row otherwise: two crm_users rows
-- whose emails differ only by case would make every (SELECT … FROM claimer) below error, so the
-- exact-case match wins, then the lowest id, LIMIT 1.
WITH claimer AS (
  SELECT u.id AS uid,
         {{WORKSPACE_ID}}::uuid AS ws,
         (SELECT id FROM crm_pipelines WHERE is_default ORDER BY created_at LIMIT 1) AS pipe
  FROM crm_users u
  WHERE lower(u.email) = lower(trim({{OWNER_EMAIL}}))
    AND (u.id = {{WORKSPACE_ID}}::uuid
         OR EXISTS (SELECT 1 FROM crm_workspace_members m
                     WHERE m.user_id = u.id
                       AND m.workspace_id = {{WORKSPACE_ID}}::uuid
                       AND m.status = 'active'))
  ORDER BY (u.email = trim({{OWNER_EMAIL}})) DESC, u.id
  LIMIT 1
),
-- THE GATE: exact match on email OR secondary_email (never a substring), then any deal in an
-- open stage on those contacts. won / lost deals do not count, so a closed client is free again.
matched_contact AS (
  SELECT id FROM crm_contacts
  WHERE workspace_id = (SELECT ws FROM claimer)
    AND (lower(trim(email)) = lower(trim({{EMAIL}}))
         OR lower(trim(secondary_email)) = lower(trim({{EMAIL}})))
),
open_deal AS (
  SELECT d.id, d.deal_number, d.stage::text AS stage, d.owner_id, d.last_activity_at,
         (SELECT u.name FROM crm_users u WHERE u.id = d.owner_id) AS owner_name
  FROM crm_deals d
  WHERE d.contact_id IN (SELECT id FROM matched_contact)
    AND d.stage IN ('new', 'contacted', 'qualified', 'proposal')
  ORDER BY d.last_activity_at DESC NULLS LAST
  LIMIT 1
),
existing_company AS (
  SELECT id FROM crm_companies
  WHERE workspace_id = (SELECT ws FROM claimer)
    AND lower(name) = lower({{COMPANY_NAME}})
    AND length(trim({{COMPANY_NAME}})) > 0
    AND NOT EXISTS (SELECT 1 FROM open_deal)
  LIMIT 1
),
new_company AS (
  INSERT INTO crm_companies (name, domain, industry, country, description, owner_id, workspace_id, lifecycle_stage)
  SELECT {{COMPANY_NAME}}, {{COMPANY_DOMAIN}}, {{COMPANY_INDUSTRY}}, {{COMPANY_COUNTRY}}, {{COMPANY_DESC}},
         (SELECT uid FROM claimer), (SELECT ws FROM claimer), 'opportunity'::lifecycle_stage
  WHERE NOT EXISTS (SELECT 1 FROM existing_company)
    AND NOT EXISTS (SELECT 1 FROM open_deal)
    AND length(trim({{COMPANY_NAME}})) > 0
  RETURNING id
),
company AS (
  SELECT id FROM existing_company
  UNION ALL
  SELECT id FROM new_company
),
existing_contact AS (
  SELECT id FROM matched_contact
  WHERE NOT EXISTS (SELECT 1 FROM open_deal)
  LIMIT 1
),
new_contact AS (
  INSERT INTO crm_contacts (first_name, email, title, phone, company_id, owner_id, workspace_id, lifecycle_stage, legal_basis, last_contacted_at)
  SELECT {{FIRST_NAME}}, trim({{EMAIL}}), {{TITLE}}, {{PHONE}},
         (SELECT id FROM company LIMIT 1),
         (SELECT uid FROM claimer), (SELECT ws FROM claimer), {{CONTACT_LIFECYCLE}}::lifecycle_stage,
         'consent'::legal_basis, now()
  WHERE NOT EXISTS (SELECT 1 FROM existing_contact)
    AND NOT EXISTS (SELECT 1 FROM open_deal)
  RETURNING id
),
contact AS (
  SELECT id FROM existing_contact
  UNION ALL
  SELECT id FROM new_contact
),
ins_deal AS (
  INSERT INTO crm_deals (name, pipeline_id, stage, contact_id, company_id, owner_id, workspace_id,
                         deal_type, lead_source, priority, notes, last_activity_at)
  SELECT {{DEAL_NAME}}, (SELECT pipe FROM claimer), {{STAGE}}::deal_stage,
         (SELECT id FROM contact LIMIT 1), (SELECT id FROM company LIMIT 1),
         (SELECT uid FROM claimer), (SELECT ws FROM claimer),
         'new_business'::deal_type, {{LEAD_SOURCE}}::lead_source, {{PRIORITY}}::deal_priority,
         {{DEAL_NOTES}}, now()
  WHERE NOT EXISTS (SELECT 1 FROM open_deal)
  RETURNING id
),
ins_note AS (
  INSERT INTO crm_activities (kind, subject, body, contact_id, company_id, deal_id, created_by, metadata)
  SELECT 'note'::activity_kind, {{NOTE_SUBJECT}}, {{NOTE_BODY}},
         (SELECT id FROM contact LIMIT 1), (SELECT id FROM company LIMIT 1), (SELECT id FROM ins_deal),
         (SELECT uid FROM claimer), {{SOURCE_META}}::jsonb
  WHERE EXISTS (SELECT 1 FROM ins_deal)
  RETURNING id
),
ins_task AS (
  INSERT INTO crm_activities (kind, subject, body, contact_id, company_id, deal_id, created_by, assignee_id, task_status, task_due_at)
  SELECT 'task'::activity_kind, {{TASK_SUBJECT}}, {{TASK_BODY}},
         (SELECT id FROM contact LIMIT 1), (SELECT id FROM company LIMIT 1), (SELECT id FROM ins_deal),
         (SELECT uid FROM claimer), (SELECT uid FROM claimer), 'todo'::task_status,
         now() + ({{TASK_DUE_DAYS}} || ' days')::interval
  WHERE EXISTS (SELECT 1 FROM ins_deal)
  RETURNING id
)
SELECT
  EXISTS (SELECT 1 FROM open_deal)                       AS blocked,
  (SELECT id FROM open_deal)                             AS existing_deal_id,
  (SELECT deal_number FROM open_deal)                    AS existing_deal_number,
  (SELECT stage FROM open_deal)                          AS existing_deal_stage,
  (SELECT owner_name FROM open_deal)                     AS existing_deal_owner,
  (SELECT last_activity_at FROM open_deal)               AS existing_deal_last_activity,
  (SELECT id FROM company LIMIT 1)                       AS company_id,
  (SELECT id FROM contact LIMIT 1)                       AS contact_id,
  (SELECT id FROM ins_deal)                              AS deal_id,
  (SELECT id FROM ins_note)                              AS note_id,
  (SELECT id FROM ins_task)                              AS task_id,
  EXISTS (SELECT 1 FROM existing_company)                AS company_existed,
  EXISTS (SELECT 1 FROM existing_contact)                AS contact_existed;
