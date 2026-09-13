"""Exercise signed updates and rollback in an explicitly disposable fixture installation.

Run using the installed maintenance interpreter. This never contacts GitHub or
uses operational credentials. The fixture candidate closes itself through Qt.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--private-key', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / 'manager'))
    from likewatch_manager.common import atomic_json, canonical, ManagerError, file_hash, locked
    from likewatch_manager.deployment import Manager
    from likewatch_manager.supervisor import run
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    manager = Manager(root)
    if not manager.fixture:
        raise RuntimeError('Qualification requires a TEST ONLY installation')
    work = Path(tempfile.mkdtemp(prefix='likewatch-update-qualification-'))
    remote = work / 'remote'
    git = str(root / manager.config['git'])
    def command(*argv, cwd=work):
        return subprocess.check_output(list(map(str, argv)), cwd=cwd, text=True).strip()
    command(git, 'clone', '--no-hardlinks', Path(args.source).resolve(), remote)
    command(git, 'config', 'user.name', 'LiKeWatch qualification', cwd=remote)
    command(git, 'config', 'user.email', 'fixture@example.invalid', cwd=remote)
    # Fixture-only auto-close: exercises healthy Qt shutdown without a production hook.
    entry = remote / 'src/likewatch/__main__.py'
    entry.write_text(entry.read_text().replace('    return app.exec()', '    QTimer.singleShot(3000, window.close)\n    return app.exec()'))
    original = manager.state()
    version = '0.3.991'
    app = remote / 'deployment/app.toml'
    app.write_text(app.read_text().replace('version = "0.3.0"', f'version = "{version}"'))
    command(git, 'add', '.', cwd=remote)
    command(git, 'commit', '-m', 'Local qualification candidate', cwd=remote)
    commit = command(git, 'rev-parse', 'HEAD', cwd=remote)
    command(git, 'tag', 'v' + version, cwd=remote)
    manifest = json.loads((root / 'seed/release-manifest.json').read_text())
    manifest.update(commit=commit, version=version, tag='v' + version, sequence=original['highest_sequence'] + 1,
                    issued=int(time.time()) - 10, expires=int(time.time()) + 3600)
    folder = work / 'signed'; folder.mkdir()
    key = Ed25519PrivateKey.from_private_bytes(Path(args.private_key).read_bytes())
    raw = canonical(manifest)
    (folder / 'release-manifest.json').write_bytes(raw)
    (folder / 'release-manifest.sig').write_bytes(key.sign(raw))
    config = manager.config.copy()
    config.update(remote=str(remote), fixture_release=str(folder), isolated_app=True, data_root=str(work / 'user-data'))
    atomic_json(root / 'manager/config.json', config)
    manager = Manager(root)
    plan = manager.prepare()
    assert plan['candidate']['environment_id'] == original['active']['environment_id']
    assert manager.state() == original
    manager.validate_plan(plan['id'])
    assert manager.state() == original
    start = time.monotonic()
    assert run(manager, transaction=plan['id']) == 0
    assert time.monotonic() - start < 30, 'Healthy exit restarted the GUI'
    updated = manager.state()
    assert updated['active']['commit'] == commit and updated['previous'] == original['active']
    assert updated['generation'] == original['generation'] + 1
    manager.check_source(original['active'])
    try:
        manager.plan(plan['id'])
    except ManagerError:
        pass
    else:
        raise AssertionError('Stale plan accepted')
    # Upgrade once more, then roll back to the first auto-closing fixture source.
    import sqlite3
    database = Path(config['data_root']) / 'history.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE qualification_retained (value TEXT)')
        db.execute("INSERT INTO qualification_retained VALUES ('history/outbox fixture sentinel')")
    app.write_text(app.read_text().replace(version, '0.3.992'))
    command(git, 'add', '.', cwd=remote); command(git, 'commit', '-m', 'Second healthy fixture', cwd=remote)
    second = command(git, 'rev-parse', 'HEAD', cwd=remote)
    command(git, 'tag', 'v0.3.992', cwd=remote)
    manifest.update(commit=second, version='0.3.992', tag='v0.3.992', sequence=manifest['sequence'] + 1)
    # Repackage identical dependencies with another native resource to exercise
    # a new environment identity and installation at its final prefix.
    import shutil, tarfile
    from likewatch_manager.environments import validate_lock
    payload = work / 'changed-payload'
    shutil.copytree(root / 'seed/payload', payload)
    marker = payload / 'native/qualification-marker'
    marker.parent.mkdir(exist_ok=True)
    marker.write_text('Second immutable environment fixture\n')
    lock = json.loads((payload / 'lock.json').read_text())
    lock['native'].append({'filename': marker.name, 'sha256': file_hash(marker)})
    identity = validate_lock(lock)
    atomic_json(payload / 'lock.json', lock)
    archive = folder / ('environment-' + identity + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as bundle:
        for path in sorted(payload.rglob('*')):
            if path.is_file():
                bundle.add(path, arcname=str(path.relative_to(payload)))
    manifest['platforms'][manager.platform] = {'environment_id': identity, 'lock_sha256': file_hash(payload / 'lock.json'),
        'payload_name': archive.name, 'payload_sha256': file_hash(archive), 'payload_size': archive.stat().st_size, 'python': '3.13'}
    raw = canonical(manifest)
    (folder / 'release-manifest.json').write_bytes(raw); (folder / 'release-manifest.sig').write_bytes(key.sign(raw))
    second_plan = manager.prepare(); manager.validate_plan(second_plan['id'])
    assert run(manager, transaction=second_plan['id']) == 0
    assert manager.state()['active']['commit'] == second
    assert manager.state()['active']['environment_id'] == identity
    assert run(manager, rollback=True) == 0
    assert manager.state()['active']['commit'] == commit
    assert manager.state()['active']['environment_id'] == original['active']['environment_id']
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT value FROM qualification_retained').fetchone()[0] == 'history/outbox fixture sentinel'
    updated = manager.state()
    # A failed candidate validation must not modify active/previous or consume sequence.
    bad = remote / 'src/likewatch/selftest.py'
    bad.write_text('raise RuntimeError("Injected candidate failure")\n')
    app.write_text(app.read_text().replace('0.3.992', '0.3.993'))
    command(git, 'add', '.', cwd=remote); command(git, 'commit', '-m', 'Local failed candidate', cwd=remote)
    bad_commit = command(git, 'rev-parse', 'HEAD', cwd=remote)
    command(git, 'tag', 'v0.3.993', cwd=remote)
    manifest.update(commit=bad_commit, version='0.3.993', tag='v0.3.993', sequence=manifest['sequence'] + 1)
    raw = canonical(manifest)
    (folder / 'release-manifest.json').write_bytes(raw); (folder / 'release-manifest.sig').write_bytes(key.sign(raw))
    bad_plan = manager.prepare()
    try:
        manager.validate_plan(bad_plan['id'])
    except ManagerError:
        pass
    else:
        raise AssertionError('Failed candidate validated')
    assert manager.state() == updated
    manager.validate(updated['previous'])
    manager.compatible(updated['previous'], config['data_root'])
    report = {'status': 'passed', 'root': str(root), 'seed_commit': original['active']['commit'],
              'candidate_commit': commit, 'environment_reused': True, 'environment_change_and_rollback': True,
              'checks': ['signed prepare', 'real spawned OCR validation', 'atomic activation',
                         'healthy Qt close without restart', 'previous source unchanged',
                         'stale plan rejected', 'failed validation leaves deployment unchanged',
                         'actual rollback with healthy Qt shutdown', 'operational database sentinel preserved'],
              'work': str(work)}
    atomic_json(args.report, report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
