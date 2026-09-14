"""Qualify source-only releases using an unchanged, previously released runtime."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def require_unchanged_runtime(seed, source=ROOT):
    paths = ['src/likewatch_manager', 'scripts/manager.py', 'packaging/constructor',
             'deployment/locks', 'deployment/public-keys.json', 'deployment/environments',
             'scripts/build_installer.py', 'scripts/lock_environment.py', 'assets/authenticate.swift']
    changed = subprocess.check_output(['git', 'diff', '--name-only', seed, 'HEAD', '--', *paths], cwd=source, text=True)
    before = tomllib.loads(subprocess.check_output(['git', 'show', seed + ':pyproject.toml'], cwd=source, text=True))['project']
    after = tomllib.loads((source / 'pyproject.toml').read_text())['project']
    for field in ('dependencies', 'requires-python', 'optional-dependencies'):
        if before.get(field) != after.get(field):
            raise RuntimeError('Python dependencies changed; publish a full installer')
    if changed.strip():
        raise RuntimeError('Runtime/bootstrap changed; publish a full installer: ' + changed.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['verify-seed', 'qualify'])
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--root')
    parser.add_argument('--platform', required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    artifact = Path(args.artifact).resolve()
    # Qualification deliberately imports the installed manager, not workspace code.
    sys.path.insert(0, str(Path(args.root).resolve() / 'manager') if args.command == 'qualify' else str(ROOT / 'src'))
    from likewatch_manager.common import atomic_json, canonical, file_hash
    from likewatch_manager.trust import verify
    keys = json.loads((ROOT / 'deployment/public-keys.json').read_text())
    manifest = verify((artifact / 'release-manifest.json').read_bytes(),
                      (artifact / 'release-manifest.sig').read_bytes(), keys, fresh=False)
    if manifest['tag'] != args.tag or args.platform not in manifest['platforms']:
        raise RuntimeError('Seed release identity mismatch')
    require_unchanged_runtime(manifest['commit'])
    if args.command == 'verify-seed':
        sums = dict(line.split('  ', 1)[::-1] for line in (artifact / 'SHA256SUMS').read_text().splitlines())
        installers = list(artifact.glob('*.exe' if args.platform == 'win-64' else '*.sh'))
        if len(installers) != 1 or sums.get(installers[0].name) != file_hash(installers[0]):
            raise RuntimeError('Missing or damaged official seed installer')
        metadata = manifest['platforms'][args.platform].copy()
        metadata.setdefault('payload_url', f"https://github.com/{manifest['repository']}/releases/download/{args.tag}/{metadata['payload_name']}")
        atomic_json(artifact / 'payload-metadata.json', metadata)
        return
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from likewatch_manager.deployment import Manager
    root = Path(args.root).resolve()
    manager = Manager(root)
    # This command is exclusively a CI fixture conversion, never user migration.
    import os
    if os.environ.get('GITHUB_ACTIONS') != 'true' or not root.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()):
        raise RuntimeError('Source qualification requires a disposable GitHub Actions installation')
    if manager.state()['active']['commit'] != manifest['commit']:
        raise RuntimeError('Installed seed differs from authenticated metadata')
    key = Ed25519PrivateKey.generate()
    key_path = artifact / 'fixture.key'
    with key_path.open('xb') as output:
        key_path.chmod(0o600)
        output.write(key.private_bytes_raw())
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode()
    config = manager.config | {'fixture': True, 'isolated_app': True, 'public_keys': [*keys, public], 'remote': str(ROOT)}
    atomic_json(root / 'manager/config.json', config)
    app = tomllib.loads((ROOT / 'deployment/app.toml').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    tag = 'v' + app['version']
    existing = subprocess.run(['git', 'rev-parse', '-q', '--verify', 'refs/tags/' + tag], cwd=ROOT, capture_output=True, text=True)
    if existing.returncode:
        subprocess.run(['git', 'tag', tag, commit], cwd=ROOT, check=True)
    elif existing.stdout.strip() != commit:
        raise RuntimeError('Candidate tag already refers to different source')
    import time
    candidate = manifest | {'commit': commit, 'version': app['version'], 'tag': tag,
                            'sequence': manifest['sequence'] + 1, 'issued': int(time.time()), 'expires': int(time.time()) + 3600,
                            'manager_protocol': app['manager_protocol'], 'profile_read': app['profile_read'], 'database_read': app['database_read']}
    folder = artifact / 'candidate'; folder.mkdir()
    raw = canonical(candidate)
    (folder / 'release-manifest.json').write_bytes(raw)
    (folder / 'release-manifest.sig').write_bytes(key.sign(raw))
    manager = Manager(root)
    plan = manager.prepare(folder)
    manager.validate_plan(plan['id'])
    validation = json.loads((root / manager.plan(plan['id'])['validation']).read_text())
    atomic_json(artifact / 'source-smoke.json', validation)
    subprocess.run([sys.executable, str(ROOT / 'scripts/qualify_installation.py'), '--root', str(root), '--source', str(ROOT),
                    '--private-key', str(key_path), '--report', str(artifact / 'update-qualification.json')], check=True)
    key_path.unlink()


if __name__ == '__main__':
    main()
