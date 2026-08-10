---
name: lobster-distill
description: 龙虾日报 · 提炼编排器。读取评分层入选 JSON，为每篇生成提炼任务清单（三级笔记 + 概念提取），分别调用 note-taking-pro 和 concept-learning skill 完成产物。当用户说"提炼入选内容""生成笔记和概念""跑提炼层"或类似指令时使用。零第三方依赖。
---

# 龙虾日报 · 提炼编排器（提炼层）

## 这个 skill 在干什么

龙虾日报流水线的第四层：**提炼**。把入选的 Top N 内容，变成两份可复用的知识产物：

```text
入选 JSON（lobster-score-filter 输出）
  -> 任务清单（每篇两个任务）
  -> 三级笔记（note-taking-pro skill）
  -> 概念提取（concept-learning skill）
  -> artifacts/distill/ 产物目录
```

**它不自己写笔记**——笔记和概念由两个专业 skill 完成，本 skill 只做编排（生成任务、记录路径、管理产物）。

## 设计理念：复用，不重造

笔记和概念提取的引擎已经存在：

- **note-taking-pro**：结构化大纲笔记（三级笔记）
- **concept-learning**：概念解析辞典（费曼 + 概念网络）

本 skill 不重复实现它们，只负责：把入选内容 → 正确的输入 → 两个 skill → 产物归档。这是"减"——不加重复功能。

## 执行步骤

### 1. 生成任务清单

```bash
python3 scripts/distill.py --top /tmp/top.json --out /tmp/tasks.json
```

### 2. 对每篇执行提炼（由 AI agent 完成）

任务清单里的每篇，执行两个独立步骤：

1. 调用 **note-taking-pro**：输入原文 → 三级笔记 → 写入 `note_path`
2. 调用 **concept-learning**：输入原文 → 概念辞典 → 写入 `concept_path`

**两个产物互不依赖、互不串扰**（和 neican-editing 的规则一致）。

### 3. 产物归档

```text
artifacts/distill/
  {source}-{n}-notes.md      # 三级笔记
  {source}-{n}-concepts.md   # 概念辞典
```

## 与其他 skill 的协作

```text
lobster-rss-collect      → 采集层（候选 JSON）
lobster-needs-extract    → 需求层（画像）
lobster-score-filter     → 评分层（Top N）
lobster-distill          ← 本 skill：提炼层（Top N → 笔记+概念）
lobster-daily-orchestrate → 编排推送（串全流程 → 飞书云文档）
```

## 关键守则

1. **只编排，不代写**：笔记/概念交给 note-taking-pro 和 concept-learning。
2. **双产物不串扰**：三级笔记和概念提取输入都是原文，互不依赖。
3. **失败就跳过+记账**：单篇失败不中断整批。
4. **零第三方依赖**：脚本只用 Python 标准库。

## 收尾汇报

完成后汇报：

- 入选篇数
- 成功生成笔记/概念的篇数
- 产物路径列表
- 失败篇数及原因
- 提示用户：下一步是 lobster-daily-orchestrate 汇总成日报
