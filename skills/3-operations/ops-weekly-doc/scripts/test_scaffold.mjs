#!/usr/bin/env node
// test_scaffold.mjs — scaffold.gs against a strict mock of Apps Script's DocumentApp (SKB-143).
//
//   node test_scaffold.mjs              the suite
//   node test_scaffold.mjs --mutate     the suite on an unmutated control, then each mutant of
//                                       scaffold.gs must turn it red
//   node test_scaffold.mjs --tz-matrix  the suite under several process time zones
//
// A mock that cannot fail proves nothing (SKB-029). This one throws where Apps Script throws: a
// child index out of range, an insert past the end, inserting an element that is still attached,
// asParagraph() on a list item. It counts every read and write, which is how the suite proves the
// scan no longer grows with the tab: the run that timed out on 12 Nov 2026 read the whole tab twice.
//
// Exit 0 green · 1 red (or a mutant survived) · 2 the harness itself is broken.

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const SELF = fileURLToPath(import.meta.url);
const SOURCE = fs.readFileSync(path.join(HERE, 'scaffold.gs'), 'utf8');
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const ZONES = ['UTC', 'Asia/Taipei', 'Europe/Amsterdam', 'America/Los_Angeles', 'Pacific/Auckland'];

// ---------------------------------------------------------------- the mock

const ElementType = Object.freeze({
  PARAGRAPH: 'PARAGRAPH', LIST_ITEM: 'LIST_ITEM', TABLE: 'TABLE', TABLE_OF_CONTENTS: 'TABLE_OF_CONTENTS',
});
const ParagraphHeading = Object.freeze({
  NORMAL: 'NORMAL', TITLE: 'TITLE', HEADING1: 'HEADING1', HEADING2: 'HEADING2', HEADING3: 'HEADING3',
});

let nextUid = 1;

class El {
  constructor(type, { heading = ParagraphHeading.NORMAL, text = '', rows = null } = {}) {
    this.uid = nextUid++;
    this.type = type;
    this.heading = heading;
    this.text = text;
    this.rows = rows;
    this.attached = false;
    this.copiedFrom = null;
    this.stats = null;
  }
  getType() { return this.type; }
  asParagraph() { this.need_(ElementType.PARAGRAPH, 'asParagraph'); return this; }
  asListItem() { this.need_(ElementType.LIST_ITEM, 'asListItem'); return this; }
  asTable() { this.need_(ElementType.TABLE, 'asTable'); return this; }
  getHeading() {
    if (this.type !== ElementType.PARAGRAPH && this.type !== ElementType.LIST_ITEM) {
      throw new Error(`getHeading() on a ${this.type}`);
    }
    return this.heading;
  }
  getText() {
    if (this.type === ElementType.TABLE) throw new Error('getText() on a TABLE in this mock');
    return this.text;
  }
  setText(t) {
    if (this.type === ElementType.TABLE) throw new Error('setText() on a TABLE');
    if (!this.attached) throw new Error('setText() on an element that is not in the document');
    this.text = String(t);
    this.stats.setText++;
    return this;
  }
  copy() {
    const c = new El(this.type, {
      heading: this.heading, text: this.text, rows: this.rows && this.rows.map((r) => r.slice()),
    });
    c.copiedFrom = this.uid;
    if (this.stats) this.stats.copy++;
    return c;
  }
  need_(type, call) {
    if (this.type !== type) throw new Error(`${call}() on a ${this.type}`);
  }
}

class Body {
  constructor(children, fault = null) {
    this.children = children;
    this.fault = fault;
    this.stats = { getNumChildren: 0, getChild: 0, insert: 0, setText: 0, copy: 0 };
    for (const c of children) { c.attached = true; c.stats = this.stats; }
  }
  getNumChildren() { this.stats.getNumChildren++; return this.children.length; }
  getChild(i) {
    this.stats.getChild++;
    if (!Number.isInteger(i) || i < 0 || i >= this.children.length) {
      throw new Error(`Child index (${i}) must be less than the number of child elements (${this.children.length}).`);
    }
    return this.children[i];
  }
  insertParagraph(i, el) { return this.insert_(ElementType.PARAGRAPH, i, el); }
  insertListItem(i, el) { return this.insert_(ElementType.LIST_ITEM, i, el); }
  insertTable(i, el) { return this.insert_(ElementType.TABLE, i, el); }
  insert_(type, i, el) {
    if (!(el instanceof El)) throw new Error('insert: not a document element');
    if (el.type !== type) throw new Error(`insert ${type}: got a ${el.type}`);
    if (el.attached) throw new Error('Element must be detached.');
    if (!Number.isInteger(i) || i < 0 || i > this.children.length) {
      throw new Error(`Index (${i}) must be less than or equal to the number of child elements (${this.children.length}).`);
    }
    this.stats.insert++;
    const n = this.stats.insert;
    // Fault injection: an insert the API reports as done that never landed.
    if (this.fault && this.fault.kind === 'dropped-insert' && n === this.fault.at) return el;
    this.children.splice(i, 0, el);
    el.attached = true;
    el.stats = this.stats;
    // Fault injection: an insert that also lands a stray dated heading, as the shift bug did.
    if (this.fault && this.fault.kind === 'extra-heading' && n === this.fault.at) {
      const stray = new El(ElementType.PARAGRAPH, { heading: ParagraphHeading.HEADING2, text: this.fault.text });
      this.children.splice(i + 1, 0, stray);
      stray.attached = true;
      stray.stats = this.stats;
    }
    return el;
  }
}

// ---------------------------------------------------------------- fixtures (generic data only)

const H = ParagraphHeading;
const P = (heading, text) => new El(ElementType.PARAGRAPH, { heading, text });
const LI = (text) => new El(ElementType.LIST_ITEM, { text });
const TBL = (rows) => new El(ElementType.TABLE, { rows });
const TOP = 3; // elements above the newest section in tab()
const SECTION = 8; // elements in section() without extras

const label = (d) => `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
const weeksBack = ([y, m, d], n) => Array.from({ length: n }, (_, k) => label(new Date(y, m, d - 7 * k)));

function section(dateText, k, extra = []) {
  return [
    P(H.HEADING2, dateText),
    P(H.HEADING3, '#Team A · owner-a@example.com'),
    LI(`Item ${k}.1 · in progress`),
    LI(`Item ${k}.2 · Done`),
    P(H.HEADING3, '#Team B · owner-b@example.com'),
    TBL([['Metric', 'Value'], ['Visits', String(100 + k)]]),
    ...extra,
    P(H.NORMAL, 'Nov 26, 2026'), // a date in a NORMAL paragraph is not a section mark
    P(H.NORMAL, ''),
  ];
}

function tab({ newest = [2026, 10, 19], sections = 6, dates = null, extraInNewest = [] } = {}) {
  const ds = dates || weeksBack(newest, sections);
  const children = [
    P(H.TITLE, 'Weekly operations'),
    P(H.HEADING2, 'How to use this tab'), // a HEADING2 that is not a date
    P(H.NORMAL, 'Newest week first.'),
  ];
  ds.forEach((d, k) => children.push(...section(d, k, k === 0 ? extraInNewest : [])));
  return children;
}

// ---------------------------------------------------------------- loading scaffold.gs

function withDryRun(src, value) {
  const from = 'const DRY_RUN = true;';
  if (src.split(from).length !== 2) throw new HarnessError('the DRY_RUN line is not in scaffold.gs exactly once');
  return src.replace(from, `const DRY_RUN = ${value};`);
}

// Utilities.formatDate's answer is computed from the Date it is given, in Asia/Taipei, so a script that
// formats the wrong Date gets the wrong day.
const TAIPEI = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hourCycle: 'h23',
});

function load(src, { children, today, hour = 23, tabs = null, fault = null }) {
  const body = new Body(children, fault);
  // The script's clock: `today` at hour:30 in Taipei, which is UTC+8 all year.
  const [ty, tm, td] = today.split('-').map(Number);
  const now = Date.UTC(ty, tm - 1, td, hour - 8, 30);
  const logs = [];
  const doc = {
    getTabs() {
      const list = tabs || [{ id: 't.0', title: 'Weekly', body }];
      return list.map((t) => ({
        getId: () => t.id,
        getTitle: () => t.title,
        asDocumentTab: () => ({ getBody: () => t.body }),
      }));
    },
    getBody() { throw new Error("getBody() on a tabbed document is not the tab's body"); },
  };
  const refuse = (name) => () => { throw new Error(`ScriptApp.${name} called from a scaffold run`); };
  const context = vm.createContext({
    DocumentApp: { ElementType, ParagraphHeading, openById: () => doc },
    Utilities: {
      formatDate(d, tz, format) {
        if (Object.prototype.toString.call(d) !== '[object Date]') throw new Error('formatDate: not a Date');
        if (tz !== 'Asia/Taipei') throw new Error(`formatDate: time zone ${tz}`);
        const p = Object.fromEntries(TAIPEI.formatToParts(d.getTime()).map((x) => [x.type, x.value]));
        if (format === 'yyyy-MM-dd') return `${p.year}-${p.month}-${p.day}`;
        if (format === 'H') return String(Number(p.hour));
        throw new Error(`formatDate: format ${format}`);
      },
    },
    Logger: { log: (m) => { logs.push(String(m)); } },
    ScriptApp: { getProjectTriggers: refuse('getProjectTriggers'), newTrigger: refuse('newTrigger'), deleteTrigger: refuse('deleteTrigger'), WeekDay: {} },
  });
  // new Date() and Date.now() read the fixed clock; a Date built from fields or a time is an ordinary one.
  vm.runInContext(`(() => { const D = Date; globalThis.Date = class extends D {
    constructor(...a) { if (a.length === 0) super(${now}); else super(...a); }
    static now() { return ${now}; } }; })();`, context);
  vm.runInContext(src, context, { filename: 'scaffold.gs' });
  return { run: context, body, logs };
}

const snap = (children) => children.map((el) => ({ el, uid: el.uid, type: el.type, heading: el.heading, text: el.text, rows: JSON.stringify(el.rows) }));
const same = (el, s) => el === s.el && el.type === s.type && el.heading === s.heading && el.text === s.text && JSON.stringify(el.rows) === s.rows;
const wrote = (body) => body.stats.insert + body.stats.setText + body.stats.copy;

function assertUnchanged(body, before) {
  assert.equal(body.children.length, before.length, 'the tab changed length');
  body.children.forEach((el, i) => assert.ok(same(el, before[i]), `element ${i} changed`));
  assert.equal(wrote(body), 0, 'something was written');
}

// Checks a finished insert: the copies sit at [from, from + count), the rest is the same elements.
function assertInserted(body, before, { from, count, newLabel, skipped = [] }) {
  const kids = body.children;
  assert.equal(kids.length, before.length + count, 'wrong number of elements inserted');
  for (let i = 0; i < from; i++) assert.ok(same(kids[i], before[i]), `element ${i} above the section changed`);
  const sources = before.slice(from).filter((s) => !skipped.includes(s.type));
  for (let j = 0; j < count; j++) {
    const c = kids[from + j];
    const s = sources[j];
    assert.notEqual(c, s.el, `copy ${j} is the original element`);
    assert.equal(c.copiedFrom, s.uid, `copy ${j} is not a copy of source element ${j}`);
    assert.equal(c.type, s.type);
    assert.equal(c.heading, s.heading);
    assert.equal(c.text, j === 0 ? newLabel : s.text, `copy ${j} text`);
    assert.equal(JSON.stringify(c.rows), s.rows, `copy ${j} rows`);
  }
  for (let i = from; i < before.length; i++) {
    assert.ok(same(kids[i + count], before[i]), `original element ${i} moved or changed`);
  }
}

// ---------------------------------------------------------------- the suite

const CASES = [
  ['normal Thursday: opens the next week above the newest, leaves the rest', (src) => {
    const children = tab();
    const before = snap(children);
    const { run, body, logs } = load(withDryRun(src, false), { children, today: '2026-11-19' });
    assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026');
    assertInserted(body, before, { from: TOP, count: SECTION, newLabel: 'Nov 26, 2026' });
    assert.ok(logs.some((l) => l.includes(`read ${TOP + SECTION + 1} of ${before.length} elements`)), 'no read count in the log');
    assert.ok(logs.some((l) => l.startsWith(`Inserted section "Nov 26, 2026" (${SECTION} elements)`)), 'no insert line in the log');
  }],

  ['reads do not grow with the tab (50 vs 2,000 sections)', (src) => {
    const counts = [50, 2000].map((n) => {
      const { run, body } = load(withDryRun(src, false), { children: tab({ sections: n }), today: '2026-11-19' });
      run.scaffoldNextWeek();
      return body.stats;
    });
    assert.equal(counts[1].getChild, counts[0].getChild, 'getChild() calls grew with the tab');
    assert.ok(counts[1].getNumChildren <= 2, `getNumChildren() called ${counts[1].getNumChildren} times`);
    // scan (TOP + SECTION + 1) + snapshot (SECTION) + re-stamp (1) + check (TOP + 2 * SECTION + 1)
    assert.equal(counts[1].getChild, 2 * TOP + 4 * SECTION + 3);
    const check = load(withDryRun(src, false), { children: tab({ sections: 2000 }), today: '2026-11-19' });
    check.run.checkScaffold();
    assert.equal(check.body.stats.getChild, TOP + SECTION + 1, 'checkScaffold() read past the second dated heading');
  }],

  ['a second run the same evening writes nothing', (src) => {
    const { run, body, logs } = load(withDryRun(src, false), { children: tab(), today: '2026-11-19' });
    assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026');
    const after = snap(body.children);
    const stats = { ...body.stats };
    assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026');
    assert.deepEqual([body.stats.insert, body.stats.setText, body.stats.copy], [stats.insert, stats.setText, stats.copy]);
    body.children.forEach((el, i) => assert.ok(same(el, after[i]), `element ${i} changed on the second run`));
    assert.ok(logs.some((l) => l.startsWith('Next week is already open')));
  }],

  ['a catch-up after the meeting (Friday 03:00, Tuesday 10:00) opens the next week', (src) => {
    for (const [today, hour] of [['2026-11-20', 3], ['2026-11-24', 10]]) {
      const children = tab();
      const before = snap(children);
      const { run, body } = load(withDryRun(src, false), { children, today, hour });
      assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026', today);
      assertInserted(body, before, { from: TOP, count: SECTION, newLabel: 'Nov 26, 2026' });
    }
  }],

  ['after missed weeks each run opens the next one, until next week is open', (src) => {
    const children = tab({ dates: ['Nov 5, 2026', 'Oct 29, 2026', 'Oct 22, 2026'] });
    const { run, body, logs } = load(withDryRun(src, false), { children, today: '2026-11-19' });
    assert.deepEqual([1, 2, 3, 4].map(() => run.scaffoldNextWeek()), ['Nov 12, 2026', 'Nov 19, 2026', 'Nov 26, 2026', 'Nov 26, 2026']);
    assert.equal(body.stats.insert, 3 * SECTION);
    const heads = body.children.filter((el) => el.type === ElementType.PARAGRAPH && el.heading === H.HEADING2 && /\d{4}$/.test(el.text.trim()));
    assert.deepEqual(heads.slice(0, 5).map((el) => el.text), ['Nov 26, 2026', 'Nov 19, 2026', 'Nov 12, 2026', 'Nov 5, 2026', 'Oct 29, 2026']);
    assert.ok(logs.some((l) => l.startsWith('Next week is already open')));
  }],

  ['a run by hand on a day before the meeting writes nothing', (src) => {
    const children = tab();
    const before = snap(children);
    const { run, body, logs } = load(withDryRun(src, false), { children, today: '2026-11-16' });
    assert.equal(run.scaffoldNextWeek(), 'Nov 19, 2026');
    assertUnchanged(body, before);
    assert.ok(logs.some((l) => l.startsWith('Next week is already open')));
  }],

  ["on the meeting's own Thursday a run opens next week only from 22:00", (src) => {
    for (const [hour, opens] of [[9, false], [16, false], [21, false], [22, true], [23, true]]) {
      const children = tab();
      const before = snap(children);
      const { run, body, logs } = load(withDryRun(src, false), { children, today: '2026-11-19', hour });
      if (opens) {
        assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026', `${hour}:00`);
        assertInserted(body, before, { from: TOP, count: SECTION, newLabel: 'Nov 26, 2026' });
      } else {
        assert.equal(run.scaffoldNextWeek(), 'Nov 19, 2026', `${hour}:00`);
        assertUnchanged(body, before);
        assert.ok(logs.some((l) => l.includes("is today's meeting, still ahead")), `${hour}:00 log`);
      }
    }
  }],

  ['a newest section more than a week ahead throws; exactly a week ahead is next week, open', (src) => {
    const ahead = tab({ dates: ['Nov 26, 2027', 'Nov 19, 2026', 'Nov 12, 2026'] });
    const before = snap(ahead);
    const a = load(withDryRun(src, false), { children: ahead, today: '2026-11-19' });
    assert.throws(() => a.run.scaffoldNextWeek(), /is more than a week after today/);
    assertUnchanged(a.body, before);
    const b = load(withDryRun(src, false), { children: tab({ dates: ['Nov 26, 2026', 'Nov 19, 2026', 'Nov 12, 2026'] }), today: '2026-11-19' });
    assert.equal(b.run.scaffoldNextWeek(), 'Nov 26, 2026');
    assert.equal(wrote(b.body), 0);
  }],

  ['a heading that reads like a date but is not one throws, writes nothing', (src) => {
    for (const dates of [['Nov 31, 2026', 'Nov 19, 2026', 'Nov 12, 2026'], ['Thu 19, 2026', 'Nov 12, 2026', 'Nov 5, 2026']]) {
      const children = tab({ dates });
      const before = snap(children);
      const { run, body } = load(withDryRun(src, false), { children, today: '2026-11-19' });
      assert.throws(() => run.scaffoldNextWeek(), /is not a real date/, dates[0]);
      assertUnchanged(body, before);
    }
  }],

  ['DRY_RUN as committed writes nothing', (src) => {
    const children = tab();
    const before = snap(children);
    const { run, body, logs } = load(src, { children, today: '2026-11-19' });
    assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026');
    assertUnchanged(body, before);
    assert.ok(logs.some((l) => l.startsWith('DRY_RUN')));
  }],

  ['checkScaffold() never writes, even with DRY_RUN = false', (src) => {
    const children = tab();
    const before = snap(children);
    const { run, body, logs } = load(withDryRun(src, false), { children, today: '2026-11-19' });
    assert.equal(run.checkScaffold(), 'Nov 26, 2026');
    assertUnchanged(body, before);
    assert.ok(logs.some((l) => /^Opened the tab in \d+ ms; read \d+ of \d+ elements in \d+ ms\.$/.test(l)), 'no timing line');
  }],

  ['top two dated headings not newest-first: throws, writes nothing', (src) => {
    for (const dates of [['Nov 12, 2026', 'Nov 19, 2026', 'Nov 5, 2026'], ['Nov 19, 2026', 'Nov 19, 2026', 'Nov 12, 2026']]) {
      const children = tab({ dates });
      const before = snap(children);
      const { run, body } = load(withDryRun(src, false), { children, today: '2026-11-19' });
      assert.throws(() => run.scaffoldNextWeek(), /not newest-first/, dates.join(' / '));
      assertUnchanged(body, before);
    }
  }],

  ['fewer than two dated sections: throws, writes nothing', (src) => {
    for (const dates of [['Nov 19, 2026'], []]) {
      const children = tab({ dates });
      const before = snap(children);
      const { run, body } = load(withDryRun(src, false), { children, today: '2026-11-19' });
      assert.throws(() => run.scaffoldNextWeek(), /Need >= 2 dated sections/);
      assertUnchanged(body, before);
    }
  }],

  ['an unsupported element is skipped and the check still holds', (src) => {
    const toc = new El(ElementType.TABLE_OF_CONTENTS);
    const children = tab({ extraInNewest: [toc] });
    const before = snap(children);
    const { run, body, logs } = load(withDryRun(src, false), { children, today: '2026-11-19' });
    assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026');
    assertInserted(body, before, { from: TOP, count: SECTION, newLabel: 'Nov 26, 2026', skipped: [ElementType.TABLE_OF_CONTENTS] });
    assert.ok(!body.children.some((el) => el.copiedFrom === toc.uid), 'the table of contents was copied');
    assert.ok(logs.includes('Skipped unsupported element type: TABLE_OF_CONTENTS'));
  }],

  ['a table is copied as a new table', (src) => {
    const children = tab();
    const source = children.slice(TOP, TOP + SECTION).find((el) => el.type === ElementType.TABLE);
    const { run, body } = load(withDryRun(src, false), { children, today: '2026-11-19' });
    run.scaffoldNextWeek();
    const copy = body.children.slice(TOP, TOP + SECTION).find((el) => el.type === ElementType.TABLE);
    assert.ok(copy && copy !== source && copy.copiedFrom === source.uid, 'no new table in the copy');
    assert.notEqual(copy.rows, source.rows);
    assert.deepEqual(copy.rows, source.rows);
  }],

  ['the year boundary: Dec 31, 2026 opens Jan 7, 2027', (src) => {
    const children = tab({ newest: [2026, 11, 31] });
    const before = snap(children);
    const { run, body } = load(withDryRun(src, false), { children, today: '2026-12-31' });
    assert.equal(run.scaffoldNextWeek(), 'Jan 7, 2027');
    assertInserted(body, before, { from: TOP, count: SECTION, newLabel: 'Jan 7, 2027' });
  }],

  ['weeks across a clock change keep their dates', (src) => {
    const cases = [[[2026, 2, 5], '2026-03-05', 'Mar 12, 2026'], [[2026, 2, 26], '2026-03-26', 'Apr 2, 2026'],
      [[2026, 3, 2], '2026-04-02', 'Apr 9, 2026'], [[2026, 8, 24], '2026-09-24', 'Oct 1, 2026'],
      [[2026, 9, 22], '2026-10-22', 'Oct 29, 2026'], [[2026, 9, 29], '2026-10-29', 'Nov 5, 2026']];
    for (const [newest, today, next] of cases) {
      const { run } = load(withDryRun(src, false), { children: tab({ newest }), today });
      assert.equal(run.scaffoldNextWeek(), next, `${today} in ${process.env.TZ || 'the local zone'}`);
    }
  }],

  ['trailing spaces on a dated heading still mark the section', (src) => {
    const children = tab({ dates: ['Nov 19, 2026  ', 'Nov 12, 2026', 'Nov 5, 2026'] });
    const before = snap(children);
    const { run, body } = load(withDryRun(src, false), { children, today: '2026-11-19' });
    assert.equal(run.scaffoldNextWeek(), 'Nov 26, 2026');
    assertInserted(body, before, { from: TOP, count: SECTION, newLabel: 'Nov 26, 2026' });
  }],

  ['the wrong tab throws before anything is read', (src) => {
    const children = tab();
    const before = snap(children);
    const other = new Body(tab());
    const { run, body } = load(withDryRun(src, false), {
      children, today: '2026-11-19', tabs: [{ id: 't.1', title: 'Archive', body: other }, { id: 't.2', title: 'Notes', body: other }],
    });
    assert.throws(() => run.scaffoldNextWeek(), /Tab t\.0 not found\. Available: t\.1 \(Archive\), t\.2 \(Notes\)/);
    assertUnchanged(body, before);
    assert.equal(other.stats.getChild + other.stats.getNumChildren, 0);
  }],

  ['an insert that goes wrong is caught: Aborting', (src) => {
    const faults = [
      [{ kind: 'extra-heading', at: 2, text: 'Nov 19, 2026' }, /^Error: Aborting: expected the dated headings/],
      [{ kind: 'dropped-insert', at: 2 }, /^Error: Aborting: expected the dated headings/],
      // A stray heading that is not a real date makes the check itself throw: still an abort with the undo note.
      [{ kind: 'extra-heading', at: 2, text: 'Nov 31, 2026' }, /^Error: Aborting: "Nov 31, 2026" reads like a week heading but is not a real date\. The document was modified/],
    ];
    for (const [fault, want] of faults) {
      const { run } = load(withDryRun(src, false), { children: tab(), today: '2026-11-19', fault });
      let err = null;
      try { run.scaffoldNextWeek(); } catch (e) { err = String(e); }
      const what = `${fault.kind} ${fault.text || ''}`;
      assert.ok(err, `${what}: no error`);
      assert.match(err, want, what);
      assert.match(err, /undo it/, what);
      assert.doesNotMatch(err, /Nothing was written/, what);
    }
  }],
];

class HarnessError extends Error {}

function runSuite(src, { quiet = false } = {}) {
  const failed = [];
  for (const [name, test] of CASES) {
    try {
      test(src);
      if (!quiet) console.log(`ok    ${name}`);
    } catch (e) {
      if (e instanceof HarnessError) throw e;
      failed.push(name);
      if (!quiet) console.log(`FAIL  ${name}\n      ${String(e && e.message).split('\n')[0]}`);
    }
  }
  return failed;
}

// ---------------------------------------------------------------- mutants

const MUTANTS = [
  ['the scan walks the whole tab',
    'for (let i = 0; i < total && marks.length < 2; i++) {', 'for (let i = 0; i < total; i++) {'],
  ['the scan counts the tab at every step',
    'for (let i = 0; i < total && marks.length < 2; i++) {', 'for (let i = 0; i < body.getNumChildren() && marks.length < 2; i++) {'],
  ['the check walks the whole tab',
    'for (let i = 0; i <= end; i++) {', 'for (let i = 0; i < body.getNumChildren(); i++) {'],
  ['the guard is gone',
    'if (newest > today) {', 'if (false) {'],
  ['the guard is off by a day',
    'if (newest > today) {', 'if (newest >= today) {'],
  ['no meeting-hour rule',
    'if (newest === today && hour < OPENS_FROM_HOUR) {', 'if (false) {'],
  ['the meeting-hour rule an hour late',
    'const OPENS_FROM_HOUR = TRIGGER_HOUR - 1;', 'const OPENS_FROM_HOUR = TRIGGER_HOUR;'],
  ['no week-ahead check',
    'if (newest > weekOn) {', 'if (false) {'],
  ['no real-date check',
    'if (MONTHS.indexOf(m[1]) < 0 || date.getDate() !== Number(m[2])) {', 'if (false) {'],
  ["the guard's month is off by one",
    "('0' + (d.getMonth() + 1)).slice(-2)", "('0' + d.getMonth()).slice(-2)"],
  ['read and write in one loop',
    'const copy = copies[j];', 'const copy = body.getChild(from + j).copy();'],
  ['the post-condition is off',
    'problem = checkTop_(body, added, marks, label);', 'problem = null;'],
  ['a throw after the insert reads as nothing written',
    "problem = String((e && e.message) || e).replace(/\\.? Nothing was written\\.$/, '');", 'throw e;'],
  ["the guard reads the newest section's day, not today's",
    "Utilities.formatDate(now, TZ, 'yyyy-MM-dd')", "Utilities.formatDate(marks[0].date, TZ, 'yyyy-MM-dd')"],
  ["the meeting-hour rule reads the newest section's hour, not now's",
    "Utilities.formatDate(now, TZ, 'H')", "Utilities.formatDate(marks[0].date, TZ, 'H')"],
  ['no re-stamp',
    'body.getChild(from).asParagraph().setText(label);', ''],
  ['no newest-first check',
    'if (marks[0].date.getTime() <= marks[1].date.getTime()) {', 'if (false) {'],
  ['checkScaffold() follows DRY_RUN',
    'return scaffold_(true);', 'return scaffold_(DRY_RUN);'],
  ['next week is six days on',
    'addDays_(marks[0].date, 7)', 'addDays_(marks[0].date, 6)'],
  ['a skipped element is still counted',
    "Logger.log('Skipped unsupported element type: ' + copy.getType());",
    "cursor++; Logger.log('Skipped unsupported element type: ' + copy.getType());"],
];

function mutate() {
  console.log('control (unmutated scaffold.gs):');
  const control = runSuite(SOURCE, { quiet: true });
  if (control.length) {
    console.log(`  RED on the control: ${control.join('; ')}. Nothing below would mean anything.`);
    return 2;
  }
  console.log(`  ${CASES.length} of ${CASES.length} passed`);
  let survived = 0;
  for (const [name, from, to] of MUTANTS) {
    const n = SOURCE.split(from).length - 1;
    if (n !== 1) throw new HarnessError(`mutant "${name}": its line is in scaffold.gs ${n} times, not once`);
    let failed;
    try {
      failed = runSuite(SOURCE.replace(from, to), { quiet: true });
    } catch (e) {
      if (e instanceof HarnessError) throw e;
      failed = [`the suite crashed: ${e.message}`];
    }
    if (failed.length) {
      console.log(`killed    ${name}  (by: ${failed.join('; ')})`);
    } else {
      survived++;
      console.log(`SURVIVED  ${name}`);
    }
  }
  console.log(`${MUTANTS.length - survived} of ${MUTANTS.length} mutants killed`);
  return survived ? 1 : 0;
}

function tzMatrix() {
  let red = 0;
  for (const tz of ZONES) {
    const r = spawnSync(process.execPath, [SELF], { env: { ...process.env, TZ: tz }, encoding: 'utf8' });
    const tail = (r.stdout || '').trim().split('\n').pop();
    console.log(`${r.status === 0 ? 'ok  ' : 'RED '}  TZ=${tz}: ${tail}`);
    if (r.status !== 0) { red++; process.stdout.write(r.stdout || ''); process.stdout.write(r.stderr || ''); }
  }
  return red ? 1 : 0;
}

function main(argv) {
  try {
    if (argv.includes('--mutate')) return mutate();
    if (argv.includes('--tz-matrix')) return tzMatrix();
    const failed = runSuite(SOURCE);
    console.log(`${CASES.length - failed.length} of ${CASES.length} passed`);
    return failed.length ? 1 : 0;
  } catch (e) {
    if (e instanceof HarnessError) { console.log(`HARNESS: ${e.message}`); return 2; }
    throw e;
  }
}

process.exitCode = main(process.argv.slice(2));
