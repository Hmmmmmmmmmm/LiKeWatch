"""Create a detached signed release manifest after source and payloads are fixed."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--payload', action='append', required=True)
    parser.add_argument('--private-key', required=True, help='Path to raw 32-byte Ed25519 key; never place in repository')
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    app = tomllib.loads((ROOT / 'deployment/app.toml').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
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
    (output / 'release-manifest.json').write_bytes(raw)
    (output / 'release-manifest.sig').write_bytes(key.sign(raw))
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    atomic_json(output / 'public-keys.json', [public])


if __name__ == '__main__':
    main()
