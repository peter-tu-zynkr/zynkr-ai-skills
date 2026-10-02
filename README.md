# Zynkr AI Skills

Zynkr 公開的 AI 技能（Claude Code skills）· Zynkr's public AI skills for Claude Code

[中文](#中文) · [English](#english)

## 中文

### 這是什麼

這個 repo 收錄 Zynkr 標記為公開的 AI 技能，由 Zynkr 內部的技能工作台自動匯出。每次匯出都是一筆 `export:` 提交，最後一行的 `Workbench-Commit:` 記下它來自哪個版本。

技能的修改都在上游完成，這裡只是匯出結果，請不要對 `skills/` 開 pull request，下一次匯出會把它覆蓋掉。

### 安裝

```sh
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill <name>
```

`<name>` 是技能 `SKILL.md` 開頭的 `name`。到 [zynkr.ai 技能市集](https://zynkr.ai/ai-skills-marketplace) 瀏覽全部技能，每張卡片都附上它的安裝指令。

### 從舊 repo 搬過來

這些技能以前放在 `peter-tu-zynkr/zynkr-skill-builder`。從那裡裝的舊版本不會自動跟過來，請用上面的指令從這裡重新安裝。

### 授權

這個 repo 沒有授予任何授權，保留一切權利。取自其他作者的技能，在各自 `SKILL.md` 的 frontmatter 保留原作者署名（`author`、`original_author`、`upstream_repo`、`original_source_url`）。

### 問題回報

請到 [zynkr.ai 聯絡頁](https://zynkr.ai/support#contact) 告訴我們。

## English

### What this is

This repo holds the AI skills Zynkr has marked public, exported automatically from Zynkr's internal skills workbench. Every export is one `export:` commit whose last line, `Workbench-Commit:`, records the version it came from.

Skills are changed upstream; this repo is the exported result. Please do not open pull requests against `skills/`: the next export overwrites them.

### Install

```sh
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill <name>
```

`<name>` is the `name` at the top of the skill's `SKILL.md`. Browse every skill on the [zynkr.ai skills marketplace](https://zynkr.ai/ai-skills-marketplace); each card shows its install command.

### Moved from the old repo

These skills used to live in `peter-tu-zynkr/zynkr-skill-builder`. Copies installed from there cannot follow the move: re-add them from here with the command above.

### Licence

No licence is granted: all rights reserved. Skills adopted from other authors keep their authors' attribution in their `SKILL.md` frontmatter (`author`, `original_author`, `upstream_repo`, `original_source_url`).

### Issues

Please tell us through the [zynkr.ai contact page](https://zynkr.ai/support#contact).
