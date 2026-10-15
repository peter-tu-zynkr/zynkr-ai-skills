import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { Unreadable, loadYaml, markReadings, readFrontmatter, readFrontmatterKey, readMark, splitMatter } from './frontmatter.mjs';

const unreadable = (fn, label) => assert.throws(fn, (err) => err instanceof Unreadable, label);
const fm = (...lines) => `---\n${lines.join('\n')}\n---\nBody.\n`;

describe('gray-matter: the split', () => {
  test('no frontmatter, a BOM, a longer rule, an empty block', () => {
    assert.deepEqual(readFrontmatter('# Title\n'), { data: {}, content: '# Title\n' });
    assert.equal(readFrontmatter('\ufeff---\nname: a\n---\nx').data.name, 'a');
    assert.deepEqual(splitMatter('----\nname: a\n----\n').yaml, null, 'four dashes open nothing');
    assert.deepEqual(readFrontmatter('---\n# only a comment\n---\nBody').data, {});
    assert.equal(readFrontmatter('---\nname: a\n---\r\nBody').content, 'Body');
  });

  test('the first line starting with --- closes the block, as gray-matter reads it', () => {
    const { data, content } = readFrontmatter('---\nname: a\n---more\nrest\n');
    assert.deepEqual(data, { name: 'a' });
    assert.equal(content, 'more\nrest\n');
  });

  test('no closing line: the rest is YAML and there is no body', () => {
    assert.deepEqual(readFrontmatter('---\nname: a\nstatus: Done\n'), { data: { name: 'a', status: 'Done' }, content: '' });
    unreadable(() => readFrontmatter('---\nname: a\n# Heading: with a colon\nSome text\n'), 'markdown read as YAML');
  });

  test('a language after the opener is refused, as the line-based guards cannot read it', () => {
    unreadable(() => readFrontmatter('---yaml\nname: a\n---\n'));
  });
});

describe('js-yaml 3.14: scalars and types', () => {
  test('plain scalars resolve as js-yaml resolves them', () => {
    const d = loadYaml(
      [
        'a: plain text',
        'b: ~',
        'c: null',
        'd: True',
        'e: false',
        'f: 0x1F',
        'g: 1_000',
        'h: 2.06',
        'i: .inf',
        'j: 2026-10-15',
        'k: 2026-10-15T08:00:00Z',
        'l: 190:20:30',
        'm: yes',
        'n: 1.2.3',
        'o: text # a comment',
        'p: a#b',
        'q:',
      ].join('\n'),
    );
    assert.equal(d.a, 'plain text');
    assert.equal(d.b, null);
    assert.equal(d.c, null);
    assert.equal(d.d, true);
    assert.equal(d.e, false);
    assert.equal(d.f, 31);
    assert.equal(d.g, 1000);
    assert.equal(d.h, 2.06, 'an unquoted sheetId is a number, which the schema refuses');
    assert.equal(d.i, Infinity);
    assert.ok(d.j instanceof Date);
    assert.ok(d.k instanceof Date);
    assert.equal(d.l, 685230, 'base 60, as js-yaml 3 reads it');
    assert.equal(d.m, 'yes', 'YAML 1.2: yes is a string');
    assert.equal(d.n, '1.2.3');
    assert.equal(d.o, 'text');
    assert.equal(d.p, 'a#b');
    assert.equal(d.q, null);
  });

  test('a plain scalar continues on more-indented lines, folded with spaces', () => {
    assert.equal(loadYaml('description: one\n  two\n\n  three\nname: x').description, 'one two\nthree');
  });

  test('double quotes: escapes, folding, an escaped line break, and continuation at column 0', () => {
    const d = loadYaml(
      [
        'a: "say \\"hi\\"\\tthen\\n\\u00e9\\x41\\/"',
        'b: "one',
        '  two',
        '',
        '  three"',
        'c: "joined\\',
        '   here"',
        // The workbench's own files continue a quoted description at column 0 (js-yaml only warns).
        'd: "Use this agent when.',
        '',
        '<example>',
        'Context: a line that looks like a key',
        'user: \\"quoted\\"',
        '</example>"',
        'e: ""',
      ].join('\n'),
    );
    assert.equal(d.a, 'say "hi"\tthen\néA/');
    assert.equal(d.b, 'one two\nthree');
    assert.equal(d.c, 'joinedhere');
    assert.equal(d.d, 'Use this agent when.\n<example> Context: a line that looks like a key user: "quoted" </example>');
    assert.equal(d.e, '');
    unreadable(() => loadYaml('a: "bad \\q escape"'));
    unreadable(() => loadYaml('a: "never closed\nb: x'));
  });

  test("single quotes: '' and folding", () => {
    const d = loadYaml("a: 'it''s'\nb: 'one\n  two'");
    assert.equal(d.a, "it's");
    assert.equal(d.b, 'one two');
  });

  test('block scalars: literal, folded, chomping, an indentation indicator, more-indented lines', () => {
    const d = loadYaml(
      [
        'lit: |',
        '  one',
        '    two',
        '',
        'keep: |+',
        '  kept',
        '',
        'strip: |-',
        '  stripped',
        'fold: >-',
        '  a',
        '  b',
        '',
        '  c',
        '    indented',
        '  d',
        'indicator: |2',
        '   three spaces',
        'after: x',
      ].join('\n'),
    );
    assert.equal(d.lit, 'one\n  two\n');
    assert.equal(d.keep, 'kept\n\n');
    assert.equal(d.strip, 'stripped');
    assert.equal(d.fold, 'a b\nc\n  indented\nd');
    assert.equal(d.indicator, ' three spaces\n');
    assert.equal(d.after, 'x');
  });
});

describe('js-yaml 3.14: collections', () => {
  test('block sequences, indented or not, flow sequences, and a nested mapping', () => {
    const d = loadYaml(
      [
        'synergy:',
        '  - "1.01"',
        '  - plain',
        'steps:',
        '- one',
        '- two',
        'handoff: ["a", b, 3,]',
        'nested: [[x], []]',
        'security_audits:',
        '  socket: pass',
        '  snyk: "fail"',
        'empty: []',
      ].join('\n'),
    );
    assert.deepEqual(d.synergy, ['1.01', 'plain']);
    assert.deepEqual(d.steps, ['one', 'two']);
    assert.deepEqual(d.handoff, ['a', 'b', 3]);
    assert.deepEqual(d.nested, [['x'], []]);
    assert.deepEqual(d.security_audits, { socket: 'pass', snyk: 'fail' });
    assert.deepEqual(d.empty, []);
  });

  test('a key with nothing after it, then the next key, is null', () => {
    assert.deepEqual(loadYaml('a:\nb: 1'), { a: null, b: 1 });
  });

  test('what js-yaml refuses, and what this reader leaves out, is Unreadable', () => {
    const cases = {
      'a repeated key': 'name: a\nname: b',
      'a repeated key, quoted once': 'visibility: public\n"visibility": team',
      'an anchor': 'a: &x 1\nb: 2',
      'an alias': 'a: 1\nb: *x',
      'a tag': 'a: !!str 1',
      'a flow mapping': 'a: {b: 1}',
      'a whole-document flow mapping': '{visibility: team, name: x}',
      'an explicit key': '? a\n: b',
      'a merge key': 'base: [1]\n<<: x',
      'a directive': '%YAML 1.2\n---\na: 1',
      'two documents': 'a: 1\n---\nb: 2',
      'bad indentation': 'a: 1\n  b: 2',
      'a value with a colon and a space': 'a: b: c',
      'a pair inside a flow sequence': 'a: [b: c]',
      'a key over two lines': 'name: a\nSome text\n',
    };
    for (const [label, text] of Object.entries(cases)) unreadable(() => loadYaml(text), label);
  });
});

describe("the workbench's line-based reading", () => {
  test('a top-level key, quotes and a comment stripped, inside the --- block only', () => {
    assert.deepEqual(readMark(fm('name: a', 'visibility : "client"  # note')), { value: 'client', line: 3 });
    assert.equal(readMark(fm('name: a')), null);
    assert.equal(readMark('# no frontmatter\nvisibility: public\n'), null);
    assert.equal(readMark('---\nname: a\n---\nvisibility: public\n'), null, 'a key after the block does not count');
    assert.equal(readFrontmatterKey(fm('install_command: npx skills add x'), 'install_command').value, 'npx skills add x');
  });

  test('markReadings: both readings, and where they part', () => {
    assert.deepEqual(markReadings(fm('name: a', 'visibility: public')), { line: 'public', yaml: 'public' });
    assert.deepEqual(markReadings(fm('name: a')), { line: undefined, yaml: undefined });
    // A quoted key hides the mark from the line reader; YAML still reads it.
    assert.deepEqual(markReadings(fm('name: a', '"visibility": team')), { line: undefined, yaml: 'team' });
    // A block scalar holding the words: the line reader sees nothing, YAML a description.
    assert.deepEqual(markReadings(fm('description: |', '  visibility: public')), { line: undefined, yaml: undefined });
    // A flow mapping over lines: the line reader reads public, YAML is refused (null: unreadable here).
    assert.deepEqual(markReadings('---\n{name: a, x: [\nvisibility: public\n], visibility: team}\n---\n'), { line: 'public', yaml: null });
    assert.deepEqual(markReadings('---\nvisibility: public\nname: a\nvisibility: team\n---\n'), { line: 'public', yaml: null });
  });
});
