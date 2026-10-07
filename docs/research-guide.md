# How to start researching your family history

A practical guide for beginners. It comes from the real family archive this engine
was extracted from: what works, where to look, how to avoid the classic mistakes,
and how to record what you find in `family_tree.json`.

The data format itself is described in [data-format.md](data-format.md). This guide
covers what to do **before** anything goes into the data, and how to write it down.
A Russian version with more detail on Russian Empire and Soviet sources is in
[research-guide.ru.md](research-guide.ru.md).

---

## 0. Before you search

### Start with yourself and work backwards

Start with yourself, your parents and grandparents, and only then go further back.
Each step depends on the previous one: to find your great-grandfather's baptism you
need his name, an approximate year and, above all, the **place**. That usually
comes from your grandparent's documents.

The classic beginner mistake is to start from a famous person with your surname
and try to connect them down to you. That is how beautiful, wrong trees are made.

### Set a goal

- **One line**: your surname line, or your grandmother's family. Faster results,
  easier to keep in your head.
- **All lines**: eight great-grandparents, sixteen great-great-grandparents.
  Slower, but you meet different regions, countries and archives.

A good first goal: "know all 8 great-grandparents by name, with dates and places,
and have at least one document for each".

### What "proven" means

A fact is established when it rests on a **document**, and that document clearly
belongs to **your** person. A family story is a valuable source, but it is a story,
not proof. Every event in the archive has a `status`:

| `status` | Use when |
|---|---|
| `documented` | a record made at the time (register entry, certificate, archive file) |
| `family_report` | this is what relatives say |
| `uncertain_family_report` | a story the relatives themselves are unsure about |
| `calculated_from_age` | date worked out from an age ("aged 32" in an 1897 record) |
| `gravestone` | from a headstone |
| `publication` | from a book, newspaper or directory |
| `probable` | likely, but not proven |

An honest "probably" is better than a confident mistake that dozens of people copy.

---

## 1. Step one — talk to your relatives

### Who to ask first

**The oldest ones.** This is urgency, not politeness: every year takes away what
was never written down. One conversation with an 85-year-old aunt can give more
than a month in archives: great-grandmothers' names, the village, "where we came
from".

Then the cousin branches: they hold different photos and different versions of
the same stories.

### What to ask — a checklist

- **Full names**: given names, middle names, surnames. For women, the **maiden
  name** (and every married name). Nicknames ("Nan", "Aunt Bessie" = Elizabeth).
  For Eastern European families: **patronymics** (Ivanovich = son of Ivan).
- **Dates**: birth, marriage, death. If no exact date: "about", "before the war",
  "when Mum was born".
- **Places**: town, parish, county, country, as they were called then. Where they
  moved later, and why (work, war, emigration, evacuation).
- **Occupations**: what they did, where, for which employer.
- **Military service**: which war, unit, wounds, captivity, missing in action;
  peacetime service.
- **Religion**: where they were baptised, married, buried.
- **Photos**: who is on them, when and where taken. Label them right away.
- **Documents**: who keeps what: certificates, letters, naturalization papers.
- **Family legends**: "we descend from nobility", "the name was changed at Ellis
  Island", "great-grandma was Cherokee". Record them **word for word**, but mark them
  as unverified. There is often a grain of truth, just not where you expect it.

### How to record

- Voice recording on a phone, **only with consent**. Say why and who will see it.
- Note the date, who was speaking, who else was present.
- Do not lead ("he was born in 1902, wasn't he?").
- Ask again a week later; people remember things after the first conversation.

### A story becomes a source

Every conversation becomes a source with `kind: "family_report"`. There may be no
file; then `scope` says who said what, and when:

```json
{"id": "S1", "kind": "family_report",
 "title": "M. Kuznetsova on her mother's family, 2026",
 "locator": "Conversation recorded 2026-03-12, audio kept by the compiler",
 "scope": "Her mother, Anna Petrovna, was born 'around 1902' in the village of Pokrovskoye. Anna's father Pyotr was a carpenter who went to Moscow for seasonal work. Legend: 'the Smirnovs were free smallholders', unverified."}
```

If you have a transcript or audio, put it in `sources/` and reference it in `file`.

---

## 2. Step two — the home archive

### What to look for

- Birth, marriage and death certificates (including later copies).
- Passports, ID cards, naturalization papers, ship tickets, visas.
- Military papers: service records, discharge papers, pay books, medals and their
  citations, telegrams and letters from the war office.
- Work records: employment books (in the USSR, the *trudovaya knizhka*), union
  cards, references, pension papers.
- School and university certificates.
- Letters and postcards (the postmark gives a date and place).
- **Photos with writing on the back**: often a name, date and studio town.
- Family Bibles, address books, funeral cards, newspaper cuttings.
- Property deeds, wills, probate papers.

### How to scan or photograph

- Documents at **300–600 dpi**, photos at **600 dpi** or more; small snapshots even
  higher. No scanner? Photograph in daylight, no flash, straight from above.
- **Both sides.** The back of a photo is a separate file: the `back` field.
- Don't crop away stamps, seals or margins with writing.
- Save the file **the way the picture is meant to be viewed** (not sideways):
  the site shows files as they are.
- Never retouch the original. A restored copy is a separate file, next to it.
- Clear file names, latin letters, no spaces:
  `kuznetsova-anna-birth-cert-1950.jpg`, `photo-1924-wedding-back.jpg`.

### Each document becomes an `S##` record

`scope` holds a **transcription** (verbatim, original spelling) and what the
document proves:

```json
{"id": "S3", "kind": "family_photo",
 "title": "Wedding photo, 1924",
 "file": "sources/photo-1924-wedding.jpg",
 "back": "sources/photo-1924-wedding-back.jpg",
 "scope": "Written on the back: 'To Nyura with love from Vasya. 1924.' Probably the groom's hand."}
```

Papers kept at home: `family_archive_document`; certified copies from a registry:
`civil_record_copy`; photos: `family_photo`.

---

## 3. Step three — free online databases

The main rule: **an index is not a document.** An index entry was typed by a
volunteer or by OCR and can be wrong in names, dates and places. Always open the
**image** of the record when there is one, and cite it.

### Everywhere

| Resource | Good for | Pitfalls |
|---|---|---|
| [FamilySearch](https://www.familysearch.org) (free account) | indexed records worldwide; **unindexed images** via the Catalog (search by place) | huge parts are images only: browse by place in the Catalog, not just by name; some images need sign-in or a FamilySearch center |
| [Internet Archive](https://archive.org) | full-text search of digitized books: county histories, directories, regimental histories, gazetteers | OCR errors; search short phrases and spelling variants |
| [Find a Grave](https://www.findagrave.com), [BillionGraves](https://billiongraves.com) | headstones, burial places | volunteer-created; family links on memorials are often guesses |
| [Commonwealth War Graves Commission](https://www.cwgc.org) | WWI/WWII dead of Commonwealth forces | dead only, not survivors |
| [Arolsen Archives](https://collections.arolsen-archives.org) | Nazi persecution, forced labour, displaced persons (incl. many from the USSR and Poland) | names in German transliteration |

### United States

- [National Archives (NARA)](https://www.archives.gov/research/genealogy): census
  (released after **72 years**: the [1950 census](https://1950census.archives.gov) is
  online), military, immigration and naturalization records.
- Passenger lists: [Statue of Liberty – Ellis Island Foundation](https://heritage.statueofliberty.org).
  Names were **not** changed on Ellis Island; changes usually came later, by the
  family itself. Check naturalization papers.
- Newspapers: [Chronicling America](https://chroniclingamerica.loc.gov) (Library of Congress).
- Vital records (birth, marriage, death) are held by **each state**; the
  [CDC "Where to Write"](https://www.cdc.gov/nchs/w2w/index.htm) page lists offices.

### United Kingdom and Ireland

- England & Wales: [GRO](https://www.gro.gov.uk) for certificates; [FreeBMD](https://www.freebmd.org.uk)
  for the civil registration index (from 1837). Census released after **100 years**.
- [The National Archives](https://www.nationalarchives.gov.uk): military, wills, census guides.
- Scotland: [ScotlandsPeople](https://www.scotlandspeople.gov.uk) (pay-per-view, but
  very complete).
- Ireland: [IrishGenealogy.ie](https://www.irishgenealogy.ie) (civil and church
  records, free); [National Archives of Ireland census](https://www.census.nationalarchives.ie)
  (1901, 1911, and the 1926 census released in 2026). Most 19th-century census
  returns were destroyed, so church registers and land records (Griffith's
  Valuation) matter more.

### Canada and Australia

- [Library and Archives Canada](https://www.bac-lac.gc.ca): census, immigration,
  military (WWI personnel files are digitized).
- [National Archives of Australia](https://www.naa.gov.au): military service,
  immigration; [Trove](https://trove.nla.gov.au) for newspapers. Vital records are
  held by each state's registry.

### Roots in the former USSR and Eastern Europe

Many English-speaking families have roots in the Russian Empire, Poland, Ukraine,
Belarus, Moldova or the Baltic states. Short version (the
[Russian guide](research-guide.ru.md) has much more):

- **Records**: Orthodox *metrical books* (baptisms, marriages, burials, by parish),
  *confession lists* (yearly household lists with ages), *revision lists* (tax
  censuses 1719–1858), Jewish, Catholic and Lutheran registers kept in parallel.
- **Where**: FamilySearch Catalog by place (province → district); regional state
  archives ([Russian archive guides](https://guides.rusarchives.ru),
  [Ukraine](https://archives.gov.ua), [Belarus](https://archives.gov.by),
  [Moldova](https://arhiva.gov.md)); Polish registers on
  [Geneteka](https://geneteka.genealodzy.pl) and
  [Szukajwarchiwach](https://www.szukajwarchiwach.gov.pl); Lithuania on
  [epaveldas.lt](https://www.epaveldas.lt); Jewish families on
  [JewishGen](https://www.jewishgen.org) and [Yad Vashem's names database](https://yvng.yadvashem.org).
- **Soviet era**: WWII soldiers on [Pamyat Naroda](https://pamyat-naroda.ru) and
  [OBD Memorial](https://obd-memorial.ru); WWI on [gwar.mil.ru](https://gwar.mil.ru);
  [Yandex Archive](https://yandex.ru/archive) has OCR-searchable registers (mostly
  Moscow region). Sites are in Russian; search in Cyrillic.
- Ask on the [VGD forum](https://forum.vgd.ru): threads per district and village
  often list archive references and new digitizations.

### Three traps with old dates and places

**1. Spelling and transliteration.** One surname can appear as Кузнецов,
Kuznetsov, Kuznetsoff, Kusnezow (German), Kuźniecow (Polish), Kooznetsov.
In 19th-century Russian records peasants were often called by their father's name
("Ivan Petrov" = Ivan son of Pyotr), and brothers might carry different surnames.
Search by first name + father's name + place, not surname alone. Put every form you
meet into `aliases`.

**2. Old Style dates.** The Russian Empire used the **Julian** calendar until
February 1918 (Britain and its colonies switched in 1752). The difference is +11 days
in the 18th century, **+12 in the 19th**, **+13 in 1900–1918**. Record the date
**as written in the source** and explain in `note`: "Old Style; New Style
1901-01-27". Never convert silently.

**3. Places change names and borders.** Province (*guberniya*) → district (*uyezd*)
→ rural district (*volost*) → village does not match today's regions; a village
might have two or three names, and the country itself may have changed (Galicia,
Bessarabia, Prussia). Use gazetteers, old maps, Wikipedia. A place in the archive
has `then` and `now`, and an event has `place_as_recorded` — **as written in the
source**.

---

## 4. Step four — archives

### Civil registration

- Most countries issue copies of birth, marriage and death records to relatives,
  often with proof of relationship for recent records.
- Russia: civil registry offices (ZAGS) keep records for 100 years, then pass them
  to state archives. Ukraine: DRATsS offices; Belarus: ZAGS; Moldova: the civil
  status service. Requests from abroad usually go through a consulate or a local
  representative.
- US: the state vital records office; UK: GRO or the local register office.

### Regional and national archives

1. Find the archive for the place (county record office, state archive, oblast
   archive).
2. Find the **collection**: a parish, a diocesan consistory (which kept copies of all
   parish registers), a tax office, a court, an employer.
3. Narrow to the item. For ex-USSR archives the full reference is
   **fond / opis / delo / list** (collection / inventory / file / folio), e.g.
   "f. 123, op. 4, d. 567, l. 89 ob." ("ob." = verso). Without a file number an
   archive has trouble searching.
4. In online viewers the **image (frame) number** is not the **folio** number;
   record both, plus the entry number.

### Writing a request

Short and specific; one person or one event per request:

```
To: <archive>, <address / e-mail>
From: <name, postal address, phone, e-mail>

Please search for the birth (baptism) record of
<name as in records, spelling variants>,
born about <year ± 2> in <village>, <district>, <province>
(today <district, region, country>), <religion>,
parents: <names, if known>.

What is known and from where: <source 1, source 2>.
If known: collection <…>, inventory <…>, file <…>.

I request a certified extract / copy of the record.
Proof of relationship is attached.
I am prepared to pay according to your price list.
```

- **Time**: from weeks to many months, depending on the archive.
- **Cost**: certificate fees are fixed; genealogical searches are often paid by the
  hour. Ask for the price before work starts.
- A negative answer is still a result: log it.

### Access restrictions

Records about private persons are closed for a period set by law: for example,
100 years for UK census returns, 72 for the US census, and in Russia, as a general
rule, **75 years** for documents containing personal and family secrets (earlier
with the person's written consent, or their heirs' after death). Rules change and
vary by country and archive: **check the current law** before you request.

---

## 5. Step five — evaluating evidence

### Kinds of source

- **Original**: the register itself, the original certificate.
- **Derivative**: a copy, extract, transcription, later certificate. Can carry
  copying errors.
- **Index**: a search entry in a database. Only a pointer to a record.

### Kinds of information

- **Primary**: recorded by someone present, at the time (baptism date in a register).
- **Secondary**: recorded later, from hearsay (age in a death record, birthplace in a
  1950s passport). One record can be primary for one event and secondary for another.

### Keep the conflicts

The story says 1902, the register says 1901. The main version goes into `birth`,
the other into `birth_alternatives`, each with its own source. Readers see both.

### Dates from ages

"Died aged 64" in 1930 gives `CAL 1866` with status `calculated_from_age`, not
`1866`. Old records often rounded ages; use `ABT` when in doubt. Several ages from
different years narrow the window; put the calculation in `note`.

### Rules that prevent mistakes

- **A patronymic is not a proven father.** "Ivanovich" only shows the father was
  called Ivan. Which Ivan needs a document. Same for "son of John" in English records.
- **Same surname does not mean related.** A village could have five Smith or Smirnov
  families with no common ancestor in living memory.
- **A downloaded record is not your person** until it matches on at least **two
  independent details**: name + place, parents + year, spouse + children, a godparent
  known from other records.
- Doubtful things get "probably" (`status: "probable"`); an unproven relative gets
  `research_status: "unlinked_candidate"` (drawn dashed); an unproven child goes
  into `probable_children`; the hypothesis itself goes into `research_leads`.

---

## 6. Step six — recording it: a worked example

*Fictional example; the archive reference is a placeholder.*

**Before:** from the interview (S1 above), Anna Petrovna Kuznetsova, née Smirnova,
born "around 1902" in Pokrovskoye. **Found:** via the FamilySearch Catalog, the 1901
register of Pokrovskoye church: "Born January 14, baptised 15: Anna; parents: peasant
Pyotr Ivanov Smirnov and his lawful wife Maria Vasilyeva". Name, patronymic, village
and the mother's name the interviewee remembered all match: more than two
independent details.

**Source:**

```json
{"id": "S2", "kind": "church_record",
 "title": "Pokrovskoye church register, 1901: birth of Anna",
 "file": "sources/pokrovskoe-1901-births-p3.jpg",
 "url": "https://www.familysearch.org/ark:/…",
 "locator": "State archive of … region, f. 000, op. 0, d. 000, l. 3 ob., births no. 2 (image 41)",
 "scope": "'January 14 born, 15 baptised: Anna. Parents: peasant of the village of Pokrovskoye Pyotr Ivanov Smirnov and his lawful wife Maria Vasilyeva, both Orthodox. Godparents: peasant of the same village Nikolai Ivanov Smirnov and peasant maiden Evdokia Petrova.' Dates are Old Style."}
```

**Person:**

```json
{"id": "I5",
 "given_names": "Anna Petrovna", "surname": "Kuznetsova",
 "display_name": "Kuznetsova (Smirnova) Anna Petrovna",
 "sex": "F", "relation": "grandmother",
 "aliases": ["Smirnova Anna Petrovna", "Nyura"],
 "identity_source_ids": ["S2"],
 "birth": {"date": "1901-01-14", "place_as_recorded": "village of Pokrovskoye",
           "place_slugs": ["pokrovskoe"], "status": "documented",
           "source_ids": ["S2"],
           "note": "Old Style; New Style 1901-01-27."},
 "birth_alternatives": [{"date": "ABT 1902", "status": "family_report",
                         "source_ids": ["S1"]}],
 "notes": ["Anna was born in January 1901 in Pokrovskoye, the daughter of the peasant Pyotr Ivanovich Smirnov (S2). At home she was called Nyura; her daughter remembered her as born 'in 1902', but the register gives a year earlier (S1)."]}
```

**Lead**: the godfather has the same patronymic as the father; maybe a brother:

```json
{"id": "L1", "title": "Nikolai Ivanov Smirnov: Pyotr's brother?",
 "status": "open", "person_id": "I5", "source_ids": ["S2"],
 "record": "Anna's godfather in 1901 is Nikolai Ivanov Smirnov of the same village.",
 "limitations": "A shared patronymic proves nothing. Check Pokrovskoye confession lists 1890–1905: same household?"}
```

**Correction**: a fact changed, so it goes into `corrections`:

```json
{"person_id": "I5", "field": "birth.date",
 "previous": "ABT 1902", "current": "1901-01-14",
 "reason": "Birth register entry found; the family version is kept in birth_alternatives.",
 "source_ids": ["S2"]}
```

**Research log**, including what was **not** found:

```json
[{"date": "2026-10-05", "action": "FamilySearch Catalog: Pokrovskoye church registers 1900–1903, births",
  "result": "Found 1901 entry (S2). 1900, 1902, 1903: no other children of Pyotr Smirnov.", "scope": "I5"},
 {"date": "2026-10-05", "action": "Yandex Archive: 'Smirnova Anna Petrovna' 1899–1903",
  "result": "Nothing: this district is not in the database.", "scope": "I5"}]
```

**Check and build** (in the site folder):

```
gene validate     # broken links, non-ISO/GEDCOM dates, S## without a source, missing files
gene build        # builds the site; refuses when validation fails
```

---

## 7. Step seven — work systematically

- **Log every session.** Where you looked, what you searched for, which years, what
  you found. A negative result ("not in the 1890–1895 registers") is just as valuable:
  it saves time for you and for the next researcher.
- **Check every source, not just the first hit.** Found a clue on FamilySearch? Keep
  going: the same family may be in a census, a newspaper, a directory, a military
  database. Work through the whole list in step 3 and log what you checked and
  what you didn't.
- **Revisit leads.** Archives digitize new collections every month. Every few months,
  go through `research_leads` with status `open`.
- **Ask relatives through the site.** The Questions section holds concrete questions
  for the family ("Who is in this photo?", "Where is grandfather buried?"). An answer
  becomes a new `family_report` with a date and the name of the person who told it.
- **One line at a time.** Ten threads started at once are never finished.

### DNA tests, briefly

- **Autosomal** tests find relatives on all lines, reliably to about 3rd–4th cousins
  and sometimes further: useful to find unknown relatives or test a hypothesis.
- **Y-DNA** follows only the direct male line; **mtDNA** only the direct female line.
- DNA does **not name** an ancestor: a match shows a common ancestor exists; who it
  is must be proven with documents.
- Results can reveal the unexpected (adoption, a different father). Test knowing
  this, and never publish other people's results.

---

## 8. Ethics and privacy

- **Living people.** By default the engine hides the living: no death date and born
  within the last 100 years means only the name is shown, no dates, places, photos
  or documents, and the page is hidden from search engines. Set `"living": false`
  only with the person's consent.
- **Consent.** Ask before publishing photos, letters and stories. A storyteller may
  say "not for the website".
- **Sensitive topics**: repression, deportation, captivity, illegitimacy, adoption,
  illness, crime. Write plainly, from the documents, without judgement. Think of
  which living people it affects; sometimes it is better to wait or to ask.
- **Hide on request.** If the family asks to remove a document, set `"hidden": true`
  on the source: the record and file stay with you, but it never reaches the site or
  GEDCOM, and links to it are removed at build time. Don't describe the hidden item
  in logs that appear on the site.
- **Copyright.** Family photos belong to you or your relatives. Archive and
  FamilySearch images: follow the archive's or site's terms (often with the full
  reference; sometimes not at all, in which case link with `url`). Other people's photos
  and illustrations: public domain or with permission, with credit.

---

## 9. Checklists

### Your first weekend

- [ ] Write down everything you know: parents, grandparents, great-grandparents.
- [ ] Call your oldest relative and arrange a conversation.
- [ ] Hold it using the step 1 checklist (recorded, with consent).
- [ ] Gather every document and photo at home; scan both sides.
- [ ] Start `family_tree.json`: you, your parents, your grandparents.
- [ ] One `S##` record per document and per conversation, transcription in `scope`.
- [ ] Choose one line and one place to start with in the databases.
- [ ] Find that place's historical name and jurisdiction (county, parish, province).
- [ ] Search FamilySearch (index **and** Catalog by place) and the national
      census/registration site for that country.
- [ ] Log what you searched in `research_log`, including empty results.
- [ ] `gene validate`.

### Before you publish

- [ ] `gene validate` passes without errors.
- [ ] Every fact has a `status` and `source_ids`; family stories are `family_report`,
      not `documented`.
- [ ] No relationships based only on a patronymic or a surname; doubtful ones are
      "probable" or in `research_leads`.
- [ ] Every change of a fact is in `corrections`.
- [ ] The living are hidden; anyone shown with `"living": false` has agreed.
- [ ] Documents the family asked to remove have `"hidden": true`.
- [ ] Photos are upright as viewed; photos with writing on the back have `back`.
- [ ] You have the right to publish every photo and scan.
- [ ] Texts on sensitive topics re-read through a relative's eyes.
- [ ] `gene build`, then look at the site on a phone.
