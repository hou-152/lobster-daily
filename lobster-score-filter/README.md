# 🦞 lobster-score-filter

**龙虾日报 · AI 评分过滤器（评分层）**

候选素材 × 你的需求画像 → 双评分 → Top N 精选。零第三方依赖。

---

## 这是什么

龙虾日报的第 ③ 步：**从一堆抓来的素材里，选出和你最相关的**。

| Skill | 职责 | 阶段 |
|---|---|---|
| lobster-rss-collect | 多源采集 → 候选 JSON | ① 采集 |
| lobster-needs-extract | 对话 → 需求画像 | ② 需求 |
| **lobster-score-filter**（本仓库） | 候选 × 画像 → Top N | ③ 评分 |
| lobster-distill | 三级笔记 + 概念提取 | ④ 提炼 |
| lobster-daily-orchestrate | 编排全流程 → 飞书云文档推送 | ⑤ 推送 |

---

## 安装（3 步）

### 前提

- Python 3.8+，无第三方依赖

### 第 1 步：下载

```bash
git clone https://github.com/你的用户名/lobster-score-filter.git
cd lobster-score-filter
```

### 第 2 步：准备输入

- 候选 JSON：由 lobster-rss-collect 生成（或任何 `[{title, url, summary, source, category, priority}]` 格式）
- 画像 JSON（可选）：由 lobster-needs-extract 生成（`{needs: [{keyword, weight, confidence}]}`）

### 第 3 步：跑起来

```bash
python3 scripts/score_filter.py \
  --candidates candidates.json \
  --profile user-profile.json \
  --top 5
```

---

## 快速上手

```bash
# 基础用法：Top 5
python3 scripts/score_filter.py --candidates candidates.json --profile profile.json

# 只要 3 条
python3 scripts/score_filter.py --candidates candidates.json --top 3

# 提高入选门槛（更挑剔）
python3 scripts/score_filter.py --candidates candidates.json --min-score 3.0

# 没有画像也能跑（中性相关性）
python3 scripts/score_filter.py --candidates candidates.json
```

### 输出

入选 JSON（含评分）：

```json
[
  {
    "title": "Using Local Coding Agents",
    "url": "https://...",
    "source": "sebastianraschka",
    "_score": {"relevance": 5.0, "quality": 3.3, "total": 4.3}
  }
]
```

---

## 评分机制

```
综合分 = 相关性 × 60% + 质量 × 40%
```

**相关性**（和你的画像匹配度）：
- 候选标题/摘要 与 画像需求关键词 重叠 → 计分
- 权重高的需求命中 → 分更高
- AI 类内容默认加成（通用偏好）

**质量**（内容本身）：
- 来源优先级（high/medium/low）
- 新鲜度（24h 内满分，越旧越低）
- 内容完整度（有摘要比裸标题好）

---

## 常见问题

**Q: 入选太少/太多？**
A: 调 `--min-score`（门槛）和 `--top`（数量）。画像越准，精选越准。

**Q: 没有画像能用吗？**
A: 能。相关性给中性分，纯按质量排序——相当于"通用精选"模式。

**Q: 想给某类内容加权？**
A: 在画像里加对应需求词即可（如"AI 工具"），或调 `CATEGORY_PREF` 常量。

---

## 目录结构

```text
lobster-score-filter/
├── SKILL.md              # AI agent 视角的流程说明
├── README.md             # 人类视角的安装指南（本文件）
└── scripts/
    └── score_filter.py   # 评分过滤器（零依赖）
```

## License

MIT
