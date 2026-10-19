#!/usr/bin/env bash
# 在生产服务器运行，第一参数为部署根目录，第二参数为已有 Compose 项目名。
set -euo pipefail

app_dir=${1:?缺少部署根目录}
project_name=${2:?缺少 Compose 项目名}
frontend_mode=${3:-docker}
site_host=${4:-tradehelper.chunpat.com}
[[ $frontend_mode == baota || $frontend_mode == docker ]] || { echo '前端部署模式无效' >&2; exit 1; }
[[ $site_host =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || { echo '站点域名无效' >&2; exit 1; }
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
extract_container=''
cleanup() {
  if [[ -n $extract_container ]]; then
    docker rm "$extract_container" >/dev/null 2>&1 || true
  fi
  rm -rf "$registry_config"
}
trap cleanup EXIT
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
    -f "$directory/docker-compose.deploy.yml" -f "$release_dir/docker-compose.polymarket-paused.yml" "$@"
}

original_frontend=$(readlink -f "$app_dir/frontend/dist" 2>/dev/null || true)
activate_frontend() {
  local directory=$1
  local live="$app_dir/frontend/dist"
  [[ -s "$directory/frontend-dist/index.html" ]] || { echo '缺少前端构建产物' >&2; return 1; }
  mkdir -p "$app_dir/frontend" || return 1
  # 首次接入时保留宝塔原有静态文件；后续只切换链接，不改 Nginx 配置。
  if [[ -d $live && ! -L $live ]]; then
    local backup
    backup=$(mktemp -d "$app_dir/releases/frontend-backup.XXXXXX") || return 1
    chmod a+rx "$backup" || return 1
    mv "$live" "$backup/frontend-dist" || return 1
    original_frontend="$backup/frontend-dist"
  fi
  ln -sfn "$directory/frontend-dist" "$live" || return 1
  # 通过本机宝塔 HTTPS 入口核验实际返回的是本次构建的首页。
  curl --fail --silent --show-error --max-time 15 \
    --resolve "$site_host:443:127.0.0.1" "https://$site_host/" \
    -o "$directory/served-index.html" || return 1
  cmp -s "$directory/frontend-dist/index.html" "$directory/served-index.html"
}

apply_release() {
  local directory=$1
  compose "$directory" up -d --no-build --wait --wait-timeout 240 backend insight-worker || return 1
  if [[ $frontend_mode == baota ]]; then
    activate_frontend "$directory" || return 1
    curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8029/health -o /dev/null || return 1
  else
    # 后端重建可能改变 IP，重新创建 Nginx 以刷新 upstream 的解析。
    compose "$directory" up -d --no-build --no-deps --force-recreate --wait --wait-timeout 120 frontend || return 1
    compose "$directory" exec -T frontend wget --quiet --tries=1 -O /dev/null http://backend:8000/health || return 1
  fi
}

previous_release=$(readlink -f "$app_dir/current" 2>/dev/null || true)
compose "$release_dir" config --quiet
# 拉取失败时保留当前容器，尚不执行服务切换。
compose "$release_dir" pull backend insight-worker frontend
# 暂停旧 worker，并关闭其自动重启；不删除容器或数据卷。
docker ps -aq --filter "label=com.docker.compose.project=$project_name" \
  --filter 'label=com.docker.compose.service=polymarket-worker' |
  while IFS= read -r worker_id; do
    [[ -n $worker_id ]] || continue
    docker update --restart=no "$worker_id" >/dev/null
    docker stop "$worker_id" >/dev/null
  done
if [[ $frontend_mode == baota ]]; then
  # 只从前端镜像取出静态文件，不启动第二套 Nginx，也不在服务器编译。
  chmod a+rx "$app_dir/releases" "$release_dir"
  mkdir -p "$release_dir/frontend-dist"
  extract_container=$(docker create "$FRONTEND_IMAGE")
  docker cp "$extract_container:/usr/share/nginx/html/." "$release_dir/frontend-dist/"
  docker rm "$extract_container" >/dev/null
  extract_container=''
  [[ -s "$release_dir/frontend-dist/index.html" ]] || { echo '镜像中缺少前端首页' >&2; exit 1; }
  chmod -R a+rX "$release_dir/frontend-dist"
fi
# 先完成幂等初始化与迁移，再启动 API 和市场洞察服务。
compose "$release_dir" run --rm --no-deps backend python -c 'from app.core.database import init_db; init_db()'

if ! apply_release "$release_dir"; then
  echo '新版本健康检查失败' >&2
  compose "$release_dir" ps >&2 || true
  # 先恢复静态入口，即使后端回退失败，也不让站点停留在失败版本的首页。
  if [[ $frontend_mode == baota && -n $original_frontend && -d $original_frontend ]]; then
    if [[ -L $app_dir/frontend/dist || ! -e $app_dir/frontend/dist ]]; then
      if ln -sfn "$original_frontend" "$app_dir/frontend/dist"; then
        echo '已恢复宝塔原有前端文件' >&2
      else
        echo '前端链接恢复失败，请检查服务器目录权限' >&2
      fi
    fi
  fi
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
echo "前端（${frontend_mode}）、后端和市场洞察 worker 均已通过健康检查；Polymarket 保持暂停"
