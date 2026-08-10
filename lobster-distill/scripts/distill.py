#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-distill · 提炼编排器

输入：评分层入选 JSON（Top N）
输出：每篇的提炼任务清单（供 AI 调用 note-taking-pro / concept-learning 完成）

本脚本不做笔记/概念本身——那由 note-taking-pro 和 concept-learning skill 完成。
它负责：读入选 → 生成任务清单 → 记录产物路径。

零第三方依赖：只用 Python 标准库。

用法：
    python3 distill.py --top /tmp/top.json --out-dir artifacts/distill/
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 提炼编排器")
    parser.add_argument("--top", required=True, help="评分层入选 JSON")
    parser.add_argument("--out-dir", default="artifacts/distill", help="产物目录")
    parser.add_argument("--out", default=None, help="任务清单输出路径")
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
