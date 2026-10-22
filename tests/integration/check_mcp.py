"""Optional consumer check: pip install genealogy-mcp==0.7.0, then run this file.
Only a disposable invented site is created; no user configuration is changed.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from gene_archive import cli
from genealogy_mcp import project

with tempfile.TemporaryDirectory(prefix='gene-mcp-contract-') as temp:
    folder = Path(temp) / 'site'
    with contextlib.redirect_stdout(io.StringIO()):
        cli.main(['init', str(folder), '--lang', 'en'])
    os.environ['GENE_CMD'] = f'{sys.executable} -m gene_archive.cli'
    os.environ['GENE_AUTHOR'] = 'Integration tester'
    os.environ['GENEALOGY_MCP_HOME'] = str(Path(temp) / 'memory')
    os.environ['GENEALOGY_MCP_SITE_BUILD'] = '1'
    site = str(folder)
    before = (folder / 'family_tree.json').read_bytes()
    preview = project.upsert(site, 'source', {'title': 'Invented register', 'locator': 'Test file, folio 1'}, dry_run=True)
    assert preview['dry_run'] and (folder / 'family_tree.json').read_bytes() == before
    source = project.upsert(site, 'source', {'title': 'Invented register', 'locator': 'Test file, folio 1'})
    assert source['commit']
    person = project.upsert(site, 'person', {'given_names': 'Invented', 'surname': 'Person', 'birth': {'date': '1900-01-02'}}, source_ids=['S1'])
    pid = person['id']
    project.upsert(site, 'person', {'id': pid, 'birth': {'date': '1900-01-03'}}, reason='PRIVATE_TEST_REASON')
    project.log(site, 'Private test search', 'PRIVATE_TEST_RESULT')
    data = json.loads((folder / 'family_tree.json').read_text())
    assert any(x.get('person_id') == pid for x in data['corrections'])
    assert any(x.get('result') == 'PRIVATE_TEST_RESULT' for x in data['research_log'])
    public = (folder / '_site/data.json').read_text()
    assert 'PRIVATE_TEST_REASON' not in public and 'PRIVATE_TEST_RESULT' not in public
    assert (folder / '_site/index.html').is_file()
    assert len(subprocess.check_output(['git', 'log', '--format=%H'], cwd=folder).splitlines()) >= 5
    try:
        project.upsert(site, 'person', {'id': pid, 'birth': {'date': '31.02.1900'}})
    except ValueError:
        pass
    else:
        raise AssertionError('Invalid date was accepted')
print('OK: released MCP consumer — preview, save, logs, Git, build, privacy, invalid date')
