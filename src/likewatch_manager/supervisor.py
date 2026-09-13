"""One parent process supervises app lifetimes and commits only a matching trial."""
import os
from pathlib import Path
import signal
import subprocess
import time
from .common import ManagerError, atomic_json, locked, read_json
from .environments import interpreter, scoped_environment


def user_data(manager):
    from platformdirs import user_data_dir
    return manager.config.get('data_root') or user_data_dir('LiKeWatch', 'LiKeWatch')


def stop_owned(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/taskkill.exe'), '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def start(manager, deployment, transaction='', arguments=()):
    manager.environments.check(deployment['environment_id'])
    data_root = user_data(manager)
    manager.compatible(deployment, data_root)
    value, context_file = manager.context(deployment, transaction=transaction, data_root=data_root,
                                          test=manager.config.get('isolated_app', False))
    prefix = manager.environments.prefix(deployment['environment_id'])
    env = scoped_environment(prefix, value)
    log = (context_file.parent / 'application.log').open('ab')
    try:
        process = subprocess.Popen([str(interpreter(prefix)), '-I', '-B', str(manager.root / 'manager/runner.py'), str(context_file), *arguments],
                                   env=env, cwd=context_file.parent, stdout=log, stderr=log,
                                   start_new_session=os.name != 'nt', creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
    finally:
        log.close()
    deadline = time.monotonic() + 60
    try:
        while time.monotonic() < deadline:
            path = Path(value['health_file'])
            if path.exists():
                report = read_json(path)
                expected = {key: value[key] for key in ('nonce', 'session', 'transaction', 'commit', 'environment_id')}
                expected.update(schema=1, pid=process.pid, status='ready', source=value['source_root'], python=str(interpreter(prefix)))
                if report != expected:
                    raise ManagerError('Trial startup reported a different process/source/environment')
                if process.poll() is not None:
                    raise ManagerError('Application exited before startup was acknowledged')
                return process, value
            if process.poll() is not None:
                raise ManagerError('Application did not reach readiness; inspect session logs (another instance may own the data)')
            time.sleep(0.1)
        raise ManagerError('Application startup timed out; active deployment unchanged')
    except BaseException:
        stop_owned(process)
        raise


def activate(manager, plan):
    state = manager.state()
    if plan['generation'] != state['generation'] or plan['phase'] != 'validated':
        raise ManagerError('Activation requires a current validated plan')
    transaction = plan['id']
    folder = manager.root / 'state/transactions' / transaction
    atomic_json(folder / 'journal.json', {'schema': 1, 'phase': 'trial', 'generation': state['generation'], 'candidate': plan['candidate']})
    process, value = start(manager, plan['candidate'], transaction=transaction)
    try:
        manager.check_source(plan['candidate'])
        manager.compatible(plan['candidate'], user_data(manager))
        new = {'schema': 1, 'generation': state['generation'] + 1, 'active': plan['candidate'],
               'previous': state['active'], 'highest_sequence': max(state['highest_sequence'], plan['sequence'])}
        atomic_json(manager.root / 'state/deployment.previous.json', state)
        atomic_json(manager.root / 'state/deployment.json', new)
        atomic_json(Path(value['activated_file']), {'nonce': value['nonce']})
        atomic_json(folder / 'journal.json', {'schema': 1, 'phase': 'committed', 'generation': new['generation']})
        return process, value
    except BaseException:
        stop_owned(process)
        raise


def run(manager, arguments=(), transaction=None, rollback=False):
    with locked(manager.root / 'state/run.lock'):
        if rollback:
            with locked(manager.root / 'state/update.lock'):
                state = manager.state()
                previous = state.get('previous')
                if not previous:
                    raise ManagerError('No previous deployment is available')
                manager.compatible(previous, user_data(manager))
                manager.validate(previous)
                import uuid
                plan = {'id': uuid.uuid4().hex, 'generation': state['generation'], 'phase': 'validated',
                        'candidate': previous, 'sequence': state['highest_sequence']}
                process, value = activate(manager, plan)
        elif transaction:
            with locked(manager.root / 'state/update.lock'):
                process, value = activate(manager, manager.plan(transaction))
        else:
            process, value = start(manager, manager.state()['active'], arguments=arguments)
        while True:
            # A healthy ordinary exit never rolls back or starts another GUI.
            code = process.wait()
            if code != 75:
                return code
            request = read_json(value['request_file'])
            if request.get('session') != value['session'] or request.get('nonce') != value['nonce']:
                raise ManagerError('Restart request belongs to another launch')
            try:
                with locked(manager.root / 'state/update.lock'):
                    process, value = activate(manager, manager.plan(request['transaction']))
            except ManagerError as error:
                # One fallback only; no loop if previous startup also fails.
                print(f'Update not activated: {error}', flush=True)
                process, value = start(manager, manager.state()['active'])
