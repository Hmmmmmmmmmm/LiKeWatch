"""Install and launch an actual fixture artifact offline with system-only PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--installer', required=True)
    p.add_argument('--prefix', required=True)
    p.add_argument('--report', required=True)
    args = p.parse_args()
    prefix = Path(args.prefix).resolve()
    if prefix.exists():
        raise RuntimeError('Installer qualification requires a new disposable prefix')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('CONDA', 'PYTHON', 'QT_', 'TESSDATA', 'LIKEWATCH'))}
    env.update(CONDA_OFFLINE='true', HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9', ALL_PROXY='http://127.0.0.1:9')
    if sys.platform == 'win32':
        env['PATH'] = os.environ['SystemRoot'] + '\\System32;' + os.environ['SystemRoot']
        command = [str(Path(args.installer).resolve()), '/InstallationType=JustMe', '/RegisterPython=0', '/AddToPath=0', '/S', '/D=' + str(prefix)]
        python = prefix / 'python.exe'
    else:
        env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
        command = ['/bin/bash', str(Path(args.installer).resolve()), '-b', '-p', str(prefix)]
        python = prefix / 'bin/python'
    try:
        subprocess.run(command, env=env, check=True, timeout=900)
    except subprocess.CalledProcessError:
        for log in (prefix / 'install.log', prefix / '.step.log'):
            if log.exists():
                print(log.read_text(errors='replace')[-12000:], flush=True)
        raise
    marker = json.loads((prefix / 'state/install-complete.json').read_text())
    if not marker:
        raise RuntimeError('Installer did not complete native validation')
    launcher = prefix / ('RunLiKeWatch.cmd' if sys.platform == 'win32' else 'RunLiKeWatch.command')
    arguments = [str(launcher), 'run', '--self-test', '--ui-stress', '--report', str(Path(args.report).resolve())]
    if sys.platform == 'win32':
        arguments = [os.environ['SystemRoot'] + '\\System32\\cmd.exe', '/d', '/c', *arguments]
    subprocess.run(arguments, env=env, cwd=prefix.parent, check=True, timeout=180)
    report = json.loads(Path(args.report).read_text())
    if report['status'] != 'passed' or report['values'] != ['83.2', '18.4']:
        raise RuntimeError('Installed launcher failed OCR qualification')
    print('Offline installed launcher and real OCR passed')


if __name__ == '__main__':
    main()
