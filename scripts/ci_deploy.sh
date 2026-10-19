#!/usr/bin/env bash
# 在 GitHub Actions 中运行：只传部署清单，生产配置留在服务器。
set -euo pipefail

for variable in DEPLOY_HOST DEPLOY_USER DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS DEPLOY_PATH COMPOSE_PROJECT_NAME BACKEND_IMAGE FRONTEND_IMAGE GHCR_USER GHCR_TOKEN GITHUB_SHA GITHUB_RUN_ID GITHUB_RUN_ATTEMPT; do
  if [[ -z ${!variable:-} ]]; then
    echo "缺少配置：${variable}" >&2
    exit 1
  fi
done
DEPLOY_PORT=${DEPLOY_PORT:-22}
[[ $DEPLOY_HOST =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || { echo 'DEPLOY_HOST 必须为主机名或 IPv4 地址' >&2; exit 1; }
[[ $DEPLOY_USER =~ ^[a-zA-Z_][a-zA-Z0-9_-]*$ ]] || { echo 'DEPLOY_USER 格式无效' >&2; exit 1; }
[[ $DEPLOY_PORT =~ ^[0-9]+$ ]] && (( 10#$DEPLOY_PORT >= 1 && 10#$DEPLOY_PORT <= 65535 )) || { echo 'DEPLOY_PORT 格式无效' >&2; exit 1; }
[[ $DEPLOY_PATH =~ ^/[a-zA-Z0-9_/-]+$ && $DEPLOY_PATH != / ]] || { echo 'DEPLOY_PATH 必须是非根目录的绝对路径，仅支持字母、数字、下划线和连字符' >&2; exit 1; }
[[ $COMPOSE_PROJECT_NAME =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { echo 'COMPOSE_PROJECT_NAME 格式无效' >&2; exit 1; }
[[ $GITHUB_SHA =~ ^[a-f0-9]{40}$ && $GITHUB_RUN_ID =~ ^[0-9]+$ && $GITHUB_RUN_ATTEMPT =~ ^[0-9]+$ ]] || exit 1
for image in "$BACKEND_IMAGE" "$FRONTEND_IMAGE"; do
  [[ $image =~ ^ghcr\.io/[a-z0-9_./-]+@sha256:[a-f0-9]{64}$ ]] || { echo '部署必须使用 GHCR 镜像摘要' >&2; exit 1; }
done

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
umask 077
printf '%s\n' "$DEPLOY_SSH_KEY" | tr -d '\r' > "$work_dir/key"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$work_dir/known_hosts"
printf 'BACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\n' "$BACKEND_IMAGE" "$FRONTEND_IMAGE" > "$work_dir/images.env"
printf '%s\n' "$GHCR_USER" > "$work_dir/registry-user"
ssh_options=(-i "$work_dir/key" -p "$DEPLOY_PORT" -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$work_dir/known_hosts" -o ConnectTimeout=15 -o ServerAliveInterval=15 -o ServerAliveCountMax=4)
release_dir="${DEPLOY_PATH%/}/releases/${GITHUB_SHA}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
remote="${DEPLOY_USER}@${DEPLOY_HOST}"

tar -czf - docker-compose.yml docker-compose.prod.yml docker-compose.deploy.yml scripts/deploy.sh \
  -C "$work_dir" images.env registry-user |
  ssh "${ssh_options[@]}" "$remote" "mkdir -p '$release_dir' && tar -xzf - -C '$release_dir'"

# 临时令牌只经 SSH 标准输入传输，服务器使用临时 Docker 登录目录。
printf '%s\n' "$GHCR_TOKEN" |
  ssh "${ssh_options[@]}" "$remote" "bash '$release_dir/scripts/deploy.sh' '${DEPLOY_PATH%/}' '$COMPOSE_PROJECT_NAME'"

if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  {
    echo '### 生产部署成功'
    echo "- 版本：\`$GITHUB_SHA\`"
    echo "- 后端及 workers：\`$BACKEND_IMAGE\`"
    echo "- 前端：\`$FRONTEND_IMAGE\`"
  } >> "$GITHUB_STEP_SUMMARY"
fi
