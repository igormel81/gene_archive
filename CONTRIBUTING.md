# Contributing

**[Русская версия](CONTRIBUTING.ru.md)**

Thank you for helping! Bug reports with a small example (`family_tree.json` fragment, the
command, what you expected) are as welcome as pull requests. Never attach real data about
living people to an issue.

## Layout

| Path | What |
|---|---|
| `gene_archive/cli.py` | the `gene` command |
| `gene_archive/build.py` | the build: data → privacy → files and previews → `data.json` → pages → languages |
| `gene_archive/validate.py` | checks of `family_tree.json` and `site.json` |
| `gene_archive/privacy.py` | living people and hidden documents |
| `gene_archive/discovery.py` | static pages for search engines, sitemap |
| `gene_archive/localize.py` | language editions |
| `gene_archive/ged_import.py`, `ged_export.py` | GEDCOM |
| `gene_archive/server.py` | the comments server (standard library only) |
| `gene_archive/engine/web/` | the browser app: `index.html` template, `app.js`, `app.css`, Leaflet |
| `gene_archive/engine/i18n/` | interface dictionaries |
| `example/` | the fictional demo family, also used by the tests |
| `tests/` | `unittest` tests and browser checks (`smoke.mjs`) |

The engine has **no runtime dependencies** besides Python 3.10+. Pillow and poppler are optional.
Keep it that way: the comments server must run on a bare Python on a small VPS.

## Running the checks

```sh
python3 -m unittest discover tests          # data, privacy, GEDCOM, translations, server, a full build
python3 -m gene_archive.cli build example   # build the demo
npm install --no-save playwright && npx playwright install chromium webkit
SMOKE_ENGINES=chromium,webkit node tests/smoke.mjs   # every language, phone and laptop
```

CI runs all of this on every push. Fixed a display bug? Add a check for it to `tests/smoke.mjs`.

## Interface texts

The interface source language is **Russian**. In `app.js` every visible string is wrapped
in `T('…')`; HTML templates (`index.html`, `help.html`, `discovery.py`) contain Russian text
that the build translates. When you add or change a string:

1. write it in Russian (`T('Новая строка')` in `app.js`);
2. add the same key to `gene_archive/engine/i18n/en.json` and `ro.json` with translations;
3. run the tests — `Translations.test_every_interface_string_is_translated` fails on a missing key.

A paragraph with tags is translated whole, tags replaced by markers: `"Подробнее в <1>Истории</1>."`
→ `"More in the <1>Story</1>."`.

## A new interface language

1. Copy `gene_archive/engine/i18n/en.json` to `<code>.json` and translate the values.
2. Add the language to `UI_LANGUAGES` in `gene_archive/config.py` (name, locale, plural rule;
   a new plural rule goes into `plural()` in `app.js`).
3. Add the tab name to `TREE_TAB` in `tests/smoke.mjs` and the language to `example/site.json`.

## Style

- Python: standard library, readable code, comments explain *why*.
- JavaScript: the existing ES5 style of `app.js`, no build step, no frameworks.
- Commits: one topic each, a clear message.
- By contributing you agree that your contribution is released under the MIT license.
