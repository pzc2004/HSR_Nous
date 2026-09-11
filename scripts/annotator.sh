#!/bin/bash
# 打标工唯一可执行入口（打标装备第二档——隔离会话权限规则只放行本件：
# Bash(bash scripts/annotator.sh*)；本件位于 scripts/，worker 写权限只有 staging 改不到）。
#
# 子命令（全部经审，worker 无其他 Bash 面）：
#   query <entity_type> <query>   —— 查游戏数据（query-game-data skill）
#   check <template.yaml>         —— 编译闸（词表/静态校验/param()/资源闸）
#   smoke <template.yaml> [max_av]—— 编译 + 沙包局开战冒烟（fixed_av 截断）
#   ping                          —— LLM API 连通性自检（换 API 后第一件事；永不回显 key）
set -euo pipefail
cd "$(dirname "$0")/.."

cmd="${1:-}"
if [ $# -gt 0 ]; then shift; fi
case "$cmd" in
  query)
    exec python3 .agents/skills/query-game-data/query.py "$@"
    ;;
  check)
    exec uv run python3 scripts/annotator_check.py compile "$@"
    ;;
  smoke)
    exec uv run python3 scripts/annotator_check.py smoke "$@"
    ;;
  ping)
    exec uv run python3 -m hsr_nous.ops.annotator.ping
    ;;
  *)
    echo "用法: bash scripts/annotator.sh <query|check|smoke> [参数...]" >&2
    exit 2
    ;;
esac
