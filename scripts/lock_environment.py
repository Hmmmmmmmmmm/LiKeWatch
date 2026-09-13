"""Resolve native build-time dependencies once; emit hashed offline payload and locks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from email.parser import BytesParser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from likewatch_manager.common import atomic_json, canonical, digest, file_hash, platform_id
from likewatch_manager.environments import validate_lock


def call(args):
    subprocess.run(list(map(str, args)), check=True)


def records(prefix, output):
    result = []
    output.mkdir(parents=True, exist_ok=True)
    for metadata in sorted((prefix / 'conda-meta').glob('*.json')):
        record = json.loads(metadata.read_text())
        filename = record.get('fn') or Path(record['url']).name
        target = output / filename
        if not target.exists():
            urllib.request.urlretrieve(record['url'], target)
        expected = record.get('sha256')
        if expected and expected != file_hash(target):
            raise RuntimeError('Conda package hash mismatch')
        result.append({k: record[k] for k in ('name','version','build','url')} | {'filename': filename, 'sha256': file_hash(target)})
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--conda', required=True)
    p.add_argument('--work', required=True)
    args = p.parse_args()
    work = Path(args.work).resolve(); work.mkdir(parents=True, exist_ok=True)
    platform = platform_id()
    base, app = work / 'maintenance', work / 'app-python'
    for prefix, specs in ((base, ['python=3.13.15', 'conda=26.7.2', 'git=2.55.0', 'cryptography=46.0.5', 'packaging=26.3', 'platformdirs=4.11.8']), (app, ['python=3.13.15', 'pip=26.2.1'])):
        if not prefix.exists():
            call([args.conda, 'create', '--yes', '--override-channels', '-c', 'conda-forge', '--prefix', prefix, *specs])
    payload = work / 'payload'; payload.mkdir(exist_ok=True)
    maintenance = records(base, work / 'maintenance-packages')
    conda_records = records(app, payload / 'conda')
    requirements = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['dependencies']
    requirements_file = work / 'requirements.in'; requirements_file.write_text('\n'.join(requirements))
    wheels = payload / 'wheels'; wheels.mkdir(exist_ok=True)
    python = app / ('python.exe' if sys.platform == 'win32' else 'bin/python')
    call([python, '-m', 'pip', 'download', '--only-binary=:all:', '-r', requirements_file, '--dest', wheels])
    wheel_records = []
    for wheel in sorted(wheels.glob('*.whl')):
        with zipfile.ZipFile(wheel) as z:
            metadata = BytesParser().parsebytes(z.read(next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))))
        wheel_records.append({'filename': wheel.name, 'name': metadata['Name'], 'version': metadata['Version'], 'sha256': file_hash(wheel)})
    native = payload / 'native'; native.mkdir(exist_ok=True)
    native_records = []
    if platform == 'osx-arm64':
        call(['/usr/bin/swiftc', '-target', 'arm64-apple-macos15.0', ROOT / 'assets/authenticate.swift', '-o', native / 'native-auth'])
        native_records.append({'filename': 'native-auth', 'sha256': file_hash(native / 'native-auth')})
    lock = {'schema': 1, 'platform': platform, 'python': '3.13.15', 'conda': conda_records, 'wheels': wheel_records, 'native': native_records}
    identity = validate_lock(lock)
    atomic_json(payload / 'lock.json', lock)
    locks = ROOT / 'deployment/locks'; locks.mkdir(exist_ok=True)
    atomic_json(locks / (platform + '.json'), lock)
    atomic_json(locks / (platform + '-maintenance.json'), {'schema': 1, 'platform': platform, 'conda': maintenance})
    # Explicit files are build inputs; users never solve a package spec.
    for name, recs in (('app', conda_records), ('maintenance', maintenance)):
        (work / (name + '-explicit.txt')).write_text('@EXPLICIT\n' + '\n'.join(r['url'] + '#' + r['sha256'] for r in recs) + '\n')
    archive = work / f'LiKeWatch-environment-{platform}-{identity}.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sorted(payload.rglob('*')):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(payload)))
    metadata = {'environment_id': identity, 'lock_sha256': file_hash(payload / 'lock.json'), 'payload_sha256': file_hash(archive), 'payload_name': archive.name, 'payload_size': archive.stat().st_size, 'python': '3.13'}
    atomic_json(work / 'payload-metadata.json', metadata)
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
