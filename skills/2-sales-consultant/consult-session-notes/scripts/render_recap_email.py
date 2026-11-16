#!/usr/bin/env python3
"""Render a post-call recap mail (JSON) into a Zynkr-styled, email-safe HTML body.  SKB-140

Why this exists: what a recap SAYS is the model's job and changes every call. How it LOOKS should
not: a stable template means every recap a client gets reads the same way, and the house rules that
are about form (one orange button, a quote box for their own words, owners on every next step) are
enforced here instead of being re-remembered on every run. The model writes a JSON payload
(references/recap-mail.md documents it); this script turns it into HTML and refuses a payload that
breaks a rule.

Usage:
    python3 render_recap_email.py recap.json > body.html
    python3 render_recap_email.py recap.json --out body.html
    python3 render_recap_email.py recap.json --check      # validate only
    python3 render_recap_email.py --self-test             # render the built-in example, assert the invariants

Output is a <div> fragment, not a document: it goes into draft_gmail_message(body=…, body_format="html",
include_signature=True), which appends the sender's Gmail signature card after it. Gmail drops <head> and
<style>, so every style is inline, layout is tables, and widths are fluid (max 600px) so phones fit it.

Seed: docs/recap-mail-shared/render_recap_email.py. Every skill that uses it carries a byte-identical
copy in its own scripts/; scripts/check-recap-mail-refs.sh proves they never drift.
"""
import argparse
import html as _html
import json
import re
import sys

# --- palette ------------------------------------------------------------------------------------
# zynkr.ai/data/tokens.json (SDD §4). Mail clients drop CSS variables, so each hex is written out.
# LINE is the solid stand-in for --line on Paper (as in render_dashboard_email.py). Sage Deep is
# typography only here (labels, arrows); Orange appears once at most (the one action button).
PAPER = "#FBF7F0"
RAISED = "#FDFAF5"
INK = "#0F0F0E"
INK_MID = "#3D3A36"
MUTE = "#6F6B62"
LINE = "#E6E1D8"
SAGE = "#86C4AC"
SAGE_SOFT = "#DCEEE6"
SAGE_DEEP = "#5FA48A"
ORANGE = "#F26B1F"
WHITE = "#FFFFFF"

LOGO_URL = "https://zynkr.ai/assets/zynkr-logo-sage.png"

F_BODY = "'Noto Sans TC','PingFang TC','Microsoft JhengHei',Helvetica,Arial,sans-serif"
F_DISPLAY = "'Space Grotesk','Noto Sans TC','PingFang TC',Helvetica,Arial,sans-serif"
F_MONO = "'JetBrains Mono',Menlo,Consolas,monospace"

BLOCK_TYPES = ("text", "quote", "flow", "pyramid", "timeline", "action", "options", "next_steps")


class PayloadError(ValueError):
    pass


# --- inline text ----------------------------------------------------------------------------------
# Two marks only: [text](https://…) for a link and `CODE` for a chip (a promo code, a command).
# Everything else is escaped, so a payload can never inject markup.
_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")
_CHIP = re.compile(r"`([^`]+)`")


def esc(v):
    return _html.escape("" if v is None else str(v), quote=True)


def inline(text):
    s = "" if text is None else str(text)
    out, pos = [], 0
    for m in _LINK.finditer(s):
        out.append(_chips(esc(s[pos:m.start()])))
        out.append(
            f'<a href="{esc(m.group(2))}" style="color:{INK};text-decoration:underline;'
            f'text-decoration-color:{SAGE};">{_chips(esc(m.group(1)))}</a>'
        )
        pos = m.end()
    out.append(_chips(esc(s[pos:])))
    return "".join(out)


def _chips(escaped):
    return _CHIP.sub(
        lambda m: f'<span style="font-family:{F_MONO};background:{SAGE_SOFT};padding:1px 6px;'
        f'border-radius:4px;">{m.group(1)}</span>',
        escaped,
    )


# --- building blocks ----------------------------------------------------------------------------------
def eyebrow(text, bottom=8):
    if not text:
        return ""
    return (
        f'<p style="margin:0 0 {bottom}px;font-family:{F_MONO};font-size:11px;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:{SAGE_DEEP};">{esc(text)}</p>'
    )


def heading(text, bottom=14):
    if not text:
        return ""
    return (
        f'<p style="margin:0 0 {bottom}px;font-family:{F_DISPLAY};font-size:20px;line-height:1.35;'
        f'font-weight:600;color:{INK};">{esc(text)}</p>'
    )


def para(text, bottom=18, size=None, color=None, align=None):
    style = f"margin:0 0 {bottom}px;"
    if size:
        style += f"font-size:{size};"
    if color:
        style += f"color:{color};"
    if align:
        style += f"text-align:{align};"
    return f'<p style="{style}">{inline(text)}</p>'


def badge(n, fill=SAGE_SOFT, size=22):
    return (
        f'<div style="display:inline-block;width:{size}px;height:{size}px;line-height:{size}px;'
        f'border-radius:{size // 2}px;background:{fill};font-family:{F_MONO};font-size:12px;font-weight:600;'
        f'text-align:center;color:{INK};">{esc(n)}</div>'
    )


def table(inner, width="100%", style="", extra=""):
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="{width}" '
        f'style="border-collapse:collapse;{style}"{extra}>{inner}</table>'
    )


# --- blocks -------------------------------------------------------------------------------------------
def b_text(b):
    paras = b.get("paragraphs") or []
    out = eyebrow(b.get("eyebrow")) + heading(b.get("heading"))
    for i, p in enumerate(paras):
        out += para(p, bottom=30 if i == len(paras) - 1 else 18)
    return out


def b_quote(b):
    src = b.get("source")
    src_html = (
        f'<div style="margin-top:6px;font-family:{F_MONO};font-size:11px;color:{MUTE};">{esc(src)}</div>'
        if src else ""
    )
    cell = (
        f'<td style="background:{RAISED};border:1px solid {LINE};border-left:3px solid {SAGE};'
        f'padding:14px 18px;font-size:15px;line-height:1.7;color:{INK_MID};">'
        f'「{inline(b["text"])}」{src_html}</td>'
    )
    return eyebrow(b.get("eyebrow")) + heading(b.get("heading")) + table(f"<tr>{cell}</tr>", style="margin:0 0 18px;")


def b_flow(b):
    steps = b["steps"]
    n = len(steps)
    arrow_w = 2.6
    cell_w = round((100 - arrow_w * (n - 1)) / n, 1)
    cells = []
    for i, s in enumerate(steps, 1):
        hi = bool(s.get("highlight"))
        bg, border, badge_fill, note_c = (SAGE_SOFT, SAGE, RAISED, INK_MID) if hi else (RAISED, LINE, SAGE_SOFT, MUTE)
        note = f'<div style="color:{note_c};">{inline(s["note"])}</div>' if s.get("note") else ""
        cells.append(
            f'<td valign="top" style="width:{cell_w}%;background:{bg};border:1px solid {border};border-radius:8px;'
            f'padding:12px 10px;font-size:13px;line-height:1.5;">{badge(i, badge_fill)}'
            f'<div style="margin-top:6px;font-weight:600;color:{INK};">{esc(s["title"])}</div>{note}</td>'
        )
        if i < n:
            cells.append(
                f'<td valign="middle" align="center" style="width:{arrow_w}%;font-size:14px;color:{SAGE_DEEP};">→</td>'
            )
    row = table("<tr>" + "".join(cells) + "</tr>", style="margin:0 0 10px;table-layout:fixed;")
    after = para(b["caption"], bottom=32, size="13.5px", color=MUTE) if b.get("caption") else '<div style="height:22px;"></div>'
    return eyebrow(b.get("eyebrow")) + heading(b.get("heading")) + (para(b["intro"]) if b.get("intro") else "") + row + after


def _tier_cell(label, body_html, border, size="13px"):
    lab = (
        f'<div style="font-family:{F_MONO};font-size:10.5px;letter-spacing:0.1em;color:{MUTE};">{esc(label)}</div>'
        if label else ""
    )
    return (
        f'<td align="center" style="background:{RAISED};border:1px solid {border};border-radius:8px;'
        f'padding:10px 6px;font-size:{size};line-height:1.5;color:{INK_MID};">{lab}{body_html}</td>'
    )


def b_pyramid(b):
    top, middle, bottom = b["top"], b["middle"], b["bottom"]
    top_label = (
        f'<div style="font-family:{F_MONO};font-size:10.5px;letter-spacing:0.1em;color:{INK_MID};">{esc(top.get("label", ""))}</div>'
        if top.get("label") else ""
    )
    top_html = table(
        f'<tr><td align="center" style="background:{SAGE_SOFT};border-radius:8px;padding:12px 10px;font-size:13px;'
        f'line-height:1.45;color:{INK};">{top_label}<div style="font-weight:600;">{esc(top["text"])}</div></td></tr>',
        width="44%",
    )
    mid_cells = "".join(
        _tier_cell(m.get("label"), f'<div style="font-weight:600;color:{INK};">{esc(m["text"])}</div>', SAGE)
        for m in middle
    )
    bot_cells = "".join(
        _tier_cell(c.get("label"), "<br>".join(esc(x) for x in c["items"]), LINE, size="12.5px")
        for c in bottom
    )
    sep = 'style="border-collapse:separate;border-spacing:6px 0;table-layout:fixed;"'
    mid_html = f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="74%" {sep}><tr>{mid_cells}</tr></table>'
    bot_html = f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" {sep}><tr>{bot_cells}</tr></table>'
    tiers = (
        f'<tr><td align="center" style="padding:0 0 8px;">{top_html}</td></tr>'
        f'<tr><td align="center" style="padding:0 0 8px;">{mid_html}</td></tr>'
        f'<tr><td align="center" style="padding:0;">{bot_html}</td></tr>'
    )
    caption = para(b["caption"], bottom=24, size="13.5px", color=MUTE, align="center") if b.get("caption") else '<div style="height:18px;"></div>'
    return (
        eyebrow(b.get("eyebrow")) + heading(b.get("heading"), bottom=10)
        + (para(b["intro"]) if b.get("intro") else "")
        + table(tiers, style="margin:0 0 6px;") + caption
    )


def b_timeline(b):
    stages = b["stages"]
    n = len(stages)
    gap = 1.3
    w = round((100 - gap * (n - 1)) / n, 1)
    cells = []
    for i, s in enumerate(stages):
        edge = SAGE_DEEP if s.get("highlight") else SAGE
        note = f'<div style="color:{MUTE};">{inline(s["note"])}</div>' if s.get("note") else ""
        pad_r = "0" if i == n - 1 else "6px"
        cells.append(
            f'<td valign="top" style="width:{w}%;border-top:3px solid {edge};padding:10px {pad_r} 0 0;font-size:13px;'
            f'line-height:1.5;"><div style="font-weight:600;color:{INK};">{esc(s["title"])}</div>{note}</td>'
        )
        if i < n - 1:
            cells.append(f'<td style="width:{gap}%;"></td>')
    row = table("<tr>" + "".join(cells) + "</tr>", style="margin:0 0 14px;table-layout:fixed;")
    after = para(b["caption"], bottom=32) if b.get("caption") else '<div style="height:20px;"></div>'
    return eyebrow(b.get("eyebrow")) + heading(b.get("heading")) + (para(b["intro"], bottom=12) if b.get("intro") else "") + row + after


def b_action(b):
    btn = b["button"]
    body = para(b["body"], bottom=20, size="15px") if b.get("body") else ""
    note = (
        f'<p style="margin:18px 0 0;font-size:13.5px;line-height:1.7;color:{MUTE};">{inline(b["note"])}</p>'
        if b.get("note") else ""
    )
    button = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td bgcolor="{ORANGE}" style="background:{ORANGE};border-radius:999px;">'
        f'<a href="{esc(btn["url"])}" style="display:inline-block;font-family:{F_DISPLAY};background:{ORANGE};'
        f'color:{WHITE};text-decoration:none;border-radius:999px;padding:14px 28px;font-size:15px;font-weight:500;'
        f'line-height:1;">{esc(btn["text"])}</a></td></tr></table>'
    )
    card = (
        f'<td style="background:{RAISED};border:1px solid {LINE};border-radius:12px;padding:24px 24px 26px;">'
        f'{eyebrow(b.get("eyebrow"))}{heading(b.get("title"), bottom=10)}{body}{button}{note}</td>'
    )
    return table(f"<tr>{card}</tr>", style="margin:0 0 34px;")


def b_options(b):
    rows = []
    items = b["items"]
    for i, it in enumerate(items):
        bottom_border = f"border-bottom:1px solid {LINE};" if i == len(items) - 1 else ""
        meta = f'<div style="font-size:14px;color:{INK_MID};margin:2px 0 6px;">{inline(it["body"])}</div>' if it.get("body") else ""
        link = it.get("link")
        link_html = (
            f'<a href="{esc(link["url"])}" style="font-size:14px;color:{INK};text-decoration:underline;'
            f'text-decoration-color:{SAGE};">{esc(link["text"])}</a>' if link else ""
        )
        rows.append(
            f'<tr><td style="padding:14px 0;border-top:1px solid {LINE};{bottom_border}">'
            f'<div style="font-weight:600;font-size:15px;color:{INK};">{esc(it["title"])}</div>{meta}{link_html}</td></tr>'
        )
    return eyebrow(b.get("eyebrow")) + table("".join(rows), style="margin:0 0 6px;") + '<div style="height:28px;line-height:28px;">&nbsp;</div>'


def b_next_steps(b):
    rows = []
    groups = b["groups"]
    for gi, g in enumerate(groups):
        rows.append(f'<tr><td style="padding:0 0 6px;font-weight:600;font-size:14px;color:{INK};">{esc(g["owner"])}</td></tr>')
        for ii, item in enumerate(g["items"], 1):
            last_in_group = ii == len(g["items"])
            pad = "16px" if last_in_group and gi < len(groups) - 1 else ("0" if last_in_group else "8px")
            rows.append(
                f'<tr><td style="padding:0 0 {pad};font-size:14px;line-height:1.6;">'
                f'<span style="display:inline-block;width:20px;height:20px;line-height:20px;border-radius:10px;'
                f'background:{SAGE_SOFT};font-family:{F_MONO};font-size:11px;font-weight:600;text-align:center;'
                f'margin-right:8px;">{ii}</span>{inline(item)}</td></tr>'
            )
    return eyebrow(b.get("eyebrow"), bottom=12) + table("".join(rows), style="margin:0 0 28px;")


RENDER = {
    "text": b_text, "quote": b_quote, "flow": b_flow, "pyramid": b_pyramid, "timeline": b_timeline,
    "action": b_action, "options": b_options, "next_steps": b_next_steps,
}


# --- validation ---------------------------------------------------------------------------------------
def _need(cond, msg):
    if not cond:
        raise PayloadError(msg)


def _https(url, where):
    _need(isinstance(url, str) and url.startswith("https://"), f"{where}: links must be https:// (got {url!r})")


def validate(d):
    _need(isinstance(d, dict), "payload must be a JSON object")
    for k in ("greeting", "blocks", "signoff"):
        _need(d.get(k), f"missing required key: {k}")
    blocks = d["blocks"]
    _need(isinstance(blocks, list) and blocks, "blocks must be a non-empty list")
    actions = 0
    for i, b in enumerate(blocks):
        where = f"blocks[{i}]"
        t = b.get("type") if isinstance(b, dict) else None
        _need(t in BLOCK_TYPES, f"{where}: unknown type {t!r} (one of {', '.join(BLOCK_TYPES)})")
        if t == "text":
            _need(b.get("paragraphs"), f"{where}: text needs paragraphs")
        elif t == "quote":
            _need(b.get("text"), f"{where}: quote needs text (the client's own words, verbatim)")
            _need(not str(b["text"]).startswith("「"), f"{where}: quote text without 「」 — the renderer adds them")
        elif t == "flow":
            s = b.get("steps") or []
            _need(2 <= len(s) <= 5, f"{where}: flow takes 2–5 steps in one row (got {len(s)})")
            _need(all(x.get("title") for x in s), f"{where}: every flow step needs a title")
        elif t == "pyramid":
            _need(b.get("top", {}).get("text"), f"{where}: pyramid needs top.text (the goal)")
            m, bt = b.get("middle") or [], b.get("bottom") or []
            _need(2 <= len(m) <= 4, f"{where}: pyramid middle takes 2–4 work types (got {len(m)})")
            _need(len(bt) == len(m), f"{where}: pyramid bottom needs one column per middle cell ({len(m)}), got {len(bt)}")
            _need(all(x.get("text") for x in m), f"{where}: every middle cell needs text")
            _need(all(x.get("items") for x in bt), f"{where}: every bottom column needs items")
        elif t == "timeline":
            s = b.get("stages") or []
            _need(2 <= len(s) <= 5, f"{where}: timeline takes 2–5 stages in one row (got {len(s)})")
            _need(all(x.get("title") for x in s), f"{where}: every stage needs a title")
        elif t == "action":
            actions += 1
            btn = b.get("button") or {}
            _need(btn.get("text") and btn.get("url"), f"{where}: action needs button.text and button.url")
            _https(btn["url"], f"{where}.button")
        elif t == "options":
            items = b.get("items") or []
            _need(items, f"{where}: options needs items")
            for j, it in enumerate(items):
                _need(it.get("title"), f"{where}.items[{j}]: needs a title")
                if it.get("link"):
                    _https(it["link"].get("url"), f"{where}.items[{j}].link")
        elif t == "next_steps":
            g = b.get("groups") or []
            _need(g, f"{where}: next_steps needs groups")
            _need(all(x.get("owner") and x.get("items") for x in g),
                  f"{where}: every next-steps group names its owner and has items (no ownerless to-dos)")
    _need(actions <= 1, f"one orange button per mail: found {actions} action blocks")
    for p in [*(d.get("intro") or []), *(d.get("closing") or [])]:
        for url in re.findall(r"\]\(([^)]+)\)", str(p)):
            _https(url, "intro/closing link")


# --- page ---------------------------------------------------------------------------------------------
def build_html(d):
    validate(d)
    pre = (
        f'<div style="display:none;max-height:0;overflow:hidden;">{esc(d["preheader"])}</div>'
        if d.get("preheader") else ""
    )
    label = (
        f'<td align="right" style="font-family:{F_MONO};font-size:11px;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:{MUTE};">{esc(d["label"])}</td>'
        if d.get("label") else ""
    )
    header = (
        f'<tr><td style="padding:28px 32px 20px;border-bottom:1px solid {LINE};">'
        + table(
            f'<tr><td align="left"><img src="{LOGO_URL}" alt="Zynkr" height="28" '
            f'style="display:block;border:0;height:28px;width:auto;"></td>{label}</tr>'
        )
        + "</td></tr>"
    )
    body = para(d["greeting"], bottom=18)
    intro = d.get("intro") or []
    for i, p in enumerate(intro):
        body += para(p, bottom=30 if i == len(intro) - 1 else 18)
    for b in d["blocks"]:
        body += RENDER[b["type"]](b)
    for p in d.get("closing") or []:
        body += para(p, bottom=6)
    body += para(d["signoff"], bottom=8)
    content = (
        f'<tr><td style="padding:36px 32px 8px;font-family:{F_BODY};font-size:15px;line-height:1.75;color:{INK};">'
        f"{body}</td></tr>"
    )
    inner = table(header + content, style=f"width:100%;max-width:600px;background:{PAPER};")
    outer = table(f'<tr><td align="center" style="padding:0;">{inner}</td></tr>', style=f"background:{PAPER};",
                  extra=f' bgcolor="{PAPER}"')
    return f'<div style="margin:0;padding:0;background:{PAPER};">{pre}{outer}</div>'


# --- self-test ----------------------------------------------------------------------------------------
# A fictional client (no real names: the CI leak gate and the public shelf both read this file).
EXAMPLE = {
    "preheader": "今天聊的重點、你的 Skills 框架圖，還有答應給你的資源",
    "label": "AI 諮詢 · 會後整理 · 11/16",
    "greeting": "小明你好，",
    "intro": ["謝謝你今天抽空聊了 45 分鐘。下面是今天的重點，還有會中答應給你的資源。"],
    "blocks": [
        {"type": "text", "eyebrow": "你現在的狀況",
         "paragraphs": ["每週兩場跨部門會議，會後你要自己整理逐字稿，再轉成待辦和報告。"]},
        {"type": "quote", "eyebrow": "你想先做的", "heading": "一份逐字稿，四個產出",
         "text": "會議紀錄丟進去，報告、email、待辦、合約修改一起出來，我後面會省事很多。", "source": "你今天說的"},
        {"type": "flow", "steps": [
            {"title": "會議逐字稿", "note": "錄音或 Fireflies"},
            {"title": "四個產出", "note": "報告 · Email · 待辦 · 修改", "highlight": True},
            {"title": "稽核", "note": "找風險和缺漏"},
            {"title": "你核准", "note": "最後一道"}],
         "caption": "第 3 步是你提的稽核角色。"},
        {"type": "pyramid", "eyebrow": "先畫框架再動手", "heading": "你的 Skills 金字塔",
         "intro": "同一層彼此不重疊、加起來不遺漏。",
         "top": {"label": "目標", "text": "合約準時定稿"},
         "middle": [{"label": "工作", "text": "會議紀錄"}, {"label": "工作", "text": "報告與溝通"}, {"label": "工作", "text": "合約管理"}],
         "bottom": [{"label": "SKILLS", "items": ["逐字稿整理", "待辦萃取"]},
                    {"label": "SKILLS", "items": ["主管報告", "Email 草稿"]},
                    {"label": "SKILLS", "items": ["修改清單", "風險稽核"]}],
         "caption": "上層是目標 · 中層是工作種類 · 下層是一隻一隻 Skill"},
        {"type": "timeline", "intro": "另一種分法是按時序：", "stages": [
            {"title": "會議前", "note": "整理未決事項"}, {"title": "會議中", "note": "錄音"},
            {"title": "會後 24 小時", "note": "四個產出", "highlight": True}, {"title": "下次會議前", "note": "追進度"}],
         "caption": "蓋到十幾二十個之後會越蓋越快。"},
        {"type": "action", "eyebrow": "答應給你的資源", "title": "《AI 導入說明書》",
         "body": "一個卡關點一章，前四章各留一張表給你填。",
         "button": {"text": "打開《AI 導入說明書》", "url": "https://zynkr.ai/free-resource"},
         "note": "技能市集在 [zynkr.ai/ai-skills-marketplace](https://zynkr.ai/ai-skills-marketplace)。"},
        {"type": "options", "eyebrow": "如果想再往下走", "items": [
            {"title": "線下實戰班", "body": "報名時輸入折扣碼 `EXAMPLE100`", "link": {"text": "看活動和報名 →", "url": "https://zynkr.ai"}}]},
        {"type": "next_steps", "eyebrow": "接下來", "groups": [
            {"owner": "你那邊", "items": ["問資訊單位能不能開 Fireflies 權限"]},
            {"owner": "我這邊", "items": ["月底前寄幾個碰面時段給你"]}]},
    ],
    "closing": ["卡住了歡迎隨時來問。"],
    "signoff": "Peter",
}


def self_test():
    out = build_html(EXAMPLE)
    checks = {
        "one orange button": out.count(f"background:{ORANGE};border-radius:999px;\"><a") == 1,
        "no <style> block (Gmail drops it)": "<style" not in out,
        "no <html>/<head> (it is a fragment)": "<html" not in out and "<head" not in out,
        "logo is a hosted https image": f'src="{LOGO_URL}"' in out,
        "quote wrapped in 「」": "「會議紀錄丟進去" in out,
        "chip rendered": ">EXAMPLE100</span>" in out,
        "markup escaped": "<script" not in build_html({**EXAMPLE, "intro": ["<script>x</script>"]}),
        "fluid width": "max-width:600px" in out and 'width="600"' not in out,
    }
    bad = []
    for broken, why in (
        ({**EXAMPLE, "blocks": EXAMPLE["blocks"] + [EXAMPLE["blocks"][5]]}, "two orange buttons"),
        ({**EXAMPLE, "blocks": [{"type": "flow", "steps": [{"title": "a"}]}]}, "a one-step flow"),
        ({**EXAMPLE, "blocks": [{"type": "next_steps", "groups": [{"items": ["x"]}]}]}, "an ownerless next step"),
        ({**EXAMPLE, "blocks": [{"type": "action", "button": {"text": "x", "url": "http://x"}}]}, "an http link"),
        ({**EXAMPLE, "blocks": [{"type": "bullets"}]}, "an unknown block"),
    ):
        try:
            build_html(broken)
            bad.append(why)
        except PayloadError:
            pass
    checks["refuses: two orange · one-step flow · ownerless step · http link · unknown block"] = not bad
    for name, ok in checks.items():
        print(("PASS  " if ok else "FAIL  ") + name)
    if bad:
        print("      accepted but should refuse: " + ", ".join(bad))
    return 0 if all(checks.values()) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("json_path", nargs="?", help="the recap payload (JSON)")
    ap.add_argument("--out", help="write the HTML here instead of stdout")
    ap.add_argument("--check", action="store_true", help="validate the payload only")
    ap.add_argument("--self-test", action="store_true", help="render the built-in example and assert the invariants")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if not a.json_path:
        ap.error("json_path is required (or --self-test)")
    with open(a.json_path, encoding="utf-8") as f:
        data = json.load(f)
    try:
        html_out = build_html(data)
    except PayloadError as e:
        print(f"recap payload refused: {e}", file=sys.stderr)
        sys.exit(1)
    if a.check:
        print("OK — payload valid")
        return
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(html_out)
    else:
        sys.stdout.write(html_out)


if __name__ == "__main__":
    main()
