# 自然语言候选提案与确定性生成

本章描述受约束的自然语言候选生成。模型负责提出候选修改，确定性层负责构造 `CandidateSet`；既有 `CandidateRunner` 仍负责执行、排名、确认和报告。它不是让模型直接编写完整 contract，也不是开放式搜索。

## 数据契约

### CandidateRule

字段：`path`、`values`、`template_kind`、`template_id`。

- `path` 是非空 tuple，组件只允许 string/int，不允许 bool。
- `values` 是非空 tuple，表示该路径允许选择的完整值域，不是范围表达式。
- configuration 规则的 `template_kind/template_id` 必须同时为 `None`；mechanism 规则必须同时提供非空字符串。
- 同一 `CandidateSpace` 中规则路径必须唯一，因此提案只需 path/value 即可唯一命中规则，不会发生模板歧义。

### CandidateSpace

字段：`base_contract`、`rules`、`max_candidates`，后者默认 4。

`base_contract` 是共享字段模板，提供 question、baseline build、stage、baseline arm、metric、protocol、budget 和 comparison_kind。它的 variant 只提供 arm ID 的形状，不会被当作额外候选，也不会把其中的 patch 或 build_override 夹带到生成结果。

`rules` 至少一项，`max_candidates` 必须容纳至少两个候选且不超过既有候选集上限。生成后仍须通过 `validate_candidate_set`，包括共享实验条件和总预算校验。

### CandidateProposal

字段：`path`、`value`、可选 `label`。

- 每个提案表示一次单路径修改；首版不支持一个提案同时修改多条路径。
- `label` 只是候选的 contract/spec 标识，不是结论或展示用自然语言。提供时必须匹配 `[A-Za-z0-9][A-Za-z0-9_-]*` 且在组内唯一；缺省时按提案顺序生成 `candidate-<index>`。
- path+canonical value 在组内必须唯一，不能用不同 label 重复提交同一修改。

三个模型都遵循既有递归冻结、严格 `from_dict`、未知字段拒绝和 canonical JSON round-trip。

## 确定性生成规则

`research_protocol.CandidateGenerator.build_candidate_set(space, proposals)` 接受至少两个、不超过 `max_candidates` 的提案，并只产出现有 `CandidateSet`。

所有提案先命中唯一规则路径，再检查值是否属于规则值域。成员比较使用 canonical JSON 类型语义；不把字符串猜成数字、ID 或布尔值。唯一例外是 mechanism 数值按契约统一转换为 float 后比较和生成。

### configuration

生成器深拷贝 `base_contract.experiment.build`，只在提案指定的已存在路径写入值：

- mapping key 必须已存在；list 索引必须是有效非负 int；
- 不允许新增/删除节点、用 bool 冒充数值或写入非有限数；
- 新值与原值类型兼容：字符串、布尔、null、对象和数组保持原 JSON 类型；int 不接受 float，float 可接受有限 int/float 并统一为 float；
- 修改后的 canonical JSON 必须不同于原值，拒绝 no-op。

最终 variant 使用完整修改后 build 作为 `build_override`，`world="canonical"` 且无 patches。baseline build、stage、metric、protocol 和 budget 不变。

### mechanism

规则必须提供 template kind/id。生成器创建 `op="set_number"`、值为 float 的单条 `MechanismPatch`，variant 使用 `world="hypothetical"` 且无 build_override。

loader 前由 `validate_patch_reference` 检查模板引用和路径形状；loader 后仍由既有 `validate_contract` 检查模板真实存在、路径存在以及原值是有限数值。生成器不读取文件，也不绕过两阶段校验。

## MCP 与宿主关联

`submit_candidate_proposals` 只接受 `candidate_space_json` 和 `candidate_proposals_json` 两个纯字符串。前者是一个 space 对象，后者是 proposal 数组。字符串传输避免 JavaScript 改变浮点数的 JSON 表示。

`ResearchGateway.submit_candidate_proposals()` 确定性构造候选集后调用既有 `submit_candidate_set`；调用方不能传 selected、效应值、CI 或报告。响应沿用 `candidate_report_id`、`candidate_set_id`、`status` 和完整 `report`。

DSH 宿主把研究问题与固定 space 交给模型，但不预先提供 proposals。运行后必须：

1. 找到唯一一次 `submit_candidate_proposals` 调用，且没有额外实验调用；
2. 要求工具输入中的 space 与宿主原始 canonical space 逐字一致；
3. 从实际 tool_call 解析 proposals，并核对成功 tool_result 的候选集和报告身份；
4. 通过 `validate_candidate_proposals_report` 按实际提案重建候选集，只读重算并核对既有报告。

自然语言最终文本始终不可信，不能替代这些机械检查。

## 范围与限制

- 报告保留实际提交的全部候选及失败，但模型可以在执行前选择规则值域的子集；本功能不声称穷举 space，也不证明全局最优。
- 当前一个提案只修改一条路径；组合修改、自动扩展值域和自适应多轮搜索不在首版。
- configuration 的 no-op 在生成时拒绝；mechanism 的模板真实路径和原值在加载后校验。
- 既有 dev/holdout、Bonferroni、不可变 artifact、`simulated/pending_real_validation` 和仅限当前候选集的 scope 不变。
- 当前仍为单进程顺序执行；异步调度、共享 Memory 和真实游戏校准不在本章实现范围内。
