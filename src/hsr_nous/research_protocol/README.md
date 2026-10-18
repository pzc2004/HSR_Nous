# research_protocol

研究实验的固定协议与执行前校验。本包依赖 `research_schema`，不调用模拟器。

## paired-v1

首版唯一注册协议固定为：

- `mode="roll"`；dev seed 为 `0..15`，holdout seed 为 `16..31`，各 16 局且不相交；
- 两臂复用相同 seed 序列，`min_valid_n=16`，总 `required_runs=64`；
- paired percentile bootstrap 固定 2000 次、置信度 0.95、bootstrap seed 为 0；
- `max_runs` 可以大于 64，但不会改变 seed、样本量或 bootstrap 参数。

`resolve_protocol()` 只从注册表解析，dev/holdout 内部也不得有重复 seed。
`validate_patch_reference()` 是 loader 前置闸：校验 op、闭合 kind、仅由
`[A-Za-z0-9_-]+` 构成的 template_id、path 组件和新值基本合法性；core 在任何模板
加载前逐 patch 调用，完整 `validate_contract()` 仍在加载后复核路径和原值。
`validate_contract()` 不接受任何协议参数覆盖，并核对必填文本、预算、单一
baseline/variant、固定 metric 和 arm 世界标记；variant 至少声明一个 patch，patch 的
`template_kind` 只取 `characters` / `light_cones` / `relics` / `enemies`。patch 校验需要
调用方提供 `templates[template_kind][template_id]` 的只读模板映射，以确认路径已存在、
原值与新值均为有限数值且不是 bool；不会修改模板。

`validate_fingerprint()` 单独核对执行必需的内容指纹及其 `protocol_id` 绑定。
`git_commit` 只是可选信息字段；核心执行器下一步必须同时重跑这两类校验。

Dev 只用于探索，accepted 的方向性结论以后只能由 holdout 证据产生。holdout 失败、
截断或有效样本不足时不得静默丢样本后接受结论。本包不执行战斗、不计算 CI、
不生成 claim 或报告。
