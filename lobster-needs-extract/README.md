# 🦞 lobster-needs-extract

**龙虾日报 · 需求倒推器（需求层）**

扫描对话记录，提取用户需求信号（显式 + 隐式），更新需求画像。**系统和用户越聊越懂用户**的核心机制。零第三方依赖。

---

## 这是什么

龙虾日报"每天自动推给你定制内容"的第 ② 步：**从对话里猜你要什么**。

| Skill | 职责 | 阶段 |
|---|---|---|
| lobster-rss-collect | 多源采集 → 候选 JSON | ① 采集 |
| **lobster-needs-extract**（本仓库） | 对话 → 需求信号 → 画像 | ② 需求 |
| lobster-score-filter | 候选 × 画像 → Top 3-5 | ③ 评分 |
| lobster-distill | 三级笔记 + 概念提取 | ④ 提炼 |
| lobster-daily-orchestrate | 编排全流程 → 飞书云文档推送 | ⑤ 推送 |

---

## 安装（3 步）

### 前提

- Python 3.8+，无第三方依赖

### 第 1 步：下载

```bash
git clone https://github.com/你的用户名/lobster-needs-extract.git
cd lobster-needs-extract
```

### 第 2 步：指向你的对话数据

OpenClaw 用户无需配置（默认读 `~/.openclaw-lobster2/agents/main/sessions/`）。

其他 AI 助手用户，把对话导出成文本/JSONL，运行时指定：

```bash
python3 scripts/extract_needs.py --sessions /path/to/your/conversations
```

### 第 3 步：跑起来

```bash
python3 scripts/extract_needs.py
```

---

## 快速上手

```bash
# 扫昨日对话，更新画像
python3 scripts/extract_needs.py

# 扫最近 3 天
python3 scripts/extract_needs.py --days 3

# 只看不写（dry-run）
python3 scripts/extract_needs.py --dry-run

# 指定画像路径
python3 scripts/extract_needs.py --profile data/my-profile.json
```

### 输出

`data/user-profile.json`：

```json
{
  "needs": [
    {"keyword": "AI 工具", "type": "explicit", "weight": 4.5,
     "confidence": 0.8, "first_seen": "2026-08-10T...", "last_seen": "2026-08-10T..."},
    {"keyword": "RSS", "type": "implicit", "weight": 2.0,
     "confidence": 0.6, "first_seen": "...", "last_seen": "..."}
  ]
}
```

---

## 工作机制

1. **清洗**：过滤系统事件（cron 注入）、URL 列表、重复消息——噪音进画像就是污染
2. **显式提取**：规则匹配"我想/我要/我关心/帮我找"等动词短语
3. **隐式提取**：高频主题统计，≥2 次才收录，按频次标置信度
4. **画像更新**：时间衰减（旧需求 ×0.7）+ 权重上限 + 清理低权重 + 上限 50 条

---

## 常见问题

**Q: 提取到的需求不准怎么办？**
A: 规则提取是快速版。需要更精准的语义提取时，可把清洗后的对话喂给 LLM（如 Codex）做结构化提取——脚本的清洗层保证喂给 LLM 的是干净数据。

**Q: 我不是 OpenClaw 用户能用吗？**
A: 能。用 `--sessions` 指向任何 JSONL/文本对话目录。

**Q: 画像会无限膨胀吗？**
A: 不会。时间衰减 + 权重下限（0.3）+ 50 条上限三重机制。

---

## 目录结构

```text
lobster-needs-extract/
├── SKILL.md              # AI agent 视角的流程说明
├── README.md             # 人类视角的安装指南（本文件）
├── scripts/
│   └── extract_needs.py  # 需求倒推器（零依赖）
└── data/
    └── user-profile.json # 需求画像（运行时生成）
```

## License

MIT
