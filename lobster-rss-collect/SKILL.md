---
name: lobster-rss-collect
description: 龙虾日报 · 统一 RSS 采集器。万物皆可 RSS：读取 config/sources.yaml 中的信息源配置，统一抓取 RSS feeds 和 API 源（如 GitHub 趋势），去重后输出候选 JSON。当用户说"采集今天的素材""抓取信息源""跑龙虾日报采集层""fetch sources"或类似指令时使用；也可被其他 skill 作为采集子步骤调用。零第三方依赖（Python 标准库），开箱即用。
---

# 龙虾日报 · RSS 采集器（采集层）

## 这个 skill 在干什么

龙虾日报流水线的第一层：**多源采集**。它只做一件事——把配置里的所有信息源抓下来，统一成标准 JSON，去重，输出候选池。不做评分、不做提炼、不推送。

```text
config/sources.yaml
  -> 统一抓取（RSS feeds + GitHub API）
  -> 解析（RSS 2.0 / Atom 自动识别）
  -> 去重（按 url）
  -> 输出候选 JSON（给 score-filter 用）
```

## 设计理念：万物皆可 RSS

所有源统一走 RSS 入口，采集层只写一个解析器：

- **有官方 RSS 的源**（arxiv、媒体、博客）→ 直接抓 RSS
- **有官方 API 的源**（GitHub 趋势）→ API 包装成 feed
- **无源的内容**（微信公众号等）→ 搜索兜底（由 needs-extract 需求信号驱动，本 skill 不负责）

好处：改 `sources.yaml` 一个文件就能增删信息源，**不用改代码**——这是可复用的关键。

## 配置项

所有信息源在 `config/sources.yaml`，结构：

```yaml
rss_feeds:                # 有 RSS 的源
  - name: simonwillison
    url: https://simonwillison.net/atom/everything/
    category: ai          # 分类（ai / chinese-tech / deep-reading / product / dev）
    priority: high        # 优先级（high / medium / low），供评分层参考

api_sources:              # 有 API 的源
  - name: github-trending
    type: github-api      # 当前支持 github-api
    query: "created:>2026-08-09 sort:stars"

search_queries:           # 搜索兜底（需求信号动态填充，本 skill 不执行）
  - name: wechat-fallback
    keywords: []

local_sources:            # 本地素材（不走网络）
  - name: qiaomu-assets
    path: inputs/树林-style-analysis.md
```

## 执行步骤

### 1. 确认配置存在

```bash
ls config/sources.yaml
```

不存在则从模板创建：`cp config/sources.example.yaml config/sources.yaml`（如无模板，告知用户自行填写信息源）。

### 2. 运行采集脚本

```bash
python3 scripts/fetch_rss.py --out /tmp/lobster-candidates.json
```

常用参数：

| 参数 | 作用 |
|---|---|
| `--config PATH` | 指定 sources.yaml 路径（默认读 skill 自带 config/） |
| `--category ai` | 只抓指定分类 |
| `--limit N` | 每源最多取 N 条（默认 30） |
| `--out PATH` | 输出 JSON 文件（不指定则打印到 stdout） |

### 3. 检查结果

脚本 stderr 会打印每个源的抓取状态：

```text
✅ simonwillison: 30 条
⚠️  the-economist: 抓取失败 (HTTP Error 403: Forbidden)
```

**失败源处理规则**：
- 单源失败**不中断整体**，跳过并记录原因
- 403 通常是反爬（如经济学人）→ 从配置移除或换代理/RSSHub 实例
- XML 解析失败 → 脚本已内置容错（控制字符清理 + 裸 & 转义），仍失败则标记该源

### 4. 输出格式

每候选项：

```json
{
  "title": "文章标题",
  "url": "https://...",
  "summary": "摘要",
  "published": "发布时间",
  "source": "来源名（如 simonwillison）",
  "category": "分类（ai / chinese-tech / ...）",
  "priority": "high / medium / low"
}
```

## 与其他 skill 的协作

龙虾日报流水线（共 5 个 skill）：

```text
lobster-rss-collect      ← 本 skill：采集层（RSS/API → 候选 JSON）
lobster-needs-extract    → 需求倒推（对话 → 需求信号 → user-profile.json）
lobster-score-filter     → 评分过滤（候选 × 需求 → Top 3-5）
lobster-distill          → 提炼（三级笔记 + 概念提取）
lobster-daily-orchestrate → 编排推送（串全流程 → 飞书云文档）
```

本 skill 可以被单独复用（只要 RSS 采集），不依赖其他 4 个。

## 关键守则

1. **只采集，不加工**：不评分、不提炼、不写库、不推送。
2. **单源失败不中断**：跳过并记录，让其他源继续。
3. **改配置不改代码**：新增信息源只改 sources.yaml。
4. **零第三方依赖**：只用 Python 标准库，不装 feedparser/PyYAML。
5. **输出去重**：按 url 去重，避免跨源重复。
6. **抓取礼貌**：带 UA、超时 15s、失败重试 2 次（2s/4s 退避）。

## 收尾汇报

完成后汇报：

- 成功源数 / 失败源数（列出失败源和原因）
- 候选总数（去重后）
- 输出文件路径
- 提示用户：下一步是 lobster-score-filter 评分过滤
