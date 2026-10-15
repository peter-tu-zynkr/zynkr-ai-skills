/**
 * frontmatter.mjs — read a skill file's frontmatter the way the private workbench reads it
 * (ATL-113 Part D, D-142), with no dependency.
 *
 * The workbench builds every zynkr.ai listing from gray-matter 4.0.3, which hands the block between
 * the `---` lines to js-yaml 3.14.2 (`safeLoad`). The shelf now builds the listings itself, from the
 * files it holds, so it must read those files the same way. This file is that reading:
 *
 *   - `splitMatter` is gray-matter's split, line for line (BOM, the `---` opener, the first `\n---`
 *     that closes it, comment-only blocks, the body after it);
 *   - `loadYaml` is js-yaml's loader for the part of YAML skill files use. Its scalar readers (plain,
 *     single- and double-quoted, block `|` and `>`), block mappings and sequences, flow sequences,
 *     implicit types (null, bool, int, float, timestamp) and duplicate-key refusal are ported from
 *     js-yaml 3.14.2's lib/js-yaml/loader.js and type/*.js. What skill files never use is refused
 *     instead of guessed: tags (`!`), anchors (`&`), aliases (`*`), flow mappings (`{}`), explicit
 *     keys (`?`), merge keys (`<<`), directives (`%`), more than one document, and a `---yaml` style
 *     opener. A refusal is an `Unreadable`: the caller treats the file as one it cannot vouch for.
 *   - `readFrontmatterKey` / `readMark` are the workbench's line-based mark reader, word for word.
 *     A mark counts only when both readings agree.
 *
 * Nothing here prints anything: a value read from a file never reaches a log through this module.
 */

/** The frontmatter is outside what this reader takes, or js-yaml itself would refuse it. */
export class Unreadable extends Error {}

const unreadable = (why) => {
  throw new Unreadable(why);
};

// ── gray-matter 4.0.3: the split ─────────────────────────────────────────────

/**
 * { hasMatter, yaml, content } as gray-matter splits `text`: `yaml` is the raw block (null when the
 * file has no frontmatter, or the block holds only whitespace and comments), `content` the body.
 */
export function splitMatter(text) {
  if (text === '') return { hasMatter: false, yaml: null, content: '' };
  const str0 = text.charAt(0) === '﻿' ? text.slice(1) : text;
  if (str0.slice(0, 3) !== '---') return { hasMatter: false, yaml: null, content: str0 };
  // `----` and longer is no opener.
  if (str0.charAt(3) === '-') return { hasMatter: false, yaml: null, content: str0 };
  let str = str0.slice(3);
  const len = str.length;
  // gray-matter reads a language name after the opener (`---yaml`); none of the workbench's guards
  // do, so a file that has one is refused rather than read two ways.
  const nl = str.search(/\r?\n/);
  const language = str.slice(0, nl);
  if (language.trim() !== '') unreadable('a language after the opening ---');
  let closeIndex = str.indexOf('\n---');
  if (closeIndex === -1) closeIndex = len;
  const block = str.slice(0, closeIndex);
  // No closing line: gray-matter reads the rest of the file as YAML and leaves no body.
  let content = '';
  if (closeIndex !== len) {
    content = str.slice(closeIndex + 4);
    if (content[0] === '\r') content = content.slice(1);
    if (content[0] === '\n') content = content.slice(1);
  }
  const empty = block.replace(/^\s*#[^\n]+/gm, '').trim() === '';
  return { hasMatter: true, yaml: empty ? null : block, content };
}

/**
 * gray-matter's `data` and `content` for `text`: {} when there is no frontmatter. Throws Unreadable
 * when the frontmatter is outside this reader.
 */
export function readFrontmatter(text) {
  const { yaml, content } = splitMatter(text);
  return { data: yaml === null ? {} : loadYaml(yaml), content };
}

// ── js-yaml 3.14.2: character classes and helpers (verbatim) ─────────────────

const CONTEXT_FLOW_IN = 1;
const CONTEXT_FLOW_OUT = 2;
const CONTEXT_BLOCK_IN = 3;
const CONTEXT_BLOCK_OUT = 4;

const CHOMPING_CLIP = 1;
const CHOMPING_STRIP = 2;
const CHOMPING_KEEP = 3;

// eslint-disable-next-line no-control-regex
const PATTERN_NON_PRINTABLE = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F￾￿]|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?:[^\uD800-\uDBFF]|^)[\uDC00-\uDFFF]/;

const isEOL = (c) => c === 0x0a || c === 0x0d;
const isWhiteSpace = (c) => c === 0x09 || c === 0x20;
const isWsOrEol = (c) => c === 0x09 || c === 0x20 || c === 0x0a || c === 0x0d;
const isFlowIndicator = (c) => c === 0x2c || c === 0x5b || c === 0x5d || c === 0x7b || c === 0x7d;

function fromHexCode(c) {
  if (c >= 0x30 && c <= 0x39) return c - 0x30;
  const lc = c | 0x20;
  if (lc >= 0x61 && lc <= 0x66) return lc - 0x61 + 10;
  return -1;
}

function escapedHexLen(c) {
  if (c === 0x78) return 2;
  if (c === 0x75) return 4;
  if (c === 0x55) return 8;
  return 0;
}

function fromDecimalCode(c) {
  if (c >= 0x30 && c <= 0x39) return c - 0x30;
  return -1;
}

function simpleEscapeSequence(c) {
  return c === 0x30 ? '\x00'
    : c === 0x61 ? '\x07'
      : c === 0x62 ? '\x08'
        : c === 0x74 ? '\x09'
          : c === 0x09 ? '\x09'
            : c === 0x6e ? '\x0A'
              : c === 0x76 ? '\x0B'
                : c === 0x66 ? '\x0C'
                  : c === 0x72 ? '\x0D'
                    : c === 0x65 ? '\x1B'
                      : c === 0x20 ? ' '
                        : c === 0x22 ? '\x22'
                          : c === 0x2f ? '/'
                            : c === 0x5c ? '\x5C'
                              : c === 0x4e ? '\x85'
                                : c === 0x5f ? '\xA0'
                                  : c === 0x4c ? ' '
                                    : c === 0x50 ? ' '
                                      : '';
}

const simpleEscapeCheck = new Array(256);
const simpleEscapeMap = new Array(256);
for (let i = 0; i < 256; i++) {
  simpleEscapeCheck[i] = simpleEscapeSequence(i) ? 1 : 0;
  simpleEscapeMap[i] = simpleEscapeSequence(i);
}

function charFromCodepoint(c) {
  if (c <= 0xffff) return String.fromCharCode(c);
  return String.fromCharCode(((c - 0x010000) >> 10) + 0xd800, ((c - 0x010000) & 0x03ff) + 0xdc00);
}

/** A plain object's own key, set without touching its prototype (js-yaml's setProperty). */
function setProperty(object, key, value) {
  if (key === '__proto__') {
    Object.defineProperty(object, key, { configurable: true, enumerable: true, writable: true, value });
  } else {
    object[key] = value;
  }
}

// ── js-yaml 3.14.2: implicit types of the DEFAULT_SAFE schema ────────────────

function resolveNull(data) {
  if (data === null) return true;
  const max = data.length;
  return (max === 1 && data === '~') || (max === 4 && (data === 'null' || data === 'Null' || data === 'NULL'));
}

function resolveBool(data) {
  if (data === null) return false;
  const max = data.length;
  return (max === 4 && (data === 'true' || data === 'True' || data === 'TRUE'))
    || (max === 5 && (data === 'false' || data === 'False' || data === 'FALSE'));
}

const isHexCode = (c) => (c >= 0x30 && c <= 0x39) || (c >= 0x41 && c <= 0x46) || (c >= 0x61 && c <= 0x66);
const isOctCode = (c) => c >= 0x30 && c <= 0x37;
const isDecCode = (c) => c >= 0x30 && c <= 0x39;

function resolveInt(data) {
  if (data === null) return false;
  const max = data.length;
  let index = 0;
  let hasDigits = false;
  if (!max) return false;
  let ch = data[index];
  if (ch === '-' || ch === '+') ch = data[++index];
  if (ch === '0') {
    if (index + 1 === max) return true;
    ch = data[++index];
    if (ch === 'b') {
      index++;
      for (; index < max; index++) {
        ch = data[index];
        if (ch === '_') continue;
        if (ch !== '0' && ch !== '1') return false;
        hasDigits = true;
      }
      return hasDigits && ch !== '_';
    }
    if (ch === 'x') {
      index++;
      for (; index < max; index++) {
        ch = data[index];
        if (ch === '_') continue;
        if (!isHexCode(data.charCodeAt(index))) return false;
        hasDigits = true;
      }
      return hasDigits && ch !== '_';
    }
    for (; index < max; index++) {
      ch = data[index];
      if (ch === '_') continue;
      if (!isOctCode(data.charCodeAt(index))) return false;
      hasDigits = true;
    }
    return hasDigits && ch !== '_';
  }
  if (ch === '_') return false;
  for (; index < max; index++) {
    ch = data[index];
    if (ch === '_') continue;
    if (ch === ':') break;
    if (!isDecCode(data.charCodeAt(index))) return false;
    hasDigits = true;
  }
  if (!hasDigits || ch === '_') return false;
  if (ch !== ':') return true;
  return /^(:[0-5]?[0-9])+$/.test(data.slice(index));
}

function constructInt(data) {
  let value = data.indexOf('_') !== -1 ? data.replace(/_/g, '') : data;
  let sign = 1;
  let ch = value[0];
  if (ch === '-' || ch === '+') {
    if (ch === '-') sign = -1;
    value = value.slice(1);
    ch = value[0];
  }
  if (value === '0') return 0;
  if (ch === '0') {
    if (value[1] === 'b') return sign * parseInt(value.slice(2), 2);
    if (value[1] === 'x') return sign * parseInt(value, 16);
    return sign * parseInt(value, 8);
  }
  if (value.indexOf(':') !== -1) {
    const digits = [];
    value.split(':').forEach((v) => digits.unshift(parseInt(v, 10)));
    let total = 0;
    let base = 1;
    digits.forEach((d) => {
      total += d * base;
      base *= 60;
    });
    return sign * total;
  }
  return sign * parseInt(value, 10);
}

const YAML_FLOAT_PATTERN = new RegExp(
  '^(?:[-+]?(?:0|[1-9][0-9_]*)(?:\\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?' +
    '|\\.[0-9_]+(?:[eE][-+]?[0-9]+)?' +
    '|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\\.[0-9_]*' +
    '|[-+]?\\.(?:inf|Inf|INF)' +
    '|\\.(?:nan|NaN|NAN))$',
);

function resolveFloat(data) {
  if (data === null) return false;
  return YAML_FLOAT_PATTERN.test(data) && data[data.length - 1] !== '_';
}

function constructFloat(data) {
  let value = data.replace(/_/g, '').toLowerCase();
  const sign = value[0] === '-' ? -1 : 1;
  if ('+-'.indexOf(value[0]) >= 0) value = value.slice(1);
  if (value === '.inf') return sign === 1 ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
  if (value === '.nan') return NaN;
  if (value.indexOf(':') >= 0) {
    const digits = [];
    value.split(':').forEach((v) => digits.unshift(parseFloat(v, 10)));
    let total = 0.0;
    let base = 1;
    digits.forEach((d) => {
      total += d * base;
      base *= 60;
    });
    return sign * total;
  }
  return sign * parseFloat(value, 10);
}

const YAML_DATE_REGEXP = /^([0-9][0-9][0-9][0-9])-([0-9][0-9])-([0-9][0-9])$/;
const YAML_TIMESTAMP_REGEXP =
  /^([0-9][0-9][0-9][0-9])-([0-9][0-9]?)-([0-9][0-9]?)(?:[Tt]|[ \t]+)([0-9][0-9]?):([0-9][0-9]):([0-9][0-9])(?:\.([0-9]*))?(?:[ \t]*(Z|([-+])([0-9][0-9]?)(?::([0-9][0-9]))?))?$/;

function resolveTimestamp(data) {
  if (data === null) return false;
  return YAML_DATE_REGEXP.exec(data) !== null || YAML_TIMESTAMP_REGEXP.exec(data) !== null;
}

function constructTimestamp(data) {
  let match = YAML_DATE_REGEXP.exec(data);
  if (match === null) match = YAML_TIMESTAMP_REGEXP.exec(data);
  if (match === null) throw new Error('Date resolve error');
  const year = +match[1];
  const month = +match[2] - 1;
  const day = +match[3];
  if (!match[4]) return new Date(Date.UTC(year, month, day));
  const hour = +match[4];
  const minute = +match[5];
  const second = +match[6];
  let fraction = 0;
  if (match[7]) {
    let f = match[7].slice(0, 3);
    while (f.length < 3) f += '0';
    fraction = +f;
  }
  let delta = null;
  if (match[9]) {
    const tzHour = +match[10];
    const tzMinute = +(match[11] || 0);
    delta = (tzHour * 60 + tzMinute) * 60000;
    if (match[9] === '-') delta = -delta;
  }
  const date = new Date(Date.UTC(year, month, day, hour, minute, second, fraction));
  if (delta) date.setTime(date.getTime() - delta);
  return date;
}

const MERGE_TAG = 'tag:yaml.org,2002:merge';

/** core: null, bool, int, float; default_safe: timestamp, merge — in that order. */
const IMPLICIT = [
  { tag: 'tag:yaml.org,2002:null', resolve: resolveNull, construct: () => null },
  { tag: 'tag:yaml.org,2002:bool', resolve: resolveBool, construct: (d) => d === 'true' || d === 'True' || d === 'TRUE' },
  { tag: 'tag:yaml.org,2002:int', resolve: resolveInt, construct: constructInt },
  { tag: 'tag:yaml.org,2002:float', resolve: resolveFloat, construct: constructFloat },
  { tag: 'tag:yaml.org,2002:timestamp', resolve: resolveTimestamp, construct: constructTimestamp },
  { tag: MERGE_TAG, resolve: (d) => d === '<<' || d === null, construct: (d) => (d !== null ? d : {}) },
];

// ── js-yaml 3.14.2: the loader (scalar readers verbatim; structures restricted) ──

function captureSegment(state, start, end, checkJson) {
  if (start < end) {
    const result = state.input.slice(start, end);
    if (checkJson) {
      for (let p = 0, l = result.length; p < l; p += 1) {
        const c = result.charCodeAt(p);
        if (!(c === 0x09 || (c >= 0x20 && c <= 0x10ffff))) unreadable('a control character in a quoted scalar');
      }
    } else if (PATTERN_NON_PRINTABLE.test(result)) {
      unreadable('non-printable characters');
    }
    state.result += result;
  }
}

function readLineBreak(state) {
  const ch = state.input.charCodeAt(state.position);
  if (ch === 0x0a) {
    state.position++;
  } else if (ch === 0x0d) {
    state.position++;
    if (state.input.charCodeAt(state.position) === 0x0a) state.position++;
  } else {
    unreadable('a line break is expected');
  }
  state.line += 1;
  state.lineStart = state.position;
}

/** Skips spaces, tabs, comments (when allowed) and line breaks; returns how many line breaks. js-yaml
 *  only warns on deficient indentation here, and safeLoad ignores warnings, so this does too. */
function skipSeparationSpace(state, allowComments) {
  let lineBreaks = 0;
  let ch = state.input.charCodeAt(state.position);
  while (ch !== 0) {
    while (isWhiteSpace(ch)) ch = state.input.charCodeAt(++state.position);
    if (allowComments && ch === 0x23) {
      do {
        ch = state.input.charCodeAt(++state.position);
      } while (ch !== 0x0a && ch !== 0x0d && ch !== 0);
    }
    if (isEOL(ch)) {
      readLineBreak(state);
      ch = state.input.charCodeAt(state.position);
      lineBreaks++;
      state.lineIndent = 0;
      while (ch === 0x20) {
        state.lineIndent++;
        ch = state.input.charCodeAt(++state.position);
      }
    } else {
      break;
    }
  }
  return lineBreaks;
}

function testDocumentSeparator(state) {
  let p = state.position;
  let ch = state.input.charCodeAt(p);
  if ((ch === 0x2d || ch === 0x2e) && ch === state.input.charCodeAt(p + 1) && ch === state.input.charCodeAt(p + 2)) {
    p += 3;
    ch = state.input.charCodeAt(p);
    if (ch === 0 || isWsOrEol(ch)) return true;
  }
  return false;
}

function writeFoldedLines(state, count) {
  if (count === 1) state.result += ' ';
  else if (count > 1) state.result += '\n'.repeat(count - 1);
}

function readPlainScalar(state, nodeIndent, withinFlowCollection) {
  const kind = state.kind;
  const result = state.result;
  let ch = state.input.charCodeAt(state.position);
  if (
    isWsOrEol(ch) || isFlowIndicator(ch) || ch === 0x23 || ch === 0x26 || ch === 0x2a || ch === 0x21 ||
    ch === 0x7c || ch === 0x3e || ch === 0x27 || ch === 0x22 || ch === 0x25 || ch === 0x40 || ch === 0x60
  ) {
    return false;
  }
  if (ch === 0x3f || ch === 0x2d) {
    const following = state.input.charCodeAt(state.position + 1);
    if (isWsOrEol(following) || (withinFlowCollection && isFlowIndicator(following))) return false;
  }
  state.kind = 'scalar';
  state.result = '';
  let captureStart = state.position;
  let captureEnd = state.position;
  let hasPendingContent = false;
  let line;
  while (ch !== 0) {
    if (ch === 0x3a) {
      const following = state.input.charCodeAt(state.position + 1);
      if (isWsOrEol(following) || (withinFlowCollection && isFlowIndicator(following))) break;
    } else if (ch === 0x23) {
      const preceding = state.input.charCodeAt(state.position - 1);
      if (isWsOrEol(preceding)) break;
    } else if ((state.position === state.lineStart && testDocumentSeparator(state)) || (withinFlowCollection && isFlowIndicator(ch))) {
      break;
    } else if (isEOL(ch)) {
      line = state.line;
      const lineStart = state.lineStart;
      const lineIndent = state.lineIndent;
      skipSeparationSpace(state, false);
      if (state.lineIndent >= nodeIndent) {
        hasPendingContent = true;
        ch = state.input.charCodeAt(state.position);
        continue;
      } else {
        state.position = captureEnd;
        state.line = line;
        state.lineStart = lineStart;
        state.lineIndent = lineIndent;
        break;
      }
    }
    if (hasPendingContent) {
      captureSegment(state, captureStart, captureEnd, false);
      writeFoldedLines(state, state.line - line);
      captureStart = captureEnd = state.position;
      hasPendingContent = false;
    }
    if (!isWhiteSpace(ch)) captureEnd = state.position + 1;
    ch = state.input.charCodeAt(++state.position);
  }
  captureSegment(state, captureStart, captureEnd, false);
  if (state.result) return true;
  state.kind = kind;
  state.result = result;
  return false;
}

function readSingleQuotedScalar(state) {
  let ch = state.input.charCodeAt(state.position);
  if (ch !== 0x27) return false;
  state.kind = 'scalar';
  state.result = '';
  state.position++;
  let captureStart = state.position;
  let captureEnd = state.position;
  while ((ch = state.input.charCodeAt(state.position)) !== 0) {
    if (ch === 0x27) {
      captureSegment(state, captureStart, state.position, true);
      ch = state.input.charCodeAt(++state.position);
      if (ch === 0x27) {
        captureStart = state.position;
        state.position++;
        captureEnd = state.position;
      } else {
        return true;
      }
    } else if (isEOL(ch)) {
      captureSegment(state, captureStart, captureEnd, true);
      writeFoldedLines(state, skipSeparationSpace(state, false));
      captureStart = captureEnd = state.position;
    } else if (state.position === state.lineStart && testDocumentSeparator(state)) {
      unreadable('the document ends inside a single-quoted scalar');
    } else {
      state.position++;
      captureEnd = state.position;
    }
  }
  return unreadable('the stream ends inside a single-quoted scalar');
}

function readDoubleQuotedScalar(state) {
  let ch = state.input.charCodeAt(state.position);
  if (ch !== 0x22) return false;
  state.kind = 'scalar';
  state.result = '';
  state.position++;
  let captureStart = state.position;
  let captureEnd = state.position;
  let tmp;
  while ((ch = state.input.charCodeAt(state.position)) !== 0) {
    if (ch === 0x22) {
      captureSegment(state, captureStart, state.position, true);
      state.position++;
      return true;
    } else if (ch === 0x5c) {
      captureSegment(state, captureStart, state.position, true);
      ch = state.input.charCodeAt(++state.position);
      if (isEOL(ch)) {
        skipSeparationSpace(state, false);
      } else if (ch < 256 && simpleEscapeCheck[ch]) {
        state.result += simpleEscapeMap[ch];
        state.position++;
      } else if ((tmp = escapedHexLen(ch)) > 0) {
        let hexLength = tmp;
        let hexResult = 0;
        for (; hexLength > 0; hexLength--) {
          ch = state.input.charCodeAt(++state.position);
          if ((tmp = fromHexCode(ch)) >= 0) hexResult = (hexResult << 4) + tmp;
          else unreadable('expected a hexadecimal character');
        }
        state.result += charFromCodepoint(hexResult);
        state.position++;
      } else {
        unreadable('an unknown escape sequence');
      }
      captureStart = captureEnd = state.position;
    } else if (isEOL(ch)) {
      captureSegment(state, captureStart, captureEnd, true);
      writeFoldedLines(state, skipSeparationSpace(state, false));
      captureStart = captureEnd = state.position;
    } else if (state.position === state.lineStart && testDocumentSeparator(state)) {
      unreadable('the document ends inside a double-quoted scalar');
    } else {
      state.position++;
      captureEnd = state.position;
    }
  }
  return unreadable('the stream ends inside a double-quoted scalar');
}

function readBlockScalar(state, nodeIndent) {
  let ch = state.input.charCodeAt(state.position);
  let folding;
  if (ch === 0x7c) folding = false;
  else if (ch === 0x3e) folding = true;
  else return false;
  let chomping = CHOMPING_CLIP;
  let didReadContent = false;
  let detectedIndent = false;
  let textIndent = nodeIndent;
  let emptyLines = 0;
  let atMoreIndented = false;
  let tmp;
  state.kind = 'scalar';
  state.result = '';
  while (ch !== 0) {
    ch = state.input.charCodeAt(++state.position);
    if (ch === 0x2b || ch === 0x2d) {
      if (chomping === CHOMPING_CLIP) chomping = ch === 0x2b ? CHOMPING_KEEP : CHOMPING_STRIP;
      else unreadable('a repeated chomping indicator');
    } else if ((tmp = fromDecimalCode(ch)) >= 0) {
      if (tmp === 0) unreadable('an indentation indicator of 0');
      else if (!detectedIndent) {
        textIndent = nodeIndent + tmp - 1;
        detectedIndent = true;
      } else {
        unreadable('a repeated indentation indicator');
      }
    } else {
      break;
    }
  }
  if (isWhiteSpace(ch)) {
    do {
      ch = state.input.charCodeAt(++state.position);
    } while (isWhiteSpace(ch));
    if (ch === 0x23) {
      do {
        ch = state.input.charCodeAt(++state.position);
      } while (!isEOL(ch) && ch !== 0);
    }
  }
  while (ch !== 0) {
    readLineBreak(state);
    state.lineIndent = 0;
    ch = state.input.charCodeAt(state.position);
    while ((!detectedIndent || state.lineIndent < textIndent) && ch === 0x20) {
      state.lineIndent++;
      ch = state.input.charCodeAt(++state.position);
    }
    if (!detectedIndent && state.lineIndent > textIndent) textIndent = state.lineIndent;
    if (isEOL(ch)) {
      emptyLines++;
      continue;
    }
    if (state.lineIndent < textIndent) {
      if (chomping === CHOMPING_KEEP) {
        state.result += '\n'.repeat(didReadContent ? 1 + emptyLines : emptyLines);
      } else if (chomping === CHOMPING_CLIP) {
        if (didReadContent) state.result += '\n';
      }
      break;
    }
    if (folding) {
      if (isWhiteSpace(ch)) {
        atMoreIndented = true;
        state.result += '\n'.repeat(didReadContent ? 1 + emptyLines : emptyLines);
      } else if (atMoreIndented) {
        atMoreIndented = false;
        state.result += '\n'.repeat(emptyLines + 1);
      } else if (emptyLines === 0) {
        if (didReadContent) state.result += ' ';
      } else {
        state.result += '\n'.repeat(emptyLines);
      }
    } else {
      state.result += '\n'.repeat(didReadContent ? 1 + emptyLines : emptyLines);
    }
    didReadContent = true;
    detectedIndent = true;
    emptyLines = 0;
    const captureStart = state.position;
    while (!isEOL(ch) && ch !== 0) ch = state.input.charCodeAt(++state.position);
    captureSegment(state, captureStart, state.position, false);
  }
  return true;
}

function readFlowCollection(state, nodeIndent) {
  let ch = state.input.charCodeAt(state.position);
  if (ch === 0x7b) unreadable('a flow mapping');
  if (ch !== 0x5b) return false;
  const tag = state.tag;
  const result = [];
  let readNext = true;
  ch = state.input.charCodeAt(++state.position);
  while (ch !== 0) {
    skipSeparationSpace(state, true);
    ch = state.input.charCodeAt(state.position);
    if (ch === 0x5d) {
      state.position++;
      state.tag = tag;
      state.kind = 'sequence';
      state.result = result;
      return true;
    } else if (!readNext) {
      unreadable('a missing comma in a flow sequence');
    }
    if (ch === 0x3f && isWsOrEol(state.input.charCodeAt(state.position + 1))) unreadable('an explicit pair in a flow sequence');
    const line = state.line;
    composeNode(state, nodeIndent, CONTEXT_FLOW_IN, false, true);
    const node = state.result;
    skipSeparationSpace(state, true);
    ch = state.input.charCodeAt(state.position);
    if (state.line === line && ch === 0x3a) unreadable('a pair inside a flow sequence');
    result.push(node);
    skipSeparationSpace(state, true);
    ch = state.input.charCodeAt(state.position);
    if (ch === 0x2c) {
      readNext = true;
      ch = state.input.charCodeAt(++state.position);
    } else {
      readNext = false;
    }
  }
  return unreadable('the stream ends inside a flow sequence');
}

function readBlockSequence(state, nodeIndent) {
  const tag = state.tag;
  const result = [];
  let detected = false;
  let ch = state.input.charCodeAt(state.position);
  while (ch !== 0) {
    if (ch !== 0x2d) break;
    const following = state.input.charCodeAt(state.position + 1);
    if (!isWsOrEol(following)) break;
    detected = true;
    state.position++;
    if (skipSeparationSpace(state, true)) {
      if (state.lineIndent <= nodeIndent) {
        result.push(null);
        ch = state.input.charCodeAt(state.position);
        continue;
      }
    }
    const line = state.line;
    composeNode(state, nodeIndent, CONTEXT_BLOCK_IN, false, true);
    result.push(state.result);
    skipSeparationSpace(state, true);
    ch = state.input.charCodeAt(state.position);
    if ((state.line === line || state.lineIndent > nodeIndent) && ch !== 0) {
      unreadable('bad indentation of a sequence entry');
    } else if (state.lineIndent < nodeIndent) {
      break;
    }
  }
  if (detected) {
    state.tag = tag;
    state.kind = 'sequence';
    state.result = result;
    return true;
  }
  return false;
}

function storeMappingPair(state, result, keyTag, keyNode, valueNode) {
  if (keyTag === MERGE_TAG) unreadable('a merge key (<<)');
  if (keyNode !== null && typeof keyNode === 'object') unreadable('a key that is not a plain value');
  const key = String(keyNode);
  if (Object.prototype.hasOwnProperty.call(result, key)) unreadable('a repeated key');
  setProperty(result, key, valueNode);
}

function readBlockMapping(state, nodeIndent, flowIndent) {
  const tag = state.tag;
  const result = {};
  let keyTag = null;
  let keyNode = null;
  let valueNode = null;
  let allowCompact = false;
  let detected = false;
  let ch = state.input.charCodeAt(state.position);
  while (ch !== 0) {
    const following = state.input.charCodeAt(state.position + 1);
    const line = state.line;
    if ((ch === 0x3f || ch === 0x3a) && isWsOrEol(following)) {
      unreadable('an explicit key (?) or a value with no key');
    } else if (composeNode(state, flowIndent, CONTEXT_FLOW_OUT, false, true)) {
      if (state.line === line) {
        ch = state.input.charCodeAt(state.position);
        while (isWhiteSpace(ch)) ch = state.input.charCodeAt(++state.position);
        if (ch === 0x3a) {
          ch = state.input.charCodeAt(++state.position);
          if (!isWsOrEol(ch)) unreadable('no whitespace after a key\'s colon');
          detected = true;
          allowCompact = false;
          keyTag = state.tag;
          keyNode = state.result;
        } else if (detected) {
          unreadable('a mapping entry with no colon');
        } else {
          state.tag = tag;
          return true;
        }
      } else if (detected) {
        unreadable('a key over more than one line');
      } else {
        state.tag = tag;
        return true;
      }
    } else {
      break;
    }
    if (state.line === line || state.lineIndent > nodeIndent) {
      if (composeNode(state, nodeIndent, CONTEXT_BLOCK_OUT, true, allowCompact)) valueNode = state.result;
      storeMappingPair(state, result, keyTag, keyNode, valueNode);
      keyTag = keyNode = valueNode = null;
      skipSeparationSpace(state, true);
      ch = state.input.charCodeAt(state.position);
    }
    if (state.lineIndent > nodeIndent && ch !== 0) unreadable('bad indentation of a mapping entry');
    else if (state.lineIndent < nodeIndent) break;
  }
  if (detected) {
    state.tag = tag;
    state.kind = 'mapping';
    state.result = result;
  }
  return detected;
}

function composeNode(state, parentIndent, nodeContext, allowToSeek, allowCompact) {
  let indentStatus = 1;
  let atNewLine = false;
  let hasContent = false;
  state.tag = null;
  state.kind = null;
  state.result = null;
  const allowBlockStyles = nodeContext === CONTEXT_BLOCK_OUT || nodeContext === CONTEXT_BLOCK_IN;
  const allowBlockScalars = allowBlockStyles;
  let allowBlockCollections = allowBlockStyles;
  if (allowToSeek && skipSeparationSpace(state, true)) {
    atNewLine = true;
    if (state.lineIndent > parentIndent) indentStatus = 1;
    else if (state.lineIndent === parentIndent) indentStatus = 0;
    else indentStatus = -1;
  }
  if (indentStatus === 1) {
    const ch = state.input.charCodeAt(state.position);
    if (ch === 0x21 || ch === 0x26) unreadable('a tag or an anchor');
  }
  if (allowBlockCollections) allowBlockCollections = atNewLine || allowCompact;
  if (indentStatus === 1 || nodeContext === CONTEXT_BLOCK_OUT) {
    const flowIndent = nodeContext === CONTEXT_FLOW_IN || nodeContext === CONTEXT_FLOW_OUT ? parentIndent : parentIndent + 1;
    const blockIndent = state.position - state.lineStart;
    if (indentStatus === 1) {
      if (
        (allowBlockCollections && (readBlockSequence(state, blockIndent) || readBlockMapping(state, blockIndent, flowIndent))) ||
        readFlowCollection(state, flowIndent)
      ) {
        hasContent = true;
      } else if (
        (allowBlockScalars && readBlockScalar(state, flowIndent)) ||
        readSingleQuotedScalar(state) ||
        readDoubleQuotedScalar(state)
      ) {
        hasContent = true;
      } else if (state.input.charCodeAt(state.position) === 0x2a) {
        unreadable('an alias');
      } else if (readPlainScalar(state, flowIndent, nodeContext === CONTEXT_FLOW_IN)) {
        hasContent = true;
        if (state.tag === null) state.tag = '?';
      }
    } else if (indentStatus === 0) {
      hasContent = allowBlockCollections && readBlockSequence(state, blockIndent);
    }
  }
  if (state.tag === '?') {
    for (const type of IMPLICIT) {
      if (type.resolve(state.result)) {
        state.result = type.construct(state.result);
        state.tag = type.tag;
        break;
      }
    }
  }
  return state.tag !== null || hasContent;
}

function readDocument(state) {
  skipSeparationSpace(state, true);
  if (state.lineIndent === 0 && state.input.charCodeAt(state.position) === 0x25) unreadable('a YAML directive');
  if (
    state.lineIndent === 0 &&
    state.input.charCodeAt(state.position) === 0x2d &&
    state.input.charCodeAt(state.position + 1) === 0x2d &&
    state.input.charCodeAt(state.position + 2) === 0x2d
  ) {
    state.position += 3;
    skipSeparationSpace(state, true);
  }
  composeNode(state, state.lineIndent - 1, CONTEXT_BLOCK_OUT, false, true);
  skipSeparationSpace(state, true);
  state.documents.push(state.result);
  if (state.position === state.lineStart && testDocumentSeparator(state)) {
    if (state.input.charCodeAt(state.position) === 0x2e) {
      state.position += 3;
      skipSeparationSpace(state, true);
    }
    return;
  }
  if (state.position < state.length - 1) unreadable('more after the end of the document');
}

/** js-yaml 3.14.2's safeLoad, for the subset above: the one document's value. */
export function loadYaml(source) {
  let input = String(source);
  if (input.length !== 0) {
    const last = input.charCodeAt(input.length - 1);
    if (last !== 0x0a && last !== 0x0d) input += '\n';
    if (input.charCodeAt(0) === 0xfeff) input = input.slice(1);
  }
  if (input.indexOf('\0') !== -1) unreadable('a null byte');
  const state = {
    input: `${input}\0`,
    length: input.length,
    position: 0,
    line: 0,
    lineStart: 0,
    lineIndent: 0,
    documents: [],
    tag: null,
    kind: null,
    result: null,
  };
  while (state.input.charCodeAt(state.position) === 0x20) {
    state.lineIndent += 1;
    state.position += 1;
  }
  while (state.position < state.length - 1) {
    readDocument(state);
    if (state.documents.length > 1) unreadable('more than one YAML document');
  }
  return state.documents.length === 0 ? undefined : state.documents[0];
}

// ── the workbench's line-based reading (verbatim) ────────────────────────────

/** A top-level frontmatter key's value (quotes and a trailing comment stripped) and its 1-based line,
 *  or null when there is no `---` frontmatter or no such key. */
export function readFrontmatterKey(text, key) {
  const lines = text.split(/\r?\n/);
  if (lines[0]?.trim() !== '---') return null;
  const re = new RegExp(`^${key}[ \\t]*:[ \\t]*(.*?)[ \\t]*(?:#.*)?$`);
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') return null;
    const m = re.exec(lines[i]);
    if (m) return { value: m[1].replace(/^(["'])(.*)\1$/, '$2').trim(), line: i + 1 };
  }
  return null;
}

/** The frontmatter `visibility` value and its line, or null. */
export const readMark = (text) => readFrontmatterKey(text, 'visibility');

/**
 * Both of the workbench's readings of a file's `visibility` (D-129): `line` as the line-based guards
 * read it, `yaml` as ingest reads it (String() of the value, as the workbench's validator compares them);
 * each undefined when absent. `yaml` is null when the frontmatter is outside this reader.
 */
export function markReadings(text) {
  const line = readMark(text)?.value;
  let yaml;
  try {
    const v = readFrontmatter(text).data?.visibility;
    yaml = v === undefined ? undefined : String(v);
  } catch (err) {
    if (!(err instanceof Unreadable)) throw err;
    yaml = null;
  }
  return { line, yaml };
}
