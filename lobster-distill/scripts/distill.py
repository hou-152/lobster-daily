#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-distill · 提炼编排器

输入：评分层入选 JSON（Top N）
输出：每篇的提炼任务清单（供 AI 调用 note-taking-pro / concept-learning 完成）
     或 --simple 模式直接生成规则版基础笔记/概念（无需 LLM）

零第三方依赖：只用 Python 标准库。

用法：
    python3 distill.py --top /tmp/top.json --out /tmp/tasks.json          # 任务清单（需LLM）
    python3 distill.py --top /tmp/top.json --simple --notes-dir notes/    # 规则版提炼（无LLM）
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


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
    text = re.sub(r"&apos;", "'", text)
    text = re.sub(r"&mdash;", "—", text)
    text = re.sub(r"&ndash;", "–", text)
    text = re.sub(r"&hellip;", "…", text)
    text = re.sub(r"&ldquo;|&rdquo;", "\"", text)
    text = re.sub(r"&lsquo;|&rsquo;", "'", text)
    text = re.sub(r"&middot;", "·", text)
    text = re.sub(r"&bull;", "•", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)  # 兜底：其他命名实体
    text = re.sub(r"\s+", " ", text).strip()
    return text


def simple_notes(item: dict) -> str:
    """规则版基础笔记：不依赖 LLM，从标题/摘要提取骨架。"""
    title = item.get("title", "")
    summary = clean_html(item.get("summary", ""))
    source = item.get("source", "")
    url = item.get("url", "")
    score = item.get("_score", {})
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 一句话主旨")
    lines.append(f"{summary[:100]}…" if len(summary) > 100 else (summary or "（摘要为空）"))
    lines.append("")
    lines.append("## 来源与评分")
    lines.append(f"- 来源：{source}")
    lines.append(f"- 综合分：{score.get('total', '?')}（相关性 {score.get('relevance', '?')} / 质量 {score.get('quality', '?')}）")
    if url:
        lines.append(f"- 原文：{url}")
    lines.append("")
    lines.append("## 三级论证骨架（规则版）")
    lines.append("### 一、核心信息")
    lines.append(f"- {summary[:150]}…" if len(summary) > 150 else f"- {summary}")
    lines.append("")
    lines.append("## 边界与说明")
    lines.append("- 本笔记由规则生成（--simple 模式），未做语义分析；如需完整三级笔记请用 LLM 模式")
    return "\n".join(lines)


def simple_concepts(item: dict) -> str:
    """规则版概念提取：从标题/摘要提取关键词做费曼式简释。"""
    title = item.get("title", "")
    summary = clean_html(item.get("summary", ""))
    # 提取中文 2-6 字片段 + 英文 3+ 字符词
    tokens = re.findall(r"[\u4e00-\u9fff]{2,6}", f"{title} {summary}")
    tokens += re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{3,20}", f"{title} {summary}")
    # 去重、过滤噪音
    seen = set()
    concepts = []
    for t in tokens:
        if t in seen or len(t) < 2:
            continue
        seen.add(t)
        concepts.append(t)
        if len(concepts) >= 8:
            break
    lines = []
    lines.append("# 概念解析辞典（规则版）")
    lines.append("")
    lines.append("## 一、核心概念")
    for i, c in enumerate(concepts[:5], 1):
        lines.append(f"### {i}. {c}")
        lines.append("")
        lines.append(f"- **费曼一下**：{c} 是本文出现的关键概念，具体含义需结合原文上下文理解（规则版未做语义分析）")
        lines.append("")
    lines.append("## 二、概念架构图")
    lines.append("")
    lines.append("> 规则版未生成 Mermaid 架构图；如需完整版请用 LLM 模式（concept-learning skill）")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 提炼编排器")
    parser.add_argument("--top", required=True, help="评分层入选 JSON")
    parser.add_argument("--out-dir", default="artifacts/distill", help="产物目录")
    parser.add_argument("--out", default=None, help="任务清单输出路径")
    parser.add_argument("--simple", action="store_true", help="规则版提炼（无需 LLM/skill，clone 即用）")
    args = parser.parse_args()

    top_path = Path(args.top)
    if not top_path.exists():
        print(f"❌ 找不到入选文件: {top_path}", file=sys.stderr)
        sys.exit(1)
    items = json.loads(top_path.read_text(encoding="utf-8"))
    if not items:
        print("⚠️ 入选列表为空", file=sys.stderr)
        sys.exit(0)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --simple 模式：直接生成规则版笔记/概念，无需 LLM
    if args.simple:
        print(f"🔧 规则版提炼（--simple，无需 LLM），{len(items)} 篇", file=sys.stderr)
        generated = 0
        for i, item in enumerate(items, 1):
            slug = (item.get("source", "item") + "-" + str(i))
            note_path = out_dir / f"{slug}-notes.md"
            concept_path = out_dir / f"{slug}-concepts.md"
            note_path.write_text(simple_notes(item), encoding="utf-8")
            concept_path.write_text(simple_concepts(item), encoding="utf-8")
            generated += 1
            print(f"  ✅ [{i}] {item.get('title','')[:40]} → {slug}", file=sys.stderr)
        print(f"\n💾 规则版提炼完成: {generated} 篇 → {out_dir}", file=sys.stderr)
        print(f"ℹ️  如需完整三级笔记/概念提取，去掉 --simple 并配置 LLM（见 SKILL.md）", file=sys.stderr)
        return

    tasks = []
    for i, item in enumerate(items, 1):
        # 每篇一个产物路径
        slug = (item.get("source", "item") + "-" + str(i))
        task = {
            "index": i,
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "category": item.get("category", ""),
            "score": item.get("_score", {}),
            "note_path": str(out_dir / f"{slug}-notes.md"),
            "concept_path": str(out_dir / f"{slug}-concepts.md"),
            "status": "pending",
        }
        tasks.append(task)

    # 生成提炼任务清单
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "total": len(tasks),
        "tasks": tasks,
        "instructions": (
            "对每篇执行两个独立步骤：\n"
            "1. 调用 note-taking-pro skill 生成三级笔记（结构化大纲）→ 写入 note_path\n"
            "2. 调用 concept-learning skill 生成概念辞典（费曼+概念网络）→ 写入 concept_path\n"
            "两个产物互不依赖、互不串扰。"
        ),
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 任务清单: {out_path}（{len(tasks)} 篇）", file=sys.stderr)
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"\n📝 提炼任务（{len(tasks)} 篇）:", file=sys.stderr)
    for t in tasks:
        print(f"  [{t['index']}] {t['title'][:50]}", file=sys.stderr)
        print(f"      → {t['note_path']}", file=sys.stderr)
        print(f"      → {t['concept_path']}", file=sys.stderr)


if __name__ == "__main__":
    main()
