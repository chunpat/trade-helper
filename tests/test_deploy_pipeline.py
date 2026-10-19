"""验证部署配置和发布顺序，不连接服务器、不创建容器。"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_compose_deployment_uses_images_and_preserves_roles(tmp_path):
    if not shutil.which('docker'):
        pytest.skip('需要 Docker Compose CLI，仅执行 config，不连接 daemon')
    env_file = tmp_path / '.env'
    env_file.write_text('DB_HOST=host.docker.internal\nDB_USER=test\nDB_PASSWORD=test-only\nDB_NAME=test\nJWT_SECRET=test-only\nREDIS_HOST=redis\n')
    env = {**os.environ, 'DEPLOY_ENV_FILE': str(env_file),
           'JWT_SECRET': 'test-only',
           'BACKEND_IMAGE': 'ghcr.io/test/backend@sha256:' + 'a' * 64,
           'FRONTEND_IMAGE': 'ghcr.io/test/frontend@sha256:' + 'b' * 64}
    command = ['docker', 'compose', '--env-file', str(env_file)]
    for filename in ('docker-compose.yml', 'docker-compose.prod.yml', 'docker-compose.deploy.yml', 'docker-compose.polymarket-paused.yml'):
        command.extend(['-f', str(ROOT / filename)])
    default_services = subprocess.run(command + ['config', '--services'], env=env, text=True, capture_output=True, check=True)
    assert 'polymarket-worker' not in default_services.stdout.splitlines()
    result = subprocess.run(command + ['--profile', 'polymarket', 'config', '--format', 'json'], env=env, text=True, capture_output=True, check=True)
    services = json.loads(result.stdout)['services']
    for name in ('backend', 'insight-worker', 'polymarket-worker'):
        service = services[name]
        assert 'build' not in service
        assert service['image'] == env['BACKEND_IMAGE']
        assert service['environment']['JWT_SECRET'] == 'test-only'
        assert service['healthcheck']['test'][1] == 'python'
        assert service['logging']['options'] == {'max-size': '20m', 'max-file': '3'}
        assert 'host.docker.internal=host-gateway' in service['extra_hosts']
        assert service['environment']['START_POLYMARKET_TRADER_CACHE'] == 'False'
        assert service['environment']['START_POLYMARKET_COPY_RUNNER'] == 'False'
    assert services['backend']['environment']['START_POSITION_SYNC'] == 'True'
    assert services['insight-worker']['environment']['START_ANOMALY_MONITOR'] == 'True'
    assert services['polymarket-worker']['restart'] == 'no'
    assert 'build' not in services['frontend']
    assert services['frontend']['healthcheck']['test'][1] == 'wget'


def prepare_release(directory, marker):
    (directory / 'scripts').mkdir(parents=True)
    shutil.copy(ROOT / 'scripts/deploy.sh', directory / 'scripts/deploy.sh')
    shutil.copy(ROOT / 'docker-compose.polymarket-paused.yml', directory / 'docker-compose.polymarket-paused.yml')
    (directory / 'images.env').write_text(f'BACKEND_IMAGE={marker}\nFRONTEND_IMAGE={marker}\n')
    (directory / 'registry-user').write_text('test-user\n')
    (directory / 'frontend-dist').mkdir()
    (directory / 'frontend-dist/index.html').write_text(marker)


@pytest.mark.parametrize('failure', ['', 'pull', 'migration', 'backend', 'frontend'])
@pytest.mark.parametrize('mode', ['docker', 'baota'])
@pytest.mark.parametrize('has_previous', [True, False])
def test_deploy_health_checks_and_rollback(tmp_path, failure, mode, has_previous):
    app = tmp_path / 'app'
    previous, release = app / 'releases/previous', app / 'releases/new'
    prepare_release(previous, 'previous')
    prepare_release(release, 'new')
    if mode == 'baota':
        shutil.rmtree(release / 'frontend-dist')
    (app / '.env').write_text('TEST=true\n')
    if has_previous:
        (app / 'current').symlink_to(previous)
    (app / 'frontend').mkdir()
    if has_previous:
        (app / 'frontend/dist').symlink_to(previous / 'frontend-dist')
    else:
        (app / 'frontend/dist').mkdir()
        (app / 'frontend/dist/index.html').write_text('manual-deployment')
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    # 使用替身验证命令顺序和失败恢复，不执行任何 Docker 变更。
    docker = binaries / 'docker'
    docker.write_text(f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps({{'args': args, 'image': os.getenv('BACKEND_IMAGE'), 'config': os.getenv('DOCKER_CONFIG')}}) + '\\n')
if args[0] == 'login':
    assert sys.stdin.read().strip() == 'test-token'
if args[0] == 'create':
    print('temporary-extract-container')
if args[:2] == ['ps', '-aq']:
    print('paused-worker')
if args[0] == 'cp':
    (Path(args[-1]) / 'index.html').write_text('new')
if os.getenv('BACKEND_IMAGE') == 'new':
    failure = os.environ['FAILURE']
    if failure == 'pull' and 'pull' in args:
        sys.exit(1)
    if failure == 'migration' and 'run' in args:
        sys.exit(1)
    if 'up' in args and failure == 'backend' and args[-1] == 'insight-worker':
        sys.exit(1)
    if 'up' in args and failure == 'frontend' and args[-1] == 'frontend':
        sys.exit(1)
''')
    docker.chmod(0o755)
    curl = binaries / 'curl'
    curl.write_text(f'''#!{sys.executable}
import os, sys
from pathlib import Path
args = sys.argv[1:]
if '--resolve' in args:
    live = Path(os.environ['APP_DIR']) / 'frontend/dist/index.html'
    if os.environ['FAILURE'] == 'frontend' and live.read_text() == 'new':
        sys.exit(22)
    Path(args[args.index('-o') + 1]).write_text(live.read_text())
''')
    curl.chmod(0o755)
    # macOS 未自带 flock；此测试只验证发布流程，生产仍使用系统 flock。
    if not shutil.which('flock'):
        flock = binaries / 'flock'
        flock.write_text('#!/bin/sh\nexit 0\n')
        flock.chmod(0o755)
    log = tmp_path / 'commands.jsonl'
    env = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
           'COMMAND_LOG': str(log), 'FAILURE': failure, 'APP_DIR': str(app)}
    result = subprocess.run(['bash', str(release / 'scripts/deploy.sh'), str(app), 'trade-helper', mode],
                            env=env, input='test-token\n', text=True, capture_output=True)
    assert (result.returncode == 0) == (not failure), result.stderr
    if not failure:
        assert (app / 'current').resolve() == release
    elif has_previous:
        assert (app / 'current').resolve() == previous
    else:
        assert not (app / 'current').exists()
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    starts = [entry for entry in commands if 'up' in entry['args']]
    if failure in ('pull', 'migration'):
        assert not starts
    elif failure and has_previous:
        assert any(entry['image'] == 'previous' for entry in starts)
    elif not failure:
        migration_index = next(i for i, entry in enumerate(commands) if 'run' in entry['args'])
        first_start_index = next(i for i, entry in enumerate(commands) if 'up' in entry['args'])
        assert migration_index < first_start_index
        assert starts[0]['args'][-2:] == ['backend', 'insight-worker']
        if mode == 'docker':
            assert starts[1]['args'][-1] == 'frontend'
            assert '--force-recreate' in starts[1]['args']
    if mode == 'baota':
        assert all('frontend' not in entry['args'] for entry in starts)
        expected = ('previous' if has_previous else 'manual-deployment') if failure else 'new'
        assert (app / 'frontend/dist/index.html').read_text() == expected
        if not failure:
            assert (app / 'frontend/dist').is_symlink()
        if failure not in ('pull',):
            assert any(entry['args'] == ['rm', 'temporary-extract-container'] for entry in commands)
    assert not any('down' in entry['args'] for entry in commands)
    assert all('polymarket-worker' not in entry['args'] for entry in starts)
    assert all(str(release / 'docker-compose.polymarket-paused.yml') in entry['args'] for entry in starts)
    if failure != 'pull':
        assert any(entry['args'] == ['update', '--restart=no', 'paused-worker'] for entry in commands)
        assert any(entry['args'] == ['stop', 'paused-worker'] for entry in commands)
    assert not Path(commands[0]['config']).exists()
    assert 'test-token' not in result.stdout + result.stderr


def test_ci_rejects_missing_deployment_configuration():
    env = {key: value for key, value in os.environ.items() if not key.startswith('DEPLOY_')}
    result = subprocess.run(['bash', str(ROOT / 'scripts/ci_deploy.sh')], env=env, text=True, capture_output=True)
    assert result.returncode != 0
    assert '缺少配置：DEPLOY_HOST' in result.stderr
