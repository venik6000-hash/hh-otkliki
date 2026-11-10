#!/usr/bin/env python3
"""Стадии вакансий волны в tmp/волна_N/state.json.

    python3 _tools/state.py mark <id>... --wave tmp/волна_N --stage <стадия> [--skip-by чтение|человек] [--reason "..."]
    python3 _tools/state.py show --wave tmp/волна_N

Стадии: пул → карточка → письмо → проверено → согласовано → отправлено | пропущено.
Для «пропущено» обязателен --skip-by.
"""
import argparse
import datetime
import json
import pathlib
import sys
from collections import Counter

STAGES = ["пул", "карточка", "письмо", "проверено", "согласовано", "отправлено", "пропущено"]
FINAL = {"отправлено", "пропущено"}


def load(wave):
    p = pathlib.Path(wave) / "state.json"
    return p, (json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})


def cmd_mark(a):
    if a.stage == "пропущено" and not a.skip_by:
        sys.exit("Для стадии «пропущено» укажи --skip-by чтение|человек")
    p, st = load(a.wave)
    p.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    for vid in a.ids:
        rec = st.setdefault(str(vid), {})
        rec["stage"] = a.stage
        rec["updated"] = today
        if a.skip_by:
            rec["skip_by"] = a.skip_by
        if a.reason:
            rec["reason"] = a.reason
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(a.ids)} → {a.stage}; всего в волне {len(st)}")
    return 0


def cmd_show(a):
    _, st = load(a.wave)
    if not st:
        print("state.json пуст или нет")
        return 0
    c = Counter(r.get("stage") for r in st.values())
    for s in STAGES:
        if c.get(s):
            print(f"  {s:<12} {c[s]}")
    open_ = [k for k, r in st.items() if r.get("stage") not in FINAL]
    print(f"Незавершённых: {len(open_)}" + (f" {open_}" if open_ else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Стадии вакансий волны")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mark")
    m.add_argument("ids", nargs="+")
    m.add_argument("--wave", required=True)
    m.add_argument("--stage", required=True, choices=STAGES)
    m.add_argument("--skip-by", choices=["чтение", "человек"])
    m.add_argument("--reason")
    s = sub.add_parser("show")
    s.add_argument("--wave", required=True)
    a = ap.parse_args()
    return cmd_mark(a) if a.cmd == "mark" else cmd_show(a)


if __name__ == "__main__":
    sys.exit(main())
