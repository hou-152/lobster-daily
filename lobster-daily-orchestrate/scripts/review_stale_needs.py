#!/usr/bin/env python3
"""根据需求命中日志生成人工复核用的陈旧需求报告。"""

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def parse_day(value: str):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="龙虾日报 · 每周陈旧需求回顾")
    parser.add_argument("--hits-log", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", default=None, help="报告路径（默认命中日志同目录）")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days 必须大于 0")

    hits_path = Path(args.hits_log)
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    rows = []
    if hits_path.exists():
        for raw in hits_path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue

    today = datetime.now(timezone.utc).date()
    window_start = today - timedelta(days=args.days - 1)
    recent = {r.get("keyword") for r in rows if (parse_day(r.get("date")) or date.min) >= window_start}
    last_hits = {}
    for row in rows:
        day = parse_day(row.get("date"))
        keyword = row.get("keyword")
        if day and keyword and day > last_hits.get(keyword, date.min):
            last_hits[keyword] = day

    stale = [n for n in profile.get("needs", []) if n.get("keyword") not in recent]
    lines = [
        "# 🦞 龙虾日报 · 陈旧需求回顾",
        "",
        f"> 回顾窗口：{window_start.isoformat()} 至 {today.isoformat()}（连续 {args.days} 天）",
        "",
        f"连续无命中需求：**{len(stale)}** 条",
        "",
    ]
    for need in stale:
        keyword = need.get("keyword", "")
        weight = float(need.get("weight", 1.0))
        last = last_hits.get(keyword)
        if last is None:
            suggestion = "淘汰"
            last_text = "从未命中"
        elif (today - last).days >= args.days * 2:
            suggestion = "降权 0.5"
            last_text = last.isoformat()
        else:
            suggestion = "保留观察"
            last_text = last.isoformat()
        lines.append(f"- **{keyword}**｜weight {weight:g}｜最后命中：{last_text}｜建议：{suggestion}")
    if not stale:
        lines.append("- 无")
    lines.append("")
    report = "\n".join(lines)
    print(report)

    if not args.dry_run:
        out_path = Path(args.out) if args.out else hits_path.parent / "stale-needs-review.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"💾 报告已写入: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
