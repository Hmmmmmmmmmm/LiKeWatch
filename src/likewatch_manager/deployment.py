"""Signed, generation-bound preparation and non-destructive deployment recovery."""
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import tomllib
import uuid
from packaging.version import Version
from .common import read_bytes, ManagerError, atomic_json, digest, file_hash, identifier, locked, owned, read_json, platform_id
from .environments import Environments, interpreter, scoped_environment
from .gitstore import GitStore
from .releases import Releases
from .trust import verify


class Manager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config = read_json(self.root / 'manager/config.json')
        if self.config.get('schema') != 1:
            raise ManagerError('Unsupported installation configuration')
        self.platform = self.config['platform']
        if self.platform != platform_id():
            raise ManagerError('Installation is for a different platform')
        self.keys = self.config['public_keys']
        self.fixture = self.config.get('fixture', False)
        git = owned(self.root, self.config['git'])
        conda = owned(self.root, self.config['conda'])
        self.git = GitStore(self.root, git, self.config['remote'], fixture=self.fixture)
        self.environments = Environments(self.root, conda)
        self.releases = Releases(self.root, self.keys)
        if self.fixture and self.config.get('fixture_release'):
            from .releases import FixtureReleases
            self.releases = FixtureReleases(self.config['fixture_release'], self.keys)

    def state(self):
        state = read_json(self.root / 'state/deployment.json')
        if state.get('schema') != 1 or type(state.get('generation')) is not int:
            raise ManagerError('Deployment state is invalid; run doctor')
        for entry in (state.get('active'), state.get('previous')):
            if entry:
                identifier(entry['commit'], r'[a-f0-9]{40}')
                identifier(entry['environment_id'])
        return state

    def manifest(self, folder, fresh=True):
        folder = Path(folder)
        raw = read_bytes(folder / 'release-manifest.json')
        signature = read_bytes(folder / 'release-manifest.sig', 64)
        return verify(raw, signature, self.keys, fresh=fresh), digest(raw)

    def deployment(self, manifest, digest_value):
        payload = manifest['platforms'].get(self.platform)
        if not payload:
            raise ManagerError('Release does not support this platform')
        return {'commit': manifest['commit'], 'version': manifest['version'],
                'environment_id': payload['environment_id'], 'manifest_digest': digest_value,
                'profile_read': manifest['profile_read'], 'database_read': manifest['database_read']}

    def check_source(self, deployment):
        path = owned(self.root, 'releases/' + deployment['commit'])
        self.git.check(path, deployment['commit'])
        return path

    def compatible(self, deployment, data_root):
        data_root = Path(data_root)
        profile = data_root / 'last-profile.json'
        if profile.exists():
            schema = read_json(profile).get('schema', 1)
            if not deployment['profile_read'][0] <= schema <= deployment['profile_read'][1]:
                raise ManagerError('Profile schema is incompatible; current data has been preserved')
        database = data_root / 'history.sqlite3'
        if database.exists():
            with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
                schema = db.execute('PRAGMA user_version').fetchone()[0]
            if not deployment['database_read'][0] <= schema <= deployment['database_read'][1]:
                raise ManagerError('Database schema blocks rollback/update; use a compatible installer')

    def context(self, deployment, *, transaction='', test=False, data_root=None):
        source = self.check_source(deployment)
        prefix = self.environments.prefix(deployment['environment_id'])
        session = uuid.uuid4().hex
        directory = owned(self.root, 'state/sessions/' + session)
        directory.mkdir(parents=True)
        value = {'source_root': str(source), 'native_root': str(prefix / 'native'),
                 'commit': deployment['commit'], 'environment_id': deployment['environment_id'],
                 'install_root': str(self.root), 'manager_python': str(interpreter(self.root)),
                 'session': session, 'nonce': uuid.uuid4().hex, 'transaction': transaction,
                 'health_file': str(directory / 'health.json'), 'request_file': str(directory / 'request.json'),
                 'activated_file': str(directory / 'activated.json'), 'test_mode': test}
        if data_root:
            value['data_root'] = str(Path(data_root).resolve())
        if test:
            sandbox = Path(data_root).resolve() if data_root else directory / 'test-data'
            value.update(data_root=str(sandbox), settings_file=str(sandbox / 'settings.ini'), log_root=str(directory / 'logs'))
        atomic_json(directory / 'context.json', value)
        return value, directory / 'context.json'

    def validate(self, deployment):
        value, context_file = self.context(deployment, test=True)
        prefix = self.environments.prefix(deployment['environment_id'])
        report = context_file.parent / 'validation.json'
        env = scoped_environment(prefix, value)
        env['QT_QPA_PLATFORM'] = 'offscreen'
        try:
            result = subprocess.run([str(interpreter(prefix)), '-I', '-B', str(self.root / 'manager/runner.py'), str(context_file), '--self-test', '--ui-stress', '--report', str(report)], env=env, cwd=context_file.parent, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired:
            raise ManagerError('Candidate validation timed out; active version is unchanged') from None
        (context_file.parent / 'validation.log').write_bytes(result.stdout + result.stderr)
        if result.returncode or not report.exists():
            raise ManagerError('Candidate OCR/GUI validation failed; active version is unchanged')
        data = read_json(report)
        child = data.get('ocr_child', {})
        if data.get('status') != 'passed' or data.get('values') != ['83.2', '18.4'] or data.get('commit') != deployment['commit'] or child.get('commit') != deployment['commit'] or child.get('environment_id') != deployment['environment_id'] or Path(child.get('python', '')).resolve() != interpreter(prefix).resolve():
            raise ManagerError('Candidate validation identity mismatch')
        if not Path(child['module']).resolve().is_relative_to(Path(value['source_root'])):
            raise ManagerError('OCR child imported a different source')
        self.git.check(value['source_root'], deployment['commit'])
        self.environments.qualify(deployment['environment_id'])
        return str(report.relative_to(self.root))

    def prepare(self, folder=None):
        with locked(self.root / 'state/update.lock'):
            state = self.state()
            self.check_source(state['active'])
            if folder is None:
                _, folder = self.releases.check()
            elif not self.fixture:
                folder = owned(self.root, str(Path(folder).resolve().relative_to(self.root)))
            manifest, manifest_digest = self.manifest(folder)
            if manifest['sequence'] <= state.get('highest_sequence', 0) or Version(manifest['version']) <= Version(state['active']['version']):
                raise ManagerError('Release is not newer than the accepted deployment')
            candidate = self.deployment(manifest, manifest_digest)
            self.git.fetch(manifest)
            source = self.git.stage(candidate['commit'])
            app = tomllib.loads((source / 'deployment/app.toml').read_text())
            if app['version'] != candidate['version'] or app['manager_protocol'] != 1 or app['profile_read'] != candidate['profile_read'] or app['database_read'] != candidate['database_read']:
                raise ManagerError('Source compatibility metadata disagrees with signed manifest')
            payload = manifest['platforms'][self.platform]
            prefix = self.environments.prefix(candidate['environment_id'])
            if not (prefix / 'likewatch-environment.json').exists():
                archive = Path(folder) / payload['payload_name'] if self.fixture else self.releases.payload(payload, Path(folder))
                self.environments.create(archive, payload, self.platform)
            else:
                self.environments.check(candidate['environment_id'])
            transaction = uuid.uuid4().hex
            directory = owned(self.root, 'state/transactions/' + transaction)
            directory.mkdir(parents=True)
            for filename in ('release-manifest.json', 'release-manifest.sig'):
                shutil.copy2(Path(folder) / filename, directory / filename)
            plan = {'schema': 1, 'id': transaction, 'generation': state['generation'], 'candidate': candidate,
                    'sequence': manifest['sequence'], 'phase': 'prepared', 'created': time.time()}
            atomic_json(directory / 'plan.json', plan)
            # Validation can be requested separately while monitoring is paused.
            return plan

    def validate_plan(self, transaction):
        with locked(self.root / 'state/update.lock'):
            plan = self.plan(transaction)
            plan['validation'] = self.validate(plan['candidate'])
            plan['phase'] = 'validated'
            atomic_json(self.root / 'state/transactions' / transaction / 'plan.json', plan)
            return plan

    def plan(self, transaction):
        identifier(transaction, r'[a-f0-9]{32}')
        folder = owned(self.root, 'state/transactions/' + transaction)
        plan = read_json(folder / 'plan.json')
        manifest, signed_digest = self.manifest(folder)
        if plan['schema'] != 1 or plan['id'] != transaction or plan['generation'] != self.state()['generation'] or plan['candidate'] != self.deployment(manifest, signed_digest):
            raise ManagerError('Stale or altered update plan; prepare again')
        self.check_source(plan['candidate'])
        return plan

    def doctor(self):
        state = self.state()
        result = {'schema': 1, 'active': state['active'], 'generation': state['generation'], 'signing_configured': bool(self.keys), 'fixture_installation': self.fixture}
        try:
            self.check_source(state['active'])
            self.environments.check(state['active']['environment_id'])
            result['status'] = 'ready'
        except (OSError, ManagerError) as error:
            result.update(status='repair-required', detail=str(error))
        return result
