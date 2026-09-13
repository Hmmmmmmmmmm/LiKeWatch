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
