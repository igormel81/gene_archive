# Settings: `site.json`

**[Русская версия](configuration.ru.md)**

`site.json` lives next to `family_tree.json`. Every key is optional except `title`;
an unknown key is an error, so typos do not go unnoticed. With the `"$schema"` line (added by `gene init`) your editor suggests the keys and their meaning. A complete example:
[`example/site.json`](../example/site.json).

```json
{
  "title": "The Harper & Novak family archive",
  "short_title": "Harper & Novak",
  "description": "Records, photographs and stories of two families who met in Pittsburgh.",
  "base_url": "https://example.org/family/",
  "languages": ["en", "ru"],
  "root_person": "I35",
  "start_person": "I22",
  "quick_focus": [{"label": "Michael, the emigrant", "person": "I3"}],
  "branches": [{"id": "harper", "title": "Harpers", "focus": "I3", "about": "County Mayo → Pittsburgh"}],
  "questions": [{"person": "I12", "text": "Where is Josef buried?"}],
  "story": {
    "timeline": [["1847", "The famine years", "s-famine"]],
    "places": [["Pittsburgh", "Pittsburgh|Allegheny"]],
    "branch_tags": {"s-famine": ["harper"]},
    "branch_names": {"harper": "Harpers"},
    "branch_colors": {"harper": "#2f6f8f"}
  },
  "surname_variants": {"Novák": "Novak"},
  "privacy": {"hide_living": true, "living_years": 100},
  "comments": false,
  "contact": {"email": "family@example.org", "label": "Write to us"},
  "links": [{"label": "Our photo album", "href": "https://example.org/album"}],
  "head_html": "",
  "strict_translations": false,
  "min_surname_page": 3,
  "gedcom_version": "5.5.1"
}
```

| Key | Default | Meaning |
|---|---|---|
| `title` | "Family archive" | site name: browser tab, search results, the tree image |
| `short_title` | = `title` | the name in the header |
| `description` | "" | one sentence for search engines and link previews |
| `base_url` | "" | the public address, ending with `/`. Enables `sitemap.xml`, `robots.txt`, canonical links and language alternates. `gene build --base-url` overrides it |
| `languages` | `["en"]` | interface languages: `en`, `ru`, `ro`. The first is published at the site root, the others in `/ru/`, `/ro/`… |
| `content_language` | first language | the language your texts are written in |
| `root_person` | `root_person_id` of the data | the person the archive is "about": relations are counted from them, privacy generations too |
| `start_person` | root person | who stands in the middle when the tree opens (often a grandparent, so more of the tree is visible) |
| `quick_focus` | `[]` | buttons above the tree that put a person in the centre |
| `branches` | `[]` | family branches: `id`, `title`, `focus` (person), `about` |
| `questions` | `[]` | questions to relatives, each tied to a person; answers appear in that person's card |
| `story` | `{}` | the Story page: see below |
| `surname_variants` | `{}` | spellings merged into one surname on surname pages and in the tree side panel |
| `privacy.hide_living` | `true` | hide living people (see [data format → Privacy](data-format.md#privacy)) |
| `privacy.living_years` | `100` | people born within this many years, without a death record, count as living |
| `comments` | `false` | `true` when the site runs with the comments server (`gene serve`, Docker). On static hosting leave it `false`: comment forms are hidden |
| `contact` | none | `email` and `label` of the envelope button in the header |
| `links` | `[]` | extra items in the "More" menu |
| `head_html` | "" | extra HTML added to `<head>` of every page: analytics, verification tags |
| `strict_translations` | `false` | fail the build when one of your texts has no translation (see [translations](translations.md)) |
| `min_surname_page` | `3` | surname pages are made for surnames with at least this many people |
| `gedcom_version` | `"5.5.1"` | version of `family_tree.ged` offered on the Archive page: `"5.5.1"` (read by MyHeritage, Ancestry, Geni, Gramps and most programs) or `"7.0"` |

## The Story page

`content/story.html` is your narrative ([content pages](content.md)). The `story` key adds
navigation to it:

- `timeline` — `[year label, short text, section id]`: the "By date" rail; a click scrolls
  to the section.
- `places` — `[label, regular expression]`: the "By place" filter. Paragraphs whose text
  matches the expression are highlighted. The build marks them in the original language,
  so the filter keeps working in translated editions.
- `branch_tags` — `{section id: [branch ids]}`: coloured tags under the section heading.
- `branch_names`, `branch_colors` — labels and colours of those tags.
