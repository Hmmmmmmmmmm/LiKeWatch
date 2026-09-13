"""Assemble constructor installer from existing exact locks and signed offline seed."""
import argparse
import json
import os
import uuid
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from likewatch_manager.common import atomic_json, file_hash, read_json, platform_id
from likewatch_manager.trust import verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', required=True)
    parser.add_argument('--signed-release', required=True)
    parser.add_argument('--constructor', required=True)
    parser.add_argument('--fixture', action='store_true', help='Label installer TEST ONLY; never publish fixture installer')
    args = parser.parse_args()
    work = Path(args.work).resolve(); signed = Path(args.signed_release).resolve()
    platform = platform_id()
    keys = read_json(signed / 'public-keys.json')
    manifest = verify((signed / 'release-manifest.json').read_bytes(), (signed / 'release-manifest.sig').read_bytes(), keys)
    if subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip() != manifest['commit']:
        raise RuntimeError('Signed source commit differs from build checkout')
    if subprocess.check_output(['git','status','--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Commit all intended source changes before building the signed installer')
    stage = work / (('constructor-fixture-' if args.fixture else 'constructor-release-') + uuid.uuid4().hex[:8])
    if stage.exists():
        raise RuntimeError('Use a fresh installer staging directory')
    stage.mkdir(parents=True)
    files = stage / 'files'; files.mkdir()
    manager = files / 'manager'; manager.mkdir()
    shutil.copytree(ROOT / 'src/likewatch_manager', manager / 'likewatch_manager', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'src/likewatch_manager/runner.py', manager / 'runner.py')
    shutil.copy2(ROOT / 'scripts/manager.py', manager / 'manager.py')
    shutil.copy2(ROOT / 'packaging/constructor/post_install.py', manager / 'post_install.py')
    seed = files / 'seed'; seed.mkdir()
    for name in ('release-manifest.json','release-manifest.sig'):
        shutil.copy2(signed / name, seed / name)
    subprocess.run(['git','bundle','create',str(seed / 'source.bundle'),'--all'], cwd=ROOT, check=True)
    shutil.copytree(work / 'payload', seed / 'payload')
    metadata = manifest['platforms'][platform]
    config = {'schema': 1, 'platform': platform, 'public_keys': keys,
              'remote': 'https://github.com/Hmmmmmmmmmm/LiKeWatch.git',
              'git': 'Library/bin/git.exe' if platform == 'win-64' else 'bin/git',
              'conda': 'Scripts/conda.exe' if platform == 'win-64' else 'bin/conda',
              'fixture': args.fixture, 'seed_sha256': file_hash(seed / 'source.bundle')}
    atomic_json(manager / 'config.json', config)
    if platform == 'win-64':
        for name, default in (('RunLiKeWatch', ''), ('RepairLiKeWatch', 'doctor')):
            (files / (name + '.cmd')).write_text('@echo off\nsetlocal DisableDelayedExpansion\nset "LW_ROOT=%~dp0"\n' +
                (f'if "%~1"=="" (\n  "%LW_ROOT%python.exe" -I -B "%LW_ROOT%manager\\manager.py" --root "%LW_ROOT%." {default}\n) else (\n  "%LW_ROOT%python.exe" -I -B "%LW_ROOT%manager\\manager.py" --root "%LW_ROOT%." %*\n)\n') +
                'set "LW_EXIT=%ERRORLEVEL%"\nif not "%LW_EXIT%"=="0" pause\nexit /b %LW_EXIT%\n')
    else:
        for name, default in (('RunLiKeWatch', 'run'), ('RepairLiKeWatch', 'doctor')):
            path = files / (name + '.command')
            path.write_text('#!/bin/sh\nset -eu\nLW_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n' +
                            f'if [ "$#" -eq 0 ]; then set -- {default}; fi\n' +
                            'exec "$LW_ROOT/bin/python" -I -B "$LW_ROOT/manager/manager.py" --root "$LW_ROOT" "$@"\n')
            path.chmod(0o755)
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', files / 'THIRD_PARTY_NOTICES.md')
    shutil.copy2(ROOT / 'docs/INSTALL.md', files / 'INSTALL.md')
    extra_files = [{str(path): str(path.relative_to(files))} for path in sorted(files.rglob('*')) if path.is_file()]
    recipe = {'name': 'LiKeWatchTest' if args.fixture else 'LiKeWatch', 'version': manifest['version'],
              'installer_type': 'exe' if platform == 'win-64' else 'sh',
              'environment_file': str(work / 'maintenance-explicit.txt'),
              'extra_envs': {'app-' + metadata['environment_id']: {'environment_file': str(work / 'app-explicit.txt'), 'menu_packages': []}},
              'channels': ['https://conda.anaconda.org/conda-forge'], 'menu_packages': [],
              'register_envs': False, 'initialize_conda': False, 'register_python': False,
              'keep_pkgs': True, 'extra_files': extra_files,
              'post_install': str(ROOT / ('packaging/constructor/post_install.bat' if platform == 'win-64' else 'packaging/constructor/post_install.sh'))}
    # JSON is a YAML subset; it preserves exact paths without manual quoting.
    (stage / 'construct.yaml').write_text(json.dumps(recipe, indent=2))
    env = {k: v for k, v in os.environ.items() if not k.startswith(('CONDA', 'PYTHON'))}
    tool_prefix = Path(args.constructor).resolve().parents[1]
    env['CONDA_EXE'] = str(tool_prefix / ('Scripts/conda.exe' if platform == 'win-64' else 'bin/conda'))
    env['CONDARC'] = str(stage / 'condarc')
    (stage / 'condarc').write_text('channels: [conda-forge]\nregister_envs: false\n')
    subprocess.run([args.constructor, str(stage), '--cache-dir', str(work / 'constructor-cache'), '--output-dir', str(work / 'installers')], check=True, env=env)


if __name__ == '__main__':
    main()
