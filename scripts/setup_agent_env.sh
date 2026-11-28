#!/bin/bash
# 在项目内准备固定版本 DSH；不全局安装，不修改用户既有 DSH_HOME。
set -euo pipefail
cd "$(dirname "$0")/.."

DSH_VERSION="0.2.1-rc.2"
DSH_DIR="external/dsh"
DSH_BIN="$DSH_DIR/node_modules/.bin/dsh"

for cmd in node npm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "缺少命令：$cmd（请先安装并加入 PATH）" >&2
    exit 1
  fi
done

mkdir -p "$DSH_DIR"
npm --prefix "$DSH_DIR" install --save-exact --no-audit --no-fund \
  "@deepseek-ai/dsh@$DSH_VERSION"
# 功能冒烟：--version 须非空——Node < 22.18 时 import.meta.main 未定义，
# DSH 入口静默 no-op（exit 0 零输出），只信 exit 0 会被骗过。
dsh_version="$("$DSH_BIN" --version 2>&1)"
if [ -z "$dsh_version" ]; then
  echo "DSH --version 空输出：入口静默 no-op（常见于 Node < 22.18，import.meta.main 未定义）；请升级 Node >= 22.18" >&2
  exit 1
fi
printf 'DSH 版本：%s\n' "$dsh_version"
printf 'DSH 可执行文件：%s\n' "$DSH_BIN"
