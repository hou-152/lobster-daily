#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lobster-needs-extract · 需求倒推器（越聊越懂你的核心）

扫描对话记录，提取用户需求信号（显式 + 隐式），更新 user-profile.json。

显式需求：用户直接说的（"我关心XX"、"帮我找XX"、"我想做XX"）
隐式需求：用户反复问/讨论的主题（频次驱动，标置信度）

零第三方依赖：只用 Python 标准库。

用法：
    python3 extract_needs.py                          # 扫昨日对话
    python3 extract_needs.py --days 3                 # 扫最近3天
    python3 extract_needs.py --sessions /path/to/sessions
    python3 extract_needs.py --profile data/user-profile.json

输出：更新 data/user-profile.json（QMD 可索引）
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 默认会话目录（OpenClaw 格式），可配置
DEFAULT_SESSIONS = Path.home() / ".openclaw-lobster2" / "agents" / "main" / "sessions"
DEFAULT_PROFILE = Path(__file__).parent.parent / "data" / "user-profile.json"

# 显式需求关键词（中文 + 英文）
# 注意：alternation 中长词在前（想要>想），避免前缀拆错
# 注意：不收录单字「想」「我」——召回率虽高但精确率太低（“我觉得这个方案不行”会被误提取）
EXPLICIT_PATTERNS = [
    r"(?:我们|想要|需要|希望|关注|关心|感兴趣|研究一下|研究|学习|了解|试试|解决|优化|改进|做一个|搭一个|写一个|做|要)\s*(?:一个|一下|点|的)?\s*([^，。！？\n]{2,30})",
    r"(?:帮我|给我|推荐|找找|找|搜索|查|看看|研究一下|调研|对比)\s*([^，。！？\n]{2,30})",
    r"(?:这个|那个|这|那)\s*(?:问题|主题|方向|项目|东西|想法|概念|产品|工具)\s*(?:怎么样|怎么看|怎么做|是什么|好不好|值不值|可行吗)",
]

# 伪需求过滤：提取出的信号包含这些短语时，判定为日常对话噪音
# 注意：用包含匹配（signal 里出现即过滤），覆盖"需要注意安全""想看看这个工具""这个工具"等变体
FAKE_SIGNAL_PREFIXES = [
    "想一下", "想一想", "想看看", "注意", "看看", "想想", "试试", "问问", "确认", "检查",
    "修改", "整理", "继续", "完成", "更新", "测试", "验证", "跑一下", "执行", "排查",
    "这个理念", "方面", "时候", "事情", "情况", "样子", "这个", "那个", "这些", "那些",
    "不是", "没有", "什么", "怎么", "为什么",
]

# 停用词（过滤噪音）
STOPWORDS = {
    "这个", "那个", "什么", "怎么", "为什么", "可以", "一个", "一下", "真的",
    "感觉", "觉得", "知道", "明白", "看看", "好的", "嗯", "啊", "吧", "吗",
    "我们", "你们", "他们", "然后", "但是", "因为", "所以", "如果", "就是",
    "对了", "还有", "其实", "应该", "可能", "没有", "不是", "这样", "那样",
    "任何", "修改", "要求", "请", "需要", "注意", "不要", "必须", "直接",
    "继续", "现在", "今天", "昨天", "明天", "之前", "之后", "时候", "东西",
    "意思", "问题", "情况", "方式", "方法", "事情", "方面", "相关", "有关",
    "以及", "或者", "并且", "同时", "另外", "其它", "其他", "这里", "那里",
    "自己", "别人", "大家", "目前", "先", "再", "很", "太", "只", "都",
    "也", "还", "就", "又", "跟", "和", "与", "对", "给", "把",
    # 技术/格式噪音
    "https", "http", "com", "org", "net", "io", "html", "xml", "json",
    "url", "rss", "api", "cron", "skill", "codex", "openclaw", "heartbeat",
    "poll", "feed", "rsshub", "github", "notion", "readwise", "python",
    "file", "files", "path", "data", "config", "docs", "outputs", "memory",
}


def load_conversations(sessions_dir: Path, days: int) -> list:
    """读取最近 N 天的用户消息文本（过滤系统事件/非用户真实发言/URL噪音/重复）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    texts = []
    seen = set()
    for f in sessions_dir.glob("*.jsonl"):
        if ".trajectory" in f.name:
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") != "message":
                    continue
                msg = d.get("message", {})
                if msg.get("role") != "user":
                    continue
                # 跳过 OpenClaw 内部注入（systemEvent / cron 等，非真实用户发言）
                oc = msg.get("__openclaw", {}) or {}
                if not oc.get("senderIsOwner"):
                    continue
                content = msg.get("content", "")
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(c.get("text", ""))
                    content = " ".join(parts)
                if isinstance(content, str) and content.strip():
                    # 去掉消息信封前缀（[message_id: ...] 和 sender 前缀）
                    content = re.sub(r"^\[message_id: [^\]]*\]\s*", "", content)
                    content = re.sub(r"^ou_[a-z0-9]+:\s*", "", content)
                    # 去掉 URL 噪音（保留上下文但截断长 URL 列表消息）
                    url_ratio = len(re.findall(r"https?://\S+", content)) / max(len(content), 1)
                    if url_ratio > 0.15:
                        continue  # 纯链接列表消息（如 RSS 源清单），不是需求信号
                    content = re.sub(r"https?://\S+", "", content)
                    # 跳过纯系统/格式噪音
                    if re.match(r"^(Current time|OpenClaw|MEMORY\.md|docs/|outputs/|cron|V2工作区|harness|heartbeat|Continue the)", content):
                        continue
                    # 去重（同一消息多次发送/重试）
                    norm = re.sub(r"\s+", "", content)[:80]
                    if norm in seen:
                        continue
                    seen.add(norm)
                    if len(content.strip()) < 4:
                        continue
                    texts.append(content.strip())
        except Exception:
            continue
    return texts


def extract_explicit(texts: list) -> Counter:
    """提取显式需求信号（规则匹配 + 伪需求过滤）。"""
    signals = Counter()
    for text in texts:
        for pattern in EXPLICIT_PATTERNS:
            for m in re.finditer(pattern, text):
                signal = m.group(1).strip()
                # 过滤停用词和过短/过长
                if len(signal) < 2 or len(signal) > 30:
                    continue
                if signal in STOPWORDS:
                    continue
                # 过滤伪需求：signal 包含任一伪需求短语（"想一下""注意""看看""这个"等）
                if any(p in signal for p in FAKE_SIGNAL_PREFIXES):
                    continue
                # 过滤纯标点/纯语气
                if re.fullmatch(r"[\W_]+", signal):
                    continue
                signals[signal] += 1
    return signals


def extract_implicit(texts: list) -> Counter:
    """提取隐式需求（高频名词/短语，频次驱动）。"""
    # 简单分词：提取中文连续片段和英文单词
    tokens = []
    for text in texts:
        # 中文 2-6 字连续片段
        tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,6}", text))
        # 英文/数字词（3+ 字符）
        tokens.extend(re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,30}", text))
    counter = Counter()
    for t in tokens:
        if t in STOPWORDS or len(t) < 2:
            continue
        counter[t] += 1
    return counter


def merge_profile(profile_path: Path, explicit: Counter, implicit: Counter,
                  days: int, min_implicit_count: int = 2) -> dict:
    """合并需求信号到 user-profile.json（带衰减和置信度）。"""
    # 读取现有画像
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            profile = {}
    else:
        profile = {}

    profile.setdefault("version", 1)
    profile.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    profile.setdefault("needs", [])

    # 现有需求索引
    existing = {n["keyword"]: n for n in profile["needs"]}

    # 衰减：显式需求慢（×0.9，用户明确说过要长期稳定），隐式需求快（×0.7）
    # 记录衰减前权重（临时字段，写盘前清理），供“重新发现时只重置衰减”使用
    for n in profile["needs"]:
        decay = 0.9 if n.get("type") == "explicit" else 0.7
        n["_pre_decay_weight"] = n.get("weight", 1)
        n["weight"] = round(n.get("weight", 1) * decay, 2)

    # 合并显式需求（权重高）
    for signal, count in explicit.most_common(20):
        if signal in existing:
            existing[signal]["weight"] = min(5, existing[signal]["weight"] + count)
            existing[signal]["type"] = "explicit"
            existing[signal]["last_seen"] = datetime.now(timezone.utc).isoformat()
            existing[signal]["_explicit_updated"] = True  # 隐式阶段不覆盖显式增量
        else:
            new_need = {
                "keyword": signal,
                "type": "explicit",
                "weight": min(5, count),
                "confidence": 0.8,  # 显式需求置信度高
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }
            profile["needs"].append(new_need)
            # 同步索引：否则同轮隐式阶段会再插入一条相同 keyword 的重复项
            existing[signal] = new_need
            existing[signal]["_explicit_updated"] = True

    # 合并隐式需求（频次 >= 阈值才收录，置信度按频次）
    # 注意：隐式需求重新发现时只重置衰减（恢复到衰减前权重），不额外加回——
    # 否则“持续讨论”会因反复扫描无限膨胀，隐式比显式更持久，违背衰减设计。
    for token, count in implicit.most_common(30):
        if count < min_implicit_count:
            continue
        if token in existing:
            # 显式阶段已加过权（用户明确表达过）：隐式只更新 last_seen，不覆盖
            if not existing[token].get("_explicit_updated"):
                existing[token]["weight"] = min(5, existing[token].get("_pre_decay_weight", existing[token]["weight"]))
            existing[token]["last_seen"] = datetime.now(timezone.utc).isoformat()
        else:
            confidence = min(0.7, 0.3 + count * 0.1)
            profile["needs"].append({
                "keyword": token,
                "type": "implicit",
                "weight": min(5, count * 0.5),
                "confidence": round(confidence, 2),
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
            })

    # 清理临时字段（不写入画像文件）
    for n in profile["needs"]:
        n.pop("_pre_decay_weight", None)
        n.pop("_explicit_updated", None)

    # 清理权重过低的（< 0.3），避免画像膨胀
    profile["needs"] = [
        n for n in profile["needs"]
        if n.get("weight", 0) >= 0.3 and len(n.get("keyword", "")) >= 2
    ]
    # 按权重排序
    profile["needs"].sort(key=lambda n: n.get("weight", 0), reverse=True)
    # 限制最多 50 条
    profile["needs"] = profile["needs"][:50]
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    profile["meta"] = {
        "scan_days": days,
        "explicit_count": len(explicit),
        "implicit_count": len(implicit),
    }

    return profile


def main():
    parser = argparse.ArgumentParser(description="龙虾日报 · 需求倒推器")
    parser.add_argument("--sessions", default=str(DEFAULT_SESSIONS), help="会话目录")
    parser.add_argument("--days", type=int, default=1, help="扫描最近 N 天")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE), help="画像输出路径")
    parser.add_argument("--min-implicit", type=int, default=2, help="隐式需求最低频次")
    parser.add_argument("--dry-run", action="store_true", help="只展示不写文件")
    args = parser.parse_args()

    sessions_dir = Path(args.sessions)
    if not sessions_dir.exists():
        print(f"❌ 会话目录不存在: {sessions_dir}", file=sys.stderr)
        sys.exit(1)

    texts = load_conversations(sessions_dir, args.days)
    if not texts:
        print(f"⚠️ 最近 {args.days} 天没有用户消息", file=sys.stderr)
        sys.exit(0)

    print(f"📝 读取 {len(texts)} 条用户消息（最近 {args.days} 天）", file=sys.stderr)

    explicit = extract_explicit(texts)
    implicit = extract_implicit(texts)

    print(f"\n🔍 显式需求信号 Top 10:", file=sys.stderr)
    for s, c in explicit.most_common(10):
        print(f"  [{c}] {s}", file=sys.stderr)

    print(f"\n🔍 隐式高频主题 Top 10:", file=sys.stderr)
    for s, c in implicit.most_common(10):
        print(f"  [{c}] {s}", file=sys.stderr)

    profile = merge_profile(
        Path(args.profile), explicit, implicit, args.days, args.min_implicit
    )

    if args.dry_run:
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        return

    profile_path = Path(args.profile)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n💾 画像已更新: {profile_path}（{len(profile['needs'])} 条需求）", file=sys.stderr)
    print(f"\n🏆 当前 Top 5 需求:", file=sys.stderr)
    for n in profile["needs"][:5]:
        print(f"  {n['weight']:.1f} | [{n['type']}] {n['keyword']} (conf={n['confidence']})", file=sys.stderr)


if __name__ == "__main__":
    main()
