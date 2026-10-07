# Story, biographies and news: `content/`

**[Русская версия](content.ru.md)**

Optional pages with your own texts. They are HTML **fragments** — no `<html>`, `<head>` or
`<body>`: the engine adds the header, styles and translations.

| File | Where it appears |
|---|---|
| `content/story.html` | the **Story** tab (and a static `history.html` for search engines) |
| `content/bios.html` | **People → Biographies** and a "Biography" button in the cards |
| `content/news.html` | the **What's new** tab |

Images and documents used in these pages go into `sources/` or `img/` of the site folder;
the build copies everything they refer to and fails if a file is missing.

## Links inside the texts

- A person: `<a class="pl" data-p="I12">Josef</a>` — opens the person's card (and in the
  static version, the person's page).
- A place: `<a class="place-link" href="#/places?place=pittsburgh">Pittsburgh</a>`.
- A document: write its number in the text — `(S7)` or `S7, S9`; in biographies they become
  footnotes, in the story — buttons.

## `story.html`

```html
<p class="lead">One paragraph that opens the story.</p>

<div id="story-nav"></div>          <!-- where the timeline and place filter go; optional -->

<section id="s-famine">
  <h3><span class="yr">1847</span> The famine years in Mayo</h3>
  <p>The oldest Harper we can name is <a class="pl" data-p="I1">Patrick Harper</a>… (S16)</p>
  <figure class="sfig photo">
    <img src="sources/harper-wedding-1884.jpg" alt="Wedding photograph, 1884">
    <figcaption>Michael and Catherine, 1884 (S3)</figcaption>
  </figure>
</section>
```

- Each chapter is a `<section id="…">` with an `<h3>`; the ids are used by `story.timeline`
  and `story.branch_tags` in [site.json](configuration.md#the-story-page).
- `<span class="yr">` in a heading shows the year above it.
- Consecutive `<figure class="sfig photo">` become a gallery; a click opens the photo full size.

## `bios.html`

```html
<article class="bio" id="bio-I12">
  <h2>Josef Novak (1866–1931)</h2>
  <p class="lead">From a Carpathian village to the coal town of Windber.</p>
  <figure class="sfig photo portrait"><img src="sources/novak-family-windber-1906.jpg" alt=""></figure>
  <p>Text with documents in brackets (S6, S9)…</p>
</article>
```

The id must be `bio-` + the person's id; the person gets a "Biography" button.

## `news.html`

Any HTML: headings, paragraphs, lists. Newest news on top is a good habit.
