# 🦞 龙虾日报（Lobster Daily）

**越聊越懂你的 AI 定制日报系统。** 每天自动从你的信息源采集素材，根据你的对话需求画像评分精选，生成含三级笔记 + 概念提取 + 推荐理由的日报，推送到飞书云文档。

## 这是什么

龙虾日报是一套开源的个性化信息推送系统，由 5 个可独立复用的 skill 组成：

| # | Skill | 职责 | 阶段 |
|---|---|---|---|
| 1 | `lobster-rss-collect` | 多源采集（RSS + API → 候选 JSON） | ① 采集 |
| 2 | `lobster-needs-extract` | 需求倒推（对话 → 需求画像） | ② 需求 |
| 3 | `lobster-score-filter` | 评分过滤（候选 × 画像 → Top N） | ③ 评分 |
| 4 | `lobster-distill` | 提炼（三级笔记 + 概念提取） | ④ 提炼 |
| 5 | `lobster-daily-orchestrate` | 编排推送（串全流程 → 飞书云文档） | ⑤ 推送 |

**核心机制**：扫描你的对话 → 提取需求信号（显式 + 隐式）→ 更新画像 → 用画像给候选内容评分 → 只推与你相关的。**你和系统聊得越多，推荐越准。**

## 快速开始（3 步）

### 1. 安装 skill

把 5 个 skill 目录复制到你的 skill 目录：

```bash
cp -R lobster-*/ ~/.agents/skills/
```

### 2. 配置信息源

编辑 `lobster-rss-collect/config/sources.yaml`，填入你想订阅的源：

```yaml
rss_feeds:
  - name: simonwillison
    url: https://simonwillison.net/atom/everything/
    category: ai
    priority: high
```

### 3. 跑全流程

```bash
# ① 采集
python3 ~/.agents/skills/lobster-rss-collect/scripts/fetch_rss.py --out /tmp/candidates.json

# ② 需求倒推
python3 ~/.agents/skills/lobster-needs-extract/scripts/extract_needs.py --days 1

# ③ 评分过滤
python3 ~/.agents/skills/lobster-score-filter/scripts/score_filter.py \
  --candidates /tmp/candidates.json \
  --profile ~/.agents/skills/lobster-needs-extract/data/user-profile.json \
  --top 5 --out /tmp/top.json

# ④ 提炼（需要 LLM，见各 skill README）
python3 ~/.agents/skills/lobster-distill/scripts/distill.py --top /tmp/top.json

# ⑤ 生成日报
python3 ~/.agents/skills/lobster-daily-orchestrate/scripts/build_daily.py \
  --top /tmp/top.json --notes-dir artifacts/distill/ --out /tmp/daily.md
```

## 产物结构

最终交付物是**飞书云文档链接**，内含：

```markdown
# 🦞 龙虾日报（Claw Daily · YYYYMMDD 期）
## 📊 今日总览       ← 入选篇数、主题分布
## 📖 今日精选       ← 每篇：标题/来源/评分/摘要/链接
                      + 📝 三级笔记全文（一句话主旨/问题/论证骨架/边界）
                      + 🧠 概念提取全文（context 原话/费曼解释/架构图）
## 💡 推荐理由       ← 每篇一句，关联你的需求画像
## 👀 反馈           ← 有用/没用，明天更准
```

## 设计理念

- **万物皆可 RSS**：所有源统一走 RSS 入口，采集层只写一个解析器
- **零第三方依赖**：所有脚本只用 Python 标准库，clone 就能跑
- **改配置不改代码**：加信息源只改 `sources.yaml`
- **越聊越懂**：需求画像持续更新，时间衰减 + 置信度
- **少而精**：默认源宁缺毋滥，评分阈值可调

## 飞书推送配置

飞书推送需要（见 `lobster-daily-orchestrate/SKILL.md`）：
1. 飞书开放平台应用，开通 `docx:document`、`drive:drive` 权限
2. 获取 `app_id` / `app_secret`
3. 用 `feishu_doc` 工具或飞书 API 创建文档 → 写入 → 返回链接

## 定时推送（可选）

配置 cron 每天早上 8:00 触发：

```text
schedule: 0 8 * * *  (Asia/Shanghai)
执行：跑全流程 → 推送飞书云文档链接
```

## License

MIT
