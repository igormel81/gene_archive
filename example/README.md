# Example: The Harper & Novak family archive

**[Русская версия](README.ru.md)**

A complete demo site for the engine. **Everyone and everything in it is fictional** —
the people, events, records, citations, ships and newspapers were invented for this example,
and the "photos" and "scans" in `sources/` were drawn by a script. Real places (Louisburgh,
Cobh, Ellis Island, Pittsburgh, Kapušany, Hamburg, Chicago, Windber) are used only as a
backdrop; links under `example.org` lead nowhere.

The data is meant to exercise every feature: 46 people over seven generations, a divorce,
an adoption, siblings with unknown parents, probable children and unlinked "possible
relatives", alternative birth and death dates, a hidden document (`S21`), living people
(the root person's family), places with routes on the map, a research journal and a
narrative Story page.

| File | What |
|---|---|
| `site.json` | site settings: title, root and start person, branches, questions, Story timeline |
| `family_tree.json` | people, families, sources, places, research journal |
| `sources/` | document images and a two-page PDF |
| `content/story.html` | the Story page |

Build and view it:

```sh
gene build example
gene serve example
```
