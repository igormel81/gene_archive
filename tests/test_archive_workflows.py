"""Disposable invented archives: backup/restore, publication and atomic edits."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest

from gene_archive import backup, cli, publication
from gene_archive.apply import apply, atomic_apply
from gene_archive.editor import Accounts, Store


class Workflows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.site = self.root / 'site'
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(['init', str(self.site), '--lang', 'en'])
        self.archive = self.root / 'backup.tar.gz'

    def tearDown(self):
        self.temp.cleanup()

    def tree(self, folder=None):
        return json.loads(((folder or self.site) / 'family_tree.json').read_text())

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.site).decode().strip()

    def requests(self):
        return [
            {'kind': 'source', 'as': 'register', 'record': {'title': 'Invented register', 'kind': 'church_record'}},
            {'kind': 'person', 'as': 'child', 'record': {'given_names': 'Anna', 'surname': 'Test', 'birth': {'date': '1900-01-02', 'source_ids': [{'$ref': 'register'}]}}},
            {'kind': 'family', 'record': {'partners': ['I1'], 'children': [{'$ref': 'child'}], 'source_ids': [{'$ref': 'register'}]}},
        ]

    def test_atomic_dependent_preview_then_one_commit(self):
        store = Store(self.site)
        before, head = store.raw(), self.git('rev-parse', 'HEAD')
        preview = atomic_apply(self.site, self.requests(), dry_run=True)
        self.assertTrue(all(r['ok'] for r in preview), preview)
        self.assertEqual(before, store.raw())
        self.assertEqual(head, self.git('rev-parse', 'HEAD'))
        result = atomic_apply(self.site, self.requests(), if_version=preview[0]['base_version'])
        self.assertTrue(all(r['ok'] for r in result), result)
        self.assertEqual(len({r['commit'] for r in result}), 1)
        self.assertEqual(self.git('rev-list', '--count', head + '..HEAD'), '1')
        self.assertEqual(self.tree()['families'][0]['children'], ['I2'])
        self.assertEqual(self.tree()['people'][1]['birth']['source_ids'], ['S1'])

    def test_invalid_batch_and_reference_write_nothing(self):
        before = (self.site / 'family_tree.json').read_bytes()
        for request in ({'kind': 'person', 'record': {'birth': {'date': '31.02.1900'}}},
                        {'kind': 'family', 'record': {'partners': [{'$ref': 'unknown'}]}}):
            result = atomic_apply(self.site, [self.requests()[0], request])
            self.assertFalse(result[0]['ok'], result)
            self.assertEqual(result[0]['failed_index'], 1)
            self.assertEqual(before, (self.site / 'family_tree.json').read_bytes())
            self.assertFalse((self.site / '.git').exists())

    def test_atomic_conflicts_and_failed_commit(self):
        store = Store(self.site)
        old = store.version()
        apply(self.site, [{'op': 'log', 'action': 'Test', 'result': 'Changed'}])
        result = atomic_apply(self.site, self.requests(), if_version=old)
        self.assertEqual(result[0]['status'], 409)
        before, head = store.raw(), self.git('rev-parse', 'HEAD')
        hook = self.site / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o755)
        result = atomic_apply(self.site, self.requests())
        self.assertFalse(result[0]['ok'])
        self.assertTrue(result[0]['rolled_back'])
        self.assertEqual(before, store.raw())
        self.assertEqual(head, self.git('rev-parse', 'HEAD'))

    def test_atomic_duplicate_aliases_and_bad_requests_are_rejected(self):
        for requests in ([self.requests()[0], self.requests()[0]], [None], [{'op': 'log', 'action': 'a', 'result': 'b', 'as': 'log'}]):
            result = atomic_apply(self.site, requests)
            self.assertFalse(result[0]['ok'], result)
        self.assertEqual(self.tree()['sources'], [])

    def test_backup_preserves_documents_state_history_and_uncommitted_files(self):
        self.assertTrue(all(r['ok'] for r in atomic_apply(self.site, self.requests())))
        (self.site / 'sources/doc.txt').write_text('Invented document')
        (self.site / 'content/story.html').write_text('<section id="a"><h2>Invented story</h2><p>Test.</p></section>')
        state = self.root / 'external-state'
        accounts = Accounts(state)
        with sqlite3.connect(accounts.path) as conn:
            conn.execute("INSERT INTO users(name,display,role,disabled,created_at) VALUES('tester','Tester','admin',0,'2026-10-22')")
            conn.execute("INSERT INTO sessions VALUES('token',1,'csrf','today',9999999999)")
            conn.execute("INSERT INTO invites VALUES('invite',1,9999999999)")
        with sqlite3.connect(state / 'comments.db') as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE comments(text TEXT)')
            conn.execute("INSERT INTO comments VALUES('Family comment')")
            conn.commit()
            (state / 'cookie-secret').write_bytes(b'old-secret')
            result = backup.create(self.site, self.archive, state)
        self.assertTrue(result['history'])
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
        checked = backup.restore(self.archive, check=True)
        self.assertTrue(checked['checked'])
        dest = self.root / 'restored'
        backup.restore(self.archive, dest)
        self.assertEqual(self.tree(), self.tree(dest))
        self.assertEqual((dest / 'sources/doc.txt').read_text(), 'Invented document')
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=dest).decode().strip(), self.git('rev-parse', 'HEAD'))
        self.assertEqual(subprocess.check_output(['git', 'show', 'HEAD:family_tree.json'], cwd=dest), subprocess.check_output(['git', 'show', 'HEAD:family_tree.json'], cwd=self.site))
        with sqlite3.connect(dest / '.gene-state/editor.db') as db:
            self.assertEqual(db.execute('SELECT name FROM users').fetchone()[0], 'tester')
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM invites').fetchone()[0], 0)
        with sqlite3.connect(dest / '.gene-state/comments.db') as db:
            self.assertEqual(db.execute('SELECT text FROM comments').fetchone()[0], 'Family comment')
        self.assertNotEqual((dest / '.gene-state/cookie-secret').read_bytes(), b'old-secret')
        self.assertTrue((dest / '_site/index.html').is_file())

    def test_backup_excludes_build_and_refuses_links_and_overwrites(self):
        (self.site / '_site').mkdir(); (self.site / '_site/secret').write_text('generated')
        backup.create(self.site, self.archive)
        with tarfile.open(self.archive) as tar:
            self.assertFalse(any('_site/' in m.name for m in tar))
        with self.assertRaises(backup.BackupError): backup.create(self.site, self.archive)
        with self.assertRaises(backup.BackupError): backup.create(self.site, self.site / 'backup.tar.gz')
        with self.assertRaises(backup.BackupError): backup.restore(self.archive, self.site)
        (self.site / 'sources/link').symlink_to(self.root / 'outside')
        with self.assertRaises(backup.BackupError): backup.create(self.site, self.root / 'other.tar.gz')

    def test_tampering_and_unsafe_archive_do_not_publish(self):
        backup.create(self.site, self.archive)
        altered = self.root / 'altered.tar.gz'
        with tarfile.open(self.archive) as src, tarfile.open(altered, 'w:gz') as dst:
            for m in src:
                content = src.extractfile(m).read()
                if m.name == 'source/family_tree.json': content = b'x' * len(content)
                dst.addfile(m, io.BytesIO(content))
        target = self.root / 'bad-restored'
        with self.assertRaises(backup.BackupError): backup.restore(altered, target)
        self.assertFalse(target.exists())
        for name in ('../escape', '/absolute', 'source/../../escape'):
            unsafe = self.root / 'unsafe.tar.gz'
            with tarfile.open(unsafe, 'w:gz') as dst:
                m = tarfile.TarInfo(name); m.size = 1
                dst.addfile(m, io.BytesIO(b'x'))
            with self.assertRaises(backup.BackupError): backup.restore(unsafe, target)
            self.assertFalse(target.exists())
        self.assertFalse((self.root / 'escape').exists())

    def test_restore_checks_data_before_publishing(self):
        data = self.tree(); data['root_person_id'] = 'I999'
        (self.site / 'family_tree.json').write_text(json.dumps(data))
        backup.create(self.site, self.archive)
        with self.assertRaises(backup.BackupError): backup.restore(self.archive, self.root / 'invalid')
        self.assertFalse((self.root / 'invalid').exists())

    def test_preview_matches_built_data_and_does_not_touch_source(self):
        (self.site / 'sources/hidden.txt').write_text('Hidden document')
        data = self.tree()
        data['sources'] = [{'id': 'S1', 'title': 'Hidden', 'kind': 'family_archive_document', 'hidden': True, 'file': 'sources/hidden.txt'},
                           {'id': 'S2', 'title': 'Public', 'kind': 'family_archive_document', 'email_subject': 'Private mail'}]
        data['people'][0]['birth'] = {'date': '2000-01-01'}
        data['research_log'] = [{'date': '2026-10-22', 'action': 'Secret', 'result': 'PRIVATE_TEXT'}]
        (self.site / 'family_tree.json').write_text(json.dumps(data))
        before = (self.site / 'family_tree.json').read_bytes()
        report = publication.preview(self.site)
        self.assertEqual(before, (self.site / 'family_tree.json').read_bytes())
        self.assertFalse((self.site / '_site').exists())
        self.assertFalse((self.site / '.git').exists())
        self.assertIn('birth', next(d for d in report['decisions'] if d['id'] == 'I1')['redacted_fields'])
        hidden = next(d for d in report['decisions'] if d['id'] == 'S1')
        self.assertFalse(hidden['published']); self.assertEqual(hidden['reason'], 'hidden_by_owner')
        self.assertIn('email_subject', next(d for d in report['decisions'] if d['id'] == 'S2')['redacted_fields'])
        self.assertEqual(report['journals']['research_log']['published'], 0)
        self.assertNotIn('PRIVATE_TEXT', json.dumps(report))
        self.assertNotIn('sources/hidden.txt', [f['path'] for f in report['files']])

    def test_preview_warns_about_custom_reference_to_hidden_document(self):
        (self.site / 'sources/hidden.txt').write_text('Hidden document')
        (self.site / 'content/story.html').write_text('<a href="sources/hidden.txt">A manual link</a>')
        data = self.tree(); data['sources'] = [{'id': 'S1', 'title': 'Hidden', 'kind': 'family_archive_document', 'hidden': True, 'file': 'sources/hidden.txt'}]
        (self.site / 'family_tree.json').write_text(json.dumps(data))
        report = publication.preview(self.site)
        self.assertTrue(any('S1' in w and 'content/media' in w for w in report['warnings']))
        self.assertIn('sources/hidden.txt', [f['path'] for f in report['files']])

    def test_backup_without_git_preserves_empty_directories(self):
        (self.site / 'sources/empty').mkdir()
        (self.site / '_site-notes.txt').write_text('Source notes')
        backup.create(self.site, self.archive)
        dest = self.root / 'restored'
        result = backup.restore(self.archive, dest)
        self.assertFalse(result['history'])
        self.assertFalse((dest / '.git').exists())
        self.assertTrue((dest / 'sources/empty').is_dir())
        self.assertEqual((dest / '_site-notes.txt').read_text(), 'Source notes')

    def test_detached_git_history_and_tags_are_portable(self):
        Store(self.site)
        self.git('tag', 'test-tag')
        self.git('checkout', '--detach', '-q')
        head = self.git('rev-parse', 'HEAD')
        backup.create(self.site, self.archive)
        dest = self.root / 'restored'
        backup.restore(self.archive, dest)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=dest).decode().strip(), head)
        self.assertEqual(subprocess.check_output(['git', 'rev-parse', 'test-tag'], cwd=dest).decode().strip(), head)
        self.assertNotEqual(subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=dest).returncode, 0)

    def test_cli_commands_and_atomic_exit_codes(self):
        requests = self.root / 'changes.json'
        requests.write_text(json.dumps(self.requests()))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(['apply', str(self.site), str(requests), '--atomic', '--dry-run', '--author', 'Tester'])
        self.assertEqual(code, 0)
        preview = json.loads(output.getvalue().splitlines()[0])
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(['apply', str(self.site), str(requests), '--atomic', '--if-version', preview['base_version'], '--author', 'Tester', '--build'])
        self.assertEqual(code, 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main(['publish-preview', str(self.site), '--json'])
        self.assertTrue(json.loads(output.getvalue())['files'])
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(['backup', str(self.site), '-o', str(self.archive)])
            cli.main(['restore', str(self.archive), '--check'])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(['apply', str(self.site), str(requests), '--atomic', '--if-version', preview['base_version'], '--author', 'Tester'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['status'], 409)

    def test_archive_links_and_duplicate_members_are_rejected(self):
        for link_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with tarfile.open(self.archive, 'w:gz') as dst:
                member = tarfile.TarInfo('source/link'); member.type = link_type; member.linkname = '../outside'
                dst.addfile(member)
            with self.assertRaises(backup.BackupError): backup.restore(self.archive, check=True)
        with tarfile.open(self.archive, 'w:gz') as dst:
            for _ in range(2):
                member = tarfile.TarInfo('manifest.json'); member.size = 2
                dst.addfile(member, io.BytesIO(b'{}'))
        with self.assertRaises(backup.BackupError): backup.restore(self.archive, check=True)
