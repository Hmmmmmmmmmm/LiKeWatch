"""Public maintenance commands with structured, credential-free diagnostics."""
import argparse
import json
from pathlib import Path
import sys
from .common import ManagerError, locked
from .deployment import Manager


def main(argv=None):
    parser = argparse.ArgumentParser(description='LiKeWatch installation manager')
    parser.add_argument('--root', required=True)
    parser.add_argument('command', nargs='?', default='run', choices=['run','status','doctor','check','prepare','validate','apply','rollback','repair','cleanup'])
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    parser.add_argument('--json', action='store_true')
    args, unknown = parser.parse_known_args(argv)
    extra = args.arguments + unknown
    target = None
    if args.command != 'run':
        extra = [value for value in extra if value != '--json']
        if len(extra) > 1:
            parser.error('This maintenance command accepts at most one target')
        target = extra[0] if extra else None
        extra = []
    try:
        manager = Manager(args.root)
        command = args.command
        if command in ('run', 'apply', 'rollback'):
            from .supervisor import run
            return run(manager, extra, transaction=target if command == 'apply' else None, rollback=command == 'rollback')
        if command in ('status', 'doctor'):
            result = manager.doctor()
        elif command == 'check':
            manifest, _ = manager.releases.check()
            from packaging.version import Version
            result = {'status': 'update-available' if Version(manifest['version']) > Version(manager.state()['active']['version']) else 'up-to-date', 'version': manifest['version'], 'notes': manifest.get('notes', '')}
        elif command == 'prepare':
            result = manager.prepare(target)
        elif command == 'validate':
            result = manager.validate_plan(target)
        elif command == 'repair':
            result = manager.repair()
        else:
            # Explicit preview only. Automatic deletion is intentionally conservative in protocol 1.
            with locked(manager.root / 'state/run.lock'), locked(manager.root / 'state/update.lock'):
                state = manager.state()
                protected = {d['commit'] for d in (state['active'], state.get('previous')) if d}
                result = {'status': 'retention-preview', 'retained': sorted(protected), 'detail': 'Source/environment deletion is not automatic; retained candidates support recovery.'}
        print(json.dumps({'ok': True, 'result': result}))
        return 0
    except (ManagerError, OSError, ValueError, KeyError, TypeError) as error:
        message = str(error) if isinstance(error, ManagerError) else 'Invalid or inaccessible installation metadata; run doctor or reinstall at a new prefix'
        print(json.dumps({'ok': False, 'error': message}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
