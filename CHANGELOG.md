# Changelog / История изменений

## Unreleased

- Estimated birth dates: under names `BET 1917 AND 1944` reads "1917…1944" and `ABT`/`EST`/`CAL` "c. 1883" instead of
  an exact year; a new date status `estimated` that needs a `note` saying how; `gene hints` suggests an estimate for
  people without a birth date (`estimate_birth`: eldest child −27, spouse or siblings ±8, parents +18…+45), never
  for people who would be born after 1935.
  Оценочные даты рождения: под именами `BET 1917 AND 1944` — «1917…1944», `ABT`/`EST`/`CAL` — «ок. 1883», а не точный
  год; новый статус даты `estimated`, к которому нужно пояснение в `note`; `gene hints` предлагает оценку людям без
  даты рождения (`estimate_birth`: старший ребёнок −27, супруг или братья и сёстры ±8, родители +18…+45), но не тем,
  кто по расчёту родился позже 1935 года.

- Person card: the note of a birth, death or burial (`note`: cause of death, Old/New Style, how to find the grave)
  is shown under the date; a Burial row; a death without a date is shown when its place or note is known;
  deaths from other documents (`death_alternatives`) are listed like births.
  Карточка человека: пояснение к рождению, смерти или погребению (`note`: причина смерти, стиль календаря, как найти
  могилу) — под датой; строка «Погребение»; смерть без даты видна, если известно место или есть пояснение; смерть
  по другому документу (`death_alternatives`) — как у рождения.

- Translations: a paragraph with links is reported for translation only as a whole, never piece by piece, and
  the text of a link to a person is kept as a name — renaming someone no longer breaks a translated paragraph.
  Titles of people whose name holds a comma («Иванова Анна, жена Петра (~1918)») keep the whole name.
  Переводы: абзац со ссылками просится к переводу только целиком, а не кусками, текст ссылки на человека остаётся
  именем — переименование человека больше не ломает переведённый абзац. В заголовках людей с запятой в имени
  («Иванова Анна, жена Петра (~1918)») имя остаётся целым.

## 0.5.0 — 2026-10-14

- License changed from MIT to GNU AGPL-3.0-or-later. Versions up to 0.4.0 stay available under MIT. Sites built
  with the engine (your data, texts, photos) are not covered by the license.
  Лицензия сменена с MIT на GNU AGPL-3.0-or-later. Версии до 0.4.0 включительно остаются доступны по MIT. Сайты,
  собранные движком (ваши данные, тексты, фото), лицензия не затрагивает.

## 0.4.0 — 2026-10-12

- **Search everything** from the magnifier: people, documents (their transcriptions), places, the Story, leads and
  questions, grouped, with the passage and the words found marked. Word endings, the pre-1918 spelling (ъ, і, ѣ) and
  Latin/Cyrillic letters match each other. Runs in the browser — static hosting works; living people are not in it
  because they are not in the published data. Browser checks added.
  Поиск по всему архиву под лупой: люди, документы (их расшифровки), места, «История», наводки и вопросы — по группам,
  с отрывком и подсвеченными словами. Окончания, дореформенное письмо (ъ, і, ѣ) и латиница/кириллица совпадают.
  Работает в браузере — подходит и статический хостинг; живых в поиске нет, потому что их нет в опубликованных данных.

- `gene apply`: changes from scripts and AI assistants through the same path as the online editor — checks,
  corrections and research logs, a git commit by the author, `--dry-run`, `--build`. The genealogy-mcp server uses it
  to research and write straight into a site folder. New sites' `AGENTS.md` tells assistants to prefer it.
  `gene apply`: правки из скриптов и ИИ-помощников тем же путём, что онлайн-редактор, — проверки, журналы исправлений
  и поисков, коммит от имени автора, `--dry-run`, `--build`. Через него сервер genealogy-mcp ищет и записывает прямо
  в папку сайта. `AGENTS.md` новых сайтов советует помощникам пользоваться им.

## 0.3.0 — 2026-10-12

- Docs: AGENTS.md for new sites, the AI guide, the research guide and the prompts cover `gene hints`,
  `research_resources`, `gene gedcom --for` and working next to the online editor; link previews in deploy.md;
  your own help page in `content/help.html`.
  Документация: AGENTS.md новых сайтов, руководство по ИИ, руководство по поиску и сборник запросов — про
  `gene hints`, `research_resources`, `gene gedcom --for` и работу рядом с онлайн-редактором; превью ссылок в
  deploy; своя справка в `content/help.html`.
- A detailed help page "How to use the site" in English, Russian and Romanian: the tree, a person's card, "How we
  are related", search, comments and proposals, the archive and its tabs, places and the story, signs, sharing,
  phones, living people.
  Подробная справка «Как пользоваться сайтом» на трёх языках: древо, карточка, «Как мы связаны», поиск, комментарии
  и предложения, архив и его вкладки, места и история, значки, «Поделиться», телефон, ныне живущие.
- `gene gedcom --for geni` (Geni, MyHeritage, Ancestry: surname at birth and `_MARNM`, deceased marked with `DEAT Y`,
  one clean note with a link to the site) and `--for public` (open forums: living people as "Living /Surname/").
  New optional field `birth_surname`.
  `gene gedcom --for geni` (Geni, MyHeritage, Ancestry: фамилия при рождении и `_MARNM`, умершие отмечены `DEAT Y`,
  одна заметка без кодов и со ссылкой на сайт) и `--for public` (открытые форумы: живые — «Живущий /Фамилия/»).
  Новое необязательное поле `birth_surname`.
- The "Share" button works: s/<id>.html pages for people, documents, places, biographies and sections, with
  1200×630 covers for link previews in messengers (Pillow and `base_url` needed for the pictures).
  Кнопка «Поделиться» работает: страницы s/<номер>.html для людей, документов, мест, биографий и разделов
  с обложками 1200×630 для превью в мессенджерах (для картинок нужны Pillow и `base_url`).
- Archive → Sources: `research_resources` in family_tree.json — the archives and databases searched, what was found
  in each, with their documents and research-log entries picked up by the build.
  «Архив → Источники»: `research_resources` в family_tree.json — архивы и базы, где искали, что в каждом нашлось;
  документы и записи журнала поиска к ним подбирает сборка.
- A person's card no longer covers the person in the tree: the tree moves into the visible part.
  Карточка человека больше не закрывает его в древе: древо сдвигается в видимую часть.

## 0.2.0 — 2026-10-08

- Online editor at `/edit/` (`gene serve --editor`, `GENE_EDITOR` in Docker): people, families, documents with uploads,
  places; checks before saving, conflict detection, automatic `corrections` and `research_log`, history in git with restore,
  background rebuild. Accounts with roles (`gene users`), invitation links, CSRF protection. See docs/editor.md.
  Онлайн-редактор на `/edit/` (`gene serve --editor`, `GENE_EDITOR` в Docker): люди, семьи, документы с загрузкой файлов,
  места; проверка перед сохранением, защита от одновременных правок, журналы `corrections` и `research_log`, история в git
  с возвратом версий, пересборка сайта. Пользователи с ролями (`gene users`), ссылки-приглашения. См. docs/editor.ru.md.
- "Suggest a correction" on person cards (with the editor); administrators apply proposals in one click.
  «Предложить исправление» в карточке человека (с редактором); администратор применяет предложение одной кнопкой.
- "How we are related" on person cards: the relation between any two people in Russian, English and Romanian
  (second cousin once removed, great-uncle, half-brother, in-laws) with the chain of people between them.
  «Как мы связаны» в карточке человека: кем приходится любому другому (троюродный дядя, двоюродная бабушка,
  единокровный брат, свойственники) и цепочка людей между ними.
- Research hints: `gene hints` and the "Checks" tab of the editor list impossible facts (born after the mother's death,
  a parent aged 11) and gaps (no dates, a date without a document, people not connected to the tree, unused documents).
  Подсказки для поиска: `gene hints` и вкладка «Проверка» в редакторе — невозможные факты (родился после смерти матери,
  родителю 11 лет) и пробелы (нет дат, дата без документа, человек не связан с древом, документ ни к кому не привязан).
- Docker image: git included; the editor needs the site folder mounted writable.
  Docker-образ: добавлен git; для редактора папка сайта монтируется с правом записи.

## 0.1.0 — 2026-10-07

First public release, extracted from the family archive at igoruan.ru/gene.
Первый открытый выпуск, выделенный из семейного архива igoruan.ru/gene.

- Tree, person cards, archive, places map, people (list, calendar, zodiac, surnames), story, questions.
  Древо, карточки, архив, карта мест, люди (список, календарь, гороскоп, фамилии), история, вопросы.
- Interface in English, Russian and Romanian; translation dictionaries for your own texts.
  Интерфейс на английском, русском и румынском; словари для перевода ваших текстов.
- Living people hidden by default; hidden documents; GEDCOM import and export.
  Живые люди скрыты по умолчанию; скрытые документы; импорт и выгрузка GEDCOM.
- `gene` command: init, import, validate, build, serve, comments, translations.
  Команда `gene`: init, import, validate, build, serve, comments, translations.
- Comments server with PIN, moderation and spam protection; Docker image; GitHub Pages template.
  Сервер комментариев с PIN, модерацией и защитой от спама; Docker; шаблон для GitHub Pages.
- Collection of AI requests for research in open sources and archives (docs/research-prompts).
  Сборник запросов к ИИ для поиска в открытых источниках и архивах (docs/research-prompts).
- GEDCOM 5.5.1 export by default (7.0 with `gedcom_version` or `gene gedcom --version 7.0`); `gene gedcom` command.
  Выгрузка GEDCOM 5.5.1 по умолчанию (7.0 — через `gedcom_version` или `gene gedcom --version 7.0`); команда `gene gedcom`.
- JSON Schemas for `family_tree.json` and `site.json`: hints and checks in editors.
  JSON Schema для `family_tree.json` и `site.json`: подсказки и проверка в редакторах.
- Guide on filling the site with Claude Code or Codex; `gene init` and `gene import` write `AGENTS.md` and `CLAUDE.md`.
  Инструкция по наполнению сайта с Claude Code или Codex; `gene init` и `gene import` создают `AGENTS.md` и `CLAUDE.md`.
