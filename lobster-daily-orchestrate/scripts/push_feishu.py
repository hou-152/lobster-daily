#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-push-feishu · 飞书云文档推送器

把日报 Markdown（含图片）推送到飞书云文档，返回文档链接。

零第三方依赖：只用 Python 标准库（urllib + json）。

用法：
    export FEISHU_APP_ID=cli_xxx
    export FEISHU_APP_SECRET=xxx
    export FEISHU_OWNER_OPEN_ID=ou_xxx
    python3 push_feishu.py --input daily-rendered.md --title "🦞 龙虾日报 2026-08-10"
    python3 push_feishu.py --input daily.md --dry-run   # 只解析不推送
    python3 push_feishu.py --input daily.md --images-dir artifacts/images

流程：取 token → 创建 docx → Markdown 转 blocks → 分批写入 → 上传图片 → 权限 → 输出 URL
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

FEISHU_BASE = "https://open.feishu.cn/open-apis"
# 租户域名：用环境变量覆盖，不硬编码（不同用户租户域名不同）
DOC_DOMAIN = os.environ.get("FEISHU_DOC_DOMAIN", "")


def get_token(app_id: str, app_secret: str) -> str:
    """获取 tenant_access_token。"""
    body = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
        data=body, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        d = json.loads(resp.read().decode())
    if d.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {d.get('msg')}")
    return d["tenant_access_token"]


def create_doc(token: str, title: str) -> str:
    """创建 docx 文档，返回 document_id。"""
    body = json.dumps({"title": title}).encode()
    req = urllib.request.Request(
        f"{FEISHU_BASE}/docx/v1/documents",
        data=body, headers={"Authorization": f"Bearer {token}",
                            "Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        d = json.loads(resp.read().decode())
    if d.get("code") != 0:
        raise RuntimeError(f"创建文档失败: {d.get('msg')}")
    return d["data"]["document"]["document_id"]


def parse_inline(text: str) -> list:
    """解析行内 **bold** 和 [text](url)，返回 elements。"""
    elements = []
    pattern = re.compile(r'(\*\*.+?\*\*|\[.+?\]\(.+?\))')
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            elements.append(make_run(text[pos:m.start()]))
        seg = m.group(0)
        if seg.startswith("**") and seg.endswith("**"):
            elements.append(make_run(seg[2:-2], bold=True))
        else:
            lm = re.match(r"\[(.+?)\]\((.+?)\)", seg)
            if lm:
                elements.append(make_run(lm.group(1), link=lm.group(2)))
            else:
                elements.append(make_run(seg))
        pos = m.end()
    if pos < len(text):
        elements.append(make_run(text[pos:]))
    return elements or [make_run("")]


def make_run(text: str, bold: bool = False, link: str = None) -> dict:
    style = {}
    if bold:
        style["bold"] = True
    if link:
        style["link"] = {"url": link}
    return {"text_run": {"content": text, "text_element_style": style}}


def line_to_block(line: str) -> dict:
    """把一行 Markdown 转成飞书 block。"""
    stripped = line.rstrip()
    if not stripped.strip() or stripped.strip() == "---":
        return None
    if stripped.startswith("# "):
        return {"block_type": 3, "heading1": {"elements": parse_inline(stripped[2:]), "style": {}}}
    if stripped.startswith("## "):
        return {"block_type": 4, "heading2": {"elements": parse_inline(stripped[3:]), "style": {}}}
    if stripped.startswith("### "):
        return {"block_type": 5, "heading3": {"elements": parse_inline(stripped[4:]), "style": {}}}
    if stripped.startswith("#### "):
        return {"block_type": 6, "heading4": {"elements": parse_inline(stripped[5:]), "style": {}}}
    if stripped.startswith("> "):
        return {"block_type": 15, "quote": {"elements": parse_inline(stripped[2:]), "style": {}}}
    if stripped.startswith("- "):
        return {"block_type": 12, "bullet": {"elements": parse_inline(stripped[2:]), "style": {}}}
    if re.match(r"^\d+\. ", stripped):
        return {"block_type": 13, "ordered": {"elements": parse_inline(re.sub(r"^\d+\. ", "", stripped)), "style": {}}}
    return {"block_type": 2, "text": {"elements": parse_inline(stripped), "style": {}}}


def write_blocks(token: str, doc_id: str, blocks: list, batch_size: int = 20) -> list:
    """分批写入 blocks，返回写入的 block_id 列表（与 blocks 顺序对应）。"""
    url = f"{FEISHU_BASE}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
    block_ids = []
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        body = json.dumps({"children": batch, "index": -1}).encode()
        req = urllib.request.Request(
            url, data=body,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read().decode())
        if d.get("code") != 0:
            raise RuntimeError(f"写入批次 {i//batch_size+1} 失败: {d.get('msg')}")
        children = d.get("data", {}).get("children", [])
        block_ids.extend(c.get("block_id", "") for c in children)
    return block_ids


def add_permission(token: str, doc_id: str, open_id: str):
    """给用户添加 full_access 权限。"""
    body = json.dumps({
        "member_type": "openid",
        "member_id": open_id,
        "perm": "full_access"
    }).encode()
    url = f"{FEISHU_BASE}/drive/v1/permissions/{doc_id}/members?type=docx"
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            d = json.loads(resp.read().decode())
        return d.get("code") == 0
    except Exception:
        return False


def upload_image(token: str, block_id: str, img_path: Path) -> str:
    """上传图片到飞书 docx（media upload_all），返回 file_token。
    parent_node 必须是 block_id（而非 document_id），否则 token 与 block 无绑定关系。"""
    import uuid
    boundary = uuid.uuid4().hex
    file_bytes = img_path.read_bytes()
    fields = {
        "file_name": img_path.name,
        "parent_type": "docx_image",
        "parent_node": block_id,
        "size": str(len(file_bytes)),
    }
    body = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{img_path.name}\"\r\nContent-Type: image/png\r\n\r\n".encode()
    body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{FEISHU_BASE}/drive/v1/medias/upload_all",
        data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode())
    if d.get("code") != 0:
        raise RuntimeError(f"上传图片失败: {d.get('msg')}")
    return d["data"]["file_token"]


def replace_image(token: str, doc_id: str, block_id: str, file_token: str):
    """PATCH replace_image：把 file_token 绑定到已创建的空 image block。"""
    body = json.dumps({"replace_image": {"token": file_token}}).encode()
    url = f"{FEISHU_BASE}/docx/v1/documents/{doc_id}/blocks/{block_id}"
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
        method="PATCH"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode())
    if d.get("code") != 0:
        raise RuntimeError(f"替换图片失败: {d.get('msg')}")
    return True


def parse_blocks(md_text: str, images_dir: Path = None) -> list:
    """把日报 Markdown 转成 blocks 列表。图片引用转为 _image 占位（main 上传后替换）。"""
    blocks = []
    for line in md_text.split("\n"):
        m = re.match(r"^!\[(.+?)\]\((.+?)\)$", line.strip())
        if m and images_dir is not None:
            img_path = images_dir / Path(m.group(2)).name
            if img_path.exists():
                blocks.append({"_image": img_path})
                continue
        b = line_to_block(line)
        if b:
            blocks.append(b)
    return blocks


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 飞书云文档推送器")
    parser.add_argument("--input", required=True, help="日报 Markdown 路径")
    parser.add_argument("--title", default=None, help="文档标题（默认用文件名）")
    parser.add_argument("--images-dir", default="artifacts/images", help="图片目录")
    parser.add_argument("--dry-run", action="store_true", help="只解析不推送")
    parser.add_argument("--doc-domain", default=os.environ.get("FEISHU_DOC_DOMAIN", DOC_DOMAIN), help="飞书租户域名")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 找不到输入文件: {input_path}", file=sys.stderr)
        sys.exit(1)
    md_text = input_path.read_text(encoding="utf-8")
    title = args.title or f"🦞 龙虾日报 {input_path.stem}"

    blocks = parse_blocks(md_text, Path(args.images_dir) if args.images_dir else None)
    print(f"📄 解析出 {len(blocks)} 个 block", file=sys.stderr)

    if args.dry_run:
        print(f"ℹ️  dry-run：不推送。文档标题: {title}，blocks: {len(blocks)}", file=sys.stderr)
        sys.exit(0)

    # 读取环境变量
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    owner_open_id = os.environ.get("FEISHU_OWNER_OPEN_ID", "")
    if not app_id or not app_secret:
        print("❌ 需要 FEISHU_APP_ID 和 FEISHU_APP_SECRET 环境变量", file=sys.stderr)
        print("   复制 .env.example 为 .env 并填写，或 export 到环境", file=sys.stderr)
        sys.exit(1)
    # 前置校验：租户域名缺失则直接失败（不创建文档后才发现无法生成链接）
    if not args.doc_domain:
        print("❌ 需要 FEISHU_DOC_DOMAIN（飞书租户域名），如 https://你的租户域名.feishu.cn", file=sys.stderr)
        print("   设置: export FEISHU_DOC_DOMAIN=https://xxx.feishu.cn", file=sys.stderr)
        sys.exit(1)

    # 1. 取 token
    print("🔑 获取 token...", file=sys.stderr)
    token = get_token(app_id, app_secret)

    # 2. 创建文档
    print("📝 创建文档...", file=sys.stderr)
    doc_id = create_doc(token, title)

    # 3. 准备 blocks：图片占位转空 image block（先写入拿 block_id，再上传绑定）
    image_slots = []  # (位置索引, 图片路径)
    final_blocks = []
    for b in blocks:
        if isinstance(b, dict) and "_image" in b:
            image_slots.append((len(final_blocks), b["_image"]))
            final_blocks.append({"block_type": 27, "image": {"file_token": ""}})
        else:
            final_blocks.append(b)

    # 4. 写入 blocks
    print("✍️  写入内容...", file=sys.stderr)
    block_ids = write_blocks(token, doc_id, final_blocks)
    print(f"  ✅ 写入 {len(block_ids)} blocks", file=sys.stderr)

    # 5. 逐个上传图片并绑定到对应 block（parent_node=block_id + replace_image）
    for pos, img_path in image_slots:
        if pos >= len(block_ids):
            print(f"  ⚠️ 图片位置越界 {img_path.name}", file=sys.stderr)
            continue
        bid = block_ids[pos]
        try:
            ft = upload_image(token, bid, img_path)
            replace_image(token, doc_id, bid, ft)
            print(f"  🖼️  图片已绑定: {img_path.name}", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️ 图片上传失败 {img_path.name}: {e}", file=sys.stderr)

    # 4. 设置权限
    if owner_open_id:
        ok = add_permission(token, doc_id, owner_open_id)
        print(f"  {'✅' if ok else '⚠️'} 权限设置: {'成功' if ok else '失败（可手动分享）'}", file=sys.stderr)

    # 5. 输出链接
    if not args.doc_domain:
        print(f"\n⚠️ 未配置 FEISHU_DOC_DOMAIN（租户域名），无法生成访问链接", file=sys.stderr)
        print(f"   文档已创建: doc_id={doc_id}", file=sys.stderr)
        print(f"   设置方法: export FEISHU_DOC_DOMAIN=https://你的租户域名.feishu.cn", file=sys.stderr)
        sys.exit(2)
    url = f"{args.doc_domain}/docx/{doc_id}"
    print(f"\n🎉 飞书云文档链接: {url}", file=sys.stderr)
    print(url)  # stdout 最后一行=链接，供 run_daily.py 捕获


if __name__ == "__main__":
    main()
