# research_schema

确定性研究后端的纯数据契约。本包只依赖 Python 标准库，不导入 `sim`、
`research_protocol` 或 `research_core`。

## 内容

- `models.py`：frozen dataclass。序列字段统一转为 tuple，mapping 递归包装为
  `MappingProxyType`，嵌套输入在构造时深拷贝，对象自身也不能原地改写；所有模型支持
  `to_dict()` / `from_dict()` 的普通 JSON dict/list 形状往返，并拒绝未知字段。
- `canonical.py`：`canonical_json()`、`canonical_bytes()`、`content_hash()` 是唯一的
  canonical JSON 与内容哈希入口；`canonical_round()` 只用于可信内核输出，统一六位小数。

Canonical JSON 按键排序、保留 Unicode、使用紧凑分隔符并拒绝 NaN/Inf。不支持的对象
直接抛错，不做字符串强转；原始模拟数值不会因存储而被 `canonical_round()` 改写。

## 边界

`ResearchContract` 首版只表达一个 baseline/variant 对照，预算只有 `max_runs`。
`MechanismPatch` 只声明 `set_number`；路径是否存在、原值是否合法由
`research_protocol` 在执行前核对。`Claim.status` 只取 `accepted`、`rejected`、
`inconclusive`、`stale`。

本包不执行实验、不解析协议，也不创建 artifact store。
