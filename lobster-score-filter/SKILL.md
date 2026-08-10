---
name: lobster-score-filter
description: 龙虾日报 · AI 评分过滤器。输入采集候选 JSON 和需求画像，按相关性 × 质量双评分，过滤并输出 Top N 入选内容。当用户说"给候选评分""过滤素材""跑评分层""选出今日 Top"或类似指令时使用；也可被其他 skill 作为评分子步骤调用。零第三方依赖，开箱即用。
---

# 龙虾日报 · AI 评分过滤器（评分层）

## 这个 skill 在干什么

龙虾日报流水线的第三层：**评分过滤**。它回答一个问题——"候选素材里，哪些与你最相关？"

```text
采集候选（lobster-rss-collect 输出 JSON）
  + 需求画像（lobster-needs-extract 输出 user-profile.json）
  -> 相关性 × 质量 双评分
  -> 阈值过滤 + Top N 排序
  -> 入选 JSON（给 distill 提炼）
```

## 评分模型

**综合分 = 相关性 × 60% + 质量 × 40%**

### 相关性（0-5）：候选与需求画像的匹配度
- 遍历画像 Top 20 需求，候选标题/摘要包含需求关键词或关键词重叠 → 计分
- 按需求权重 × 置信度累加
- 分类偏好加成（ai 类默认 +1.2，其他递减）
- 无画像时给中性分 1.0

### 质量（0-5）：来源 + 新鲜度 + 内容
- 来源优先级：high=1.5 / medium=1.0 / low=0.5
- 新鲜度：24h 内满分 2.0，一周以上 0.5
- 内容长度：摘要 ≥200 字满分 1.5，无摘要 0

## 配置项

| 项目 | 默认值 | 说明 |
|---|---|---|
| 候选文件 | `--candidates`（必填） | 采集层输出 |
| 画像文件 | `--profile`（可选） | 需求画像；缺省时给中性相关性分 |
| 入选数量 | `--top 5` | Top N |
| 最低分 | `--min-score 1.5` | 低于阈值不入选 |

## 执行步骤

### 1. 运行评分

```bash
python3 scripts/score_filter.py \
  --candidates /tmp/candidates.json \
  --profile data/user-profile.json \
  --top 5 --out /tmp/top.json
```

### 2. 检查入选

脚本打印：

```text
🏆 入选 Top 5（阈值 1.5）:
  4.3 (rel=5.0 q=3.3) | [source] Title
```

每条的 `_score` 字段保留相关性/质量/综合分，供 distill 和用户回溯。

### 3. 输出格式

```json
[
  {
    "title": "...",
    "url": "...",
    "summary": "...",
    "source": "...",
    "category": "...",
    "priority": "...",
    "_score": {"relevance": 5.0, "quality": 3.3, "total": 4.3}
  }
]
```

## 与其他 skill 的协作

```text
lobster-rss-collect      → 采集层（候选 JSON）
lobster-needs-extract    → 需求层（画像）
lobster-score-filter     ← 本 skill：评分层（候选 × 画像 → Top N）
lobster-distill          → 提炼（Top N → 三级笔记 + 概念提取）
lobster-daily-orchestrate → 编排推送（串全流程 → 飞书云文档）
```

本 skill 可被单独复用：任何"内容 × 用户画像 → 精选"的场景。

## 关键守则

1. **相关性优先**：权重 60%，画像越准，推荐越准。
2. **双评分不混**：相关性和质量分开计算，综合分加权，不拍脑袋。
3. **阈值可调**：`--min-score` 控制入选门槛，口味不同调参即可。
4. **画像缺省不崩**：无画像时给中性分，系统仍能跑。
5. **零第三方依赖**：只用 Python 标准库。

## 收尾汇报

完成后汇报：

- 候选总数、画像需求数
- 入选 Top N（含综合分/相关性/质量）
- 阈值内被过滤的数量
- 提示用户：下一步是 lobster-distill 对入选内容做三级笔记 + 概念提取
