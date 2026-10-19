#!/bin/bash
# quickfix 通道：小改动不直推 main，一条命令走 "临时分支 → PR → auto-merge"。
# 用法: scripts/quickfix.sh "提交信息" [分支名]
set -euo pipefail
cd "$(dirname "$0")/.."
msg="${1:?用法: quickfix.sh \"提交信息\" [分支名]}"
branch="${2:-chore/quickfix-$(date +%m%d-%H%M)}"
git checkout -b "$branch"
git add -A
git commit -m "$msg"
git push -u origin "$branch"
url=$(gh pr create --base main --head "$branch" --title "$msg" --body "quickfix 通道提交，CI 绿后自动合并。")
gh pr merge "$url" --auto --squash || echo "auto-merge 未启用，CI 绿后手动合"
echo "PR: $url（auto-merge 已挂，CI 绿即合）"
