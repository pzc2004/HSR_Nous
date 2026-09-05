# 使用指南

各产品界面的用法汇总。设计/原理见 `docs/engine_design.md`；机制 spec 见 `docs/mechanics/`。

## 安装

```bash
# 核心 + dev
uv pip install -e ".[dev]"

# 含网页调试台（fastapi/uvicorn）
uv pip install -e ".[dev,web]"

# 全量可选（账号/屏幕识别/自动战斗，一般不需要）
uv pip install -e ".[dev,account,screen,pilot,web]"
```

## 数据更新（`hsr-data-update`）

游戏数据是模拟器的输入，存 `data/`（gitignored）。

```bash
hsr-data-update                 # 角色/光锥/遗器等（StarRailRes，英文）
hsr-data-update --lang cn       # 简体中文
hsr-data-update --enemies       # 敌人（遗留源 theBowja）
hsr-data-update --stages        # 关卡编成（深渊，含异相仲裁）
hsr-data-update --ssh           # 用 SSH 下载（国内更快）
hsr-data-update --data-dir DIR  # 指定数据目录
```

红线：只接入**已正式上线版本**的数据；版本更新后跑一遍即可。

## 模拟战斗 CLI（`hsr-sim`）

### `hsr-sim run <build.yaml> <stage.yaml>`

一把梭跑完整场出战报：总伤害/分伤/轮次/行动数（`--log` 附全战斗日志）。
可选 `--mode expected|roll`（期望值=不掷骰 / roll=按种子掷骰）、`--seed N`。

### `hsr-sim debug <build.yaml> <stage.yaml>`

交互调试 REPL（`--no-rewind` 关闭回退、`--checkpoint-interval N` 调检查点间隔）。
提示符 `(oronyx)`，手动模式默认开（我方决策点会问你）。

| 命令 | 作用 |
|------|------|
| `step` / `s` | 推进一个单位的一动 |
| `continue` / `c` | 连跑到断点或终局 |
| `break turn <n>` / `break actor <名或id>` | 设断点 |
| `breaks` / `clear` | 查看 / 清空断点 |
| `bar [n]` | 行动条预览（前 n 个，含预计时刻） |
| `field` | 全场概览（时钟/战技点/各单位血线能量） |
| `inspect <名或id>` / `i` | 单单位检视（HP/能量/韧性/modifier/资源/形态） |
| `log [n]` | 最近 n 条战斗日志 |
| `trace [n]` | 轨迹表（最近 n 动：谁/时刻/回合类型） |
| `snapshot [--out 文件]` | 当前局面快照（JSON） |
| `back [n]` | 回退 n 动 |
| `goto <n>` | 跳到第 n 动（前跑后放） |
| `manual` / `auto` | 手动接管决策 / 交还编译策略 |
| `help` / `quit` | 帮助 / 退出 |

## 网页调试台（`hsr-sim web`）

```bash
uv run hsr-sim web <build.yaml> <stage.yaml> [--port 8000] [--no-open] [--mode expected|roll] [--seed N]
```

起本地 FastAPI + 浏览器单页（默认自动开 `http://127.0.0.1:8000`）。布局：顶部敌人卡（HP/韧性/弱点）、
左侧行动条、底部我方卡（HP/能量/战技点 pips/终结技就绪）、中央决策区、底部日志流。

操作（与游戏本体同构）：

| 输入 | 作用 |
|------|------|
| `Q` 普攻 / `E` 战技（或点行动按钮） | 进入瞄准态（行动卡带作用域：单体/扩散/群攻/弹射/自身） |
| 瞄准态下 `←`/`→` 或 `A`/`D` | 移动目标箭头（**目标记忆**：默认上次选的对象；扩散会高亮主目标±1 相邻） |
| 瞄准态下按另一行动键（Q↔E） | 直接切换行动（免取消） |
| 瞄准态下 `Enter` / `空格` / 再按同键 / 点目标卡 | 确认释放 |
| `Esc` / 右键 | 取消瞄准 |
| `1`-`4`（终结技窗口弹出时） | 释放对应站位角色的终结技；`Esc` 跳过（能量保留） |
| 单步 / 连续 / 回退 / 跳转 / 断点按钮 | 同 CLI |
| 点单位卡 | 弹该单位 inspect JSON |
| 「重新开始」 | 贴 build/stage YAML 重开一局 |

## 输入格式

### build.yaml（编队 + 策略）

```yaml
build:
  team:
    - character_template: "1308"   # 引用 data/sim_templates/characters/1308_黄泉.yaml
      level: 80
      eidolon: 0
      # 或 inline 内联（测试用）：character_template: "inline" + base_stats/actions 全写
  policy:
    action_rules:                  # 条件（表达式）→ 行动 + 优先级，首个命中生效
      - {condition: "energy >= max_energy", action: "ultimate", priority: 90}
      - {condition: "skill_points > 0", action: "skill", priority: 50}
      - {condition: "true", action: "basic", priority: 0}
    target_rules: []               # 条件 + 选择器（lowest_hp/broken/highest_atk/random…）
    parameters: {}
```

### stage.yaml（敌人 + 终止条件）

```yaml
stage:
  enemies:
    - {actor_id: "e1", name: "王下一桶", level: 80, hp: 300000, spd: 90,
       weakness: ["thunder"], max_toughness: 120}
  termination: {mode: "fixed_av", max_action_value: 1500}   # 或杀光即停
```

## 数据查询（`query-game-data`）

```bash
python3 .agents/skills/query-game-data/query.py <entity_type> <查询>
# entity_type: character | light_cone | relic | enemy | list <characters|light_cones|relic_sets|enemies>
# 例：.../query.py character 昔涟   .../query.py light_cone 23042   .../query.py enemy 1002011
```

规则：查机制/数值/中英文名用它（不要直读 data 原始 JSON）；查不到先跑 `hsr-data-update` 再报不存在。

## LLM 配置（`.env`，gitignored）

统一 `HSR_NOUS_LLM_` 前缀、按用途分组（OpenAI 兼容协议）：

| 变量 | 用途 | 说明 |
|------|------|------|
| `HSR_NOUS_LLM_AGENTS_{API_KEY,MODEL,API_BASE}` | agents 分支 ReAct 层 | 归 agents 分支配置 |
| `HSR_NOUS_LLM_ANNOTATOR_{API_KEY,MODEL,API_BASE,EFFORT}` | 机制标注流水线 | `EFFORT=max` 时 reasoning 吃 max_tokens 预算，输出额度给足 |

## 机制标注流水线（在建）

`adapters/mechanism_annotator.py`：LLM 把角色/光锥/遗器的机制文本翻译成 DSL hooks（机械层=代码已完工，
语义层=LLM 标注），每实体四级验证（lint → compile → 回读 → 行为冒烟/对拍），失败带错误反馈自愈重试。
运行期状态 `data/annotator/run_state.json`（gitignored 自建）断点续跑（中断后自动接着跑，
`--no-resume` 关 / `--fresh` 清空重跑）；热更文件在仓库树外
`~/.config/hsr_nous/annotator_live_config.json`（含端点/模型等部署事实，不放 data/），
运行中改端点/模型/effort/并发生效于之后的派发。用法见 `--help` 与模块 docstring。
