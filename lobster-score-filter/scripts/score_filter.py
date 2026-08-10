#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-score-filter · AI 评分过滤器

输入：采集候选 JSON + 需求画像 user-profile.json
输出：相关性 × 质量 双评分，Top N 入选

相关性 = 候选内容与用户需求画像的匹配度（关键词重叠 + 分类偏好）
质量   = 基础质量分（来源优先级 + 发布时间新鲜度 + 内容长度）

零第三方依赖：只用 Python 标准库。

用法：
    python3 score_filter.py --candidates /tmp/candidates.json --profile data/user-profile.json
    python3 score_filter.py --candidates /tmp/candidates.json --top 5
    python3 score_filter.py --candidates /tmp/candidates.json --min-score 2.0

输出：入选 JSON（Top N，按综合分排序）
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PRIORITY_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.5}
# 信息层级加权：一手 +0.5 / 二手 +0.3 / 三手 +0（四手已由采集层黑名单/营销词过滤）
TIER_WEIGHT = {1: 0.5, 2: 0.3, 3: 0.0}
# 分类偏好：默认均衡（不从画像学时不给 AI 特殊加成，避免硬编码偏见）
# 分类权重实际由画像命中度驱动；此表仅作无画像时的兜底
CATEGORY_PREF = {
    "ai": 1.0,
    "dev": 1.0,
    "chinese-tech": 1.0,
    "deep-reading": 1.0,
    "product": 1.0,
    "podcast": 1.0,
    "science": 1.0,   # q-bio.NC 等学术一手源（泛化：源配置不为单一用户画像服务）
    "social": 1.0,
    "wechat": 1.0,
    "other": 1.0,
}


def parse_date(published: str):
    """解析各种时间格式，失败返回 None。"""
    if not published:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d"):
        try:
            return datetime.strptime(published.strip(), fmt)
        except ValueError:
            continue
    return None


def tokenize(text: str) -> set:
    """提取关键词集合（中文片段 + 英文词）。"""
    tokens = set()
    if not text:
        return tokens
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,8}", text))
    tokens.update(re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,20}", text.lower()))
    # 过滤常见噪音
    tokens.discard("https")
    tokens.discard("com")
    tokens.discard("www")
    return tokens


def keyword_hit(keyword: str, title: str, summary: str) -> bool:
    """判断需求关键词是否命中候选内容（修正子串匹配问题）。

    规则：
    - 英文关键词：前后不是英文字母/数字才算命中（Codex 可匹配 Codex反代；AI 不匹配 RAILWAY）
    - 中文关键词：>=4 字整串匹配算强命中；2-3 字短词不单独命中（避免"学习"泛匹配）
    - 其他（混合/短词）：直接子串
    """
    if not keyword or len(keyword) < 2:
        return False
    text = f"{title} {summary[:500]}".lower()
    kw = keyword.lower()

    # 英文/数字词：前后不能是英文字母或数字（中文不算边界，可紧邻）
    if re.fullmatch(r"[a-z0-9][a-z0-9\-]*", kw):
        return re.search(rf"(?<![a-zA-Z0-9]){re.escape(kw)}(?![a-zA-Z0-9])", text) is not None

    # 中文：>=4 字整串匹配才算强命中；2-3 字短词不单独命中
    if re.search(r"[\u4e00-\u9fff]", kw):
        return len(kw) >= 4 and kw in text

    # 其他：直接子串
    return kw in text


def relevance_score(candidate: dict, needs: list) -> float:
    """相关性：候选内容与需求画像的匹配度（0-5）。"""
    if not needs:
        return 1.0  # 无画像时给中性分

    title = candidate.get("title", "")
    summary = candidate.get("summary", "")
    category = candidate.get("category", "other")

    # 候选关键词（用于 token 重叠兜底）
    cand_tokens = tokenize(title + " " + summary[:500])

    score = 0.0
    matched = 0
    for need in needs[:20]:  # 只比对 top 20 需求
        keyword = need.get("keyword", "")
        if not keyword or len(keyword) < 2:
            continue
        # 主路径：修正后的精确匹配
        if keyword_hit(keyword, title, summary):
            weight = need.get("weight", 1.0)
            confidence = need.get("confidence", 0.5)
            score += weight * confidence
            matched += 1
            continue
        # 兜底：中文短词（2-3字）通过 token 重叠判断，避免"学习"泛匹配
        kw_tokens = tokenize(keyword)
        if kw_tokens and len(keyword) <= 3 and (kw_tokens & cand_tokens):
            weight = need.get("weight", 1.0)
            confidence = need.get("confidence", 0.5)
            score += weight * confidence * 0.3  # 短词命中降权
            matched += 1

    # 分类偏好加成（画像里高频的分类）
    if category in CATEGORY_PREF:
        score += CATEGORY_PREF[category] * 0.3

    # 归一化到 0-5
    return min(5.0, score + matched * 0.5)


def matched_need_keywords(candidate: dict, needs: list) -> list:
    """返回对相关性产生正贡献的需求关键词，不改变评分算法。"""
    title = candidate.get("title", "")
    summary = candidate.get("summary", "")
    cand_tokens = tokenize(title + " " + summary[:500])
    hits = []
    for need in needs[:20]:
        keyword = need.get("keyword", "")
        if not keyword or len(keyword) < 2:
            continue
        if keyword_hit(keyword, title, summary):
            hits.append(keyword)
            continue
        kw_tokens = tokenize(keyword)
        if kw_tokens and len(keyword) <= 3 and (kw_tokens & cand_tokens):
            hits.append(keyword)
    return hits


def quality_score(candidate: dict) -> float:
    """质量：来源优先级 + 新鲜度 + 内容长度（0-5）。"""
    score = 0.0

    # 来源优先级（0-1.5）
    priority = candidate.get("priority", "medium")
    score += PRIORITY_WEIGHT.get(priority, 1.0)

    # 新鲜度（0-2）：越新分越高
    published = parse_date(candidate.get("published", ""))
    if published:
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)  # 无时区按 UTC 处理
        age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
        if age_hours <= 24:
            score += 2.0
        elif age_hours <= 72:
            score += 1.5
        elif age_hours <= 168:
            score += 1.0
        else:
            score += 0.5
    else:
        score += 0.8  # 无时间信息给中低分

    # 内容长度（0-1.5）：有摘要的比裸标题好
    summary_len = len(candidate.get("summary", "") or "")
    if summary_len >= 200:
        score += 1.5
    elif summary_len >= 80:
        score += 1.0
    elif summary_len > 0:
        score += 0.5

    return min(5.0, score)


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · AI 评分过滤器")
    parser.add_argument("--candidates", required=True, help="采集候选 JSON 路径")
    parser.add_argument("--profile", default=None, help="需求画像 JSON 路径")
    parser.add_argument("--top", type=int, default=5, help="入选数量")
    parser.add_argument("--min-score", type=float, default=1.5, help="最低综合分")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--hits-log", default=None, help="需求命中日志 JSONL 路径（缺省不写）")
    args = parser.parse_args()

    # 读候选
    cand_path = Path(args.candidates)
    if not cand_path.exists():
        print(f"❌ 找不到候选文件: {cand_path}", file=sys.stderr)
        sys.exit(1)
    candidates = json.loads(cand_path.read_text(encoding="utf-8"))
    print(f"📥 候选: {len(candidates)} 条", file=sys.stderr)

    # 读画像
    needs = []
    if args.profile:
        prof_path = Path(args.profile)
        if prof_path.exists():
            profile = json.loads(prof_path.read_text(encoding="utf-8"))
            needs = profile.get("needs", [])
            print(f"🧠 画像需求: {len(needs)} 条", file=sys.stderr)

    # 双评分 + tier 加成：tier 不进 quality 的 5.0 封顶（否则高质量候选的 tier 加权被吞）
    scored = []
    for cand in candidates:
        rel = relevance_score(cand, needs)
        qual = quality_score(cand)
        tier_bonus = TIER_WEIGHT.get(cand.get("tier", 3), 0.0)
        total = rel * 0.6 + qual * 0.4 + tier_bonus  # 相关性 60% + 质量 40% + 信息层级加成
        scored.append({**cand, "_score": {"relevance": round(rel, 2), "quality": round(qual, 2), "total": round(total, 2)}})

    # 过滤 + 排序
    all_scored = scored
    scored = [s for s in all_scored if s["_score"]["total"] >= args.min_score]
    scored.sort(key=lambda s: s["_score"]["total"], reverse=True)
    top = scored[: args.top]

    if args.hits_log:
        hits_path = Path(args.hits_log)
        hits_path.parent.mkdir(parents=True, exist_ok=True)
        top_ids = {id(item) for item in top}
        today = datetime.now(timezone.utc).date().isoformat()
        with hits_path.open("a", encoding="utf-8") as fh:
            for candidate in all_scored:
                for keyword in matched_need_keywords(candidate, needs):
                    row = {
                        "date": today,
                        "keyword": keyword,
                        "in_top": id(candidate) in top_ids,
                        "candidate_title": candidate.get("title", ""),
                        "score": candidate["_score"]["total"],
                    }
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n🏆 入选 Top {len(top)}（阈值 {args.min_score}）:", file=sys.stderr)
    for s in top:
        sc = s["_score"]
        print(f"  {sc['total']:.1f} (rel={sc['relevance']:.1f} q={sc['quality']:.1f}) | [{s.get('source','')}] {s.get('title','')[:50]}", file=sys.stderr)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(top, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 已写入: {out_path}", file=sys.stderr)
    else:
        print(json.dumps(top, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
