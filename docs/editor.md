# Online editor

**[Русская версия](editor.ru.md)**

The editor lets you change the data in a browser, without JSON or a command line: people,
families, documents (with scan uploads) and places. It is part of the `gene serve` server, so
static hosting (GitHub Pages, Netlify) does not have it — you need your own server or Docker
([publishing](deploy.md)).

What it does:

- **Password sign-in**, an account for each person. Two roles: an *editor* changes the data; an
  *administrator* also handles readers' proposals, restores earlier versions and manages users.
  The PIN for readers of the site stays as it was and has nothing to do with the editor.
- **Checks before saving.** A change that would add an error (a broken reference to a person or
  document, an unreadable date) is not saved; the editor shows what is wrong. Errors that were
  already in the file do not block editing other records.
- **Dates as people write them.** "about 1899", "before 1950", "between 1900 and 1905",
  "9.10.1899", "9 October 1899" (and the same in Russian) are stored as `ABT 1899`, `BEF 1950`,
  `BET 1900 AND 1905`, `1899-10-09`, `9 OCT 1899`.
- **Nobody overwrites anybody.** If two people open the same record and the first one saves,
  the second gets "someone else changed this record" instead of silently overwriting it.
  Edits of different records never conflict.
- **The journals keep themselves.** Every changed field becomes a line in `corrections` (before,
  after, who, why, which document) and every save a line in `research_log` — the corrections
  log on the site.
- **History in git.** Every save is a commit by the person who made it. If the site folder is
  not a git repository yet, the editor creates one on first start. An administrator can bring
  the data back to any version (that is a new change too and can be undone the same way).
- **The site updates itself** a few seconds after a save; the previous version stays online
  while it builds. A failed build is shown in the editor.
- **Readers' proposals.** A person's card on the site gets "Suggest a correction": a relative
  picks what to correct (date or place of birth or death, the name, or "other"), writes the
  correct value and how they know. An administrator sees them under "Proposals" and applies
  one with a click, opens the record, or rejects it.
- **Data checks** (the "Checks" tab, also `gene hints`): impossible facts (born after the
  mother's death, a parent younger than 14, a mother over 55 or a father over 75, a marriage before 15) and gaps (no dates, a date without a
  document, people not connected to the tree, unused documents, places without coordinates) —
  a to-do list for the next search; every item opens its record.
- **Uploads of scans and photos**: JPEG, PNG, WebP, GIF, PDF up to 30 MB. Photos are re-saved
  (with Pillow installed): turned upright, with camera and GPS details removed.

## Turning it on

```sh
gene users my-family add igor --role admin --display "Igor"
# → a one-time invitation link where the password is set
gene serve my-family --editor
```

Open the link (or `http://127.0.0.1:8111/edit/` and sign in). With `base_url` in `site.json`
the link already has your site's address.

For the "Suggest a correction" button on the site, `site.json` needs `"comments": true`
(the site runs with the server).

## Users

The easiest way is the editor itself, "Users" (administrators only): "Create and get a link",
then send the link to the relative, who sets the password there. The link works once and for
7 days; "New link" if it expired or the password is forgotten.

The same from the command line:

```sh
gene users my-family list
gene users my-family add anna --display "Aunt Anna"           # editor
gene users my-family add petr --role admin                    # administrator
gene users my-family invite anna                              # a new link (password reset)
gene users my-family role anna admin
gene users my-family disable anna                             # enable to turn back on
gene users my-family passwd igor                              # set a password right here
```

Logins use latin letters (`anna`, `anna.k`); the name (`--display`) signs the changes in the
history and the corrections log. Passwords have at least 10 characters; only a scrypt hash is
stored.

## Docker

```yaml
services:
  gene:
    image: ghcr.io/igormel81/gene_archive:latest
    ports: ["127.0.0.1:8111:8111"]
    volumes:
      - ./my-family:/site          # no ":ro": the editor writes to the folder
      - gene-state:/state
    environment:
      GENE_EDITOR: /site
    user: "1000:1000"              # owner of my-family (id -u; id -g)
```

Users: `docker compose exec gene gene users /site add igor --role admin`.

## Security

- Open the editor over **HTTPS** only (Caddy, nginx — see [publishing](deploy.md)): the sign-in
  cookie is `Secure` and is not sent over plain http (except on `127.0.0.1`).
- Sign-in: at most 10 failed attempts per 15 minutes per address and per login.
- Sessions last 30 days; changing the password or disabling a user ends all their sessions.
- Changes are accepted only from the editor page (a client header and the session's CSRF
  token, `SameSite=Strict` cookie); the editor cannot be framed by other sites.
- The editor shows **all** data, living people included — give access only to people you
  trust. The published site still hides the living.
- Sign-ins and actions are logged in the `audit` table of `<state>/editor.db`.

## Backups

Keep the site folder (with its `.git` — the whole history of changes) and the state folder
(`.gene-state` or the Docker volume: `editor.db` with users and proposals, `comments.db`).
A daily `git push` from the site folder to a private GitHub repository is an easy backup.

## What the editor does not cover

Fields without a form — residences, profiles on other sites, alternative dates, place
timelines and materials — are edited in "Other fields (JSON)" of the same record, in the
`family_tree.json` format. Research leads, `content/` pages and `site.json` stay in files;
AI assistants can help — [ai-assistants.md](ai-assistants.md).
