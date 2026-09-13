"""Create a detached signed release manifest after source and payloads are fixed."""
import ast
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import tomllib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from likewatch_manager.common import canonical, atomic_json
from likewatch_manager.trust import verify
from packaging.version import Version


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--payload', action='append', required=True)
    parser.add_argument('--private-key', required=True, help='Path to raw 32-byte Ed25519 key; never place in repository')
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--previous', help='Directory containing previous signed manifest and public keys')
    args = parser.parse_args()
    app = tomllib.loads((ROOT / 'deployment/app.toml').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
    declarations = ast.parse((ROOT / 'src/likewatch/__init__.py').read_text())
    versions = [ast.literal_eval(n.value) for n in declarations.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets)]
    if versions != [app['version']] or project['version'] != app['version']:
        raise RuntimeError('Application version declarations disagree')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Release source has uncommitted changes')
    if args.previous:
        previous = Path(args.previous)
        authority = json.loads((ROOT / 'deployment/public-keys.json').read_text())
        old = verify((previous / 'release-manifest.json').read_bytes(), (previous / 'release-manifest.sig').read_bytes(), authority, fresh=False)
        if args.sequence <= old['sequence'] or Version(app['version']) <= Version(old['version']):
            raise RuntimeError('Release version and sequence must increase')
    existing = subprocess.run(['git', 'rev-parse', '-q', '--verify', 'refs/tags/' + args.tag + '^{}'], cwd=ROOT, text=True, capture_output=True)
    if existing.returncode == 0 and existing.stdout.strip() != commit:
        raise RuntimeError('Release tag already identifies a different commit')
    platforms = {}
    for item in args.payload:
        platform, file = item.split('=', 1)
        platforms[platform] = json.loads(Path(file).read_text())
    manifest = {'schema': 1, 'repository': 'Hmmmmmmmmmm/LiKeWatch', 'version': app['version'],
                'tag': args.tag, 'commit': commit, 'channel': 'stable', 'sequence': args.sequence,
                'issued': int(time.time()), 'expires': int(time.time()) + 90 * 86400,
                'manager_protocol': app['manager_protocol'], 'profile_read': app['profile_read'],
                'database_read': app['database_read'], 'platforms': platforms,
                'notes': 'Source-managed LiKeWatch release. Monitoring and delivery restart paused.'}
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    raw = canonical(manifest)
    key = Ed25519PrivateKey.from_private_bytes(Path(args.private_key).read_bytes())
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    signature = key.sign(raw)
    verify(raw, signature, [public])
    (output / 'release-manifest.json').write_bytes(raw)
    (output / 'release-manifest.sig').write_bytes(signature)
    atomic_json(output / 'public-keys.json', [public])


if __name__ == '__main__':
    main()
