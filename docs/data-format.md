# Data format: `family_tree.json`

**[Русская версия](data-format.ru.md)**

A site is one folder with `site.json` (settings, see [configuration.md](configuration.md)),
`family_tree.json` (the data described here), `sources/` (scans and photos) and optional
`content/` pages. `gene validate` checks everything below; `gene build` refuses to build
when there are errors.

**Hints in your editor.** `gene init` puts a `"$schema"` line at the top of `family_tree.json`
and `site.json`. VS Code, Cursor, JetBrains editors and others then suggest field names, show
descriptions and underline mistakes as you type — an unknown `sex`, a date like "before the war".
The schemas are in [`schemas/`](../schemas/); for an older file add the line yourself:

```json
{"$schema": "https://raw.githubusercontent.com/igormel81/gene_archive/main/schemas/family_tree.schema.json", …}
```

All text fields are plain text in the language of your content. Numbers like `S12` inside
any text (`notes`, `scope`, place texts…) become clickable links to that document.

## Top level

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

Only `root_person_id`, `people`, `families` and `sources` are required.

## IDs

| Record | Format | Example |
|---|---|---|
| person | `I` + digits | `I1`, `I058` |
| family | `F` + digits | `F7` |
| source (document, photo) | `S` + digits | `S12` |
| research lead | `L` + digits | `L3` |
| place | `slug`: lowercase latin, digits, `-` | `krasnoye`, `new-york` |

IDs are never reused: deleting a person leaves a gap.

## Dates

ISO (`1899`, `1899-10`, `1899-10-09`) or GEDCOM phrases:
`ABT 1899`, `BEF 1950`, `AFT 12 NOV 1950`, `EST 1880`, `CAL 1881`,
`BET 1900 AND 1905`, `FROM 1900 TO 1910`, `9 OCT 1899`.
Anything else (`"before the war"`) is an error: put such wording in `note`.

## Person — `people[]`

```json
{
  "id": "I4",
  "given_names": "Ivan Sergeevich",
  "surname": "Ivanov",
  "display_name": "Ivanov Ivan Sergeevich",
  "sex": "M",
  "relation": "grandfather",
  "placeholder": false,
  "aliases": ["Ioann Sergeev"],
  "identity_source_ids": ["S1", "S4"],
  "birth": {"date": "1895-06-10", "place_as_recorded": "Krasnoye, Ryazan gov.",
            "place_slugs": ["krasnoye"], "status": "documented", "source_ids": ["S4"],
            "note": "Birth register, entry 42"},
  "death": {"date": "1958-01-10", "status": "gravestone", "source_ids": ["S9"]},
  "burial": {"place_as_recorded": "Krasnoye cemetery"},
  "residences": [{"place": "Ryazan, factory housing", "date": "1947–1952",
                  "place_slugs": ["ryazan"], "place_event_kind": "residence", "source_ids": ["S5"]}],
  "notes": ["A connected story of the life, paragraph by paragraph. Mentions S4 become buttons."],
  "profiles": [{"site": "Geni", "url": "https://…", "match": "probable"}],
  "living": false
}
```

| Field | Required | Meaning |
|---|---|---|
| `id`, `given_names`, `surname`, `display_name`, `sex`, `notes` | yes | `sex`: `M`, `F` or `U` |
| `relation` | no | relation to the root person, shown on the card (`relation_to_igor` is accepted as an old name) |
| `placeholder` | no | `true` for "unknown child" style placeholders |
| `aliases` | no | other spellings, maiden names — used by search |
| `identity_source_ids` | no | documents that prove who this person is |
| `birth`, `death`, `burial` | no | events, see below |
| `birth_alternatives`, `death_alternatives` | no | conflicting versions of the same event |
| `residences` | no | where the person lived or what happened where; `date` here is free text |
| `research_status` | no | `unlinked_candidate` = "possibly a relative", drawn dashed |
| `research_note` | no | why the link is uncertain |
| `living` | no | `true`/`false` overrides the automatic living-person rule (see Privacy) |

**Event** (`birth`, `death`, `burial`, `marriage`): `date`, `place_as_recorded` (as written in the source),
`place_slugs` (links to `places`), `status`, `source_ids`, `note`.
`status` says how we know: `documented`, `family_report`, `uncertain_family_report`,
`calculated_from_age`, `gravestone`, `publication`, `probable`.

## Family — `families[]`

```json
{"id": "F4", "partners": ["I9", "I10"], "children": ["I4", "I6"],
 "adopted_children": [], "probable_children": ["I11"], "probable_note": "Named in the 1858 census only",
 "relation": "spouses", "marriage": {"date": "1920", "source_ids": ["S25"]},
 "source_ids": ["S1"], "notes": ["…"]}
```

- `partners`: 0–2 people. Siblings with unknown parents: a family with empty `partners`.
- `relation`: `spouses`, `divorced`, `siblings` or empty (unmarried partners).
- `probable_children`: children whose link to these parents is not proven; they are drawn dashed.

A person is the biological child (`children`) of at most one family with partners.

## Source — `sources[]`

```json
{"id": "S4", "title": "Birth register of Krasnoye church, 1895", "kind": "church_record",
 "file": "sources/krasnoye-1895-p12.jpg", "back": "sources/krasnoye-1895-p12-back.jpg",
 "locator": "Regional state archive, f. 1, op. 2, d. 3, l. 12",
 "scope": "Transcription and what this document proves.", "preview_page": 2, "hidden": false}
```

- `file` (a file in `sources/`) or `url` (online record). Both may be absent for oral reports.
- `back`: the back side of a photo; the viewer shows a "Back" button.
- `preview_page`: which page of a PDF to use as the thumbnail.
- `hidden: true`: the family asked to remove it. The record stays in your JSON but never
  reaches the site or GEDCOM, and links to it are removed during the build.
- `kind` groups documents in the Archive filter:

  | Group | `kind` values |
  |---|---|
  | Documents | `civil_record_copy`, `church_record`, `family_archive_document`, `education_record`, `revision_list`, `census_record`, `immigration_record`, `digitized_archive_original`, `digitized_archive_case` |
  | Military | `online_military_record`, `military_record_copy` |
  | Photographs | `family_photo` |
  | Manuscripts | `family_manuscript`, `letter` |
  | Newspapers and publications | `newspaper`, `publication`, `published_reference`, `published_diary` |
  | Gravestones | `gravestone`, `gravestone_image`, `memorial_image` |
  | Family stories | `family_report`, `family_testimony` |
  | Directories and databases | `online_reference`, `online_archive_index`, `online_archive_catalog`, `archive_database` |
  | Findings to check | `research_scan` |

  Any other value is shown as "Other".

## Places — `places[]`, `place_groups[]`, `place_routes[]`

```json
{"slug": "krasnoye", "name": "Krasnoye", "where": "Ryazan gov., Pronsk district",
 "lat": 53.90, "lon": 40.10, "geo_note": "church location", "period": "1894–1902",
 "then": "Pronsk district", "now": "Ryazan region",
 "aliases": ["krasnoye", "krasnoe"], "groups": ["paternal"], "sort_year": 1894,
 "text": "Short description shown on the map.", "details": ["Longer history, paragraph by paragraph."],
 "people": ["I12"], "sources": ["S5"],
 "timeline": [{"date": "1894", "text": "Wedding of Pyotr and Anna", "people": ["I14"], "sources": ["S6"]}],
 "materials": [{"label": "Regional archive guide", "url": "https://…"}],
 "media": [{"file": "img/places/krasnoye-church.jpg", "caption": "…", "credit": "Public domain", "credit_url": "https://…"}]}
```

`place_groups`: `{"id", "name", "color", "about"}` — branches of the family on the map.
`place_routes`: `{"group", "from_place", "to_place", "label", "sources"}` — moves drawn as arrows.

## Research journal

- `research_leads[]` — open questions and hints: `{"id": "L3", "title", "status", "record",
  "person_id", "source_ids", "limitations", "url", "resolution"}`.
  `status`: `open`, `to_verify`, `accepted`, `closed`, `superseded`, `candidate_unlinked`…
- `corrections[]` — every change of a fact: `{"person_id" | "family_id" | "record", "field",
  "previous", "current", "reason", "source_ids", "date", "author"}`. Shown on the site as the corrections log;
  the [online editor](editor.md) writes these lines itself (`date` and `author` are optional).
- `research_log[]` — what was searched, where, with what result: `{"date": "2026-10-06",
  "action", "result", "scope"}`.
- `surnames{}` — `{"Ivanov": {"history": ["paragraph", …]}}`: stories shown on surname pages.

## Privacy

A person is treated as **living** when there is no death record (even one without a date) and
no burial, and they were born within the last 100 years (`privacy.living_years` in
`site.json`) — or, with no birth date, they belong to the generation of the root person's
parents or younger. Older generations without dates stay public.

For living people the published site, its `data.json` and the GEDCOM export keep only the
name, sex and relation: no dates, places, notes, aliases, profiles or documents. The marriage
of a couple where either partner is living is hidden too, and a document that only living
people refer to is not published at all. Their pages are hidden from search engines.

Set `"living": false` on a person to publish them anyway (with their consent), or
`"living": true` to hide someone the rule missed.
