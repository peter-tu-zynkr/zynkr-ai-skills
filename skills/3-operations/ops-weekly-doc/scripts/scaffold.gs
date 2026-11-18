/**
 * Zynkr — 營運每週彙報 週次骨架自動複製
 * Doc: [3.1] 營運每週彙報 Operation weekly
 * Tab: 每週事項 2026 (t.0)
 *
 * WHAT IT DOES
 *   Duplicates the newest weekly section verbatim and re-stamps it with the
 *   NEXT Thursday's date, inserting it above the current newest section.
 *
 * WHY DUPLICATE INSTEAD OF BUILDING A FRESH SPINE
 *   Each department heading carries an OWNER as a Google Docs person chip
 *   (e.g. #Demand Marketing → Sam Rivera <owner-a@example.com>). Neither Apps Script
 *   nor the Docs REST API can CREATE a person chip — so the only way to keep
 *   the owner map alive is to never destroy it. Duplication preserves it.
 *   Stripping finished items is the Friday tidy's job (SKB-030 blocks,
 *   SKB-039 Done/Drop bullets), where judgement belongs — not this script's.
 *   So a Done or Drop line IS copied forward here, on purpose.
 *
 * WHY IT READS ONLY THE TOP OF THE TAB (SKB-143)
 *   Sections run newest-first and only the newest one is copied, so the scan stops
 *   at the second dated heading, and the check after the insert reads only down to
 *   where that heading moved. Until SKB-143 it read every element of the year's tab
 *   twice, and on 12 Nov 2026 a run hit Apps Script's 30-minute limit. The tab still
 *   gains a section every week (SKB-029's archive was reverted), so nothing here may
 *   walk the whole tab.
 *
 * SAFETY
 *   - Idempotent: exits when next week is already open, that is when the newest
 *     section's date is after today in TZ, and on the meeting's own day before
 *     OPENS_FROM_HOUR. Once next week is open a second run writes nothing, and so
 *     does a run by hand before the meeting. After missed weeks each run opens the
 *     week after the newest, one run per missing week, until next week is open. A
 *     newest section more than a week ahead, or a dated heading that is not a real
 *     date, stops it with an error before it writes.
 *   - Insert-only: never deletes or rewrites existing content.
 *   - Set DRY_RUN = true to log what it would do without touching the doc, or run
 *     checkScaffold(), which never writes whatever DRY_RUN says, and logs how many
 *     elements the scan read and how long that took.
 *
 * ⚠️ SETUP — pasting this file is NOT enough. You must:
 *   1. Set DOC_ID to a DUPLICATE of the doc and run checkScaffold(); read the log.
 *   2. In the duplicate, delete the newest week section (its dated heading down to
 *      the next one): a run opens a week only once the newest one's meeting has
 *      passed. Set DRY_RUN = false, run scaffoldNextWeek(), then confirm the owner
 *      chips survived the copy. If they came through as plain text, see
 *      NOTE_ON_CHIPS below.
 *   3. Only then point DOC_ID at the real doc and run installTriggers() ONCE.
 *      Without running installTriggers() nothing is ever scheduled.
 */

const DOC_ID  = 'PUT_A_DUPLICATE_DOC_ID_HERE_FIRST';
const TAB_ID  = 't.0';              // 每週事項 2026
const DRY_RUN = true;               // flip to false once verified

/* WHEN IT RUNS — the trigger fires in TZ, regardless of the script project's own
 * timezone. Note the Apps Script Triggers panel DISPLAYS times in the PROJECT's
 * timezone (File > Project Settings), so if that is not TZ the row shows a
 * different clock than the trigger actually uses. Set the project timezone to
 * match TZ and the two agree.
 * Apps Script schedules within the HOUR, not on the minute: hour 23 means the run
 * lands somewhere in 23:00-24:00. Anything that must happen AFTER the scaffold has
 * to allow for that whole window. */
const TRIGGER_DAY  = 'THURSDAY';    // ScriptApp.WeekDay key
const TRIGGER_HOUR = 23;            // 23 => fires in the 23:00-24:00 window
const TZ           = 'Asia/Taipei';
/* On the meeting's own day a run opens next week only from this hour on (TZ): an hour
 * before the trigger's, so a trigger that fires early still runs, and a run by hand
 * before the meeting writes nothing (SKB-143). */
const OPENS_FROM_HOUR = TRIGGER_HOUR - 1;

/** Matches the weekly date headings, e.g. "Aug 27, 2026" */
const DATE_RE = /^([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})$/;
const MONTHS  = ['Jan','Feb','Mar','Apr','May','Jun',
                 'Jul','Aug','Sep','Oct','Nov','Dec'];

function scaffoldNextWeek() {
  return scaffold_(DRY_RUN);
}

/**
 * Run by hand to see what the next run would do. It never writes, whatever DRY_RUN
 * says, and its log says how many elements the scan read and how long that took.
 */
function checkScaffold() {
  return scaffold_(true);
}

function scaffold_(dryRun) {
  const started = Date.now();
  const body = getTabBody_(DOC_ID, TAB_ID);
  const opened = Date.now();
  const total = body.getNumChildren();

  // 1. The two NEWEST weekly date headings. Sections run newest-first, so the scan
  //    stops at the second one: everything below it is older weeks, which this run
  //    never copies (SKB-143). Never walk the whole tab: it gains a section every week.
  const marks = [];
  let read = 0;
  for (let i = 0; i < total && marks.length < 2; i++) {
    read++;
    const mk = dateHeading_(body.getChild(i));
    if (mk) marks.push({ index: i, text: mk.text, date: mk.date });
  }
  Logger.log('Opened the tab in ' + (opened - started) + ' ms; read ' + read + ' of ' + total +
             ' elements in ' + (Date.now() - opened) + ' ms.');
  if (marks.length < 2) throw new Error('Need >= 2 dated sections to infer the section range. Found ' + marks.length);
  if (marks[0].date.getTime() <= marks[1].date.getTime()) {
    throw new Error('The top two dated sections are not newest-first: "' + marks[0].text + '" sits above "' +
                    marks[1].text + '". Nothing was written.');
  }

  // 2. The newest section spans [marks[0], marks[1]).
  const from = marks[0].index;
  const to   = marks[1].index;

  // 3. Next Thursday after the newest section's date.
  const next  = addDays_(marks[0].date, 7);
  const label = MONTHS[next.getMonth()] + ' ' + next.getDate() + ', ' + next.getFullYear();

  // 4. Idempotency guard — never open a second future week, and never before the
  //    meeting (SKB-143). The trigger fires on the meeting's own Thursday, after it,
  //    when the newest section is today's. A newest section dated after today means
  //    next week is already open; one more than a week ahead is a mistyped date.
  const now    = new Date();
  const today  = Utilities.formatDate(now, TZ, 'yyyy-MM-dd');
  const hour   = Number(Utilities.formatDate(now, TZ, 'H'));
  const newest = ymd_(marks[0].date);
  const d      = today.split('-').map(Number);
  const weekOn = ymd_(addDays_(new Date(d[0], d[1] - 1, d[2]), 7));
  if (newest > weekOn) {
    throw new Error('The newest section, "' + marks[0].text + '", is more than a week after today (' + today +
                    ', ' + TZ + '). If its date is mistyped, fix it; if a week is skipped on purpose, every run ' +
                    'stops here until that section is at most a week ahead. Nothing was written.');
  }
  if (newest > today) {
    Logger.log('Next week is already open: "' + marks[0].text + '" is after today (' + today + ', ' + TZ +
               '). Nothing to do.');
    return marks[0].text;
  }
  if (newest === today && hour < OPENS_FROM_HOUR) {
    Logger.log('"' + marks[0].text + '" is today\'s meeting, still ahead: next week opens from ' +
               OPENS_FROM_HOUR + ':00 ' + TZ + '. Nothing to do.');
    return marks[0].text;
  }

  Logger.log('Duplicating "' + marks[0].text + '" (elements ' + from + '..' + (to - 1) +
             ', ' + (to - from) + ' elements) as "' + label + '"');
  if (dryRun) { Logger.log('DRY_RUN — no changes written.'); return label; }

  // 5. SNAPSHOT the source elements BEFORE writing anything.
  //     Every insert shifts the index of everything after it. Reading and writing in
  //     the same loop therefore re-reads the SAME element each pass (i advances at the
  //     same rate the insert pushes it forward) and duplicates it. Observed live: it
  //     produced ~100 copies of the date heading instead of the section. Read first.
  const copies = [];
  for (let i = from; i < to; i++) copies.push(body.getChild(i).copy());

  // 6. Insert the snapshot above the newest section, preserving order.
  let cursor = from;
  for (let j = 0; j < copies.length; j++) {
    const copy = copies[j];
    switch (copy.getType()) {
      case DocumentApp.ElementType.PARAGRAPH:
        body.insertParagraph(cursor++, copy.asParagraph()); break;
      case DocumentApp.ElementType.LIST_ITEM:
        body.insertListItem(cursor++, copy.asListItem()); break;
      case DocumentApp.ElementType.TABLE:
        body.insertTable(cursor++, copy.asTable()); break;
      default:
        Logger.log('Skipped unsupported element type: ' + copy.getType());
    }
  }
  const added = cursor - from;

  // 7. Re-stamp the copied date heading (it is the first element we inserted).
  body.getChild(from).asParagraph().setText(label);

  // 8. Post-condition, on the top of the tab only (SKB-143): the new heading first, the
  //    old newest heading right after the copies, the second-newest where it moved to,
  //    and no other dated heading above it. This is the guard that would have caught the
  //    shift bug (~100 copies of the date heading) on its first run instead of by eye.
  let problem;
  try {
    problem = checkTop_(body, added, marks, label);
  } catch (e) {
    // Whatever throws here throws after the insert: report it as an abort, never as "Nothing was written".
    problem = String((e && e.message) || e).replace(/\.? Nothing was written\.$/, '');
  }
  if (problem) {
    throw new Error('Aborting: ' + problem + '. The document was modified — undo it (Ctrl/Cmd-Z in the doc, ' +
                    'or File > Version history) before re-running.');
  }
  Logger.log('Inserted section "' + label + '" (' + added + ' elements) in ' + (Date.now() - started) + ' ms.');
  return label;
}

/** A top-level dated HEADING2 paragraph as { text, date }, or null. */
function dateHeading_(el) {
  if (el.getType() !== DocumentApp.ElementType.PARAGRAPH) return null;
  const p = el.asParagraph();
  if (p.getHeading() !== DocumentApp.ParagraphHeading.HEADING2) return null;
  const text = p.getText().trim();
  const m = DATE_RE.exec(text);
  if (!m) return null;
  const date = parseDate_(m);
  if (MONTHS.indexOf(m[1]) < 0 || date.getDate() !== Number(m[2])) {
    throw new Error('"' + text + '" reads like a week heading but is not a real date. Nothing was written.');
  }
  return { text: text, date: date };
}

/**
 * The insert's post-condition, read from the top of the tab down to where the
 * second-newest heading should now sit, and no further. Returns what is wrong, or
 * null when it holds. A read past the end of the tab throws, and the caller reports
 * that as an abort too.
 */
function checkTop_(body, added, marks, label) {
  const want = [
    { index: marks[0].index, text: label },
    { index: marks[0].index + added, text: marks[0].text },
    { index: marks[1].index + added, text: marks[1].text }
  ];
  const end = want[2].index;
  const seen = [];
  for (let i = 0; i <= end; i++) {
    const mk = dateHeading_(body.getChild(i));
    if (mk) seen.push({ index: i, text: mk.text });
  }
  const show = function (list) {
    return list.map(function (h) { return '"' + h.text + '" at ' + h.index; }).join(', ');
  };
  const same = seen.length === want.length && want.every(function (w, k) {
    return seen[k].index === w.index && seen[k].text === w.text;
  });
  return same ? null : 'expected the dated headings ' + show(want) + ' at the top of the tab, found ' +
                       (show(seen) || 'none');
}

/** A date as yyyy-MM-dd from its own calendar fields, to compare with Utilities.formatDate's. */
function ymd_(d) {
  return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
}

/** Resolve a tab's body — a tabbed doc's top-level getBody() is NOT the tab. */
function getTabBody_(docId, tabId) {
  const doc  = DocumentApp.openById(docId);
  const tabs = doc.getTabs();
  for (let i = 0; i < tabs.length; i++) {
    if (tabs[i].getId() === tabId) return tabs[i].asDocumentTab().getBody();
  }
  throw new Error('Tab ' + tabId + ' not found. Available: ' +
                  tabs.map(function (t) { return t.getId() + ' (' + t.getTitle() + ')'; }).join(', '));
}

function parseDate_(m) {
  return new Date(Number(m[3]), MONTHS.indexOf(m[1]), Number(m[2]));
}

function addDays_(d, n) {
  const c = new Date(d.getTime());
  c.setDate(c.getDate() + n);
  return c;
}

/**
 * Run ONCE, by hand, after verifying on a duplicate.
 * Fires Thursday evening — right after the ops meeting, so the week closes
 * and the next one opens in the same beat, and Tuesday's rollup always has
 * a section waiting for it.
 */
function installTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'scaffoldNextWeek') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('scaffoldNextWeek')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay[TRIGGER_DAY])
    .atHour(TRIGGER_HOUR)
    .inTimezone(TZ)
    .create();
  Logger.log('Trigger installed: scaffoldNextWeek, ' + TRIGGER_DAY + 's ' +
             TRIGGER_HOUR + ':00-' + (TRIGGER_HOUR + 1) + ':00 ' + TZ +
             '. (The Triggers panel shows this in the PROJECT timezone — set the ' +
             'project timezone to ' + TZ + ' if the row disagrees.)');
}

/*
 * NOTE_ON_CHIPS
 * If step 2 shows owners arriving as plain text instead of person chips,
 * DocumentApp dropped them. Fallback: after the copy, re-apply each owner as a
 * plain mailto hyperlink —
 *   para.editAsText().setLinkUrl(start, end, 'mailto:owner-a@example.com');
 * It loses the chip pill visually but stays machine-readable, so the Tuesday
 * rollup can still route by owner email exactly as before.
 */
