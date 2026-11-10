#!/usr/bin/env python3
"""Механическая проверка сопроводительного письма.

    python3 _tools/letters.py check <файл>          проверить одно письмо (.txt или .md, только текст письма)
    python3 _tools/letters.py check --wave <отчёт>  проверить все письма из отчёта волны
    python3 _tools/letters.py stats                 повторы фраз и первых строк в отправленных письмах

Корпус отправленных писем собирается из разделов «## Тексты писем» отчётов в папке `волны/`.
FAIL — письмо не идёт к человеку, пока ошибка не исправлена. WARN — диагностика.
Скрипт не проверяет достоверность фактов: это делает агент по карьерной базе.
"""
import argparse
import pathlib
import re
import sys
from collections import Counter

MAX_CHARS = 1100
TARGET = (600, 900)
MAX_FIRST = 200
CORPUS_N = 6  # слов подряд, совпадающих с уже отправленными письмами

FORBIDDEN_CHARS = {"—": "длинное тире", "–": "короткое тире", "→": "стрелка"}
MARKERS = ["синерги", "экспертиз", "комплексный подход", "в рамках", "на стыке", "драйв",
           "принести пользу", "быть полезен вашей", "меня заинтересовала", "уникальн",
           "в современном мире", "динамично развивающ", "являюсь", "обладаю"]
RETELL = [r"^вы ищете", r"^ваша задача", r"^в вашей (роли|команде|компании) нужно", r"^вам нужен",
          r"^я увидел(а)? вашу вакансию", r"^меня заинтересовала ваша вакансия", r"^прочитал(а)? вакансию"]
NOT_X_BUT_Y = re.compile(r"\bне\s+[^.,;!?]{1,40},\s*а\s+", re.I)
GREETING = re.compile(r"^(добрый день|доброе утро|добрый вечер|здравствуйте|привет|hello|hi\b|good (morning|afternoon|day)|dear)", re.I)


def root_dir():
    cwd = pathlib.Path.cwd()
    if (cwd / "hh-otkliki.md").exists():
        return cwd
    return pathlib.Path(__file__).resolve().parent.parent


def words(text):
    return re.findall(r"[a-zа-яё0-9]+", text.lower())


def ngrams(text, n):
    w = words(text)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def parse_report(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^## Тексты писем.*?(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return []
    letters, cur = [], None
    for line in m.group(0).splitlines():
        h = re.match(r"^###\s*(\d+)\.\s*(.+?)\s*$", line)
        if h:
            if cur and cur["lines"]:
                letters.append(cur)
            cur = {"src": path.stem, "title": h.group(2), "lines": []}
        elif line.startswith(">") and cur is not None:
            cur["lines"].append(re.sub(r"^>\s?", "", line))
    if cur and cur["lines"]:
        letters.append(cur)
    for l in letters:
        l["text"] = "\n".join(l["lines"]).strip()
    return letters


def corpus(root, exclude=None):
    out = []
    for p in sorted((root / "волны").glob("*.md")):
        if p.name.startswith("_"):
            continue
        if exclude and p.resolve() == exclude.resolve():
            continue
        out.extend(parse_report(p))
    return out


def body_paragraphs(text):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if paras and GREETING.match(paras[0]) and len(paras[0]) < 60:
        paras = paras[1:]
    elif paras and GREETING.match(paras[0]):
        paras[0] = GREETING.sub("", paras[0]).lstrip(" ,!.\n")
    return paras


def check_text(text, known):
    fails, warns = [], []
    n = len(text)
    if n > MAX_CHARS:
        fails.append(f"длина {n} > {MAX_CHARS}")
    elif n < TARGET[0]:
        warns.append(f"длина {n} < {TARGET[0]}: короткое письмо допустимо, если оно содержательное")
    elif n > TARGET[1]:
        warns.append(f"длина {n} больше ориентира {TARGET[1]}")
    for ch, name in FORBIDDEN_CHARS.items():
        if ch in text:
            warns.append(f"{name} «{ch}» ×{text.count(ch)}: заметный признак текста нейросети")
    low = text.lower()
    for m in MARKERS:
        if m in low:
            warns.append(f"канцелярский маркер «{m}»")
    if NOT_X_BUT_Y.search(text):
        warns.append("конструкция «не X, а Y»")
    paras = body_paragraphs(text)
    if paras:
        first = paras[0]
        for pat in RETELL:
            if re.search(pat, first.lower()):
                fails.append(f"начало с пересказа вакансии: «{first[:60]}…»")
                break
        if len(first) > MAX_FIRST:
            warns.append(f"первый содержательный абзац {len(first)} знаков > {MAX_FIRST}")
    if known:
        grams = ngrams(text, CORPUS_N)
        hits = Counter()
        for l in known:
            common = grams & ngrams(l["text"], CORPUS_N)
            if common:
                hits[f"{l['src']} / {l['title']}"] = len(common)
        for src, k in hits.most_common(3):
            warns.append(f"совпадает {k} фраз(ы) по {CORPUS_N} слов с письмом {src}")
    return n, fails, warns


def report(name, n, fails, warns):
    status = "FAIL" if fails else "OK"
    print(f"{status}  {name}  ({n} знаков)")
    for f in fails:
        print(f"  FAIL  {f}")
    for w in warns:
        print(f"  WARN  {w}")
    return bool(fails)


def cmd_check(args):
    root = root_dir()
    bad = False
    if args.wave:
        path = pathlib.Path(args.wave)
        letters = parse_report(path)
        if not letters:
            sys.exit(f"В {path} нет раздела «## Тексты писем» с письмами")
        known = corpus(root, exclude=path)
        for i, l in enumerate(letters):
            others = known + [x for j, x in enumerate(letters) if j != i]
            bad |= report(l["title"], *check_text(l["text"], others))
    else:
        path = pathlib.Path(args.file)
        text = path.read_text(encoding="utf-8").strip()
        text = "\n".join(re.sub(r"^>\s?", "", line) for line in text.splitlines())
        bad = report(path.name, *check_text(text, corpus(root)))
    return 1 if bad else 0


def cmd_stats(_args):
    letters = corpus(root_dir())
    print(f"Писем в корпусе: {len(letters)}")
    if not letters:
        return 0
    first = Counter(body_paragraphs(l["text"])[0][:50] for l in letters if body_paragraphs(l["text"]))
    print("\nЧастые начала:")
    for s, k in first.most_common(5):
        if k > 1:
            print(f"  ×{k}  {s}…")
    grams = Counter()
    for l in letters:
        grams.update(ngrams(l["text"], CORPUS_N))
    print(f"\nФразы по {CORPUS_N} слов, которые повторяются чаще всего:")
    for g, k in grams.most_common(10):
        if k > 2:
            print(f"  ×{k}  {g}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Проверка сопроводительных писем hh-otkliki")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="проверить письмо или отчёт волны")
    c.add_argument("file", nargs="?")
    c.add_argument("--wave", help="путь к отчёту волны")
    sub.add_parser("stats", help="повторы в отправленных письмах")
    args = ap.parse_args()
    if args.cmd == "check" and not (args.file or args.wave):
        ap.error("нужен файл письма или --wave <отчёт>")
    return {"check": cmd_check, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
