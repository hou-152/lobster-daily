# 🦞 lobster-distill

**龙虾日报 · 提炼编排器（提炼层）**

把入选内容变成两份知识产物：**三级笔记 + 概念提取**。复用现有引擎，零重造。

---

## 这是什么

龙虾日报的第 ④ 步：**把选出来的内容吃透，变成笔记和概念**。

| Skill | 职责 | 阶段 |
|---|---|---|
| lobster-rss-collect | 多源采集 → 候选 JSON | ① 采集 |
| lobster-needs-extract | 对话 → 需求画像 | ② 需求 |
| lobster-score-filter | 候选 × 画像 → Top N | ③ 评分 |
| **lobster-distill**（本仓库） | 三级笔记 + 概念提取 | ④ 提炼 |
| lobster-daily-orchestrate | 编排全流程 → 飞书云文档推送 | ⑤ 推送 |

---

## 安装（3 步）

### 前提

- Python 3.8+，无第三方依赖
- 可选：`note-taking-pro`、`concept-learning` skill（笔记/概念引擎）

### 第 1 步：下载

```bash
git clone https://github.com/你的用户名/lobster-distill.git
cd lobster-distill
```

### 第 2 步：准备输入

- 入选 JSON：由 lobster-score-filter 生成（`[{title, url, summary, _score}]`）

### 第 3 步：生成任务清单

```bash
python3 scripts/distill.py --top top.json --out tasks.json
```

---

## 快速上手

```bash
# 生成提炼任务清单
python3 scripts/distill.py --top /tmp/top.json --out /tmp/tasks.json

# 指定产物目录
python3 scripts/distill.py --top top.json --out-dir artifacts/distill
```

### 任务清单结构

```json
{
  "tasks": [
    {
      "title": "Using Local Coding Agents",
      "url": "https://...",
      "note_path": "artifacts/distill/xxx-notes.md",
      "concept_path": "artifacts/distill/xxx-concepts.md"
    }
  ]
}
```

---

## 工作机制

本 skill **只做编排，不代写笔记**：

1. 读入选 JSON → 每篇生成两个任务（笔记 + 概念）
2. 由 AI agent 调用 `note-taking-pro`（三级笔记）和 `concept-learning`（概念辞典）
3. 产物写入 `artifacts/distill/`，双产物互不串扰

---

## 常见问题

**Q: 为什么脚本不直接写笔记？**
A: 笔记/概念是语义任务，需要 LLM。脚本负责编排和归档，引擎复用现有 skill——不重复造轮子。

**Q: 没有那两个 skill 能用吗？**
A: 能。任务清单照常生成，你可以用自己的方式完成提炼，或接入任意 LLM。

---

## 目录结构

```text
lobster-distill/
├── SKILL.md              # AI agent 视角的流程说明
├── README.md             # 人类视角的安装指南（本文件）
└── scripts/
    └── distill.py        # 提炼编排器（零依赖）
```

## License

MIT
