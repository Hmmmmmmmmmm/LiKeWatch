"""Explicit resource and persistent-store context shared with spawned OCR workers."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys


@dataclass
class RuntimeContext:
    source_root: Path = field(default_factory=lambda: Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])))
    native_root: Path | None = None
    data_root: Path | None = None
    settings_file: Path | None = None
    log_root: Path | None = None
    test_mode: bool = False
    commit: str = 'development'
    environment_id: str = 'development'
    install_root: str = ''
    manager_python: str = ''
    session: str = ''
    nonce: str = ''
    transaction: str = ''
    health_file: str = ''
    request_file: str = ''
    activated_file: str = ''
    supervised: bool = False

    @classmethod
    def from_dict(cls, data):
        known = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        for key in ('source_root', 'native_root', 'data_root', 'settings_file', 'log_root'):
            if known.get(key):
                known[key] = Path(known[key]).resolve()
        return cls(**known)

    def export(self):
        return {key: str(value) if isinstance(value, Path) else value
                for key, value in self.__dict__.items()}

    def source(self, *parts):
        return self.source_root.joinpath(*parts)

    def native(self, name):
        return (self.native_root or self.source_root / 'assets') / name


_context = None


def context():
    global _context
    if _context is None:
        # One explicit process context is inherited by spawn; never read active deployment here.
        _context = RuntimeContext.from_dict(json.loads(os.environ.get('LIKEWATCH_CONTEXT', '{}')))
    return _context


def configure(value):
    global _context
    _context = value
    os.environ['LIKEWATCH_CONTEXT'] = json.dumps(value.export())
