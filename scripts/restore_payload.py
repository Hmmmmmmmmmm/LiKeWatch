"""Restore a qualified native payload without solving or rebuilding dependencies."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from likewatch_manager.common import read_json, file_hash, canonical, platform_id
from likewatch_manager.environments import extract_payload, validate_lock, Environments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--work', required=True)
    args = parser.parse_args()
    artifact = Path(args.artifact).resolve(); work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    metadata = read_json(artifact / 'payload-metadata.json')
    archive = artifact / metadata['payload_name']
    if archive.stat().st_size != metadata['payload_size'] or file_hash(archive) != metadata['payload_sha256']:
        raise RuntimeError('Qualified payload archive is damaged')
    payload = work / 'payload'
    if payload.exists():
        raise RuntimeError('Restore requires a fresh build directory')
    extract_payload(archive, payload)
    lock = read_json(payload / 'lock.json')
    if lock['platform'] != platform_id() or validate_lock(lock) != metadata['environment_id'] or file_hash(payload / 'lock.json') != metadata['lock_sha256']:
        raise RuntimeError('Qualified environment identity mismatch')
    Environments.verify_files(payload, lock)
    expected = read_json(ROOT / 'deployment/locks' / (platform_id() + '.json'))
    maintenance = read_json(artifact / 'locks' / (platform_id() + '-maintenance.json'))
    if canonical(lock) != canonical(expected) or canonical(maintenance) != canonical(read_json(ROOT / 'deployment/locks' / (platform_id() + '-maintenance.json'))):
        raise RuntimeError('Commit the qualified native locks before building production installers')
    for name, records in (('app', lock['conda']), ('maintenance', maintenance['conda'])):
        (work / (name + '-explicit.txt')).write_text('@EXPLICIT\n' + '\n'.join(r['url'] + '#' + r['sha256'] for r in records) + '\n')
    shutil.copy2(archive, work / archive.name)
    shutil.copy2(artifact / 'payload-metadata.json', work / 'payload-metadata.json')


if __name__ == '__main__':
    main()
