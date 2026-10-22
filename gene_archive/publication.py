"""Preview the exact build in isolation, with publication decisions and file hashes."""
import json
import hashlib
from pathlib import Path
import tempfile

from .backup import copy_source, _digest
from .build import build, load_site, public_data
from .locking import site_lock
from .privacy import journal_exclusion


def preview(folder):
    source = Path(folder).resolve()
    with site_lock(source), tempfile.TemporaryDirectory(prefix='gene-publication-') as temp:
        snapshot = Path(temp) / 'archive'
        copy_source(source, snapshot)
        cfg, raw = load_site(snapshot)
        public, living = public_data(cfg, raw)
        built = build(snapshot)
        out = built['out']
        # Read the output too: the builder additionally removes mail metadata and adds previews.
        data = json.loads((out / 'data.json').read_text(encoding='utf-8'))
        people = {p['id']: p for p in data['people']}
        sources = {s['id']: s for s in data['sources']}
        decisions = []
        for person in raw['people']:
            published = people.get(person['id'], {})
            fields = sorted(k for k in person if k not in published or published[k] != person[k])
            decisions.append({'kind': 'person', 'id': person['id'], 'published': bool(published),
                              'restricted': person['id'] in living, 'redacted_fields': fields,
                              'reason': 'living_person' if person['id'] in living else 'public_record'})
        warnings = list(built['warnings'])
        for record in raw['sources']:
            published = sources.get(record['id'])
            reason = ('hidden_by_owner' if record.get('hidden') else 'merged_document' if record.get('merged_into')
                      else 'living_only_document' if published is None else 'public_record')
            fields = sorted(k for k in record if published is not None and k not in published)
            files = [record[k] for k in ('file', 'back') if record.get(k)]
            copied = [rel for rel in files if (out / rel).is_file()]
            decisions.append({'kind': 'source', 'id': record['id'], 'published': published is not None,
                              'reason': reason, 'redacted_fields': fields, 'files_in_output': copied})
            if published is None and copied:
                warnings.append('Unlisted document ' + record['id'] + ' is still copied by a content/media reference: ' + ', '.join(copied))
        journals = {kind: {'total': len(raw.get(kind, [])), 'published': len(public.get(kind, [])),
                           'hidden': len(raw.get(kind, [])) - len(public.get(kind, [])),
                           'rule': 'explicit_public_and_no_living_references' if cfg['privacy'].get('hide_living', True) else 'privacy_protection_disabled'}
                    for kind in ('corrections', 'research_log')}
        private_families = {f['id'] for f in raw.get('families', [])
                            if set(f.get('partners', []) + f.get('children', []) + f.get('adopted_children', [])) & living}
        for kind, summary in journals.items():
            summary['entries'] = []
            for index, entry in enumerate(raw.get(kind, [])):
                reason = journal_exclusion(entry, living, private_families) if cfg['privacy'].get('hide_living', True) else None
                summary['entries'].append({'index': index, 'published': reason is None, 'reason': reason or 'public_journal'})
        files = [{'path': path.relative_to(out).as_posix(), 'bytes': path.stat().st_size, 'sha256': _digest(path)}
                 for path in sorted(out.rglob('*')) if path.is_file()]
        warnings.append('Custom HTML, img/ and geo/ are published as supplied; review their contents manually.')
        return {'version': hashlib.sha256((snapshot / 'family_tree.json').read_bytes()).hexdigest()[:16],
                'hide_living': cfg['privacy'].get('hide_living', True), 'living_people': sorted(living),
                'decisions': decisions, 'journals': journals, 'files': files, 'warnings': warnings,
                'missing_translations': built['missing_translations']}


def text(report):
    from .messages import m
    lines = [m('Publication preview', 'Предпросмотр публикации') + ' — ' + report['version']]
    for row in report['decisions']:
        state = m('public', 'публикуется') if row['published'] else m('hidden', 'скрыто')
        line = f"{row['id']}: {state} ({row['reason']})"
        if row['redacted_fields']:
            line += m('; redacted fields: ', '; скрытые/изменённые поля: ') + ', '.join(row['redacted_fields'])
        lines.append(line)
    for kind, row in report['journals'].items():
        lines.append(f"{kind}: " + m(f"{row['published']} public, {row['hidden']} hidden", f"{row['published']} публикуется, {row['hidden']} скрыто"))
    lines.append(m(f"Files in output: {len(report['files'])}", f"Файлов в публикации: {len(report['files'])}"))
    lines.extend('! ' + warning for warning in report['warnings'])
    return '\n'.join(lines)
