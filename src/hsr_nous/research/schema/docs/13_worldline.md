# 单世界线证据链（worldline-v1）

本章描述与 paired-v1 平行的"单条脚本化世界线"证据链：`research/core/worldline.py` 的
`WorldlineRunner`、`research/core/artifacts.py` 的 worldline 方法对，以及
`research/core/fingerprint.py` 的 `collect_worldline_fingerprint`。

## 定位与边界

paired-v1 回答"机制 patch 是否改变指标分布"（arm/cohort/seed 坐标系，固定 64 runs）；
worldline-v1 回答"这一条完全声明的轨迹执行出来是什么"——`WorldlineSpec` → 一次
确定性执行 → 一个不可变 `WorldlineArtifact`。边界：

- 不共用 paired 的 arm/cohort/seed 坐标，不产生 `RunRecord`/`ComparisonSet`；
- 不进 `ReportComposer`/`ClaimValidator`，`resolve_evidence` 不认 worldline
  （paired 证据下钻的世界线版本未实装）；
- 不接 Agent 桥、前端、workbench 与 CandidateSet。

## WorldlineSpec

输入契约（frozen dataclass，字段递归只读）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `build` | Mapping | build 声明，必须含 `"build"` 键 |
| `stage` | Mapping | 关卡声明 |
| `random_values` | tuple[float, ...] | 固定随机序列，逐项实数且 0 ≤ v < 1 |
| `initial_sp` | int \| None | 开局战技点（缺省走引擎缺省） |
| `initial_energy_ratio` | float \| None | 开局能量比（缺省走引擎缺省） |
| `derived_from` | Mapping \| None | 父世界线引用（派生声明），形状与语义见「派生与父链」节；缺省 None = 独立世界线 |

构造期校验（违反即拒）：

- `build["build"]["policy"]["mode"]` 必须 == `"scripted"`——世界线是声明轨迹，
  非 scripted 策略拒收；
- `random_values` 逐项校验语义同 `ScriptedRandom`（拒 bool/非实数/NaN/越界），
  并归一化为 float（canonical JSON 里 `0` 与 `0.0` 字节不同，归一化保证身份稳定）；
- `derived_from` 非 None 时必须是 mapping，键集闭集
  `{worldline_id, content_hash, note}`：`worldline_id`/`content_hash` 逐项匹配
  `^[0-9a-f]{64}$`（64 位小写十六进制 SHA-256），`note` 若存在必须是 str；
- `spec_hash` property = `content_hash(spec)`，发布与读时重算共用。

## 世界线指纹

`collect_worldline_fingerprint(spec)` 返回 plain dict，键集是 paired 研究指纹
（`VersionFingerprint`）的 worldline 投影：

| 键 | 来源 |
|---|---|
| `rulebook_hash` / `fixtures_hash` / `data_hash` | 复用 `sim.montecarlo.collect_version_fingerprint` |
| `policy_hash` | 绑定 `spec.build["build"]["policy"]` 的 canonical JSON 文本 |
| `implementation_hash` | `sim`/`sim_schema`/`research` 源码 + `uv.lock` 内容哈希 |
| `config_hash` | `content_hash({build, stage, random_values, initial_sp, initial_energy_ratio})` |
| `git_commit` | 信息字段，**不参与身份**（同 trial 惯例） |
| `schema_version` | 恒 `"worldline-v1"` |

不含 paired 专属的 `variant_hash`/`protocol_id`/`artifact_schema_version`。
随机序列经 `config_hash` 进入指纹：**改随机序列 = 改世界线身份**。

## 身份公式

```text
worldline_id = content_hash({
    "worldline_spec": spec.to_dict(),
    "worldline_fingerprint": {**fingerprint, "git_commit" 剔除},
})
```

镜像 `_fingerprint_identity` 的原则：`git_commit` 只是信息字段，同 spec 同内容指纹
必然同 `worldline_id`；声明或配置任何变化（含随机序列）必然变 ID。

## WorldlineArtifact

执行证据（frozen dataclass）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `worldline_id` | str | 身份哈希，绑定 spec + 指纹 |
| `spec` | WorldlineSpec | 嵌入的声明副本 |
| `fingerprint` | Mapping | 执行时收集的内容指纹（冻结视图） |
| `status` | str | `"completed"` / `"failed"` |
| `observed` | Mapping | completed 时为 `asdict(classify_outcome(...))` + `turn_count` + 随机审计两键；failed 时为空 |
| `events` | tuple[Mapping, ...] | structured 事件，含 `event_id`/`ordinal`/`payload` |
| `final_save` | Mapping \| None | 引擎 `save_state()` 全精度终态；failed 恒 None |
| `modifiers` | tuple[Mapping, ...] | 终态 modifier 全字段，含 `modifier_id` |
| `caveats` | tuple[str, ...] | 编译 caveats 的 canonical 文本行 |
| `failure_reasons` | tuple[str, ...] | failed 时非空，`"{TypeName}: {message}"` |
| `schema_version` | str | 恒 `"worldline-v1"`，构造期强制 |

结构性自检：completed 要求 `final_save` 非空且 `failure_reasons` 为空；failed 要求
`final_save` 为 None 且 `failure_reasons` 非空。读时另有深度重算（见下）。

observed 的随机审计两键：`random_total == len(spec.random_values)` 且
`random_consumed == random_total`——`run_scripted` 内部强制随机序列恰好耗尽，
审计键把"恰好消费"固化进证据，读时交叉核验。

## 存储布局

```text
<research_root>/artifacts/worldlines/<worldline_id>/
├── spec.json         # {worldline_id, spec, fingerprint, spec_hash}
└── worldline.json    # WorldlineArtifact.to_dict() + content_hash
```

与 trial 布局同纪律：canonical JSON 字节、mkstemp + fsync + chmod 0o444 +
`os.replace` 原子发布、同 ID 同字节幂等 no-op、同 ID 不同字节
`ArtifactConflictError` 永不覆盖。不写 metadata.json——单发执行无断点需求。

## 执行与失败保留

`WorldlineRunner.run(spec, *, skip_existing=False)`：

1. 收集指纹、`publish_worldline_spec`（幂等）；
2. `skip_existing` 且 worldline.json 已存在 → `read_worldline` 直接返回
   （幂等重跑语义，同 trial 的 skip_existing）；
3. `compile_encounter(spec.build, spec.stage)` 取 caveats；
4. `run_scripted(...)`，prepare 回调挂法镜像 `TrialRunner._execute`：
   `StructuredLogger` 在 setup 前挂、`engine.setup()`、`RunRecorder` 在
   setup 后 run 前挂；
5. 成功：observed/events/modifiers/final_save 组装镜像 TrialRunner，
   status="completed"；
6. **任何异常（编译失败、脚本失配、随机耗尽）→ status="failed" 的
   artifact**：observed 空、events/modifiers 空、final_save None、
   failure_reasons 记 `"{TypeName}: {message}"`——失败世界线同样发布、同样可读，
   不删样本（镜像 paired 的失败保留）；
7. `publish_worldline` 后返回 `read_worldline` 的结果（读时校验过的对象）。

`final_save` 是引擎整机存档（`save_version=1` 纯数据），可直接喂回
`CombatEngine.load_state(..., rng=ScriptedRandom(...))` 续跑（存档恢复契约见
sim/save_load.py）。

## 读时重算与篡改拒绝

`read_worldline(worldline_id)` 逐项重算（镜像 `read_run`/`_validate_run_evidence`）：

1. `read_worldline_spec` 先校验 spec.json：字节 canonical、`spec_hash` 相符、
   `worldline_id` 与 spec+指纹（去 git_commit）重算一致；
2. worldline.json 字节 canonical 且 `content_hash` 重算相符；
3. 构造 `WorldlineArtifact`（契约不变量违反 → IntegrityError）；
4. 嵌入 spec/指纹与已发布 spec.json 对账（`result does not match its
   published spec` 同款语义）；
5. completed：`final_save.state` 存在，`observed.total_damage`/
   `truncated`/`action_value`/`turn_count` 与 state 逐键一致（
   `action_value` 对 `state.clock`），随机审计与 `len(spec.random_values)`
   一致；failed：`failure_reasons` 非空且 `final_save` 为 None；
6. events 的 ordinal 必须恰为 `range(n)` 冻结序，每条 `event_id` 以
   worldline_id 为坐标重算；modifiers 每条 `modifier_id` 重算；
7. `schema_version == "worldline-v1"`；
8. 携带 `derived_from` 时父链完整校验（见下节「派生与父链」）。

`verify_worldline(store, worldline_id)` 是读时全量校验的便捷入口，直接转发
`read_worldline`。

## 派生与父链（lineage）

世界线支持声明式派生：子代 spec 的 `derived_from` 记录父代身份与父代
worldline.json 的 content_hash，把"这条世界线是从哪条改出来的"固化进证据链。

### derived_from 形状

```json
{"worldline_id": "<64 位小写 hex>", "content_hash": "<64 位小写 hex>", "note": "<可选人类可读说明>"}
```

- `worldline_id`：父代身份哈希；
- `content_hash`：父代 worldline.json 的 `content_hash` 字段值，即
  `content_hash(父 artifact.to_dict())`——与 `publish_worldline` 发布时的
  存储哈希同公式，派生即对父代证据字节的内容寻址引用；
- `note`：可选，人类可读派生说明（如"窗口条目微调重跑"）。

### 身份绑定

`derived_from` 是 `WorldlineSpec` 字段，自然进入 `spec.to_dict()` 并参与
worldline_id 哈希——**改父子关系必然改子代身份**；同时 worldline.json 内嵌
spec 与已发布 spec.json 的既有对账（「与已发布 spec 一致」校验）保证两份副本
一致。任何单边篡改都会在身份重算或 spec 对账处触发 IntegrityError。

### 派生便捷函数

`research/core/worldline.py` 的 `derive_child_spec(parent, *, script=None,
ultimate_script=None, random_values=None, initial_sp=None,
initial_energy_ratio=None, note=None)`：

- deepcopy 父代 spec.build 后按非 None 覆盖项替换：`script` →
  `build["build"]["policy"]["script"]`，`ultimate_script` → 同 policy 的
  `ultimate_script`，`initial_sp`/`initial_energy_ratio` 替换顶层对应字段，
  `random_values` 给则使用（转 tuple）；
- **未指定的字段一律继承父值**——压缩优先：派生是声明式覆盖，不引入 diff 格式；
- 组 `derived_from = {"worldline_id": parent.worldline_id,
  "content_hash": content_hash(parent.to_dict()), 可选 note}`；
- 父代是 failed artifact 允许派生——"修脚本错误再跑"是合法场景
  （`derive_child_spec` 不检查父 status）。

### 读时父链校验

`read_worldline` 在上述校验之后追加 `_validate_worldline_lineage`：
**迭代**上溯（非递归，深度即链长），visited 集防环——首跳
`parent_id == 自身 worldline_id` 即自环，任何后续跳重复已见 id 即成环，
均抛 ArtifactIntegrityError。每一步：

1. 父代 worldline.json 必须存在于本 store（父缺失 = 孤儿派生， IntegrityError，
   报错带 parent_id）；
2. 父 payload 轻量校验：字节 canonical、content_hash 字段重算相符、payload
   的 worldline_id 字段与路径 id 一致；
3. 父 payload 重算哈希必须与子女 `derived_from.content_hash` 记录一致——
   链上每一环都是内容寻址，换父/改父必然断链；
4. 取父 spec 的 `derived_from` 继续上溯。

父代的**完整**契约校验（身份/证据/事件）由父代自己被 `read_worldline` 读取时
保证——本步只做链环对账，不递归 read_worldline（避免重复全量校验与不可控深度）。

### 发布宽松，读取严格

`publish_worldline` 不追父链（发布不做链上校验，与「读是闸」哲学一致）；
`WorldlineRunner.run` 末尾的 `read_worldline` 会自然拦截孤儿/断链/环——
派生世界线可以落盘，但读过才算数。

### 与 paired 链的边界

lineage 只活在 `worldlines/` 目录内：不动 trial/run/result 的
`parent_run_id` 体系，不进 `resolve_evidence`（worldline 证据下钻仍未实装），
世界线之间不构成 paired 证据——派生是谱系声明，不是统计对照。
