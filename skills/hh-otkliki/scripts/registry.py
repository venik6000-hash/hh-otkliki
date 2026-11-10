#!/usr/bin/env python3
"""Реестр откликов: статистика и обновление статусов из кабинета hh.

    python3 _tools/registry.py stats
    python3 _tools/registry.py update tmp/negotiations.json [--dry-run]

Реестр — файл `реестр.md` в рабочей папке, одна таблица:
| Волна | Дата | Компания | Должность | Резюме | Статус | Примечание | Ссылка |

`update` принимает JSON со страницы https://hh.ru/applicant/negotiations:
весь объект из <template id="HH-Lux-InitialState">, только `applicantNegotiations`
или список топиков. Скрипт сам находит `topicList` и `vacanciesShort.vacanciesList`.
Перевод статусов: RESPONSE → «ждёт ответа», DISCARD → «отказ», INTERVIEW → «собеседование».
Топик с `archived` (вкладка «Архив» кабинета) → «вакансия снята», стоящий «отказ» сохраняется.
«Отказ» с пометкой «закрыт» в примечании скрипт не переоткрывает.
Пометку `hh: просмотрен` / `hh: не просмотрен` в примечании скрипт ведёт сам.
Расхождения между кабинетом и реестром только печатаются: решение за человеком.
Без --dry-run файл перезаписывается.
"""
import sys, re, json, datetime, difflib, pathlib
from collections import Counter, OrderedDict


def root_dir():
    cwd = pathlib.Path.cwd()
    if (cwd / "hh-otkliki.md").exists():
        return cwd
    return pathlib.Path(__file__).resolve().parent.parent


ROOT = root_dir()
REG = ROOT / "реестр.md"
COLS = ["Волна", "Дата", "Компания", "Должность", "Резюме", "Статус", "Примечание", "Ссылка"]
STATE = {"RESPONSE": "ждёт ответа", "DISCARD": "отказ", "INTERVIEW": "собеседование",
         "INVITATION": "собеседование", "HIDDEN": "вакансия снята"}
VALID_STATUS = {"ждёт ответа", "отказ", "собеседование", "вакансия снята"}


def load():
    text = REG.read_text(encoding="utf-8")
    lines = text.splitlines()
    head, rows, header_idx = [], [], None
    for i, line in enumerate(lines):
        if line.startswith("| Волна"):
            header_idx = i
            break
        head.append(line)
    if header_idx is None:
        sys.exit("Не нашёл строку заголовка таблицы «| Волна | …» в реестре")
    for line in lines[header_idx + 2:]:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(COLS):
            print(f"!! строка с {len(cells)} колонками вместо {len(COLS)}: {line[:80]}")
            continue
        rows.append(OrderedDict(zip(COLS, cells)))
    return head, rows


def vacancy_id(link):
    m = re.search(r"vacancy/(\d+)", link or "")
    return m.group(1) if m else None


def dump(head, rows, dry_run):
    out = list(head)
    out.append("| " + " | ".join(COLS) + " |")
    out.append("|" + "---|" * len(COLS))
    for r in rows:
        out.append("| " + " | ".join(r[c] for c in COLS) + " |")
    text = "\n".join(out) + "\n"
    if dry_run:
        print("\n[dry-run] файл не записан")
    else:
        REG.write_text(text, encoding="utf-8")
        print(f"\nЗаписано: {REG} ({len(rows)} строк)")


def stats(rows):
    print(f"Всего откликов: {len(rows)}")
    print("\nПо статусу:")
    for s, n in Counter(r["Статус"] for r in rows).most_common():
        flag = "" if s in VALID_STATUS else "   <- нестандартный статус"
        print(f"  {n:>4}  {s}{flag}")
    print("\nПо волнам:")
    for w, n in sorted(Counter(r["Волна"] for r in rows).items(), key=lambda x: int(x[0]) if x[0].isdigit() else -1):
        print(f"  волна {w:>2}: {n}")
    print("\nПо резюме:")
    for res, n in Counter(r["Резюме"] for r in rows).most_common():
        print(f"  {n:>4}  {res}")
    print("\nСобеседования (проверять чат: автостатус ≠ живой лид):")
    for r in rows:
        if r["Статус"] == "собеседование":
            print(f"  {r['Дата']}  {r['Компания']} — {r['Должность']}  {('(' + r['Примечание'] + ')') if r['Примечание'] else ''}")
    ids = [vacancy_id(r["Ссылка"]) for r in rows if vacancy_id(r["Ссылка"])]
    dups = [i for i, n in Counter(ids).items() if n > 1]
    print(f"\nСо ссылкой на вакансию: {len(ids)} из {len(rows)}; дублей id: {len(dups)}" + (f" {dups}" if dups else ""))
    bad = [r for r in rows if r["Статус"] not in VALID_STATUS]
    if bad:
        print(f"\n!! Нестандартных статусов: {len(bad)} — привести к словарю: {sorted(VALID_STATUS)}")


def find_key(obj, key):
    """Рекурсивно ищет первый список/словарь под указанным ключом."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def topic_vacancy_id(t):
    for k in ("vacancyId", "vacancy_id"):
        if k in t and t[k] is not None:
            return str(t[k])
    v = t.get("vacancy")
    if isinstance(v, dict):
        for k in ("vacancyId", "id"):
            if k in v:
                return str(v[k])
    return None


def norm(s):
    return re.sub(r"[^a-zа-я0-9 ]", " ", (s or "").lower()).split()


def similar(a, b):
    return difflib.SequenceMatcher(None, " ".join(norm(a)), " ".join(norm(b))).ratio()


def set_hh_note(note, viewed):
    parts = [p.strip() for p in note.split(";") if p.strip() and not p.strip().startswith("hh:")]
    parts.insert(0, "hh: просмотрен" if viewed else "hh: не просмотрен")
    return "; ".join(parts)


def update(path, dry_run):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    topics = data if isinstance(data, list) else find_key(data, "topicList")
    if not topics:
        sys.exit("В JSON не нашёл topicList. Нужен объект applicantNegotiations или список топиков.")
    vac_list = find_key(data, "vacanciesList") or []
    vac_by_id = {}
    for v in vac_list:
        vid = str(v.get("vacancyId") or v.get("id") or "")
        if vid:
            vac_by_id[vid] = v
    today = datetime.date.today().strftime("%d.%m.%Y")
    head, rows = load()
    by_id = {}
    for t in topics:
        vid = topic_vacancy_id(t)
        if vid:
            by_id[vid] = t
    print(f"Топиков в кабинете: {len(topics)}, с id вакансии: {len(by_id)}; вакансий в словаре имён: {len(vac_by_id)}")

    hh_rows = rows
    changed, matched_ids, proposals = [], set(), []
    for r in hh_rows:
        vid = vacancy_id(r["Ссылка"])
        t = by_id.get(vid) if vid else None
        if t is None and not vid and vac_by_id:
            # строки без ссылки: пробуем сопоставить по названию компании и вакансии
            best, best_score = None, 0.0
            for cand_id, v in vac_by_id.items():
                if cand_id in matched_ids or cand_id not in by_id:
                    continue
                comp = (v.get("company") or {}).get("name") if isinstance(v.get("company"), dict) else v.get("companyName") or v.get("company")
                score = min(similar(r["Компания"], str(comp or "")), similar(r["Должность"], str(v.get("name") or "")))
                if score > best_score:
                    best, best_score = cand_id, score
            if best and best_score >= 0.6:
                proposals.append((r, best, best_score))
                t, vid = by_id[best], best
                r["Ссылка"] = f"https://hh.ru/vacancy/{best}"
        if t is None:
            continue
        matched_ids.add(vid)
        new_status = STATE.get(str(t.get("lastState") or "").upper())
        if t.get("archived") and new_status in ("ждёт ответа", "собеседование"):
            # вакансия в архиве hh: ответа уже не будет; закрытый вручную отказ не трогаем
            new_status = "отказ" if r["Статус"] == "отказ" else "вакансия снята"
        if r["Статус"] == "отказ" and "закрыт" in r["Примечание"]:
            new_status = "отказ"  # лид закрыт человеком: автостатус hh его не переоткрывает
        if new_status and new_status != r["Статус"]:
            changed.append((r["Компания"], r["Должность"], r["Статус"], new_status))
            r["Статус"] = new_status
        viewed = t.get("viewedByOpponent")
        if viewed is not None:
            r["Примечание"] = set_hh_note(r["Примечание"], bool(viewed))

    print(f"\nСопоставлено строк: {len(matched_ids)} из {len(hh_rows)}")
    if proposals:
        print("\nСопоставления по названию (проверь глазами, ссылка вписана):")
        for r, vid, sc in proposals:
            print(f"  {r['Дата']} {r['Компания']} — {r['Должность']}  ->  {vid}  (сходство {sc:.2f})")
    if changed:
        print("\nИзменения статусов:")
        for c in changed:
            print(f"  {c[0]} — {c[1]}: {c[2]} -> {c[3]}")
    else:
        print("\nИзменений статусов нет")
    missing = [
        row
        for row in hh_rows
        if vacancy_id(row["Ссылка"]) and vacancy_id(row["Ссылка"]) not in by_id
    ]
    if missing:
        print(f"\nВ реестре есть, в кабинете нет ({len(missing)}) — возможно, вакансия снята работодателем; статус не менял:")
        for r in missing:
            print(f"  {r['Дата']} {r['Компания']} — {r['Должность']}  [{r['Статус']}]")
    known_hh_ids = {vacancy_id(row["Ссылка"]) for row in hh_rows}
    extra = [vid for vid in by_id if vid not in known_hh_ids]
    if extra:
        print(f"\nВ кабинете есть, в реестре нет ({len(extra)}):")
        for vid in extra:
            v = vac_by_id.get(vid, {})
            print(f"  {vid}  {v.get('name', '')}")
    # обновить строку сверки в шапке
    for i, line in enumerate(head):
        if line.startswith("> Сверено с кабинетом hh:"):
            head[i] = f"> Сверено с кабинетом hh: {today} (скриптом `registry.py update`)."
    dump(head, rows, dry_run)


def main(argv):
    if len(argv) < 2 or argv[1] not in ("stats", "update"):
        print(__doc__)
        return 2
    if argv[1] == "stats":
        _, rows = load()
        stats(rows)
        return 0
    if len(argv) < 3:
        print("Нужен путь к JSON: registry.py update negotiations.json [--dry-run]")
        return 2
    update(argv[2], "--dry-run" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
