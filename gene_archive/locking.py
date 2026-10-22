"""Shared reentrant locks for writers/builders, across threads and local processes."""
import hashlib
import os
import tempfile
import threading
from pathlib import Path

_REGISTRY = {}
_REGISTRY_LOCK = threading.Lock()


class FileLock:
    def __init__(self, path):
        self.path = path
        self.thread = threading.RLock()
        self.depth = 0
        self.handle = None

    def __enter__(self):
        self.thread.acquire()
        try:
            if self.depth == 0:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.handle = open(self.path, 'a+b')
                if os.name == 'nt':
                    import msvcrt
                    if self.path.stat().st_size == 0:
                        self.handle.write(b'0'); self.handle.flush()
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            self.depth += 1
            return self
        except BaseException:
            if self.handle is not None:
                self.handle.close(); self.handle = None
            self.thread.release()
            raise

    def __exit__(self, *exc):
        try:
            self.depth -= 1
            if self.depth == 0:
                try:
                    if os.name == 'nt':
                        import msvcrt
                        self.handle.seek(0)
                        msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                finally:
                    self.handle.close(); self.handle = None
        finally:
            self.thread.release()


def lock(path):
    path = Path(path).resolve()
    with _REGISTRY_LOCK:
        return _REGISTRY.setdefault(str(path), FileLock(path))


def site_lock(folder):
    return lock(Path(folder) / '.gene-state' / 'archive.lock')


def output_lock(output):
    key = hashlib.sha256(str(Path(output).resolve()).encode()).hexdigest()
    return lock(Path(tempfile.gettempdir()) / 'gene-archive-build-locks' / (key + '.lock'))
