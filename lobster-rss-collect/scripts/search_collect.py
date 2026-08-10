#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-rss-collect · 搜索通道采集器（需求驱动，最小验证版）

搜索也走 RSS 入口：Bing 的 RSS 输出端点（format=rss），零第三方依赖。
输入：需求画像（user-profile.json）或 --needs 直接传关键词
输出：候选 JSON（与 fetch_rss.py 同结构 + channel 标注），供评分层使用

为什么用 Bing RSS：
- 零依赖（urllib + ElementTree，复用 fetch_rss 的解析容错）
- 返回标准 RSS XML，符合"万物皆可 RSS"
- 不需要 API key

用法：
    python3 search_collect.py --profile /path/to/user-profile.json --top 5
    python3 search_collect.py --needs "AI Agent" "心理学" --out /tmp/search-cands.json

输出：JSON 数组，每项：
    {title, url, summary, published, source, category, priority, channel}
    channel 固定为 "search"，source 为 "search:{query}"
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
TIMEOUT = 15
USER_AGENT = "lobster-rss-collect/0.1 search-channel (open source daily digest)"

# 域名黑名单（已知营销号/低质站，命中直接过滤）。初始少量，后续按需增补。
DOMAIN_BLACKLIST = {
    "adspower.net",        # 营销文（卖自己产品）
    "ai-bot.cn",           # 工具集目录站
}
# 知乎降权：不拉黑（有优质回答），但命中则降级到候选尾部并降分
ZHIHU_PENALTY = 0.5

# 营销词规则：标题/摘要含这些词 → 直接过滤（盘点/十大/大全/优惠 等）
MARKETING_KEYWORDS = [
    "盘点", "十大", "大全", "优惠", "价格", "购买", "试用", "推广", "广告",
    "排行榜", "top 10", "top10", "best 10", "2026最佳", "最新工具",
]

# 摘要长度阈值：搜索结果的摘要过短大概率是标题党/无正文，丢弃
MIN_SUMMARY_LEN = 50


def fetch_rss(query: str, count: int = 10) -> str:
    """Bing RSS 搜索端点：https://www.bing.com/search?format=rss&q=..."""
    params = urllib.parse.urlencode({"format": "rss", "q": query, "count": count})
    url = f"https://www.bing.com/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_search_rss(xml_text: str, query: str) -> list:
    """解析 Bing 搜索 RSS（RSS 2.0 格式）。"""
    # 容错：清理非法控制字符 + 裸 & 转义（与 fetch_rss 一致）
    xml_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_text)
    xml_text = re.sub(
        r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)",
        "&amp;",
        xml_text,
    )
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        desc = item.findtext("description", default="")
        pub = item.findtext("pubDate", default="")
        items.append({
            "title": title.strip(),
            "url": link.strip(),
            "summary": desc.strip(),
            "published": pub.strip(),
            "source": f"search:{query}",
            "category": "search",
            "priority": "medium",
            "channel": "search",
        })
    return items


def clean_html(text: str) -> str:
    """剥掉摘要里的 HTML 标签和实体。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", "\"", text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_blacklisted(url: str) -> bool:
    """域名黑名单检查。"""
    for domain in DOMAIN_BLACKLIST:
        if domain in url:
            return True
    return False


def normalize_title(title: str) -> str:
    """标题归一化：小写 + 去标点，用于去重。"""
    t = re.sub(r"[\W_]+", "", title.lower())
    return t


def is_marketing(item: dict) -> bool:
    """营销文检测：标题/摘要含营销词 → 过滤。"""
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return any(kw.lower() in text for kw in MARKETING_KEYWORDS)


def collect(queries: list, count: int = 10, max_per_query: int = 10,
            dedup: bool = True, min_summary: int = MIN_SUMMARY_LEN) -> dict:
    """对每个需求关键词执行搜索 + 质量预筛（去重/黑名单/营销词/摘要长度/知乎降权）。"""
    results = []
    seen_titles = set()
    stats = {"queries": 0, "fetched": 0, "deduped": 0, "blacklisted": 0,
             "marketing": 0, "short_summary": 0, "zhihu_penalized": 0,
             "kept": 0, "errors": []}

    for q in queries:
        stats["queries"] += 1
        try:
            xml_text = fetch_rss(q, count)
            items = parse_search_rss(xml_text, q)
            stats["fetched"] += len(items)
            for it in items:
                it["summary"] = clean_html(it["summary"])
                # 质量预筛 1：域名黑名单
                if is_blacklisted(it["url"]):
                    stats["blacklisted"] += 1
                    continue
                # 质量预筛 2：营销词（盘点/十大/优惠 等）
                if is_marketing(it):
                    stats["marketing"] += 1
                    continue
                # 质量预筛 3：摘要过短（标题党）
                if len(it["summary"]) < min_summary:
                    stats["short_summary"] += 1
                    continue
                # 质量预筛 4：标题去重（同事件不同源报道只留一个）
                key = normalize_title(it["title"])
                if dedup and key in seen_titles:
                    stats["deduped"] += 1
                    continue
                seen_titles.add(key)
                # 知乎降权：不拉黑，但降低排序优先级
                if "zhihu.com" in it["url"]:
                    stats["zhihu_penalized"] += 1
                    it["_zhihu_penalty"] = ZHIHU_PENALTY
                results.append(it)
                stats["kept"] += 1
                if len(results) >= max_per_query * len(queries):
                    break
        except Exception as e:
            stats["errors"].append(f"{q}: {e}")
        time.sleep(1)  # 轻量限速，避免被 Bing 429

    # 知乎降权排序：非知乎在前，知乎按原序在后（保持稳定性）
    results.sort(key=lambda it: it.get("_zhihu_penalty", 1.0))
    return {"items": results, "stats": stats}


def load_profile_needs(profile_path: Path, top: int = 5) -> list:
    """从 user-profile.json 取 top N 需求关键词。"""
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    needs = data.get("needs", [])
    needs = sorted(needs, key=lambda n: n.get("weight", 0), reverse=True)
    return [n["keyword"] for n in needs[:top]]


def covered_needs(rss_items: list, needs: list, threshold: int = 1) -> set:
    """判断哪些需求已被 RSS 通道覆盖：RSS 候选标题/摘要含需求关键词 >= threshold 次。
    被覆盖的需求不再走搜索，避免候选池无谓膨胀（按需启用）。"""
    covered = set()
    for n in needs:
        kw = n["keyword"]
        if len(kw) < 2:
            continue
        hits = sum(1 for it in rss_items
                   if kw.lower() in (it.get("title", "") + " " + it.get("summary", "")).lower())
        if hits >= threshold:
            covered.add(kw)
    return covered


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 搜索通道采集器（需求驱动）")
    parser.add_argument("--profile", help="user-profile.json 路径（取 top N 需求）")
    parser.add_argument("--needs", nargs="*", help="直接指定需求关键词")
    parser.add_argument("--top", type=int, default=5, help="从画像取前 N 个需求")
    parser.add_argument("--count", type=int, default=10, help="每个需求搜索返回条数")
    parser.add_argument("--max", type=int, default=10, help="每需求最多保留候选数")
    parser.add_argument("--out", default=None, help="输出 JSON 路径（默认 stdout）")
    parser.add_argument("--no-dedup", action="store_true", help="关闭标题去重")
    parser.add_argument("--rss-candidates", default=None,
                        help="RSS 通道候选 JSON：用于判断已覆盖需求，跳过不搜（按需启用）")
    parser.add_argument("--append", default=None,
                        help="合并输出路径：把搜索结果追加进该候选文件（用于采集层合并）")
    args = parser.parse_args()

    if args.profile:
        queries = load_profile_needs(Path(args.profile), args.top)
    elif args.needs:
        queries = list(args.needs)
    else:
        print("❌ 需要 --profile 或 --needs", file=sys.stderr)
        sys.exit(1)

    # 按需启用：如果给了 RSS 候选，跳过已被 RSS 覆盖的需求
    if args.rss_candidates:
        rss_path = Path(args.rss_candidates)
        if rss_path.exists():
            try:
                rss_items = json.loads(rss_path.read_text(encoding="utf-8"))
                needs_full = json.loads(Path(args.profile).read_text(encoding="utf-8")).get("needs", [])
                covered = covered_needs(rss_items, needs_full)
                if covered:
                    print(f"🔄 跳过已由 RSS 覆盖的需求: {sorted(covered)}", file=sys.stderr)
                    queries = [q for q in queries if q not in covered]
            except Exception as e:
                print(f"⚠️ 读取 RSS 候选失败（跳过按需逻辑）: {e}", file=sys.stderr)

    if not queries:
        print("⚠️ 画像为空，无可搜索需求", file=sys.stderr)
        sys.exit(0)

    print(f"🔍 搜索通道：{len(queries)} 个需求关键词", file=sys.stderr)
    for q in queries:
        print(f"   - {q}", file=sys.stderr)

    result = collect(queries, count=args.count, max_per_query=args.max,
                     dedup=not args.no_dedup)
    stats = result["stats"]
    print(f"\n📊 统计: 抓取 {stats['fetched']} → 去重 {stats['deduped']} / "
          f"黑名单 {stats['blacklisted']} / 摘要过短 {stats['short_summary']} → "
          f"保留 {stats['kept']}", file=sys.stderr)
    if stats["errors"]:
        print("⚠️ 失败:", file=sys.stderr)
        for e in stats["errors"]:
            print(f"   {e}", file=sys.stderr)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result["items"], ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"💾 已写入: {out_path}", file=sys.stderr)
    elif args.append:
        # 合并模式：把搜索结果追加进已有候选文件（RSS + 搜索 = 合并候选池）
        append_path = Path(args.append)
        existing = []
        if append_path.exists():
            try:
                existing = json.loads(append_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = []
        existing_titles = {re.sub(r"[\W_]+", "", i.get("title", "").lower()) for i in existing}
        merged = list(existing)
        added = 0
        for it in result["items"]:
            key = re.sub(r"[\W_]+", "", it.get("title", "").lower())
            if key not in existing_titles:
                merged.append(it)
                existing_titles.add(key)
                added += 1
        append_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 已合并: {append_path}（新增 {added} 条，共 {len(merged)} 条）", file=sys.stderr)
    else:
        print(json.dumps(result["items"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
