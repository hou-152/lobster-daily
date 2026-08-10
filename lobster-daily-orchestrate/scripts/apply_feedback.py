#!/usr/bin/env python3
"""把经防污染处理的显式反馈写入需求画像。"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="龙虾日报 · 应用画像反馈")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--action", required=True, choices=("up", "down"))
    parser.add_argument("--amount", type=float, default=0.2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.amount <= 0:
        parser.error("--amount 必须大于 0")

    profile_path = Path(args.profile)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    need = next((n for n in profile.get("needs", []) if n.get("keyword") == args.keyword), None)
    if need is None:
        print(f"⚠️ 找不到完全匹配的 keyword: {args.keyword}", file=sys.stderr)
        return 1

    old_weight = float(need.get("weight", 1.0))
    pending = need.get("feedback_pending")
    if not isinstance(pending, dict):
        pending = {}
    pending = {"up": int(pending.get("up", 0)), "down": int(pending.get("down", 0))}
    opposite = "down" if args.action == "up" else "up"
    weight_changed = False

    if pending[opposite] > 0:
        pending[opposite] -= 1
    else:
        pending[args.action] += 1
        if pending[args.action] >= 2:
            delta = args.amount if args.action == "up" else -args.amount
            need["weight"] = round(min(5.0, max(1.0, old_weight + delta)), 10)
            pending = {"up": 0, "down": 0}
            weight_changed = need["weight"] != old_weight

    need["feedback_pending"] = pending
    now = datetime.now(timezone.utc).isoformat()
    need["last_seen"] = now
    profile["updated_at"] = now

    new_weight = float(need.get("weight", old_weight))
    print(json.dumps({
        "keyword": args.keyword,
        "action": args.action,
        "weight_before": old_weight,
        "weight_after": new_weight,
        "feedback_pending": pending,
        "effective": weight_changed,
        "dry_run": args.dry_run,
    }, ensure_ascii=False))

    if args.dry_run:
        return 0

    if weight_changed:
        backup = profile_path.with_name("user-profile.backup.json")
        if backup.exists():
            backup.unlink()
        shutil.copy2(profile_path, backup)
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
