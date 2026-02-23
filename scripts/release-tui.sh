#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

VERSION="$(date -u +%Y.%m.%d)"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

DIST_DIR="${ROOT_DIR}/dist"
PKG_NAME="fin-agent-tui-${VERSION}"
PKG_DIR="${DIST_DIR}/${PKG_NAME}"
ARCHIVE_PATH="${DIST_DIR}/${PKG_NAME}.tar.gz"
SHA_PATH="${ARCHIVE_PATH}.sha256"

if [[ ${DRY_RUN} -eq 1 ]]; then
  echo "release dry-run"
  echo "version=${VERSION}"
  echo "package_dir=${PKG_DIR}"
  echo "archive=${ARCHIVE_PATH}"
  exit 0
fi

rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}"
mkdir -p "${DIST_DIR}"

mkdir -p "${PKG_DIR}/scripts"
cp README.md "${PKG_DIR}/README.md"
if [[ ! -f LICENSE ]]; then
  echo "missing LICENSE file; cannot build release package" >&2
  exit 1
fi
cp LICENSE "${PKG_DIR}/LICENSE"
cp .env.example "${PKG_DIR}/.env.example"
cp scripts/*.sh "${PKG_DIR}/scripts/"

mkdir -p "${PKG_DIR}/py"
cp -r py/fin_agent py/pyproject.toml py/tests "${PKG_DIR}/py/"

mkdir -p "${PKG_DIR}/apps/fin-agent/src"
cp apps/fin-agent/package.json apps/fin-agent/package-lock.json "${PKG_DIR}/apps/fin-agent/"
cp -r apps/fin-agent/src/. "${PKG_DIR}/apps/fin-agent/src/"

mkdir -p "${PKG_DIR}/apps/fin-agent-web/src"
mkdir -p "${PKG_DIR}/apps/fin-agent-web/dist"
cp apps/fin-agent-web/package.json apps/fin-agent-web/index.html apps/fin-agent-web/vite.config.js "${PKG_DIR}/apps/fin-agent-web/"
cp -r apps/fin-agent-web/src/. "${PKG_DIR}/apps/fin-agent-web/src/"
cp -r apps/fin-agent-web/dist/. "${PKG_DIR}/apps/fin-agent-web/dist/"

mkdir -p "${PKG_DIR}/.opencode"
cp -r .opencode/commands .opencode/plugins .opencode/rules .opencode/skills .opencode/tools "${PKG_DIR}/.opencode/"
cp .opencode/package.json "${PKG_DIR}/.opencode/package.json"

mkdir -p "${PKG_DIR}/docs/runbooks"
cp docs/runbooks/stage1-operator.md "${PKG_DIR}/docs/runbooks/stage1-operator.md"
cp docs/runbooks/publish-stage1.md "${PKG_DIR}/docs/runbooks/publish-stage1.md"

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo "nogit")"
cat > "${PKG_DIR}/RELEASE_MANIFEST.txt" <<EOF
package=${PKG_NAME}
version=${VERSION}
built_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
git_sha=${GIT_SHA}
EOF

tar -C "${DIST_DIR}" -czf "${ARCHIVE_PATH}" "${PKG_NAME}"
sha256sum "${ARCHIVE_PATH}" > "${SHA_PATH}"

echo "release package created"
echo "archive=${ARCHIVE_PATH}"
echo "sha256=${SHA_PATH}"
