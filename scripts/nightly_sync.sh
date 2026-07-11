#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
reason="${1:-scheduled_daily}"

config_path="${WECHAT_FETCHER_CONFIG:-config.ima.json}"
ima_script="${WECHAT_FETCHER_IMA_SCRIPT:-/home/andrey/.openclaw-ima/workspace/skills/ima-skill/ima_api.cjs}"
node_bin="${WECHAT_FETCHER_NODE_BIN:-/home/andrey/.openclaw-runtime/tools/node-v22.22.0/bin/node}"

publish_root="$(mktemp -d "${repo}/.nightly-publish.XXXXXX")"
worktree_dir="${publish_root}/worktree"
staging_dir="${publish_root}/staging"
pages_relative_path="site_output/_pages"
pages_artifact_dir="${repo}/${pages_relative_path}"
today="$(date +%F)"
ima_output_file="$(mktemp)"

cleanup() {
  cd "${repo}" >/dev/null 2>&1 || true
  if [ -d "${worktree_dir}" ]; then
    git worktree remove "${worktree_dir}" --force >/dev/null 2>&1 || true
  fi
  rm -rf "${publish_root}" "${ima_output_file}"
}
trap cleanup EXIT

reset_directory() {
  local path="$1"
  rm -rf "${path}"
  mkdir -p "${path}"
}

export PATH="/home/andrey/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"
export HTTP_PROXY="${HTTP_PROXY:-http://192.168.50.1:8899}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://192.168.50.1:8899}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1,192.168.50.1,192.168.50.2,essmaster}"
export NODE_USE_ENV_PROXY=1
export WECHAT_FETCHER_NODE_BIN="${node_bin}"

echo "== nightly sync start =="
echo "repo: ${repo}"
echo "date: ${today}"
echo "reason: ${reason}"

cd "${repo}"
. .venv/bin/activate

echo "== ima sync =="
extra_args=()
if [ "${reason}" = "monthly_audit" ]; then
  extra_args+=(--full-rescan)
fi

python run_fetcher.py \
  --config "${config_path}" \
  --mode ima \
  --reason "${reason}" \
  --ima-script "${ima_script}" \
  "${extra_args[@]}" | tee "${ima_output_file}"

ima_sync_result="$(grep '^IMA_SYNC_RESULT=' "${ima_output_file}" | tail -n 1 | sed 's/^IMA_SYNC_RESULT=//')"
skip_publish="0"
if [ -n "${ima_sync_result}" ]; then
  skip_publish="$(python3 -c 'import json,sys; data=json.loads(sys.argv[1]); print("1" if data.get("status")=="partial" and data.get("quota_exhausted") is True and int(data.get("rendered_pages",0))==0 and int(data.get("updated_indexes",0))==0 else "0")' "${ima_sync_result}")"
fi

if [ "${skip_publish}" = "1" ]; then
  echo "quota-limited partial sync without new pages; skipping publish"
  echo "== nightly sync done =="
  exit 0
fi

echo "== pages build =="
python run_fetcher.py --config "${config_path}" --mode pages

if [ ! -d "${pages_artifact_dir}" ]; then
  echo "pages artifact not found: ${pages_artifact_dir}" >&2
  exit 1
fi

echo "== prepare publish worktree =="
git worktree add --detach "${worktree_dir}" HEAD

reset_directory "${staging_dir}"
cp -a "${pages_artifact_dir}/." "${staging_dir}/"

worktree_pages_dir="${worktree_dir}/${pages_relative_path}"
reset_directory "${worktree_pages_dir}"
cp -a "${staging_dir}/." "${worktree_pages_dir}/"

cd "${worktree_dir}"
if ! git config user.name >/dev/null; then
  git config user.name "andyzhao2025"
fi
if ! git config user.email >/dev/null; then
  git config user.email "253004644@qq.com"
fi

status_output="$(git status --porcelain -- "${pages_relative_path}")"
if [ -z "${status_output}" ]; then
  echo "no pages changes detected"
  echo "== nightly sync done =="
  exit 0
fi

echo "== commit publish artifact =="
git add "${pages_relative_path}"
git commit -m "chore: ${reason} sync ${today}"
git push origin HEAD:main
echo "pages changes committed and pushed"
echo "== nightly sync done =="
