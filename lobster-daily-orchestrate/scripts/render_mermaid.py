#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-render-mermaid · Mermaid 架构图渲染器

扫描 Markdown 中的 ```mermaid 代码块，调用 mermaid.ink 渲染为 PNG，
缓存到 artifacts/images/，返回替换后的 Markdown + 图片清单。

零第三方依赖：只用 Python 标准库。

用法：
    python3 render_mermaid.py --input daily.md --output daily-rendered.md
    python3 render_mermaid.py --input daily.md --backend none   # 不渲染，仅扫描
    python3 render_mermaid.py --input daily.md --dry-run

输出：
    - daily-rendered.md（Mermaid 块替换为图片占位）
    - artifacts/images/mermaid-{hash}.png（缓存）
    - stdout 打印图片清单
"""

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

TIMEOUT = 15
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB 上限


def extract_mermaid_blocks(md_text: str) -> list:
    """提取所有 ```mermaid ... ``` 块，返回 [(start, end, code)]。"""
    blocks = []
    pattern = re.compile(r"```mermaid\s*\n(.*?)```", re.S)
    for m in pattern.finditer(md_text):
        blocks.append((m.start(), m.end(), m.group(1).strip()))
    return blocks


def render_mermaid_ink(code: str) -> bytes:
    """调用 mermaid.ink 渲染 PNG。返回图片字节，失败抛异常。"""
    b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
    # URL 编码 base64（mermaid.ink 需要）
    url = "https://mermaid.ink/img/" + urllib.parse.quote(b64, safe="")
    req = urllib.request.Request(url, headers={"User-Agent": "lobster-daily/0.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = resp.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise RuntimeError(f"图片过大: {len(data)} bytes")
    # mermaid.ink 可能返回 PNG 或 JPEG，都接受
    is_png = data.startswith(b"\x89PNG")
    is_jpeg = data.startswith(b"\xff\xd8\xff")
    if not (is_png or is_jpeg):
        raise RuntimeError("返回内容不是图片（PNG/JPEG）")
    return data


def render_all(md_text: str, backend: str, images_dir: Path,
               verbose: bool = True) -> tuple:
    """渲染所有 Mermaid 块，返回 (替换后文本, 图片清单)。"""
    blocks = extract_mermaid_blocks(md_text)
    if not blocks:
        return md_text, []

    images_dir.mkdir(parents=True, exist_ok=True)
    image_manifest = []

    # 从后往前替换，避免位置偏移
    for start, end, code in reversed(blocks):
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
        img_path = images_dir / f"mermaid-{code_hash}.png"
        rel_path = f"images/mermaid-{code_hash}.png"

        if backend == "none":
            # 不渲染：保留代码 + 提示
            placeholder = (
                f"\n> 📊 概念架构图（未渲染，后端=none）\n"
                f"> 源码：{rel_path}\n"
                f"```mermaid\n{code}\n```\n"
            )
            image_manifest.append({"hash": code_hash, "rendered": False, "path": None})
        else:
            try:
                if not img_path.exists():
                    data = render_mermaid_ink(code)
                    img_path.write_bytes(data)
                    if verbose:
                        print(f"  ✅ 渲染: {rel_path} ({len(data)} bytes)", file=sys.stderr)
                else:
                    if verbose:
                        print(f"  ♻️  缓存命中: {rel_path}", file=sys.stderr)
                placeholder = f"\n![概念架构图]({rel_path})\n"
                image_manifest.append({"hash": code_hash, "rendered": True, "path": str(rel_path)})
            except Exception as e:
                # 渲染失败：保留代码 + 明确提示，不静默
                placeholder = (
                    f"\n> ⚠️ 架构图渲染失败：{e}\n"
                    f"> 源码：\n"
                    f"```mermaid\n{code}\n```\n"
                )
                image_manifest.append({"hash": code_hash, "rendered": False, "error": str(e)})

        md_text = md_text[:start] + placeholder + md_text[end:]

    return md_text, image_manifest


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · Mermaid 架构图渲染器")
    parser.add_argument("--input", required=True, help="输入 Markdown")
    parser.add_argument("--output", default=None, help="输出 Markdown（默认覆盖输入）")
    parser.add_argument("--images-dir", default="artifacts/images", help="图片缓存目录")
    parser.add_argument("--backend", default="mermaid-ink", choices=["mermaid-ink", "none"], help="渲染后端")
    parser.add_argument("--manifest", default=None, help="图片清单输出路径（JSON）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不渲染")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 找不到输入文件: {input_path}", file=sys.stderr)
        sys.exit(1)
    md_text = input_path.read_text(encoding="utf-8")

    blocks = extract_mermaid_blocks(md_text)
    print(f"📊 发现 {len(blocks)} 个 Mermaid 块", file=sys.stderr)

    if args.dry_run:
        for i, (_, _, code) in enumerate(blocks, 1):
            h = hashlib.sha256(code.encode()).hexdigest()[:16]
            print(f"  [{i}] hash={h} 首行: {code.splitlines()[0] if code else '(空)'}", file=sys.stderr)
        sys.exit(0)

    if args.backend == "none":
        print("ℹ️  后端=none，不渲染", file=sys.stderr)

    new_text, manifest = render_all(
        md_text, args.backend, Path(args.images_dir), verbose=True
    )

    out_path = Path(args.output) if args.output else input_path
    out_path.write_text(new_text, encoding="utf-8")
    print(f"💾 已写入: {out_path}", file=sys.stderr)

    if args.manifest:
        m_path = Path(args.manifest)
        m_path.parent.mkdir(parents=True, exist_ok=True)
        m_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 清单: {m_path}", file=sys.stderr)

    rendered = [m for m in manifest if m.get("rendered")]
    failed = [m for m in manifest if not m.get("rendered")]
    print(f"\n📈 渲染成功 {len(rendered)} / 失败 {len(failed)}", file=sys.stderr)
    for m in rendered:
        print(f"  ✅ {m['path']}", file=sys.stderr)
    for m in failed:
        print(f"  ⚠️  {m.get('error', '未渲染')}", file=sys.stderr)


if __name__ == "__main__":
    main()
