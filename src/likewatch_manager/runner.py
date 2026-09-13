"""Bind one immutable source/environment context before importing application code."""
import json
import os
from pathlib import Path
import sys


def main():
    context_file = Path(sys.argv[1]).resolve()
    data = json.loads(context_file.read_text(encoding='utf-8'))
    source = Path(data['source_root']).resolve()
    sys.path.insert(0, str(source / 'src'))
    os.environ['LIKEWATCH_CONTEXT'] = json.dumps(data)
    import likewatch
    if not Path(likewatch.__file__).resolve().is_relative_to(source / 'src' / 'likewatch'):
        raise RuntimeError('Application imported from an unexpected source tree')
    sys.argv = [str(source / 'src/likewatch/__main__.py'), *sys.argv[2:]]
    from likewatch.__main__ import main as launch
    return launch()


if __name__ == '__main__':
    raise SystemExit(main())
