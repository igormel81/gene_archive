# Backups, publication previews and atomic changes

## Private backups and tested restoration

```sh
gene backup my-family -o ../family-backup.tar.gz
# Select the actual server state if it lives elsewhere:
gene backup my-family -o ../family-backup.tar.gz --state /path/to/server-state
gene restore ../family-backup.tar.gz --check
gene restore ../family-backup.tar.gz restored-family
```

A backup includes source data/settings, all documents (including hidden and Git-ignored
files), content, translations, Git history and server state: comments, accounts,
proposals and audit records. SQLite's backup API includes committed WAL data.
Individual databases are consistent; pause server writes if multiple databases must
represent exactly the same instant. Pass `--state` for an external state directory;
the command does not discover server configuration on other machines.

Generated `_site/`, `_site.*`, folders marked `.gene-archive-output`, caches, `.venv`,
`node_modules` and editor temporary files are excluded. Links and special files are
rejected: keep real documents inside the archive. Git history travels in a bundle;
remote configuration, hooks and the staging index are not restored. Uncommitted
working files are preserved. An archive with history must be its repository root.

**The backup is private and unencrypted.** It contains living-person details and password
hashes. Its mode is 600; keep it outside public/source folders. Existing backup files
are never overwritten. Checksums detect damage, not authenticity; restore only trusted
backups. Limits: fewer than 100,000 files, 100 GiB unpacked, a 16 MiB manifest.

`restore --check` verifies paths, SHA-256, databases and Git history, and actually builds
the site in a temporary folder. It leaves the original archive intact and exits nonzero
on failure. Restoration requires a **new** destination, published only after verification.
Server state is restored to `<destination>/.gene-state`. Accounts/passwords are retained;
sessions and invitations are cleared and the cookie secret rotated. Sign in again and
reissue invitations as needed. Deployment environment variables, a PIN, proxy and remote
services are not configured automatically. Update the server's state path after moving.

## Inspect what will be published

```sh
gene publish-preview my-family
gene publish-preview my-family --json > publication.json
```

The real builder runs on a temporary snapshot. Source JSON, Git, the existing output and
cache are unchanged; the normal lock file in `.gene-state` coordinates readers/writers.
The report lists living-person restrictions and changed/removed fields; document
publication decisions and reasons, removed mail metadata and original files present in
the output; journal counts and decisions by zero-based entry index; all output files with
size/SHA-256 (JSON); build warnings and missing translations. Hidden values and private
journal text are not printed. IDs, file names and structure can still be private: do not
publish this report.

A hidden document's file may still be copied by a manual content/media link; the preview
warns explicitly. Custom HTML, `img/` and `geo/` are published as supplied and need manual
review. The report describes this snapshot only; rerun it after changes.

## One transaction for related changes

```json
[
  {"kind":"source","as":"register","record":{"title":"Invented register","kind":"church_record"}},
  {"kind":"person","as":"anna","record":{"given_names":"Anna","surname":"Example","birth":{"date":"1900-01-02","source_ids":[{"$ref":"register"}]}}},
  {"kind":"family","record":{"partners":["I1"],"children":[{"$ref":"anna"}],"source_ids":[{"$ref":"register"}]}}
]
```

```sh
gene apply my-family changes.json --atomic --dry-run
gene apply my-family changes.json --atomic --if-version VERSION --build
```

Use the preview response's `base_version` as VERSION. The entire batch is evaluated in
memory under one lock. Each intermediate operation must pass the normal editor checks:
create documents before citing them and people before families. Successful operations
are persisted once, with journals for every change and one batch commit. The first use
of Git also creates an initial-history commit. A failed check/commit leaves no partially
saved batch. A subsequent build failure does not undo saved data: the CLI returns a
`build_error`.

`as` is a unique operation name; `{"$ref":"anna"}` resolves to the ID returned by an
earlier record operation. Unknown/forward references are rejected. Preview sees prior
in-memory operations but does not reserve IDs. `--if-version` checks family_tree.json,
not settings/document files. Without `--atomic`, the original per-operation behavior
is unchanged. These features are CLI commands; dedicated browser-editor screens have
not been added.
