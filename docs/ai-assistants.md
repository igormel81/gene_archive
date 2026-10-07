# Filling the site with Claude or Codex

**[Русская версия](ai-assistants.ru.md)**

A gene-archive site is a folder of files: `family_tree.json`, scans in `sources/`, texts in
`content/`. Coding agents work well with such a folder — **Claude Code** (Anthropic) and
**Codex** (OpenAI). You can tell them in plain words: "here is a scan of a birth register,
transcribe it and add it to the archive", and the agent finds the right people, creates the
document record, extends the life story, checks the data and builds the site. The archive
this engine grew from was made that way: about 550 people and 500 documents, with two agents
working in parallel.

An agent is an assistant, not a researcher. It transcribes, structures and writes quickly and
neatly, but it misreads old handwriting, can take a namesake for a relative and can confidently
"fill in" what is missing. So the main rule is: **you review every change**, and the rules for
the agent are written down in `AGENTS.md`.

---

## 1. Setup

### The site folder and git

```sh
gene init my-family --lang en     # or: gene import tree.ged my-family
cd my-family
git init && git add -A && git commit -m "Start the archive"
```

`gene init` puts two files for agents into the folder:

- **`AGENTS.md`** — the working rules: where things are, how to number records, what counts as
  proven, how to write life stories, what to do after an edit. Codex and other agents read it.
- **`CLAUDE.md`** — one line, `@AGENTS.md`: Claude Code loads the same rules.

Add your own notes to `AGENTS.md`: who keeps the archive, which relatives send material, how the
family surnames are spelled, which archives have already been asked. The agent reads this file at
the start of every session — it is its memory of the project.

Git lets you see every change (`git diff`) and undo a bad one (`git restore`). If the repository
goes to GitHub, make it **private**: `family_tree.json` contains details of living people.

### Claude Code

1. Install: https://code.claude.com/docs (a Claude Pro/Max plan or an API key).
2. Open a terminal in the site folder and run `claude`.
3. You can also use the Claude desktop app, or claude.ai/code with the repository on GitHub.

Claude Code sees images: drop a scan into the window or give the path of a file in `sources/`.

### Codex

1. Install the Codex CLI: https://developers.openai.com/codex (a ChatGPT plan or an API key).
2. In the site folder: `codex` for a conversation, or `codex exec "task"` for a single task.
3. Codex reads `AGENTS.md` by itself.

### Privacy

Everything the agent sees goes to its company's servers. Before you start:

- check your plan's data settings and policy (whether data is used to train models and how to opt out);
- do not show the agent documents the family asked not to share, or details of living relatives
  without their consent;
- the agent does not send letters to archives or relatives — it only drafts them.

---

## 2. First steps

Start with a short introduction — the agent reads the data and the rules:

> Read AGENTS.md and family_tree.json. Tell me briefly what the archive already has: how many
> people, which branches, who has no document at all. Do not change anything.

After every task, ask to see the changes:

> Show `git diff --stat` and list in words what you changed and why.

Check especially:

- **transcriptions** — compare with the scan itself: names, dates, numbers;
- **relationships** — what each new link is based on;
- **status** — `documented` only where there really is a document.

Good — commit (`git commit -am "…"` or ask the agent); bad — `git restore .` and tell the agent
what is wrong.

---

## 3. Common tasks and ready-made requests

Copy and adapt these. The agent applies the rules from `AGENTS.md` by itself; there is no need
to repeat them in every request.

### A relative's account → people and families

> Here is my conversation with Aunt Anna (28 September 2026). Add to the archive: new people and
> families, a `family_report` source with a summary of the conversation in `scope`, and references
> to it in the notes. Approximate dates — `ABT`, status `family_report`. What she is unsure about
> goes to `research_leads`. Record it in `research_log`.
>
> "Grandma Mary, born Sullivan, was born in Ballina, I think in 1902…"

### A scan → a source and facts

> I put `sources/ballina-baptisms-1902-p45.jpg` into the folder — the baptism register of Ballina
> parish, 1902, page 45. Find the baptism of Mary, daughter of Patrick Sullivan. Transcribe it fully
> into `scope` (literally, illegible parts as `[illegible]`) and create a `church_record` source `S…`.
> If it confirms Mary's (I23) birth date, set `documented` with the source and record the old value
> in `corrections`. Add parents and godparents only when at least two details match; otherwise a lead.

The agent shows the transcription — **compare it line by line with the scan** before accepting.

### A family photo with its back

> There are two files in `sources/`: `sullivan-family-1925.jpg` and `sullivan-family-1925-back.jpg`.
> It is one photo with its back side. Create a `family_photo` source with `back`; copy the
> inscription into `scope`: "Inscription on the back: «…»". Link the people named in the inscription
> through `identity_source_ids`. If the photo is sideways, rotate the file.

### A life story

> Write `notes` for Patrick Sullivan (I20) from all his documents: a connected story in the order of
> his life, every fact citing its document, family knowledge marked "according to…", doubts in a
> separate last paragraph. Do not repeat dates and relatives the card already shows. Show me the
> text before writing it.

### What to look for next

> Look at the Sullivan line. What do we know, what is missing, where could it be found? Make a
> step-by-step research plan (archives, databases, years and parishes) and record it in
> `research_leads`. Do not add anything to the tree.

More requests for searching databases and archives — in [a separate collection](research-prompts.md).

It helps to give the agent the [research guide](research-guide.md):
"Read docs/research-guide.md of gene-archive and make the plan by it".

### Something found online

> Here is a link to a record in a military database and its text: … Compare it with our John Sullivan
> (I31): year and place of birth, place of enlistment, relatives. If two or more details match, create
> an `online_military_record` source with the `url` and link it; if not, a lead explaining what
> matched and what did not.

### Places

> Add the place "Ballina" (County Mayo): slug `ballina`, coordinates of the church, "then" and "now"
> names, a short description from Wikipedia with the link in `materials`. Link births and marriages
> whose `place_as_recorded` mentions Ballina.

### The Story page

> Write `content/story.html` following docs/content.md of the engine: chapters as
> `<section id="s-…">` by generation, people as `<a class="pl" data-p="I…">` links, documents in
> brackets (S…). Only facts from the archive, no embellishment. Add the timeline to `site.json` →
> `story.timeline`.

### Questions to relatives

> See what we do not know about the generations still within living memory, and write 5–7 questions
> to relatives in `site.json` → `questions`, each tied to a person. Make them concrete, answerable from
> memory.

### Comments from the site (with the comments server)

```sh
gene comments . list > /tmp/comments.txt
```

> Here are new comments from relatives: … Add what is confirmed to the archive (a `family_report`
> source from the comment's author) and what is disputed to the leads. For each, tell me what was
> done; I will mark it with `gene comments . done N "…"`.

### Translation

```sh
gene translations . ru > todo-ru.json
```

> Translate the texts in todo-ru.json into Russian and add them to translations/ru.json. Keep names
> spelled the same way every time, translate kinship terms exactly, explain archaic words. Do not
> touch the `<1>…</1>` markers.

### Importing GEDCOM and tidying up

> I imported the tree from MyHeritage (`gene import`). Go through the people: make `display_name`
> "Surname Given names", merge obvious duplicates (show me the list before merging), move dates from
> notes into events where possible. Every change goes to `corrections`.

---

## 4. Checking and publishing

Ask the agent to finish every task like this:

> Run `gene validate` and `gene build`, fix the errors, show `git diff --stat`.

Look at the result in a browser: `gene serve .` → http://127.0.0.1:8111. Open the people and
documents that changed and check living relatives — only their names must be visible.
Publishing — [docs/deploy.md](deploy.md).

---

## 5. Two agents at once

Claude and Codex can run in parallel on different tasks — for example, Codex transcribes a batch of
scans while Claude writes life stories. To keep them out of each other's way:

- give them tasks about **different** people or files;
- `AGENTS.md` already tells them to check `git status` before editing;
- commit after every task — then you can see who did what;
- if both edited `family_tree.json`, run `gene validate` after both.

Codex is handy for batches without a conversation:

```sh
codex exec "Transcribe the scans sources/ballina-baptisms-1902-*.jpg and create sources by the rules in AGENTS.md. Do not change facts about people, only sources." < /dev/null
```

---

## 6. What not to delegate

- **Deciding who is related to whom** without documents. The agent proposes — you decide.
- **Setting `documented`** from an index or someone else's tree: it is `online_reference` until the
  original is checked.
- **Sending letters and requests** to archives and relatives.
- **Deleting** people, documents and comments. A document someone asked to remove gets `"hidden": true`.
- **Publishing details of living people** "to complete the story".

---

## Cheat sheet

| Task | Request |
|---|---|
| Introduction | "Read AGENTS.md and family_tree.json, tell me what is there. Change nothing." |
| A relative's account | "Here is my conversation with … — add people and families, a family_report source." |
| A scan | "Transcribe sources/….jpg into scope, create the source, confirm the facts." |
| A photo with its back | "Create a family_photo with back, the inscription into scope." |
| A life story | "Write notes for I…: connected, citing documents, doubts separately." |
| A research plan | "What is missing on the … line? The plan into research_leads." |
| Translation | "Translate todo-ru.json into translations/ru.json." |
| End of a task | "gene validate, gene build, git diff --stat." |
