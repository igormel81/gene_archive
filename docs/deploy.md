# Publishing the site

**[Русская версия](deploy.ru.md)**

`gene build my-family` puts a complete static site into `my-family/_site`. How to put it
online depends on whether you want comments from relatives.

| | Static hosting | Your own server |
|---|---|---|
| Cost | free (GitHub Pages, Netlify, Cloudflare Pages) | a small VPS |
| Comments from relatives | no | yes, with moderation |
| PIN-protected private archive | no | yes |
| `site.json` | `"comments": false` | `"comments": true` |

## Before you publish: privacy

- The built site hides living people, but **your `family_tree.json` does not**. Never publish
  the site folder itself (or a public repository with it) — only the built `_site`.
- Check `gene build` output: "N living, details hidden". Open a few living relatives on the
  built site: only names must be visible.
- Ask relatives before publishing photos and stories about them; mark documents they want
  removed with `"hidden": true` — see the [research guide](research-guide.md#8-ethics-and-privacy).

## GitHub Pages

**A. Upload the built site** (simplest, the data stays on your computer):

1. Create a repository, e.g. `family-site`. Settings → Pages → Source: *Deploy from a branch*, `main`, `/ (root)`.
2. `gene build my-family --base-url https://<user>.github.io/family-site/`
3. Copy the contents of `my-family/_site` into the repository and push.

**B. Build on GitHub** (the data lives in a **private** repository — GitHub Pages from a
private repository needs a paid plan): copy [`templates/github-pages.yml`](../templates/github-pages.yml)
to `.github/workflows/site.yml` in the repository with your site, then Settings → Pages →
Source: *GitHub Actions*. Every push rebuilds and publishes the site.

## Netlify, Cloudflare Pages, any web server

Upload the contents of `_site` (drag and drop in Netlify, `rsync` to a server). For nginx or
Apache no configuration is needed: the site is plain files with relative links and works in
a sub-folder.

## Your own server with comments

The comments server is part of the package and needs only Python:

```sh
gene serve my-family --host 127.0.0.1 --port 8111
```

It builds the site, serves it and stores comments in `my-family/.gene-state/comments.db`.
Put it behind a web server with HTTPS (Caddy, nginx) and set `GENE_TRUST_PROXY=1` so that
the limits see real visitors' addresses.

Caddy:

```
family.example.org {
    reverse_proxy 127.0.0.1:8111
}
```

nginx, the site in a sub-folder:

```
location /family/ {
    proxy_pass http://127.0.0.1:8111/;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

with `gene serve my-family --prefix /family`.

systemd unit (`/etc/systemd/system/gene.service`):

```ini
[Unit]
Description=Family archive
After=network.target

[Service]
User=gene
WorkingDirectory=/srv/my-family
Environment=GENE_TRUST_PROXY=1
ExecStart=/usr/local/bin/gene serve /srv/my-family --host 127.0.0.1 --port 8111
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Docker

```sh
docker run -d -p 127.0.0.1:8111:8111 -v "$PWD/my-family:/site:ro" -v gene-state:/state ghcr.io/igormel81/gene_archive:latest
```

(or build the image yourself: `docker build -t gene-archive .`)

or `docker compose up -d` with [`docker-compose.yml`](../docker-compose.yml). After changing
the data, restart the container: it rebuilds the site on start.

### Options

| Flag of `gene serve` | Environment | Meaning |
|---|---|---|
| `--pin 1234` | `GENE_PIN` | the site opens only after entering the PIN (a private archive; pages are `noindex`) |
| `--moderate` | `GENE_MODERATE=1` | new comments are hidden until you approve them |
| `--prefix /family` | `GENE_PREFIX` | the public path when the site lives in a sub-folder behind a proxy |
| `--state DIR` | `GENE_STATE_DIR` | where `comments.db` lives |
| — | `GENE_TRUST_PROXY=1` | take the visitor address from `X-Forwarded-For` (only behind your own proxy) |

### Comments

```sh
gene comments my-family list                         # all comments
gene comments my-family approve 12                   # publish a moderated one
gene comments my-family hide 13                      # hide spam
gene comments my-family done 12 "added to the tree"  # "✓ Taken into account" under the comment
```

Comments are limited to 4000 characters, 30 per 10 minutes from one address; a hidden form
field catches simple bots. Back up `comments.db` together with your data.

## Online editor

With `gene serve <folder> --editor` (or `GENE_EDITOR=/site` in Docker) relatives with an account edit
the data in a browser at `/edit/`: see [editor.md](editor.md).

## Releases (for maintainers)

```sh
# bump the version in pyproject.toml, move CHANGELOG "Unreleased" under the new version, commit, then:
git tag v0.2.0 && git push origin v0.2.0
```

or run Actions → Release → *Run workflow*: it creates the tag `v<version>` on the current `main` itself.

The `Release` workflow checks that the tag matches `pyproject.toml`, runs the tests, creates the
GitHub release with the CHANGELOG section and the package files, and publishes the Docker image
`ghcr.io/igormel81/gene_archive:<version>` (and `:latest`).

Publishing to PyPI is off until it is set up once:
1. On pypi.org → *Your projects* → *Publishing* → add a pending trusted publisher: project `gene-archive`,
   owner `igormel81`, repository `gene_archive`, workflow `release.yml`, environment `pypi`.
2. On GitHub → Settings → Environments → create `pypi`; Settings → Secrets and variables → Actions →
   *Variables* → `PYPI_PUBLISH` = `true`.
The next tag then also publishes the package, and `pip install gene-archive` works.
