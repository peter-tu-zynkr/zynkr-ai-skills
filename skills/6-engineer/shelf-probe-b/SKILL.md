---
name: shelf-probe-b
sheetId: "6.99"
description: "上架流程的暫時測試，只會短暫上架，請勿安裝 · A temporary test of the public shelf, listed only briefly: it does nothing, so please do not install it. Zynkr Atlas uses it, with shelf-probe-a, to see its public shelf work for real (ATL-113, AC-14 and AC-16): a new public skill waits for the owner's sign-off, reaches the shelf once signed off, and leaves it when its own file is marked team, even while the shelf cannot ask Atlas."
category: engineer
project: shelf-probe-b
platform: claude
status: WIP
visibility: public
author: Peter Tu
disable-model-invocation: true
input: "Nothing: the skill takes no input."
process: "Says that it is a temporary test of the public shelf, then stops."
output: "One line saying that this skill is a test and does nothing."
synergy: []
house-style: exempt — test fixture, prints one fixed line and no prose
---

# shelf-probe-b

```bash
npx skills add https://github.com/peter-tu-zynkr/zynkr-ai-skills --skill shelf-probe-b
```

**A temporary test of the public shelf. It does nothing, so please do not install it.** 這是上架流程的暫時測試，不做任何事，請勿安裝；測試結束就會移除。

Zynkr Atlas uses this folder, with `shelf-probe-a`, to watch its public shelf do three things for real (`ATL-113`, AC-14 to AC-16): a new public skill waits off the shelf until the owner signs it off in Atlas (同意上架), reaches the shelf and zynkr.ai at the next run after, and leaves again. This one leaves when its own file is marked team, even while the shelf cannot ask Atlas (AC-16). Both folders are deleted from the workbench once the test is done, and their sheetIds, 6.98 and 6.99, are retired with them.

---

## Workflow

1. Say this one line, and nothing else: "shelf-probe-b is a temporary test of the public shelf, and it does nothing."
2. Stop. Read no file, write no file and call no tool.
