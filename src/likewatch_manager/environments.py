"""Immutable final-prefix environments assembled from verified offline packages."""
import json
import os
from pathlib import Path
import subprocess
import tarfile
from .common import ManagerError, canonical, digest, file_hash, identifier, owned, read_json, atomic_json


def validate_lock(lock):
    if lock.get('schema') != 1 or lock.get('platform') not in ('win-64', 'osx-arm64') or not lock.get('python', '').startswith('3.13.'):
        raise ManagerError('Unsupported Python/platform environment lock')
    seen = set()
    for group in ('conda', 'wheels', 'native'):
        for record in lock[group]:
            filename = record['filename']
            identifier(filename, r'[A-Za-z0-9_.+-]+')
            identifier(record['sha256'])
            if filename in seen:
                raise ManagerError('Duplicate locked payload')
            seen.add(filename)
    if not lock['conda'] or not lock['wheels']:
        raise ManagerError('Environment lock is incomplete')
    from packaging.utils import parse_wheel_filename, InvalidWheelFilename
    for record in lock['wheels']:
        try:
            _, _, _, tags = parse_wheel_filename(record['filename'])
        except InvalidWheelFilename:
            raise ManagerError('Invalid locked wheel filename') from None
        def supported(tag):
            python = tag.interpreter in ('py3', 'py2.py3', 'cp313') or (tag.abi == 'abi3' and tag.interpreter.startswith('cp3') and tag.interpreter[3:].isdigit() and int(tag.interpreter[3:]) <= 13)
            platform = tag.platform == 'any' or (lock['platform'] == 'win-64' and tag.platform == 'win_amd64') or (lock['platform'] == 'osx-arm64' and tag.platform.startswith('macosx_') and tag.platform.endswith(('_arm64', '_universal2')))
            return python and platform and tag.abi in ('none', 'abi3', 'cp313')
        if not any(supported(tag) for tag in tags):
            raise ManagerError('Locked wheel ABI does not match the private Python/platform')
    return digest(canonical(lock))


def extract_payload(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        if len(members) > 10000 or sum(m.size for m in members) > 5_000_000_000:
            raise ManagerError('Environment archive exceeds limits')
        for member in members:
            owned(destination, member.name)
            if not member.isfile() and not member.isdir():
                raise ManagerError('Environment archive links/devices are forbidden')
        bundle.extractall(destination, members=members, filter='data')


def scoped_environment(prefix, context=None):
    prefix = Path(prefix)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PYTHON', 'CONDA', 'QT_')) and k not in ('TESSDATA_PREFIX', 'TESSERACT_CMD', 'LIKEWATCH_CONTEXT', 'LIKEWATCH_LOG_DIR')}
    if os.name == 'nt':
        paths = [prefix, prefix / 'Library/bin', prefix / 'Library/usr/bin', prefix / 'Library/mingw-w64/bin', prefix / 'Scripts', Path(os.environ['SystemRoot']) / 'System32', Path(os.environ['SystemRoot'])]
    else:
        paths = [prefix / 'bin', Path('/usr/bin'), Path('/bin')]
    env['PATH'] = os.pathsep.join(map(str, paths))
    env['CONDA_PREFIX'] = str(prefix)
    env['PYTHONNOUSERSITE'] = '1'
    if context:
        env['LIKEWATCH_CONTEXT'] = json.dumps(context)
    return env


def interpreter(prefix):
    return Path(prefix) / ('python.exe' if os.name == 'nt' else 'bin/python')


class Environments:
    def __init__(self, root, conda):
        self.root, self.conda = Path(root), str(conda)

    def prefix(self, identity):
        identifier(identity)
        return owned(self.root, 'envs/app-' + identity)

    def check(self, identity):
        prefix = self.prefix(identity)
        lock = read_json(prefix / 'likewatch-environment.json')
        if validate_lock(lock) != identity or not interpreter(prefix).is_file():
            raise ManagerError('Application environment is missing or incomplete')
        self.check_conda(prefix, lock)
        for item in lock['native']:
            if file_hash(prefix / 'native' / item['filename']) != item['sha256']:
                raise ManagerError('Native helper is damaged; repair the environment')
        return prefix

    @staticmethod
    def check_conda(prefix, lock):
        records = [read_json(path) for path in (Path(prefix) / 'conda-meta').glob('*.json')]
        actual = {r['name']: (r['version'], r['build'], r.get('sha256')) for r in records}
        expected = {r['name']: (r['version'], r['build'], r['sha256']) for r in lock['conda']}
        if actual != expected:
            raise ManagerError('Installed conda inventory disagrees with the environment lock')

    def create(self, payload, metadata, platform):
        identity = metadata['environment_id']
        prefix = self.prefix(identity)
        if (prefix / 'likewatch-environment.json').exists():
            return self.check(identity)
        if prefix.exists():
            raise ManagerError('Incomplete environment preserved; use a new installer or repair directory before retrying')
        folder = owned(self.root, 'cache/environments/' + identity)
        if file_hash(payload) != metadata['payload_sha256']:
            raise ManagerError('Environment archive hash mismatch')
        extract_payload(payload, folder)
        lock = read_json(folder / 'lock.json')
        if file_hash(folder / 'lock.json') != metadata['lock_sha256'] or validate_lock(lock) != identity or lock['platform'] != platform:
            raise ManagerError('Environment identity or platform mismatch')
        self.verify_files(folder, lock)
        explicit = folder / 'explicit-local.txt'
        explicit.write_text('@EXPLICIT\n' + '\n'.join((folder / 'conda' / r['filename']).as_uri() + '#' + r['sha256'] for r in lock['conda']) + '\n')
        env = scoped_environment(self.root)
        env.update(CONDA_REGISTER_ENVS='false', CONDA_PKGS_DIRS=str(self.root / 'cache/packages'), CONDA_NO_PLUGINS='true', CONDA_SOLVER='classic')
        self.command([self.conda, 'create', '--yes', '--offline', '--no-default-packages', '--prefix', str(prefix), '--file', str(explicit)], env)
        self.install_wheels(prefix, folder, lock)
        return prefix

    @staticmethod
    def verify_files(folder, lock):
        for group in ('conda', 'wheels', 'native'):
            for record in lock[group]:
                if file_hash(Path(folder) / group / record['filename']) != record['sha256']:
                    raise ManagerError('Offline package integrity check failed')

    @staticmethod
    def command(args, env=None):
        try:
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired):
            raise ManagerError('Environment operation unavailable or timed out') from None
        if result.returncode:
            raise ManagerError('Environment installation or inventory validation failed')
        return result.stdout

    def install_wheels(self, prefix, folder, lock):
        import shutil
        self.check_conda(prefix, lock)
        requirements = Path(folder) / 'requirements.txt'
        requirements.write_text('\n'.join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}" for r in lock['wheels']) + '\n')
        self.command([str(interpreter(prefix)), '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', '--require-hashes', '--find-links', str(Path(folder) / 'wheels'), '-r', str(requirements)], scoped_environment(prefix))
        (Path(prefix) / 'native').mkdir(exist_ok=True)
        for r in lock['native']:
            shutil.copy2(Path(folder) / 'native' / r['filename'], Path(prefix) / 'native' / r['filename'])
        self.command([str(interpreter(prefix)), '-I', '-m', 'pip', 'check'], scoped_environment(prefix))
        inventory = json.loads(self.command([str(interpreter(prefix)), '-I', '-c', 'import importlib.metadata as m,json;print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version for d in m.distributions()}))'], scoped_environment(prefix)))
        for r in lock['wheels']:
            if inventory.get(r['name'].lower().replace('_', '-')) != r['version']:
                raise ManagerError('Installed wheel inventory disagrees with lock')
        if 'likewatch' in inventory:
            raise ManagerError('Managed application must not be pip-installed')
        # Qualification is recorded only by the caller after real source/OCR tests.
        atomic_json(Path(prefix) / 'likewatch-pending-environment.json', lock)

    def qualify(self, identity):
        prefix = self.prefix(identity)
        pending = prefix / 'likewatch-pending-environment.json'
        if pending.exists():
            lock = read_json(pending)
            if validate_lock(lock) != identity:
                raise ManagerError('Environment identity changed during validation')
            atomic_json(prefix / 'likewatch-environment.json', lock)
