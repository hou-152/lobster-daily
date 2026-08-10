# 🦞 lobster-daily-orchestrate

**龙虾日报 · 每日编排推送器（入口 skill）**

把采集 → 需求 → 评分 → 提炼串成一条流水线，最终产物是一份**飞书云文档链接**。越聊越懂你，每天给你定制内容。

---

## 这是什么

龙虾日报的 ⑤（入口）：**一键跑完整条流水线，产物是一份飞书云文档链接**。

| Skill | 职责 | 阶段 |
|---|---|---|
| lobster-rss-collect | 多源采集 → 候选 JSON | ① 采集 |
| lobster-needs-extract | 对话 → 需求画像 | ② 需求 |
| lobster-score-filter | 候选 × 画像 → Top N | ③ 评分 |
| lobster-distill | 三级笔记 + 概念提取 | ④ 提炼 |
| **lobster-daily-orchestrate**（本仓库） | 串全流程 → 飞书云文档 | ⑤ 推送 |

**产物结构**（飞书云文档，无 Notion、无排版美化）：

```
今日总览
  + 精选文章（每篇：三级笔记全文 + 概念提取全文 + 推荐理由）
```

---

## 安装（3 步）

### 前提

- Python 3.8+，无第三方依赖
- 另外 4 个 lobster skill（或只用本仓库的 `build_daily.py` 生成日报 Markdown）

### 第 1 步：下载

```bash
git clone https://github.com/你的用户名/lobster-daily-orchestrate.git
cd lobster-daily-orchestrate
```

### 第 2 步：确认四个前置 skill

```bash
ls ~/.agents/skills/ | grep lobster
# lobster-rss-collect / lobster-needs-extract / lobster-score-filter / lobster-distill
```

缺哪个装哪个（各自仓库 clone 即可）。

### 第 3 步：跑全流程

完整流程见 `SKILL.md`，或只生成日报：

```bash
python3 scripts/build_daily.py --top top.json --out daily.md
```

---

## 快速上手

```bash
# 生成日报 Markdown
python3 scripts/build_daily.py --top /tmp/top.json --notes-dir artifacts/distill/

# 指定日期
python3 scripts/build_daily.py --top top.json --date 2026-08-10

# 预览不写文件
python3 scripts/build_daily.py --top top.json --dry-run
```

### 日报结构

```markdown
# 🦞 龙虾日报（Claw Daily · 20260810 期）
## 📊 今日总览      ← 入选篇数、主题分布
## 📖 今日精选      ← 每篇：标题/来源/评分/摘要/链接
                      + 三级笔记全文 + 概念提取全文
## 💡 推荐理由      ← 每篇一句，关联你的需求画像
## 👀 反馈          ← 告诉它哪篇有用，明天更准
```

推送到飞书：`feishu_doc` action=create 创建文档 → action=write 写入日报 → 返回链接。

---

## 定时推送（cron）

每天早上 8:00 自动跑：

```text
schedule: 0 8 * * *  (Asia/Shanghai)
执行：agentTurn 跑本 skill 全流程 → 上传飞书云文档 → 发送链接
```

---

## 常见问题

**Q: 最终交付物是什么？**
A: **飞书云文档链接**——不是贴长文，是链接 + 摘要。文档内含每篇的三级笔记全文、概念提取全文、推荐理由。不做 Notion 页面、不做排版美化。

**Q: 想跳过某层？**
A: 各层脚本独立，可单独调用。比如只想采集：只跑 lobster-rss-collect。

**Q: 推荐理由怎么写？**
A: 每篇一句，关联画像需求："推这篇因为你说过要研究 XX（需求 weight 5.0）"。

---

## 目录结构

```text
lobster-daily-orchestrate/
├── SKILL.md              # AI agent 视角的完整流程
├── README.md             # 人类视角的安装指南（本文件）
└── scripts/
    └── build_daily.py    # 日报构建器（零依赖）
```

## License

MIT
