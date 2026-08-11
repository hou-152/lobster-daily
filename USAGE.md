# 🦞 龙虾日报 · 使用教学（教师指南）

> 本文档写给 Codex / 任何 AI Agent：如何使用「龙虾日报」系统完成每日定制推送。
> 系统已开源：https://github.com/hou-152/lobster-daily

## 系统是什么

龙虾日报是一套"越聊越懂你"的个性化日报系统，5 个 skill 串成流水线：

```text
① 采集（lobster-rss-collect）→ 候选 JSON
② 需求（lobster-needs-extract）→ 需求画像 user-profile.json
③ 评分（lobster-score-filter）→ Top N
④ 提炼（lobster-distill）→ 三级笔记 + 概念提取
⑤ 编排（lobster-daily-orchestrate）→ 日报 → 飞书云文档
```

## 安装（3 步，已验证可用）

### 第 1 步：下载 skill

```bash
git clone https://github.com/hou-152/lobster-daily.git
# 把 5 个 lobster-* 目录复制到你的 skill 目录
cp -R lobster-* ~/.agents/skills/
```

### 第 2 步：配置信息源

编辑 `lobster-rss-collect/config/sources.yaml`：

```yaml
rss_feeds:
  - name: simonwillison
    url: https://simonwillison.net/atom/everything/
    category: ai
    priority: high
```

> 加源 = 加一行，不用改代码。默认已含 19 个 RSS 源（其中 3 个 arxiv，另配搜索/学术通道）。

### 第 3 步：跑全流程（两条路径任选）

**路径 A：一键入口（推荐）**

```bash
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/run_daily.py --dry-run   # 预演
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/run_daily.py             # 本地全流程
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/run_daily.py --push-feishu  # +飞书推送
```

**路径 B：分步执行（需要调试时）**

```bash
# ① 采集
python3 ~/.agents/skills/lobster-rss-collect/scripts/fetch_rss.py --out /tmp/candidates.json

# ② 需求倒推（读最近1天对话）
python3 ~/.agents/skills/lobster-needs-extract/scripts/extract_needs.py --days 1

# ③ 评分过滤
python3 ~/.agents/skills/lobster-score-filter/scripts/score_filter.py \
  --candidates /tmp/candidates.json \
  --profile ~/.agents/skills/lobster-needs-extract/data/user-profile.json \
  --top 5 --out /tmp/top.json

# ④ 提炼（生成任务清单，笔记/概念由 Agent 完成）
python3 ~/.agents/skills/lobster-distill/scripts/distill.py --top /tmp/top.json --out /tmp/tasks.json

# ⑤ 日报 + Mermaid 转图
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/build_daily.py \
  --top /tmp/top.json --profile <画像> --notes-dir <笔记目录> --out /tmp/daily.md
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/render_mermaid.py \
  --input /tmp/daily.md --output /tmp/daily-rendered.md --images-dir artifacts/images

# ⑥ 飞书推送（需 FEISHU_APP_ID / FEISHU_APP_SECRET）
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/push_feishu.py \
  --input /tmp/daily-rendered.md --title "🦞 龙虾日报 2026-08-10"
```

## 环境预检

```bash
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/doctor.py       # 全量
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/doctor.py --feishu  # 只查飞书
```

## 关键文件

| 文件 | 作用 |
|---|---|
| `lobster-rss-collect/config/sources.yaml` | 信息源配置（改这里加源） |
| `lobster-needs-extract/data/user-profile.json` | 需求画像（系统自动更新） |
| `lobster-daily-orchestrate/scripts/run_daily.py` | 一键入口 |
| `lobster-daily-orchestrate/scripts/doctor.py` | 环境预检 |
| `lobster-daily-orchestrate/scripts/render_mermaid.py` | Mermaid 架构图转 PNG |
| `lobster-daily-orchestrate/scripts/push_feishu.py` | 飞书云文档推送 |

## 飞书推送配置（一次性）

1. 飞书开放平台创建"企业自建应用"
2. 开通权限：docx 文档读写、drive 文件/文件夹、`drive:file:upload`
3. 配置环境变量：

```bash
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=***
export FEISHU_OWNER_OPEN_ID=ou_xxx
```

4. `python3 doctor.py --feishu` 验证通过后即可推送

## 每日自动运行（cron）

```text
schedule: 0 8 * * *（Asia/Shanghai）
执行：run_daily.py --push-feishu
交付：飞书云文档链接
```

## 常见问题

| 问题 | 解决 |
|---|---|
| 某源抓取失败 | 单源失败不影响整体，⚠️ 记录原因继续 |
| 画像没有更新 | 确认 `--sessions` 指向真实对话目录 |
| Mermaid 图是文本 | 先跑 render_mermaid.py 再推送 |
| 飞书 403 | 缺权限，`doctor.py --feishu` 看缺哪个 scope |
| 想改入选数量 | `--top N` |

## 输出物结构

```markdown
# 🦞 龙虾日报（Claw Daily · YYYYMMDD 期）
## 📊 今日总览
## 📖 今日精选（每篇：三级笔记全文 + 概念提取全文 + 架构图）
## 💡 推荐理由（每篇一句，关联画像需求）
## 👀 反馈
```
