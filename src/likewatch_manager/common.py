"""Bounded data, atomic records, canonical ownership, and OS-held locks."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile


class ManagerError(RuntimeError):
    pass


def read_bytes(path, limit=1_000_000):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ManagerError('Metadata exceeds size limit')
    return raw


def read_json(path, limit=1_000_000):
    return json.loads(read_bytes(path, limit))


def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(data))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def owned(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ManagerError('Deployment path escapes installation')
    return path


def identifier(value, pattern=r'[a-f0-9]{64}'):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ManagerError('Invalid deployment identifier')
    return value


@contextmanager
def locked(path):
    """Kernel lock survives stale files and is released on process death."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b'0'); stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ManagerError('Another LiKeWatch process owns this operation') from None
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ManagerError('Another LiKeWatch process owns this operation') from None
        yield
    finally:
        stream.close()


def platform_id():
    import platform
    if sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64'):
        return 'win-64'
    if sys.platform == 'darwin' and platform.machine() == 'arm64':
        return 'osx-arm64'
    raise ManagerError('Supported targets are Windows x64 and macOS Apple Silicon')
