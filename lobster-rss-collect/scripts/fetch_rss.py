#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-rss-collect · 统一 RSS 抓取器（万物皆可 RSS）

零第三方依赖：只用 Python 标准库（urllib + xml.etree.ElementTree）。
支持 RSS 2.0 和 Atom 两种格式，自动识别、统一输出 JSON。

用法：
    python3 fetch_rss.py                          # 读默认 config/sources.yaml
    python3 fetch_rss.py --config path/to/sources.yaml
    python3 fetch_rss.py --category ai            # 只抓指定分类
    python3 fetch_rss.py --limit 50               # 每源最多取 N 条
    python3 fetch_rss.py --out candidates.json    # 输出到文件

输出：JSON 数组，每项：
    {title, url, summary, published, source, category, priority, channel}
    channel 固定为 "rss"
"""

import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# Atom 与 RSS 命名空间
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
RSS_NS = {"rss": ""}

TIMEOUT = 15  # 单源抓取超时（秒）
USER_AGENT = "lobster-rss-collect/0.1 (+open source daily digest)"


def fetch_feed(url: str, retries: int = 2) -> str:
    """抓取 feed 内容，带超时、UA、失败重试。"""
    import time
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))  # 2s, 4s 退避
    raise last_err


def parse_feed(xml_text: str, source_name: str, category: str, priority: str) -> list:
    """解析 RSS 2.0 / Atom，统一输出条目列表。带容错：非法 XML 字符清理 + 裸 & 转义。"""
    import re
    # 清理 XML 1.0 不允许的控制字符（有些 feed 会混入）
    xml_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml_text)
    # 修复裸 &（URL 参数里的 & 没转义，如 "?a=1&b=2"）：
    # 只补非实体名的 &，避免重复转义已正确的 &amp;
    xml_text = re.sub(
        r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)",
        "&amp;",
        xml_text,
    )
    root = ET.fromstring(xml_text)
    items = []

    if root.tag.endswith("feed"):
        # ---- Atom 格式 ----
        for entry in root.findall("atom:entry", ATOM_NS):
            title = entry.findtext("atom:title", default="", namespaces=ATOM_NS)
            link_el = entry.find("atom:link", ATOM_NS)
            url = link_el.get("href", "") if link_el is not None else ""
            summary = entry.findtext("atom:summary", default="", namespaces=ATOM_NS)
            published = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
            if not published:
                published = entry.findtext("atom:updated", default="", namespaces=ATOM_NS)
            items.append({
                "title": title.strip(),
                "url": url.strip(),
                "summary": summary.strip(),
                "published": published,
                "source": source_name,
                "category": category,
                "priority": priority,
                "channel": "rss",
            })
    else:
        # ---- RSS 2.0 格式 ----
        for item in root.findall(".//item"):
            title = item.findtext("title", default="")
            url = item.findtext("link", default="")
            summary = item.findtext("description", default="")
            published = item.findtext("pubDate", default="")
            items.append({
                "title": title.strip(),
                "url": url.strip(),
                "summary": summary.strip(),
                "published": published,
                "source": source_name,
                "category": category,
                "priority": priority,
                "channel": "rss",
            })

    return items


def load_sources(config_path: Path) -> dict:
    """读取 sources.yaml（简化解析：只支持我们自己的结构，不引入 PyYAML）。"""
    text = config_path.read_text(encoding="utf-8")
    sources = {"rss_feeds": [], "api_sources": []}

    # 极简 YAML 子集解析：rss_feeds / api_sources 下每行 "- name:" 起一条记录
    current_section = None
    current_item = None

    def flush_item():
        nonlocal current_item
        if current_item and current_section in ("rss_feeds", "api_sources"):
            sources[current_section].append(current_item)
        current_item = None

    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if indent == 0 and stripped.endswith(":") and not stripped.startswith("- "):
            # 段切换：先 flush 上一段最后一条
            flush_item()
            if stripped.startswith("rss_feeds:"):
                current_section = "rss_feeds"
            elif stripped.startswith("api_sources:"):
                current_section = "api_sources"
            else:
                current_section = "__skip__"
            continue

        if current_section is None or current_section == "__skip__":
            continue

        if stripped.startswith("- name:"):
            flush_item()
            current_item = {"name": stripped.split(":", 1)[1].strip()}
        elif current_item is not None and ":" in stripped:
            key, _, value = stripped.partition(":")
            current_item[key.strip()] = value.strip().strip('"').strip("'")

    flush_item()
    return sources


def fetch_github_trending(source: dict) -> list:
    """GitHub 趋势：调官方搜索 API，按 star 排序（无官方 RSS 的包装方案）。"""
    from urllib.parse import quote
    query = source.get("query", "created:>2026-01-01 sort:stars")
    encoded = quote(query, safe="")
    url = f"https://api.github.com/search/repositories?q={encoded}&per_page=10"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    items = []
    for repo in data.get("items", []):
        items.append({
            "title": repo.get("full_name", ""),
            "url": repo.get("html_url", ""),
            "summary": (repo.get("description") or "")[:200],
            "published": repo.get("created_at", ""),
            "source": source.get("name", "github-trending"),
            "category": source.get("category", "dev"),
            "priority": source.get("priority", "medium"),
        })
    return items


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 统一 RSS 抓取器")
    parser.add_argument("--config", default=None, help="sources.yaml 路径")
    parser.add_argument("--category", default=None, help="只抓指定分类")
    parser.add_argument("--limit", type=int, default=30, help="每源最多取 N 条")
    parser.add_argument("--out", default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    # 定位 config
    if args.config:
        config_path = Path(args.config)
    else:
        config_path = Path(__file__).parent.parent / "config" / "sources.yaml"
    if not config_path.exists():
        print(f"❌ 找不到配置文件: {config_path}", file=sys.stderr)
        sys.exit(1)

    sources = load_sources(config_path)
    all_items = []

    # 抓 RSS feeds
    for feed in sources.get("rss_feeds", []):
        if args.category and feed.get("category") != args.category:
            continue
        name = feed.get("name", "unknown")
        try:
            xml_text = fetch_feed(feed["url"])
            items = parse_feed(
                xml_text, name,
                feed.get("category", "general"),
                feed.get("priority", "medium"),
            )
            all_items.extend(items[: args.limit])
            print(f"  ✅ {name}: {len(items[:args.limit])} 条", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  {name}: 抓取失败 ({e})", file=sys.stderr)

    # 抓 API 源
    for api in sources.get("api_sources", []):
        if args.category and api.get("category") != args.category:
            continue
        try:
            if api.get("type") == "github-api":
                items = fetch_github_trending(api)
                all_items.extend(items[: args.limit])
                print(f"  ✅ {api.get('name')}: {len(items)} 条 (API)", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️  {api.get('name')}: 抓取失败 ({e})", file=sys.stderr)

    # 去重（按 url）
    seen = set()
    unique = []
    for item in all_items:
        if item["url"] and item["url"] in seen:
            continue
        if item["url"]:
            seen.add(item["url"])
        unique.append(item)

    print(f"\n📦 共 {len(unique)} 条候选（去重后）", file=sys.stderr)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"💾 已写入: {out_path}", file=sys.stderr)
    else:
        print(json.dumps(unique, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
