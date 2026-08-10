# 🦞 lobster-rss-collect

**龙虾日报 · 统一 RSS 采集器（采集层）**

万物皆可 RSS：读取一个配置文件里的所有信息源，统一抓取、解析、去重，输出标准 JSON 候选池。**零第三方依赖，装好 Python 就能跑。**

---

## 这是什么

龙虾日报是一个"每天自动给你推送定制内容"的开源系统。它由 5 个可独立复用的 skill 组成：

| Skill | 职责 | 阶段 |
|---|---|---|
| **lobster-rss-collect**（本仓库） | 多源采集 → 候选 JSON | ① 采集 |
| lobster-needs-extract | 对话 → 需求信号 → 用户画像 | ② 需求 |
| lobster-score-filter | 候选 × 需求 → Top 3-5 | ③ 评分 |
| lobster-distill | 三级笔记 + 概念提取 | ④ 提炼 |
| lobster-daily-orchestrate | 编排全流程 → 飞书云文档推送 | ⑤ 推送 |

**本仓库只负责①采集**，可以被单独使用，也可以和另外 4 个拼成完整日报。

---

## 安装（3 步）

### 前提

- Python 3.8+（macOS / Linux / Windows 都行）
- 不需要任何第三方库（只用标准库）

### 第 1 步：下载

```bash
git clone https://github.com/你的用户名/lobster-rss-collect.git
cd lobster-rss-collect
```

### 第 2 步：配置你的信息源

编辑 `config/sources.yaml`，填入你想订阅的源：

```yaml
rss_feeds:
  - name: simonwillison
    url: https://simonwillison.net/atom/everything/
    category: ai
    priority: high
```

> 想加源？在 `rss_feeds:` 下加一行即可，**不用改代码**。
> 想要 GitHub 今日趋势？`api_sources:` 下加 `type: github-api` 的条目（默认已配好）。

### 第 3 步：跑起来

```bash
python3 scripts/fetch_rss.py --out candidates.json
```

看输出 `candidates.json`，里面有所有抓到的文章。

---

## 快速上手

```bash
# 抓所有源，每源 30 条
python3 scripts/fetch_rss.py --out candidates.json

# 只抓 AI 分类
python3 scripts/fetch_rss.py --category ai --out ai-candidates.json

# 每源只要 5 条（测试用）
python3 scripts/fetch_rss.py --limit 5

# 指定自己的配置文件
python3 scripts/fetch_rss.py --config /my/path/sources.yaml
```

### 输出格式

```json
[
  {
    "title": "Auto mode is now the default in Claude Code",
    "url": "https://simonwillison.net/...",
    "summary": "Simon Willison 的每周 AI 观察...",
    "published": "2026-08-09T...",
    "source": "simonwillison",
    "category": "ai",
    "priority": "high"
  }
]
```

---

## 信息源配置说明（sources.yaml）

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 源的名字（唯一） |
| `url` | RSS 必填 | RSS feed 地址 |
| `type` | API 必填 | 目前支持 `github-api` |
| `category` | ✅ | 分类：`ai` / `chinese-tech` / `deep-reading` / `product` / `dev`（可自定义） |
| `priority` | 建议 | `high` / `medium` / `low`，供后续评分层参考 |

### 内置默认源（可直接用）

- **AI 核心**：Simon Willison、arXiv（cs.AI / cs.CL / cs.LG）、Hacker News 头版
- **中文科技**：爱范儿、少数派
- **国际深度**：MIT Technology Review、纽约时报中文网
- **产品**：Product Hunt
- **开发**：GitHub 今日趋势（API）

> 💡 经济学人 RSS 有反爬（403），默认未启用。需要时用代理或自建 RSSHub 实例解决。

---

## 常见问题

**Q: 某个源抓失败了会怎样？**
A: 单源失败不影响整体，脚本会跳过并打印 `⚠️` 警告。403 通常是反爬，换代理或移除该源。

**Q: 需要装 feedparser 吗？**
A: 不需要。脚本只用 Python 标准库（urllib + xml.etree），装好 Python 就能跑。

**Q: 能识别哪些 RSS 格式？**
A: RSS 2.0 和 Atom 都支持，自动识别，无需配置。

**Q: 怎么接入完整龙虾日报？**
A: 采集产物传给 `lobster-score-filter` 做评分过滤。完整流程见各 skill 的 README。

---

## 开发 / 贡献

```text
lobster-rss-collect/
├── SKILL.md              # AI agent 视角的流程说明
├── README.md             # 人类视角的安装指南（本文件）
├── config/
│   └── sources.yaml      # 信息源配置（改这里）
└── scripts/
    └── fetch_rss.py      # 统一抓取器（零依赖）
```

欢迎 PR：加新源类型、修解析容错、改进输出格式。

## License

MIT
