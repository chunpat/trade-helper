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
    for filename in ('docker-compose.yml', 'docker-compose.prod.yml', 'docker-compose.deploy.yml'):
        command.extend(['-f', str(ROOT / filename)])
    result = subprocess.run(command + ['config', '--format', 'json'], env=env, text=True, capture_output=True, check=True)
    services = json.loads(result.stdout)['services']
    for name in ('backend', 'insight-worker', 'polymarket-worker'):
        service = services[name]
        assert 'build' not in service
        assert service['image'] == env['BACKEND_IMAGE']
        assert service['environment']['JWT_SECRET'] == 'test-only'
        assert service['healthcheck']['test'][1] == 'python'
    assert services['backend']['environment']['START_POSITION_SYNC'] == 'True'
    assert services['insight-worker']['environment']['START_ANOMALY_MONITOR'] == 'True'
    assert services['polymarket-worker']['environment']['START_POLYMARKET_TRADER_CACHE'] == 'True'
    assert 'build' not in services['frontend']
    assert services['frontend']['healthcheck']['test'][1] == 'wget'


def prepare_release(directory, marker):
    (directory / 'scripts').mkdir(parents=True)
    shutil.copy(ROOT / 'scripts/deploy.sh', directory / 'scripts/deploy.sh')
    (directory / 'images.env').write_text(f'BACKEND_IMAGE={marker}\nFRONTEND_IMAGE={marker}\n')
    (directory / 'registry-user').write_text('test-user\n')


@pytest.mark.parametrize('failure', ['', 'pull', 'migration', 'backend', 'frontend'])
def test_deploy_health_checks_and_rollback(tmp_path, failure):
    app = tmp_path / 'app'
    previous, release = app / 'releases/previous', app / 'releases/new'
    prepare_release(previous, 'previous')
    prepare_release(release, 'new')
    (app / '.env').write_text('TEST=true\n')
    (app / 'current').symlink_to(previous)
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    # 使用替身验证命令顺序和失败恢复，不执行任何 Docker 变更。
    docker = binaries / 'docker'
    docker.write_text(f'''#!{sys.executable}
import json, os, sys
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps({{'args': args, 'image': os.getenv('BACKEND_IMAGE'), 'config': os.getenv('DOCKER_CONFIG')}}) + '\\n')
if args[0] == 'login':
    assert sys.stdin.read().strip() == 'test-token'
if os.getenv('BACKEND_IMAGE') == 'new':
    failure = os.environ['FAILURE']
    if failure == 'pull' and 'pull' in args:
        sys.exit(1)
    if failure == 'migration' and 'run' in args:
        sys.exit(1)
    if 'up' in args and failure == 'backend' and args[-1] == 'polymarket-worker':
        sys.exit(1)
    if 'up' in args and failure == 'frontend' and args[-1] == 'frontend':
        sys.exit(1)
''')
    docker.chmod(0o755)
    # macOS 未自带 flock；此测试只验证发布流程，生产仍使用系统 flock。
    if not shutil.which('flock'):
        flock = binaries / 'flock'
        flock.write_text('#!/bin/sh\nexit 0\n')
        flock.chmod(0o755)
    log = tmp_path / 'commands.jsonl'
    env = {**os.environ, 'PATH': str(binaries) + os.pathsep + os.environ['PATH'],
           'COMMAND_LOG': str(log), 'FAILURE': failure}
    result = subprocess.run(['bash', str(release / 'scripts/deploy.sh'), str(app), 'trade-helper'],
                            env=env, input='test-token\n', text=True, capture_output=True)
    assert (result.returncode == 0) == (not failure), result.stderr
    assert (app / 'current').resolve() == (previous if failure else release)
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    starts = [entry for entry in commands if 'up' in entry['args']]
    if failure in ('pull', 'migration'):
        assert not starts
    elif failure:
        assert any(entry['image'] == 'previous' for entry in starts)
    else:
        migration_index = next(i for i, entry in enumerate(commands) if 'run' in entry['args'])
        first_start_index = next(i for i, entry in enumerate(commands) if 'up' in entry['args'])
        assert migration_index < first_start_index
        assert starts[0]['args'][-3:] == ['backend', 'insight-worker', 'polymarket-worker']
        assert starts[1]['args'][-1] == 'frontend'
        assert '--force-recreate' in starts[1]['args']
    assert not any('down' in entry['args'] for entry in commands)
    assert not Path(commands[0]['config']).exists()
    assert 'test-token' not in result.stdout + result.stderr


def test_ci_rejects_missing_deployment_configuration():
    env = {key: value for key, value in os.environ.items() if not key.startswith('DEPLOY_')}
    result = subprocess.run(['bash', str(ROOT / 'scripts/ci_deploy.sh')], env=env, text=True, capture_output=True)
    assert result.returncode != 0
    assert '缺少配置：DEPLOY_HOST' in result.stderr
