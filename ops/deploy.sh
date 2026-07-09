#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/image-web}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/image-web-deploy}"
STORAGE_DIR="${STORAGE_DIR:-/opt/image-web-storage}"
STATE_FILE="${STATE_FILE:-${DEPLOY_DIR}/last_deployed_sha}"
LOG_FILE="${LOG_FILE:-/var/log/image-web-deploy.log}"
ENV_FILE="${ENV_FILE:-${DEPLOY_DIR}/env}"
REPO_URL="${REPO_URL:-https://github.com/1264585648/image-web.git}"
BRANCH="${BRANCH:-main}"
IMAGE_REPO="${IMAGE_REPO:-image-web}"
IMAGE_NAME="${IMAGE_NAME:-${IMAGE_REPO}:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-image-web}"
PORT="${PORT:-8000}"
SMOKE_PORT="${SMOKE_PORT:-18000}"

exec >> "${LOG_FILE}" 2>&1

echo "===== $(date -Is) deploy check ====="

exec 9>/run/image-web-deploy.lock
if ! flock -n 9; then
  echo "Another deployment is already running; skipping."
  exit 0
fi

mkdir -p "${DEPLOY_DIR}" "${STORAGE_DIR}"

if [ ! -f "${ENV_FILE}" ]; then
  umask 077
  {
    printf 'AUTH_SECRET='
    head -c 48 /dev/urandom | base64 | tr -d '\n'
    printf '\nAUTH_COOKIE_NAME=productshot_session\n'
  } > "${ENV_FILE}"
fi
chmod 600 "${ENV_FILE}"

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

if [ -z "${AUTH_SECRET:-}" ]; then
  echo "AUTH_SECRET is required in ${ENV_FILE}."
  exit 1
fi
AUTH_COOKIE_NAME="${AUTH_COOKIE_NAME:-productshot_session}"

if [ ! -d "${APP_DIR}/.git" ]; then
  rm -rf "${APP_DIR}"
  git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

cd "${APP_DIR}"
git fetch --prune origin "${BRANCH}"
REMOTE_SHA="$(git rev-parse "origin/${BRANCH}")"
LAST_SHA="$(cat "${STATE_FILE}" 2>/dev/null || true)"

FORCE="false"
if [ "${1:-}" = "--force" ]; then
  FORCE="true"
fi

if [ "${FORCE}" != "true" ] && [ "${REMOTE_SHA}" = "${LAST_SHA}" ] && docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "No git change detected (${REMOTE_SHA}); container is running."
  exit 0
fi

PUBLIC_IP="$(curl -fsS -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip || true)"
if [ -z "${PUBLIC_BASE_URL:-}" ]; then
  if [ -n "${APP_HOSTNAME:-}" ]; then
    PUBLIC_BASE_URL="https://${APP_HOSTNAME}"
  elif [ -n "${PUBLIC_IP}" ]; then
    PUBLIC_BASE_URL="http://${PUBLIC_IP}:${PORT}"
  else
    PUBLIC_BASE_URL="http://localhost:${PORT}"
  fi
fi

echo "Deploying ${REMOTE_SHA}"
git reset --hard "origin/${BRANCH}"
git clean -fd

CANDIDATE_IMAGE="${IMAGE_REPO}:${REMOTE_SHA}"
SMOKE_CONTAINER="${CONTAINER_NAME}-smoke"
SMOKE_STORAGE="$(mktemp -d /tmp/image-web-smoke.XXXXXX)"
SMOKE_COOKIE_JAR="$(mktemp /tmp/image-web-cookie.XXXXXX)"
SMOKE_AUTH_RESPONSE="$(mktemp /tmp/image-web-auth.XXXXXX)"
SMOKE_UPLOAD_RESPONSE="$(mktemp /tmp/image-web-upload.XXXXXX)"
SMOKE_PNG="$(mktemp /tmp/image-web-product.XXXXXX.png)"

cleanup_smoke() {
  docker rm -f "${SMOKE_CONTAINER}" >/dev/null 2>&1 || true
  rm -rf "${SMOKE_STORAGE}" "${SMOKE_COOKIE_JAR}" "${SMOKE_AUTH_RESPONSE}" "${SMOKE_UPLOAD_RESPONSE}" "${SMOKE_PNG}" >/dev/null 2>&1 || true
}
trap cleanup_smoke EXIT

docker build --pull -f "${APP_DIR}/backend/Dockerfile" -t "${CANDIDATE_IMAGE}" "${APP_DIR}"

docker rm -f "${SMOKE_CONTAINER}" >/dev/null 2>&1 || true
docker run -d \
  --name "${SMOKE_CONTAINER}" \
  -p "127.0.0.1:${SMOKE_PORT}:8000" \
  -e ENVIRONMENT=production \
  -e DATABASE_URL="sqlite:////app/storage/app.db" \
  -e STORAGE_DIR="/app/storage" \
  -e PUBLIC_BASE_URL="http://127.0.0.1:${SMOKE_PORT}" \
  -e AUTH_SECRET="${AUTH_SECRET}" \
  -e AUTH_COOKIE_NAME="${AUTH_COOKIE_NAME}" \
  -v "${SMOKE_STORAGE}:/app/storage" \
  "${CANDIDATE_IMAGE}" >/dev/null

for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${SMOKE_PORT}/api/health" >/dev/null; then
    break
  fi
  if [ "${i}" = "30" ]; then
    echo "Smoke container did not become healthy."
    docker logs "${SMOKE_CONTAINER}" --tail 200 || true
    exit 1
  fi
  sleep 2
done

curl -fsS "http://127.0.0.1:${SMOKE_PORT}/api/templates" >/dev/null
UNAUTH_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:${SMOKE_PORT}/api/history?limit=1")"
if [ "${UNAUTH_STATUS}" != "401" ]; then
  echo "Expected unauthenticated history to return 401, got ${UNAUTH_STATUS}."
  exit 1
fi

SMOKE_EMAIL="deploy-${REMOTE_SHA}-$(date +%s)@example.test"
curl -fsS \
  -c "${SMOKE_COOKIE_JAR}" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"Deploy-smoke-123\",\"display_name\":\"Deploy Smoke\"}" \
  "http://127.0.0.1:${SMOKE_PORT}/api/auth/register" > "${SMOKE_AUTH_RESPONSE}"
SMOKE_TOKEN="$(sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p' "${SMOKE_AUTH_RESPONSE}")"
if [ -z "${SMOKE_TOKEN}" ]; then
  echo "Could not parse smoke access token."
  cat "${SMOKE_AUTH_RESPONSE}" || true
  exit 1
fi
curl -fsS -H "Authorization: Bearer ${SMOKE_TOKEN}" "http://127.0.0.1:${SMOKE_PORT}/api/auth/me" >/dev/null

printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=' | base64 -d > "${SMOKE_PNG}"
curl -fsS \
  -H "Authorization: Bearer ${SMOKE_TOKEN}" \
  -F "file=@${SMOKE_PNG};type=image/png;filename=smoke.png" \
  "http://127.0.0.1:${SMOKE_PORT}/api/upload" > "${SMOKE_UPLOAD_RESPONSE}"

echo "Smoke test passed for ${REMOTE_SHA}."

OLD_IMAGE="$(docker inspect -f '{{.Image}}' "${CONTAINER_NAME}" 2>/dev/null || true)"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "${PORT}:8000" \
  -e ENVIRONMENT=production \
  -e DATABASE_URL="sqlite:////app/storage/app.db" \
  -e STORAGE_DIR="/app/storage" \
  -e PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" \
  -e AUTH_SECRET="${AUTH_SECRET}" \
  -e AUTH_COOKIE_NAME="${AUTH_COOKIE_NAME}" \
  -v "${STORAGE_DIR}:/app/storage" \
  "${CANDIDATE_IMAGE}" >/dev/null

for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null; then
    docker tag "${CANDIDATE_IMAGE}" "${IMAGE_NAME}"
    echo "${REMOTE_SHA}" > "${STATE_FILE}"
    echo "Deployment healthy at ${PUBLIC_BASE_URL}"
    docker image prune -f --filter "dangling=true" >/dev/null 2>&1 || true
    exit 0
  fi
  sleep 2
done

echo "Deployment did not become healthy in time."
docker logs "${CONTAINER_NAME}" --tail 200 || true
if [ -n "${OLD_IMAGE}" ]; then
  echo "Attempting rollback to previous image ${OLD_IMAGE}."
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    -p "${PORT}:8000" \
    -e ENVIRONMENT=production \
    -e DATABASE_URL="sqlite:////app/storage/app.db" \
    -e STORAGE_DIR="/app/storage" \
    -e PUBLIC_BASE_URL="${PUBLIC_BASE_URL}" \
    -e AUTH_SECRET="${AUTH_SECRET}" \
    -e AUTH_COOKIE_NAME="${AUTH_COOKIE_NAME}" \
    -v "${STORAGE_DIR}:/app/storage" \
    "${OLD_IMAGE}" >/dev/null || true
fi
exit 1
