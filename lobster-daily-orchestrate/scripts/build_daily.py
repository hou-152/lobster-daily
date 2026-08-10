#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-daily-orchestrate · 每日编排器（入口 skill 的辅助脚本）

串起全流程：采集 → 需求 → 评分 → 提炼 → 生成日报 Markdown。
实际执行由 AI agent 按 SKILL.md 编排（各层脚本各自独立），
本脚本负责：生成日报 Markdown 文件（供推送到飞书云文档）。

用法：
    python3 build_daily.py --top /tmp/top.json --notes-dir artifacts/distill/ --date 2026-08-10
    python3 build_daily.py --top top.json --notes-dir artifacts/distill/ --dry-run
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def build_daily(top_items: list, notes_dir: Path, date_str: str, embed: bool = True, needs: list = None) -> str:
    """生成日报 Markdown。embed=True 时把笔记/概念全文内嵌进日报。"""
    lines = []
    lines.append(f"# 🦞 龙虾日报（Claw Daily · {date_str.replace('-', '')} 期）")
    lines.append("")
    lines.append("> 根据你最近对话中的需求信号，从你的信息源中精选。越聊越懂你。")
    lines.append("")

    # 总览
    lines.append("## 📊 今日总览")
    lines.append("")
    lines.append(f"- **入选篇数**：{len(top_items)}")
    cats = {}
    for it in top_items:
        c = it.get("category", "other")
        cats[c] = cats.get(c, 0) + 1
    if cats:
        top_cats = sorted(cats.items(), key=lambda x: -x[1])[:3]
        lines.append(f"- **主题分布**：{'、'.join(f'{c}×{n}' for c, n in top_cats)}")
    lines.append("")

    # 入选文章
    lines.append("## 📖 今日精选")
    lines.append("")
    for i, item in enumerate(top_items, 1):
        title = item.get("title", "(无标题)")
        url = item.get("url", "")
        source = item.get("source", "")
        summary = item.get("summary", "")
        score = item.get("_score", {})
        lines.append(f"### {i}｜{title}")
        lines.append("")
        if source:
            lines.append(f"*来源：{source}*")
        if score:
            lines.append(f"*评分：综合 {score.get('total', '?')}（相关性 {score.get('relevance', '?')} / 质量 {score.get('quality', '?')}）*")
        if summary:
            lines.append("")
            lines.append(summary[:200])
        if url:
            lines.append("")
            lines.append(f"🔗 [阅读原文]({url})")
        lines.append("")

        # 内嵌笔记/概念产物（默认内嵌全文）
        note = notes_dir / f"{source}-{i}-notes.md"
        concept = notes_dir / f"{source}-{i}-concepts.md"
        if embed:
            if note.exists():
                lines.append("**📝 三级笔记：**")
                lines.append("")
                lines.append(note.read_text(encoding="utf-8", errors="replace").strip())
                lines.append("")
            if concept.exists():
                lines.append("**🧠 概念提取：**")
                lines.append("")
                lines.append(concept.read_text(encoding="utf-8", errors="replace").strip())
                lines.append("")
            if not note.exists() and not concept.exists():
                lines.append("*（提炼产物待生成：三级笔记 + 概念提取）*")
                lines.append("")
        else:
            if note.exists() or concept.exists():
                lines.append("**提炼产物：**")
                if note.exists():
                    lines.append(f"- 📝 [三级笔记]({note.name})")
                if concept.exists():
                    lines.append(f"- 🧠 [概念提取]({concept.name})")
                lines.append("")

    # 推荐理由区（基于画像确定性生成，非占位符）
    lines.append("---")
    lines.append("## 💡 推荐理由")
    lines.append("")
    for i, item in enumerate(top_items, 1):
        title = item.get('title', '')[:40]
        reason = generate_reason(item, needs)
        lines.append(f"- **{i}｜{title}**：{reason}")
    lines.append("")

    # 反馈
    lines.append("---")
    lines.append("## 👀 反馈")
    lines.append("")
    lines.append("回复告诉我哪篇有用/没用，我会更新你的需求画像，明天更准。")
    lines.append("")

    return "\n".join(lines)


def generate_reason(item: dict, needs: list) -> str:
    """基于需求画像生成确定性推荐理由（不需要 LLM）。"""
    title = (item.get("title", "") + " " + item.get("summary", ""))[:500].lower()
    score = item.get("_score", {})
    rel = score.get("relevance", 0)

    # 找命中的需求（按权重排序）
    hits = []
    for n in (needs or [])[:20]:
        kw = n.get("keyword", "")
        if not kw or len(kw) < 2:
            continue
        if kw.lower() in title:
            hits.append(n)
    hits.sort(key=lambda n: n.get("weight", 0), reverse=True)

    if hits:
        top = hits[0]
        return f"命中你的需求「{top.get('keyword', '')}」（权重 {top.get('weight', 1.0)}），相关性 {rel:.1f}/5"
    if rel >= 3:
        return f"内容质量高（相关性 {rel:.1f}/5），与你的画像相关度较高"
    return f"本期值得一读（相关性 {rel:.1f}/5），评分 {score.get('total', '?')}"


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 日报构建器")
    parser.add_argument("--top", required=True, help="评分层入选 JSON")
    parser.add_argument("--notes-dir", default="artifacts/distill", help="提炼产物目录")
    parser.add_argument("--profile", default=None, help="需求画像 JSON（用于生成推荐理由）")
    parser.add_argument("--date", default=None, help="日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--out", default=None, help="日报 Markdown 输出路径")
    parser.add_argument("--dry-run", action="store_true", help="打印不写文件")
    args = parser.parse_args()

    top_path = Path(args.top)
    if not top_path.exists():
        print(f"❌ 找不到入选文件: {top_path}", file=sys.stderr)
        sys.exit(1)
    items = json.loads(top_path.read_text(encoding="utf-8"))

    # 读画像（可选，用于推荐理由）
    needs = []
    if args.profile:
        prof_path = Path(args.profile)
        if prof_path.exists():
            try:
                profile = json.loads(prof_path.read_text(encoding="utf-8"))
                needs = profile.get("needs", [])
            except (json.JSONDecodeError, OSError) as e:
                print(f"⚠️ 画像读取失败（{e}），推荐理由将退化为通用文案", file=sys.stderr)
        else:
            print(f"⚠️ 画像不存在: {prof_path}，推荐理由将退化为通用文案", file=sys.stderr)

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    notes_dir = Path(args.notes_dir)

    md = build_daily(items, notes_dir, date_str, needs=needs)

    if args.dry_run:
        print(md)
        return

    out_path = Path(args.out) if args.out else Path(f"artifacts/daily/{date_str}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"💾 日报已生成: {out_path}", file=sys.stderr)
    print(f"📄 共 {len(items)} 篇精选", file=sys.stderr)


if __name__ == "__main__":
    main()
