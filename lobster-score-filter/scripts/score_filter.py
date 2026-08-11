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

费曼三步法终审（可选，LLM 在编排层调用，本脚本零第三方依赖）：
    1) 导出待审清单：  --review-out /tmp/review-task.json [--review-top 15]
    2) LLM 按立场/证据/逻辑打分（编排层），结果格式：
       [{"review_id": "<导出清单里的16位id>", "position": 4.5, "evidence": 3.5, "logic": 4, "total": 4.0}]
       review_id 必须原样回传，用于跨运行稳定关联（不用排序位置）
    3) 合并重排：      --review-file /tmp/review-result.json [--review-weight 0.5]
       最终分 = 规则分 × (1-w) + 费曼分 × w

输出：入选 JSON（Top N，按综合分排序）
"""

import argparse
import hashlib
import json
import math
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

    # 画像最大权重：广度奖励的归一化基准（高权重核心需求命中才有高广度分）
    max_weight = max((n.get("weight", 1.0) for n in needs[:20]), default=1.0)

    score = 0.0
    matched = 0
    hit_weight_sum = 0.0
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
            hit_weight_sum += weight
            continue
        # 兜底：中文短词（2-3字）通过 token 重叠判断，避免"学习"泛匹配
        kw_tokens = tokenize(keyword)
        if kw_tokens and len(keyword) <= 3 and (kw_tokens & cand_tokens):
            weight = need.get("weight", 1.0)
            confidence = need.get("confidence", 0.5)
            score += weight * confidence * 0.3  # 短词命中降权
            matched += 1
            hit_weight_sum += weight

    # 分类偏好加成（画像里高频的分类）
    cat_bonus = CATEGORY_PREF.get(category, 1.0) * 0.3

    # 归一化到 0-5：强度×0.8 + 加权广度奖励 + 分类加成。
    # 广度奖励按命中需求的平均权重缩放（avg/max_weight），低权重需求堆数量拿不到高分，
    # 高权重核心需求单命中也有价值——深度优先，区分度仍 >1.0。
    # （评审约束实测：1×w5=3.50 > 5×w1=2.70；5×w5 区分度=1.50）
    breadth = 0.0
    if matched > 0:
        avg_weight = hit_weight_sum / matched
        breadth = min(2.0, matched * 0.4 * (avg_weight / max_weight))
    return min(5.0, score * 0.8 + breadth + cat_bonus)


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


def candidate_review_id(candidate: dict) -> str:
    """生成稳定评审 ID：优先规范化 URL；无 URL 时用 source+title 生成 SHA-256。

    与排序位置无关，跨运行（候选/画像/参数变化）仍能稳定关联到同一篇文章。
    """
    url = (candidate.get("url") or "").strip()
    if url:
        raw = f"url:{url}"
    else:
        raw = "fallback:{source}\n{title}".format(
            source=(candidate.get("source") or "").strip(),
            title=(candidate.get("title") or "").strip(),
        )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def finite_number(value, field: str) -> float:
    """把值转成有限实数；bool/NaN/Inf/非数字一律拒绝。"""
    if isinstance(value, bool):
        raise ValueError(f"{field} 必须是数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是数字") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} 必须是有限数字")
    return number


def main():
    def nonnegative_int(value):
        number = int(value)
        if number < 0:
            raise argparse.ArgumentTypeError("必须 >= 0")
        return number

    parser = argparse.ArgumentParser(description="龙虾日报 · AI 评分过滤器")
    parser.add_argument("--candidates", required=True, help="采集候选 JSON 路径")
    parser.add_argument("--profile", default=None, help="需求画像 JSON 路径")
    parser.add_argument("--top", type=int, default=5, help="入选数量")
    parser.add_argument("--min-score", type=float, default=1.5, help="最低综合分")
    parser.add_argument("--out", default=None, help="输出 JSON 路径")
    parser.add_argument("--hits-log", default=None, help="需求命中日志 JSONL 路径（缺省不写）")
    parser.add_argument("--review-out", default=None, help="导出待 LLM 评审的候选清单 JSON（含 review_id/规则分）；仅写文件，不改评分输出")
    parser.add_argument("--review-top", type=nonnegative_int, default=15, help="--review-out 导出的条数（默认 15）")
    parser.add_argument("--review-file", default=None, help="LLM 费曼三步法评审结果 JSON，与规则分混合重排")
    parser.add_argument("--review-weight", type=float, default=0.5, help="费曼分权重（默认 0.5，规则分占 1-w）")
    args = parser.parse_args()

    if not math.isfinite(args.review_weight):
        parser.error("--review-weight 必须是有限数字")

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

    # ── 模式 A：导出待 LLM 评审清单（不改变评分/排序输出，仅额外写文件）──
    if args.review_out:
        review_task = []
        for i, s in enumerate(scored[: args.review_top], 1):
            review_task.append({
                "idx": i,
                "review_id": candidate_review_id(s),
                "title": s.get("title", ""),
                "summary": (s.get("summary", "") or "")[:300],
                "source": s.get("source", ""),
                "category": s.get("category", ""),
                "tier": s.get("tier", 3),
                "current_total": s["_score"]["total"],
            })
        rv_path = Path(args.review_out)
        rv_path.parent.mkdir(parents=True, exist_ok=True)
        rv_path.write_text(json.dumps(review_task, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"💬 已导出 {len(review_task)} 条待评审清单: {rv_path}（LLM 按立场/证据/逻辑打分后，用 --review-file 合并）", file=sys.stderr)

    # ── 模式 B：读入 LLM 费曼三步法评审结果，按 review_id 稳定关联并混合重排 ──
    if args.review_file:
        rv_path = Path(args.review_file)
        if not rv_path.exists():
            print(f"❌ 找不到评审结果: {rv_path}", file=sys.stderr)
            sys.exit(1)
        reviews = json.loads(rv_path.read_text(encoding="utf-8"))
        if not isinstance(reviews, list):
            parser.error("--review-file 顶层必须是 JSON 数组")
        by_review_id = {}
        for row_no, r in enumerate(reviews, 1):
            if not isinstance(r, dict):
                parser.error(f"评审第 {row_no} 项必须是对象")
            review_id = r.get("review_id")
            if isinstance(review_id, bool) or not isinstance(review_id, str) or len(review_id) != 16:
                parser.error(f"评审第 {row_no} 项 review_id 必须是 16 位字符串")
            if review_id in by_review_id:
                parser.error(f"评审结果存在重复 review_id: {review_id}")
            try:
                total = finite_number(r.get("total"), f"review_id={review_id} total")
            except ValueError as exc:
                parser.error(str(exc))
            if not 0.0 <= total <= 5.0:
                parser.error(f"review_id={review_id} total 必须在 0..5")
            by_review_id[review_id] = {**r, "total": total}
        w = max(0.0, min(1.0, args.review_weight))
        merged = 0
        # 按稳定 review_id 关联：与排序位置无关，跨运行候选/排序变化不会错配。
        # 遍历全部候选而非 scored[:review_top]：同分候选跨越导出边界时也能合并。
        for s in scored:
            r = by_review_id.get(candidate_review_id(s))
            if r is None:
                continue
            feynman = r["total"]
            rule_total = s["_score"]["total"]
            final_total = rule_total * (1 - w) + feynman * w
            s["_score"]["feynman"] = {
                "position": r.get("position"),
                "evidence": r.get("evidence"),
                "logic": r.get("logic"),
                "total": round(feynman, 2),
            }
            s["_score"]["final_total"] = round(final_total, 2)
            merged += 1
        unmatched = len(by_review_id) - merged
        if unmatched:
            print(f"⚠️ {unmatched} 条评审未匹配到当前候选（候选/排序可能已变化），已忽略", file=sys.stderr)
        print(f"🎭 已合并 {merged} 条费曼评审（权重 {w:.0%}），最终分 = 规则分×{1-w:.0%} + 费曼分×{w:.0%}", file=sys.stderr)
        # 已评审组永远在前（按 final_total 降序），未评审组沉底（组内按规则分降序）
        def sort_key(s):
            score = s.get("_score", {})
            reviewed = "final_total" in score
            primary = score["final_total"] if reviewed else score["total"]
            return (reviewed, primary, score["total"])
        scored.sort(key=sort_key, reverse=True)

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
        if "final_total" in sc:
            print(f"  {sc['final_total']:.2f} (rule={sc['total']:.2f} feynman={sc['feynman']['total']:.2f}) | [{s.get('source','')}] {s.get('title','')[:50]}", file=sys.stderr)
        else:
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
