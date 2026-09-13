"""Source-only publication must never silently change its private runtime."""
import importlib.util
from pathlib import Path
import subprocess
import pytest

spec = importlib.util.spec_from_file_location('source_release', Path(__file__).parents[1] / 'scripts/source_release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('changed', ['application', 'manager', 'dependency', 'native'])
def test_source_release_boundary(tmp_path, changed):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=tmp_path, text=True).strip()
    git('init')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    project = tmp_path / 'pyproject.toml'
    project.write_text('[project]\nversion="0.3.0"\ndependencies=["example==1"]\n')
    git('add', '.')
    git('commit', '-m', 'Seed')
    seed = git('rev-parse', 'HEAD')
    paths = {'application': 'src/likewatch/ui.py', 'manager': 'src/likewatch_manager/cli.py', 'native': 'assets/authenticate.swift'}
    if changed == 'dependency':
        project.write_text(project.read_text().replace('example==1', 'example==2'))
    else:
        target = tmp_path / paths[changed]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('fixture\n')
    git('add', '.')
    git('commit', '-m', 'Candidate')
    if changed == 'application':
        module.require_unchanged_runtime(seed, tmp_path)
    else:
        with pytest.raises(RuntimeError, match='full installer'):
            module.require_unchanged_runtime(seed, tmp_path)


def test_signer_rejects_retargeted_release_tag(tmp_path, monkeypatch):
    signing_spec = importlib.util.spec_from_file_location('release_manifest', Path(__file__).parents[1] / 'scripts/release_manifest.py')
    signing = importlib.util.module_from_spec(signing_spec)
    signing_spec.loader.exec_module(signing)
    def git(*args):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    for name, body in {'deployment/app.toml': 'version="0.3.0"\n', 'pyproject.toml': '[project]\nversion="0.3.0"\n', 'src/likewatch/__init__.py': '__version__ = "0.3.0"\n'}.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    git('add', '.')
    git('commit', '-m', 'Tagged source')
    git('tag', 'v0.3')
    (tmp_path / 'change.txt').write_text('new source')
    git('add', '.')
    git('commit', '-m', 'Different source')
    monkeypatch.setattr(signing, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['release_manifest', '--output', str(tmp_path / 'output'), '--payload', 'win-64=unused', '--private-key', 'unused', '--sequence', '1', '--tag', 'v0.3'])
    with pytest.raises(RuntimeError, match='different commit'):
        signing.main()
    assert not (tmp_path / 'output').exists()
