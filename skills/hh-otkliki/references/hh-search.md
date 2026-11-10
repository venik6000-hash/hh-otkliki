# Механика hh.ru: поиск, пул и тексты вакансий

Все запросы выполняй из вкладки, открытой на hh.ru, где человек вошёл в аккаунт. API `api.hh.ru` без токена отвечает `{"errors":[{"type":"forbidden"}]}`. Данные страницы лежат в JSON внутри `<template id="HH-Lux-InitialState">`.

## Сбор пула

Вставь функцию в JS-инструмент браузера на вкладке hh.ru:

```js
window.__hhSearch = async function(q, extra) {
  const url = 'https://hh.ru/search/vacancy?order_by=publication_time&items_on_page=50&text='
    + encodeURIComponent(q) + (extra || '');
  const html = await fetch(url, {credentials: 'include'}).then(r => r.text());
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const tpl = doc.querySelector('template#HH-Lux-InitialState');
  if (!tpl) return {q, err: 'no state'};
  const r = JSON.parse(tpl.innerHTML).vacancySearchResult || {};
  return {q, found: r.found, items: (r.vacancies || []).map(v => ({
    id: v.vacancyId,
    n: v.name,
    c: v.company && v.company.name,
    s: v.compensation && (v.compensation.from || v.compensation.to)
       ? ((v.compensation.from || '') + '-' + (v.compensation.to || '')) : null
  }))};
};
```

Полезные параметры для `extra`:

| Параметр | Что делает |
|---|---|
| `&work_format=REMOTE` | только удалёнка |
| `&area=1` | Москва; `113` — вся Россия, `2` — Санкт-Петербург |
| `&search_period=3` | вакансии младше трёх дней |
| `&search_field=name` | поиск только по заголовку: меньше мусора, меньше охват |
| `&experience=between3And6` | опыт 3–6 лет |

1. Возьми запросы из `профиль.md`, раздел «Поисковые запросы». Если раздела нет, составь 8–15 запросов из целевых ролей и покажи человеку.
2. Прогони запросы, собери результаты в `Map` по id.
3. Отфильтруй по стоп-словам в заголовке и по `реестр.md`.
4. Печатай список кусками по 12–15 строк: вывод инструмента обрезается.
5. Сохрани пул в `tmp/волна_{N}/pool.json`.

**Свежесть:** начинай с `&search_period=3`. Расширяй окно до 7 дней, только если пул не набирается, и отметь это в отчёте.

## Полный текст вакансии

Письмо пишется от полного текста, выдачи поиска мало. Вставь функцию:

```js
window.__hhVacancy = async function(id) {
  const html = await fetch('https://hh.ru/vacancy/' + id, {credentials: 'include'}).then(r => r.text());
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const tpl = doc.querySelector('template#HH-Lux-InitialState');
  if (!tpl) return {id, err: 'no state'};
  let v;
  try { v = JSON.parse(tpl.innerHTML).vacancyView.vacancyFull.vacancy; } catch (e) { return {id, err: 'no vacancy'}; }
  const d = new DOMParser().parseFromString(v.description || '', 'text/html');
  d.querySelectorAll('li').forEach(li => li.prepend('- '));
  d.querySelectorAll('p,li,br,h1,h2,h3,h4,div').forEach(el => el.append('\n'));
  const c = v.compensation || {};
  const meta = [
    ['Компания', v.company && v.company.name],
    ['Регион', v.area && v.area.name],
    ['Зарплата', (c.from || c.to) ? [c.from, c.to].filter(Boolean).join('–') + ' ' + (c.currencyCode || '') : 'не указана'],
    ['Опыт', v.workExperience],
    ['Формат', (v.workFormats || []).join(', ')],
    ['Языки', (v.languages || []).map(l => (l.isoCode || '') + ' ' + (l.degree || '')).join(', ')],
    ['Навыки', (v.keySkills || []).join(', ')],
    ['Опубликована', (v.publicationTimeIso || '').slice(0, 10)],
    ['Архив', v.status && v.status.archived ? 'да' : '']
  ].filter(x => x[1]).map(x => x[0] + ': ' + x[1]).join('\n');
  const body = d.body.textContent.replace(/\n\s*\n+/g, '\n\n').trim();
  return '# ' + id + ' — ' + v.name + '\n' + meta + '\n\n## Описание\n\n' + body + '\n';
};
```

1. Вызови `await __hhVacancy(<id>)` для каждой вакансии пула.
2. Сохрани ответ в `tmp/волна_{N}/vacancies/{id}.md`.
3. Уже скачанные вакансии повторно не скачивай.

Имена менеджеров и контакты работодателя функция не берёт.

## Вывод JS-инструмента

JS-инструмент иногда блокирует вывод, если в нём есть строка, похожая на токен или хэш.

**Запрещено:** возвращать из скрипта хэши и URL с параметрами. Сохраняй их в переменные, возвращай только нужные поля.
