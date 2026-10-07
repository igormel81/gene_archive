# Family archive — rules for AI agents (Claude Code, Codex and others)

This site is built with [gene-archive](https://github.com/igormel81/gene_archive).
You help keep a family archive: add findings, transcribe documents, write life stories,
translate. The owner of the archive reviews every change.

## Where things are

| Path | What |
|---|---|
| `family_tree.json` | **the single source of data**: people, families, documents, places, leads, logs |
| `site.json` | site settings: title, languages, branches, questions to relatives, story timeline |
| `sources/` | scans and photos; file names in latin letters, meaningful: `smith-john-birth-1895.jpg` |
| `content/story.html`, `bios.html`, `news.html` | story, biographies, news (HTML fragments) |
| `translations/<lang>.json` | translations of texts: `{"original text": "translation"}` |
| `_site/` | the built site — never edit it by hand, it is rebuilt |

Data format: https://github.com/igormel81/gene_archive/blob/main/docs/data-format.md
Requests for searching databases and archives: https://github.com/igormel81/gene_archive/blob/main/docs/research-prompts.md
Schema for checks and hints: https://raw.githubusercontent.com/igormel81/gene_archive/main/schemas/family_tree.schema.json

## How to work

1. Before editing, check `git status`: the folder may contain someone else's uncommitted changes.
2. A new id is the next after the maximum (`I`, `F`, `S`, `L`); ids are never reused:
   `python3 -c "import json;d=json.load(open('family_tree.json'));[print(k,max([int(x['id'][1:]) for x in d[k]]+[0])+1) for k in ('people','families','sources','research_leads')]"`
3. After editing: `gene validate` (0 errors), then `gene build`. The site does not build with data errors.
4. Show what changed (`git diff --stat` and a few words) and commit one topic per commit if the owner
   asked you to commit.
5. Write JSON with indent 2 and `ensure_ascii=False`, without reordering existing records.

## Rules of evidence

- **Never invent.** Every fact comes from a document, a relative's account, or is clearly marked as a guess.
- A shared surname is not a relationship until proven by at least two independent matches
  (place, years, parents' names, godparents). A patronymic tells only the father's first name:
  do not create a father from it.
- Doubtful things go to `research_leads`, or get `research_status: "unlinked_candidate"`,
  `probable_children` and the word "probably" in the text — never into established facts.
- Every event has a `status`: `documented`, `family_report`, `uncertain_family_report`,
  `calculated_from_age`, `gravestone`, `publication`, `probable`. A date computed from an age is `CAL 1881`.
- When sources disagree, keep both versions (`birth_alternatives`) with their sources.
- Every change of a fact → an entry in `corrections` (`person_id`, `field`, `previous`, `current`,
  `reason`, `source_ids`) and a line in `research_log` (`date`, `action`, `result`, `scope`).
  Record empty searches in `research_log` too: it saves time next time.

## Documents and photos

- File → `sources/`, a record `S###` with `title`, `kind`, `file`, `locator` (archive, fonds, series,
  file, page — or "family papers, kept by …") and `scope` — the transcription and what it proves.
- Transcribe literally, keeping the original spelling; illegible — `[illegible]`, a guess — `[?]`.
  Never fill in what you cannot see.
- The back of a photo — the `back` field; its inscription goes into `scope`: "Inscription on the back: «…»".
- Put photo files the way they are viewed (not sideways): the site shows the file as is.
- A document the family asked to remove gets `"hidden": true` (keep the record and the file).

## Life stories (`notes`)

- A connected story of the life in order, not a work log ("Patronymic reported on 25 Sept" — no).
- Every fact from a document cites it `(S27)`; family knowledge is marked "according to his daughter".
- Doubts in a separate paragraph: "What is not confirmed…".
- Short plain sentences. Dates in words: "25 September 1926".
- Do not repeat what the card already shows: parents, spouses, children, dates.
- When deleting text, make sure no `S##` reference is lost.

## Privacy

- The site itself shows only the names of living people. Do not put dates, addresses and life details
  of living relatives into other people's stories without their consent.
- Do not send archive data to outside services (translators, people-search sites) unless the owner asks.
- Letters to archives and relatives only with the owner's explicit permission.
