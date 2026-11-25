# Recap mail — the HTML format for a post-call recap (SKB-140)

A recap that goes to a client after a call is rendered, not typed: the skill writes the content as a
JSON payload and `scripts/render_recap_email.py` (inside this skill folder) turns it into a
Zynkr-styled HTML body. The words are the run's job; the look is the renderer's, so every recap reads
the same way and the form rules hold without anyone remembering them.

## When it applies

| Mail | Format |
|---|---|
| A recap after a call (a discovery call, a demo, an AI 諮詢, a consulting session) | **This format** |
| A first-touch outbound mail, a reply to a short question, a scheduling mail | Plain text, per 《[2.2]》 Part 3 §八 — unchanged |

The house voice still governs every word in the payload: 《[2.0]》, 《[2.2]》 Part 3 §八 and
《[3.2]》 十一 with the categories its scope names. The renderer replaces only 十一's *form* rules for this one
genre (plain text only, `── 文字 · 文字 ──` as the only heading, at most two lists): headings, the
quote box, the diagrams and the numbered next steps are the renderer's, and are allowed here.

## Content rules

1. **Their words, verbatim.** A `quote` block holds the client's own sentence from the transcript,
   cleaned of filler only. Never rewrite it into marketing language. The renderer adds the 「」.
2. **A diagram only when the call drew it.** `flow` is a process the client described or the one you
   proposed on the call; `pyramid` is advice about how to structure their work; `timeline` is stages
   in time. No diagram is decorative, and none adds a step, a skill or a goal nobody said.
3. **One orange button, at most.** The `action` block is the promised resource when the transcript
   shows one was promised (「我會把資源包寄給你」). With no promise, it is the one agreed next step
   (`sales-follow-up`: the convert line to `https://zynkr.ai/crm`). With neither, the mail has no
   `action` block. The renderer refuses a second one.
4. **Every next step has an owner.** `next_steps` groups are named by owner (「你那邊」「我這邊」 or
   a name). The renderer refuses a group without one.
5. **Links are real and https.** Every URL comes from the transcript, Atlas `sales-kit`, or the skill's
   fixed facts. Never a guessed URL. Prices stay out of the mail (link the pricing page instead).
6. **Length is the genre's.** The body text keeps the skill's own length limit; diagrams do not count
   toward it, and do not justify more text.
7. **Language follows the client.** Labels (`eyebrow`, `label`, owners) are written in the client's
   language too.

## How to run it

```bash
python3 scripts/render_recap_email.py <tmp>/recap.json --check            # refuses a payload that breaks a rule
python3 scripts/render_recap_email.py <tmp>/recap.json --out <tmp>/recap.html
```

Then pass the file's contents to `mcp__google-workspace__draft_gmail_message(body=<recap.html>,
body_format="html", include_signature=true, …)`, with the threading arguments when it replies on a
thread. The HTML is a fragment: Gmail adds the sender's signature card under it. Never send; the
person reads the draft and sends it. Keep the payload in the run's temp folder, never in a repo: it
holds a client's name.

## The payload

```json
{
  "preheader": "inbox preview line (optional)",
  "label": "AI 諮詢 · 會後整理 · 11/16",
  "greeting": "小明你好，",
  "intro": ["one or two paragraphs: thank them for one specific thing, say what follows"],
  "blocks": [ … ],
  "closing": ["one line that is an action or a short thanks"],
  "signoff": "Peter"
}
```

`greeting`, `blocks` and `signoff` are required. Paragraph text takes two inline marks:
`[text](https://…)` for a link and `` `CODE` `` for a chip (a promo code, a command). Everything else
is escaped.

### Blocks, in the order you list them

| `type` | Keys | Use it for |
|---|---|---|
| `text` | `eyebrow?` `heading?` `paragraphs` | Their situation, your advice, one thing we cannot do |
| `quote` | `eyebrow?` `heading?` `text` `source?` | Their own sentence, verbatim |
| `flow` | `eyebrow?` `heading?` `intro?` `steps[2–5]{title, note?, highlight?}` `caption?` | A process, in one row |
| `pyramid` | `eyebrow?` `heading?` `intro?` `top{label?, text}` `middle[2–4]{label?, text}` `bottom[same count]{label?, items[]}` `caption?` | A MECE structure: goal → kinds of work → skills or tasks |
| `timeline` | `eyebrow?` `heading?` `intro?` `stages[2–5]{title, note?, highlight?}` `caption?` | The same work split by time instead |
| `action` | `eyebrow?` `title?` `body?` `button{text, url}` `note?` | The one orange button (rule 3) |
| `options` | `eyebrow?` `items[]{title, body?, link?{text, url}}` | Ways to go further: an event, a programme, a call |
| `next_steps` | `eyebrow?` `groups[]{owner, items[]}` | Who does what next |

A worked payload is the built-in example in `render_recap_email.py` (`EXAMPLE`); run
`python3 scripts/render_recap_email.py --self-test` to render it and check the invariants.

## Seed

This file and `render_recap_email.py` are copies. The seed is `docs/recap-mail-shared/` in the skills
workbench; `scripts/check-recap-mail-refs.sh` proves every copy is byte-identical. Change the seed,
then run `scripts/check-recap-mail-refs.sh --sync`.
