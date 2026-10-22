# Reliable edits and journal publication (0.7)

`gene apply`, the online editor and `gene build` coordinate with a shared site lock,
including across local processes. Saves cover read → validation → atomic replacement →
git commit. Do not run unrelated Git commands in the same archive during a save.
A commit failure is returned as an error; JSON and staging are restored. When Git is
not installed, the existing no-history mode remains available (`commit: null`).
A build scheduling failure after a successful commit is explicitly reported as already
saved; it does not undo a completed commit.

The output must not replace the archive, its ancestors or input directories. A nonempty
unrecognised directory is refused. Existing generated sites remain supported. Temporary
and backup directories have unique names, so unrelated `.build` and `.old` directories
are not removed. A failed output swap restores the previous generated site.

IDs are never recycled: `id_counters` records high-water marks for I/F/S/L/R/C, including
historical IDs and IDs allocated before a restore. Do not edit these counters downwards.
Old archives get counters when first saved; legacy records are not otherwise migrated.

## Journals are private until reviewed

With `privacy.hide_living=true` (the default), both `research_log` and `corrections`
require `"visibility":"public"` to be published. This includes legacy entries: they
remain intact in `family_tree.json`, but no longer appear on the public site until
reviewed. Generated editor corrections/logs and `gene apply` logs default to private.
Known references to living people/families are filtered even when marked public.

Review the whole entry, including reason, previous/current values and scope, before
publishing it. Do not mass-publish old logs: free text may mention a different living
person. This is not automatic anonymisation of arbitrary story/content text. The demo's
fictional journals have explicit public flags to demonstrate the feature.

A reviewed log can be added explicitly:

```json
{"op":"log","action":"Register search, parish and years","result":"No matching record in the examined index","visibility":"public"}
```

`privacy.hide_living=false` retains all journals; use that only within the owner's
chosen privacy policy. Private original journals are never deleted by a build.

## Research resources and reading progress

`gene apply` accepts `kind: "research_resources"` (R#) and `kind: "coverage"` (C#),
with the same dry run, validation, journals and Git history as other records.

```json
[
  {"kind":"research_resources","record":{"name":"Example archive","url":"https://example.org"}},
  {"kind":"coverage","record":{"parish":"Example parish","resource_id":"R1","entries":[{"year":1858,"part":"revisions","status":"partial","up_to":"household 4","film":"Archive file 12","frames":"folios 1–8"}]}}
]
```

Use the returned resource ID rather than assuming R1 in an existing archive. Save a record
with its `id` to update it; `op: "delete"` deletes an unreferenced record. Without `--atomic`, requests in an
array are sequential independent transactions, not an all-or-nothing batch. Such a dry-run
array does not reserve IDs or make one preview visible to the next; preview dependent
requests separately after saving their prerequisite.

Parts: `births`, `marriages`, `deaths`, `confessions`, `revisions`, `census`.
A legacy coverage row without an ID can be edited with its exact original object in
`base`; only that edited row is assigned C#. A stale or ambiguous base is rejected:

```json
{"kind":"coverage","base":{"parish":"Example parish","entries":[]},"record":{"entries":[{"year":1858,"part":"revisions","status":"complete"}]}}
```

Leads can retain `next`, `checked`, `stage`, `blocked_by`, and `expected_sources`.
The engine preserves those fields; it does not infer research permissions from text or
impose one family's archive-request ban on everyone. The catalogue and online search
belong to genealogy-mcp; these changes only affect gene-archive.

For tested backups, publication previews and atomic batches, see [archive workflows](archive-workflows.md).
