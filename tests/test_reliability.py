"""Regressions from the audit: invented data, disposable site folders only."""
import contextlib
import io
import json
import multiprocessing
import subprocess
import tempfile
import unittest
from pathlib import Path

from gene_archive import build, cli, config
from gene_archive.apply import apply
from gene_archive.editor import Store
from gene_archive.validate import parse_date

USER = {'name': 'tester', 'display': 'Test editor'}


def competing_save(folder, pid, start, queue):
    Store(folder)
    start.wait(10)
    result = apply(folder, [{'kind': 'person', 'record': {'id': pid, 'notes': ['edited ' + pid]}}])[0]
    queue.put(result['ok'])


class Reliability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = Path(self.tmp.name) / 'site'
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(['init', str(self.site), '--lang', 'en'])

    def tearDown(self):
        self.tmp.cleanup()

    def tree(self):
        return json.loads((self.site / 'family_tree.json').read_text())

    def test_build_rejects_source_root_ancestor_and_input_subdirectory(self):
        before = (self.site / 'family_tree.json').read_bytes()
        for output in (self.site, self.site.parent, self.site / 'sources', self.site / 'content', self.site / '.git'):
            with self.subTest(output=output), self.assertRaises(build.BuildError):
                build.build(self.site, output)
            self.assertEqual((self.site / 'family_tree.json').read_bytes(), before)

    def test_build_does_not_delete_unrelated_old_or_build_directories(self):
        for suffix in ('.old', '.build'):
            other = self.site / ('_site' + suffix)
            other.mkdir()
            (other / 'keep').write_text('unrelated')
        build.build(self.site)
        build.build(self.site)
        for suffix in ('.old', '.build'):
            self.assertEqual((self.site / ('_site' + suffix) / 'keep').read_text(), 'unrelated')

    def test_private_and_unreviewed_journals_stay_out_of_public_payload(self):
        apply(self.site, [{'kind': 'person', 'record': {'id': 'I1', 'birth': {'date': '1990-05-16'}}, 'reason': 'PRIVATE_REASON'}])
        data = self.tree()
        data['research_log'].extend([
            {'date': '2026-10-22', 'action': 'lookup', 'result': 'UNREVIEWED_PRIVATE'},
            {'date': '2026-10-22', 'action': 'reviewed', 'result': 'PUBLIC_REVIEWED', 'visibility': 'public'},
        ])
        (self.site / 'family_tree.json').write_text(json.dumps(data))
        out = build.build(self.site)['out']
        payload = (out / 'data.json').read_text()
        self.assertNotIn('PRIVATE_REASON', payload)
        self.assertNotIn('UNREVIEWED_PRIVATE', payload)
        self.assertIn('PUBLIC_REVIEWED', payload)
        self.assertIn('PRIVATE_REASON', json.dumps(self.tree()))
        cfg = config.load(self.site)
        cfg['privacy']['hide_living'] = False
        self.assertIn('UNREVIEWED_PRIVATE', json.dumps(build.public_data(cfg, data)[0]))

    def test_ids_are_not_reused_after_delete_or_restore(self):
        a = apply(self.site, [{'kind': 'person', 'record': {'given_names': 'First'}}])[0]
        store = Store(self.site)
        old = store.history()[-1]['commit']
        self.assertTrue(apply(self.site, [{'op': 'delete', 'kind': 'person', 'id': a['id']}])[0]['ok'])
        b = apply(self.site, [{'kind': 'person', 'record': {'given_names': 'Second'}}])[0]
        self.assertNotEqual(a['id'], b['id'])
        Store(self.site).restore(USER, old)
        c = apply(self.site, [{'kind': 'person', 'record': {'given_names': 'After restore'}}])[0]
        self.assertNotIn(c['id'], (a['id'], b['id']))

    def test_empty_family_can_be_deleted_but_real_references_are_checked(self):
        f = apply(self.site, [{'kind': 'family', 'record': {'partners': [], 'children': []}}])[0]
        self.assertTrue(apply(self.site, [{'op': 'delete', 'kind': 'family', 'id': f['id']}])[0]['ok'])

    def test_failed_git_commit_rolls_back_data_and_staging(self):
        store = Store(self.site)
        before = store.raw()
        unrelated = self.site / 'unrelated.txt'
        unrelated.write_text('keep staged')
        subprocess.run(['git', 'add', 'unrelated.txt'], cwd=self.site, check=True)
        index = subprocess.check_output(['git', 'diff', '--cached', '--binary'], cwd=self.site)
        hook = self.site / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o755)
        r = apply(self.site, [{'kind': 'person', 'record': {'given_names': 'Must not save'}}])[0]
        self.assertFalse(r['ok'])
        self.assertEqual(store.raw(), before)
        self.assertEqual(subprocess.check_output(['git', 'diff', '--cached', '--binary'], cwd=self.site), index)

    def test_two_store_instances_cannot_enter_write_section_together(self):
        from gene_archive import locking
        a, b = Store(self.site), Store(self.site)
        self.assertIs(a.lock, b.lock)
        self.assertIsNotNone(locking)

    def test_two_processes_preserve_different_records(self):
        apply(self.site, [{'kind': 'person', 'record': {'given_names': 'Second'}}])
        ctx = multiprocessing.get_context('spawn')
        event, queue = ctx.Event(), ctx.Queue()
        processes = [ctx.Process(target=competing_save, args=(str(self.site), pid, event, queue)) for pid in ('I1', 'I2')]
        for p in processes: p.start()
        event.set()
        try:
            for p in processes:
                p.join(25)
                self.assertEqual(p.exitcode, 0)
            self.assertTrue(queue.get(timeout=3)); self.assertTrue(queue.get(timeout=3))
            self.assertTrue(all(p.get('notes') == ['edited ' + p['id']] for p in self.tree()['people']))
        finally:
            for p in processes:
                if p.is_alive(): p.terminate(); p.join()
            queue.close()

    def test_date_bounds_and_reversed_ranges(self):
        for value in ('00 JAN 1900', '0 JAN 1900', 'BET 1910 AND 1900', 'FROM 1910 TO 1900', '000 JAN 1900', '31 FEB 1900'):
            self.assertIsNone(parse_date(value), value)
        for value in ('1 JAN 1900', 'BET MAR 1900 AND 1900', 'FROM 1900 TO DEC 1900'):
            self.assertEqual(parse_date(value), 1900, value)

    def test_research_resources_and_coverage_apply_dry_run_update_delete(self):
        resource = {'name': 'Invented archive', 'url': 'https://example.org'}
        preview = apply(self.site, [{'kind': 'research_resources', 'record': resource}], dry_run=True)[0]
        self.assertTrue(preview['ok'])
        self.assertNotIn('research_resources', self.tree())
        r = apply(self.site, [{'kind': 'research_resources', 'record': resource}])[0]
        self.assertEqual(r['id'], 'R1')
        c = apply(self.site, [{'kind': 'coverage', 'record': {'parish': 'Invented parish', 'resource_id': 'R1', 'entries': [
            {'year': 1858, 'part': 'revisions', 'status': 'complete'},
            {'year': 1859, 'part': 'confessions', 'status': 'partial', 'up_to': 'household 4'}]}}])[0]
        self.assertTrue(c['ok'], c)
        self.assertEqual(c['id'], 'C1')
        refused = apply(self.site, [{'op': 'delete', 'kind': 'research_resources', 'id': 'R1'}])[0]
        self.assertFalse(refused['ok'])  # coverage still refers to it
        self.assertTrue(apply(self.site, [{'op': 'delete', 'kind': 'coverage', 'id': 'C1'}])[0]['ok'])
        self.assertTrue(apply(self.site, [{'op': 'delete', 'kind': 'research_resources', 'id': 'R1'}])[0]['ok'])

    def test_legacy_coverage_gets_id_only_on_explicit_edit_and_detects_conflict(self):
        data = self.tree()
        old = {'parish': 'Legacy parish', 'entries': [{'year': 1858, 'part': 'births', 'status': 'partial', 'up_to': 'No. 4'}]}
        data['coverage'] = [old]
        (self.site / 'family_tree.json').write_text(json.dumps(data))
        refused = apply(self.site, [{'kind': 'coverage', 'base': old, 'record': {'id': 'C99'}}])[0]
        self.assertFalse(refused['ok'])
        self.assertEqual(self.tree()['coverage'], [old])
        r = apply(self.site, [{'kind': 'coverage', 'base': old, 'record': {'entries': [{'year': 1858, 'part': 'births', 'status': 'complete'}]}}])[0]
        self.assertTrue(r['ok'], r)
        self.assertEqual(self.tree()['coverage'][0]['id'], 'C1')
        self.assertFalse(apply(self.site, [{'kind': 'coverage', 'base': old, 'record': {'parish': 'stale'}}])[0]['ok'])

    def test_unrelated_output_directory_is_not_replaced(self):
        target = Path(self.tmp.name) / 'unrelated'
        target.mkdir(); (target / 'keep').write_text('keep')
        with self.assertRaises(build.BuildError): build.build(self.site, target)
        self.assertEqual((target / 'keep').read_text(), 'keep')

    def test_explicit_public_log_and_private_default(self):
        requests = [{'op': 'log', 'action': 'Reviewed', 'result': 'Public result', 'visibility': 'public'},
                    {'op': 'log', 'action': 'Not reviewed', 'result': 'Private result'}]
        self.assertTrue(all(r['ok'] for r in apply(self.site, requests)))
        public, _ = build.public_data(config.load(self.site), self.tree())
        self.assertEqual([r['result'] for r in public['research_log']], ['Public result'])
        self.assertFalse(apply(self.site, [{'op': 'log', 'action': 'a', 'result': 'b', 'visibility': 'bad'}])[0]['ok'])

    def test_failed_log_and_upload_commits_leave_no_changes(self):
        from test_editor import tiny_png
        store = Store(self.site)
        before = store.raw()
        hook = self.site / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o755)
        result = apply(self.site, [{'op': 'log', 'action': 'lookup', 'result': 'not saved'}])[0]
        self.assertFalse(result['ok'])
        self.assertEqual(store.raw(), before)
        with self.assertRaises(ValueError): store.upload(USER, 'new.png', tiny_png())
        self.assertEqual(list((self.site / 'sources').iterdir()), [])
        self.assertEqual(list(self.site.glob('.gene-rollback-*')), [])

    def test_failed_build_swap_preserves_previous_output(self):
        from unittest.mock import patch
        output = build.build(self.site)['out']
        original = (output / 'data.json').read_bytes()
        rename = Path.rename
        def refuse_new_output(path, target):
            if '-build-' in path.name and Path(target) == output:
                raise OSError('injected swap failure')
            return rename(path, target)
        with patch.object(Path, 'rename', refuse_new_output), self.assertRaises(OSError):
            build.build(self.site)
        self.assertEqual((output / 'data.json').read_bytes(), original)

    def test_reliability_fields_pass_schema(self):
        from test_schema import TREE, check
        apply(self.site, [{'kind': 'person', 'record': {'given_names': 'Second'}}])
        apply(self.site, [{'op': 'log', 'action': 'search', 'result': 'nothing', 'visibility': 'public'}])
        self.assertEqual(check(self.tree(), TREE, TREE), [])

    def test_dry_run_does_not_initialise_git_history(self):
        result = apply(self.site, [{'kind': 'person', 'record': {'given_names': 'Preview'}}], dry_run=True)[0]
        self.assertTrue(result['ok'])
        self.assertFalse((self.site / '.git').exists())
