---
name: lobster-daily-orchestrate
description: 龙虾日报 · 每日编排推送器（入口 skill）。串起全流程：采集 → 需求倒推 → 评分过滤 → 提炼 → 生成日报 → 推送到飞书云文档。当用户说"跑今天的龙虾日报""生成日报""执行每日流程""跑全流程"或类似指令时使用；也可配置 cron 定时触发。
---

# 龙虾日报 · 每日编排推送器（入口）

## 这个 skill 在干什么

龙虾日报流水线的第五层（也是入口）：**编排推送**。它把前四层串起来，产出最终交付物——飞书云文档链接。

```text
① 采集   lobster-rss-collect    → 候选 JSON
② 需求   lobster-needs-extract  → user-profile.json
③ 评分   lobster-score-filter   → Top N
④ 提炼   lobster-distill        → 笔记 + 概念
⑤ 编排   （本 skill）           → 日报 Markdown → 飞书云文档
```

**最终产物：飞书云文档链接**（含三级笔记 + 概念提取 + 推荐理由），交给用户。

## 执行流程（完整一轮）

### 第 1 步：采集（lobster-rss-collect）

```bash
python3 ~/.agents/skills/lobster-rss-collect/scripts/fetch_rss.py \
  --out /tmp/lobster-candidates.json
```

### 第 2 步：需求倒推（lobster-needs-extract）

```bash
python3 ~/.agents/skills/lobster-needs-extract/scripts/extract_needs.py \
  --days 1
```

### 第 3 步：评分过滤（lobster-score-filter）

```bash
python3 ~/.agents/skills/lobster-score-filter/scripts/score_filter.py \
  --candidates /tmp/lobster-candidates.json \
  --profile ~/.agents/skills/lobster-needs-extract/data/user-profile.json \
  --top 5 --out /tmp/lobster-top.json
```

### 第 4 步：提炼（lobster-distill）

```bash
python3 ~/.agents/skills/lobster-distill/scripts/distill.py \
  --top /tmp/lobster-top.json --out /tmp/lobster-tasks.json
```

对每篇调用 note-taking-pro（三级笔记）+ concept-learning（概念提取），产物写入 `artifacts/distill/`。

### 第 5 步：生成日报 + 推荐理由（本 skill）

```bash
python3 scripts/build_daily.py \
  --top /tmp/lobster-top.json \
  --notes-dir artifacts/distill/ \
  --out artifacts/daily/YYYY-MM-DD.md
```

默认会把每篇的**三级笔记 + 概念提取全文内嵌**进日报（不需要 Notion 页面、不需要排版美化）。然后在日报的「💡 推荐理由」区，为每篇写一句推荐理由（关联哪条需求信号）。

### 第 6 步：推送飞书云文档（feishu-doc）

用 feishu-doc skill 把日报 Markdown 上传为飞书云文档：

1. **创建文档**（`feishu_doc` action=create）：
   ```json
   {"action": "create", "title": "🦞 龙虾日报 2026-08-10", "owner_open_id": "ou_xxx"}
   ```
2. **写入内容**（action=write，整篇替换）：把日报 Markdown 作为 content 写入
3. **返回文档链接**：把 docx 链接发给用户

> 产物 = 飞书云文档链接，内含：今日总览 + 精选文章（三级笔记全文 + 概念提取全文 + 推荐理由）。
> 不需要 Notion、不需要排版美化——飞书里能看到笔记和概念即可。

## 推荐理由写法

每篇一句，必须关联具体需求：

```text
✅ 好：推这篇因为你说过要研究"本地编码 Agent"（画像需求 #1，weight 5.0）
❌ 差：这篇不错，推荐阅读
```

原则：**让用户看到"你为什么推给我"**——这是与通用资讯的本质区别。

## 定时触发（可选）

配置 cron 每天早上 8:00 触发（与内参日报 8:00 可错开，或合并推送）：

```text
schedule: 0 8 * * *  (Asia/Shanghai)
payload: agentTurn 执行本 skill 全流程
```

## 与其他 skill 的协作

```text
lobster-rss-collect      → 采集层
lobster-needs-extract    → 需求层
lobster-score-filter     → 评分层
lobster-distill          → 提炼层
lobster-daily-orchestrate ← 本 skill：编排推送层（入口）
```

## 关键守则

1. **产物 = 飞书云文档链接**：不直接贴长文，给链接 + 摘要。
2. **不做 Notion、不做排版美化**：产物就是三级笔记 + 概念提取 + 推荐理由，飞书里可见即可。
3. **推荐理由必须有**：每篇一句，关联画像需求。
4. **串全流程不跳过**：采集 → 需求 → 评分 → 提炼 → 推送，缺一环产物不完整。
5. **失败记账**：某层失败记录原因，其余层照常，不静默失败。
6. **越聊越懂**：用户反馈（有用/没用）→ 更新画像 → 明天更准。

## 收尾汇报

完成后汇报：

- 今日入选 Top N（标题 + 评分）
- 推荐理由（每篇一句）
- 飞书云文档链接
- 画像更新摘要（新增/强化的需求）
- 各层运行状态（成功/失败）
