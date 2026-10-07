# Как участвовать

**[English version](CONTRIBUTING.md)**

Спасибо за помощь! Сообщения об ошибках с небольшим примером (фрагмент `family_tree.json`,
команда, что ожидали) так же ценны, как pull request. Никогда не прикладывайте к issue
настоящие данные о живых людях.

## Устройство

| Путь | Что |
|---|---|
| `gene_archive/cli.py` | команда `gene` |
| `gene_archive/build.py` | сборка: данные → приватность → файлы и превью → `data.json` → страницы → языки |
| `gene_archive/validate.py` | проверка `family_tree.json` и `site.json` |
| `gene_archive/privacy.py` | живые люди и скрытые документы |
| `gene_archive/discovery.py` | статические страницы для поисковиков, sitemap |
| `gene_archive/localize.py` | языковые версии |
| `gene_archive/ged_import.py`, `ged_export.py` | GEDCOM |
| `gene_archive/server.py` | сервер комментариев (только стандартная библиотека) |
| `gene_archive/engine/web/` | приложение в браузере: шаблон `index.html`, `app.js`, `app.css`, Leaflet |
| `gene_archive/engine/i18n/` | словари интерфейса |
| `example/` | вымышленная демонстрационная семья, на ней же работают тесты |
| `tests/` | тесты `unittest` и браузерные проверки (`smoke.mjs`) |

У движка **нет обязательных зависимостей**, кроме Python 3.10+. Pillow и poppler — по желанию.
Пусть так и остаётся: сервер комментариев должен работать на голом Python на маленьком VPS.

## Проверки

```sh
python3 -m unittest discover tests          # данные, приватность, GEDCOM, переводы, сервер, полная сборка
python3 -m gene_archive.cli build example   # собрать пример
npm install --no-save playwright && npx playwright install chromium webkit
SMOKE_ENGINES=chromium,webkit node tests/smoke.mjs   # все языки, телефон и ноутбук
```

CI запускает всё это на каждый push. Исправили ошибку вёрстки — добавьте на неё проверку в `tests/smoke.mjs`.

## Тексты интерфейса

Исходный язык интерфейса — **русский**. В `app.js` каждая видимая строка обёрнута в `T('…')`;
шаблоны HTML (`index.html`, `help.html`, `discovery.py`) содержат русский текст, который
переводит сборка. Добавляя или меняя строку:

1. напишите её по-русски (`T('Новая строка')` в `app.js`);
2. добавьте тот же ключ в `gene_archive/engine/i18n/en.json` и `ro.json` с переводами;
3. запустите тесты — `Translations.test_every_interface_string_is_translated` упадёт на пропущенном ключе.

Абзац с тегами переводится целиком, теги заменены метками: `"Подробнее в <1>Истории</1>."`
→ `"More in the <1>Story</1>."`.

## Новый язык интерфейса

1. Скопируйте `gene_archive/engine/i18n/en.json` в `<код>.json` и переведите значения.
2. Добавьте язык в `UI_LANGUAGES` в `gene_archive/config.py` (название, локаль, правило
   множественного числа; новое правило — в `plural()` в `app.js`).
3. Добавьте название вкладки в `TREE_TAB` в `tests/smoke.mjs` и язык в `example/site.json`.

## Стиль

- Python: стандартная библиотека, понятный код, комментарии объясняют *зачем*.
- JavaScript: стиль ES5, как в `app.js`, без сборщиков и фреймворков.
- Коммиты: одна тема на коммит, понятное описание.
- Отправляя изменения, вы соглашаетесь распространять их по лицензии MIT.
