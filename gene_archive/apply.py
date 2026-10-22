"""`gene apply`: changes to family_tree.json from scripts and AI assistants, through the same path as the online editor —
the checks (a change that adds an error is refused), the corrections and research logs, a git commit per change by
its author and, with --build, a rebuild of the site.

    echo '{"op": "save", "kind": "people", "record": {"given_names": "Пётр", "surname": "Колодин", "sex": "M"}}' \\
        | gene apply my-family --author "Igor" --build

With --atomic, the whole batch is previewed in memory and saved with one commit.
Use as / {"$ref": "alias"} for dependencies and --if-version for a previewed data revision.

Requests (one JSON object, a list, or one object per line):
  {"op": "save", "kind": K, "record": {...}, "reason": "…", "source_ids": ["S12"]}
        a new record (no id) or an update of the record with this id: the fields given are merged into it
        (nested objects too; a field set to null is removed)
  {"op": "delete", "kind": K, "id": "I12", "reason": "…"}
  {"op": "log", "action": "what was searched and where", "result": "what came out", "scope": "…"}
K is one of people, families, sources, places, research_leads, research_resources, coverage (person, family, source, place, lead also work).
Answer: one JSON object per request, {"ok": true, ...} or {"ok": false, "error": "…", "errors": [...]}.
"""
import copy
import json

from .editor import KINDS, SaveError, Store

ALIASES = {"person": "people", "family": "families", "source": "sources", "place": "places", "lead": "research_leads"}


def merge(old, new):
    """Fields of `new` over `old`; nested objects merged; None removes a field."""
    out = copy.deepcopy(old)
    for k, v in new.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def parse(text):
    text = text.strip()
    if not text:
        return []
    try:
        req = json.loads(text)
        return req if isinstance(req, list) else [req]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def run_one(store, user, req, dry_run=False):
    op = req.get("op", "save")
    if op == "log":
        return store.log(user, req.get("action"), req.get("result"), req.get("scope", ""), dry_run=dry_run, visibility=req.get("visibility", "private"))
    kind = ALIASES.get(req.get("kind"), req.get("kind"))
    if kind not in KINDS:
        raise SaveError(f"kind must be one of {', '.join(KINDS)}", 400)
    key_field, _ = KINDS[kind]
    current = {r.get(key_field): r for r in store.load().get(kind, [])}
    if op == "delete":
        key = req.get("id") or req.get(key_field)
        if key not in current:
            raise SaveError(f"no {key} in {kind}", 404)
        return store.delete(user, kind, current[key], req.get("reason", ""), dry_run=dry_run)
    if op != "save":
        raise SaveError(f"unknown op {op!r}", 400)
    record = req.get("record")
    if not isinstance(record, dict):
        raise SaveError("record must be an object", 400)
    if kind == 'coverage' and isinstance(req.get('base'), dict) and not req['base'].get('id'):
        base = req['base']
        return store.save(user, kind, merge(base, record), base=base, reason=req.get('reason', ''),
                          source_ids=req.get('source_ids'), dry_run=dry_run)
    key = record.get(key_field) or req.get("id")
    if key and key in current:   # update: merge into the stored record, which is also the base (no lost edits)
        base = current[key]
        rec = merge(base, record)
        rec[key_field] = key
        return store.save(user, kind, rec, base=base, reason=req.get("reason", ""),
                          source_ids=req.get("source_ids"), dry_run=dry_run)
    if key and kind != "places":
        raise SaveError(f"no {key} in {kind} (leave the id out to create a record)", 404)
    return store.save(user, kind, record, reason=req.get("reason", ""), source_ids=req.get("source_ids"), dry_run=dry_run)


def apply(folder, requests, author="gene apply", login="cli", dry_run=False):
    store = Store(folder, initialize_git=not dry_run)
    user = {"name": login, "display": author, "role": "editor"}
    out = []
    for req in requests:
        try:
            r = run_one(store, user, req if isinstance(req, dict) else {}, dry_run)
            out.append({"ok": True, **r})
        except SaveError as e:
            out.append({"ok": False, "error": str(e), "status": e.status, **e.extra})
        except (ValueError, TypeError, KeyError) as e:
            out.append({"ok": False, "error": f"bad request: {e}", "status": 400})
    return out


class _Draft(Store):
    """The normal validation/journal path, with persistence confined to memory."""
    def __init__(self, folder):
        super().__init__(folder, initialize_git=False)
        self.content = self.path.read_bytes()

    def raw(self):
        return self.content

    def _persist(self, data, user, message):
        counters = self._counters(self.load())
        for prefix, value in self._counters(data).items():
            counters[prefix] = max(counters.get(prefix, 0), value)
        data['id_counters'] = counters
        self.content = (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()
        return None


def _references(value, names):
    if isinstance(value, dict):
        if set(value) == {'$ref'}:
            name = value['$ref']
            if not isinstance(name, str) or name not in names:
                raise SaveError('Unknown batch reference: ' + str(name), 422)
            return names[name]
        return {k: _references(v, names) for k, v in value.items()}
    if isinstance(value, list):
        return [_references(v, names) for v in value]
    return value


def atomic_apply(folder, requests, author='gene apply', login='cli', dry_run=False, if_version=None):
    """One locked preview, one durable save/commit, or no changes to archive data.

    `as` names a new record for subsequent {"$ref": "name"} values. Preview
    consumes IDs in memory only. Each intermediate operation must remain valid.
    """
    import re
    from .locking import site_lock
    with site_lock(folder):
        draft = _Draft(folder)
        version = draft.version()
        if if_version is not None and if_version != version:
            return [{'ok': False, 'status': 409, 'error': 'Archive changed; preview the batch again.',
                     'version': version, 'atomic': True}]
        user = {'name': login, 'display': author, 'role': 'editor'}
        results, names = [], {}
        index = 0
        try:
            for index, req in enumerate(requests):
                if not isinstance(req, dict):
                    raise SaveError('Each batch operation must be an object', 400)
                name = req.get('as')
                if name is not None and (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) or name in names):
                    raise SaveError('Batch aliases must be unique identifiers', 422)
                result = run_one(draft, user, _references(req, names))
                if name is not None:
                    if not result.get('id'):
                        raise SaveError('Only records can have a batch alias', 422)
                    names[name] = result['id']
                results.append(result)
            commit = None
            if draft.version() != version and not dry_run:
                store = Store(folder)
                commit = store._persist(draft.load(), user, f'Пакет из {len(requests)} правок / Batch of {len(requests)} changes')
            return [dict(r, ok=True, atomic=True, dry_run=dry_run, commit=commit,
                         base_version=version, version=draft.version()) for r in results]
        except (SaveError, ValueError, TypeError, KeyError) as error:
            extra = error.extra if isinstance(error, SaveError) else {}
            return [{'ok': False, 'atomic': True, 'failed_index': index, 'error': str(error),
                     'status': error.status if isinstance(error, SaveError) else 400,
                     'rolled_back': not extra.get('saved', False), **extra}]
