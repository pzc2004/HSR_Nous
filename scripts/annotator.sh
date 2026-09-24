#!/bin/bash
# 打标调度入口（annotator DAG dispatcher——compile/smoke 闸、LLM 自检、DAG 可视化、
# 批量调度的统一壳。历史：原为打标装备隔离会话的 Bash 白名单唯一面，rig 已退役
# 并入 DAG（2026-09-24），本件保留为 DAG/主会话共用 dispatcher）。
#
# 子命令：
#   query <entity_type> <query>   —— 查游戏数据（query-game-data skill）
#   check <template.yaml>         —— 编译闸（词表/静态校验/param()/资源闸）
#   smoke <template.yaml> [max_av]—— 编译 + 沙包局开战冒烟（fixed_av 截断）
#   ping                          —— LLM API 连通性自检（换 API 后第一件事；永不回显 key）
#   dag [--port 8010]             —— DAG 可视化（运行图实时渲染，零硬编码）
#   batch [--ids a,b|--limit N]   —— 批量打标（全花名册断点续跑；默认跳锚，--include-anchors 放行）
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
  dag)
    exec uv run python3 -m hsr_nous.ops.annotator.web "$@"
    ;;
  batch)
    exec uv run python3 -m hsr_nous.ops.annotator.batch "$@"
    ;;
  *)
    echo "用法: bash scripts/annotator.sh <query|check|smoke|ping|dag|batch> [参数...]" >&2
    exit 2
    ;;
esac
