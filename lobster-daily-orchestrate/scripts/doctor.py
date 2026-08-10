#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-doctor · 环境与权限预检

检查龙虾日报系统能否开箱即用：Python、脚本、配置、网络、飞书凭证/权限。

零第三方依赖：只用 Python 标准库。

用法：
    python3 doctor.py              # 全量检查
    python3 doctor.py --feishu     # 只检查飞书
    python3 doctor.py --sources    # 只检查信息源配置
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent  # lobster-daily-orchestrate 根


def check(name, ok, detail=""):
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 环境预检")
    parser.add_argument("--feishu", action="store_true", help="只检查飞书")
    parser.add_argument("--sources", action="store_true", help="只检查信息源配置")
    args = parser.parse_args()

    print(f"\n🔍 龙虾日报环境预检\n{'='*50}")

    if not args.feishu and not args.sources:
        # ---- Python ----
        print("\n[1] Python")
        check("Python 3.8+", sys.version_info >= (3, 8), f"{sys.version.split()[0]}")

        # ---- 脚本 ----
        print("\n[2] 脚本")
        scripts = {
            "采集 fetch_rss.py": SKILLS_DIR.parent / "lobster-rss-collect" / "scripts" / "fetch_rss.py",
            "需求 extract_needs.py": SKILLS_DIR.parent / "lobster-needs-extract" / "scripts" / "extract_needs.py",
            "评分 score_filter.py": SKILLS_DIR.parent / "lobster-score-filter" / "scripts" / "score_filter.py",
            "提炼 distill.py": SKILLS_DIR.parent / "lobster-distill" / "scripts" / "distill.py",
            "日报 build_daily.py": SKILLS_DIR / "scripts" / "build_daily.py",
            "Mermaid render_mermaid.py": SKILLS_DIR / "scripts" / "render_mermaid.py",
            "飞书 push_feishu.py": SKILLS_DIR / "scripts" / "push_feishu.py",
            "入口 run_daily.py": SKILLS_DIR / "scripts" / "run_daily.py",
        }
        for name, path in scripts.items():
            check(name, path.exists(), str(path) if path.exists() else f"缺少: {path}")
            if path.exists():
                # 语法检查
                r = subprocess.run(["python3", "-m", "py_compile", str(path)],
                                   capture_output=True, text=True)
                check(f"  {name} 语法", r.returncode == 0)

        # ---- 配置 ----
        print("\n[3] 信息源配置")
        sources_path = SKILLS_DIR.parent / "lobster-rss-collect" / "config" / "sources.yaml"
        check("sources.yaml 存在", sources_path.exists())
        if sources_path.exists():
            import sys as _sys
            sys.path.insert(0, str(SKILLS_DIR.parent / "lobster-rss-collect" / "scripts"))
            try:
                from fetch_rss import load_sources
                s = load_sources(sources_path)
                check("配置可解析", True, f"{len(s['rss_feeds'])} 个 RSS 源, {len(s['api_sources'])} 个 API 源")
            except Exception as e:
                check("配置可解析", False, str(e))

        # ---- 画像 ----
        print("\n[4] 需求画像")
        profile = SKILLS_DIR.parent / "lobster-needs-extract" / "data" / "user-profile.json"
        check("画像存在", profile.exists())
        if profile.exists():
            try:
                p = json.loads(profile.read_text(encoding="utf-8"))
                check("画像可读", True, f"{len(p.get('needs', []))} 条需求")
            except Exception as e:
                check("画像可读", False, str(e))

    if not args.sources:
        # ---- 飞书 ----
        print("\n[5] 飞书配置")
        app_id = os.environ.get("FEISHU_APP_ID", "")
        app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        owner = os.environ.get("FEISHU_OWNER_OPEN_ID", "")
        check("FEISHU_APP_ID", bool(app_id))
        check("FEISHU_APP_SECRET", bool(app_secret))
        check("FEISHU_OWNER_OPEN_ID", bool(owner), "文档创建后给该用户授权")

        if app_id and app_secret:
            print("\n[6] 飞书 API 可用性")
            try:
                body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
                req = urllib.request.Request(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    data=body, headers={"Content-Type": "application/json; charset=utf-8"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    d = json.loads(resp.read().decode())
                check("token 获取", d.get("code") == 0, d.get("msg", ""))
                if d.get("code") == 0:
                    token = d["tenant_access_token"]
                    # 测试创建文档（dry 测试：创建后删掉？先只测创建）
                    try:
                        body2 = json.dumps({"title": "🦞 doctor 测试文档"}).encode()
                        req2 = urllib.request.Request(
                            "https://open.feishu.cn/open-apis/docx/v1/documents",
                            data=body2,
                            headers={"Authorization": f"Bearer {token}",
                                     "Content-Type": "application/json; charset=utf-8"})
                        with urllib.request.urlopen(req2, timeout=20) as resp2:
                            d2 = json.loads(resp2.read().decode())
                        check("docx 创建权限", d2.get("code") == 0, d2.get("msg", ""))
                        if d2.get("code") == 0:
                            doc_id = d2["data"]["document"]["document_id"]
                            print(f"      🧪 测试文档已创建（doc_id={doc_id}），可手动删除")
                    except Exception as e:
                        check("docx 创建权限", False, str(e))
            except Exception as e:
                check("飞书 API 连通", False, str(e))

    if args.sources:
        # 只检查源
        print("\n[3] 信息源配置")
        sources_path = SKILLS_DIR.parent / "lobster-rss-collect" / "config" / "sources.yaml"
        check("sources.yaml 存在", sources_path.exists())

    print(f"\n{'='*50}\n预检完成。运行 python3 run_daily.py --push-feishu 一键出日报。")


if __name__ == "__main__":
    main()
