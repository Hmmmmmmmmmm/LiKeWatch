"""Real local Git and signed-metadata tests; no production keys or data."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from likewatch_manager.common import ManagerError, atomic_json, canonical, digest, locked, owned
from likewatch_manager.trust import verify
from likewatch_manager.gitstore import GitStore
from likewatch_manager.environments import extract_payload, validate_lock


@pytest.fixture
def signed():
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    value = {'schema':1,'repository':'Hmmmmmmmmmm/LiKeWatch','version':'0.3.1','tag':'v0.3.1',
             'commit':'a'*40,'channel':'stable','sequence':2,'manager_protocol':1,
             'issued':int(time.time())-10,'expires':int(time.time())+3600,
             'profile_read':[1,1],'database_read':[0,1],
             'platforms':{'osx-arm64':{'environment_id':'b'*64,'lock_sha256':'c'*64,
                          'payload_sha256':'d'*64,'payload_name':'environment.tar.gz',
                          'payload_size':100,'python':'3.13'}}}
    return key, public, value


def test_signed_manifest_exact_bytes(signed):
    key, public, value = signed
    raw = canonical(value)
    assert verify(raw,key.sign(raw),[public]) == value
    for changed, signature, keys in ((raw+b' ',key.sign(raw),[public]), (raw,b'x'*64,[public]), (raw,key.sign(raw),[])):
        with pytest.raises(ManagerError):
            verify(changed,signature,keys)


@pytest.mark.parametrize('field,value', [('schema',2),('repository','evil/repo'),('tag','--upload-pack=evil'),('channel','beta'),('version','0.3.1rc1'),('commit','../escape'),('sequence',0),('expires',0),('manager_protocol',2)])
def test_bad_signed_metadata_rejected(signed,field,value):
    key, public, data = signed
    data[field]=value; raw=canonical(data)
    with pytest.raises(ManagerError):
        verify(raw,key.sign(raw),[public])


def test_expiry_does_not_invalidate_installed_seed(signed):
    key, public, data=signed
    data['issued']=1;data['expires']=2;raw=canonical(data)
    assert verify(raw,key.sign(raw),[public],fresh=False)['version']=='0.3.1'


def test_atomic_records_and_containment(tmp_path):
    state=tmp_path/'state.json'
    atomic_json(state,{'generation':1});atomic_json(state,{'generation':2})
    assert json.loads(state.read_text())=={'generation':2}
    with pytest.raises(ManagerError): owned(tmp_path,'../outside')
    if os.name != 'nt':
        (tmp_path/'link').symlink_to(tmp_path.parent, target_is_directory=True)
        with pytest.raises(ManagerError): owned(tmp_path,'link/outside')


def test_duplicate_operation_lock(tmp_path):
    with locked(tmp_path/'lock'):
        with pytest.raises(ManagerError):
            with locked(tmp_path/'lock'): pass
    with locked(tmp_path/'lock'): pass


@pytest.mark.parametrize('name,link', [('../escape',False),('/absolute',False),('link',True)])
def test_archive_escape_rejected(tmp_path,name,link):
    archive=tmp_path/'payload.tar'
    with tarfile.open(archive,'w') as tar:
        item=tarfile.TarInfo(name)
        if link: item.type=tarfile.SYMTYPE;item.linkname='../outside'
        else: item.size=1
        tar.addfile(item,None if link else io.BytesIO(b'x'))
    with pytest.raises(ManagerError): extract_payload(archive,tmp_path/'destination')
    assert not (tmp_path/'escape').exists()


def git(*args,cwd):
    return subprocess.check_output(['git',*map(str,args)],cwd=cwd,text=True).strip()


def test_real_git_detached_sources_and_retargeted_tag(tmp_path):
    remote=tmp_path/'remote';remote.mkdir()
    git('init',cwd=remote);git('config','user.name','Fixture',cwd=remote);git('config','user.email','fixture@example.invalid',cwd=remote)
    (remote/'value.py').write_text('VALUE=1\n');git('add','.',cwd=remote);git('commit','-m','first',cwd=remote)
    first=git('rev-parse','HEAD',cwd=remote);git('tag','v0.3.0',cwd=remote)
    bundle=tmp_path/'seed.bundle';git('bundle','create',bundle,'--all',cwd=remote)
    root=tmp_path/'installation';root.mkdir()
    import shutil
    store=GitStore(root,shutil.which('git'),str(remote),fixture=True)
    store.initialize(bundle);active=store.stage(first)
    assert (active/'.git').is_file()
    (remote/'value.py').write_text('VALUE=2\n');git('add','.',cwd=remote);git('commit','-m','second',cwd=remote)
    second=git('rev-parse','HEAD',cwd=remote);git('tag','v0.3.1',cwd=remote)
    store.fetch({'tag':'v0.3.1','commit':second});candidate=store.stage(second)
    assert (active/'value.py').read_text()=='VALUE=1\n'
    assert (candidate/'value.py').read_text()=='VALUE=2\n'
    git('tag','-f','v0.3.1',first,cwd=remote)
    with pytest.raises(ManagerError,match='signed commit'):
        store.fetch({'tag':'v0.3.1','commit':second})
    (candidate/'extra.py').write_text('local change')
    with pytest.raises(ManagerError,match='modified or extra'): store.check(candidate,second)
    assert (candidate/'extra.py').read_text()=='local change'


def test_sqlite_backup_preserves_history_and_offsets(tmp_path):
    from likewatch.storage import Store
    from likewatch.profiles import demo_profile
    store=Store(tmp_path/'history.sqlite3');p=demo_profile()
    store.enqueue(p,'TEST','retained');store.update_offset(p.id,123)
    snapshot=tmp_path/'snapshot.sqlite3';store.backup(snapshot)
    import sqlite3
    with sqlite3.connect(snapshot) as db:
        assert db.execute('SELECT count(*) FROM events').fetchone()[0]==1
        assert db.execute('SELECT offset FROM telegram_cursor').fetchone()[0]==123
    assert store.history(p.id)[0]['kind']=='TEST'


def test_manager_imports_no_application_stack():
    result=subprocess.run([os.sys.executable,'-c', "import likewatch_manager.deployment,sys;assert not any(n in sys.modules for n in ('likewatch','PySide6','cv2','numpy','tesserocr','keyring'))"],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_network_allowlist_rejects_credentials_and_other_origins():
    from likewatch_manager.releases import allowed
    for url in ('http://github.com/file', 'https://user:secret@github.com/file', 'https://evil.example/file', 'file:///tmp/file'):
        with pytest.raises(ManagerError): allowed(url)
    allowed('https://github.com/Hmmmmmmmmmm/LiKeWatch/releases/download/v0.3/release-manifest.json')


def test_future_database_is_not_mutated(tmp_path):
    from likewatch.storage import Store
    import sqlite3
    path=tmp_path/'new.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=999')
    before=path.read_bytes()
    with pytest.raises(ValueError,match='newer'): Store(path)
    assert path.read_bytes()==before


def test_test_context_blocks_real_credentials(monkeypatch,tmp_path):
    from likewatch.paths import RuntimeContext,context,configure
    from likewatch.messaging import deliver,poll_acknowledgements,save_token
    from likewatch.profiles import demo_profile
    previous=context()
    def forbidden(*args): raise AssertionError('Production keyring accessed')
    monkeypatch.setattr('keyring.get_password',forbidden)
    monkeypatch.setattr('keyring.set_password',forbidden)
    try:
        configure(RuntimeContext(test_mode=True))
        save_token('profile','fake')
        deliver(None,'profile')
        poll_acknowledgements(None,demo_profile())
    finally:
        configure(previous)


def test_streamed_payload_is_bounded_and_incomplete_files_are_removed(tmp_path, monkeypatch):
    from likewatch_manager.releases import Releases
    class Response(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 1024 * 1024
            return super().read(size)
    class Opener:
        def open(self, *args, **kwargs):
            return Response(b'x' * 2000000)
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    destination = tmp_path / 'download.part'
    client = Releases(tmp_path, [])
    assert client.get('https://github.com/file', 2000000, destination) == 2000000
    assert destination.stat().st_size == 2000000
    with pytest.raises(ManagerError, match='expected size'):
        client.get('https://github.com/file', 100, destination)
    assert not destination.exists()


def test_oversized_local_metadata_is_bounded(tmp_path):
    from likewatch_manager.common import read_bytes
    path = tmp_path / 'metadata'
    path.write_bytes(b'x' * 65)
    with pytest.raises(ManagerError, match='size limit'):
        read_bytes(path, 64)


def test_wheel_wrong_architecture_rejected():
    lock = {'schema': 1, 'platform': 'win-64', 'python': '3.13.15',
            'conda': [{'filename': 'python.conda', 'sha256': 'a' * 64}],
            'wheels': [{'filename': 'example-1.0-cp313-cp313-macosx_15_0_arm64.whl', 'sha256': 'b' * 64}], 'native': []}
    with pytest.raises(ManagerError, match='ABI'):
        validate_lock(lock)


def test_mismatched_trial_health_never_commits(tmp_path, monkeypatch):
    from likewatch_manager import supervisor
    from types import SimpleNamespace
    class Process:
        pid = 42
        def poll(self): return None
    context = dict(nonce='n', session='s', transaction='t', commit='a' * 40,
                   environment_id='b' * 64, source_root=str(tmp_path / 'source'), health_file=str(tmp_path / 'health.json'))
    atomic_json(context['health_file'], {'pid': 43, 'status': 'ready'})
    manager = SimpleNamespace(root=tmp_path, config={'data_root': str(tmp_path / 'data')},
        environments=SimpleNamespace(check=lambda _: None, prefix=lambda _: tmp_path),
        compatible=lambda *a: None, context=lambda *a, **kw: (context, tmp_path / 'context.json'))
    monkeypatch.setattr(supervisor.subprocess, 'Popen', lambda *a, **kw: Process())
    stopped = []
    monkeypatch.setattr(supervisor, 'stop_owned', lambda p: stopped.append(p.pid))
    with pytest.raises(ManagerError, match='different process'):
        supervisor.start(manager, {'environment_id': 'b' * 64})
    assert stopped == [42]
    assert not (tmp_path / 'state/deployment.json').exists()


def test_launcher_forwards_report_option_without_consuming_its_path(monkeypatch):
    from likewatch_manager import cli, supervisor
    sentinel = object()
    monkeypatch.setattr(cli, 'Manager', lambda root: sentinel)
    received = []
    monkeypatch.setattr(supervisor, 'run', lambda manager, arguments, **kwargs: received.append(arguments) or 0)
    assert cli.main(['--root', '/fixture', 'run', '--self-test', '--ui-stress', '--report', '/tmp/report with spaces.json']) == 0
    assert received == [['--self-test', '--ui-stress', '--report', '/tmp/report with spaces.json']]


def test_repair_requires_accepted_signature_before_mutating_installation(tmp_path, monkeypatch):
    from likewatch_manager.deployment import Manager
    monkeypatch.setattr('likewatch_manager.deployment.platform_id', lambda: 'osx-arm64')
    atomic_json(tmp_path / 'manager/config.json', {'schema': 1, 'platform': 'osx-arm64', 'public_keys': [],
        'fixture': True, 'remote': str(tmp_path / 'fixture-remote'), 'git': 'bin/git', 'conda': 'bin/conda'})
    deployment = {'commit': 'a' * 40, 'environment_id': 'b' * 64, 'version': '0.3.0', 'manifest_digest': 'c' * 64, 'profile_read': [1, 1], 'database_read': [0, 1]}
    state = {'schema': 1, 'generation': 1, 'active': deployment, 'previous': None, 'highest_sequence': 1}
    atomic_json(tmp_path / 'state/deployment.json', state)
    marker = tmp_path / 'envs' / ('app-' + 'b' * 64) / 'user-diagnostic.txt'
    marker.parent.mkdir(parents=True); marker.write_text('preserve me')
    manager = Manager(tmp_path)
    with pytest.raises(ManagerError, match='signed metadata'):
        manager.repair()
    assert marker.read_text() == 'preserve me'
    assert manager.state() == state
    assert not (tmp_path / 'preserved').exists()


def test_supervisor_pipe_eof_closes_window(monkeypatch):
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtTest import QTest
    from likewatch.lifecycle import watch_manager
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr('sys.stdin', SimpleNamespace(fileno=lambda: 123))
    monkeypatch.setattr('os.read', lambda descriptor, size: b'')
    window = QWidget(); window.show()
    watch_manager(window)
    QTest.qWait(300)
    assert not window.isVisible()
    window.manager_watch.stop()


def test_exported_schemas_match_typed_protocol_records():
    from likewatch_manager.models import RECORDS, json_schema
    root = Path(__file__).resolve().parents[1] / 'deployment/schemas'
    for record in RECORDS:
        expected = {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'title': record.__name__, **json_schema(record)}
        assert json.loads((root / (record.__name__ + '.json')).read_text()) == expected


@pytest.mark.parametrize('changes', [{'schema': True}, {'generation': 0}, {'highest_sequence': False}, {'unexpected': 'field'}])
def test_state_models_reject_malformed_fields(changes):
    from likewatch_manager.models import DeploymentState, validate
    deployment = {'commit': 'a' * 40, 'environment_id': 'b' * 64, 'version': '0.3.0', 'manifest_digest': 'c' * 64, 'profile_read': [1, 1], 'database_read': [0, 1]}
    state = {'schema': 1, 'generation': 1, 'active': deployment, 'previous': None, 'highest_sequence': 1, **changes}
    with pytest.raises(ManagerError): validate(state, DeploymentState)


def test_retention_inventory_detects_modified_or_added_files(tmp_path):
    from likewatch_manager.environments import Environments
    prefix = tmp_path / 'environment'; prefix.mkdir()
    (prefix / 'module.py').write_text('VALUE = 1')
    baseline = Environments.snapshot(prefix)
    (prefix / 'module.py').write_text('VALUE = 2')
    assert Environments.snapshot(prefix) != baseline
    (prefix / 'module.py').write_text('VALUE = 1')
    (prefix / 'user-note.txt').write_text('preserve')
    assert Environments.snapshot(prefix) != baseline


def test_retention_protects_active_previous_pending_and_modified_sources(tmp_path):
    from types import SimpleNamespace
    import shutil
    from likewatch_manager.retention import cleanup
    root = tmp_path
    def deployment(letter):
        return {'commit': letter * 40, 'environment_id': letter * 64, 'version': '0.3.0',
                'manifest_digest': 'f' * 64, 'profile_read': [1, 1], 'database_read': [0, 1]}
    records = {letter: deployment(letter) for letter in 'abcde'}
    state = {'schema': 1, 'generation': 2, 'active': records['a'], 'previous': records['b'], 'highest_sequence': 2}
    manifests = {'seed': records['d']}
    for letter, generation in (('c', 2), ('e', 1)):
        transaction = letter * 32
        atomic_json(root / 'state/transactions' / transaction / 'plan.json',
                    {'schema': 1, 'id': transaction, 'generation': generation, 'candidate': records[letter],
                     'sequence': 3, 'phase': 'validated', 'created': 1.0})
        manifests[transaction] = records[letter]
    for record in records.values():
        (root / 'releases' / record['commit']).mkdir(parents=True)
        (root / 'envs' / ('app-' + record['environment_id'])).mkdir(parents=True)
    def check(path, commit):
        if commit == records['e']['commit']:
            raise ManagerError('Modified source preserved')
    def call(*args):
        assert args[-3:-1] == ('worktree', 'remove')
        shutil.rmtree(args[-1])
    manager = SimpleNamespace(root=root, state=lambda: copy.deepcopy(state), accepted_manifest=lambda value: None,
        manifest=lambda folder, **kwargs: (manifests[folder.name], 'digest'), deployment=lambda value, digest: value,
        git=SimpleNamespace(repo=root / 'repo.git', check=check, call=call),
        environments=SimpleNamespace(unchanged=lambda identity: root / 'envs' / ('app-' + identity)))
    preview = cleanup(manager)
    assert preview['sources'] == [records['d']['commit']]
    assert preview['environments'] == [records['d']['environment_id']]
    assert (root / 'releases' / records['d']['commit']).exists()
    with locked(root / 'state/run.lock'):
        with pytest.raises(ManagerError): cleanup(manager, apply=True)
    result = cleanup(manager, apply=True)
    assert result['status'] == 'retention-cleaned'
    assert not (root / 'releases' / records['d']['commit']).exists()
    assert not (root / 'envs' / ('app-' + records['d']['environment_id'])).exists()
    for letter in 'abce':
        assert (root / 'releases' / records[letter]['commit']).exists()
        assert (root / 'envs' / ('app-' + records[letter]['environment_id'])).exists()
    assert manager.state() == state


@pytest.mark.parametrize('phase', ['prepared', 'validated', 'trial', 'health', 'previous', 'deployment', 'ack', 'committed'])
def test_process_exit_at_transaction_phase_preserves_coherent_tuple(tmp_path, phase):
    script = r'''
import os, sys
from pathlib import Path
from types import SimpleNamespace
from likewatch_manager import supervisor
from likewatch_manager.common import atomic_json, read_json
root=Path(sys.argv[1]); phase=sys.argv[2]
def record(letter):
 return dict(commit=letter*40,environment_id=letter*64,manifest_digest=letter*64,version='0.3.0',profile_read=[1,1],database_read=[0,1])
old=record('a');new=record('b')
state=dict(schema=1,generation=1,active=old,previous=None,highest_sequence=1)
atomic_json(root/'state/deployment.json',state)
if phase in ('prepared','validated'):
 atomic_json(root/'state/fixture-plan.json',dict(phase=phase,candidate=new))
 os._exit(91)
manager=SimpleNamespace(root=root,config={'data_root':str(root/'data')},state=lambda:read_json(root/'state/deployment.json'),check_source=lambda d:None,compatible=lambda *args:None)
def start(*args,**kwargs):
 if phase=='health':os._exit(91)
 return SimpleNamespace(),dict(nonce='c'*32,activated_file=str(root/'activated.json'))
supervisor.start=start
supervisor.stop_owned=lambda p:None
def write(path,value):
 atomic_json(path,value)
 label={'deployment.previous.json':'previous','deployment.json':'deployment','activated.json':'ack'}.get(Path(path).name)
 if Path(path).name=='journal.json':label=value['phase']
 if label==phase:os._exit(91)
supervisor.atomic_json=write
supervisor.activate(manager,dict(id='d'*32,generation=1,phase='validated',candidate=new,sequence=2))
'''
    process = subprocess.run([os.sys.executable, '-c', script, str(tmp_path), phase], capture_output=True, text=True)
    assert process.returncode == 91, process.stderr
    state = json.loads((tmp_path / 'state/deployment.json').read_text())
    selected = 'b' if phase in ('deployment', 'ack', 'committed') else 'a'
    assert state['active']['commit'] == selected * 40
    assert state['active']['environment_id'] == selected * 64
    assert state['generation'] == (2 if selected == 'b' else 1)


def test_rate_limit_honors_retry_after_and_blocks_repeat_request(tmp_path, monkeypatch):
    import urllib.error
    from likewatch_manager.releases import Releases
    calls = []
    class Opener:
        def open(self, request, **kwargs):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 429, 'limited', {'Retry-After': '180'}, None)
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    client = Releases(tmp_path, [])
    before = time.time()
    with pytest.raises(ManagerError, match='unknown'): client.get('https://api.github.com/rate')
    assert json.loads((tmp_path / 'state/network.json').read_text())['retry_after'] >= before + 180
    with pytest.raises(ManagerError, match='rate limited'): client.get('https://api.github.com/rate')
    assert len(calls) == 1


def test_signed_payload_reuse_url_is_official_and_bound(signed):
    key, public, value = signed
    payload = value['platforms']['osx-arm64']
    payload['payload_url'] = 'https://github.com/Hmmmmmmmmmm/LiKeWatch/releases/download/v0.3/environment.tar.gz'
    raw = canonical(value); assert verify(raw, key.sign(raw), [public])
    for url in ('https://evil.example/environment.tar.gz', 'https://github.com/other/repo/releases/download/v0.3/environment.tar.gz'):
        payload['payload_url'] = url; raw = canonical(value)
        with pytest.raises(ManagerError): verify(raw, key.sign(raw), [public])
