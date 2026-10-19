#!/bin/bash
# 统一准备本地与 CI 的全量测试环境：Python 项目包、Release 数据快照、
# 生成件、optimizer 对拍依赖和 Playwright。可重复执行；已有完整数据默认复用。
set -euo pipefail
cd "$(dirname "$0")/.."

OPTIMIZER_COMMIT="d68d14cf63bc5c2be448b40822588fe95b86066e"
PLAYWRIGHT_VERSION="1.61.0"
OPTIMIZER_DIR="external/hsr-optimizer"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令：$1（请先安装并加入 PATH）" >&2
    exit 1
  fi
}

for cmd in uv git curl tar node npm; do
  require_cmd "$cmd"
done

if [ ! -d .venv ]; then
  uv venv
fi
uv pip install -e ".[dev,account,web,agent]"

required_data=(
  data/starrailres/index_new/cn/characters.json
  data/stages/hakushin/maze.json
  data/turnbasedgamedata/MonsterTemplateConfig.json
  data/fandom_enemy_data.json
)
need_data=0
if [ "${CI:-}" = "true" ] || [ "${TEST_ENV_REFRESH_DATA:-0}" = "1" ]; then
  need_data=1
else
  for path in "${required_data[@]}"; do
    if [ ! -f "$path" ]; then
      need_data=1
      break
    fi
  done
fi

if [ "$need_data" = "1" ]; then
  mkdir -p data
  snapshot_url=$(.venv/bin/python -c \
    "from hsr_nous.pipeline.pins import snapshot_url; print(snapshot_url())")
  echo "恢复数据快照：$snapshot_url"
  curl -fSL "$snapshot_url" | tar -xz -C data
else
  echo "数据文件完整，复用现有 data/（TEST_ENV_REFRESH_DATA=1 可从 Release 强制刷新）"
fi

.venv/bin/python -m hsr_nous.adapters.template_generator
if [ ! -f data/tbgd_skill_data.json ]; then
  .venv/bin/python -m hsr_nous.pipeline.extract_tbgd_skills
fi

if [ -e "$OPTIMIZER_DIR" ] && [ ! -d "$OPTIMIZER_DIR/.git" ]; then
  if [ -n "$(ls -A "$OPTIMIZER_DIR")" ]; then
    echo "$OPTIMIZER_DIR 已存在但不是 Git 仓库；请先移走该目录再运行" >&2
    exit 1
  fi
fi
if [ ! -d "$OPTIMIZER_DIR/.git" ]; then
  mkdir -p external
  git clone --depth 1 https://github.com/fribbels/hsr-optimizer.git "$OPTIMIZER_DIR"
fi
current_optimizer=$(git -C "$OPTIMIZER_DIR" rev-parse HEAD)
if [ "$current_optimizer" != "$OPTIMIZER_COMMIT" ]; then
  git -C "$OPTIMIZER_DIR" fetch --depth 1 origin "$OPTIMIZER_COMMIT"
  git -C "$OPTIMIZER_DIR" checkout --detach "$OPTIMIZER_COMMIT"
fi
npm --prefix "$OPTIMIZER_DIR" ci --no-audit --no-fund

uv pip install "playwright==$PLAYWRIGHT_VERSION"
if [ "${CI:-}" = "true" ]; then
  .venv/bin/playwright install --with-deps chromium
else
  .venv/bin/playwright install chromium
fi

printf 'Python: '; .venv/bin/python --version
printf 'Node: '; node --version
printf 'Playwright: '; .venv/bin/python -c \
  "import importlib.metadata; print(importlib.metadata.version('playwright'))"
printf 'Optimizer: '; git -C "$OPTIMIZER_DIR" rev-parse --short=12 HEAD
echo "测试环境就绪。全量回归：.venv/bin/python -m pytest tests/ -q -rs"
