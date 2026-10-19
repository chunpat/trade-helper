#!/usr/bin/env bash
# 在生产服务器运行，第一参数为部署根目录，第二参数为已有 Compose 项目名。
set -euo pipefail

app_dir=${1:?缺少部署根目录}
project_name=${2:?缺少 Compose 项目名}
release_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[[ $app_dir = /* && $app_dir != / ]] || { echo '部署根目录无效' >&2; exit 1; }
[[ -s "$app_dir/.env" ]] || { echo '请先在部署根目录配置生产 .env 文件' >&2; exit 1; }
export DEPLOY_ENV_FILE="$app_dir/.env"
command -v flock >/dev/null
exec 9> "$app_dir/.deploy.lock"
flock -n 9 || { echo '已有部署正在执行' >&2; exit 1; }

read -r registry_user < "$release_dir/registry-user"
read -r registry_token
[[ -n $registry_user && -n $registry_token ]] || { echo '缺少镜像仓库凭证' >&2; exit 1; }
registry_config=$(mktemp -d)
trap 'rm -rf "$registry_config"' EXIT
export DOCKER_CONFIG="$registry_config"
printf '%s\n' "$registry_token" | docker login ghcr.io --username "$registry_user" --password-stdin
unset registry_token
docker compose version >/dev/null

compose() {
  local directory=$1
  shift
  # 文件由 CI 生成，只包含校验过的镜像名称和摘要。
  source "$directory/images.env"
  export BACKEND_IMAGE FRONTEND_IMAGE
  docker compose --project-name "$project_name" --env-file "$DEPLOY_ENV_FILE" \
    -f "$directory/docker-compose.yml" -f "$directory/docker-compose.prod.yml" \
    -f "$directory/docker-compose.deploy.yml" "$@"
}

apply_release() {
  local directory=$1
  compose "$directory" up -d --no-build --wait --wait-timeout 240 backend insight-worker polymarket-worker || return 1
  # 后端重建可能改变 IP，重新创建 Nginx 以刷新 upstream 的解析。
  compose "$directory" up -d --no-build --no-deps --force-recreate --wait --wait-timeout 120 frontend || return 1
  compose "$directory" exec -T frontend wget --quiet --tries=1 -O /dev/null http://backend:8000/health || return 1
}

previous_release=$(readlink -f "$app_dir/current" 2>/dev/null || true)
compose "$release_dir" config --quiet
# 拉取失败时保留当前容器，尚不执行服务切换。
compose "$release_dir" pull backend insight-worker polymarket-worker frontend
# 先完成幂等初始化与迁移，再同时启动三个后端角色。
compose "$release_dir" run --rm --no-deps backend python -c 'from app.core.database import init_db; init_db()'

if ! apply_release "$release_dir"; then
  echo '新版本健康检查失败' >&2
  compose "$release_dir" ps >&2 || true
  if [[ -n $previous_release && -f "$previous_release/images.env" ]]; then
    echo '正在恢复上一成功版本的容器；数据库变更不会撤销' >&2
    if ! apply_release "$previous_release"; then
      echo '上一版本恢复失败，请检查服务器服务状态' >&2
    fi
  else
    echo '首次部署没有可恢复的历史版本，请检查服务器服务状态' >&2
  fi
  exit 1
fi

ln -sfn "$release_dir" "$app_dir/current"
echo '前端、后端和两个 worker 均已通过健康检查'
