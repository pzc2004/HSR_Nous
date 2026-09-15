# tribios / 缇里西庇俄丝——LLM 统一接入层名册卡

- **代号**：tribios / 缇里西庇俄丝——「碎作千片」、分赴各地传递神谕 ↔ 多 key 并发承运调用
- **职责**：项目级 LLM 调用统一 infra——多 key 管理（逗号分隔，每 key 独立并发额度）、
  每 key 并发可配、**流式任务调度**（完成一个立刻补一个，不等批）、限次重试 + dead 人工队列、
  **热更新**（live_config.json：运行中改端点/模型/effort/并发，不重启生效于之后的派发）
- **特批**：半神名跨层级使用（owner 裁决）——引擎**内部组件**仍走泰坦级名册
  （janus/talanton/…，见 `src/hsr_nous/sim/README.md`）；本模块非引擎内，特批登记于此
- **边界**：`llm/` 零项目依赖（只标准库 + httpx）；`adapters`/`agents`/`api` 可 import
- **租户**：① `adapters/mechanism_annotator.py`（机制标注流水线，首个租户）；
  ② agents 层 / 将来 evaluator 接入时复用同一 `LLMClient` + `Scheduler`

## 配置规范速查

```
HSR_NOUS_LLM_<USE>_API_KEY=key1,key2   # 逗号分隔多 key，每 key 独立并发额度
HSR_NOUS_LLM_<USE>_MODEL=...
HSR_NOUS_LLM_<USE>_API_BASE=https://...
HSR_NOUS_LLM_<USE>_EFFORT=max          # reasoning_effort 透传，有值才带
HSR_NOUS_LLM_<USE>_CONCURRENCY=4       # 每 key 并发上限，默认 4
HSR_NOUS_LLM_<USE>_POOL=[{...},{...}]  # 号池：端点优先级链（JSON 数组，见下）
```

### 号池（按各 key 并发上限分配 + 判死出池）

`POOL` = JSON 数组，元素 `{api_base, model, api_key, extra_headers?, concurrency?}`
（`api_key` 支持逗号分隔；`concurrency` 缺省 0=不限）。**并发仅两处**：

- **key 并发**（本模块统一调配）：每槽一把信号量，每次调用按数组顺序取第一个
  「活着且有空」的槽用——A 满了溢出落 B（容量分配，不排队；全满才等最前活槽空出）
- **流水线外层并发**：调用方自理（如 annotator `batch_workers`）

`client.chat` 语义：

- **auth/quota 判死出池**（HTTP 401/402/403 或报文含 quota/balance/insufficient/额度）
  → 该槽标记出池不再分配，本调用落下一个活槽重发；活槽全灭抛 `LLMError`
- 429/5xx 传输族 → 槽内指数退避重试；400/空 content 等确定性错误 → 当场抛（不换槽）
- 空 `POOL` = 单端点旧径（行为与引入号池前逐比特一致）
- v1 只走 env 配置（live config 热更不接 pool——换槽需求重起进程读 env 即生效，
  与 runs_root 断点续跑同节奏）

## 热更新（live config）

`LiveConfig` 监视租户口径的热更文件（标注流水线缺省
`~/.config/hsr_nous/annotator_live_config.json`——仓库树外：内含端点/模型等部署事实，
不放 data/ 免被整体拷贝外泄；首次运行以 env 值物化；api_key 只从 env 读、永不进文件）。
`Scheduler(client, live=live)` 挂上后每派发 tick 前查文件 mtime，变了才 reload，
且只生效于**之后的派发**：

- `concurrency` 调大 → 之后的派发立即加槽；调小 → 在飞自然回落（不杀在飞）
- `api_base` / `model` / `effort` → client `apply_endpoint` 重建 config（保留 key 列表），
  在飞任务在原端点跑完
- 进度行追加当前生效的 `model @ api_base · 并发 N/key`；文件非法沿用旧值并在进度行示警

断点续跑（run_state.json）是租户层能力，见 `adapters/mechanism_annotator.py` 模块 docstring。
