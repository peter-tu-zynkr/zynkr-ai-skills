#!/usr/bin/env node
/**
 * kb-drive-mirror.mjs — v2 (ATL-114): render the 知識庫, read from Zynkr Atlas, to local files for
 * the Drive mirror.
 *
 * Zynkr Atlas holds the 知識庫: its published collection `kb`, one collection per section under it
 * (`kb.<slug>`), the cards filed in those. This script only READS it, through Atlas's MCP endpoint
 * with an export token (one minted with 「可以匯出知識（給鏡像用）」), and writes into --out one
 * Markdown file per section, `00-index.md`, the restore copy `_KB-SNAPSHOT.json` and
 * `_MANIFEST.json`. It never uploads: /zynkr-kms does that with the google-workspace MCP, so the
 * mirror flows Atlas → Drive, one way. (v1 read the CRM's tables with a service-role key; it is in
 * git history.)
 *
 * Usage:
 *   node kb-drive-mirror.mjs --out <dir> [--full] [--env <file>]
 *   node kb-drive-mirror.mjs pending-add  --out <dir> --key <key> --collection <key> --title <title> [--thread <id>]
 *   node kb-drive-mirror.mjs pending-drop --out <dir> --key <key>
 *
 * --out holds Drive's _MANIFEST.json and _KB-SNAPSHOT.json, which /zynkr-kms downloads over the
 * local copies at the start of every run: Drive's pair is the record. Without --full the run is
 * incremental: it lists the collection, exports the notes whose updated_at moved (and the root `kb`,
 * which the listing never names), and carries every other note's body from the previous snapshot
 * after hashing it again. With no v2 pair there — none at all, a v1 file in it, or a pair from two
 * different runs (an upload that stopped half-way) — it runs in full: one export of the whole
 * collection. One file without the other, or a file that does not parse, stops it.
 *
 * The token: ATLAS_MCP_TOKEN from the environment, else from the env file (--env, or
 * ~/.config/zynkr/kb-mirror.env). It is never printed, never logged and never put on a command
 * line, and it is sent only to atlas.zynkr.ai (or a loopback address, for a local copy of Atlas,
 * never through a proxy). Unset, malformed or refused, the run exits 1 having rewritten nothing:
 * every call and every check happens before the first file is written, and the manifest is written
 * last. Every line it writes to stderr passes a net that masks anything shaped like a token. The JSON
 * summary on stdout is data /zynkr-kms reads, and a note key may start `zatl_`, so only the token
 * itself is taken out of it.
 *
 * pending-add / pending-drop edit _MANIFEST.json's pending[] (the drafts /zynkr-kms filed) and call
 * nothing. A draft stays in pending[] until pending-drop takes it out: once list_knowledge lists it,
 * every run names it in pending_published, so /zynkr-kms labels its thread, then drops it.
 *
 * Prints a JSON summary to stdout (counts, keys, the files to upload); progress goes to stderr.
 * Exit 0 written · 1 refused (nothing rewritten) or a write failed (upload nothing: the next run
 * starts again from Drive's pair) · 2 bad arguments.
 */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, realpathSync, renameSync, statSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const DEFAULT_URL = 'https://atlas.zynkr.ai/api/mcp'
const ATLAS_HOST = 'atlas.zynkr.ai'
export const ROOT = 'kb'
export const FORMAT = 'atlas-kb/2'
const KEY = '[a-z0-9][a-z0-9._-]{1,63}'
const KEY_RE = new RegExp(`^${KEY}$`)
const TOKEN_RE = /^zatl_[A-Za-z0-9_-]{20,128}$/
const PROTOCOL = '2025-06-18'
const PACE_MS = 1200 // at most 50 calls a minute: each tool call costs two of the 120-per-60 s window
const BACKOFF_MS = 60_000
const EXPORT_KEYS_MAX = 100
const LIST_MAX_CHARS = 60_000
const EXPORT_MAX_CHARS = 300_000
const MAX_PAGES = 100
const DOC_PREFIX = 'Zynkr Support KB'
const INDEX_TITLE = `${DOC_PREFIX} — 00 INDEX & Retrieval Map`
const KIND_ORDER = ['fact', 'policy', 'reference', 'collection']

/** A refusal or failure: the run stops, and nothing is rewritten. */
export class Stop extends Error {
  constructor(message, code = 1) { super(message); this.code = code }
}

export const sha256 = (s) => createHash('sha256').update(s, 'utf8').digest('hex')
/** Control characters, U+2028 and U+2029 — built from code points, so no source line holds one (or an escape that turns into one). */
const BREAKS = new RegExp(`[${String.fromCharCode(0)}-${String.fromCharCode(0x1f)}${String.fromCharCode(0x7f)}-${String.fromCharCode(0x9f)}${String.fromCharCode(0x2028, 0x2029)}]+`, 'g')
const oneLine = (s, n = 300) => String(s ?? '').replace(BREAKS, ' ').trim().slice(0, n)
const pad2 = (n) => String(n).padStart(2, '0')
const stampOf = (d) => d.toISOString().replace(/\.\d{3}Z$/, 'Z')
const byKey = (a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0)
const redact = (s, token) => String(s ?? '').split(token).join('[REDACTED]')
/** Anything shaped like an Atlas token, in any case: the net under every line this script prints. */
const scrub = (s) => String(s ?? '').replace(/zatl_[a-z0-9_-]+/gi, 'zatl_[REDACTED]')

// --- the token and where it may go ---------------------------------------------------------------

/** ATLAS_MCP_TOKEN from the environment, else from the env file. Its value is never in a message. */
export function loadToken(env, envFile) {
  let token = env.ATLAS_MCP_TOKEN || ''
  let from = 'the environment'
  let warning = null
  if (!token && envFile && existsSync(envFile)) {
    let text
    try {
      text = readFileSync(envFile, 'utf8')
      if (statSync(envFile).mode & 0o077) warning = `${envFile} can be read by other accounts on this Mac — run chmod 600 on it`
    } catch {
      throw new Stop(`could not read ${envFile}. Nothing was called or rewritten.`)
    }
    for (const line of text.split(/\r?\n/)) {
      const m = line.match(/^\s*(?:export\s+)?ATLAS_MCP_TOKEN\s*=\s*(.*?)\s*$/)
      if (m) token = m[1].replace(/^(["'])(.*)\1$/, '$2')
    }
    from = envFile
  }
  if (!token) {
    // A path is named only when the file is there: a token passed to --env by mistake is never echoed.
    const where = envFile && existsSync(envFile) ? `${envFile} has no ATLAS_MCP_TOKEN= line` : 'no env file was found'
    throw new Stop(`ATLAS_MCP_TOKEN is not set (${where}): export it, or put ATLAS_MCP_TOKEN=… in ~/.config/zynkr/kb-mirror.env or the file --env names (chmod 600). Nothing was called or rewritten.`)
  }
  // Checked before it goes in a header: a value fetch refuses would be quoted in fetch's own error.
  if (!TOKEN_RE.test(token)) {
    throw new Stop(`ATLAS_MCP_TOKEN (from ${from}) is not an Atlas token, zatl_ and 43 characters; its value is not printed. Nothing was called or rewritten.`)
  }
  return { token, from, warning }
}

/** The token goes only to Atlas itself, or to a loopback address (a local copy of Atlas). */
export function checkUrl(raw, env = {}, execArgv = []) {
  let u
  try { u = new URL(raw) } catch { throw new Stop('--url is not a URL', 2) }
  const loopback = ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname)
  const atlas = u.protocol === 'https:' && u.hostname === ATLAS_HOST && u.port === ''
  if (!atlas && !(loopback && (u.protocol === 'http:' || u.protocol === 'https:'))) {
    throw new Stop(`refusing to send the token to ${u.host || raw}: only https://${ATLAS_HOST} or a loopback address`, 2)
  }
  if (u.username || u.password) throw new Stop('--url carries a user name or password', 2)
  // Once Node's environment proxy is on, even a loopback request goes through the proxy, and plain
  // http in the clear: a local copy of Atlas is reached directly or not at all. Atlas itself is
  // reached through a CONNECT tunnel, so a proxy sees only the host.
  const flag = /(^|\s)--use-env-proxy(=\S*)?(\s|$)/
  const switched = !/^(|0|false)$/i.test(String(env.NODE_USE_ENV_PROXY ?? '')) || flag.test(String(env.NODE_OPTIONS ?? '')) || execArgv.some((a) => flag.test(a))
  if (loopback && switched && ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy'].some((k) => env[k])) {
    throw new Stop('refusing to send the token to a loopback address through a proxy: unset HTTP_PROXY / HTTPS_PROXY (or NODE_USE_ENV_PROXY) for this run. Nothing was called or rewritten.')
  }
  if (u.protocol === 'https:' && env.NODE_TLS_REJECT_UNAUTHORIZED === '0') {
    throw new Stop('refusing to send the token with TLS checks off (NODE_TLS_REJECT_UNAUTHORIZED=0). Nothing was called or rewritten.')
  }
  return u
}

// --- one JSON-RPC client, stateless, paced ---------------------------------------------------------

/** Every `data:` payload of a text/event-stream body, parsed. */
export function parseSse(raw) {
  const out = []
  for (const block of raw.split(/\r?\n\r?\n/)) {
    const data = block.split(/\r?\n/).filter((l) => l.startsWith('data:')).map((l) => l.slice(5).replace(/^ /, ''))
    if (!data.length) continue
    try { out.push(JSON.parse(data.join('\n'))) } catch { throw new Stop('Atlas sent an event that is not JSON') }
  }
  return out
}

/**
 * Atlas's route builds a fresh MCP server for every POST, so each request stands alone: one
 * `initialize` per run, then `tools/list` and the tool calls. Every POST waits out the pace first. A
 * rate_limited answer (HTTP 429, or the tool's own) backs off once per run, then the run stops.
 */
export function createClient({ url, token, fetchImpl, sleep, clock, pace, backoff, log }) {
  let id = 0
  let calls = 0
  let lastAt = -Infinity
  let backedOff = false
  let protocol = null
  const clean = (s) => oneLine(redact(s, token), 240)

  async function rateLimited(what) {
    if (backedOff) throw new Stop(`rate_limited again on ${what} after backing off once. Nothing was rewritten; run it again in a few minutes.`)
    backedOff = true
    log(`rate_limited on ${what}: backing off ${Math.round(backoff / 1000)} s, once`)
    await sleep(backoff)
    lastAt = clock()
  }

  async function read(res, reqId) {
    const type = (res.headers.get('content-type') ?? '').split(';')[0].trim().toLowerCase()
    const raw = await res.text()
    let messages
    if (type === 'text/event-stream') messages = parseSse(raw)
    else if (type === 'application/json') {
      try { messages = [JSON.parse(raw)].flat() } catch { throw new Stop('Atlas answered JSON that does not parse') }
    } else throw new Stop(`Atlas answered ${oneLine(scrub(type), 60) || 'with no content type'}, not JSON or an event stream`)
    const m = messages.find((x) => x && x.id === reqId && (x.result !== undefined || x.error !== undefined))
    if (!m) throw new Stop(`Atlas sent no answer to request ${reqId}`)
    return m
  }

  async function post(method, params) {
    const what = method === 'tools/call' ? params.name : method
    for (;;) {
      // Checked again after each sleep: a timer may fire a little early.
      for (let wait = lastAt + pace - clock(); wait > 0; wait = lastAt + pace - clock()) await sleep(wait)
      lastAt = clock()
      calls++
      const reqId = ++id
      const headers = {
        authorization: `Bearer ${token}`,
        'content-type': 'application/json',
        accept: 'application/json, text/event-stream',
        'user-agent': 'zynkr-kms-mirror/2',
      }
      if (protocol) headers['mcp-protocol-version'] = protocol
      let res
      try {
        res = await fetchImpl(url, {
          method: 'POST',
          headers,
          body: JSON.stringify({ jsonrpc: '2.0', id: reqId, method, params }),
          redirect: 'error', // a redirect could carry the Authorization header to another host
          signal: AbortSignal.timeout(60_000),
        })
      } catch (e) {
        throw new Stop(`could not reach Atlas during ${what} (${clean(e?.cause?.code ?? e?.name ?? 'network error')}). Nothing was rewritten.`)
      }
      if (res.status === 429) { await rateLimited(what); continue }
      if (res.status === 401) {
        throw new Stop('Atlas refused ATLAS_MCP_TOKEN (401): it is unknown, revoked or expired, or its holder is no longer a member — the owner mints a new one. Nothing was rewritten.')
      }
      if (!res.ok) throw new Stop(`Atlas answered HTTP ${res.status} to ${what}. Nothing was rewritten.`)
      const msg = await read(res, reqId)
      if (msg.error) {
        const code = Number(msg.error.code)
        const hint = what === 'export_knowledge' && code === -32602 ? ' — this token cannot export: mint one with 「可以匯出知識（給鏡像用）」' : ''
        throw new Stop(`JSON-RPC error ${code} on ${what}: ${clean(msg.error.message)}${hint}. Nothing was rewritten.`)
      }
      const result = msg.result
      if (method === 'tools/call' && result?.isError) {
        const first = clean(String(result.content?.find?.((c) => c?.type === 'text')?.text ?? '').split('\n')[0]).replace(/[.。]$/, '')
        if (first.startsWith('rate_limited')) { await rateLimited(what); continue }
        throw new Stop(`${what} refused: ${first || 'an error with no text'}. Nothing was rewritten.`)
      }
      return result
    }
  }

  return {
    async initialize() {
      const r = await post('initialize', { protocolVersion: PROTOCOL, capabilities: {}, clientInfo: { name: 'zynkr-kms-mirror', version: '2.0.0' } })
      protocol = typeof r?.protocolVersion === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(r.protocolVersion) ? r.protocolVersion : PROTOCOL
      return r
    },
    async tools() {
      const names = []
      let cursor
      for (let page = 0; page < 5; page++) {
        const r = await post('tools/list', cursor ? { cursor } : {})
        for (const t of Array.isArray(r?.tools) ? r.tools : []) if (typeof t?.name === 'string') names.push(t.name)
        cursor = typeof r?.nextCursor === 'string' && r.nextCursor ? r.nextCursor : null
        if (!cursor) break
      }
      return names
    },
    call: (name, args) => post('tools/call', { name, arguments: args }),
    get calls() { return calls },
    get backedOff() { return backedOff },
  }
}

// --- reading the 知識庫 -------------------------------------------------------------------------

function listedRow(n) {
  if (!n || typeof n.key !== 'string' || !KEY_RE.test(n.key)) throw new Stop('list_knowledge listed a row without a valid key')
  if (n.key.startsWith('company.')) {
    throw new Stop(`list_knowledge listed the company fact ${n.key} under ${ROOT}: a company fact is never mirrored. Nothing was rewritten — tell the owner.`)
  }
  return {
    key: n.key,
    kind: typeof n.kind === 'string' ? n.kind : 'unknown',
    title: typeof n.title === 'string' ? n.title : '',
    part_of: typeof n.part_of === 'string' && KEY_RE.test(n.part_of) ? n.part_of : null,
    cites: Array.isArray(n.cites) ? n.cites.filter((k) => typeof k === 'string' && KEY_RE.test(k)) : [],
    ...(n.cites_truncated === true ? { cites_truncated: true } : {}),
    updated_at: typeof n.updated_at === 'string' ? n.updated_at : null,
    last_verified_at: typeof n.last_verified_at === 'string' ? n.last_verified_at : null,
    verify_interval_days: Number.isInteger(n.verify_interval_days) ? n.verify_interval_days : null,
  }
}

/** Every published note under the root, by key, without text: list_knowledge paged to its end. */
export async function listAll(c) {
  const rows = new Map()
  let after = null
  let pages = 0
  for (;;) {
    if (++pages > MAX_PAGES) throw new Stop(`list_knowledge did not finish in ${MAX_PAGES} pages. Nothing was rewritten.`)
    const r = await c.call('list_knowledge', { collection: ROOT, limit: 500, max_chars: LIST_MAX_CHARS, ...(after ? { after } : {}) })
    const s = r?.structuredContent
    if (!s || !Array.isArray(s.notes) || typeof s.truncated !== 'boolean') {
      throw new Stop('list_knowledge answered without its structured listing. Nothing was rewritten.')
    }
    if (s.depth_limited === true) {
      throw new Stop(`notes lie deeper under ${ROOT} than list_knowledge walks (depth_limited): the mirror cannot copy them. Nothing was rewritten — tell the owner.`)
    }
    for (const n of s.notes) {
      const row = listedRow(n)
      if (rows.has(row.key)) throw new Stop(`list_knowledge listed ${row.key} twice. Nothing was rewritten.`)
      rows.set(row.key, row)
    }
    if (!s.truncated) break
    // next_after is the page's last key shown: anything else would skip notes or loop.
    const last = s.notes.at(-1)?.key
    if (!last || s.next_after !== last || s.next_after === after) throw new Stop('list_knowledge paged without moving forward. Nothing was rewritten.')
    after = s.next_after
  }
  return { rows, pages }
}

const HEADER_RE = new RegExp(
  `^Exported (${KEY}) · (\\d+) notes · next_after: (\\(none\\)|${KEY}) · truncated: (true|false) · depth_limited: (true|false) · missing: (\\(none\\)|${KEY}(?:, ${KEY})*)$`,
)

function exportedNote(line, i) {
  let n
  try { n = JSON.parse(line) } catch { throw new Stop(`export line ${i + 1} is not JSON. Nothing was rewritten.`) }
  if (!n || typeof n.key !== 'string' || !KEY_RE.test(n.key)) throw new Stop(`export line ${i + 1} has no valid key. Nothing was rewritten.`)
  if (n.key.startsWith('company.')) throw new Stop(`export_knowledge copied the company fact ${n.key}: never mirrored. Nothing was rewritten — tell the owner.`)
  if (typeof n.body_md !== 'string' || typeof n.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(n.sha256)) {
    throw new Stop(`export line ${i + 1} (${n.key}) has no body or sha256. Nothing was rewritten.`)
  }
  // Hashed again over the body's UTF-8 bytes, as Atlas does: a body that changed on the way stops the run.
  if (sha256(n.body_md) !== n.sha256) throw new Stop(`${n.key}'s body does not match the sha256 Atlas served. Nothing was rewritten.`)
  return {
    key: n.key,
    kind: typeof n.kind === 'string' ? n.kind : 'unknown',
    title: typeof n.title === 'string' ? n.title : '',
    part_of: typeof n.part_of === 'string' && KEY_RE.test(n.part_of) ? n.part_of : null,
    body_md: n.body_md,
    sha256: n.sha256,
    updated_at: typeof n.updated_at === 'string' ? n.updated_at : null,
    last_verified_at: typeof n.last_verified_at === 'string' ? n.last_verified_at : null,
    verify_interval_days: Number.isInteger(n.verify_interval_days) ? n.verify_interval_days : null,
  }
}

/**
 * One export_knowledge answer: the pinned header line (Atlas `src/lib/mcp/shape.ts` exportHeader —
 * change both, or neither), then one fenced block of JSON lines, one note per line.
 */
export function parseExport(text) {
  const lines = String(text).split('\n')
  const h = HEADER_RE.exec(lines[0] ?? '')
  if (!h) throw new Stop('export_knowledge answered with a header this mirror does not read (its format is pinned in Atlas). Nothing was rewritten.')
  const open = lines.findIndex((l, i) => i > 0 && /^`{3,}jsonl$/.test(l))
  if (open < 0) throw new Stop('export_knowledge answered without its JSON-lines block. Nothing was rewritten.')
  const fence = lines[open].slice(0, -'jsonl'.length)
  const close = lines.indexOf(fence, open + 1)
  if (close < 0) throw new Stop('export_knowledge answer was cut off (no closing fence). Nothing was rewritten.')
  const notes = lines.slice(open + 1, close).map(exportedNote)
  if (notes.length !== Number(h[2])) throw new Stop(`export_knowledge said ${h[2]} notes and held ${notes.length}. Nothing was rewritten.`)
  return {
    collection: h[1],
    notes,
    next_after: h[3] === '(none)' ? null : h[3],
    truncated: h[4] === 'true',
    depth_limited: h[5] === 'true',
    missing: h[6] === '(none)' ? [] : h[6].split(', '),
  }
}

/** Whole notes with their bodies: the collection (keys null), or those keys, ≤100 a call, paged. */
export async function exportNotes(c, keys) {
  const got = new Map()
  let pages = 0
  const batches = keys === null ? [null] : Array.from({ length: Math.ceil(keys.length / EXPORT_KEYS_MAX) }, (_, i) => keys.slice(i * EXPORT_KEYS_MAX, (i + 1) * EXPORT_KEYS_MAX))
  for (const batch of batches) {
    let after = null
    for (;;) {
      if (++pages > MAX_PAGES) throw new Stop(`export_knowledge did not finish in ${MAX_PAGES} pages. Nothing was rewritten.`)
      const r = await c.call('export_knowledge', { collection: ROOT, max_chars: EXPORT_MAX_CHARS, ...(batch ? { keys: batch } : {}), ...(after ? { after } : {}) })
      const text = r?.content?.find?.((x) => x?.type === 'text')?.text
      if (typeof text !== 'string') throw new Stop('export_knowledge answered without text. Nothing was rewritten.')
      const page = parseExport(text)
      if (page.collection !== ROOT) throw new Stop(`export_knowledge copied ${page.collection}, not ${ROOT}. Nothing was rewritten.`)
      if (page.depth_limited) {
        throw new Stop(`notes lie deeper under ${ROOT} than export_knowledge copies (depth_limited). Nothing was rewritten — tell the owner.`)
      }
      if (page.missing.length) {
        throw new Stop(`export_knowledge did not copy ${page.missing.length} listed note(s) (${page.missing.slice(0, 5).join(', ')}): the 知識庫 changed during the run. Nothing was rewritten — run it again.`)
      }
      for (const n of page.notes) {
        if (got.has(n.key)) throw new Stop(`export_knowledge copied ${n.key} twice. Nothing was rewritten.`)
        if (batch && !batch.includes(n.key)) throw new Stop(`export_knowledge copied ${n.key}, which was not asked for. Nothing was rewritten.`)
        got.set(n.key, n)
      }
      if (!page.truncated) break
      const last = page.notes.at(-1)?.key
      if (!last || page.next_after !== last || page.next_after === after) throw new Stop('export_knowledge paged without moving forward. Nothing was rewritten.')
      after = page.next_after
    }
  }
  return { notes: got, pages }
}

// --- the previous run, read from --out ------------------------------------------------------------

function readJson(file) {
  if (!existsSync(file)) return null
  try { return JSON.parse(readFileSync(file, 'utf8')) } catch { return undefined }
}

/** The previous manifest and snapshot, and whether an incremental run can build on them. */
export function previousRun(out) {
  const manifest = readJson(join(out, '_MANIFEST.json'))
  const snapshot = readJson(join(out, '_KB-SNAPSHOT.json'))
  // Both are downloaded from Drive at the start of every run, so a file that does not parse, or one
  // without the other, is a download that went wrong. A run on it would forget pending[] and the
  // section numbers, or the record of removed notes, and upload that over Drive's.
  for (const [name, x] of [['_MANIFEST.json', manifest], ['_KB-SNAPSHOT.json', snapshot]]) {
    if (x === undefined) throw new Stop(`${name} in --out does not parse: download it again from Drive. Nothing was called or rewritten.`)
  }
  if (!manifest !== !snapshot) {
    throw new Stop(`--out holds ${manifest ? '_MANIFEST.json but no _KB-SNAPSHOT.json' : '_KB-SNAPSHOT.json but no _MANIFEST.json'}: download both from Drive first. Nothing was called or rewritten.`)
  }
  const v2 = (x) => Boolean(x && typeof x === 'object' && x.format === FORMAT)
  const manifestV2 = v2(manifest)
  const snapshotV2 = v2(snapshot) && Array.isArray(snapshot.notes)
  // A v1 file beside a v2 one is the first v2 upload, stopped between the two — or stopped sooner,
  // and then Step 6 uploaded the manifest alone. A v1 file holds nothing a v2 run builds on but the
  // manifest's section numbers and pending[], which a full run keeps.
  let reason = null
  if (!manifest) reason = 'no previous _MANIFEST.json in --out'
  else if (!manifestV2) reason = 'the previous _MANIFEST.json is v1 (the CRM era)'
  else if (!snapshotV2) reason = 'the previous _KB-SNAPSHOT.json is v1 (the CRM era)'
  // Written by different runs: an upload stopped between the two, so Drive's Docs may be older than
  // either says. A full run renders and uploads every Doc again.
  else if (manifest.mirrored_at !== snapshot.mirrored_at) reason = 'the previous _MANIFEST.json and _KB-SNAPSHOT.json are from different runs (an upload stopped half-way)'
  return { manifest: manifest || null, manifestV2, snapshot: snapshotV2 ? snapshot : null, reason }
}

/** A note's body carried from the previous snapshot — only if it is whole and its updated_at stands. */
function carried(prev, row) {
  const m = prev.manifest?.notes?.[row.key]
  const s = prev.byKey?.get(row.key)
  if (!m || !s || m.updated_at == null || m.updated_at !== row.updated_at) return null
  if (typeof s.body_md !== 'string' || s.sha256 !== m.sha256 || sha256(s.body_md) !== s.sha256) return null
  return { body_md: s.body_md, sha256: s.sha256, updated_at: m.updated_at }
}

// --- the shape of the copy -----------------------------------------------------------------------

/** Sections (collections filed under the root), each section's cards, and the cards in none. */
export function layout(notes) {
  const by = new Map(notes.map((n) => [n.key, n]))
  const sections = notes.filter((n) => n.kind === 'collection' && n.part_of === ROOT)
  const sectionKeys = new Set(sections.map((s) => s.key))
  const sectionOf = (key, depth = 0) => {
    const n = by.get(key)
    if (!n || depth > 8) return null
    if (sectionKeys.has(n.part_of)) return n.part_of
    return n.part_of && n.part_of !== ROOT ? sectionOf(n.part_of, depth + 1) : null
  }
  const cards = new Map(sections.map((s) => [s.key, []]))
  const orphans = []
  for (const n of notes) {
    if (n.key === ROOT || sectionKeys.has(n.key)) continue
    const s = sectionOf(n.key)
    if (s) cards.get(s).push(n)
    else orphans.push(n)
  }
  return { sections, cards, orphans }
}

const sig = (n) => JSON.stringify([n.kind, n.title, n.part_of, n.cites ?? [], n.cites_truncated === true, n.updated_at, n.last_verified_at, n.verify_interval_days, n.sha256])

/** Each section's place in the Doc registry: kept from the last manifest (v2, or v1's files[]). */
function numberSections(sections, manifest) {
  const known = new Map()
  if (manifest?.format === FORMAT && Array.isArray(manifest.sections)) {
    for (const s of manifest.sections) if (typeof s?.key === 'string' && Number.isInteger(s.nn) && s.nn > 0) known.set(s.key, s.nn)
  } else if (Array.isArray(manifest?.files)) {
    for (const f of manifest.files) if (typeof f?.slug === 'string' && Number.isInteger(f.nn) && f.nn > 0) known.set(`${ROOT}.${f.slug}`, f.nn)
  }
  const used = new Set()
  let next = Math.max(0, ...known.values()) + 1
  const out = new Map()
  for (const s of [...sections].sort(byKey)) {
    let nn = known.get(s.key)
    if (!nn || used.has(nn)) nn = next++
    used.add(nn)
    out.set(s.key, nn)
  }
  return out
}

// --- rendering -------------------------------------------------------------------------------------

function render({ notes, stamp, link, nn, pending, removedNow }) {
  const { sections, cards, orphans } = layout(notes)
  const head = (title, line) => [
    `# ${title}`,
    '',
    '> **AUTO-GENERATED MIRROR — do not edit this Doc.**',
    `> Source of truth is Zynkr Atlas: the 知識庫, collection \`${ROOT}\` (${link(ROOT)}).`,
    '> Edits made here are **not** read back and will be overwritten on the next mirror run.',
    `> ${line}`,
    '',
    '---',
    '',
  ].join('\n')
  const kindRank = (k) => { const i = KIND_ORDER.indexOf(k); return i < 0 ? KIND_ORDER.length : i }
  const order = (a, b) => kindRank(a.kind) - kindRank(b.kind) || (a.title < b.title ? -1 : a.title > b.title ? 1 : 0) || byKey(a, b)
  const card = (n) => {
    const meta = [`**key:** \`${n.key}\` · **kind:** ${oneLine(n.kind, 40)}`]
    meta.push(`**updated:** ${n.updated_at ?? '—'} · **verified:** ${n.last_verified_at ?? 'never'}${n.verify_interval_days ? ` · every ${n.verify_interval_days} days` : ''}`)
    if (n.cites?.length) meta.push(`**cites:** ${n.cites.map((k) => `\`${k}\``).join(', ')}${n.cites_truncated ? ' (and more: see Atlas)' : ''}`)
    meta.push(`**Atlas:** ${link(n.key)}`)
    return [`## ${oneLine(n.title) || n.key}`, '', meta.join('  \n'), '', n.body_md.trim(), '', '---', ''].join('\n')
  }

  const files = new Map()
  const sectionRows = []
  for (const s of [...sections].sort((a, b) => nn.get(a.key) - nn.get(b.key))) {
    const list = cards.get(s.key).sort(order)
    // A section need not be keyed kb.<slug>: any collection filed under the root is one.
    const slug = (s.key.startsWith(`${ROOT}.`) ? s.key.slice(ROOT.length + 1) : s.key).replace(/[^a-z0-9._-]/g, '-')
    const file = `${pad2(nn.get(s.key))}-${slug}.md`
    const docTitle = `${DOC_PREFIX} — ${pad2(nn.get(s.key))} ${oneLine(s.title) || s.key}`
    const body = head(docTitle, `Mirrored: ${stamp} · ${list.length} cards · section \`${s.key}\``) +
      (s.body_md.trim() ? `${s.body_md.trim()}\n\n---\n\n` : '') +
      (list.length ? list.map(card).join('\n') : '_(no cards in this section)_\n')
    files.set(file, body)
    sectionRows.push({ key: s.key, slug, nn: nn.get(s.key), title: oneLine(s.title), file, doc_title: docTitle, cards: list.length })
  }

  const all = [...cards.values()].flat().concat(orphans)
  const byKind = {}
  for (const n of all) byKind[n.kind] = (byKind[n.kind] ?? 0) + 1
  const cell = (s) => oneLine(s, 300).replace(/\|/g, '/')
  const index = [
    head(INDEX_TITLE,`Mirrored: ${stamp} · ${all.length} cards in ${sections.length} sections`),
    '| # | Section | key | cards | aliases / covers |',
    '|---|---|---|---|---|',
    ...sectionRows.map((r) => `| ${pad2(r.nn)} | ${cell(r.title)} | \`${r.key}\` | ${r.cards} | ${cell(notes.find((n) => n.key === r.key).body_md)} |`),
    '',
    `**Totals:** ${all.length} cards · ${Object.keys(byKind).sort().map((k) => `${byKind[k]} ${oneLine(k, 40)}`).join(' · ') || 'none'}`,
    ...(orphans.length ? ['', `**${orphans.length} card(s) in no section** (filed under \`${ROOT}\` itself, or under a collection no section holds):`, ...orphans.sort(byKey).map((n) => `- \`${n.key}\` — ${oneLine(n.title)}`)] : []),
    ...(pending.length ? ['', `**Waiting in 審核** — ${pending.length} draft(s) /zynkr-kms filed; not in the mirror until published:`, ...pending.map((p) => `- \`${p.key}\` — ${oneLine(p.title)} (in \`${oneLine(p.collection, 64).replace(/`/g, '')}\`, drafted ${oneLine(p.drafted_at, 40)})`)] : []),
    ...(removedNow.length ? ['', `**No longer published since the last run:** ${removedNow.map((n) => `\`${n.key}\``).join(', ')}`] : []),
    '',
  ].join('\n')
  files.set('00-index.md', index)
  return { files, sectionRows, byKind, orphans, cardCount: all.length }
}

// --- the run ---------------------------------------------------------------------------------------

function writeAtomic(file, text) {
  const tmp = `${file}.tmp-${process.pid}`
  writeFileSync(tmp, text, 'utf8')
  renameSync(tmp, file)
}

function parseArgs(argv) {
  const out = { cmd: null, flags: {} }
  let i = 0
  if (argv[0] && !argv[0].startsWith('--')) out.cmd = argv[i++]
  for (; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--full') { out.flags.full = true; continue }
    const m = /^--(out|env|url|key|collection|title|thread)$/.exec(a)
    if (!m || i + 1 >= argv.length) throw new Stop(`unknown or incomplete argument: ${oneLine(scrub(a), 60)}`, 2)
    out.flags[m[1]] = argv[++i]
  }
  return out
}

async function mirror(flags, deps) {
  const url = checkUrl(flags.url ?? DEFAULT_URL, deps.env, deps.execArgv)
  const { token, from, warning } = loadToken(deps.env, flags.env ?? join(deps.home, '.config', 'zynkr', 'kb-mirror.env'))
  if (warning) deps.log(`warning: ${warning}`)
  const state = { writing: false }
  try {
    const summary = await run(flags, deps, { url, token, from }, state)
    // The summary is data /zynkr-kms reads, so it skips the net (a note key may start zatl_): only the
    // token itself is taken out of it.
    return JSON.parse(redact(JSON.stringify(summary), token))
  } catch (e) {
    if (e instanceof Stop) throw e
    // Anything unexpected is reported with the token taken out, wherever the text came from.
    const what = oneLine(redact(e?.stack ?? e, token), 600)
    throw new Stop(state.writing
      ? `a write into ${flags.out} failed (${what}): upload nothing — the next run starts again from Drive's pair`
      : `unexpected error (${what}). Nothing was rewritten.`)
  }
}

async function run(flags, deps, { url, token, from }, state) {
  const { fetchImpl, sleep, clock, now, log, pace, backoff } = deps
  const out = flags.out
  const started = clock()
  const prev = previousRun(out)
  const full = flags.full === true || prev.reason !== null
  const reason = flags.full === true ? 'asked for (--full)' : prev.reason
  prev.byKey = new Map((prev.snapshot?.notes ?? []).filter((n) => n && typeof n.key === 'string').map((n) => [n.key, n]))
  log(`kb-drive-mirror v2: ${full ? `full run (${reason})` : 'incremental run'} → ${out}; token from ${from}`)

  // 1. every call and every check, before anything is written
  const c = createClient({ url: url.href, token, fetchImpl, sleep, clock, pace, backoff, log })
  await c.initialize()
  const tools = await c.tools()
  if (!tools.includes('export_knowledge')) {
    throw new Stop('this token cannot export: export_knowledge is not in tools/list. Mint one with 「可以匯出知識（給鏡像用）」. Nothing was rewritten.')
  }
  if (!tools.includes('list_knowledge')) throw new Stop('Atlas does not serve list_knowledge (tools/list). Nothing was rewritten.')
  const who = (await c.call('whoami', {}))?.structuredContent
  const slug = typeof who?.workspace?.slug === 'string' && /^[a-z0-9-]{1,64}$/.test(who.workspace.slug) ? who.workspace.slug : null
  if (!slug) throw new Stop('whoami did not name the workspace. Nothing was rewritten.')
  const link = (key) => `${url.origin}/w/${slug}/knowledge/${key}`

  const { rows, pages: listPages } = await listAll(c)
  const bodies = new Map()
  let exportKeys = null
  if (!full) {
    exportKeys = [ROOT]
    for (const row of rows.values()) {
      const kept = carried(prev, row)
      if (kept) bodies.set(row.key, kept)
      else exportKeys.push(row.key)
    }
  }
  const { notes: exported, pages: exportPages } = await exportNotes(c, exportKeys)
  if (!exported.has(ROOT)) throw new Stop(`the export did not hold the root collection ${ROOT}. Nothing was rewritten.`)
  for (const key of rows.keys()) {
    if (!exported.has(key) && !bodies.has(key)) throw new Stop(`${key} was listed but not exported: the 知識庫 changed during the run. Nothing was rewritten — run it again.`)
  }
  for (const key of exported.keys()) {
    if (key !== ROOT && !rows.has(key)) throw new Stop(`${key} was exported but not listed: the 知識庫 changed during the run. Nothing was rewritten — run it again.`)
  }

  // 2. the copy, in memory
  const notes = []
  for (const row of rows.values()) {
    const e = exported.get(row.key)
    const b = e ? { body_md: e.body_md, sha256: e.sha256, updated_at: e.updated_at } : bodies.get(row.key)
    notes.push({ ...row, body_md: b.body_md, sha256: b.sha256, updated_at: b.updated_at })
  }
  const root = exported.get(ROOT)
  notes.push({ key: ROOT, kind: root.kind, title: root.title, part_of: null, cites: [], body_md: root.body_md, sha256: root.sha256, updated_at: root.updated_at, last_verified_at: root.last_verified_at, verify_interval_days: root.verify_interval_days })
  notes.sort(byKey)

  const stamp = stampOf(now())
  const live = new Set(notes.map((n) => n.key))
  const prevNotes = [...prev.byKey.values()]
  // What the last record held: the snapshot's notes, and the manifest's, which differ only when the
  // two come from different runs.
  const held = new Map(prev.byKey)
  for (const [key, m] of Object.entries(prev.manifestV2 && prev.manifest.notes ? prev.manifest.notes : {})) {
    if (KEY_RE.test(key) && !held.has(key)) held.set(key, { key, part_of: m?.part_of ?? null })
  }
  const removedNow = [...held.values()].filter((n) => !live.has(n.key)).sort(byKey).map((n) => ({ key: n.key, kind: n.kind ?? null, title: oneLine(n.title), part_of: n.part_of ?? null, removed_at: stamp }))
  // A key already in the record of removed notes keeps its first entry.
  const removed = [...new Map([...removedNow, ...(Array.isArray(prev.snapshot?.removed) ? prev.snapshot.removed : [])]
    .filter((n) => n && typeof n.key === 'string' && !live.has(n.key)).map((n) => [n.key, n])).values()].sort(byKey)

  const pendingBefore = (Array.isArray(prev.manifest?.pending) ? prev.manifest.pending : []).filter((p) => p && typeof p.key === 'string' && KEY_RE.test(p.key))
  // A draft stays in pending[] until /zynkr-kms drops it, after labelling its thread: a run that stops
  // before then loses nothing, because every run names a published one again.
  const waiting = pendingBefore.filter((p) => !live.has(p.key))
  const published = pendingBefore.filter((p) => live.has(p.key)).map((p) => ({ key: p.key, ...(typeof p.thread === 'string' ? { thread: p.thread } : {}) }))

  const nn = numberSections(layout(notes).sections, prev.manifest)
  const { files, sectionRows, byKind, orphans, cardCount } = render({ notes, stamp, link, nn, pending: waiting, removedNow })

  // A section Doc is uploaded again only when something in it changed (a full run: all of them).
  const before = layout(prevNotes)
  const current = layout(notes)
  const prevSig = new Map(prevNotes.map((n) => [n.key, sig(n)]))
  const touched = new Set()
  for (const s of current.sections) {
    const members = current.cards.get(s.key)
    const was = before.cards.get(s.key)
    if (full || !was || prevSig.get(s.key) !== sig(s) || members.some((n) => prevSig.get(n.key) !== sig(n)) ||
      was.map((n) => n.key).sort().join() !== members.map((n) => n.key).sort().join()) touched.add(s.key)
  }
  // The sections the last record held, the manifest's among them, as for `held`.
  const heldSections = new Set(before.sections.map((s) => s.key))
  for (const s of prev.manifestV2 && Array.isArray(prev.manifest.sections) ? prev.manifest.sections : []) {
    if (typeof s?.key === 'string' && KEY_RE.test(s.key)) heldSections.add(s.key)
  }
  const sectionsNow = new Set(current.sections.map((s) => s.key))
  const removedSections = [...heldSections].filter((k) => !sectionsNow.has(k)).sort()

  const snapshot = {
    format: FORMAT,
    mirrored_at: stamp,
    source: { atlas: url.origin, workspace: slug, collection: ROOT },
    counts: { notes: notes.length, collections: notes.filter((n) => n.kind === 'collection').length, by_kind: byKind },
    notes,
    removed,
  }
  const upload = [
    ...sectionRows.filter((r) => touched.has(r.key)).map((r) => ({ file: r.file, section: r.key, nn: r.nn, doc_title: r.doc_title })),
    { file: '00-index.md', doc_title: INDEX_TITLE },
    { file: '_KB-SNAPSHOT.json' },
    { file: '_MANIFEST.json' },
  ]
  const calls = c.calls
  const manifest = {
    format: FORMAT,
    mirrored_at: stamp,
    mode: full ? 'full' : 'incremental',
    source: snapshot.source,
    counts: { notes: notes.length, sections: sectionRows.length, cards: cardCount, orphans: orphans.length },
    sections: sectionRows,
    notes: Object.fromEntries(notes.map((n) => [n.key, { updated_at: n.updated_at, sha256: n.sha256, part_of: n.part_of }])),
    pending: pendingBefore,
    run: { calls, list_pages: listPages, export_pages: exportPages, exported: exported.size, carried: bodies.size, elapsed_ms: Math.round(clock() - started), backed_off: c.backedOff },
  }

  // 3. only now the files, the manifest last
  state.writing = true
  mkdirSync(out, { recursive: true })
  for (const [file, text] of files) {
    if (file === '00-index.md' || touched.has(sectionRows.find((r) => r.file === file)?.key)) writeAtomic(join(out, file), text)
  }
  writeAtomic(join(out, '_KB-SNAPSHOT.json'), JSON.stringify(snapshot, null, 2))
  writeAtomic(join(out, '_MANIFEST.json'), JSON.stringify(manifest, null, 2))

  log(`calls: ${calls} (paced at ≤${Math.floor(60_000 / Math.max(pace, 1))} a minute) · elapsed: ${(manifest.run.elapsed_ms / 1000).toFixed(1)} s`)
  return {
    mode: manifest.mode,
    ...(full ? { reason } : {}),
    mirrored_at: stamp,
    workspace: slug,
    collection: ROOT,
    counts: manifest.counts,
    by_kind: byKind,
    exported: exported.size,
    carried: bodies.size,
    removed: removedNow.map((n) => n.key),
    removed_sections: removedSections,
    pending: waiting.length,
    pending_published: published,
    orphans: orphans.map((n) => n.key),
    upload,
    calls,
    elapsed_ms: manifest.run.elapsed_ms,
  }
}

function editPending(cmd, flags, now) {
  const file = join(flags.out, '_MANIFEST.json')
  const manifest = readJson(file)
  // A v1 manifest takes pending[] too, and the first v2 run carries it over: before then, a run whose
  // mirror cannot work still records its drafts.
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw new Stop('no _MANIFEST.json in --out, or one that does not parse: download it from Drive first')
  }
  if (!KEY_RE.test(flags.key ?? '')) throw new Stop('--key must be a note key (a–z, 0–9, dot, dash, underscore)', 2)
  const pending = Array.isArray(manifest.pending) ? manifest.pending : []
  if (cmd === 'pending-drop') {
    if (!pending.some((p) => p?.key === flags.key)) throw new Stop(`${flags.key} is not in pending[]`)
    manifest.pending = pending.filter((p) => p?.key !== flags.key)
    writeAtomic(file, JSON.stringify(manifest, null, 2))
    return { pending: manifest.pending.length, dropped: flags.key }
  }
  if (!KEY_RE.test(flags.collection ?? '')) throw new Stop('--collection must be a collection key, such as kb.billing', 2)
  const title = oneLine(flags.title)
  if (!title) throw new Stop('--title is required', 2)
  if (flags.thread !== undefined && !/^[0-9a-f]{8,32}$/i.test(flags.thread)) throw new Stop('--thread must be a Gmail thread id (hex)', 2)
  if (manifest.notes?.[flags.key]) throw new Stop(`${flags.key} is already published, so there is nothing to wait for`)
  if (pending.some((p) => p?.key === flags.key)) return { pending: pending.length, added: null }
  manifest.pending = [...pending, { key: flags.key, collection: flags.collection, title, drafted_at: stampOf(now()), ...(flags.thread ? { thread: flags.thread } : {}) }]
  writeAtomic(file, JSON.stringify(manifest, null, 2))
  return { pending: manifest.pending.length, added: flags.key }
}

/** The whole command; returns the exit code. `deps` lets the tests run it with no network. */
export async function main(argv, deps = {}) {
  const d = {
    env: process.env,
    fetchImpl: globalThis.fetch,
    sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
    clock: () => Date.now(),
    now: () => new Date(),
    log: (s) => process.stderr.write(`${s}\n`),
    print: (s) => process.stdout.write(`${s}\n`),
    pace: PACE_MS,
    backoff: BACKOFF_MS,
    home: homedir(),
    execArgv: process.execArgv,
    ...deps,
  }
  // The net: whatever a message quotes — a path, an argument, a server's words — nothing shaped like
  // a token reaches stderr. stdout carries only the JSON summary, which is data (see mirror()).
  const log = d.log
  d.log = (s) => log(scrub(s))
  try {
    const { cmd, flags } = parseArgs(argv)
    if (!flags.out) throw new Stop('--out <dir> is required', 2)
    if (cmd !== null && cmd !== 'pending-add' && cmd !== 'pending-drop') throw new Stop(`unknown command: ${oneLine(scrub(cmd), 40)}`, 2)
    const summary = cmd ? editPending(cmd, flags, d.now) : await mirror(flags, d)
    d.print(JSON.stringify(summary, null, 2))
    return 0
  } catch (e) {
    // Anything unexpected goes through the net too, never out to Node with its stack.
    if (!(e instanceof Stop)) {
      d.log(`kb-drive-mirror: unexpected error (${oneLine(e?.stack ?? e, 600)})`)
      return 1
    }
    d.log(`kb-drive-mirror: ${e.message}`)
    return e.code
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === realpathSync(process.argv[1])) process.exitCode = await main(process.argv.slice(2))
