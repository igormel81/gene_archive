"""Private, portable backups with checksummed files and verified staged restores."""
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import tempfile

from . import __version__
from .locking import site_lock


class BackupError(ValueError):
    pass


SKIP = {'.git', '.gene-state', '.cache', '__pycache__', '.venv', 'node_modules', '.DS_Store'}


def copy_source(source, target, state=None):
    """Snapshot all original files, including ignored documents; no symbolic links."""
    source, target = Path(source).resolve(), Path(target)
    state = Path(state).resolve() if state else source / '.gene-state'
    target.mkdir(parents=True, exist_ok=True)

    def visit(folder, dest):
        for path in sorted(folder.iterdir()):
            generated = path.is_dir() and (path.name == '_site' or path.name.startswith('_site.'))
            if path.name in SKIP or generated or path.name.startswith(('.gene-write-', '.gene-rollback-')) or path == state:
                continue
            if path.is_symlink():
                raise BackupError('Symbolic links are not portable; copy their files into the archive: ' + str(path))
            out = dest / path.name
            if path.is_dir():
                if (path / '.gene-archive-output').is_file():
                    continue
                out.mkdir()
                visit(path, out)
            elif path.is_file():
                shutil.copy2(path, out)
            else:
                raise BackupError('Unsupported special file: ' + str(path))
    visit(source, target)


def _sqlite_copy(source, target):
    # SQLite's backup API includes committed WAL content without copying a live WAL.
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=10) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise BackupError('SQLite integrity check failed: ' + source.name)
    os.chmod(target, 0o600)


def _snapshot_state(source, target):
    target.mkdir()
    if not source.exists():
        return
    if source.is_symlink() or not source.is_dir():
        raise BackupError('State must be a directory, not a link')
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise BackupError('State contains a symbolic link: ' + str(path))
        if path.name == 'archive.lock' or path.name.endswith(('-wal', '-shm', '-journal')):
            continue
        dest = target / path.relative_to(source)
        if path.is_dir():
            dest.mkdir(exist_ok=True)
        elif path.is_file():
            if path.suffix == '.db':
                _sqlite_copy(path, dest)
            else:
                shutil.copy2(path, dest)
        else:
            raise BackupError('State contains a special file: ' + str(path))


def _git_snapshot(source, target):
    if not (source / '.git').exists():
        return None
    if not shutil.which('git'):
        raise BackupError('Git is required to back up this archive history')
    def git(*args, check=True):
        return subprocess.run(['git', *args], cwd=source, capture_output=True, check=check, timeout=120)
    root = Path(git('rev-parse', '--show-toplevel').stdout.decode().strip()).resolve()
    if root != source:
        raise BackupError('Archive must be the root of its Git repository')
    head = git('rev-parse', '--verify', 'HEAD', check=False)
    if head.returncode:
        return None
    git('bundle', 'create', str(target / 'history.bundle'), '--all', 'HEAD')
    branch = git('symbolic-ref', '--short', 'HEAD', check=False)
    return {'head': head.stdout.decode().strip(), 'branch': branch.stdout.decode().strip() or None}


def _digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def create(folder, output, state=None):
    source, output = Path(folder).resolve(), Path(output).resolve()
    if state is not None and not Path(state).is_dir():
        raise BackupError('The explicitly selected state folder does not exist')
    state = Path(state).resolve() if state else source / '.gene-state'
    if source.is_relative_to(state):
        raise BackupError('State must not contain the source folder')
    if not (source / 'family_tree.json').is_file():
        raise BackupError('family_tree.json not found')
    if output.is_relative_to(source) or output.is_relative_to(state):
        raise BackupError('Save the backup outside the source and state directories')
    if output.exists():
        raise BackupError('Backup output already exists; choose a new filename')
    with site_lock(source), tempfile.TemporaryDirectory(prefix='gene-backup-') as temp:
        stage = Path(temp)
        copy_source(source, stage / 'source', state)
        _snapshot_state(state, stage / 'state')
        history = _git_snapshot(source, stage)
        files = {}
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                files[path.relative_to(stage).as_posix()] = {'size': path.stat().st_size,
                    'sha256': _digest(path), 'mode': stat.S_IMODE(path.stat().st_mode) & 0o777}
        manifest = {'format': 'gene-archive-backup', 'version': 1, 'engine_version': __version__,
                    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'history': history, 'files': files,
                    'directories': [p.relative_to(stage).as_posix() for p in sorted(stage.rglob('*')) if p.is_dir()]}
        if any(not _safe_name(rel) for rel in [*files, *manifest['directories']]):
            raise BackupError('An input filename is not portable; rename it before backup')
        meta = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
        if len(files) >= 100000 or len(manifest['directories']) > 100000 or len(meta) > 16 * 1024 * 1024 or sum(f['size'] for f in files.values()) > 100 * 1024 ** 3:
            raise BackupError('Backup exceeds the supported restore limits')
        (stage / 'manifest.json').write_bytes(meta)
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.gene-backup-', dir=output.parent)
        os.close(fd)
        try:
            with tarfile.open(name, 'w:gz') as tar:
                for rel in ['manifest.json', *files]:
                    tar.add(stage / rel, arcname=rel, recursive=False)
            # Never clobber an existing backup, including a concurrent creator's output.
            os.link(name, output)
        finally:
            Path(name).unlink(missing_ok=True)
    return {'backup': str(output), 'files': len(files), 'history': bool(history),
            'private': True, 'state_included': any(rel.startswith('state/') for rel in files)}


def _safe_name(name):
    p = PurePosixPath(name)
    return bool(p.parts) and not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name and p.as_posix() == name


def _unpack(archive, stage):
    with tarfile.open(archive, 'r:gz') as tar:
        members = {}
        for member in tar:
            if not member.isfile() or not _safe_name(member.name) or member.name in members:
                raise BackupError('Unsafe or duplicate backup entry: ' + member.name)
            members[member.name] = member
            if len(members) > 100000:
                raise BackupError('Backup contains too many files')
        meta = members.get('manifest.json')
        if meta is None or meta.size > 16 * 1024 * 1024:
            raise BackupError('Missing or oversized manifest')
        manifest = json.load(tar.extractfile(meta))
        if not isinstance(manifest, dict):
            raise BackupError('Manifest must be an object')
        if manifest.get('format') != 'gene-archive-backup' or manifest.get('version') != 1:
            raise BackupError('Unsupported backup format')
        files = manifest.get('files')
        if not isinstance(files, dict) or set(members) != set(files) | {'manifest.json'}:
            raise BackupError('Manifest does not match archive files')
        if 'source/family_tree.json' not in files:
            raise BackupError('Backup has no family_tree.json')
        if sum(m.size for m in members.values()) > 100 * 1024 ** 3:
            raise BackupError('Backup exceeds the 100 GiB restore limit')
        directories = manifest.get('directories', [])
        if not isinstance(directories, list) or not all(isinstance(p, str) for p in directories) or len(directories) > 100000:
            raise BackupError('Invalid directory inventory')
        for rel in directories:
            parts = PurePosixPath(rel).parts
            if not _safe_name(rel) or parts[0] not in ('source', 'state') or '.git' in parts or '.gene-state' in parts:
                raise BackupError('Invalid directory: ' + str(rel))
            (stage / rel).mkdir(parents=True, exist_ok=True)
        for rel, info in files.items():
            parts = PurePosixPath(rel).parts
            if not _safe_name(rel) or not (parts[0] in ('source', 'state') or rel == 'history.bundle'):
                raise BackupError('Invalid manifest path: ' + rel)
            # A repository/config supplied by an archive must never be executed on restore.
            if '.git' in parts or '.gene-state' in parts or (parts[0] == 'state' and 'archive.lock' in parts):
                raise BackupError('Reserved backup path: ' + rel)
            member = members[rel]
            if not isinstance(info, dict) or info.get('size') != member.size:
                raise BackupError('Size mismatch: ' + rel)
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as src, dest.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            if _digest(dest) != info.get('sha256'):
                raise BackupError('Checksum mismatch: ' + rel)
            mode = info.get('mode', 0o600)
            if type(mode) is not int or not 0 <= mode <= 0o777:
                raise BackupError('Invalid file permissions: ' + rel)
            os.chmod(dest, mode)
    return manifest


def _restore_history(stage, manifest):
    history = manifest.get('history')
    bundle = stage / 'history.bundle'
    source = stage / 'source'
    if history is not None and not isinstance(history, dict):
        raise BackupError('Invalid saved Git metadata')
    if not history:
        if bundle.exists():
            raise BackupError('Unexpected Git bundle')
        return
    if not bundle.is_file() or not shutil.which('git'):
        raise BackupError('Git and its history bundle are required for this restore')
    def git(*args):
        return subprocess.run(['git', *args], cwd=source, capture_output=True, check=True, timeout=120)
    git('init', '-q')
    git('bundle', 'verify', str(bundle))
    git('fetch', '-q', '--update-head-ok', str(bundle), 'refs/*:refs/*')
    git('fetch', '-q', str(bundle), 'HEAD')
    head = history.get('head')
    import re
    if not isinstance(head, str) or not re.fullmatch(r'[0-9a-f]{40,64}', head):
        raise BackupError('Invalid saved Git revision')
    git('cat-file', '-e', head + '^{commit}')
    branch = history.get('branch')
    if branch:
        git('check-ref-format', '--branch', branch)
        git('symbolic-ref', 'HEAD', 'refs/heads/' + branch)
    if not branch:
        git('update-ref', '--no-deref', 'HEAD', head)
    git('reset', '--mixed', head)  # keep the working files, including uncommitted changes


def _reset_sessions(state):
    path = state / 'editor.db'
    if path.exists():
        with sqlite3.connect(path) as db:
            for table in ('sessions', 'invites'):
                if db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (table,)).fetchone():
                    db.execute('DELETE FROM ' + table)
    secret = state / 'cookie-secret'
    secret.write_bytes(secrets.token_bytes(32))
    os.chmod(secret, 0o600)


def restore(archive, folder=None, check=False):
    destination = Path(folder).absolute() if folder else None
    if not check and destination is None:
        raise BackupError('Choose a new destination folder, or use --check')
    if destination is not None and (destination.exists() or destination.is_symlink()):
        raise BackupError('Restore destination must not exist')
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gene-restore-', dir=destination.parent if destination else None) as temp:
        stage = Path(temp)
        manifest = _unpack(archive, stage)
        _restore_history(stage, manifest)
        source = stage / 'source'
        state = stage / 'state'
        state.mkdir(exist_ok=True)
        for path in state.rglob('*.db'):
            with sqlite3.connect(path) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise BackupError('Restored database is corrupt: ' + path.name)
        from .build import build, BuildError
        _reset_sessions(state)
        state.rename(source / '.gene-state')
        try:
            built = build(source)
        except BuildError as error:
            raise BackupError(str(error)) from error
        result = {'ok': True, 'checked': True, 'files': len(manifest['files']), 'history': bool(manifest.get('history')),
                  'people': built['people'], 'warnings': built['warnings'], 'sessions_reset': True}
        if not check:
            # Publish only the completely verified archive. No existing folder is overwritten.
            source.chmod(0o700)
            destination.mkdir()  # reserve the name; fail even if another creator made an empty directory
            try:
                source.rename(destination)
            except BaseException:
                destination.rmdir()
                raise
            result.update(folder=str(destination), state=str(destination / '.gene-state'))
        return result
