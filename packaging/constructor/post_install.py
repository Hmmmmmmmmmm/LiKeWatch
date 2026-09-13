"""Offline installer finalization. No system Python/Git or package solve is used."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'manager'))
from likewatch_manager.common import atomic_json, file_hash, read_json, ManagerError
from likewatch_manager.deployment import Manager
from likewatch_manager.environments import validate_lock


def main():
    manager = Manager(ROOT)
    manifest, signed_digest = manager.manifest(ROOT / 'seed', fresh=False)
    metadata = manifest['platforms'][manager.platform]
    lock = read_json(ROOT / 'seed/payload/lock.json')
    if validate_lock(lock) != metadata['environment_id'] or file_hash(ROOT / 'seed/payload/lock.json') != metadata['lock_sha256']:
        raise ManagerError('Seed environment lock mismatch')
    if file_hash(ROOT / 'seed/source.bundle') != manager.config['seed_sha256']:
        raise ManagerError('Seed source bundle mismatch')
    manager.environments.verify_files(ROOT / 'seed/payload', lock)
    prefix = manager.environments.prefix(metadata['environment_id'])
    manager.environments.install_wheels(prefix, ROOT / 'seed/payload', lock)
    manager.git.initialize(ROOT / 'seed/source.bundle')
    manager.git.stage(manifest['commit'])
    deployment = manager.deployment(manifest, signed_digest)
    report = manager.validate(deployment)
    atomic_json(ROOT / 'state/deployment.json', {'schema': 1, 'generation': 1, 'active': deployment, 'previous': None, 'highest_sequence': manifest['sequence']})
    atomic_json(ROOT / 'state/install-complete.json', {'schema': 1, 'validation': report, 'commit': manifest['commit']})
    print('LiKeWatch installed and verified. Run the RunLiKeWatch launcher in this folder.')


if __name__ == '__main__':
    main()
