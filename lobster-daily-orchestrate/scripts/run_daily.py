#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-run-daily · 龙虾日报一键入口

统一调用五阶段：采集 → 需求 → 评分 → 提炼 → 日报（+ Mermaid 转图 + 飞书推送）。
每条命令生成 run 目录、记录状态、支持 --dry-run 和 --push-feishu。

零第三方依赖：只用 Python 标准库。

用法：
    python3 run_daily.py --dry-run                  # 预演全流程（不写最终产物）
    python3 run_daily.py                            # 跑采集→需求→评分→日报（不含提炼/推送）
    python3 run_daily.py --push-feishu              # 完整流程 + 飞书推送
    python3 run_daily.py --with-distill             # 生成提炼任务清单（需要 LLM 执行）
    python3 run_daily.py --workdir /tmp/lobster-run # 指定工作目录
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent  # lobster-daily-orchestrate 根
SCRIPTS = {
    "collect": SKILLS_DIR.parent / "lobster-rss-collect" / "scripts" / "fetch_rss.py",
    "needs": SKILLS_DIR.parent / "lobster-needs-extract" / "scripts" / "extract_needs.py",
    "score": SKILLS_DIR.parent / "lobster-score-filter" / "scripts" / "score_filter.py",
    "distill": SKILLS_DIR.parent / "lobster-distill" / "scripts" / "distill.py",
    "build": SKILLS_DIR / "scripts" / "build_daily.py",
    "render": SKILLS_DIR / "scripts" / "render_mermaid.py",
    "push": SKILLS_DIR / "scripts" / "push_feishu.py",
}


def run_step(name, cmd, env=None):
    """运行一个步骤，返回 (exit_code, output)。"""
    print(f"\n{'='*50}\n▶️  {name}\n{'='*50}", file=sys.stderr)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env or os.environ.copy(), timeout=600)
        if proc.stdout:
            print(proc.stdout[-2000:], file=sys.stderr)
        if proc.stderr:
            print(proc.stderr[-2000:], file=sys.stderr)
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        print(f"⏰ {name} 超时", file=sys.stderr)
        return -1, ""
    except FileNotFoundError as e:
        print(f"❌ {name} 脚本不存在: {e}", file=sys.stderr)
        return -1, ""


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 一键入口")
    parser.add_argument("--dry-run", action="store_true", help="预演（打印将执行的命令）")
    parser.add_argument("--push-feishu", action="store_true", help="推送到飞书云文档")
    parser.add_argument("--with-distill", action="store_true", help="生成提炼任务清单（需 LLM 执行）")
    parser.add_argument("--workdir", default=None, help="工作目录（默认 /tmp/lobster-daily-run）")
    parser.add_argument("--top", type=int, default=5, help="入选数量")
    parser.add_argument("--days", type=int, default=1, help="需求扫描天数")
    parser.add_argument("--limit", type=int, default=5, help="每源采集条数")
    args = parser.parse_args()

    date_str = datetime.now().strftime("%Y-%m-%d")
    workdir = Path(args.workdir or "/tmp/lobster-daily-run")
    workdir.mkdir(parents=True, exist_ok=True)

    cand_path = workdir / "candidates.json"
    profile_path = Path.home() / ".openclaw-lobster2" / "agents" / "main" / "skills" / "lobster-needs-extract" / "data" / "user-profile.json"
    # profile 默认路径：skill 自身 data 目录
    profile_path = SKILLS_DIR.parent / "lobster-needs-extract" / "data" / "user-profile.json"
    top_path = workdir / "top.json"
    tasks_path = workdir / "tasks.json"
    daily_path = workdir / f"daily-{date_str}.md"
    rendered_path = workdir / f"daily-{date_str}-rendered.md"
    images_dir = workdir / "images"
    manifest_path = workdir / "images-manifest.json"

    steps = []

    # ① 采集
    steps.append(("① 采集 (lobster-rss-collect)",
                  ["python3", str(SCRIPTS["collect"]), "--limit", str(args.limit),
                   "--out", str(cand_path)]))

    # ② 需求倒推
    steps.append(("② 需求倒推 (lobster-needs-extract)",
                  ["python3", str(SCRIPTS["needs"]), "--days", str(args.days)]))

    # ③ 评分过滤
    steps.append(("③ 评分过滤 (lobster-score-filter)",
                  ["python3", str(SCRIPTS["score"]),
                   "--candidates", str(cand_path),
                   "--profile", str(profile_path),
                   "--top", str(args.top),
                   "--out", str(top_path)]))

    # ④ 提炼任务清单（可选）
    if args.with_distill:
        steps.append(("④ 提炼任务清单 (lobster-distill)",
                      ["python3", str(SCRIPTS["distill"]),
                       "--top", str(top_path), "--out", str(tasks_path)]))

    # ⑤ 生成日报
    steps.append(("⑤ 生成日报 (build_daily)",
                  ["python3", str(SCRIPTS["build"]),
                   "--top", str(top_path),
                   "--notes-dir", str(workdir / "notes"),
                   "--date", date_str,
                   "--out", str(daily_path)]))

    # ⑥ Mermaid 转图
    steps.append(("⑥ Mermaid 转图 (render_mermaid)",
                  ["python3", str(SCRIPTS["render"]),
                   "--input", str(daily_path),
                   "--output", str(rendered_path),
                   "--images-dir", str(images_dir),
                   "--manifest", str(manifest_path)]))

    # ⑦ 飞书推送（可选）
    if args.push_feishu:
        steps.append(("⑦ 飞书推送 (push_feishu)",
                      ["python3", str(SCRIPTS["push"]),
                       "--input", str(rendered_path),
                       "--title", f"🦞 龙虾日报 {date_str}",
                       "--images-dir", str(images_dir)]))

    # 执行
    if args.dry_run:
        print("🔍 预演模式，将执行以下步骤：\n", file=sys.stderr)
        for name, cmd in steps:
            print(f"  {name}\n    {' '.join(cmd)}", file=sys.stderr)
        print(f"\n工作目录: {workdir}", file=sys.stderr)
        sys.exit(0)

    status = {}
    last_output = ""
    for name, cmd in steps:
        code, output = run_step(name, cmd)
        status[name] = "✅" if code == 0 else "❌"
        last_output = output
        if code != 0:
            print(f"\n⛔ {name} 失败（exit {code}），停止后续步骤", file=sys.stderr)
            break

    print(f"\n{'='*50}\n📊 执行状态\n{'='*50}", file=sys.stderr)
    for name, s in status.items():
        print(f"  {s} {name}", file=sys.stderr)

    if args.push_feishu and status.get("⑦ 飞书推送 (push_feishu)") == "✅":
        # 提取最后一行 URL
        lines = [l for l in last_output.strip().split("\n") if l.startswith("http")]
        if lines:
            print(f"\n🎉 飞书文档链接: {lines[-1]}")

    print(f"\n📁 产物目录: {workdir}", file=sys.stderr)


if __name__ == "__main__":
    main()
