# AI requests for research in open sources and archives

**[Русская версия](research-prompts.ru.md)**

Ready-made requests for Claude, Codex, ChatGPT, Gemini and other AI assistants: planning the
research, searching databases and archives, checking findings and recording them in
`family_tree.json`. They are written for an agent working in the site folder (see
[filling the site with AI](ai-assistants.md)), but work in a plain chat too — then the agent
returns text and JSON, and you paste them into the files.

The examples use a fictional Patrick Sullivan (I20) from Ballina, County Mayo, Ireland, who
emigrated to Pittsburgh. Archive references and image numbers in the examples are made up. Put in your own people, places and ids. For roots in the Russian Empire
and the USSR see the [Russian version](research-prompts.ru.md), which lists the sources there.

---

## First of all

- **The agent needs internet access.** Claude Code, Codex and ChatGPT can search the web and open
  pages; many databases (FamilySearch, Ancestry) need a login — then the agent works in your browser
  (Claude in Chrome, the built-in browser) or you send it pages and screenshots.
- **Do not give the agent logins or passwords.** Sign in yourself; the agent works in the open tab.
- **Follow the sites' terms.** Do not ask for bulk downloads where they are not allowed; save only the
  images you need.
- **Search for deceased ancestors.** Do not send living relatives' details to search engines or
  people-search sites.
- **Found is not proven.** Every finding is checked (section 4) and goes into the tree only with a
  source; doubtful ones go to leads (`research_leads`).
- **An empty search is a result too.** Ask to record in `research_log` what was searched without
  success: it saves weeks.

Add a short list to your site's `AGENTS.md`: which databases you have checked, where you have
access, which archives you have written to.

---

## 1. Planning

### What we know and what is missing

> Read family_tree.json. For the Sullivan line make a table: person, what is known (dates, places,
> documents), what is missing, which record could give it (civil or church register, census,
> passenger list, naturalization, military, newspaper), where it may be held. Sort by what is easiest
> to find. Do not change the data.

### Every source, not just one

> Make a research plan for Patrick Sullivan's (I20) birth, about 1858, Ballina, County Mayo. Go through
> the whole list: irishgenealogy.ie (civil and church records), the National Library of Ireland Catholic
> parish registers, FamilySearch (index and unindexed images through the catalog), Griffith's Valuation,
> the 1901/1911 Irish census, US records of his arrival and naturalization. For each source: what exactly
> to look for, which years, which parish, what we are most likely to find. Record the plan in
> research_leads (one lead per source, status open).

### Where the place belonged

> Ballina, County Mayo. Find out from open sources: which civil parish, Catholic parish, barony and
> poor-law union / registration district it belonged to in 1840–1900, which townlands were nearby.
> A link for every statement. Create the place `ballina` in places with then/now and materials.

Without the parish and registration district you will not find the register: records are kept by
parish and district, not by village.

---

## 2. Spelling variants

> Make spelling variants for searching: surname Sullivan (O'Sullivan, Sulivan, Suilleabhain in Irish),
> given name Patrick (Pat, Patk., Padraig, Patricius in Latin registers), wife's maiden name, the
> place (Ballina, Bealach an Átha). Separately — how an indexer could have misread them (abbreviations,
> Latin forms, old letter shapes). One variant per line.

> Find all earlier names and spellings of Kapušany (Slovakia): Hungarian, German, Polish, and how US
> immigration records wrote it.

---

## 3. Searching the sources

### FamilySearch: the index

> On FamilySearch (I am signed in, the tab is open) search the index for births/baptisms: Patrick
> Sullivan, 1855–1862, County Mayo. Try the spelling variants and a search by parents only. For each match:
> name, date, place, parents, collection, link to the record and to the image. As a table; do not add
> anything to the archive.

### FamilySearch: unindexed images

> In the FamilySearch catalog find the Catholic registers of Ballina parish for 1850–1865. For each
> film: number, years, contents, whether images are viewable. Open the baptisms for 1858: which image
> starts the year. Record what you found in research_log and add a lead to read the right images.

### Censuses and passenger lists

> Find Patrick Sullivan, born about 1858 in Ireland, in the US censuses 1900–1930 in Pittsburgh
> (FamilySearch, the National Archives), and his arrival: passenger lists of New York 1875–1890
> (Ellis Island / Castle Garden). For each record: household, ages, year of immigration, ship, date,
> link. Compare ages across censuses.

### Military records

> Look for John Sullivan, born 1895 in Pittsburgh, in WWI draft registration cards and service records
> (FamilySearch, the National Archives, Fold3 if I have access). For each: date and place of birth,
> address, next of kin, link. Compare with our I31.

### Newspapers

> Search digitized newspapers (Chronicling America, Trove, the British Newspaper Archive if I have
> access, Google News Archive) for Patrick Sullivan in Pittsburgh 1880–1930: obituaries, marriages,
> court and parish news. For each: newspaper, date, page, quotation, link.

### Archive catalogues

> Find in the catalogues of the National Archives of Ireland and the Pennsylvania State Archives which
> series may hold records of the Sullivans: land, court, naturalization, poor law. For each: reference,
> years, whether it is digitized, how to order a copy. Make a table and leads.

### Place history and pictures

> Find the history of Ballina and old photographs of St Muredach's Cathedral on Wikipedia and Wikimedia
> Commons. Only public-domain or freely licensed images; for each — author, year, licence, link to the
> file page. Download suitable ones to img/places/ and add them to the media of the place `ballina`
> with caption and credit.

### Other people's trees

> Look for Patrick Sullivan (about 1858, Ballina) on WikiTree, Geni, MyHeritage and the FamilySearch
> Family Tree. Other trees are only leads: note who made them, which records they cite and how their
> version differs from ours. Do not copy anything into the tree.

---

## 4. Checking a finding

### Is it the same person?

> Here is a record I found: "…". Compare it with our Patrick Sullivan (I20) in a table: name, year of
> birth (an age in a record ±2 years), place, parents' names, spouse, children, occupation. For each
> feature: matches / does not match / unknown. Conclusion: "it is him" only if at least two independent
> features besides the name match and nothing contradicts; otherwise "possibly" or "no". Explain.

### Index versus original

> This is an index entry, not an image. Find the original image it comes from and check every field.
> Where the index and the image differ, trust the image and note the difference.

### Conflicting dates

> Patrick's records give two years of birth: 1858 (baptism) and 1860 (census). Keep the baptism date as
> the main one, put the other into birth_alternatives with its source, and explain in a note why the
> baptism was preferred.

---

## 5. Recording in the archive

### A record found online

> Add the finding: baptism of Patrick Sullivan, Ballina Catholic parish register, 12 March 1858; National
> Library of Ireland, microfilm 04229/04, page 45 — link. Create a church_record source with url and
> locator, the transcription in scope. If it confirms I20's birth date — status documented with the source,
> the old value in corrections, a line in research_log. Show the changes before saving.

### A negative result

> Record in research_log: searched the 1901 and 1911 Irish census for Sullivans in Ballina townlands,
> variants O'Sullivan, Sulivan — no household matching Patrick's parents; checked 7 October 2026.

### A possible relative without a proven link

> Griffith's Valuation (1856) lists a John Sullivan holding land in Ballina. The link to our I20 is not
> proven. Create a source, a person with research_status unlinked_candidate and a research_note saying why
> it is possible, and a lead with the record that could prove the link.

### A downloaded scan

> I put the scan into sources/ballina-baptisms-1858-p45.jpg. Find the entry for Patrick, transcribe it in
> full (literally, illegible parts as [illegible]), translate the Latin, list who is named: parents,
> sponsors, priest. Create the source and link it to I20.

---

## 6. Requests to archives

> Draft a request to the archive for a certified copy of Patrick Sullivan's baptism, 1858, Ballina parish.
> State what is known (parents, parish, years), ask for a copy and a check of neighbouring years, my
> relationship and the documents that prove it. Polite, short, formal. **Do not send it** — save it to
> requests/ballina-sullivan-1858.md and add a lead "request being prepared".

> The archive answered (text below). Add the confirmed facts with a family_archive_document source (a copy
> of the reply in sources/), update the lead, record in research_log what else could be requested.

---

## 7. Going over the whole archive

### Audit

> Go through family_tree.json and find: people with no document at all; facts marked documented without
> source_ids; dates computed from an age but written as exact; children born when the mother was under 15
> or after her death; namesakes linked only by surname. List them with ids, do not fix anything.

### What is new since last time

> Look at research_log for the last month and research_leads with status open. Which leads are stale,
> which have new sources (database updates, newly digitized collections)? Suggest the five most promising
> next steps.

---

## Cheat sheet

| Task | Start of the request |
|---|---|
| Gaps | "Make a table: what is known, what is missing, which record would give it…" |
| Plan | "Go through the whole list of sources; for each — what to look for…" |
| Place | "Which parish and district did the place belong to in 1840–1900…" |
| Variants | "Make spelling variants of the surname, given name, place…" |
| Database | "Search … for records of …; as a table, add nothing" |
| Check | "Compare feature by feature: matches / does not / unknown…" |
| Record | "Create the source, confirm the fact, corrections, research_log" |
| Nothing found | "Record in research_log: searched …, nothing found" |
| Archive | "Draft a request, do not send it" |
