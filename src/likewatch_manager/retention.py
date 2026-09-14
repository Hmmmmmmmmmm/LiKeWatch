"""Explicit retention of authenticated artifacts; operational data is never a target."""
import shutil
from .common import ManagerError, identifier, locked, read_json
from .models import UpdatePlan, validate


def cleanup(manager, apply=False):
    with locked(manager.root / 'state/run.lock'), locked(manager.root / 'state/update.lock'):
        state = manager.state()
        protected = [value for value in (state['active'], state.get('previous')) if value]
        for value in protected:
            manager.accepted_manifest(value)
        known = {value['commit']: value for value in protected}
        seed, signature = manager.manifest(manager.root / 'seed', fresh=False)
        deployment = manager.deployment(seed, signature)
        known[deployment['commit']] = deployment
        for path in (manager.root / 'state/transactions').glob('*/plan.json'):
            plan = validate(read_json(path), UpdatePlan)
            manifest, signature = manager.manifest(path.parent, fresh=False)
            candidate = manager.deployment(manifest, signature)
            if candidate != plan['candidate']:
                raise ManagerError('Altered transaction blocks cleanup; artifacts have been preserved')
            known[candidate['commit']] = candidate
            if plan['generation'] == state['generation']:
                protected.append(candidate)
        protected_commits = {value['commit'] for value in protected}
        protected_environments = {value['environment_id'] for value in protected}
        removed, preserved = [], {}
        remaining = set()
        unknown_source = False
        for path in sorted((manager.root / 'releases').iterdir()):
            try:
                identifier(path.name, r'[a-f0-9]{40}')
                if path.is_symlink() or path.name not in known:
                    raise ManagerError('Unrecognized source retained')
                if path.name in protected_commits:
                    remaining.add(path.name)
                    continue
                manager.git.check(path, path.name)
                if apply:
                    # No force: Git rechecks cleanliness before removing a worktree.
                    manager.git.call('--git-dir', manager.git.repo, 'worktree', 'remove', path)
                removed.append(path.name)
            except (OSError, ValueError, ManagerError) as error:
                preserved[path.name] = str(error)
                remaining.add(path.name)
                unknown_source |= path.name not in known
        for commit in remaining:
            if commit in known:
                protected_environments.add(known[commit]['environment_id'])
        known_environments = {value['environment_id'] for value in known.values()}
        environments = []
        for path in sorted((manager.root / 'envs').glob('app-*')):
            identity = path.name[4:]
            if identity in protected_environments:
                continue
            try:
                identifier(identity)
                if unknown_source or path.is_symlink() or identity not in known_environments:
                    raise ManagerError('Unrecognized or possibly referenced environment retained')
                manager.environments.unchanged(identity)
                if apply:
                    shutil.rmtree(path)
                environments.append(identity)
            except (OSError, ValueError, KeyError, TypeError, ManagerError) as error:
                preserved[path.name] = str(error)
        return {'status': 'retention-cleaned' if apply else 'retention-preview',
                'sources': removed, 'environments': environments, 'preserved': preserved,
                'protected_sources': sorted(protected_commits), 'protected_environments': sorted(protected_environments)}
