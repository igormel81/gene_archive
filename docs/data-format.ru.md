# Формат данных: `family_tree.json`

**[English version](data-format.md)**

Сайт — это одна папка: `site.json` (настройки, см. [configuration.ru.md](configuration.ru.md)),
`family_tree.json` (данные, о которых здесь речь), `sources/` (сканы и фотографии) и
необязательные страницы в `content/`. `gene validate` проверяет всё описанное ниже;
при ошибках `gene build` сайт не собирает.

**Подсказки в редакторе.** `gene init` ставит в начало `family_tree.json` и `site.json` строку
`"$schema"`. Тогда VS Code, Cursor, редакторы JetBrains и другие подсказывают названия полей,
показывают описания и подчёркивают ошибки прямо при вводе — неизвестный `sex`, дату вида «до войны».
Схемы лежат в [`schemas/`](../schemas/); в старый файл строку можно добавить самому:

```json
{"$schema": "https://raw.githubusercontent.com/igormel81/gene_archive/main/schemas/family_tree.schema.json", …}
```

Все текстовые поля — обычный текст на языке ваших материалов. Номера вида `S12` в любом
тексте (`notes`, `scope`, описания мест…) становятся ссылками на документ.

## Верхний уровень

```json
{
  "schema_version": "1.0",
  "root_person_id": "I1",
  "people": [], "families": [], "sources": [],
  "places": [], "place_groups": [], "place_routes": [],
  "research_leads": [], "corrections": [], "research_log": [],
  "surnames": {}
}
```

Обязательны только `root_person_id`, `people`, `families` и `sources`.

## Номера

| Запись | Вид | Пример |
|---|---|---|
| человек | `I` + цифры | `I1`, `I058` |
| семья | `F` + цифры | `F7` |
| источник (документ, снимок) | `S` + цифры | `S12` |
| наводка | `L` + цифры | `L3` |
| место | `slug`: строчная латиница, цифры, `-` | `krasnoye`, `moskva` |

Номера не используются повторно: после удаления человека остаётся пропуск.

## Даты

ISO (`1899`, `1899-10`, `1899-10-09`) или формы GEDCOM:
`ABT 1899` (около), `BEF 1950` (до), `AFT 12 NOV 1950` (после), `EST 1880` (оценка),
`CAL 1881` (вычислено), `BET 1900 AND 1905` (между), `FROM 1900 TO 1910`, `9 OCT 1899`.
Всё остальное («до войны») — ошибка: такие слова пишите в `note`.

Даты из документов Российской империи до 1918 года записывайте как в документе (по старому
стилю) и отмечайте это в `note`.

## Человек — `people[]`

```json
{
  "id": "I4",
  "given_names": "Иван Сергеевич",
  "surname": "Иванов",
  "display_name": "Иванов Иван Сергеевич",
  "sex": "M",
  "relation": "дедушка",
  "placeholder": false,
  "aliases": ["Иоанн Сергеев"],
  "identity_source_ids": ["S1", "S4"],
  "birth": {"date": "1895-06-10", "place_as_recorded": "с. Красное Рязанской губ.",
            "place_slugs": ["krasnoye"], "status": "documented", "source_ids": ["S4"],
            "note": "Метрическая книга, запись № 42"},
  "death": {"date": "1958-01-10", "status": "gravestone", "source_ids": ["S9"]},
  "burial": {"place_as_recorded": "кладбище с. Красное"},
  "residences": [{"place": "Рязань, заводской посёлок", "date": "1947–1952",
                  "place_slugs": ["ryazan"], "place_event_kind": "residence", "source_ids": ["S5"]}],
  "notes": ["Связный рассказ о жизни, абзац за абзацем. Упоминания S4 становятся кнопками."],
  "profiles": [{"site": "Geni", "url": "https://…", "match": "вероятно"}],
  "living": false
}
```

| Поле | Обязательно | Что значит |
|---|---|---|
| `id`, `given_names`, `surname`, `display_name`, `sex`, `notes` | да | `sex`: `M`, `F` или `U` |
| `relation` | нет | кем приходится главному человеку, показывается в карточке (принимается и старое имя `relation_to_igor`) |
| `placeholder` | нет | `true` для заглушек вроде «неизвестный ребёнок» |
| `aliases` | нет | другие написания, девичьи фамилии — по ним работает поиск |
| `identity_source_ids` | нет | документы, по которым установлено, кто этот человек |
| `birth`, `death`, `burial` | нет | события, см. ниже |
| `birth_alternatives`, `death_alternatives` | нет | расходящиеся версии одного события |
| `residences` | нет | где жил и что где происходило; `date` здесь — свободный текст |
| `research_status` | нет | `unlinked_candidate` — «возможная родня», рисуется пунктиром |
| `research_note` | нет | почему связь под вопросом |
| `living` | нет | `true`/`false` вместо автоматического правила о живых (см. «Приватность») |

**Событие** (`birth`, `death`, `burial`, `marriage`): `date`, `place_as_recorded` (как написано
в источнике), `place_slugs` (ссылки на `places`), `status`, `source_ids`, `note`.
`status` — откуда известно: `documented` (документ), `family_report` (рассказ семьи),
`uncertain_family_report` (неуверенный рассказ), `calculated_from_age` (вычислено по возрасту),
`gravestone` (надгробие), `publication` (публикация), `probable` (вероятно).

## Семья — `families[]`

```json
{"id": "F4", "partners": ["I9", "I10"], "children": ["I4", "I6"],
 "adopted_children": [], "probable_children": ["I11"], "probable_note": "Назван только в ревизии 1858 г.",
 "relation": "spouses", "marriage": {"date": "1920", "source_ids": ["S25"]},
 "source_ids": ["S1"], "notes": ["…"]}
```

- `partners`: 0–2 человека. Братья и сёстры с неизвестными родителями — семья с пустым `partners`.
- `relation`: `spouses` (супруги), `divorced` (развелись), `siblings` (братья и сёстры) или пусто (не в браке).
- `probable_children`: дети, связь которых с этими родителями не доказана; рисуются пунктиром.

Родным ребёнком (`children`) человек может быть только в одной семье с родителями.

## Источник — `sources[]`

```json
{"id": "S4", "title": "Метрическая книга церкви с. Красное, 1895", "kind": "church_record",
 "file": "sources/krasnoye-1895-l12.jpg", "back": "sources/krasnoye-1895-l12-back.jpg",
 "locator": "Областной госархив, ф. 1, оп. 2, д. 3, л. 12",
 "scope": "Расшифровка и что этот документ доказывает.", "preview_page": 2, "hidden": false}
```

- `file` (файл в `sources/`) или `url` (запись в интернете). Для устных рассказов может не быть ни того, ни другого.
- `back`: оборот снимка; в просмотре появится кнопка «Оборот». Надпись на обороте — в `scope`.
- `preview_page`: какая страница PDF идёт на превью.
- `hidden: true`: семья попросила убрать. Запись остаётся в вашем JSON, но не попадает ни на сайт,
  ни в GEDCOM, а ссылки на неё вычищаются при сборке.
- `kind` — группа в фильтре архива:

  | Группа | Значения `kind` |
  |---|---|
  | Документы | `civil_record_copy`, `church_record`, `family_archive_document`, `education_record`, `revision_list`, `census_record`, `immigration_record`, `digitized_archive_original`, `digitized_archive_case` |
  | Военные | `online_military_record`, `military_record_copy` |
  | Фотографии | `family_photo` |
  | Рукописи | `family_manuscript`, `letter` |
  | Газеты и публикации | `newspaper`, `publication`, `published_reference`, `published_diary` |
  | Надгробия и памятники | `gravestone`, `gravestone_image`, `memorial_image` |
  | Рассказы семьи | `family_report`, `family_testimony` |
  | Справочники и базы | `online_reference`, `online_archive_index`, `online_archive_catalog`, `archive_database` |
  | Находки для проверки | `research_scan` |

  Остальные значения попадают в «Прочее».

## Места — `places[]`, `place_groups[]`, `place_routes[]`

```json
{"slug": "krasnoye", "name": "Красное", "where": "Рязанская губ., Пронский уезд",
 "lat": 53.90, "lon": 40.10, "geo_note": "точка храма", "period": "1894–1902",
 "then": "Пронский уезд", "now": "Рязанская область",
 "aliases": ["красное", "красное село"], "groups": ["paternal"], "sort_year": 1894,
 "text": "Короткое описание для карты.", "details": ["Подробная история, абзацами."],
 "people": ["I12"], "sources": ["S5"],
 "timeline": [{"date": "1894", "text": "Венчание Петра и Анны", "people": ["I14"], "sources": ["S6"]}],
 "materials": [{"label": "Путеводитель областного архива", "url": "https://…"}],
 "media": [{"file": "img/places/krasnoye-church.jpg", "caption": "…", "credit": "Общественное достояние", "credit_url": "https://…"}]}
```

`place_groups`: `{"id", "name", "color", "about"}` — ветви семьи на карте.
`place_routes`: `{"group", "from_place", "to_place", "label", "sources"}` — переезды, рисуются линиями.

## Журнал исследования

- `research_leads[]` — открытые вопросы и наводки: `{"id": "L3", "title", "status", "record",
  "person_id", "source_ids", "limitations", "url", "resolution"}`.
  `status`: `open`, `to_verify`, `accepted`, `closed`, `superseded`, `candidate_unlinked`…
- `corrections[]` — каждое изменение факта: `{"person_id" | "family_id" | "record", "field",
  "previous", "current", "reason", "source_ids"}`. На сайте — «Журнал исправлений».
- `research_log[]` — что, где и с каким результатом искали: `{"date": "2026-10-06",
  "action", "result", "scope"}`.
- `surnames{}` — `{"Иванов": {"history": ["абзац", …]}}`: история рода на странице фамилии.

## Приватность

Человек считается **живым**, если нет записи о смерти (даже без даты) и о погребении, а родился
он за последние 100 лет (`privacy.living_years` в `site.json`) — или, если даты рождения нет,
принадлежит поколению родителей главного человека и младше. Старшие поколения без дат
остаются открытыми.

О живых на сайте, в его `data.json` и в выгрузке GEDCOM остаются только имя, пол и родство:
ни дат, ни мест, ни заметок, ни других имён, ни профилей, ни документов. Брак, в котором хотя бы
один из супругов жив, тоже скрыт, а документ, на который ссылаются только живые, не публикуется
вовсе. Их страницы не показываются поисковикам.

Поставьте человеку `"living": false`, чтобы всё же опубликовать сведения (с его согласия), или
`"living": true`, чтобы скрыть того, кого правило пропустило.
