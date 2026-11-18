#!/usr/bin/env python3
"""flow_svg.py: ops-workflow-design's flow kit (SKB-144). One flow text, drawn on a page.

The flow text is a Zynkr Atlas workflow body, unchanged. Its frontmatter holds `steps:` lines,
`"<id> | <kind> | <title>[ | ref=<slug> | by=internal|external | col=N]"`, grouped under
`"## <phase>"` lines, and `flow:` lines, `"a -> b[ | label]"` for the main path (the spine) and
`"a ~> b[ | label]"` for reads and writes (plumbing). This file:

  - parses it exactly as Atlas does (zynkr-atlas src/lib/steps.ts and declarations.ts): the same
    twelve kinds, the same caps (200 steps, 300 lines, titles of 60, phase names of 40), the same
    drops and the same warnings;
  - lays it out exactly as Atlas's canvas does: longest-path columns with the back edges set aside,
    companions (a store, artifact or knowledge step a `~>` line points at) under the step that
    uses them, `col=` honoured, then one step per row and column, nudged right on a collision;
  - draws it as ONE self-contained SVG: lanes FE · BE · DB, each step in its kind's shape and fill,
    lines routed orthogonally around the boxes, every colour inline from references/flow-colours.json,
    the root stamped data-flow-colours="<registry version>", and the same input gives the same bytes;
  - lints it: V4, V5, V6, V9, V12 (label length), V14 (after layout), overlapping boxes, labels or
    phase bands, and anything Atlas would drop or cut (`parse`), with validation.md's severities.

It also draws three page-only kinds Atlas has no kind for yet: `context` (encoding row 4),
`junction` (row 13) and `ephemeral` (row 15). Atlas would drop those steps, so lint warns, and a
flow that uses one stays a page drawing.

  python3 flow_svg.py render <flow.md> [--registry P] [--out F.svg] [--lang en|zh-TW] [--register audit|clean]
  python3 flow_svg.py lint <flow.md> [--json] [--registry P]
  python3 flow_svg.py --selftest

  dev only, beside the workbench's scripts/flow-golden.ts:
  python3 flow_svg.py compare <flow.md>... --goldens <dir>

render writes the SVG to --out, or to stdout. lint prints validation.md's report (or --json) and
exits 1 when any rule is broken; warnings never change the exit. Exit 2 means it could not run.
Python 3.9, standard library only: a Mac's /usr/bin/python3 runs it with nothing to install.
"""

import heapq
import html
import json
import math
import os
import re
import sys
import traceback
from bisect import bisect_left, bisect_right

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REGISTRY = os.path.normpath(os.path.join(HERE, '..', 'references', 'flow-colours.json'))
FIXTURES = os.path.join(HERE, 'fixtures')


class KitError(Exception):
    """The kit could not run: a missing file or a bad registry. Exit 2, never a pass."""


# ----------------------------------------------------------------------------------------------
# JavaScript string semantics. Atlas's parser is TypeScript, so trimming, `\s` and slicing follow
# JavaScript's rules here, not Python's: the whitespace set differs (JS trims U+FEFF, Python does
# not; Python strips U+001C-U+001F and U+0085, JS does not) and `slice` counts UTF-16 code units.

JS_WS = ('\t\n\x0b\x0c\r \xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009'
         '\u200a\u2028\u2029\u202f\u205f\u3000\ufeff')
_WS = ''.join('\\u%04x' % ord(c) for c in JS_WS)
S = '[' + _WS + ']'            # JS \s
NS = '[^' + _WS + ']'          # JS \S
DOT = '[^\\n\\r\\u2028\\u2029]'  # JS . (no s flag)


def js_trim(s):
    return s.strip(JS_WS)


def js_trim_start(s):
    return s.lstrip(JS_WS)


def js_len(s):
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def js_slice(s, n):
    """`s.slice(0, n)`: the first n UTF-16 code units. A cut through a pair keeps its high half."""
    if n <= 0:
        return ''
    out, units = [], 0
    for ch in s:
        u = 2 if ord(ch) > 0xFFFF else 1
        if units + u > n:
            if u == 2 and units + 1 == n:
                out.append(chr(0xD800 + ((ord(ch) - 0x10000) >> 10)))
            break
        out.append(ch)
        units += u
        if units == n:
            break
    return ''.join(out)


# ----------------------------------------------------------------------------------------------
# Frontmatter: Atlas's YAML subset (declarations.ts parseFrontmatter / splitFrontmatter).

ITEM_RE = re.compile('^' + S + '+-' + S + '+(' + DOT + '*)\\Z')
KEY_RE = re.compile('^([A-Za-z_][A-Za-z0-9_-]*):(?:' + S + '+(' + DOT + '*))?\\Z')
BLOCK_SCALAR_RE = re.compile('^([|>])([-+]?)([0-9]*)\\Z')
COMMENT_RE = re.compile(S + '+#' + DOT + '*\\Z')


def normalise_newlines(md):
    return re.sub('\r\n?', '\n', md)


def split_frontmatter(md):
    text = md[1:] if md.startswith('\ufeff') else md
    lines = text.split('\n')
    if js_trim(lines[0]) != '---':
        return None, text, {'code': 'no_frontmatter', 'field': '', 'detail': ''}
    for i in range(1, len(lines)):
        t = js_trim(lines[i])
        if t == '---' or t == '...':
            return '\n'.join(lines[1:i]), '\n'.join(lines[i + 1:]), None
    return None, text, {'code': 'unterminated_frontmatter', 'field': '', 'detail': ''}


def unquote(raw):
    s = js_trim(raw)
    if js_len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1].replace('\\"', '"').replace('\\\\', '\\'), None
    if js_len(s) >= 2 and s.startswith("'") and s.endswith("'"):
        return s[1:-1].replace("''", "'"), None
    if len(s) >= 1 and (s.startswith('"') or s.startswith("'")):
        return s, 'unterminated_quote'
    return js_trim(COMMENT_RE.sub('', s, count=1)), None


def split_flow_seq(inner):
    out, cur, quote = [], '', None
    for ch in inner:
        if quote:
            if ch == quote:
                quote = None
            else:
                cur += ch
            continue
        if ch == '"' or ch == "'":
            quote = ch
            continue
        if ch == ',':
            out.append(cur)
            cur = ''
            continue
        cur += ch
    out.append(cur)
    return [t for t in (js_trim(x) for x in out) if t]


def indent_of(line):
    return len(line) - len(js_trim_start(line))


def read_block_scalar(lines, start, key_indent, style, chomp):
    collected = []
    i = start
    while i < len(lines):
        line = lines[i]
        if js_trim(line) == '':
            collected.append('')
            i += 1
            continue
        if indent_of(line) <= key_indent:
            break
        collected.append(line)
        i += 1
    while collected and collected[-1] == '':
        collected.pop()
    if not collected:
        return '', i
    content = min(indent_of(x) for x in collected if js_trim(x))
    dedented = ['' if js_trim(x) == '' else x[content:] for x in collected]
    if style == '|':
        value = '\n'.join(dedented)
    else:
        value, buf, blanks = '', [], 0
        for x in dedented:
            if x == '':
                if buf:
                    value += ' '.join(buf)
                    buf = []
                blanks += 1
                continue
            if blanks:
                value += '\n' * blanks
                blanks = 0
            buf.append(x)
        if buf:
            value += ' '.join(buf)
    if chomp == '+':
        value += '\n'
    return value, i


def parse_frontmatter(block):
    fm, warnings, current = {}, [], None
    lines = block.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        t = js_trim(line)
        if not t or t.startswith('#'):
            i += 1
            continue
        item = ITEM_RE.match(line)
        if item and current is not None:
            value, warning = unquote(item.group(1))
            if warning:
                warnings.append({'code': warning, 'field': current, 'detail': js_trim(item.group(1))})
            if isinstance(fm.get(current), list):
                fm[current].append(value)
            else:
                fm[current] = [value]
            i += 1
            continue
        kv = KEY_RE.match(line)
        if not kv:
            warnings.append({'code': 'unparsed_line', 'field': current if current is not None else '',
                             'detail': js_slice(js_trim(line), 120)})
            i += 1
            continue
        key = kv.group(1)
        rest = js_trim(kv.group(2) or '')
        current = key
        bs = BLOCK_SCALAR_RE.match(rest)
        if bs:
            fm[key], i = read_block_scalar(lines, i + 1, indent_of(line), bs.group(1), bs.group(2))
            continue
        i += 1
        if rest == '':
            fm[key] = []
            continue
        if rest.startswith('['):
            if not rest.endswith(']'):
                warnings.append({'code': 'unparsed_line', 'field': key, 'detail': js_slice(rest, 120)})
                fm[key] = []
                continue
            fm[key] = split_flow_seq(rest[1:-1])
            continue
        value, warning = unquote(rest)
        if warning:
            warnings.append({'code': warning, 'field': key, 'detail': js_slice(rest, 120)})
        fm[key] = value
    return fm, warnings


def read_frontmatter(text):
    """parseArtifact's first half: newlines, the --- block, the YAML subset. (fm, warnings, body)."""
    md = normalise_newlines(text)
    block, body, warning = split_frontmatter(md)
    warnings = [warning] if warning else []
    fm = {}
    if block is not None:
        fm, more = parse_frontmatter(block)
        warnings.extend(more)
    return fm, warnings, body


# ----------------------------------------------------------------------------------------------
# The step block (steps.ts parseStepBlock), with the page-only kinds when page=True.

ATLAS_KINDS = ('start', 'end', 'input', 'output', 'hitl', 'llm', 'deterministic',
               'gate', 'store', 'artifact', 'knowledge', 'offpage')
PAGE_ONLY_KINDS = ('context', 'junction', 'ephemeral')
MODES = ('llm', 'deterministic', 'hitl')
MAX_STEPS, MAX_FLOW, MAX_TITLE, MAX_PHASE_NAME = 200, 300, 60, 40
STEP_ID_RE = re.compile('[a-z][a-z0-9_]{0,31}\\Z')
PHASE_RE = re.compile('##' + S + '*(' + NS + DOT + '*)\\Z')
FLOW_RE = re.compile('(' + NS + '+)' + S + '*(->|~>)' + S + '*(' + NS + '+)\\Z')
COL_RE = re.compile('[0-9]{1,3}\\Z')
OMISSION_CODES = ('too_many_steps', 'step_malformed', 'step_id_invalid', 'step_id_duplicate',
                  'step_kind_unknown', 'step_ref_duplicate', 'flow_malformed', 'flow_unknown_step')


def empty_block():
    return {'steps': [], 'phases': [], 'flow': [], 'feSublane': 0, 'executionMode': None, 'warnings': []}


def as_array(v):
    arr = v if isinstance(v, list) else ([] if v is None else [v])
    return [x for x in arr if isinstance(x, str)]


def parse_step_block(fm, page=False, cuts=None):
    """Atlas cuts a long title or phase name and says nothing. A `cuts` list, when given, collects each
    cut for lint outside the block, so the block stays Atlas's."""
    warnings = []

    def warn(code, field, detail):
        warnings.append({'code': code, 'field': field, 'detail': detail})

    raw_steps, raw_flow = as_array(fm.get('steps')), as_array(fm.get('flow'))
    if not raw_steps and not raw_flow:
        return empty_block()
    eb = js_trim(fm['executed_by']) if isinstance(fm.get('executed_by'), str) else ''
    if eb and eb != 'external-user' and eb != 'internal-user':
        warn('override_unknown', 'executed_by', eb)
    fe_sublane = 1 if eb == 'internal-user' else 0
    em = js_trim(fm['execution_mode']) if isinstance(fm.get('execution_mode'), str) else ''
    if em and em not in MODES:
        warn('override_unknown', 'execution_mode', em)
    mode = em if em in MODES else None

    def is_header(raw):
        return PHASE_RE.match(js_trim(raw)) is not None

    step_lines = len([r for r in raw_steps if not is_header(r)])
    if step_lines > MAX_STEPS:
        warn('too_many_steps', 'steps', '%d > %d' % (step_lines, MAX_STEPS))
    if len(raw_flow) > MAX_FLOW:
        warn('too_many_steps', 'flow', '%d > %d' % (len(raw_flow), MAX_FLOW))
    budget, capped = MAX_STEPS, []
    for raw in raw_steps:
        if not is_header(raw):
            if budget == 0:
                break
            budget -= 1
        capped.append(raw)

    kinds = ATLAS_KINDS + PAGE_ONLY_KINDS if page else ATLAS_KINDS
    steps, phases, phase, ordinal, seen, bound = [], [], None, 0, set(), {}
    for i, raw in enumerate(capped):
        line = i + 1
        head = PHASE_RE.match(js_trim(raw))
        if head:
            whole = js_trim(head.group(1))
            if cuts is not None and js_len(whole) > MAX_PHASE_NAME:
                cuts.append({'what': 'phase', 'id': None, 'length': js_len(whole),
                             'kept': js_slice(whole, MAX_PHASE_NAME)})
            phases.append({'name': js_slice(whole, MAX_PHASE_NAME), 'from': ordinal + 1, 'to': ordinal})
            phase = len(phases) - 1
            continue
        parts = [js_trim(p) for p in raw.split('|')]
        if len(parts) < 3:
            warn('step_malformed', 'steps', js_slice(raw, 120))
            continue
        sid, kind, title, opts = parts[0], parts[1], parts[2], parts[3:]
        if not STEP_ID_RE.match(sid):
            warn('step_id_invalid', 'steps', js_slice(sid, 120))
            continue
        if sid in seen:
            warn('step_id_duplicate', 'steps', sid)
            continue
        if kind not in kinds:
            warn('step_kind_unknown', 'steps', '%s: %s' % (sid, kind))
            continue
        if not title:
            warn('step_malformed', 'steps', '%s: no title' % sid)
            continue
        ref = by = col = None
        for opt in opts:
            eq = opt.find('=')
            if eq < 1:
                warn('step_opt_malformed', 'steps', '%s: %s' % (sid, js_slice(opt, 60)))
                continue
            k, v = js_trim(opt[:eq]), js_trim(opt[eq + 1:])
            if k == 'ref':
                ref = v or None
            elif k == 'by':
                if v == 'internal':
                    by = 1
                elif v == 'external':
                    by = 0
                else:
                    warn('step_opt_malformed', 'steps', '%s: by=%s' % (sid, v))
                    by = None
            elif k == 'col':
                n = int(v) if COL_RE.match(v) else None
                if n is not None and 0 <= n <= MAX_STEPS:
                    col = n
                else:
                    warn('step_opt_malformed', 'steps', '%s: col=%s' % (sid, v))
                    col = None
            else:
                warn('step_opt_unknown', 'steps', '%s: %s' % (sid, k))
        bare = (ref[6:] if ref.startswith('atlas:') else ref) if ref else None
        if bare:
            if bare in bound:
                warn('step_ref_duplicate', 'steps', '%s: %s (%s)' % (sid, ref, bound[bare]))
                continue
            bound[bare] = sid
        seen.add(sid)
        ordinal += 1
        if phase is not None:
            phases[phase]['to'] = ordinal
        if cuts is not None and js_len(title) > MAX_TITLE:
            cuts.append({'what': 'step', 'id': sid, 'length': js_len(title), 'kept': js_slice(title, MAX_TITLE)})
        steps.append({'id': sid, 'kind': kind, 'title': js_slice(title, MAX_TITLE), 'ref': ref, 'by': by,
                      'col': col, 'raw': js_trim(raw), 'line': line, 'phase': phase, 'ordinal': ordinal})

    gates = set(s['id'] for s in steps if s['kind'] == 'gate')
    flow = []
    for raw in raw_flow[:MAX_FLOW]:
        parts = [js_trim(p) for p in raw.split('|')]
        m = FLOW_RE.match(parts[0])
        if not m:
            warn('flow_malformed', 'flow', js_slice(raw, 120))
            continue
        a, arrow, b = m.group(1), m.group(2), m.group(3)
        if a not in seen:
            warn('flow_unknown_step', 'flow', a)
            continue
        if b not in seen:
            warn('flow_unknown_step', 'flow', b)
            continue
        label = js_trim('|'.join(parts[1:])) or None
        if arrow == '->' and a in gates and not label:
            warn('gate_branch_unlabeled', 'flow', js_slice(raw, 120))
        flow.append({'from': a, 'to': b, 'role': 'spine' if arrow == '->' else 'plumbing', 'label': label})
    return {'steps': steps, 'phases': [p for p in phases if p['to'] >= p['from']], 'flow': flow,
            'feSublane': fe_sublane, 'executionMode': mode, 'warnings': warnings}


# ----------------------------------------------------------------------------------------------
# Layout: steps.ts composePicture's columns, frame.ts frameStep, frameGeometry.ts conventionLayout.

# kind -> (lane, fixed sub-row or None, shape). None: the sub-row is `by=`, else the file's executed_by.
STEP_FRAMING = {
    'start': ('fe', None, 'terminal'), 'end': ('fe', None, 'terminal'),
    'input': ('fe', None, 'manualIO'), 'output': ('fe', None, 'manualIO'),
    'hitl': ('be', 0, 'manualOp'), 'llm': ('be', 1, 'process'),
    'deterministic': ('be', 1, 'process'), 'gate': ('be', 1, 'decision'),
    'store': ('db', 0, 'database'), 'artifact': ('db', 0, 'document'),
    'knowledge': ('db', 1, 'document'), 'offpage': ('be', 1, 'offpage'),
    # page-only (encoding rows 4, 13, 15)
    'context': ('fe', None, 'document'), 'junction': ('be', 1, 'junction'),
    'ephemeral': ('db', 0, 'document'),
}
ROW_ORDER = (('fe', 0), ('fe', 1), ('be', 0), ('be', 1), ('db', 0), ('db', 1))
COMPANIONS = ('store', 'artifact', 'knowledge')
PAGE_COMPANIONS = COMPANIONS + ('context', 'ephemeral')


def frame_step(kind, fe_sublane, by):
    lane, sub, shape = STEP_FRAMING.get(kind, STEP_FRAMING['llm'])
    if sub is None:
        sub = by if by is not None else fe_sublane
    return lane, sub, shape


def back_edges_of(spine, order):
    """Indices into `spine` of the edges that return to a step already on the walk (steps.ts)."""
    out, outgoing = set(), {}
    for idx, f in enumerate(spine):
        outgoing.setdefault(f['from'], []).append(idx)
    colour = dict((sid, 0) for sid in order)
    for root in order:
        if colour.get(root) != 0:
            continue
        colour[root] = 1
        stack = [[root, 0]]
        while stack:
            top = stack[-1]
            edges = outgoing.get(top[0], [])
            if top[1] >= len(edges):
                colour[top[0]] = 2
                stack.pop()
                continue
            idx = edges[top[1]]
            top[1] += 1
            c = colour.get(spine[idx]['to'], 0)
            if c == 1:
                out.add(idx)
            elif c == 0:
                colour[spine[idx]['to']] = 1
                stack.append([spine[idx]['to'], 0])
    return out


def layout(block, page=False):
    steps, flow = block['steps'], block['flow']
    by_id = dict((s['id'], s) for s in steps)
    ids = [s['id'] for s in steps]
    spine = [f for f in flow if f['role'] == 'spine' and f['from'] in by_id and f['to'] in by_id]
    back = back_edges_of(spine, ids)
    forward = [f for i, f in enumerate(spine) if i not in back]
    col = dict((sid, 0) for sid in ids)
    for _ in range(len(ids)):
        moved = False
        for f in forward:
            nxt = col.get(f['from'], 0) + 1
            if nxt > col.get(f['to'], 0):
                col[f['to']] = nxt
                moved = True
        if not moved:
            break
    companions = PAGE_COMPANIONS if page else COMPANIONS
    for f in flow:
        if f['role'] != 'plumbing' or f['from'] not in by_id or f['to'] not in by_id:
            continue
        if by_id[f['to']]['kind'] in companions:
            col[f['to']] = max(col.get(f['to'], 0), col.get(f['from'], 0))
    tier, lane, sub, shape = {}, {}, {}, {}
    for s in steps:
        tier[s['id']] = s['col'] if s['col'] is not None else col.get(s['id'], 0)
        lane[s['id']], sub[s['id']], shape[s['id']] = frame_step(s['kind'], block['feSublane'], s['by'])
    present = [(lane[i], sub[i]) for i in ids]
    rows = [rk for rk in ROW_ORDER if rk in present]
    taken, final = {}, {}
    for i in ids:
        used = taken.setdefault((lane[i], sub[i]), set())
        c = max(0, int(tier[i]))
        while c in used:
            c += 1
        used.add(c)
        final[i] = c
    cols = max([0] + list(final.values())) + 1
    return {'ids': ids, 'tier': tier, 'lane': lane, 'sub': sub, 'shape': shape, 'col': final,
            'rows': rows, 'cols': cols, 'back': [spine[i] for i in sorted(back)]}


def atlas_view(text):
    """What Atlas keeps and where its canvas puts it, in the shape of the golden files."""
    fm, fm_warnings, _ = read_frontmatter(text)
    block = parse_step_block(fm, page=False)
    lay = layout(block, page=False)
    columns = {'rows': [ln + str(sb) for ln, sb in lay['rows']], 'cols': lay['cols'],
               'steps': [{'id': i, 'lane': lay['lane'][i], 'sublane': lay['sub'][i], 'tier': lay['tier'][i],
                          'col': lay['col'][i]} for i in lay['ids']]}
    return {'frontmatterWarnings': fm_warnings, 'block': block}, columns


# ----------------------------------------------------------------------------------------------
# The colour registry.

COLOUR_RE = re.compile('#[0-9A-Fa-f]{6}\\Z')
VERSION_RE = re.compile('[0-9]{4}-[0-9]{2}-[0-9]{2}\\.[0-9]+\\Z')
SHAPES = ('terminal', 'manualIO', 'manualOp', 'process', 'decision', 'database', 'document', 'offpage', 'junction')


def registry_problems(reg):
    out = []
    if not isinstance(reg, dict):
        return ['the registry is not a JSON object']
    if not isinstance(reg.get('version'), str) or not VERSION_RE.match(reg['version']):
        out.append('version must read YYYY-MM-DD.N')

    def walk(v, where):
        if isinstance(v, dict):
            for k in v:
                walk(v[k], where + '.' + k)
        elif isinstance(v, list):
            for n, x in enumerate(v):
                walk(x, '%s[%d]' % (where, n))
        elif isinstance(v, str) and v.startswith('#') and not COLOUR_RE.match(v):
            out.append('%s: %r is not a #RRGGBB colour' % (where, v))
    walk(reg, 'registry')

    def colour(v, where):
        if not isinstance(v, str) or not COLOUR_RE.match(v):
            out.append('%s: missing or not a #RRGGBB colour' % where)

    seen = {}
    for n, r in enumerate(reg.get('roles') or []):
        where = 'roles[%d]' % n
        for k in r.get('kinds') or []:
            if k in seen:
                out.append('%s: kind %s already has a role' % (where, k))
            seen[k] = r
            want = STEP_FRAMING.get(k)
            if want is None:
                out.append('%s: unknown kind %s' % (where, k))
            elif r.get('shape') != want[2]:
                out.append('%s: kind %s is drawn as %s, not %s' % (where, k, want[2], r.get('shape')))
        if r.get('shape') not in SHAPES:
            out.append('%s: shape %r is not one the kit draws' % (where, r.get('shape')))
        colour(r.get('fill'), where + '.fill')
        colour(r.get('stroke'), where + '.stroke')
        if not isinstance(r.get('label'), dict) or not r['label'].get('en') or not r['label'].get('zh-TW'):
            out.append('%s: needs a label in en and zh-TW' % where)
    for k in ATLAS_KINDS + PAGE_ONLY_KINDS:
        if k not in seen:
            out.append('no role draws kind %s' % k)
    edges = reg.get('edges') or {}
    for e in ('spine', 'plumbing'):
        colour((edges.get(e) or {}).get('stroke'), 'edges.%s.stroke' % e)
        if not isinstance((edges.get(e) or {}).get('width'), (int, float)):
            out.append('edges.%s.width must be a number' % e)
    lanes = reg.get('lanes') or {}
    for path in (('header', 'fill'), ('header', 'text'), ('subheader', 'fill'), ('subheader', 'text'),
                 ('fill', 'fe'), ('fill', 'be'), ('fill', 'db')):
        colour((lanes.get(path[0]) or {}).get(path[1]), 'lanes.' + '.'.join(path))
    colour(lanes.get('separator'), 'lanes.separator')
    colour(lanes.get('frame'), 'lanes.frame')
    for lang in ('en', 'zh-TW'):
        for lane in ('fe', 'be', 'db'):
            if not ((lanes.get('titles') or {}).get(lang) or {}).get(lane):
                out.append('lanes.titles.%s.%s is missing' % (lang, lane))
            rows = ((lanes.get('rows') or {}).get(lang) or {}).get(lane)
            if not isinstance(rows, list) or len(rows) != 2:
                out.append('lanes.rows.%s.%s needs two titles' % (lang, lane))
    for k in ('primary', 'secondary', 'muted'):
        colour((reg.get('text') or {}).get(k), 'text.' + k)
    page = reg.get('page') or {}
    colour(page.get('background'), 'page.background')
    colour((page.get('panel') or {}).get('fill'), 'page.panel.fill')
    colour((page.get('panel') or {}).get('stroke'), 'page.panel.stroke')
    for k in ('fill', 'stroke', 'text'):
        colour((page.get('phase') or {}).get(k), 'page.phase.' + k)
    colour((page.get('badge') or {}).get('fill'), 'page.badge.fill')
    colour(page.get('labelHalo'), 'page.labelHalo')
    avoid = reg.get('avoid')
    if not isinstance(avoid, list) or not avoid:
        out.append('avoid must list the colours a drawing never uses')
    else:
        used = set()

        def gather(v):
            if isinstance(v, dict):
                for k in v:
                    if k != 'avoid':
                        gather(v[k])
            elif isinstance(v, list):
                for x in v:
                    gather(x)
            elif isinstance(v, str) and COLOUR_RE.match(v):
                used.add(v.upper())
        gather(dict((k, v) for k, v in reg.items() if k != 'avoid'))
        for a in avoid:
            if isinstance(a, str) and a.upper() in used:
                out.append('%s is on the avoid list but the registry paints it' % a)
    return out


def load_registry(path=None):
    path = path or DEFAULT_REGISTRY
    try:
        with open(path, encoding='utf-8') as fh:
            reg = json.load(fh)
    except (OSError, ValueError) as e:
        raise KitError('cannot read the colour registry %s: %s' % (path, e))
    problems = registry_problems(reg)
    if problems:
        raise KitError('the colour registry %s is not usable:\n  ' % path + '\n  '.join(problems))
    reg['_role'] = {}
    for r in reg['roles']:
        for k in r['kinds']:
            reg['_role'][k] = r
    return reg


# ----------------------------------------------------------------------------------------------
# Text: a rough width (CJK and full-width count as one em), and a balanced greedy wrap.

FONT = "Inter, 'Noto Sans TC', 'PingFang TC', 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', Menlo, Consolas, monospace"


def tw(s, size):
    return sum(size if ord(c) > 0x2E7F else size * .6 for c in s)


def is_word(c):
    """A letter or digit of a spaced script: breaking between two of these cuts a word in half."""
    return c.isalnum() and ord(c) <= 0x2E7F


def _wrap(s, size, room):
    """Greedy wrap: break at the last space (or CJK comma) when it lies past a quarter of the line,
    else between two characters. Returns (lines, cuts): cuts counts the words cut in half."""
    lines, cur, cuts = [], '', 0
    for ch in s:
        if cur and tw(cur + ch, size) > room:
            k = max(cur.rfind(' '), cur.rfind('，') + 1 if '，' in cur else -1,
                    cur.rfind('、') + 1 if '、' in cur else -1)
            if k > len(cur) * .25:
                lines.append(cur[:k])
                cur = cur[k:].lstrip() + ch
            else:
                if is_word(cur[-1]) and is_word(ch):
                    cuts += 1
                lines.append(cur)
                cur = ch
        else:
            cur += ch
    if cur.strip():
        lines.append(cur)
    out = []
    for i, x in enumerate(lines):
        x = x.strip()
        if i:
            x = x.lstrip('·').strip()
        if i < len(lines) - 1:
            x = x.rstrip('·').strip()
        if x:
            out.append(x)
    return out, cuts


def wrap(s, size, room):
    """Greedy wrap by measured width, then narrowed while the line count holds and no more words
    are cut, so the lines balance without breaking a word that fitted whole."""
    best, cuts = _wrap(s, size, room)
    if len(best) > 1:
        r = room - 4
        while r > room * .5:
            t, c = _wrap(s, size, r)
            if len(t) != len(best) or c > cuts:
                break
            best = t
            r -= 4
    return best or ['']


def esc(s):
    s = ''.join('\ufffd' if 0xD800 <= ord(c) <= 0xDFFF else c for c in s)
    return html.escape(s, quote=True)


def f(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')


# ----------------------------------------------------------------------------------------------
# The router: orthogonal A* over a sparse grid, from the bootcamp lanes kit (lanes_svg_1118.py).
# x = gutter tracks + port stubs, y = an 8px track grid + port stubs. Obstacles are padded boxes.
# A route pays for length, bends, crossings, touching another route's corner, and (heavily) for
# sharing a segment.

CLEAR, TRACK, RC = 10, 8, 6
BEND, CROSS, TOUCH, OVERLAP = 34, 46, 420, 6000
NEAR = .8
VEC = {0: (1, 0), 1: (-1, 0), 2: (0, 1), 3: (0, -1)}
OPP = {0: 1, 1: 0, 2: 3, 3: 2}
SIDE_DIR = {'L': 1, 'R': 0, 'T': 3, 'B': 2}


class Router(object):
    def __init__(self, xs, ys, obst, box):
        x0, y0, x1, y1 = box
        self.X = X = sorted(set(round(v * 2) / 2 for v in xs if x0 <= v <= x1))
        self.Y = Y = sorted(set(round(v * 2) / 2 for v in ys if y0 <= v <= y1))
        nX, nY = len(X), len(Y)
        self.pt = [[True] * nY for _ in range(nX)]
        self.hs = [[True] * nY for _ in range(max(nX - 1, 0))]
        self.vs = [[True] * max(nY - 1, 0) for _ in range(nX)]
        for (a, b, c, d) in obst:
            i0, i1 = bisect_right(X, a), bisect_left(X, c)
            j0, j1 = bisect_right(Y, b), bisect_left(Y, d)
            for i in range(i0, i1):
                column = self.pt[i]
                for j in range(j0, j1):
                    column[j] = False
            sa, sb = max(i0 - 1, 0), min(i1, nX - 1)
            for j in range(j0, j1):
                for i in range(sa, sb):
                    self.hs[i][j] = False
            ta, tb = max(j0 - 1, 0), min(j1, nY - 1)
            for i in range(i0, i1):
                column = self.vs[i]
                for j in range(ta, tb):
                    column[j] = False
        self.seg = {}
        self.use = {}

    def ij(self, p):
        X, Y = self.X, self.Y
        x, y = round(p[0] * 2) / 2, round(p[1] * 2) / 2
        i, j = bisect_left(X, x), bisect_left(Y, y)
        if i < len(X) and X[i] == x and j < len(Y) and Y[j] == y and self.pt[i][j]:
            return (i, j)
        return None

    def step_cost(self, i, j, d, ni, nj):
        X, Y = self.X, self.Y
        c = abs(X[ni] - X[i]) + abs(Y[nj] - Y[j])
        key = ('h', min(i, ni), j) if d < 2 else ('v', i, min(j, nj))
        if key in self.seg:
            c += OVERLAP
        if d < 2:
            for st in (-1, 1):
                jj = j + st
                while 0 <= jj < len(Y) and abs(Y[jj] - Y[j]) <= TRACK + 1:
                    if ('h', min(i, ni), jj) in self.seg:
                        c += NEAR * abs(X[ni] - X[i])
                        break
                    jj += st
        else:
            for st in (-1, 1):
                ii = i + st
                while 0 <= ii < len(X) and abs(X[ii] - X[i]) <= TRACK + 1:
                    if ('v', ii, min(j, nj)) in self.seg:
                        c += NEAR * abs(Y[nj] - Y[j])
                        break
                    ii += st
        u = self.use.get((ni, nj))
        if u:
            if d < 2:
                if u.get('v'):
                    c += CROSS
                if u.get('h'):
                    c += OVERLAP
            else:
                if u.get('h'):
                    c += CROSS
                if u.get('v'):
                    c += OVERLAP
            if u.get('c'):
                c += TOUCH
        return c

    def search(self, starts, goals, xlim=None):
        """starts: [(i, j, dir_out, cost, tag)]; goals: {(i, j): [(dir_in, cost, tag)]}. Returns
        (path [(i, j)...], start tag, goal tag) or None. xlim bounds the columns a route may use."""
        X, Y = self.X, self.Y
        gl = [(X[i], Y[j]) for (i, j) in goals]

        def hfun(i, j):
            return min(abs(X[i] - gx) + abs(Y[j] - gy) for gx, gy in gl)

        openh, best, parent, tick = [], {}, {}, 0
        for (i, j, d, c0, tag) in starts:
            s = (i, j, d)
            if c0 < best.get(s, 1e18):
                best[s] = c0
                parent[s] = ('start', tag)
                tick += 1
                heapq.heappush(openh, (c0 + hfun(i, j), c0, tick, s))
        nX, nY = len(X), len(Y)
        lo, hi = xlim if xlim else (-1e18, 1e18)
        while openh:
            _, g, _, s = heapq.heappop(openh)
            if s[0] == 'done':
                return s[1], s[2], s[3]
            if g > best.get(s, 1e18):
                continue
            i, j, d = s
            if (i, j) in goals:
                path = None
                for (dn, cg, tag) in goals[(i, j)]:
                    if d == OPP[dn]:
                        continue
                    if path is None:
                        path, st = [], s
                        while True:
                            path.append((st[0], st[1]))
                            pr = parent[st]
                            if pr[0] == 'start':
                                stag = pr[1]
                                break
                            st = pr
                        path = path[::-1]
                    tot = g + cg + (BEND if d != dn else 0)
                    tick += 1
                    heapq.heappush(openh, (tot, tot, tick, ('done', path, stag, tag)))
            for nd in (0, 1, 2, 3):
                if nd == OPP[d]:
                    continue
                dx, dy = VEC[nd]
                ni, nj = i + dx, j + dy
                if not (0 <= ni < nX and 0 <= nj < nY) or not self.pt[ni][nj]:
                    continue
                if not (lo <= X[ni] <= hi):
                    continue
                if nd < 2:
                    if not self.hs[min(i, ni)][j]:
                        continue
                elif not self.vs[i][min(j, nj)]:
                    continue
                c = g + self.step_cost(i, j, nd, ni, nj)
                if nd != d:
                    c += BEND
                    if self.use.get((i, j)):
                        c += TOUCH
                ns = (ni, nj, nd)
                if c < best.get(ns, 1e18):
                    best[ns] = c
                    parent[ns] = s
                    tick += 1
                    heapq.heappush(openh, (c + hfun(ni, nj), c, tick, ns))
        return None

    def mark(self, path):
        for a, b in zip(path, path[1:]):
            key = ('h', min(a[0], b[0]), a[1]) if a[1] == b[1] else ('v', a[0], min(a[1], b[1]))
            self.seg[key] = self.seg.get(key, 0) + 1
        for k, p in enumerate(path):
            u = self.use.setdefault(p, {})
            if k in (0, len(path) - 1):
                u['c'] = u.get('c', 0) + 1
                continue
            a, b = path[k - 1], path[k + 1]
            if a[1] == p[1] == b[1]:
                u['h'] = u.get('h', 0) + 1
            elif a[0] == p[0] == b[0]:
                u['v'] = u.get('v', 0) + 1
            else:
                u['c'] = u.get('c', 0) + 1


def simplify(pts):
    out = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < .01 and abs(out[-1][1] - p[1]) < .01:
            continue
        out.append(p)
        while len(out) >= 3:
            (ax, ay), (bx, by), (cx, cy) = out[-3:]
            if (abs(ax - bx) < .01 and abs(bx - cx) < .01) or (abs(ay - by) < .01 and abs(by - cy) < .01):
                del out[-2]
            else:
                break
    return out


def path_d(pts):
    out = ['M%s,%s' % (f(pts[0][0]), f(pts[0][1]))]
    for k in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[k - 1], pts[k], pts[k + 1]
        d1, d2 = math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x1, y2 - y1)
        if d1 < .01 or d2 < .01:
            continue
        r = min(RC, d1 / 2, d2 / 2)
        ax, ay = x1 - (x1 - x0) / d1 * r, y1 - (y1 - y0) / d1 * r
        bx, by = x1 + (x2 - x1) / d2 * r, y1 + (y2 - y1) / d2 * r
        out.append('L%s,%s Q%s,%s %s,%s' % (f(ax), f(ay), f(x1), f(y1), f(bx), f(by)))
    out.append('L%s,%s' % (f(pts[-1][0]), f(pts[-1][1])))
    return ' '.join(out)


# ----------------------------------------------------------------------------------------------
# Geometry.

MARGIN, HEAD_W, NW, COL_W = 20, 158, 176, 268
ROW_PAD, MIN_ROW_H = 26, 100
TITLE_H, PHASE_H, PHASE_GAP = 46, 24, 12
FS_NODE, LH_NODE = 12.5, 16
FS_LABEL, LH_LABEL = 11, 14
FS_BADGE, FS_HEAD, FS_ROW = 10, 11.5, 11
MAX_NODE_LINES, MAX_LABEL_LINES, LABEL_W = 3, 2, 132
SLANT, WAVE, CYL, POINT, TAB = 10, 5, 7, 14, 8
PADS = {'process': (10, 10), 'terminal': (10, 10), 'manualIO': (10 + SLANT, 10), 'manualOp': (10, 10),
        'document': (10, 10 + WAVE * 2), 'database': (2 * CYL + 6, CYL + 6), 'offpage': (10, POINT + 8)}
# A step number at the start of a title: 3 or 1.2 as the step card writes them (process-step-card.md §1),
# or a range such as 2.3–2.6, which Atlas's own flows use for a step that stands for several. No letter
# suffix, so "10x faster" or "24h" keep their first word.
NUM_RE = re.compile('([0-9]{1,2}(?:\\.[0-9]{1,2})*(?:[–-][0-9]{1,2}(?:\\.[0-9]{1,2})*)?)' + S + '+(' + NS + DOT + '*)\\Z')

UI = {
    'en': {'legend': 'Legend', 'how': 'How to read this', 'colours': 'colours',
           'steps': 'steps', 'lines': 'lines', 'audit': 'audit register', 'clean': 'clean register',
           'how_text': 'Read left to right along the solid line: each box is one step, and the number on its tab is '
                       'the step\'s number in the document. The lanes say who does it: a person at the top, the system '
                       'in the middle, data and knowledge at the bottom. A box’s shape and colour say what kind of step '
                       'it is. Dashed grey lines are reads and writes, and the arrow points the way the data moves. '
                       'Only the branches of a decision or a fork carry labels.'},
    'zh-TW': {'legend': '圖例', 'how': '怎麼讀這張圖', 'colours': '配色',
              'steps': '步', 'lines': '條線', 'audit': '稽核版', 'clean': '簡報版',
              'how_text': '沿著實線由左往右讀，每個方塊是一步，方塊上的編號就是文件裡的步驟編號。泳道說明誰做：上面是人，中間是系統，下面是資料和知識。'
                          '方塊的形狀和顏色說明是哪一種步驟。灰色虛線是讀寫資料，箭頭是資料往哪走。只有判斷和分岔的出口有標籤。'},
}


def text_room(shape):
    if shape == 'decision':
        return NW * .56
    if shape in ('terminal', 'manualOp'):
        return NW - 36
    if shape == 'junction':
        return NW - 8
    return NW - 20


def split_number(title):
    m = NUM_RE.match(title)
    return (m.group(1), m.group(2)) if m else (None, title)


def node_height(shape, n):
    n = max(1, n)
    if shape == 'decision':
        return max(72, n * LH_NODE + 44)
    if shape == 'junction':
        return 32 + 6 + n * LH_NODE
    top, bottom = PADS[shape]
    return max(44 if shape == 'terminal' else 50, top + n * LH_NODE + bottom)


def top_at(nd, px):
    """The y of a shape's top edge at x = px."""
    x, y, w = nd['x'], nd['y'], nd['w']
    if nd['shape'] == 'manualIO':
        return y + SLANT * (1 - (px - x) / w)
    if nd['shape'] == 'database':
        dx = px - (x + w / 2)
        return y + CYL - CYL * math.sqrt(max(0, 1 - (dx / (w / 2)) ** 2))
    if nd['shape'] == 'decision':
        cx = x + w / 2
        return y + (nd['h'] / 2) * abs(px - cx) / (w / 2)
    return y


def bottom_at(nd, px):
    x, y, w, h = nd['x'], nd['y'], nd['w'], nd['h']
    cx = x + w / 2
    if nd['shape'] == 'database':
        dx = px - cx
        return y + h + CYL * math.sqrt(max(0, 1 - (dx / (w / 2)) ** 2))
    if nd['shape'] == 'document':
        t = 2 * (1 - (px - x) / w) if px >= cx else 2 * (px - x) / w
        return y + h - 2 * WAVE * (2 * t * (1 - t)) * (1 if px >= cx else -1)
    if nd['shape'] == 'offpage':
        return y + h - POINT * (abs(px - cx) / (w / 2))
    if nd['shape'] == 'decision':
        return y + h - (h / 2) * abs(px - cx) / (w / 2)
    return y + h


def shape_path(shape, x, y, w, h):
    """The outline of one shape in the box (x, y, w, h). Junction is drawn by the caller."""
    if shape == 'terminal':
        r = min(h / 2, w / 2)
        return ('M%s,%s H%s A%s,%s 0 0 1 %s,%s H%s A%s,%s 0 0 1 %s,%s Z'
                % (f(x + r), f(y), f(x + w - r), f(r), f(r), f(x + w - r), f(y + h), f(x + r), f(r), f(r), f(x + r), f(y)))
    if shape == 'manualIO':
        s = min(SLANT, h / 3)
        return 'M%s,%s L%s,%s V%s H%s Z' % (f(x), f(y + s), f(x + w), f(y), f(y + h), f(x))
    if shape == 'manualOp':
        i = min(10, w / 6)
        return 'M%s,%s H%s L%s,%s H%s Z' % (f(x), f(y), f(x + w), f(x + w - i), f(y + h), f(x + i))
    if shape == 'decision':
        cx, cy = x + w / 2, y + h / 2
        return 'M%s,%s L%s,%s L%s,%s L%s,%s Z' % (f(cx), f(y), f(x + w), f(cy), f(cx), f(y + h), f(x), f(cy))
    if shape == 'document':
        wv = min(WAVE, h / 6) * 2
        return ('M%s,%s H%s V%s Q%s,%s %s,%s T%s,%s Z'
                % (f(x), f(y), f(x + w), f(y + h), f(x + w * .75), f(y + h - wv), f(x + w / 2), f(y + h), f(x), f(y + h)))
    if shape == 'database':
        ry = min(CYL, h / 5)
        rx = w / 2
        return ('M%s,%s V%s A%s,%s 0 0 0 %s,%s V%s A%s,%s 0 0 0 %s,%s Z'
                % (f(x), f(y + ry), f(y + h), f(rx), f(ry), f(x + w), f(y + h), f(y + ry), f(rx), f(ry), f(x), f(y + ry)))
    if shape == 'offpage':
        p = min(POINT, h / 3)
        return 'M%s,%s H%s V%s L%s,%s L%s,%s Z' % (f(x), f(y), f(x + w), f(y + h - p), f(x + w / 2), f(y + h), f(x), f(y + h - p))
    return 'M%s,%s H%s V%s H%s Z' % (f(x), f(y), f(x + w), f(y + h), f(x))


def shape_svg(shape, x, y, w, h, fill, stroke, dash=None, sw=1.3):
    extra = ' stroke-dasharray="%s"' % dash if dash else ''
    common = 'fill="%s" stroke="%s" stroke-width="%s"%s' % (fill, stroke, f(sw), extra)
    if shape == 'junction':
        r = min(w, h) / 2
        cx, cy = x + w / 2, y + h / 2
        k = r * .6
        return ('<circle cx="%s" cy="%s" r="%s" %s/>' % (f(cx), f(cy), f(r), common)
                + '<path d="M%s,%s H%s M%s,%s V%s" stroke="%s" stroke-width="%s" fill="none"/>'
                % (f(cx - k), f(cy), f(cx + k), f(cx), f(cy - k), f(cy + k), stroke, f(sw)))
    out = '<path d="%s" %s/>' % (shape_path(shape, x, y, w, h), common)
    if shape == 'database':
        ry = min(CYL, h / 5)
        out += '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" %s/>' % (f(x + w / 2), f(y + ry), f(w / 2), f(ry), common)
    return out


def rects_overlap(a, b, pad=0):
    return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad


def seg_hits_rect(p, q, r):
    lo_x, hi_x = sorted((p[0], q[0]))
    lo_y, hi_y = sorted((p[1], q[1]))
    return lo_x < r[2] and hi_x > r[0] and lo_y < r[3] and hi_y > r[1]


# ----------------------------------------------------------------------------------------------
# Build: parse, lay out, size, route, label. One model serves render and lint.

def flow_title(fm, path):
    for k in ('originalName', 'name'):
        v = fm.get(k)
        if isinstance(v, str) and js_trim(v):
            return js_trim(v)
    return os.path.splitext(os.path.basename(path or 'flow'))[0]


def build(text, reg, lang='en', register='audit', path=None):
    fm, fm_warnings, _ = read_frontmatter(text)
    cuts = []
    block = parse_step_block(fm, page=True, cuts=cuts)
    lay = layout(block, page=True)
    steps, flow = block['steps'], block['flow']
    audit = register == 'audit'
    ui = UI[lang]
    model = {'fm': fm, 'fm_warnings': fm_warnings, 'cuts': cuts, 'block': block, 'layout': lay,
             'title': flow_title(fm, path),
             'nodes': {}, 'routes': [], 'labels': [], 'phases': [], 'overlaps': [], 'long_labels': [],
             'lang': lang, 'register': register}
    if not steps:
        return model
    rows = lay['rows']
    row_index = dict((rk, n) for n, rk in enumerate(rows))

    # node text and sizes
    nodes = model['nodes']
    for s in steps:
        sid = s['id']
        shape = lay['shape'][sid]
        number, name = split_number(s['title'])
        lines = wrap(name, FS_NODE, text_room(shape))
        if len(lines) > MAX_NODE_LINES:
            model['long_labels'].append((sid, 'step', '%d lines' % len(lines)))
        # The tab carries the step number in both registers: a drawing and its document match by
        # step number alone (process-step-card.md §1). A step with no number shows its id in the
        # audit register, and no tab in the clean one.
        badge = number or (sid if audit else None)
        nodes[sid] = {'id': sid, 'kind': s['kind'], 'role': reg['_role'][s['kind']], 'shape': shape,
                      'lines': lines, 'badge': badge, 'number': number, 'w': NW if shape != 'junction' else 32,
                      'h': node_height(shape, len(lines)), 'col': lay['col'][sid],
                      'row': row_index[(lay['lane'][sid], lay['sub'][sid])], 'lane': lay['lane'][sid],
                      'title': s['title']}

    # lane header text
    lane_rows = {}
    for n, (ln, sb) in enumerate(rows):
        lane_rows.setdefault(ln, []).append(n)
    titles, row_titles = reg['lanes']['titles'][lang], reg['lanes']['rows'][lang]
    lane_title_lines = dict((ln, wrap(titles[ln], FS_HEAD, HEAD_W - 18)) for ln in lane_rows)
    row_title_lines = [wrap(row_titles[ln][sb], FS_ROW, HEAD_W - 18) for (ln, sb) in rows]

    # rows: tall enough for the tallest box (its badge tab and its bottom curve included) and the header
    row_h = []
    for n, (ln, sb) in enumerate(rows):
        need = MIN_ROW_H
        for nd in nodes.values():
            if nd['row'] == n:
                extent = nd['h'] + (TAB if nd['badge'] else 0) + 2 * WAVE + 2
                if nd['shape'] == 'junction':
                    extent = nd['h'] * 2
                need = max(need, extent + 2 * ROW_PAD)
        head = 14 + 15 * len(row_title_lines[n])
        if lane_rows[ln][0] == n:
            head += 16 + 15 * len(lane_title_lines[ln])
        row_h.append(max(need, head))

    has_phases = any(p for p in block['phases'])
    x0 = MARGIN + HEAD_W
    lanes_top = MARGIN + TITLE_H + ((PHASE_H + PHASE_GAP) if has_phases else 0)
    row_top = [lanes_top]
    for h in row_h:
        row_top.append(row_top[-1] + h)
    lanes_bottom = row_top[-1]
    lanes_right = x0 + lay['cols'] * COL_W
    model.update({'x0': x0, 'lanes_top': lanes_top, 'lanes_bottom': lanes_bottom, 'lanes_right': lanes_right,
                  'row_top': row_top, 'row_h': row_h, 'lane_rows': lane_rows,
                  'lane_title_lines': lane_title_lines, 'row_title_lines': row_title_lines})

    # place the boxes: centred in their cell, every box in a row on the row's centre line
    for nd in nodes.values():
        mid = row_top[nd['row']] + row_h[nd['row']] / 2
        cx = x0 + nd['col'] * COL_W + COL_W / 2
        if nd['shape'] == 'junction':
            nd['x'], nd['y'] = cx - 16, mid - 16
            nd['h'] = 32
            lw = max(tw(x, FS_NODE) for x in nd['lines']) if nd['lines'] else 0
            nd['label_box'] = (cx - lw / 2 - 2, mid + 20, cx + lw / 2 + 2, mid + 22 + LH_NODE * len(nd['lines']))
        else:
            nd['x'], nd['y'] = cx - NW / 2, mid - nd['h'] / 2
        nd['cx'], nd['cy'] = cx, mid
        x, y, w, h = nd['x'], nd['y'], nd['w'], nd['h']
        top, bottom = y, y + h
        if nd['shape'] in ('database',):
            bottom += CYL
        if nd['shape'] == 'document':
            bottom += WAVE
        left, right = x, x + w
        if nd['shape'] == 'junction':
            lb = nd['label_box']
            left, right, bottom = min(left, lb[0]), max(right, lb[2]), lb[3]
        if nd['badge']:
            bw = len(nd['badge']) * FS_BADGE * .62 + 10
            if nd['shape'] == 'decision':
                bx, by = x, y - 2
            elif nd['shape'] == 'junction':
                bx, by = x - bw - 6, y - 4
            else:
                bx = x + 14
                by = top_at(nd, bx) - TAB
            nd['badge_box'] = (bx, by, bx + bw, by + 16)
            top = min(top, by)
            left = min(left, bx)
        nd['bbox'] = (left, top, right, bottom)

    # phase bands, from the cells of the steps each phase holds
    by_ordinal = dict((s['ordinal'], s['id']) for s in steps)
    bands = []
    for ph in block['phases']:
        members = [by_ordinal[o] for o in range(ph['from'], ph['to'] + 1) if o in by_ordinal]
        if not members:
            continue
        c0 = min(nodes[m]['col'] for m in members)
        c1 = max(nodes[m]['col'] for m in members)
        bx0, bx1 = x0 + c0 * COL_W + 6, x0 + (c1 + 1) * COL_W - 6
        by0 = lanes_top - PHASE_GAP - PHASE_H
        room = bx1 - bx0 - 16
        name = ph['name']
        shown = name
        if tw(name, FS_HEAD) > room:
            model['long_labels'].append((members[0], 'phase', ph['name']))
            while shown and tw(shown + '…', FS_HEAD) > room:
                shown = shown[:-1]
            shown += '…'
        bands.append({'name': name, 'shown': shown, 'box': (bx0, by0, bx1, by0 + PHASE_H), 'members': members,
                      'c0': c0, 'c1': c1})
    model['phases'] = bands
    for a in range(len(bands)):
        for b in range(a + 1, len(bands)):
            if rects_overlap(bands[a]['box'], bands[b]['box']):
                pa, pb = bands[a], bands[b]
                # name the steps that sit inside the other phase's columns: those are the ones to move.
                # Two bands that share a column always have one: the leftmost step of one band sits in
                # the other's columns.
                inside = ([m for m in pa['members'] if pb['c0'] <= nodes[m]['col'] <= pb['c1']] +
                          [m for m in pb['members'] if pa['c0'] <= nodes[m]['col'] <= pa['c1']])
                model['overlaps'].append({'what': 'phase', 'steps': inside,
                                          'detail': 'phase bands "%s" (col=%d–%d) and "%s" (col=%d–%d) share columns: %s'
                                                    % (pa['name'], pa['c0'], pa['c1'], pb['name'], pb['c0'], pb['c1'],
                                                       ', '.join('%s at col=%d' % (m, nodes[m]['col']) for m in inside))})

    for a in steps:
        for b in steps:
            if a['id'] < b['id'] and rects_overlap(nodes[a['id']]['bbox'], nodes[b['id']]['bbox']):
                model['overlaps'].append({'what': 'box', 'steps': [a['id'], b['id']],
                                          'detail': 'boxes %s and %s overlap' % (a['id'], b['id'])})

    route_edges(model, reg)
    place_labels(model, reg)
    return model


def ports_of(nd):
    shape, x, y, w, h = nd['shape'], nd['x'], nd['y'], nd['w'], nd['h']
    cx, cy = nd['cx'], nd['cy']
    bx0, by0, bx1, by1 = nd['bbox']
    out = []

    def add(px, py, side, cost):
        if side == 'L':
            s = (bx0 - CLEAR - 4, py)
        elif side == 'R':
            s = (bx1 + CLEAR + 4, py)
        elif side == 'T':
            s = (px, by0 - CLEAR - 4)
        else:
            s = (px, by1 + CLEAR + 4)
        stub = abs(s[0] - px) + abs(s[1] - py) - (CLEAR + 4)
        out.append({'p': (px, py), 'side': side, 's': s, 'node': nd['id'], 'cost': cost + max(0, stub) * .5})

    if shape == 'junction':
        r = w / 2
        add(cx - r, cy, 'L', 0)
        add(cx + r, cy, 'R', 0)
        add(cx, cy - r, 'T', 0)
        add(cx, cy + r, 'B', 0)
        return out
    if shape == 'decision':
        add(x, cy, 'L', 0)
        add(x + w, cy, 'R', 0)
        add(cx, y, 'T', 0)
        add(cx, y + h, 'B', 0)
        for px, py, sides in ((x + w * .25, y + h * .25, 'LT'), (x + w * .75, y + h * .25, 'RT'),
                              (x + w * .25, y + h * .75, 'LB'), (x + w * .75, y + h * .75, 'RB')):
            add(px, py, sides[0], 14)
            add(px, py, sides[1], 18)
        return out
    for dy in (0, -8, 8, -16, 16, -24, 24):
        py = cy + dy
        if py < y + 8 or py > y + h - 8:
            continue
        inset = 10 * (py - y) / h if shape == 'manualOp' else 0
        add(x + inset, py, 'L', .4 * abs(dy) + (2 if dy else 0))
        add(x + w - inset, py, 'R', .4 * abs(dy) + (2 if dy else 0))
    lim = w / 2 - (24 if shape in ('manualOp', 'terminal') else 14)
    for slot, dx in enumerate((0, -24, 24, -48, 48, -72, 72)):
        if abs(dx) > lim:
            continue
        px = cx + dx
        add(px, top_at(nd, px), 'T', 9 * slot)
        if shape == 'offpage' and dx:
            continue
        add(px, bottom_at(nd, px), 'B', 9 * slot)
    return out


def route_edges(model, reg):
    nodes, flow = model['nodes'], model['block']['flow']
    x0, top, right, bottom = model['x0'], model['lanes_top'], model['lanes_right'], model['lanes_bottom']
    allports = dict((sid, ports_of(nd)) for sid, nd in nodes.items())
    infl = [(a - CLEAR, b - CLEAR, c + CLEAR, d + CLEAR) for (a, b, c, d) in (nd['bbox'] for nd in nodes.values())]
    box = (x0 + 3, top + 3, right - 3, bottom - 3)

    def stub_ok(pt, own):
        (px, py), (sx, sy) = pt['p'], pt['s']
        if not (box[0] <= sx <= box[2] and box[1] <= sy <= box[3]):
            return False
        ob = nodes[own]['bbox']
        mine = (ob[0] - CLEAR, ob[1] - CLEAR, ob[2] + CLEAR, ob[3] + CLEAR)
        for r in infl:
            if r == mine:
                continue
            lo_x, hi_x = sorted((px, sx))
            lo_y, hi_y = sorted((py, sy))
            if lo_x < r[2] and hi_x > r[0] and lo_y < r[3] and hi_y > r[1] \
                    and not (lo_x == hi_x and (lo_x <= r[0] or lo_x >= r[2])) \
                    and not (lo_y == hi_y and (lo_y <= r[1] or lo_y >= r[3])):
                return False
        return True

    xs, ys = [], []
    ncol = model['layout']['cols']
    for i in range(ncol + 1):
        left = x0 + 3 if i == 0 else x0 + COL_W * i - (COL_W - NW) / 2 + CLEAR
        rgt = right - 3 if i == ncol else x0 + COL_W * i + (COL_W - NW) / 2 - CLEAR
        mid = x0 + COL_W * i if 0 < i < ncol else (left + rgt) / 2
        k = 0
        while True:
            a, b = mid - TRACK * (k + .5), mid + TRACK * (k + .5)
            if a < left and b > rgt:
                break
            if a >= left:
                xs.append(a)
            if b <= rgt:
                xs.append(b)
            k += 1
    for pl in allports.values():
        for pt in pl:
            xs.append(pt['s'][0])
            ys.append(pt['s'][1])
    y = top + 3.5
    while y < bottom - 3:
        ys.append(y)
        y += TRACK
    router = Router(xs, ys, infl, box)
    used = set()

    def pkey(pt):
        return (pt['node'], round(pt['p'][0], 1), round(pt['p'][1], 1))

    order = sorted(range(len(flow)), key=lambda q: (flow[q]['role'] != 'spine',
                                                    abs(nodes[flow[q]['from']]['col'] - nodes[flow[q]['to']]['col']),
                                                    abs(nodes[flow[q]['from']]['row'] - nodes[flow[q]['to']]['row']), q))
    back = model['layout']['back']

    def ends(e, sides):
        """The free ports of a line's two steps, as A* starts and goals; `sides` limits the sides
        and adds a cost per side."""
        starts, goals = [], {}
        for pt in allports[e['from']]:
            if (sides and pt['side'] not in sides) or pkey(pt) in used or not stub_ok(pt, e['from']):
                continue
            ij = router.ij(pt['s'])
            if ij:
                starts.append((ij[0], ij[1], SIDE_DIR[pt['side']], pt['cost'] + (sides[pt['side']] if sides else 0), pt))
        for pt in allports[e['to']]:
            if (sides and pt['side'] not in sides) or pkey(pt) in used or not stub_ok(pt, e['to']):
                continue
            ij = router.ij(pt['s'])
            if ij:
                goals.setdefault(ij, []).append((OPP[SIDE_DIR[pt['side']]], pt['cost'] + (sides[pt['side']] if sides else 0), pt))
        return starts, goals

    routes = []
    for q in order:
        e = flow[q]
        a, b = nodes[e['from']], nodes[e['to']]
        # A back edge (a retry) leaves and enters through the bottom or the top, so it loops around
        # the row and reads as a return, not as one more step forward.
        starts, goals = ends(e, {'B': 0, 'T': 30}) if any(e is x for x in back) else ([], {})
        if not starts or not goals:
            starts, goals = ends(e, None)
        lo = min(a['bbox'][0], b['bbox'][0]) - COL_W
        hi = max(a['bbox'][2], b['bbox'][2]) + COL_W
        res = router.search(starts, goals, (lo, hi)) if starts and goals else None
        if res is None and starts and goals:
            res = router.search(starts, goals)
        if res:
            path, ps, pd = res
            router.mark(path)
            used.add(pkey(ps))
            used.add(pkey(pd))
            pts = simplify([ps['p']] + [(router.X[i], router.Y[j]) for i, j in path] + [pd['p']])
        else:
            ax, ay = a['bbox'][2], a['cy']
            bx, by = b['bbox'][0], b['cy']
            mx = (ax + bx) / 2
            pts = simplify([(ax, ay), (mx, ay), (mx, by), (bx, by)])
            model['overlaps'].append({'what': 'line', 'steps': [e['from'], e['to']],
                                      'detail': 'the line %s %s %s could not be routed clear of the boxes'
                                                % (e['from'], '->' if e['role'] == 'spine' else '~>', e['to'])})
        routes.append({'q': q, 'edge': e, 'pts': pts})
    routes.sort(key=lambda r: r['q'])
    model['routes'] = routes


def label_shown(model, e):
    if not e['label']:
        return False
    if model['register'] == 'audit':
        return True
    # The clean register keeps the labels of the branches out of a decision or a fork only (a gate or
    # a junction, as place_labels treats them): every other label is left off.
    return e['role'] == 'spine' and model['nodes'][e['from']]['kind'] in ('gate', 'junction')


def label_spot(model, r, lines, blockers, placed, segs, area, gate):
    """The best free rectangle for a label of these lines on route r, or None. Candidates sit on
    the line every 5px and at each run's middle, then beside it; a gate's label prefers the start
    of its line, any other label the middle. Crossing another line costs, overlapping never fits."""
    w = max(tw(x, FS_LABEL) for x in lines) + 8
    h = len(lines) * LH_LABEL + 4
    pts = r['pts']
    lengths = [abs(q[0] - p[0]) + abs(q[1] - p[1]) for p, q in zip(pts, pts[1:])]
    total = sum(lengths) or 1
    best = None
    walked = 0
    for k, (p, q) in enumerate(zip(pts, pts[1:])):
        seg_len = lengths[k]
        n_steps = max(1, int(seg_len // 5))
        alongs = sorted(set([seg_len * t / n_steps for t in range(n_steps + 1)] + [seg_len / 2]))
        vertical = abs(q[0] - p[0]) < .01
        for along in alongs:
            frac = along / seg_len if seg_len else 0
            cx, cy = p[0] + (q[0] - p[0]) * frac, p[1] + (q[1] - p[1]) * frac
            pos = walked + along
            base = pos if gate else abs(pos - total / 2)
            # On the line first; then beside it (right or left of a vertical run, above or below
            # a horizontal one), where a narrow gap leaves no room on the line itself.
            if vertical:
                spots = ((cx - w / 2, cy - h / 2, 0), (cx + 3, cy - h / 2, 30), (cx - 3 - w, cy - h / 2, 30))
            else:
                spots = ((cx - w / 2, cy - h / 2, 0), (cx - w / 2, cy - 3 - h, 30), (cx - w / 2, cy + 3, 30))
            for (lx, ly, extra) in spots:
                score = base + extra
                if best is not None and score >= best[0]:
                    continue
                rect = (lx, ly, lx + w, ly + h)
                if not (area[0] <= rect[0] and rect[2] <= area[2] and area[1] <= rect[1] and rect[3] <= area[3]):
                    continue
                if any(rects_overlap(rect, bb, -2) for bb in blockers):
                    continue
                if any(rects_overlap(rect, pl['box'], -2) for pl in placed):
                    continue
                score += 400 * sum(1 for (rq, a2, b2) in segs if rq != r['q'] and seg_hits_rect(a2, b2, rect))
                if best is None or score < best[0]:
                    best = (score, rect)
        walked += seg_len
    return best[1] if best else None


def place_labels(model, reg):
    nodes = model['nodes']
    blockers = [nd['bbox'] for nd in nodes.values()]
    for nd in nodes.values():
        if nd.get('label_box'):
            blockers.append(nd['label_box'])
    placed = []
    area = (model['x0'] + 2, model['lanes_top'] + 2, model['lanes_right'] - 2, model['lanes_bottom'] - 2)
    segs = []
    for r in model['routes']:
        for p, q in zip(r['pts'], r['pts'][1:]):
            segs.append((r['q'], p, q))
    for r in model['routes']:
        e = r['edge']
        if not e['label']:
            continue
        lines = wrap(e['label'], FS_LABEL, LABEL_W)
        if len(lines) > MAX_LABEL_LINES:
            model['long_labels'].append((e['from'], 'line', e['label']))
        if not label_shown(model, e):
            continue
        gate = nodes[e['from']]['kind'] in ('gate', 'junction')
        # The label's own width first; where the line runs through a gap too narrow for it, the
        # same words on more, shorter lines (a gutter between two columns is under 100px).
        tries = [lines]
        for room in (100, 84, 68):
            alt = wrap(e['label'], FS_LABEL, room)
            if len(alt) <= MAX_LABEL_LINES + 1 and alt not in tries:
                tries.append(alt)
        rect = None
        for attempt in tries:
            rect = label_spot(model, r, attempt, blockers, placed, segs, area, gate)
            if rect:
                lines = attempt
                break
        if rect is None:
            w = max(tw(x, FS_LABEL) for x in lines) + 8
            h = len(lines) * LH_LABEL + 4
            mid = r['pts'][len(r['pts']) // 2]
            rect = (mid[0] - w / 2, mid[1] - h / 2, mid[0] + w / 2, mid[1] + h / 2)
            model['overlaps'].append({'what': 'label', 'steps': [e['from'], e['to']],
                                      'detail': 'the label "%s" on %s %s %s has no free place'
                                                % (e['label'], e['from'], '->' if e['role'] == 'spine' else '~>', e['to'])})
        placed.append({'box': rect, 'lines': lines, 'edge': e, 'gate': gate})
    model['labels'] = placed


# ----------------------------------------------------------------------------------------------
# Render.

def legend_items(model, reg):
    present = []
    for s in model['block']['steps']:
        role = reg['_role'][s['kind']]
        if role not in present:
            present.append(role)
    roles = [r for r in reg['roles'] if r in present]
    roles_edges = []
    for role in ('spine', 'plumbing'):
        if any(e['role'] == role for e in model['block']['flow']):
            roles_edges.append(role)
    return roles, roles_edges


def glyph(role, x, y, reg):
    """A small copy of a role's shape for the legend, in a 30 x 18 box."""
    shape = role['shape']
    if shape == 'junction':
        return shape_svg('junction', x + 6, y, 18, 18, role['fill'], role['stroke'], role.get('dash'), 1.1)
    if shape == 'decision':
        return shape_svg('decision', x + 1, y, 28, 18, role['fill'], role['stroke'], role.get('dash'), 1.1)
    hh = 14 if shape in ('database', 'document') else 18
    return shape_svg(shape, x, y, 30, hh, role['fill'], role['stroke'], role.get('dash'), 1.1)


def render_svg(model, reg):
    lang, ui = model['lang'], UI[model['lang']]
    audit = model['register'] == 'audit'
    text = reg['text']
    page = reg['page']
    lanes = reg['lanes']
    nodes = model['nodes']
    steps = model['block']['steps']
    o = []
    if not steps:
        raise KitError('the flow declares no steps')
    lanes_right, x0 = model['lanes_right'], model['x0']
    roles, edge_roles = legend_items(model, reg)

    # legend and panel geometry, below the lanes
    width = max(lanes_right + MARGIN, 720)
    inner = width - 2 * MARGIN - 24
    items = []
    for role in roles:
        items.append(('role', role, role['label'][lang]))
    for er in edge_roles:
        items.append(('edge', er, reg['edges'][er]['label'][lang]))
    lx, ly = 0, 0
    placed_items = []
    for kind, what, label in items:
        iw = 30 + 8 + tw(label, FS_LABEL) + 22
        if lx and lx + iw > inner:
            lx, ly = 0, ly + 26
        placed_items.append((kind, what, label, lx, ly))
        lx += iw
    legend_h = ly + 26
    how_lines = wrap(ui['how_text'], FS_LABEL, inner) if not audit else []
    panel_top = model['lanes_bottom'] + 18
    panel_h = 30 + legend_h + 10 + ((26 + LH_LABEL * len(how_lines) + 6) if how_lines else 0) + 16
    height = panel_top + panel_h + MARGIN

    o.append('<rect x="0" y="0" width="%s" height="%s" fill="%s"/>' % (f(width), f(height), page['background']))
    # title
    o.append('<text x="%s" y="%s" font-family="%s" font-size="16" font-weight="700" fill="%s">%s</text>'
             % (f(MARGIN), f(MARGIN + 16), esc(FONT), text['primary'], esc(model['title'])))
    if audit:
        sub = '%d %s · %d %s · %s · %s %s' % (
            len(steps), ui['steps'], len(model['block']['flow']), ui['lines'], ui['audit'], ui['colours'], reg['version'])
        o.append('<text x="%s" y="%s" font-family="%s" font-size="11" fill="%s">%s</text>'
                 % (f(MARGIN), f(MARGIN + 34), esc(FONT), text['muted'], esc(sub)))
    # phase bands
    ph = page['phase']
    for band in model['phases']:
        a, b, c, d = band['box']
        o.append('<rect x="%s" y="%s" width="%s" height="%s" rx="4" fill="%s" stroke="%s" stroke-width="1"/>'
                 % (f(a), f(b), f(c - a), f(d - b), ph['fill'], ph['stroke']))
        o.append('<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="600" fill="%s" text-anchor="middle">%s</text>'
                 % (f((a + c) / 2), f(b + PHASE_H / 2 + 4), esc(FONT), f(FS_HEAD), ph['text'], esc(band['shown'])))
    # lanes: a faint fill per layer, a light header column, dark titles
    rows, row_top, row_h = model['layout']['rows'], model['row_top'], model['row_h']
    for n, (ln, sb) in enumerate(rows):
        o.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>'
                 % (f(x0), f(row_top[n]), f(lanes_right - x0), f(row_h[n]), lanes['fill'][ln]))
    for ln, idxs in model['lane_rows'].items():
        top, bot = row_top[idxs[0]], row_top[idxs[-1]] + row_h[idxs[-1]]
        tl = model['lane_title_lines'][ln]
        band = 16 + 15 * len(tl)
        o.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>'
                 % (f(MARGIN), f(top), f(HEAD_W), f(bot - top), lanes['subheader']['fill']))
        o.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>'
                 % (f(MARGIN), f(top), f(HEAD_W), f(band), lanes['header']['fill']))
        for i, line in enumerate(tl):
            o.append('<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="700" fill="%s">%s</text>'
                     % (f(MARGIN + 9), f(top + 15 + 15 * i), esc(FONT), f(FS_HEAD), lanes['header']['text'], esc(line)))
        for n in idxs:
            rl = model['row_title_lines'][n]
            start = row_top[n] + (band if n == idxs[0] else 0)
            room = row_top[n] + row_h[n] - start
            y0 = start + max(8, (room - 15 * len(rl)) / 2) + 11
            for i, line in enumerate(rl):
                o.append('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s">%s</text>'
                         % (f(MARGIN + 9), f(y0 + 15 * i), esc(FONT), f(FS_ROW), lanes['subheader']['text'], esc(line)))
    for n in range(1, len(rows)):
        same = rows[n][0] == rows[n - 1][0]
        o.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s"%s/>'
                 % (f(MARGIN + (HEAD_W if same else 0)), f(row_top[n]), f(lanes_right), f(row_top[n]),
                    lanes['separator'] if same else lanes['frame'], '1' if same else '1.5',
                    ' stroke-dasharray="3 4"' if same else ''))
    o.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="1"/>'
             % (f(x0), f(model['lanes_top']), f(x0), f(model['lanes_bottom']), lanes['frame']))
    o.append('<rect x="%s" y="%s" width="%s" height="%s" rx="6" fill="none" stroke="%s" stroke-width="1.5"/>'
             % (f(MARGIN + .5), f(model['lanes_top'] + .5), f(lanes_right - MARGIN - 1),
                f(model['lanes_bottom'] - model['lanes_top'] - 1), lanes['frame']))
    # lines: plumbing under the spine
    o.append('<defs>' + ''.join(
        '<marker id="mk-%s" viewBox="0 0 8 8" refX="7.6" refY="4" markerWidth="%s" markerHeight="%s" '
        'markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="%s"/></marker>'
        % (er, 8 if er == 'spine' else 7, 8 if er == 'spine' else 7, reg['edges'][er]['stroke'])
        for er in ('spine', 'plumbing')) + '</defs>')
    for role in ('plumbing', 'spine'):
        st = reg['edges'][role]
        dash = ' stroke-dasharray="%s"' % st['dash'] if st.get('dash') else ''
        for r in model['routes']:
            e = r['edge']
            if e['role'] != role:
                continue
            o.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s"%s marker-end="url(#mk-%s)" data-line="%s %s %s"/>'
                     % (path_d(r['pts']), st['stroke'], f(st['width']), dash, role, esc(e['from']),
                        '->' if role == 'spine' else '~>', esc(e['to'])))
    # boxes
    for s in steps:
        nd = nodes[s['id']]
        role = nd['role']
        parts = ['<g data-step="%s" data-kind="%s">' % (esc(nd['id']), nd['kind'])]
        parts.append(shape_svg(nd['shape'], nd['x'], nd['y'], nd['w'], nd['h'], role['fill'], role['stroke'], role.get('dash')))
        lines = nd['lines']
        if nd['shape'] == 'junction':
            ty = nd['label_box'][1] + 12
        else:
            top, bottom = PADS.get(nd['shape'], (0, 0)) if nd['shape'] != 'decision' else (0, 0)
            body_top, body_bottom = nd['y'] + top, nd['y'] + nd['h'] - bottom
            if nd['shape'] == 'decision':
                body_top, body_bottom = nd['y'], nd['y'] + nd['h']
            ty = (body_top + body_bottom) / 2 - LH_NODE * len(lines) / 2 + 12
        for i, line in enumerate(lines):
            parts.append('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s" text-anchor="middle">%s</text>'
                         % (f(nd['cx']), f(ty + LH_NODE * i), esc(FONT), f(FS_NODE), text['primary'], esc(line)))
        if nd['badge']:
            a, b, c, d = nd['badge_box']
            parts.append('<rect x="%s" y="%s" width="%s" height="%s" rx="8" fill="%s" stroke="%s" stroke-width="1"/>'
                         % (f(a), f(b), f(c - a), f(d - b), page['badge']['fill'], role['stroke']))
            parts.append('<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="700" fill="%s" text-anchor="middle"%s>%s</text>'
                         % (f((a + c) / 2), f(b + 11.5), esc(MONO), f(FS_BADGE), text['primary'],
                            ' data-number="%s"' % esc(nd['number']) if nd['number'] else '', esc(nd['badge'])))
        parts.append('</g>')
        o.append(''.join(parts))
    # labels, on a halo so the line under them stays readable
    for lab in model['labels']:
        a, b, c, d = lab['box']
        o.append('<rect x="%s" y="%s" width="%s" height="%s" rx="3" fill="%s"/>'
                 % (f(a), f(b), f(c - a), f(d - b), page['labelHalo']))
        for i, line in enumerate(lab['lines']):
            o.append('<text x="%s" y="%s" font-family="%s" font-size="%s"%s fill="%s" text-anchor="middle">%s</text>'
                     % (f((a + c) / 2), f(b + 2 + 10.5 + LH_LABEL * i), esc(FONT), f(FS_LABEL),
                        ' font-weight="700"' if lab['gate'] else '',
                        text['primary'] if lab['gate'] else text['secondary'], esc(line)))
    # the legend panel (and the how-to-read panel in the clean register)
    pn = page['panel']
    o.append('<rect x="%s" y="%s" width="%s" height="%s" rx="6" fill="%s" stroke="%s" stroke-width="1"/>'
             % (f(MARGIN), f(panel_top), f(width - 2 * MARGIN), f(panel_h), pn['fill'], pn['stroke']))
    o.append('<text x="%s" y="%s" font-family="%s" font-size="12" font-weight="700" fill="%s">%s</text>'
             % (f(MARGIN + 12), f(panel_top + 20), esc(FONT), text['primary'], esc(ui['legend'])))
    o.append('<text x="%s" y="%s" font-family="%s" font-size="10" fill="%s" text-anchor="end">%s</text>'
             % (f(width - MARGIN - 12), f(panel_top + 20), esc(MONO), text['muted'],
                esc('flow-colours %s' % reg['version'])))
    base_y = panel_top + 32
    for kind, what, label, ix, iy in placed_items:
        gx, gy = MARGIN + 12 + ix, base_y + iy
        if kind == 'role':
            o.append(glyph(what, gx, gy, reg))
        else:
            st = reg['edges'][what]
            dash = ' stroke-dasharray="%s"' % st['dash'] if st.get('dash') else ''
            o.append('<path d="M%s,%s H%s" stroke="%s" stroke-width="%s"%s marker-end="url(#mk-%s)"/>'
                     % (f(gx + 1), f(gy + 9), f(gx + 28), st['stroke'], f(st['width']), dash, what))
        o.append('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s">%s</text>'
                 % (f(gx + 38), f(gy + 13), esc(FONT), f(FS_LABEL), text['secondary'], esc(label)))
    if how_lines:
        hy = base_y + legend_h + 10
        o.append('<text x="%s" y="%s" font-family="%s" font-size="12" font-weight="700" fill="%s">%s</text>'
                 % (f(MARGIN + 12), f(hy + 12), esc(FONT), text['primary'], esc(ui['how'])))
        for i, line in enumerate(how_lines):
            o.append('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s">%s</text>'
                     % (f(MARGIN + 12), f(hy + 30 + LH_LABEL * i), esc(FONT), f(FS_LABEL), text['secondary'], esc(line)))
    aria = '%s: %d %s' % (model['title'], len(steps), ui['steps'])
    head = ('<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s" role="img" '
            'aria-label="%s" data-flow-colours="%s" data-register="%s">'
            % (f(width), f(height), f(width), f(height), esc(aria), esc(reg['version']), model['register']))
    return head + '\n' + '\n'.join(o) + '\n</svg>\n'


# ----------------------------------------------------------------------------------------------
# Lint.

RULES = {
    'parse': ('hard', 'fix the line so Atlas reads it: a step is "<id> | <kind> | <title>", a flow line "a -> b" '
                      'or "a ~> b" between two steps the file declares'),
    'V4': ('hard', 'write the decision down: `<hitl step> ~> <decision log>`, with the log as a store step '
                   '(`Decision log (new)` when it does not exist yet)'),
    'V5': ('soft', 'add a gate downstream that checks confidence or validity, a hitl step that reviews the output, '
                   'or an error or retry line: a labelled branch out of the AI step beside its main line, or a line '
                   'back to an earlier step'),
    'V6': ('hard', 'label it: `big -> review | Yes`, or the outcome\'s name'),
    'V9': ('soft', 'one start that only leads out, and an end (or more than one) that only takes lines in'),
    'V12': ('soft', 'shorten it: a title is its number and at most four words, a label a word or two; '
                    'the detail goes on the step card'),
    'V14': ('hard', 'pick one path as the spine and run it left to right; other paths leave through an offpage step, '
                    'and a source that steps only read takes col= under its reader (columns count from 0)'),
    'overlap': ('hard', 'shorten the title or the label, or move one step with col=; keep each phase a run of '
                        'neighbouring columns'),
}
RULE_ORDER = ('parse', 'V4', 'V5', 'V6', 'V9', 'V12', 'V14', 'overlap')


def lint_model(model):
    """(violations, warnings, notes). Every violation is a rule lint checks, and every one fails lint
    (validation.md). Warnings are page-only kinds: drawn here, dropped by Atlas. Notes are parser
    warnings that drop nothing (an unknown option, an unknown executed_by)."""
    block = model['block']
    steps, flow = block['steps'], block['flow']
    by_id = dict((s['id'], s) for s in steps)
    found, warnings, notes = [], [], []

    def hit(rule, ids, message, fix=None):
        found.append({'rule': rule, 'severity': RULES[rule][0], 'steps': ids, 'message': message,
                      'fix': fix or RULES[rule][1]})

    for w in model['fm_warnings']:
        if w['code'] == 'no_frontmatter':
            hit('parse', [], 'the file does not open with a --- line, so Atlas reads no frontmatter and no steps',
                'start the file at the flow text\'s --- line: drop anything above it, such as the header '
                'get_artifact_body puts over the fenced body')
        elif w['code'] == 'unterminated_frontmatter':
            hit('parse', [], 'the frontmatter never closes, so Atlas reads no steps',
                'close it with a --- line after the last flow: line')
        elif w['field'] in ('steps', 'flow'):
            hit('parse', [], '%s in %s: %s' % (w['code'], w['field'], w['detail']))
        else:
            notes.append({'code': w['code'], 'field': w['field'], 'message': w['detail']})
    for w in block['warnings']:
        if w['code'] == 'gate_branch_unlabeled':
            continue  # V6 names it
        if w['code'] in OMISSION_CODES:
            hit('parse', [], '%s: %s' % (w['code'], w['detail']))
        else:
            notes.append({'code': w['code'], 'field': w['field'], 'message': w['detail']})
    if not steps and not any(h['rule'] == 'parse' for h in found):
        hit('parse', [], 'the file declares no steps')
    # a title or a phase name Atlas cuts: the parser keeps the first 60 or 40 characters, as Atlas's
    # does, and says nothing. A phase with no steps is dropped, not cut.
    phase_names = set(p['name'] for p in block['phases'])
    for c in model['cuts']:
        if c['what'] == 'step':
            hit('parse', [c['id']], 'the title has %d characters and Atlas keeps the first %d, "%s"'
                % (c['length'], MAX_TITLE, c['kept']),
                'shorten the title to %d characters or fewer; the detail goes on the step card' % MAX_TITLE)
        elif c['kept'] in phase_names:
            hit('parse', [], 'a phase name has %d characters and Atlas keeps the first %d, "%s"'
                % (c['length'], MAX_PHASE_NAME, c['kept']),
                'shorten the phase name to %d characters or fewer' % MAX_PHASE_NAME)
    for s in steps:
        if s['kind'] in PAGE_ONLY_KINDS:
            warnings.append({'code': 'page_only_kind', 'steps': [s['id']],
                             'message': 'kind %s is page-only: the kit draws it, Atlas has no kind for it and would '
                                        'drop the step, so this flow stays a page drawing' % s['kind']})
    spine_out, spine_in, plumb_out = {}, {}, {}
    for e in flow:
        if e['role'] == 'spine':
            spine_out.setdefault(e['from'], []).append(e)
            spine_in.setdefault(e['to'], []).append(e)
        else:
            plumb_out.setdefault(e['from'], []).append(e)
    back = model['layout']['back']
    # V4: a hitl step with no ~> line to a store or artifact
    for s in steps:
        if s['kind'] == 'hitl':
            if not any(by_id[e['to']]['kind'] in ('store', 'artifact') for e in plumb_out.get(s['id'], [])):
                hit('V4', [s['id']], 'a human step with no ~> line to a store or artifact, so its decision leaves '
                                     'no record')
    # V5: an llm step with no gate, hitl step or error path after it. Its own error path is a line
    # back to an earlier step (a retry), or a labelled branch beside its main line, the line out with
    # no label. A label on its only line out names the next step, and a step whose every line out is
    # labelled sorts its result: neither is an error path. Otherwise every path out must pass a gate
    # or a hitl step before it reaches an output, an end or another flow.
    for s in steps:
        if s['kind'] != 'llm':
            continue
        outs = spine_out.get(s['id'], [])
        main_line = any(not e['label'] for e in outs)
        if any(any(e is b for b in back) for e in outs) or (main_line and any(e['label'] for e in outs)):
            continue
        seen, queue, checked, unchecked = set([s['id']]), [e['to'] for e in outs], False, []
        while queue:
            n = queue.pop(0)
            if n in seen:
                continue
            seen.add(n)
            kind = by_id[n]['kind']
            if kind in ('gate', 'hitl'):
                checked = True  # this path is checked: don't walk past it
            elif kind in ('output', 'end', 'offpage'):
                unchecked.append(n)
            else:
                queue.extend(e['to'] for e in spine_out.get(n, []))
        if not checked:
            hit('V5', [s['id']], 'an AI step whose result no gate or person checks, and with no error or retry line')
        elif unchecked:
            hit('V5', [s['id']], 'an AI step whose result reaches %s with no gate or person checking it on the way, '
                                 'and with no error or retry line' % ', '.join(unchecked))
    # V6: a -> line out of a gate with no label
    for e in flow:
        if e['role'] == 'spine' and by_id[e['from']]['kind'] == 'gate' and not e['label']:
            hit('V6', [e['from']], 'the branch %s -> %s has no label' % (e['from'], e['to']))
    # V9: a start with a -> line into it, or an end with a -> line out of it
    for s in steps:
        if s['kind'] == 'start' and spine_in.get(s['id']):
            hit('V9', [s['id']], 'the start has a -> line into it (from %s)'
                % ', '.join(e['from'] for e in spine_in[s['id']]))
        if s['kind'] == 'end' and spine_out.get(s['id']):
            hit('V9', [s['id']], 'the end has a -> line out of it (to %s)'
                % ', '.join(e['to'] for e in spine_out[s['id']]))
    # V12: a label over its length
    for sid, what, detail in model['long_labels']:
        if what == 'step':
            hit('V12', [sid], 'the title takes %s in its box, more than %d' % (detail, MAX_NODE_LINES))
        elif what == 'line':
            hit('V12', [sid], 'the line label "%s" takes more than %d lines' % (detail, MAX_LABEL_LINES))
        else:
            hit('V12', [sid], 'the phase name "%s" is wider than its phase\'s columns' % detail)
    # V14: more than three steps in one column, after layout
    per_col = {}
    for s in steps:
        per_col.setdefault(model['layout']['col'][s['id']], []).append(s['id'])
    for c in sorted(per_col):
        if len(per_col[c]) > 3:
            hit('V14', per_col[c], 'col=%d holds %d steps' % (c, len(per_col[c])))
    # two boxes or labels that overlap (and a line no route keeps off the boxes)
    for ov in model['overlaps']:
        hit('overlap', ov['steps'], ov['detail'])
    found.sort(key=lambda h: RULE_ORDER.index(h['rule']))
    return found, warnings, notes


def lint_report(path, model):
    found, warnings, notes = lint_model(model)
    hard = [h for h in found if h['severity'] == 'hard']
    soft = [h for h in found if h['severity'] == 'soft']
    # where each step landed, so a V14 or an overlap can be traced to the step that moved
    columns = dict((s['id'], model['layout']['col'][s['id']]) for s in model['block']['steps'])
    return {'file': path, 'title': model['title'], 'steps': len(model['block']['steps']),
            'lines': len(model['block']['flow']), 'violations': found, 'warnings': warnings, 'notes': notes,
            'columns': columns,
            'summary': {'hard': len(hard), 'soft': len(soft), 'warnings': len(warnings), 'notes': len(notes)},
            'exit': 1 if found else 0}


def lint_text(report, model):
    """validation.md's report: rule · step ids (titles) · what is wrong · fix."""
    titles = dict((s['id'], s['title']) for s in model['block']['steps'])

    def who(ids):
        if not ids:
            return 'the flow'
        out = ', '.join('%s (%s)' % (i, titles.get(i, '')) for i in ids[:5])
        return out + (', …' if len(ids) > 5 else '')

    def full_stop(s):
        return s if s.endswith('.') else s + '.'

    def line(h):
        return '- %s — %s: %s Fix: %s' % (h['rule'], who(h['steps']), full_stop(h['message']), full_stop(h['fix']))

    out = ['Lint of %s · %s' % (report['file'], report['title'])]
    hard = [h for h in report['violations'] if h['severity'] == 'hard']
    soft = [h for h in report['violations'] if h['severity'] == 'soft']
    if hard:
        out.append('Hard rule violations (ship-blockers):')
        out.extend(line(h) for h in hard)
    if soft:
        out.append('Soft observations:')
        out.extend(line(h) for h in soft)
    # validation.md's one Warnings group: what Atlas would drop (a page-only kind), then an option or
    # a frontmatter line it can't read, which drops nothing
    if report['warnings'] or report['notes']:
        out.append('Warnings:')
        out.extend('- %s — %s: %s' % (w['code'], who(w['steps']), w['message']) for w in report['warnings'])
        out.extend('- %s — %s: %s' % (n['code'], n['field'] or 'frontmatter', n['message']) for n in report['notes'])
    if report['violations']:
        out.append('Total: %d hard, %d soft.' % (len(hard), len(soft)))
    else:
        out.append('Clean — no convention violations.')
    return '\n'.join(out)


# ----------------------------------------------------------------------------------------------
# CLI.

def whole_chars(s):
    """U+FFFD for half a surrogate pair: the half js_slice keeps when Atlas's cut (60, or 40 for a phase
    name) goes through an emoji."""
    return ''.join('\ufffd' if 0xD800 <= ord(c) <= 0xDFFF else c for c in s)


def read_text(path):
    try:
        with open(path, 'rb') as fh:
            return fh.read().decode('utf-8', errors='replace')
    except OSError as e:
        raise KitError('cannot read %s: %s' % (path, e))


def option(args, name, default=None, choices=None):
    if name in args:
        at = args.index(name)
        if at + 1 >= len(args):
            raise KitError('%s needs a value' % name)
        value = args[at + 1]
        del args[at:at + 2]
        if choices and value not in choices:
            raise KitError('%s must be one of %s' % (name, ', '.join(choices)))
        return value
    return default


def cmd_render(args):
    reg_path = option(args, '--registry')
    out = option(args, '--out')
    lang = option(args, '--lang', 'en', ('en', 'zh-TW'))
    register = option(args, '--register', 'audit', ('audit', 'clean'))
    if len(args) != 1:
        raise KitError('usage: flow_svg.py render <flow.md> [--registry P] [--out F.svg] [--lang en|zh-TW] [--register audit|clean]')
    reg = load_registry(reg_path)
    model = build(read_text(args[0]), reg, lang, register, args[0])
    svg = render_svg(model, reg)
    if out:
        with open(out, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(svg)
        sys.stderr.write('drew %d steps and %d lines into %s (flow-colours %s, %s register)\n'
                         % (len(model['block']['steps']), len(model['block']['flow']), out, reg['version'], register))
    else:
        sys.stdout.write(svg)
    return 0


def cmd_lint(args):
    as_json = '--json' in args
    if as_json:
        args.remove('--json')
    reg = load_registry(option(args, '--registry'))
    if len(args) != 1:
        raise KitError('usage: flow_svg.py lint <flow.md> [--json]')
    model = build(read_text(args[0]), reg, 'en', 'audit', args[0])
    report = lint_report(args[0], model)
    print(whole_chars(json.dumps(report, ensure_ascii=False, indent=2) if as_json else lint_text(report, model)))
    return report['exit']


def golden_diff(path, goldens):
    name = os.path.splitext(os.path.basename(path))[0]
    parsed, columns = atlas_view(read_text(path))
    out = {}
    for what, mine in (('parsed', parsed), ('columns', columns)):
        g = os.path.join(goldens, '%s.%s.json' % (name, what))
        if not os.path.exists(g):
            out[what] = 'no golden'
            continue
        with open(g, encoding='utf-8') as fh:
            want = json.load(fh)
        out[what] = 'match' if want == mine else first_difference(want, mine)
    return out, parsed


def first_difference(want, have, where='$'):
    if type(want) != type(have):
        return '%s: Atlas %r, kit %r' % (where, want, have)
    if isinstance(want, dict):
        for k in list(want) + [k for k in have if k not in want]:
            if k not in want or k not in have:
                return '%s.%s: only in %s' % (where, k, 'Atlas' if k in want else 'the kit')
            d = first_difference(want[k], have[k], '%s.%s' % (where, k))
            if d:
                return d
        return None
    if isinstance(want, list):
        for i in range(min(len(want), len(have))):
            d = first_difference(want[i], have[i], '%s[%d]' % (where, i))
            if d:
                return d
        if len(want) != len(have):
            return '%s: Atlas has %d items, the kit %d' % (where, len(want), len(have))
        return None
    return None if want == have else '%s: Atlas %r, kit %r' % (where, want, have)


def cmd_compare(args):
    goldens = option(args, '--goldens')
    if not goldens or not args:
        raise KitError('usage: flow_svg.py compare <flow.md>... --goldens <dir>')
    bad = 0
    total_steps = total_lines = 0
    for path in args:
        res, parsed = golden_diff(path, goldens)
        total_steps += len(parsed['block']['steps'])
        total_lines += len(parsed['block']['flow'])
        ok = res['parsed'] == 'match' and res['columns'] == 'match'
        bad += 0 if ok else 1
        print('%s %s: %d steps · %d lines · parse %s · layout %s' % (
            'ok  ' if ok else 'DIFF', os.path.basename(path), len(parsed['block']['steps']), len(parsed['block']['flow']),
            res['parsed'], res['columns']))
    print('%d file(s): %d steps · %d lines · %d differ from Atlas' % (len(args), total_steps, total_lines, bad))
    return 1 if bad else 0


# ----------------------------------------------------------------------------------------------
# Selftest.

BAD_FIXTURES = (('bad-v4.md', 'V4'), ('bad-v5.md', 'V5'), ('bad-v6.md', 'V6'), ('bad-v9.md', 'V9'),
                ('bad-v12.md', 'V12'), ('bad-v14.md', 'V14'), ('bad-overlap.md', 'overlap'))
CLEAN_FIXTURES = ('example-2.md', 'page-only-kinds.md')


def selftest():
    failures = []

    def check(cond, message):
        if not cond:
            failures.append(message)
        return cond

    reg = load_registry()
    # A fixture whose frontmatter is not valid YAML on purpose is a .txt: the workbench's ingest
    # reads every .md under skills/ as YAML and stops on the first it cannot parse.
    names = sorted(n for n in os.listdir(FIXTURES) if n.endswith(('.md', '.txt')))
    # 1. the parser and the layout against Atlas's own answers
    n_parse = ok_parse = n_layout = ok_layout = 0
    for name in names:
        path = os.path.join(FIXTURES, name)
        res, _ = golden_diff(path, FIXTURES)
        check(res['parsed'] != 'no golden' and res['columns'] != 'no golden', '%s has no golden files' % name)
        if res['parsed'] != 'no golden':
            n_parse += 1
            ok_parse += res['parsed'] == 'match'
            check(res['parsed'] == 'match', '%s parse: %s' % (name, res['parsed']))
        if res['columns'] != 'no golden':
            n_layout += 1
            ok_layout += res['columns'] == 'match'
            check(res['columns'] == 'match', '%s layout: %s' % (name, res['columns']))
    check(n_parse > 0, 'no fixtures with goldens')
    print('parse: %d/%d fixtures match Atlas' % (ok_parse, n_parse))
    print('layout: %d/%d fixtures match Atlas' % (ok_layout, n_layout))

    # 2. one bad fixture per lint rule fails with that rule, and the clean ones pass
    ok_bad = 0
    for name, rule in BAD_FIXTURES:
        path = os.path.join(FIXTURES, name)
        if not check(os.path.exists(path), 'missing fixture %s' % name):
            continue
        model = build(read_text(path), reg, 'en', 'audit', path)
        report = lint_report(path, model)
        rules = sorted(set(h['rule'] for h in report['violations']))
        good = report['exit'] == 1 and rule in rules
        ok_bad += good
        check(good, '%s: expected exit 1 with %s, got exit %d with %s' % (name, rule, report['exit'], rules))
    print('lint: %d/%d bad fixtures fail with their rule' % (ok_bad, len(BAD_FIXTURES)))
    for name in CLEAN_FIXTURES:
        path = os.path.join(FIXTURES, name)
        model = build(read_text(path), reg, 'en', 'audit', path)
        report = lint_report(path, model)
        check(report['exit'] == 0, '%s should lint clean: %s' % (name, [h['message'] for h in report['violations']]))
    print('lint: %s exit 0' % ' and '.join(CLEAN_FIXTURES))

    # 3. the page-only kinds: drawn in their row's fill, and a warning that Atlas would drop each one
    path = os.path.join(FIXTURES, 'page-only-kinds.md')
    model = build(read_text(path), reg, 'en', 'audit', path)
    svg = render_svg(model, reg)
    report = lint_report(path, model)
    drawn = 0
    for kind in PAGE_ONLY_KINDS:
        ids = [s['id'] for s in model['block']['steps'] if s['kind'] == kind]
        if not check(len(ids) == 1, 'page-only-kinds.md should hold one %s step' % kind):
            continue
        m = re.search('<g data-step="%s" data-kind="%s"><(?:path|circle)[^>]*fill="([^"]+)"' % (ids[0], kind), svg)
        good = bool(m) and m.group(1) == reg['_role'][kind]['fill']
        drawn += good
        check(good, '%s is not drawn in its role fill' % kind)
    warned = [w for w in report['warnings'] if w['code'] == 'page_only_kind']
    check(len(warned) == len(PAGE_ONLY_KINDS), 'expected %d page-only warnings, got %d' % (len(PAGE_ONLY_KINDS), len(warned)))
    atlas_parsed, _ = atlas_view(read_text(path))
    dropped = [w for w in atlas_parsed['block']['warnings'] if w['code'] == 'step_kind_unknown']
    check(len(dropped) == len(PAGE_ONLY_KINDS), 'Atlas should drop the %d page-only steps' % len(PAGE_ONLY_KINDS))
    print('page-only: %d/%d kinds drawn in their fill, %d warnings, Atlas drops %d' % (
        drawn, len(PAGE_ONLY_KINDS), len(warned), len(dropped)))

    # 4. one deterministic, self-contained SVG, stamped with the registry's version
    path = os.path.join(FIXTURES, 'example-2.md')
    text = read_text(path)
    for register in ('audit', 'clean'):
        for lang in ('en', 'zh-TW'):
            a = render_svg(build(text, reg, lang, register, path), reg)
            b = render_svg(build(text, reg, lang, register, path), reg)
            check(a == b, 'example-2 (%s, %s) renders differently twice' % (register, lang))
            check('var(--' not in a and '<style' not in a and '@import' not in a and 'href=' not in a
                  and 'prefers-color-scheme' not in a, 'example-2 (%s, %s) is not self-contained' % (register, lang))
            check('data-flow-colours="%s"' % reg['version'] in a, 'example-2 SVG is not stamped with the registry version')
            urls = re.findall('https?://[^"\\s]+', a)
            check(urls == ['http://www.w3.org/2000/svg'], 'example-2 SVG names an outside address: %s' % urls)
            painted = set(c.upper() for c in re.findall('#[0-9A-Fa-f]{6}', a))
            check(painted <= registry_colours(reg), 'example-2 paints colours the registry does not hold: %s'
                  % sorted(painted - registry_colours(reg)))
            check(not (painted & set(c.upper() for c in reg['avoid'])), 'example-2 paints an avoided colour')
    print('render: deterministic, self-contained, stamped flow-colours %s' % reg['version'])

    # 5. every fixture renders in both registers. Both keep every step's number on its tab (a drawing
    # and its document match by step number alone); clean shows only the labels on the branches out
    # of a gate or a junction.
    numbered = kept = 0
    for name in names:
        path = os.path.join(FIXTURES, name)
        for register in ('audit', 'clean'):
            try:
                model = build(read_text(path), reg, 'en', register, path)
                svg = render_svg(model, reg)
            except Exception as e:  # noqa: BLE001 - a crash is a failure, whatever it is
                check(False, '%s (%s) does not render: %r' % (name, register, e))
                continue
            for s in model['block']['steps']:
                number = split_number(s['title'])[0]
                if not number:
                    continue
                numbered += 1
                group = re.search('<g data-step="%s" [^>]*>(.*?)</g>' % re.escape(esc(s['id'])), svg)
                good = bool(group) and ('data-number="%s">%s</text>' % (esc(number), esc(number))) in group.group(1)
                kept += good
                check(good, '%s (%s): step %s does not show its number %s' % (name, register, s['id'], number))
            branch = [e for e in model['block']['flow'] if e['role'] == 'spine' and e['label']
                      and model['nodes'][e['from']]['kind'] in ('gate', 'junction')]
            for e in branch:
                check(any(lab['edge'] is e for lab in model['labels']),
                      '%s (%s): the branch %s -> %s lost its label' % (name, register, e['from'], e['to']))
            if register == 'clean':
                for lab in model['labels']:
                    check(any(lab['edge'] is e for e in branch), '%s (clean): the label on %s %s %s should be left off'
                          % (name, lab['edge']['from'], '->' if lab['edge']['role'] == 'spine' else '~>', lab['edge']['to']))
    print('render: %d fixtures draw in both registers; %d/%d numbered steps keep their number in each'
          % (len(names), kept, numbered))

    # 6. JavaScript string rules the parser depends on
    lf = '---\nsteps:\n  - "a | start | A"\n  - "b | end | B"\nflow:\n  - "a -> b"\n---\n'
    check(atlas_view(lf.replace('\n', '\r\n')) == atlas_view(lf), 'CRLF parses differently from LF')
    check(js_slice('ab\U0001F600', 3) == 'ab\ud83d', 'js_slice must keep the high half of a cut pair')
    check(js_trim('\ufeff x \x1c') == 'x \x1c', 'js_trim must follow JavaScript’s whitespace')

    # 7. what the two reviews of SKB-144 fixed, one sentence of validation.md or scaffold.md each
    def text_of(steps, lines, head=''):
        return head + '---\nexecuted_by: internal-user\nsteps:\n%s\nflow:\n%s\n---\n' % (
            '\n'.join('  - "%s"' % s for s in steps), '\n'.join('  - "%s"' % x for x in lines))

    def model_of(steps, lines, register='audit', head=''):
        return build(text_of(steps, lines, head), reg, 'en', register, 'inline')

    def exit_of(text, crash=False):
        """main's exit for `lint` on `text`, its stdout as strict as a real one's; crash: cmd_lint raises."""
        import io
        import tempfile
        fd, path = tempfile.mkstemp(suffix='.md')
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        saved = sys.stdout, sys.stderr, globals()['cmd_lint']
        sys.stdout, sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding='utf-8'), io.StringIO()
        if crash:
            globals()['cmd_lint'] = lambda args: 1 // 0
        try:
            return main(['flow_svg.py', 'lint', path])
        except Exception as e:
            return type(e).__name__
        finally:
            sys.stdout, sys.stderr, globals()['cmd_lint'] = saved
            os.remove(path)

    def found(steps, lines, severity=None, head=''):
        report = lint_report('inline', model_of(steps, lines, head=head))
        return [h for h in report['violations'] if severity in (None, h['severity'])]

    st, en = 'start | start | Start', 'end | end | End'
    ai = ['draft | llm | 1 Draft', 'send | output | 2 Send', 'fix | hitl | 3 Fix']
    v14 = os.path.join(FIXTURES, 'bad-v14.md')
    fork = model_of([st, 'j | junction | Fork', 'a | deterministic | 1 A', 'b | deterministic | 2 B', en],
                    ['start -> j', 'j -> a | Path A', 'j -> b | Path B', 'a -> end', 'b -> end'], 'clean')
    review = [
        ('V5: a label on an AI step\'s only line out is no error path, and V5 is soft',
         [h['rule'] for h in found([st] + ai[:2] + [en], ['start -> draft', 'draft -> send | Ready', 'send -> end'],
                                   'soft')] == ['V5']),
        ('V5: a labelled branch beside the main line is an error path',
         not [h for h in found([st] + ai + [en], ['start -> draft', 'draft -> send', 'draft -> fix | Error',
                                                  'send -> end', 'fix -> end']) if h['rule'] == 'V5']),
        ('V5: a line back to an earlier step is an error path',
         not found([st, 'prep | deterministic | 1 Prep', 'draft | llm | 2 Draft', 'send | output | 3 Send', en],
                   ['start -> prep', 'prep -> draft', 'draft -> prep', 'draft -> send', 'send -> end'])),
        ('V9 and V12 are soft', RULES['V9'][0] == RULES['V12'][0] == 'soft'),
        ('V14 counts columns as col= does, from 0',
         [h['message'] for h in lint_report(v14, build(read_text(v14), reg, 'en', 'audit', v14))['violations']
          if h['rule'] == 'V14'] == ['col=3 holds 4 steps']),
        ('a header above the --- is named as the cause',
         any('does not open with a --- line' in h['message']
             for h in found([st, en], ['start -> end'], head='# A workflow\n\n```markdown\n'))),
        ('a title Atlas cuts at 60 characters is named',
         any('Atlas keeps the first 60' in h['message']
             for h in found([st, 'w | deterministic | 1 ' + 'w' * 70, en], ['start -> w', 'w -> end']))),
        ('a step number has no letter suffix, and a range is one number',
         split_number('10x faster review') == (None, '10x faster review')
         and split_number('2.3–2.6 Footprint check') == ('2.3–2.6', 'Footprint check')),
        ('the clean register keeps a fork\'s branch labels',
         sorted(lab['edge']['label'] for lab in fork['labels']) == ['Path A', 'Path B']),
    ]
    # the second review; half_text puts half an emoji where Atlas cuts a phase name (40) and a title (60)
    half_text = text_of(['## ' + 'p' * 39 + '\U0001F600 phase', st, 'w | deterministic | 1 ' + 'x' * 57 + '\U0001F600 y',
                         en], ['start -> w', 'w -> end'])
    half = build(half_text, reg, 'en', 'audit', 'inline')
    dots = model_of([st, en], ['start -> end', 'start => end...'])
    review += [
        ('V5: every path out of an AI step passes a check',
         [h['message'] for h in found([st, 'draft | llm | 1 Draft', 'check | gate | 2 Check', 'send | output | 3 Send',
                                       'post | output | 4 Post', en],
                                      ['start -> draft', 'draft -> check', 'draft -> post', 'check -> send | OK',
                                       'check -> end | No', 'send -> end', 'post -> end']) if h['rule'] == 'V5']
         == ['an AI step whose result reaches post with no gate or person checking it on the way, and with no error '
             'or retry line']),
        ('V5: a step whose every line out is labelled sorts its result, and each path needs its check',
         [h['rule'] for h in found([st, 'sort | llm | 1 Sort', 'a | output | 2 Billing reply',
                                    'b | output | 3 Tech reply', en],
                                   ['start -> sort', 'sort -> a | Billing', 'sort -> b | Tech', 'a -> end',
                                    'b -> end'])] == ['V5']),
        ('V5: a labelled branch beside the main line is an error path, also when it ends in a notice',
         not [h for h in found([st, 'decide | llm | 1 Decide', 'check | gate | 2 Check', 'fail | output | Failure mail',
                                'done | output | 3 Done', en],
                               ['start -> decide', 'decide -> check', 'decide -> fail | Gave up', 'check -> done | OK',
                                'check -> end | No', 'fail -> end', 'done -> end']) if h['rule'] == 'V5']),
        ('a phase name Atlas cuts at 40 characters is named',
         any('Atlas keeps the first 40' in h['message'] for h in lint_model(half)[0])),
        ('half a character at the cut reaches no output: lint exits 1, its findings', exit_of(half_text) == 1),
        ('a crash exits 2, never lint\'s 1', exit_of(half_text, crash=True) == 2),
        ('a report line keeps the full stops the file wrote',
         'start => end... Fix:' in lint_text(lint_report('inline', dots), dots)),
    ]
    for what, good in review:
        check(good, 'review: ' + what)
    print('review: %d/%d checks hold (V5 per path, severity, col=, header, cuts, numbers, fork labels, '
          'half characters, exit 2, full stops)' % (sum(1 for _, good in review if good), len(review)))

    if failures:
        print('selftest FAILED:')
        for m in failures:
            print('  - ' + m)
        return 1
    print('selftest passed')
    return 0


def registry_colours(reg):
    out = set()

    def gather(v):
        if isinstance(v, dict):
            for k in v:
                if not k.startswith('_'):
                    gather(v[k])
        elif isinstance(v, list):
            for x in v:
                gather(x)
        elif isinstance(v, str) and COLOUR_RE.match(v):
            out.add(v.upper())
    gather(reg)
    return out


def main(argv):
    args = list(argv[1:])
    try:
        if args == ['--selftest']:
            return selftest()
        if not args:
            raise KitError('usage: flow_svg.py render|lint|compare ... | --selftest (see the docstring)')
        cmd = args.pop(0)
        if cmd == 'render':
            return cmd_render(args)
        if cmd == 'lint':
            return cmd_lint(args)
        if cmd == 'compare':
            return cmd_compare(args)
        raise KitError('unknown command %r: use render, lint, compare or --selftest' % cmd)
    except KitError as e:
        sys.stderr.write('flow_svg: %s\n' % e)
        return 2
    except Exception:
        # exit 1 means lint found something, so a crash must not end with it
        traceback.print_exc()
        sys.stderr.write('flow_svg: the kit stopped on an error it does not expect (above)\n')
        return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
