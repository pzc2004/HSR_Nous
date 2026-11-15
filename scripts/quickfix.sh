#!/bin/bash
# quickfix 安全通道：显式路径 → 检查 → 测试 → 提交；push/PR 需显式开启，不自动合并。
set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
  cat >&2 <<'EOF'
用法: scripts/quickfix.sh "提交信息" 分支名 路径 [路径 ...]

环境变量：
  QUICKFIX_DRY_RUN=0   执行提交（默认只打印计划，不修改仓库）
  QUICKFIX_TEST_CMD    默认 .venv/bin/python -m pytest tests/ -q -rs
  QUICKFIX_PUSH=1      测试通过后 push 临时分支（默认 0）
  QUICKFIX_CREATE_PR=1 创建 PR（默认 0；必须同时 QUICKFIX_PUSH=1）
EOF
}

if [ "$#" -lt 3 ]; then
  usage
  exit 2
fi

msg=$1
branch=$2
shift 2
paths=("$@")
dry_run=${QUICKFIX_DRY_RUN:-1}
push=${QUICKFIX_PUSH:-0}
create_pr=${QUICKFIX_CREATE_PR:-0}
test_cmd=${QUICKFIX_TEST_CMD:-'.venv/bin/python -m pytest tests/ -q -rs'}

if [ "$create_pr" = 1 ] && [ "$push" != 1 ]; then
  echo "QUICKFIX_CREATE_PR=1 需要同时 QUICKFIX_PUSH=1" >&2
  exit 2
fi
if [ "$create_pr" = 1 ] && ! command -v gh >/dev/null 2>&1; then
  echo "创建 PR 需要 gh CLI" >&2
  exit 2
fi

python3 - "${paths[@]}" <<'PY'
import subprocess
import sys

allowed = sys.argv[1:]
changed = set()
for command in (
    ["git", "diff", "--name-only"],
    ["git", "diff", "--cached", "--name-only"],
    ["git", "ls-files", "--others", "--exclude-standard"],
):
    changed.update(subprocess.check_output(command, text=True).splitlines())

for path in sorted(changed):
    if not any(path == root or path.startswith(root.rstrip("/") + "/") for root in allowed):
        print(f"发现未指定改动：{path}（只允许：{' '.join(allowed)}）", file=sys.stderr)
        sys.exit(1)
PY

if git show-ref --verify --quiet "refs/heads/$branch"; then
  echo "本地分支已存在：$branch" >&2
  exit 1
fi
if git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
  echo "远程分支已存在：$branch" >&2
  exit 1
fi

if [ "$dry_run" = 1 ]; then
  printf 'DRY RUN: 分支=%s\n路径=%s\n测试=%s\npush=%s\ncreate_pr=%s\n' \
    "$branch" "${paths[*]}" "$test_cmd" "$push" "$create_pr"
  exit 0
fi

start_branch=$(git branch --show-current)
if [ -z "$start_branch" ]; then
  start_branch=$(git rev-parse HEAD)
fi
cleanup() {
  git checkout "$start_branch" >/dev/null 2>&1 || echo "无法恢复原分支：$start_branch" >&2
}
trap cleanup EXIT

git checkout -b "$branch"
git add -- "${paths[@]}"
if git diff --cached --quiet; then
  echo "没有可提交的改动" >&2
  exit 1
fi
git diff --cached --check
leak_scan=$(git rev-parse --git-path hooks/leak-scan.sh)
if [ -x "$leak_scan" ]; then
  git diff --cached -- . ':!uv.lock' | "$leak_scan" >/dev/null 2>&1
fi
if [ -n "$test_cmd" ]; then
  eval "$test_cmd"
fi
git commit -m "$msg"

if [ "$push" = 1 ]; then
  git push -u origin "$branch"
fi
if [ "$create_pr" = 1 ]; then
  gh pr create --base main --head "$branch" --title "${msg%%$'\n'*}" \
    --body "quickfix 安全通道：显式路径、diff/leak-scan、测试通过；不自动合并。"
fi
