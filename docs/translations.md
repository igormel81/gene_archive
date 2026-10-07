# Languages and translations

**[Русская версия](translations.ru.md)**

## Interface

The interface (buttons, headings, help) is translated by the engine. Choose the languages in
`site.json`:

```json
"languages": ["en", "ru", "ro"]
```

The first language is published at the site root, the others in `/ru/`, `/ro/`. A language
menu appears in the header and keeps the open person, document or place when switching.

Available: **English, Russian, Romanian**. Adding a language to the engine is a pull request
with one file — see [CONTRIBUTING](../CONTRIBUTING.md#a-new-interface-language).

## Your texts

Names are never translated. Other texts — notes, document titles and transcriptions, place
descriptions, the story — stay as you wrote them unless you add a translation. Translations
live in your site folder:

```
my-family/translations/en.json
```

```json
{
  "Родился в деревне Красное.": "Born in the village of Krasnoye.",
  "Метрическая книга церкви села Красное, 1895": "Birth register of Krasnoye church, 1895"
}
```

The key is the exact original text (a whole paragraph), the value is its translation.
To get the list of texts without a translation:

```sh
gene translations my-family en > todo-en.json
```

It prints a JSON object with empty values: fill them in and merge into `translations/en.json`.
A paragraph with links or bold text is translated whole, with markers instead of tags:
`"Подробнее в <1>Истории</1>."` → `"More in the <1>Story</1>."` — the markers must stay the same.

Untranslated texts appear in the original language. To make the build fail instead, set
`"strict_translations": true` in `site.json`.

Only texts in Cyrillic are looked up in the dictionaries (the interface source is Russian).
If your content is in English and you publish a Russian edition, the interface becomes Russian
and your texts stay in English.

The engine never sends your texts anywhere. Translate them yourself, with a person you trust,
or with a tool of your choice, and review the result: machine translation confuses kinship
terms and archaic words.
