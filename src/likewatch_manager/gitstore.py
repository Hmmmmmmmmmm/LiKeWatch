"""Managed Git cache and detached candidates; no operations on developer checkouts."""
import os
from pathlib import Path
import subprocess
from .common import ManagerError, identifier, owned


class GitStore:
    def __init__(self, root, executable, remote, fixture=False):
        self.root = Path(root).resolve()
        self.executable = str(executable)
        self.remote = remote
        self.fixture = fixture
        if not fixture and remote != 'https://github.com/Hmmmmmmmmmm/LiKeWatch.git':
            raise ManagerError('Unexpected source repository')
        self.repo = self.root / 'repo.git'

    def call(self, *args, cwd=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT='0', GIT_ATTR_NOSYSTEM='1')
        command = [self.executable, '-c', 'core.hooksPath=' + os.devnull,
                   '-c', 'init.templateDir=', '-c', 'protocol.ext.allow=never',
                   '-c', 'protocol.file.allow=' + ('always' if self.fixture else 'never'),
                   '-c', 'submodule.recurse=false', *map(str, args)]
        try:
            result = subprocess.run(command, cwd=cwd or self.root, env=env,
                                    capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            raise ManagerError('Git unavailable or request timed out') from None
        if result.returncode:
            raise ManagerError('Git operation failed; check connection, permissions, or modified source')
        return result.stdout.strip()

    def initialize(self, bundle):
        if self.repo.exists():
            raise ManagerError('Git cache already exists; use repair instead of overwriting')
        self.call('init', '--bare', self.repo)
        self.call('-c', 'protocol.file.allow=always', '--git-dir', self.repo, 'fetch', str(Path(bundle).resolve()), '+refs/*:refs/*')

    def fetch(self, manifest):
        tag = manifest['tag']
        identifier(tag, r'v[0-9]+\.[0-9]+(?:\.[0-9]+)?')
        self.call('--git-dir', self.repo, 'fetch', '--no-tags', '--no-recurse-submodules',
                  self.remote, f'+refs/tags/{tag}:refs/tags/{tag}')
        commit = self.call('--git-dir', self.repo, 'rev-parse', f'refs/tags/{tag}^{{commit}}')
        if commit != manifest['commit']:
            raise ManagerError('Published tag does not match signed commit')

    def stage(self, commit):
        identifier(commit, r'[a-f0-9]{40}')
        path = owned(self.root, 'releases/' + commit)
        if not path.exists():
            self.call('--git-dir', self.repo, 'worktree', 'add', '--detach', path, commit)
        self.check(path, commit)
        if (path / '.gitmodules').exists():
            raise ManagerError('Managed sources cannot include submodules')
        for item in path.rglob('*'):
            if item.is_symlink():
                raise ManagerError('Managed source symlinks are unsupported')
        return path

    def check(self, path, commit):
        if self.call('-C', path, 'rev-parse', 'HEAD') != commit:
            raise ManagerError('Source commit changed; modified files have been preserved')
        if self.call('-C', path, 'status', '--porcelain', '--untracked-files=all', '--ignored'):
            raise ManagerError('Managed source contains modified or extra files; repair preserves them')
